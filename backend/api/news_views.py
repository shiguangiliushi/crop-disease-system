from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.pagination import PageNumberPagination
from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import Http404
import logging

from .models import News
from .serializers import NewsSerializer
# 第 91 批：图片上传统一校验（大小上限 + 按文件头探测真实格式 + 随机文件名）
from .image_validation import (
    ALLOWED_FORMATS,
    ImageValidationError,
    validate_image_upload,
)

#: 新闻配图允许的格式（不含 BMP：编辑器插图用不到，且体积偏大）
NEWS_IMAGE_FORMATS = {k: v for k, v in ALLOWED_FORMATS.items() if k != 'BMP'}


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


logger = logging.getLogger(__name__)


class NewsViewSet(viewsets.ModelViewSet):
    """
    行业新闻API
    - 所有用户可查看已发布的新闻；管理员可查看全部
    - 管理员可创建、编辑、删除新闻（作者本人也可编辑自己的新闻）
    """

    serializer_class = NewsSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = StandardResultsSetPagination
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_serializer_context(self):
        """确保 request 对象被传入序列化器（用于拼接完整图片地址）"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    @staticmethod
    def _is_admin(user):
        """管理员判定：is_staff / is_superuser / role=ADMIN（与前端 isAdmin 对齐）"""
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_staff
                or user.is_superuser
                or getattr(user, 'role', None) == 'ADMIN'
            )
        )

    def get_permissions(self):
        """
        权限划分：
        - 列表 / 详情：任何人可读
        - 新增：仅管理员
        - 修改 / 删除：管理员或该新闻作者
        """
        # 只读动作对所有人开放（含旧版兼容接口 legacy_detail）
        if self.action in ['list', 'retrieve', 'recent', 'legacy_detail']:
            return [permissions.AllowAny()]

        user = self.request.user
        if not user or not user.is_authenticated:
            return [permissions.IsAdminUser()]

        if self._is_admin(user):
            return [permissions.IsAuthenticated()]

        if self.action in ['update', 'partial_update', 'destroy']:
            try:
                if self.get_object().author_id == user.id:
                    return [permissions.IsAuthenticated()]
            except Exception as e:  # 对象不存在等情况交给视图正常处理
                logger.warning('新闻权限检查出错: %s', e)

        return [permissions.IsAdminUser()]

    def get_queryset(self):
        """
        管理员可看到全部新闻（含未发布 / 等待定时发布），其他人只能看到"已发布且到点"的。

        管理员判定统一走 `_is_admin`，避免与 `get_permissions`、前端 `isAdmin`
        出现"三处口径不一"（本项目历史上已因此踩过坑，见完善记录第 17 批）。

        第 38 批：新增**定时发布** —— `published_at` 为空或已到点才对外可见；
        设成未来时间的新闻在到点前只有管理员能看到（管理页会显示"定时"状态）。
        """
        from django.db.models import Q
        from django.utils import timezone

        queryset = News.objects.all().order_by('-created_at')
        if self._is_admin(self.request.user):
            return queryset
        return queryset.filter(is_published=True).filter(
            Q(published_at__isnull=True) | Q(published_at__lte=timezone.now())
        )

    def create(self, request, *args, **kwargs):
        """
        新增新闻

        注意：这里直接把 request.data 交给序列化器。
        原实现做了 request.data.copy()，它会深拷贝上传文件；当图片超过
        2.5MB（FILE_UPLOAD_MAX_MEMORY_SIZE）时 Django 使用的是
        TemporaryUploadedFile（内部持有真实文件句柄），深拷贝会抛
        TypeError: cannot pickle '_io.BufferedRandom' object，导致 500。
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        """自动把当前用户设为发布人"""
        serializer.save(author=self.request.user)

    def list(self, request, *args, **kwargs):
        """
        新闻列表
        - 支持分页
        - 支持按标题 / 内容 / 全部搜索（search + search_type）
        - 支持按分类筛选（category）
        - 支持按发布状态筛选（is_published=true/false，仅对管理员有意义）
        """
        queryset = self.get_queryset()

        search_query = request.query_params.get('search', '')
        search_type = request.query_params.get('search_type', 'title')
        category = request.query_params.get('category')
        is_published = request.query_params.get('is_published')

        if search_query:
            if search_type == 'title':
                queryset = queryset.filter(title__icontains=search_query)
            elif search_type == 'content':
                queryset = queryset.filter(content__icontains=search_query)
            else:
                queryset = queryset.filter(
                    Q(title__icontains=search_query) | Q(content__icontains=search_query)
                )

        if category:
            queryset = queryset.filter(category=category)

        if is_published not in (None, ''):
            queryset = queryset.filter(
                is_published=str(is_published).lower() in ('true', '1', 'yes')
            )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """
        新闻详情

        ⚠️ 这里必须显式捕获 `Http404`：
        `get_object()` 在"对象不存在 **或已下架（对非管理员不可见）**"时抛的是
        DRF 包装过的 `Http404`，**不是** `News.DoesNotExist`。原实现只捕获后者，
        于是 Http404 落进最后的 `except Exception` 兜底分支，把一个正常的 404
        变成了 **500**。实测（修复前）：

            匿名 GET /api/news/25/（已下架）  -> 500 {"error":"服务器内部错误"}
            匿名 GET /api/news/999999/（不存在） -> 500 {"error":"服务器内部错误"}

        用户点开一条已下架新闻的旧链接，因此看到的是"服务器错误"，而不是
        "新闻不存在或已下架"，这也是"下架了但好像还能访问"的错觉来源之一。
        """
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except (Http404, News.DoesNotExist):
            return Response(
                {'error': '新闻不存在或未发布'},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error('获取新闻详情时出错: %s', e, exc_info=True)
            return Response(
                {'error': '服务器内部错误'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def update(self, request, *args, **kwargs):
        """更新新闻（支持部分更新，可同时替换封面图片）"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial or True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def perform_update(self, serializer):
        serializer.save()

    @action(detail=False, methods=['get'])
    def recent(self, request):
        """
        新闻列表（兼容旧版接口）
        - 支持 params[key]=value 与 key=value 两种参数写法
        """
        params = {}
        for key in request.query_params:
            if key.startswith('params[') and key.endswith(']'):
                params[key[7:-1]] = request.query_params[key]
            else:
                params[key] = request.query_params[key]

        page_size = int(params.get('page_size', 12))
        search = params.get('search', '')
        category = params.get('category')
        is_published = params.get('is_published', 'true').lower() == 'true'

        queryset = self.get_queryset()

        # 原实现用的是 `request.user.is_staff`，与 get_queryset 的判定不一致
        # （role=ADMIN 但 is_staff=False 的账号会走到"非管理员"分支）。
        # 这里统一到 _is_admin，且非管理员无论如何都只返回已发布。
        if self._is_admin(request.user):
            queryset = queryset.filter(is_published=is_published)
        else:
            queryset = queryset.filter(is_published=True)

        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(content__icontains=search)
            )

        if category:
            queryset = queryset.filter(category=category)

        ordering = params.get('ordering', '-created_at')
        if ordering:
            queryset = queryset.order_by(ordering)

        paginator = self.pagination_class()
        paginator.page_size = page_size
        page = paginator.paginate_queryset(queryset, request)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='detail')
    def legacy_detail(self, request, pk=None):
        """
        获取新闻详情（兼容旧版接口 `GET /api/news/{pk}/detail/`）

        ⚠️ 本动作**绝对不能**命名为 `detail`：
        DRF 的路由在创建视图时会传入 `initkwargs={'detail': True/False, ...}`，
        视图实例上因此存在一个布尔属性 `self.detail = True`，它会把**同名的 action
        方法整个覆盖掉**；随后 `ViewSetMixin` 执行
        `setattr(self, 'get', getattr(self, 'detail'))`，`self.get` 就成了布尔值 `True`，
        请求时 `handler(request)` 直接抛
        `TypeError: 'bool' object is not callable`。

        实测（修复前）：`GET /api/news/12/detail/` 无论匿名还是管理员都 **100% 500**。
        现改名为 `legacy_detail`，并用 `url_path='detail'` 保持对外 URL 不变。
        """
        try:
            news = self.get_queryset().get(pk=pk)
            serializer = self.get_serializer(news)
            return Response(serializer.data)
        except News.DoesNotExist:
            return Response({'error': 'News not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser])
    def upload_image(self, request):
        """
        上传新闻图片，返回图片地址（只保存文件，不创建新闻记录）

        第 91 批（安全）：与通用图片上传同一套校验 ——
        大小上限、按**文件头**判断真实格式（不信任 `content_type`）、随机文件名。
        此前这里既没有大小上限，也直接用了用户给的 `image_file.name` 拼路径。
        """
        try:
            meta = validate_image_upload(
                request.FILES.get('image'),
                allowed_formats=NEWS_IMAGE_FORMATS,
                prefix='news_',
            )
        except ImageValidationError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 原实现是 News().image.save(..., save=True)，会插入一条 title/content 为空的
            # 新闻记录并触发数据库约束错误，这里直接落到媒体目录即可。
            name = default_storage.save(f'news_images/{meta["filename"]}', request.FILES['image'])
            image_url = request.build_absolute_uri(f'{settings.MEDIA_URL}{name}')
            return Response(
                {'url': image_url, 'image_url': image_url, 'message': '图片上传成功'},
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.error('图片上传失败: %s', e, exc_info=True)
            return Response({'error': '图片上传失败'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
