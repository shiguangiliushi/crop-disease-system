# 论坛接口（版块 / 帖子 / 评论 / 点赞 / 收藏 / 举报的处理）
# ============================================================================
# **这是后端第二大的视图文件**（1300 余行）。按 ViewSet 分块：
#   · `ForumBoardViewSet`  版块（含版主管理）
#   · `PostViewSet`        帖子：`get_queryset` 里有 8 个可选筛选 + 角色可见性
#                          + `?only_deleted`（回收站）+ 热度排序；
#                          另有 `like` / `favorite` / `likes`（谁赞了）三个 action
#   · `CommentViewSet`     评论与回复（含嵌套路由 `posts/<pk>/comments/`）
#   · `LikeViewSet`        直接点赞（`POST /api/forums/likes/`）
#
# 改这个文件前值得知道的几件事：
#   · **计数（like_count / comment_count / reply_count）由模型层维护**
#     （`models_forum.Like.save/delete`、`Comment.delete`），视图**不要**再自己加减 ——
#     第 106 批修的就是这类重复计数（视图又 `F()+1`，而模型已经重算过）；
#   · 帖子的**可见性**统一走 `Post.active` 管理器（软删除的行不能被点赞/评论）；
#   · 改 `get_queryset` 里任何一个筛选，都要同步看前端
#     `ForumBoardView.vue` / `ContentReviewView.vue` 传了什么参数；
#   · 本文件里已有若干"第 N 批"的 bug 记录（第 16 批预取缓存导致的计数为 0、
#     第 17 批回复数、第 91 批软删除、第 35 批一个不存在的通知方法导致必定 500）——
#     **动相关代码前先读那些注释**，它们记录的都是真实踩过的坑。
import logging  # 日志模块（原先该文件用 print 输出调试信息，现统一走 logging）

from rest_framework import viewsets, status, permissions, mixins, serializers  # 导入DRF相关模块
from .permissions import IsOwnerOrReadOnly, CanDeletePost  # 导入自定义权限类
from rest_framework.decorators import action, permission_classes, throttle_classes  # 导入DRF装饰器
from rest_framework.response import Response  # 导入DRF响应类
from rest_framework.pagination import PageNumberPagination  # 导入分页类
from rest_framework.throttling import UserRateThrottle  # 导入限流类
from django.db.models import Count, Q, F, Exists, OuterRef  # 导入Django查询工具
from django.utils import timezone  # 导入时区工具
from django.shortcuts import get_object_or_404  # 导入快捷函数
from django.core.exceptions import PermissionDenied  # 导入权限异常
from django.conf import settings  # 第 38 批：发帖审核策略开关
from django.contrib.auth import get_user_model  # 第 38 批：通知版主

# ---------------------------------------------------------------------------
# 点赞限流（第 106 批：从"魔法数字"提成具名常量）
# ---------------------------------------------------------------------------
# 原来这两个值以裸数字写在 `LikeViewSet.create` 里（`seconds=10` / `>= 5`），
# 而且变量名叫 `one_minute_ago` —— 名字说是"一分钟"、实际是 10 秒。
# 提到模块级并改名后，规则一眼可见，也便于测试直接引用（而不是硬抄数字）。
#
# 为什么是"10 秒 5 次"：这是**防误触/防脚本**的粗限流，不是精确配额。
# 正常用户连点 5 次赞已经算异常；真要刷赞也拦不住（换个账号即可）——
# 与 `CommentViewSet` 的"每分钟 3 条"同一个量级、同一个目的。
LIKE_RATE_WINDOW_SECONDS = 10
LIKE_RATE_LIMIT = 5

from .permissions import (  # 导入自定义权限类
    IsOwnerOrReadOnly, IsModeratorOrReadOnly, IsPostOwnerOrModerator,
    IsCommentOwnerOrPostOwner, IsBoardModerator, CanEditPost, CanDeletePost
)
# 第 124 批：能力判定统一收口；第 128 批：内容再分模块
# （版块管理 = BROADCAST；审核/评论处置/置顶加精 = review 模块）
from .capabilities import (
    IsBroadcastManager, CAP_BROADCAST, MODULE_FORUM, MODULE_REVIEW,
    has_capability, has_content_module, is_full_admin,
)

from .models_forum import ForumBoard, Post, Comment, Like, Favorite  # 导入论坛模型
from .serializers_forum import (  # 导入论坛序列化器
    ForumBoardSerializer, PostListSerializer,
    PostDetailSerializer, CommentSerializer,
    CommentCreateSerializer, LikeSerializer,
    LikeUserSerializer,  # 第 25 批：点赞者名单
)
from .pagination import CustomPagination  # 导入自定义分页类

User = get_user_model()  # 第 38 批：给版主发通知时需要

logger = logging.getLogger(__name__)
from .audit import log_admin_action  # noqa: E402  第 146 批：管理操作日志
from .bulk import parse_ids  # noqa: E402  第 147 批：批量接口的公共校验  # 日志记录器（配置见 settings.LOGGING 的 api 记录器）


def is_moderator(user):
    """版主判定：**内容维护者**（CONTENT 能力）或 Moderators 组成员

    第 24 批统一：`PostViewSet.perform_create` 原来只认 `is_staff` 与 Moderators 组，
    漏了 `role=ADMIN`（与项目其它处的口径不一致）；置顶/加精的权限判定也复用它。

    第 124/128 批：管理员那部分改为 `has_content_module(user, 'review')`（判定统一收口到
    `capabilities.py`）。语义不变（今天具备 CONTENT 的正是 is_staff / is_superuser /
    role=ADMIN），**第 125 批起信息编辑员（EDITOR）也能审核帖子、置顶加精** ——
    这些正是内容审核工作。Moderators 组那条路径保持原样。
    """
    if not user or not user.is_authenticated:
        return False
    # 第 151 批：`forum`（论坛交流）也算 —— 这个模块存在的意义就是
    # "只管论坛、不碰审核队列"，而置顶/加精/审帖/删评论都在这个判定之下。
    return bool(
        has_content_module(user, MODULE_REVIEW)
        or has_content_module(user, MODULE_FORUM)
        or user.groups.filter(name='Moderators').exists()
    )


class ForumBoardViewSet(viewsets.ModelViewSet):  # 定义论坛版块视图集
    """
    论坛版块视图集
    - 所有用户可查看版块列表和详情
    - 管理员和版主可创建/更新/删除版块
    - 支持版块排序、状态管理
    """
    serializer_class = ForumBoardSerializer  # 设置序列化器类
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]  # 设置权限类
    pagination_class = None  # 不需要分页

    def get_queryset(self):  # 定义获取查询集方法
        # 基础查询
        queryset = ForumBoard.objects.all()  # 获取所有版块

        # 版块维护者（BROADCAST 能力）与版主能看到停用的版块；其余人只看启用的。
        # 第 124 批：管理员那部分改为 has_capability(CAP_BROADCAST)，判定统一收口；
        # 语义与原来的 is_staff / Moderators 组一致（信息编辑员**不可**管理版块）。
        user = self.request.user
        can_see_inactive = bool(
            user.is_authenticated
            and (has_capability(user, CAP_BROADCAST)
                 or user.groups.filter(name='Moderators').exists())
        )
        if not can_see_inactive:
            queryset = queryset.filter(is_active=True)  # 只筛选启用的版块

        # 按排序字段排序
        return queryset.order_by('order', '-created_at')  # 返回排序后的查询集

    def get_permissions(self):  # 定义获取权限方法
        # ⚠️ 这个白名单必须覆盖**所有**写操作的自定义 action。
        # 原先漏了 update_order，导致任何登录用户（哪怕 role=USER）都能批量改版块排序
        # （实测：普通用户 POST /forums/boards/update_order/ 返回 200 并真的改了顺序）。
        #
        # 第 124 批：`IsAdminUser`（只认 is_staff）换成 `IsBroadcastManager`（BROADCAST 能力）
        # —— 与用户管理、公告同一口径，且不会把"role=ADMIN 但 is_staff=False"漏掉。
        if self.action in [
            'create', 'update', 'partial_update', 'destroy',
            'set_status', 'update_order',
        ]:  # 检查操作类型
            self.permission_classes = [IsBroadcastManager | IsModeratorOrReadOnly]  # 设置特定权限
        return super().get_permissions()  # 返回父类权限

    def perform_create(self, serializer):  # 定义创建操作
        # 保存帖子
        board = serializer.save()  # 保存序列化器数据
        # 第 150 批：新建版块是"农户端能看到什么"的结构性改动，落一条审计日志
        log_admin_action(
            self.request.user, 'board.create', target=board,
            detail=f'新建版块（排序 {board.order}，{"启用" if board.is_active else "停用"}）',
            request=self.request,
        )

    def perform_update(self, serializer):  # 定义更新操作
        # 更新帖子
        # 第 150 批：编辑版块也留痕 —— 并把**改了哪些字段**记下来。
        # 只写"编辑了版块"等于没写：事后追查要知道"名字是不是被人改过"。
        tracked = ('name', 'description', 'icon', 'order', 'is_active')
        before = {field: getattr(serializer.instance, field, None) for field in tracked}
        board = serializer.save()  # 保存序列化器数据
        changed = [
            f'{field}: {before[field]} → {getattr(board, field, None)}'
            for field in tracked if before[field] != getattr(board, field, None)
        ]
        log_admin_action(
            self.request.user, 'board.update', target=board,
            detail='编辑版块：' + ('；'.join(changed) if changed else '无字段变化'),
            request=self.request,
        )

    @action(detail=True, methods=['post'])  # 定义自定义动作
    def set_status(self, request, pk=None):  # 定义设置状态方法
        """设置版块状态（启用/禁用）"""
        board = self.get_object()  # 获取版块对象
        is_active = request.data.get('is_active')  # 获取请求数据中的状态值

        if is_active is None:  # 检查状态值是否存在
            return Response(  # 返回错误响应
                {'is_active': ['This field is required.']},
                status=status.HTTP_400_BAD_REQUEST  # 设置HTTP状态码
            )

        board.is_active = is_active  # 设置版块状态
        # 注意：ForumBoard 模型**没有 updated_by 字段**。原来把它写进 update_fields，
        # save() 会直接抛 ValueError（field names do not exist in this model）→ 接口稳定 500。
        board.save(update_fields=['is_active', 'updated_at'])  # 保存更新

        action = '启用' if is_active else '禁用'  # 设置操作名称
        # 第 146 批：落一条操作日志（版块启停直接影响农户端能不能看到它）
        log_admin_action(request.user, 'board.set_status', target=board,
                         detail=f'{action}版块', request=request)
        return Response({  # 返回成功响应
            'detail': f'已{action}版块',
            'is_active': board.is_active  # 返回更新后的状态
        })

    @action(detail=False, methods=['post'])  # 定义自定义动作
    def update_order(self, request):  # 定义更新排序方法
        """批量更新版块排序"""
        orders = request.data.get('orders')  # 获取请求数据中的排序列表

        if not isinstance(orders, list):  # 检查数据类型
            return Response(  # 返回错误响应
                {'orders': ['This field must be a list.']},
                status=status.HTTP_400_BAD_REQUEST  # 设置HTTP状态码
            )

        # 验证数据格式
        try:  # 尝试解析数据
            order_data = [  # 创建数据列表
                {'id': int(item['id']), 'order': int(item['order'])}
                for item in orders  # 遍历排序数据
            ]
        except (KeyError, ValueError, TypeError):  # 捕获异常
            return Response(  # 返回错误响应
                {'orders': ['Invalid data format.']},
                status=status.HTTP_400_BAD_REQUEST  # 设置HTTP状态码
            )

        # 批量更新排序
        updated = 0  # 初始化更新计数器
        for item in order_data:  # 遍历排序数据
            updated += ForumBoard.objects.filter(  # 更新版块排序
                pk=item['id']  # 按ID筛选
            ).update(  # 执行更新
                order=item['order'],  # 设置排序值
                # 原代码这里还传了 updated_by=request.user，但 ForumBoard 没有该字段，
                # queryset.update() 会抛 FieldError → 接口稳定 500。已移除。
                updated_at=timezone.now()  # 设置更新时间
            )

        # 第 146 批：排序会改变农户端论坛里版块的先后顺序，值得留痕
        log_admin_action(request.user, 'board.update_order', target_type='board',
                         detail=f'更新 {updated} 个版块的排序', request=request)
        return Response({  # 返回成功响应
            'detail': f'成功更新 {updated} 个版块的排序',
            'updated': updated  # 返回更新数量
        })


class PostViewSet(viewsets.ModelViewSet):  # 定义帖子视图集
    """
    帖子视图集
    - 所有用户可查看帖子列表和详情
    - 登录用户可创建帖子
    - 作者和版主可编辑/删除帖子
    - 支持按版块、搜索、排序等筛选
    - 支持置顶、精华等操作
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]  # 设置权限类
    pagination_class = CustomPagination  # 设置分页类

    def get_permissions(self):  # 定义获取权限方法
        if self.action in ['update', 'partial_update']:  # 检查操作类型
            return [permissions.IsAuthenticated(), IsOwnerOrReadOnly()]  # 返回需要认证和所有者的权限
        elif self.action == 'destroy':  # 删除操作
            return [permissions.IsAuthenticated(), CanDeletePost()]  # 使用删除权限类
        return [permission() for permission in self.permission_classes]  # 返回默认权限

    def get_serializer_class(self):  # 定义获取序列化器类方法
        if self.action == 'retrieve':  # 检查操作类型
            return PostDetailSerializer  # 返回详情序列化器
        return PostListSerializer  # 返回列表序列化器

    def get_queryset(self):  # 定义获取查询集方法
        # 第 91 批：默认口径是**未删除**的帖子（Post.active）。
        # 删帖已改为软删除，若这里仍从 Post.objects 起手，删掉的帖子会继续出现在
        # 列表/详情里（只是标题变成"[已删除]"）—— 那等于"删了个寂寞"。
        queryset = Post.active.select_related('author', 'board').prefetch_related('pests')  # 获取帖子并关联作者和版块（第 168 批：一并取出病害标签，避免逐帖再查）

        # 第 91 批：管理员/版主可用 ?only_deleted=true 审计"被删掉的帖子"。
        # 其余人即使传这个参数也拿不到（下面 user 分支里会被继续按可见性过滤掉）。
        only_deleted = (self.request.query_params.get('only_deleted') or '').strip().lower()
        if only_deleted in ('true', '1', 'yes') and is_moderator(self.request.user):
            queryset = Post.objects.filter(is_deleted=True).select_related('author', 'board')

        # 记录初始查询SQL（改用 debug 级日志：原先 print 会在每个请求把整条 SQL 打到控制台）
        logger.debug("帖子列表初始查询SQL: %s", queryset.query)

        # 过滤条件
        board_id = self.request.query_params.get('board') or self.request.query_params.get('board_id')  # 获取版块ID参数
        author_id = self.request.query_params.get('author')  # 获取作者ID参数
        
        if board_id:  # 检查版块ID是否存在
            try:  # 尝试转换版块ID
                board_id = int(board_id)  # 转换为整数
                queryset = queryset.filter(board_id=board_id)  # 按版块ID筛选
                logger.debug("按版块过滤 board_id=%s 后: %s", board_id, queryset.query)
            except (ValueError, TypeError):  # 捕获异常
                # 如果 board_id 不是有效的数字，则忽略该过滤条件
                logger.warning("忽略无效的版块ID参数: %r", board_id)
                pass  # 跳过

        # 按作者ID过滤
        if author_id:  # 检查作者ID是否存在
            try:  # 尝试转换作者ID
                author_id = int(author_id)  # 转换为整数
                before_count = queryset.count()  # 获取过滤前数量
                queryset = queryset.filter(author_id=author_id)  # 按作者ID筛选
                after_count = queryset.count()  # 获取过滤后数量
                logger.debug(
                    "按作者过滤 author_id=%s, 过滤前=%s, 过滤后=%s",
                    author_id, before_count, after_count,
                )
                logger.debug("按作者过滤后的SQL: %s", queryset.query)

            except (ValueError, TypeError) as e:  # 捕获异常
                logger.warning("忽略无效的作者ID参数: %r (%s)", author_id, e)
                # 如果 author_id 不是有效的数字，则忽略该过滤条件
                pass  # 跳过

        # 搜索
        search = self.request.query_params.get('search')  # 获取搜索参数
        if search:  # 检查搜索参数是否存在
            queryset = queryset.filter(  # 应用搜索条件
                Q(title__icontains=search) |  # 标题包含搜索词
                Q(content__icontains=search)  # 内容包含搜索词
            )

        # 精华筛选（第 24 批）：前端版块页有「精华」标签，但此前从不传参、后端也不认，
        # 该标签纯装饰（点了和"全部"完全一样）。
        essence = (self.request.query_params.get('is_essence')
                   or self.request.query_params.get('essence') or '').strip().lower()
        if essence in ('true', '1', 'yes'):
            queryset = queryset.filter(is_essence=True)

        # 病害标签筛选（第 168 批）：?pest=<词条 id>
        #
        # 帖子能打「苹果黑星病」这样的标签之后，"按病害聚合讨论"就是一次普通筛选：
        # 词条页/聚合入口拿 pest 参数一查，就是这个病的所有讨论。
        # 标签是 M2M，这里按单个 id 过滤（每个帖子最多命中一次，不会出现重复行）。
        pest_id = (self.request.query_params.get('pest') or '').strip()
        if pest_id:
            try:
                queryset = queryset.filter(pests__id=int(pest_id))
            except (TypeError, ValueError):
                logger.warning('忽略无效的病害标签 id: %r', pest_id)

        # 可见性（第 24 批）：已发布对所有人可见；**作者本人**还能看到自己的草稿/隐藏帖，
        # 否则"保存草稿"之后这条帖子就再也找不到了（列表、详情都是 404）。
        #
        # 第 38 批修正：版主/管理员必须能看到**全部**帖子 —— 否则待审核（pending）的帖子
        # 连管理员都取不到（`get_object()` 直接 404），审核动作 approve/reject 根本无法执行；
        # 管理端的"待审核"列表也需要它。
        user = self.request.user

        # 第 38 批：按状态筛选（管理端"待审核"列表用 ?status=pending，论坛页的"草稿"筛选用 ?status=draft）
        #
        # 第 166 批：把这段**挪到可见性判断之前**，并用 `?status=all` 表示"明确不做状态过滤"。
        # 为什么需要这个哨兵值：控制台「论坛管理」页的「全部」选项要能看到**所有**状态
        # （含草稿 —— 第 147 批的设计，那里有测试盯着），而公开的论坛列表**不该**混入别人的草稿。
        # 两者都传"没有 status 参数"是区分不出来的，所以让控制台显式传 `status=all`。
        status_param = (self.request.query_params.get('status') or '').strip()
        explicit_all = status_param.lower() == 'all'
        if explicit_all:
            status_param = ''
        elif status_param:
            valid_status = {choice[0] for choice in Post.STATUS_CHOICES}
            if status_param not in valid_status:
                logger.warning('忽略无效的帖子状态筛选: %r', status_param)
                status_param = ''

        if is_moderator(user):
            # 版主/管理员：不做可见性过滤（待审核帖子也要能取到，否则 approve/reject 无从执行）。
            #
            # 第 166 批补一条：**列表**默认不混入草稿 —— 草稿是别人没写完的东西，
            # 版主浏览论坛时不该看到（版块页还会给它打「草稿」标签）。
            # 想连草稿一起看有两个办法：显式 `?status=draft`，或者控制台那样传 `?status=all`。
            #
            # ⚠️ 只在 `list` 上排除，**绝不能连详情一起排**：
            # 第一版写成无条件排除，结果版主/管理员**连自己的草稿都打不开**
            # （`GET /api/forums/posts/<id>/` 直接 404，"继续编辑"点进去是空白页）。
            if self.action == 'list' and not status_param and not explicit_all:
                queryset = queryset.exclude(status='draft')
        elif user.is_authenticated:
            queryset = queryset.filter(Q(status='published') | Q(author=user))
        else:
            queryset = queryset.filter(status='published')

        if status_param:
            queryset = queryset.filter(status=status_param)

        # 收藏筛选（第 24 批）：?favorited=true → 只看当前用户收藏过的帖子（「我的收藏」）
        favorited = (self.request.query_params.get('favorited') or '').strip().lower()
        if favorited in ('true', '1', 'yes'):
            if user.is_authenticated:
                queryset = queryset.filter(favorited_by__user=user)
            else:
                queryset = queryset.none()

        # 当前用户是否收藏 —— 用注解一次算完，避免列表里逐条 exists 查询（N+1）
        if user.is_authenticated:
            queryset = queryset.annotate(
                _is_favorited=Exists(Favorite.objects.filter(post=OuterRef('pk'), user=user))
            )

        # 排序
        # 第 24 批：前端排序下拉发的是 `ordering`，而后端只认 `order_by` →
        # 排序功能一直是装饰。这里两个参数都接受，并补齐前端提供的几种排序方式。
        order_by = (self.request.query_params.get('order_by')
                    or self.request.query_params.get('ordering')
                    or '-created_at').strip()
        if order_by == 'hot':  # 检查是否为热门排序
            # 注意：两个 Count 同时参与时会被 join 放大（2 赞 3 评论会算成 6/6），
            # 必须 distinct=True —— 原来少了它，热度排序实际是错的。
            queryset = queryset.annotate(  # 添加注解
                hot_score=Count('likes', distinct=True) * 2 + Count('comments', distinct=True)
            ).order_by('-is_pinned', '-hot_score', '-created_at')  # 按热度排序
        else:  # 其它排序方式
            ordering_map = {
                'latest': '-created_at',
                '-created_at': '-created_at',
                'created_at': 'created_at',
                'last_reply': '-last_comment_at',
                '-last_reply': '-last_comment_at',
                '-last_comment_at': '-last_comment_at',
                'view_count': '-view_count',
                '-view_count': '-view_count',
                'comment_count': '-comment_count',
                '-comment_count': '-comment_count',
                'like_count': '-like_count',
                '-like_count': '-like_count',
            }
            order_field = ordering_map.get(order_by, '-created_at')
            queryset = queryset.order_by('-is_pinned', order_field)  # 置顶始终在最前

        return queryset

    def perform_create(self, serializer):  # 定义创建操作
        user = self.request.user
        wants_pin = bool(serializer.validated_data.get('is_pinned'))
        wants_essence = bool(serializer.validated_data.get('is_essence'))

        # 第 38 批：标题与正文先过敏感词（命中直接 400，避免"发出去再被删"）
        from .sensitive import check_text
        check_text(
            serializer.validated_data.get('title'),
            serializer.validated_data.get('content'),
            field_label='帖子',
        )

        if is_moderator(user):  # 版主/管理员可以设置置顶与精华
            serializer.save(author=user)
            self._apply_review_policy(serializer.instance)
            self._award_points(serializer.instance)
            self._translate_post(serializer.instance)
            return

        # 第 24 批：普通用户**不能**把自己的帖子置顶/加精。
        # 此前序列化器把这两个字段暴露为可写，服务端又没有任何校验，
        # 实测普通用户 POST/PATCH is_pinned=true 会真的生效（越权）。
        if wants_pin or wants_essence:
            raise PermissionDenied('只有版主或管理员可以设置置顶/精华')

        serializer.save(author=user, is_pinned=False, is_essence=False)  # 强制为 False
        self._apply_review_policy(serializer.instance)
        self._award_points(serializer.instance)
        self._translate_post(serializer.instance)

    def _translate_post(self, post):
        """第 85 批：给新帖补英文译文（失败只记日志，绝不影响发帖）

        作者自己带了完整英文（title_en + content_en）时，序列化器已把它记成
        人工译文，这里会被 services_translate 的"人工优先"规则跳过。
        `TRANSLATE_ON_WRITE=False` 时整块跳过，改由
        `manage.py translate_forum_content` 批量补译。
        """
        if not getattr(settings, 'TRANSLATE_ON_WRITE', True):
            return
        try:
            from .services_translate import safe_translate_instance
            safe_translate_instance(post)
        except Exception:  # noqa: BLE001 —— 连导入失败也不能影响发帖
            logger.exception('帖子翻译调度失败 post=%s', getattr(post, 'id', None))

    def _award_points(self, post):
        """第 42 批：发帖 +5 积分（审核中的帖子也先记分，通过与否由管理员决定）"""
        try:
            from .services_points import award_points
            award_points(post.author, 'post', ref_type='post', ref_id=post.id)
        except Exception:
            logger.exception('发帖积分失败 post=%s', getattr(post, 'id', None))

    def _apply_review_policy(self, post):
        """
        第 38 批：发帖审核策略

        `settings.POST_REQUIRE_REVIEW` 打开时，普通用户的新帖先进"待审核"，
        审核通过才对别人可见（作者本人始终能看到自己的帖子，与草稿同一套可见性规则）。
        草稿（作者主动存的）不受影响。
        """
        if not getattr(settings, 'POST_REQUIRE_REVIEW', False):
            return
        if post.status != 'published':
            return
        if is_moderator(post.author):
            return

        post.status = 'pending'
        post.save(update_fields=['status'])
        self._notify_moderators(post)

    def _notify_moderators(self, post):
        """给版主/管理员发"有新的待审核帖子"通知"""
        try:
            from .views_notify import notify
            moderators = User.objects.filter(is_staff=True, is_active=True)
            for moderator in moderators:
                notify(
                    moderator,
                    type='system',
                    title=f'有新的待审核帖子：{post.title}',
                    title_en=f'New post awaiting review: {post.title}',
                    message=f'{post.author.username} 在「{post.board.name}」发布了新帖，等待审核',
                    message_en=(
                        f'{post.author.username} posted in "{post.board.name_en or post.board.name}" '
                        f'and it is waiting for review'
                    ),
                    # 第 183 批：审核队列在「内容管理」页的**帖子页签**（原 /admin/review）
                    url='/admin/content?tab=posts',
                    actor=post.author,
                    post=post,
                )
        except Exception:
            logger.exception('发送待审核通知失败 post=%s', getattr(post, 'id', None))

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def approve(self, request, pk=None):
        """
        审核通过（第 38 批，仅版主/管理员）

        通过后帖子进入 `published`，并给作者发一条通知。
        """
        if not is_moderator(request.user):
            return Response({'detail': '只有版主或管理员可以审核帖子'},
                            status=status.HTTP_403_FORBIDDEN)

        post = self.get_object()
        post.status = 'published'
        post.save(update_fields=['status'])

        try:
            from .views_notify import notify
            notify(
                post.author,
                type='system',
                title=f'你的帖子已通过审核：{post.title}',
                title_en=f'Your post was approved: {post.title}',
                message='现在其他用户可以看到这篇帖子了',
                message_en='Other users can now see this post',
                url=f'/forum/post/{post.id}',
                actor=request.user,
                post=post,
            )
        except Exception:
            logger.exception('发送审核通过通知失败 post=%s', post.id)

        logger.info('帖子审核通过 id=%s by=%s', post.id, request.user.id)
        return Response({'id': post.id, 'status': post.status, 'detail': '已通过审核'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def reject(self, request, pk=None):
        """
        审核驳回（第 38 批，仅版主/管理员）

        驳回后帖子进入 `hidden`（作者仍能看到，其他用户看不到），并通知作者原因。
        """
        if not is_moderator(request.user):
            return Response({'detail': '只有版主或管理员可以审核帖子'},
                            status=status.HTTP_403_FORBIDDEN)

        reason = (request.data.get('reason') or '').strip()
        post = self.get_object()
        post.status = 'hidden'
        post.save(update_fields=['status'])

        try:
            from .views_notify import notify
            notify(
                post.author,
                type='system',
                title=f'你的帖子未通过审核：{post.title}',
                title_en=f'Your post was rejected: {post.title}',
                message=reason or '内容不符合社区规范，请修改后重新发布',
                url=f'/forum/post/{post.id}',
                actor=request.user,
                post=post,
            )
        except Exception:
            logger.exception('发送审核驳回通知失败 post=%s', post.id)

        logger.info('帖子审核驳回 id=%s by=%s reason=%s', post.id, request.user.id, reason[:50])
        return Response({'id': post.id, 'status': post.status, 'detail': '已驳回'})

    # ------------------------------------------------------------------
    # 第 100 批：审核逻辑抽成可复用方法 + 批量审核
    # ------------------------------------------------------------------
    # 抽出来的原因：批量审核要逐条走**完全一样**的流程（改状态 + 通知作者）——
    # 如果批量版本自己再写一遍，两处就会慢慢跑偏（比如这里加了通知、那里忘了），
    # 而这种偏差只有在"用户说我没收到通知"时才会被发现。
    def _approve_post(self, post, actor):
        """通过一篇待审帖（单条与批量共用）"""
        post.status = 'published'
        post.save(update_fields=['status'])
        try:
            from .views_notify import notify
            notify(
                post.author,
                type='system',
                title=f'你的帖子已通过审核：{post.title}',
                title_en=f'Your post was approved: {post.title}',
                message='现在其他用户可以看到这篇帖子了',
                message_en='Other users can now see this post',
                url=f'/forum/post/{post.id}',
                actor=actor,
                post=post,
            )
        except Exception:
            logger.exception('发送审核通过通知失败 post=%s', post.id)

    def _reject_post(self, post, actor, reason=''):
        """驳回一篇待审帖（单条与批量共用）"""
        post.status = 'hidden'
        post.save(update_fields=['status'])
        try:
            from .views_notify import notify
            notify(
                post.author,
                type='system',
                title=f'你的帖子未通过审核：{post.title}',
                title_en=f'Your post was rejected: {post.title}',
                message=reason or '内容不符合社区规范，请修改后重新发布',
                url=f'/forum/post/{post.id}',
                actor=actor,
                post=post,
            )
        except Exception:
            logger.exception('发送审核驳回通知失败 post=%s', post.id)

    @action(detail=False, methods=['post'], url_path='bulk-review',
            permission_classes=[permissions.IsAuthenticated])
    def bulk_review(self, request):
        """
        批量审核（第 100 批，仅版主/管理员）

            POST /api/forums/posts/bulk-review/
            body: {"ids": [1,2,3], "action": "approve" | "reject", "reason": "可选"}

        为什么需要它：待审帖多起来之后，审核员只能一条一条点"通过"——
        每条都要一次点击 + 一次网络往返，20 条就是 20 次。
        更麻烦的是**漏审**：列表分页一翻，很容易看漏中间某条。

        设计取舍：
          · **逐条处理、不整体失败**：某一条不合法（比如 id 不存在、或不是待审状态）
            不应该让另外 19 条白做。响应里逐条给结果，前端把失败原因显示出来。
          · **通过只处理 pending**：已发布的帖子被"批量通过"没有意义；
            第 182 批起 **驳回** 也处理 `published`（撤回发布 = 下架，可再次通过恢复），
            但不能处理已 hidden 的（那是重复操作）
            已隐藏的帖子被"批量通过"等于绕过驳回 —— 这两类明确跳过并说明原因。
          · 上限 200 条：一次点几千条会让请求超时，而且前端也不该有这种入口。
        """
        if not is_moderator(request.user):
            return Response({'detail': '只有版主或管理员可以审核帖子'},
                            status=status.HTTP_403_FORBIDDEN)

        action_name = (request.data.get('action') or '').strip().lower()
        if action_name not in ('approve', 'reject'):
            return Response({'detail': 'action 只能是 approve 或 reject'},
                            status=status.HTTP_400_BAD_REQUEST)

        raw_ids = request.data.get('ids') or []
        if not isinstance(raw_ids, (list, tuple)):
            return Response({'detail': 'ids 必须是数组'}, status=status.HTTP_400_BAD_REQUEST)

        ids = []
        for value in raw_ids:
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
        # 去重但保持顺序（前端多选可能带上重复 id）
        seen = set()
        ids = [i for i in ids if not (i in seen or seen.add(i))]
        if not ids:
            return Response({'detail': '没有选中任何帖子'}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > 200:
            return Response({'detail': '一次最多处理 200 条'}, status=status.HTTP_400_BAD_REQUEST)

        reason = (request.data.get('reason') or '').strip()[:500]
        posts = {p.id: p for p in Post.objects.filter(id__in=ids)}

        results = []
        ok_count = 0
        for post_id in ids:
            post = posts.get(post_id)
            if post is None:
                results.append({'id': post_id, 'ok': False, 'detail': '帖子不存在'})
                continue
            if post.is_deleted:
                results.append({'id': post_id, 'ok': False, 'detail': '帖子已删除'})
                continue
            # 第 182 批：**驳回**允许处理"已发布"的帖子 —— 语义是**撤回发布（下架）**。
            # 原先两种动作共用"只处理 pending"，于是"已经发出去的内容发现有错"在界面上
            # 无路可走：单条驳回只对待审显示、批量驳回静默跳过（用户反馈"点批量驳回没用"
            # 就是这个）。单条 reject 接口本来对已发布也生效（实测 200 → hidden），
            # 批量这里只是把口径对齐。**通过**仍然只认 pending：已发布的再"通过"没有意义。
            # 第 187 批：**对称化** —— 驳回能把 pending/published 变成 hidden，
            # 那么通过就必须能把 hidden 变回 published（用户报的"批量驳回后批量通过没用"）。
            # 上一版只有驳回放宽了，通过仍只认 pending，于是"下架容易、恢复无门"。
            allowed = (('pending', 'hidden') if action_name == 'approve'
                       else ('pending', 'published'))
            if post.status not in allowed:
                detail = (f'不是待审状态（当前 {post.status}），已跳过'
                          if action_name == 'approve'
                          else f'当前状态是 {post.status}，不能撤回（只有待审或已发布可以）')
                results.append({'id': post_id, 'ok': False, 'detail': detail})
                continue

            if action_name == 'approve':
                self._approve_post(post, request.user)
            else:
                self._reject_post(post, request.user, reason)
            ok_count += 1
            results.append({'id': post_id, 'ok': True, 'detail': post.status})

        logger.info(
            '批量审核 action=%s by=%s 成功=%s/请求=%s',
            action_name, request.user.id, ok_count, len(ids),
        )
        return Response({
            'action': action_name,
            'requested': len(ids),
            'succeeded': ok_count,
            'failed': len(ids) - ok_count,
            'results': results,
        })

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        """
        批量删除帖子（第 147 批，**仅全权管理员**）

            POST /api/forums/posts/bulk-delete/   {"ids": [1, 2, 3]}

        为什么需要：控制台的「论坛管理」页要能一次清掉一批垃圾帖 / 广告帖。
        单条删除要一条条点确认框，20 条就是 20 轮。

        权限刻意比单条删除**更严一档**（与反馈那边一致）：
          · 单条 `destroy`：作者本人或版主/管理员都能删（`CanDeletePost`）；
          · 批量删除：**只给全权管理员** —— 批量是不可逆的破坏性操作，
            "能审核"不等于"能一次抹掉一批"。列表页里版主看到的本来就是全部帖子，
            开放给他等于把"作者才能删自己的帖子"这条边界从后门绕过去。

        与反馈的批量删除同口径：逐条处理不整体失败（响应里给每条成败）、
        复用 `parse_ids` 的那套校验（数组/转 int/去重/上限 200）、
        走 `post.soft_delete()`（**软删除**：评论与点赞留在库里，不做级联真删）。
        """
        if not is_full_admin(request.user):
            return Response({'detail': '只有管理员可以批量删除帖子'},
                            status=status.HTTP_403_FORBIDDEN)

        ids, error = parse_ids(request.data.get('ids'), label='帖子')
        if error:
            return error

        # 只删**能看得到**的帖子：`Post.active` 已排除软删除的，重复点不会重复计数
        posts = {p.id: p for p in Post.active.filter(id__in=ids).select_related('board')}

        results = []
        ok_count = 0
        for post_id in ids:
            post = posts.get(post_id)
            if post is None:
                results.append({'id': post_id, 'ok': False, 'detail': '帖子不存在或已被删除'})
                continue
            title = post.title
            post.soft_delete()
            ok_count += 1
            results.append({'id': post_id, 'ok': True, 'detail': title[:50]})

        log_admin_action(
            request.user, 'post.bulk_delete', target_type='post',
            target_id=','.join(str(i) for i in ids[:20]),
            detail=f'批量删除帖子 {ok_count}/{len(ids)} 条（软删除，评论与点赞保留）',
            request=request,
        )
        logger.info('批量删除帖子 by=%s 成功=%s/%s', request.user.id, ok_count, len(ids))
        return Response({
            'requested': len(ids),
            'succeeded': ok_count,
            'failed': len(ids) - ok_count,
            'results': results,
        })

    def perform_update(self, serializer):
        """更新帖子：普通用户不得借编辑把自己"升级"成置顶/精华"""
        user = self.request.user
        instance = serializer.instance
        data = serializer.validated_data

        if is_moderator(user):
            serializer.save()
            self._translate_post(serializer.instance)  # 第 85 批：正文改了要重译
            return

        # 普通用户：把"本来不是置顶/精华"的帖子改成 true → 明确的 403；
        # 其它情况（包括前端总是回传 is_pinned=false 这种）一律保持数据库原值，
        # 免得作者想改正文却被这条规则卡住。
        if (bool(data.get('is_pinned')) and not instance.is_pinned) or \
                (bool(data.get('is_essence')) and not instance.is_essence):
            raise PermissionDenied('只有版主或管理员可以设置置顶/精华')

        data.pop('is_pinned', None)
        data.pop('is_essence', None)
        serializer.save()
        self._translate_post(serializer.instance)  # 第 85 批：正文改了要重译

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def set_pinned(self, request, pk=None):
        """置顶 / 取消置顶（仅版主或管理员）—— 第 24 批新增"""
        if not is_moderator(request.user):
            return Response({'detail': '只有版主或管理员可以置顶帖子'},
                            status=status.HTTP_403_FORBIDDEN)
        post = self.get_object()
        post.is_pinned = bool(request.data.get('is_pinned', not post.is_pinned))
        post.save(update_fields=['is_pinned'])
        return Response({'id': post.id, 'is_pinned': post.is_pinned})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def set_essence(self, request, pk=None):
        """加精 / 取消加精（仅版主或管理员）—— 第 24 批新增"""
        if not is_moderator(request.user):
            return Response({'detail': '只有版主或管理员可以设置精华'},
                            status=status.HTTP_403_FORBIDDEN)
        post = self.get_object()
        post.is_essence = bool(request.data.get('is_essence', not post.is_essence))
        post.save(update_fields=['is_essence'])
        return Response({'id': post.id, 'is_essence': post.is_essence})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def translate(self, request, pk=None):
        """第 85 批：按需翻译帖子（英文界面的「立即翻译」按钮）

        发帖时后端已经会顺手翻一次，这个接口补的是两种情况：
          · 历史帖子（功能上线前发的）还没有译文；
          · 当时自动翻译失败（接口超时/额度用尽）。

        权限：任何登录用户都能触发 —— 译文是**共享的公共数据**，让每个读者
        各自去点一次不会产生错误结果（同一原文的译文是确定的），也不涉及隐私；
        取帖子对象仍走 get_object()，所以看不到的帖子（别人的草稿）照样 404。

        失败语义：翻译服务不可用时返回 503 + 具体原因，而不是静默 200，
        否则前端会以为"翻译成功"却什么都没变。
        """
        from .services_translate import (TranslateError, is_enabled, translate_instance)

        post = self.get_object()
        if not is_enabled():
            return Response({'detail': '翻译服务未启用（TRANSLATE_PROVIDER=none）'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        try:
            translate_instance(post)
        except TranslateError as exc:
            logger.warning('按需翻译帖子失败 post=%s: %s', post.id, exc)
            return Response({'detail': f'翻译失败：{exc}'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        post.refresh_from_db(fields=['title_en', 'content_en', 'translation_hash',
                                     'translation_source', 'translated_at'])
        return Response({
            'id': post.id,
            'title_en': post.title_en,
            'content_en': post.content_en,
            'translation_stale': post.translation_stale,
            'translation_source': post.translation_source,
            'translated_at': post.translated_at,
        })

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])  # 定义自定义动作
    def favorite(self, request, pk=None):  # 定义收藏方法
        """收藏/取消收藏帖子"""
        post = self.get_object()  # 获取帖子对象
        favorite, created = Favorite.objects.get_or_create(  # 获取或创建收藏记录
            user=request.user,  # 设置用户
            post=post,  # 设置帖子
        )

        if not created:  # 如果收藏已存在
            favorite.delete()  # 删除收藏记录
            return Response({'status': 'unfavorited', 'is_favorited': False})  # 返回取消收藏响应

        # 第 37 批：首次收藏时给作者发通知（取消收藏不发）
        try:
            from .views_notify import notify
            notify(
                post.author,
                type='favorite',
                title=f'{request.user.username} 收藏了你的帖子：{post.title}',
                title_en=f'{request.user.username} favourited your post: {post.title}',
                url=f'/forum/post/{post.id}',
                actor=request.user,
                post=post,
            )
        except Exception:
            logger.exception('发送收藏通知失败 post=%s', post.id)

        # 第 42 批：作者被收藏 +2 积分
        try:
            from .services_points import award_points
            award_points(post.author, 'favorite_received', ref_type='post', ref_id=post.id)
        except Exception:
            logger.exception('收藏积分失败 post=%s', post.id)

        return Response({'status': 'favorited', 'is_favorited': True}, status=status.HTTP_201_CREATED)  # 返回收藏成功响应

    @action(detail=True, methods=['post'], url_path='view', permission_classes=[permissions.AllowAny])  # 定义自定义动作
    def view(self, request, pk=None):  # 定义增加浏览量方法
        """增加浏览次数"""
        post = self.get_object()  # 获取帖子对象
        post.view_count = F('view_count') + 1  # 使用F()原子操作增加浏览量
        post.save(update_fields=['view_count'])  # 保存更新
        post.refresh_from_db()  # 从数据库重新加载以获取更新后的值
        return Response({'view_count': post.view_count}, status=status.HTTP_200_OK)  # 返回成功响应和更新后的浏览量

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])  # 定义自定义动作
    def like(self, request, pk=None):  # 定义点赞方法
        """点赞/取消点赞"""
        # 安全提示：原代码在此打印了 dict(request.headers)（其中包含 Authorization: Token ...），
        # 等于把用户凭证写进 django 日志文件；已改为只记录非敏感标识。
        post = self.get_object()  # 获取帖子对象

        # 检查是否已经有点赞记录
        existing_like = Like.objects.filter(user=request.user, post=post).first()
        if existing_like:
            existing_like.delete()  # 删除点赞记录（Like.delete 会重算 like_count）
            post.refresh_from_db(fields=['like_count'])
            # 前端 ForumBoardView.toggleLike 需要 is_liked / like_count 来更新按钮与计数；
            # 原来只返回 {detail}，导致点赞后 is_liked/like_count 被赋成 undefined，图标和数字消失。
            return Response({
                'detail': '已取消点赞',
                'status': 'unliked',
                'is_liked': False,
                'like_count': post.like_count,
            }, status=status.HTTP_200_OK)

        # 创建新的点赞记录（Like.save 会重算 like_count）
        Like.objects.create(user=request.user, post=post)
        post.refresh_from_db(fields=['like_count'])
        logger.debug("[LIKE] 用户 %s 点赞了帖子 %s", request.user.id, post.id)

        # 第 37 批：给作者发"有人点赞了你"的通知
        try:
            from .views_notify import notify
            notify(
                post.author,
                type='like',
                title=f'{request.user.username} 点赞了你的帖子：{post.title}',
                title_en=f'{request.user.username} liked your post: {post.title}',
                url=f'/forum/post/{post.id}',
                actor=request.user,
                post=post,
            )
        except Exception:
            logger.exception('发送点赞通知失败 post=%s', post.id)

        # 第 42 批：作者被点赞 +1 积分
        try:
            from .services_points import award_points
            award_points(post.author, 'like_received', ref_type='post', ref_id=post.id)
        except Exception:
            logger.exception('点赞积分失败 post=%s', post.id)

        return Response({
            'detail': '点赞成功',
            'status': 'liked',
            'is_liked': True,
            'like_count': post.like_count,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='likes',
            permission_classes=[permissions.AllowAny])
    def likes(self, request, pk=None):
        """谁点赞了这条帖子（第 25 批新增）

        说明：`LikeViewSet.get_queryset` 只返回 `user=request.user` 的记录
        （即"我赞过什么"），没有任何接口能反查"某条帖子/评论被谁赞过"，
        所以界面上一直无法展示点赞者名单。
        """
        post = self.get_object()
        queryset = Like.objects.filter(post=post).select_related('user').order_by('-created_at')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = LikeUserSerializer(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)

        serializer = LikeUserSerializer(queryset, many=True, context=self.get_serializer_context())
        return Response({'count': queryset.count(), 'results': serializer.data})

    @action(detail=False, methods=['get'])  # 定义自定义动作
    def hot(self, request):  # 定义获取热门帖子方法
        """获取热门帖子"""
        limit = int(request.query_params.get('limit', 10))  # 获取限制参数

        # 获取热门帖子（按点赞数和评论数计算热度）
        # 第 24 批：两个 Count 一起用必须 distinct=True，否则会被 join 互相放大
        # 第 91 批：改用 Post.active —— 软删除的帖子不该出现在热门榜里
        hot_posts = (Post.active
                    .filter(status='published')  # 筛选已发布帖子
                    .annotate(
                        hot_score=Count('likes', distinct=True) * 2 + Count('comments', distinct=True),
                        comments_count=Count('comments', distinct=True)  # 计算评论数
                    )
                    .order_by('-hot_score', '-created_at')  # 按热度排序
                    .select_related('author', 'board')  # 关联作者和版块
                    [:limit]  # 限制数量
        )

        # 使用PostListSerializer序列化数据
        serializer = self.get_serializer(hot_posts, many=True)  # 序列化数据
        return Response(serializer.data)  # 返回序列化数据

    def destroy(self, request, *args, **kwargs):
        """
        删除帖子（第 91 批：改为**软删除**）

        改前是 DRF 默认实现 —— `instance.delete()` 真删行，而 `Comment.post`、
        `Like.post`、`Favorite.post` 都是 `CASCADE`：

            管理员删一条被举报的帖子 → 别人写的 20 条评论、30 个点赞一起消失，
            报错没有、回收站没有、恢复更不可能。

        评论从第 17 批起就是软删除（`is_deleted`），只有帖子是硬删除 —— 口径不一致。
        现在改成：作者本人或管理员删帖 → `post.soft_delete()`（标记 + 清空正文），
        关联的评论/点赞/收藏**原样留在库里**，只是帖子不再出现在任何列表与详情。

        权限不变（`CanDeletePost`：作者或管理员），响应仍是 204。
        需要**真删**（GDPR 式清理、清理测试数据）时请用管理命令，
        不要把这个入口改回硬删除。
        """
        post = self.get_object()
        title = post.title
        post.soft_delete()
        logger.info(
            '帖子软删除 id=%s title=%r 操作人=%s（评论/点赞/收藏保留在库中）',
            post.id, title, request.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommentViewSet(viewsets.ModelViewSet):  # 定义评论视图集
    """
    评论视图集
    - 所有用户可查看评论
    - 登录用户可发表评论
    - 评论作者、帖子作者或版主可删除评论
    - 支持评论回复功能
    - 防刷限制和敏感词过滤
    """
    serializer_class = CommentSerializer  # 设置序列化器类
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsCommentOwnerOrPostOwner]  # 设置权限类
    pagination_class = CustomPagination  # 设置分页类

    def get_permissions(self):  # 定义获取权限方法
        if self.action in ['create']:  # 检查操作类型
            self.permission_classes = [permissions.IsAuthenticated]  # 设置创建权限
        elif self.action in ['update', 'partial_update']:  # 检查操作类型
            self.permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]  # 设置更新权限
        elif self.action in ['destroy']:  # 检查操作类型
            self.permission_classes = [permissions.IsAuthenticated, IsCommentOwnerOrPostOwner]  # 设置删除权限
        elif self.action in ['like']:
            # 第 16 批修复：like 是 POST，会落到类级 [IsAuthenticatedOrReadOnly,
            # IsCommentOwnerOrPostOwner]，而该权限类的 has_object_permission 在非安全方法下
            # 要求「评论作者/帖子作者/版主」——于是**给别人点赞评论一律 403**，
            # 界面上每个人评论旁的点赞按钮对非作者全部失效。
            # 点赞只要求登录，不应要求对象所有权。
            self.permission_classes = [permissions.IsAuthenticated]
        return super().get_permissions()  # 返回父类权限

    def get_queryset(self):  # 定义获取查询集方法
        """
        评论查询集

        第 16 批修复：此前完全忽略查询参数，导致两个真实故障：
        1. 前端一直传 ``parent__isnull=true``（PostDetailView 的 fetchComments），
           后端不读 → **回复被当成顶级评论混进列表**，评论数（count）也被抬高；
        2. 前端一直传 ``ordering=-created_at``，后端不读 → 排序参数形同虚设。
        现支持 ``parent__isnull`` / ``parent`` / ``ordering``，并对回复数做 annotate。
        """
        queryset = Comment.objects.filter(  # 返回评论查询集
            post_id=self.kwargs['post_pk'],  # 按帖子ID筛选
            is_deleted=False  # 只返回未删除的评论
        )

        params = self.request.query_params
        parent_isnull = (params.get('parent__isnull') or '').strip().lower()
        if parent_isnull in ('true', '1', 'yes'):
            queryset = queryset.filter(parent__isnull=True)  # 只要顶级评论
        elif parent_isnull in ('false', '0', 'no'):
            queryset = queryset.filter(parent__isnull=False)  # 只要回复

        parent_id = (params.get('parent') or '').strip()
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)  # 指定父评论的回复

        ordering = (params.get('ordering') or 'created_at').strip()
        if ordering.lstrip('-') not in ('created_at', 'updated_at', 'like_count', 'id'):
            ordering = 'created_at'  # 白名单，避免随意字段排序报错

        return (
            queryset
            .select_related('author', 'reply_to_user')
            # 注意：这里**不要**加 prefetch_related('likes')。CommentSerializer.get_is_liked
            # 用的是 obj.likes.filter(user=...).exists()（filter 会重新查库，预取缓存帮不上忙），
            # 而 Django 的 QuerySet.count() 遇到已填充的预取缓存会直接返回缓存长度，
            # 会让 Like.save() 里的点赞数统计恒为 0（第 16 批修复的真实缺陷）。
            .annotate(reply_count_annotated=Count('replies', filter=Q(replies__is_deleted=False)))
            .order_by(ordering)
        )

    def list(self, request, *args, **kwargs):  # 重写列表方法
        # 重写 list 方法以支持分页
        queryset = self.filter_queryset(self.get_queryset())  # 获取过滤后的查询集

        # 添加分页
        page = self.paginate_queryset(queryset)  # 分页查询集
        if page is not None:  # 检查分页是否存在
            serializer = self.get_serializer(page, many=True)  # 序列化分页数据
            return self.get_paginated_response(serializer.data)  # 返回分页响应

        serializer = self.get_serializer(queryset, many=True)  # 序列化所有数据
        return Response(serializer.data)  # 返回响应

    def get_serializer_class(self):  # 定义获取序列化器类方法
        if self.action in ['create', 'update', 'partial_update']:  # 检查操作类型
            return CommentCreateSerializer  # 返回创建序列化器
        return CommentSerializer  # 返回默认序列化器

    def get_serializer_context(self):  # 定义获取序列化器上下文方法
        context = super().get_serializer_context()  # 获取父类上下文
        context['post_id'] = self.kwargs['post_pk']  # 添加上下文数据
        return context  # 返回上下文

    def create(self, request, *args, **kwargs):
        """
        创建评论/回复

        第 16 批修复：DRF 默认用「输入序列化器」回显创建结果，而
        ``CommentCreateSerializer.Meta.fields`` 只有 `content / parent / reply_to`，
        于是 **201 响应里没有 id**。前端 PostDetailView 拿到后用
        ``parentComment.replies.unshift({...newComment})`` 渲染，``:key="reply.id"``
        恒为 undefined；评论列表去重也依赖 id。现统一用 ``CommentSerializer``
        返回完整对象（含 id / author / created_at / reply_count）。
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        instance = serializer.instance
        output = CommentSerializer(instance, context=self.get_serializer_context())
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        """
        编辑评论（作者本人）

        与 create 同理：默认回显用的是只有 `content / parent / reply_to` 的输入序列化器，
        前端编辑保存后拿不到 `updated_at` 等字段。统一改为返回完整评论对象。
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        output = CommentSerializer(serializer.instance, context=self.get_serializer_context())
        return Response(output.data)

    @throttle_classes([UserRateThrottle])
    def perform_create(self, serializer):  # 定义创建操作
        # 检查是否在短时间内发送了过多评论
        one_minute_ago = timezone.now() - timezone.timedelta(minutes=1)
        recent_comments = Comment.objects.filter(
            author=self.request.user,
            created_at__gte=one_minute_ago
        ).count()
        
        if recent_comments >= 3:  # 限制每分钟最多3条评论
            raise serializers.ValidationError({
                'detail': '操作过于频繁，请稍后再试',
                'code': 'too_many_requests'
            })
            
        # 设置回复对象
        parent_id = self.request.data.get('parent')
        reply_to = None
        if parent_id:
            try:
                parent_comment = Comment.objects.get(id=parent_id, post_id=self.kwargs['post_pk'])
                reply_to = parent_comment.author
            except Comment.DoesNotExist:
                raise serializers.ValidationError({
                    'detail': '回复的评论不存在',
                    'code': 'parent_comment_not_found'
                })

        # 第 38 批：评论内容过敏感词
        from .sensitive import check_text
        check_text(serializer.validated_data.get('content'), field_label='评论')

        saved = serializer.save(
            author=self.request.user,
            post_id=self.kwargs['post_pk'],
            reply_to=reply_to
        )

        # 第 42 批：评论 +2 积分
        try:
            from .services_points import award_points
            award_points(self.request.user, 'comment', ref_type='comment', ref_id=saved.id)
        except Exception:
            logger.exception('评论积分失败 comment=%s', getattr(saved, 'id', None))

        # 第 85 批：给评论补英文译文。**必须放在发通知之前** —— 下面的站内通知
        # 要把英文摘要写进 message_en，翻译晚了就只能塞中文（英文界面下通知里
        # 会重新冒出中文）。翻译失败只记日志，不影响评论本身。
        if getattr(settings, 'TRANSLATE_ON_WRITE', True):
            try:
                from .services_translate import safe_translate_instance
                safe_translate_instance(serializer.instance)
            except Exception:  # noqa: BLE001
                logger.exception('评论翻译调度失败 comment=%s', getattr(serializer.instance, 'id', None))

        # 第 37 批：给帖子作者发"有人回复了你"的站内通知（notify() 内部会跳过自己回复自己）
        try:
            from .views_notify import notify
            post = serializer.instance.post
            comment = serializer.instance
            # 第 85 批：英文标题/摘要优先用译文，没有译文才回落中文
            notify(
                post.author,
                type='reply',
                title=f'{self.request.user.username} 回复了你的帖子：{post.title}',
                title_en=f'{self.request.user.username} replied to your post: {post.display_title_en}',
                message=(comment.content or '')[:120],
                message_en=(comment.content_en or comment.content or '')[:120],
                url=f'/forum/post/{post.id}',
                actor=self.request.user,
                post=post,
                comment=comment,
            )
        except Exception:
            logger.exception('发送回复通知失败 comment=%s', getattr(serializer.instance, 'id', None))

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def translate(self, request, *args, **kwargs):
        """第 85 批：按需翻译评论/回复（与帖子同名接口同语义，见 PostViewSet.translate）"""
        from .services_translate import TranslateError, is_enabled, translate_instance

        comment = self.get_object()
        if not is_enabled():
            return Response({'detail': '翻译服务未启用（TRANSLATE_PROVIDER=none）'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        try:
            translate_instance(comment)
        except TranslateError as exc:
            logger.warning('按需翻译评论失败 comment=%s: %s', comment.id, exc)
            return Response({'detail': f'翻译失败：{exc}'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        comment.refresh_from_db(fields=['content_en', 'translation_hash',
                                        'translation_source', 'translated_at'])
        return Response({
            'id': comment.id,
            'content_en': comment.content_en,
            'translation_stale': comment.translation_stale,
            'translation_source': comment.translation_source,
            'translated_at': comment.translated_at,
        })

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def delete(self, request, *args, **kwargs):
        """软删除评论"""
        comment = self.get_object()
        
        # 检查用户是否有权限删除评论（本人 / 内容维护者 / 版主）
        # 第 124/128 批：`request.user.is_staff` 改为 review 模块判定
        # —— 内容审核属于内容事务，第 125 批起信息编辑员也能删违规评论。
        if not (request.user == comment.author
                or has_content_module(request.user, MODULE_REVIEW)
                or request.user.groups.filter(name='Moderators').exists()):
            return Response(
                {'detail': '您没有权限删除此评论'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # 第 149 批：实现抽到模块级 `soft_delete_comment()` ——
        # 控制台的评论管理（`views_comments_admin.py`）也要走**同一个**函数，
        # 否则"农户端删评论"与"控制台删评论"迟早会变成两套口径。
        # 第 152 批：把操作人一并记下（作者本人删 vs 版主删，恢复前要分得清）
        soft_delete_comment(comment, by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
        
    def perform_destroy(self, instance):
        """硬删除评论（**不可逆**：仅全权管理员 / 版主）"""
        # 第 124/128 批：这里刻意**不用** review 模块 ——
        # 内容编辑（EDITOR）做审核用上面的软删除（内容置为 [已删除]，可追溯），
        # 而"从库里真的删掉"属于不可逆动作，与"删除意见反馈"同类，只给全权管理员。
        # （口径：不可逆动作 = is_full_admin()，见 capabilities.py 的说明。）
        if not (is_full_admin(self.request.user)
                or self.request.user.groups.filter(name='Moderators').exists()):
            raise PermissionDenied('只有管理员可以硬删除评论')
            
        # 软/硬删除都只需处理评论本身；原代码在此维护不存在的 parent.reply_count
        # 会抛 ValueError 导致 500，已移除（见 destroy 中的说明）。
        instance.delete()

    @action(detail=True, methods=['get'], url_path='replies',
            permission_classes=[permissions.AllowAny])  # 定义自定义动作
    def replies(self, request, post_pk=None, pk=None):
        """
        获取某条评论的回复列表（分页）

        说明：前端 PostDetailView 展开「查看回复」时会调用
        /forums/posts/{post_pk}/comments/{pk}/replies/，但后端此前没有这个动作，
        导致回复列表一直加载不出来。
        """
        comment = self.get_object()  # 获取评论对象
        queryset = comment.replies.filter(is_deleted=False).select_related('author').order_by('created_at')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CommentSerializer(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)

        serializer = CommentSerializer(queryset, many=True, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='likes',
            permission_classes=[permissions.AllowAny])
    def likes(self, request, post_pk=None, pk=None):
        """谁点赞了这条评论（第 25 批新增）"""
        comment = self.get_object()
        queryset = Like.objects.filter(comment=comment).select_related('user').order_by('-created_at')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = LikeUserSerializer(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)

        serializer = LikeUserSerializer(queryset, many=True, context=self.get_serializer_context())
        return Response({'count': queryset.count(), 'results': serializer.data})

    @action(detail=True, methods=['post'])  # 定义自定义动作
    def like(self, request, post_pk=None, pk=None):  # 定义点赞评论方法
        """点赞/取消点赞评论

        第 16 批修复：原先只返回 ``{'detail': '点赞成功'}``，前端拿不到最新状态，
        只能靠本地取反猜测（与帖子点赞接口的返回契约也不一致）。
        现与 ``PostViewSet.like`` 对齐，返回 status / is_liked / like_count。
        """
        comment = self.get_object()  # 获取评论对象
        like, created = Like.objects.get_or_create(  # 获取或创建点赞记录
            user=request.user,  # 设置用户
            comment=comment  # 设置评论
        )
        if not created:  # 如果点赞已存在
            like.delete()  # 删除点赞记录
            comment.refresh_from_db(fields=['like_count'])  # 取回联动更新后的计数
            return Response({
                'status': 'unliked',
                'is_liked': False,
                'like_count': comment.like_count,
                'detail': '已取消点赞',
            }, status=status.HTTP_200_OK)  # 返回取消点赞响应
        comment.refresh_from_db(fields=['like_count'])

        # 第 37 批：评论被点赞也给作者发通知
        try:
            from .views_notify import notify
            notify(
                comment.author,
                type='comment_like',
                title=f'{request.user.username} 点赞了你的评论',
                title_en=f'{request.user.username} liked your comment',
                message=(comment.content or '')[:120],
                url=f'/forum/post/{comment.post_id}',
                actor=request.user,
                post=comment.post,
                comment=comment,
            )
        except Exception:
            logger.exception('发送评论点赞通知失败 comment=%s', comment.id)

        return Response({
            'status': 'liked',
            'is_liked': True,
            'like_count': comment.like_count,
            'detail': '点赞成功',
        }, status=status.HTTP_201_CREATED)  # 返回点赞成功响应


class LikeViewSet(viewsets.ModelViewSet):  # 定义点赞视图集
    """
    点赞视图集
    - 登录用户可点赞/取消点赞
    - 不能给自己点赞
    - 防刷限制和频率控制
    """
    serializer_class = LikeSerializer  # 设置序列化器类
    permission_classes = [permissions.IsAuthenticated]  # 设置权限类

    def get_queryset(self):  # 定义获取查询集方法
        # 用户只能查看自己的点赞记录
        return Like.objects.filter(user=self.request.user)  # 按用户筛选点赞记录

    def create(self, request, *args, **kwargs):  # 重写创建方法
        """
        直接创建点赞记录（`POST /api/forums/likes/`）。

        ⚠️ 第 106 批修了一个"计数被加两次"的 bug
        ------------------------------------------------------------------
        改前这里在 `Like.objects.create(...)` 之后又写了：

            post.like_count = F('like_count') + 1
            post.save(update_fields=['like_count', 'updated_at'])

        **但计数字段不是这个视图维护的** —— `models_forum.Like.save()`
        （被上面那句 create 触发）已经把 `post.like_count` **精确重算**成
        `Like.objects.filter(post_id=...).count()`。于是同一次请求里有两个人
        写同一个字段，结果是「真实行数 + 1」。

        实测（第 106 批）：点赞前 `like_count=0 / 真实行数=0`，POST 之后
        `like_count=2 / 真实行数=1`。

        为什么线上没暴露：前端点赞走的是 `PostViewSet.like`
        （`/forums/posts/{id}/like/`），那条路径的注释明确写着
        「Like.save 会重算 like_count」，**写法是对的**。但这个
        `POST /api/forums/likes/` 是公开注册的接口，任何直接调它的客户端
        （移动端、脚本、第三方）都会把数据写坏。

        结论：**计数只由模型层维护**，视图不再自己加减。
        """
        # 检查请求频率
        # ⚠️ 原来这里的变量名是 `one_minute_ago`，但实际减的是 10 秒 ——
        #    名字与事实不符，会让人按"每分钟"去理解限流规则（第 106 批改名）。
        window_start = timezone.now() - timezone.timedelta(seconds=LIKE_RATE_WINDOW_SECONDS)

        recent_likes = Like.objects.filter(  # 获取窗口内的点赞数
            user=request.user,  # 按用户筛选
            created_at__gte=window_start  # 按时间筛选
        ).count()  # 计数

        if recent_likes >= LIKE_RATE_LIMIT:  # 检查频率限制
            return Response(  # 返回错误响应
                # 第 106 批：文案里带上真实规则（"N 秒内最多 M 次"），
                # 否则用户只知道"太频繁"、不知道要等多久。
                {
                    'detail': f'操作过于频繁，{LIKE_RATE_WINDOW_SECONDS} 秒内最多点赞 '
                              f'{LIKE_RATE_LIMIT} 次，请稍后再试',
                    'code': 'too_many_requests',
                    'retry_after': LIKE_RATE_WINDOW_SECONDS,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS  # 设置HTTP状态码
            )

        # 获取帖子ID
        post_id = request.data.get('post')  # 获取帖子ID
        if not post_id:  # 检查帖子ID是否存在
            return Response(  # 返回错误响应
                {'post': ['This field is required.']},
                status=status.HTTP_400_BAD_REQUEST  # 设置HTTP状态码
            )

        try:  # 尝试获取帖子
            # 第 91 批：Post.active —— 已软删除的帖子不能再被点赞（否则"删了还能赞"）
            post = Post.active.get(pk=post_id)  # 获取帖子对象
        except Post.DoesNotExist:  # 捕获异常
            return Response(  # 返回错误响应
                {'post': ['Invalid post id.']},
                status=status.HTTP_404_NOT_FOUND  # 设置HTTP状态码
            )

        # 检查是否已经点过赞
        if Like.objects.filter(user=request.user, post=post).exists():  # 检查点赞是否存在
            return Response(  # 返回错误响应
                {'detail': '已经点过赞了'},
                status=status.HTTP_400_BAD_REQUEST  # 设置HTTP状态码
            )

        # 不能给自己点赞
        if post.author == request.user:  # 检查是否为作者
            return Response(  # 返回错误响应
                {'detail': '不能给自己的帖子点赞'},
                status=status.HTTP_400_BAD_REQUEST  # 设置HTTP状态码
            )

        # 创建点赞记录
        #
        # 第 106 批：**删掉了这里的 `post.like_count = F('like_count') + 1`**
        # （原来在第 1318-1319 行）。理由见方法 docstring：计数由
        # `Like.save()` 精确重算，视图再加 1 就是重复计数。
        # 需要读回最新计数时用 `refresh_from_db`（与 PostViewSet.like 一致）。
        #
        # ⚠️ 返回值仍然要接住：下面 `self.get_serializer(like)` 需要这个对象。
        #    （第 106 批我第一版把它改成不接返回值的 `Like.objects.create(...)`，
        #     结果序列化那一行 `NameError: name 'like' is not defined` → 500。
        #     这个接口本来就没人测过，所以这种低级错误也不会有人替你发现。）
        like = Like.objects.create(user=request.user, post=post)  # 创建点赞
        post.refresh_from_db(fields=['like_count'])

        # 注意（第 35 批）：这里原本调用 self.send_like_notification(post, request.user)，
        # 但**整个项目里根本没有这个方法** —— LikeViewSet / PostViewSet 及任何 mixin 都没有定义它。
        # 只要有人请求 POST /api/forums/likes/，就会 AttributeError → 500。
        # （前端点赞走的是 PostViewSet.like，即 /forums/posts/{id}/like/，所以一直没暴露。）
        # "被点赞通知"是用户反馈里提到的待做功能，等真正实现通知模型后再接回来，
        # 现在先移除这个必然报错的调用，避免留一个 500 的公开接口。

        # 返回创建成功的响应
        serializer = self.get_serializer(like)  # 序列化点赞数据
        headers = self.get_success_headers(serializer.data)  # 获取成功头
        return Response(  # 返回成功响应
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers  # 设置响应头
        )

    def destroy(self, request, *args, **kwargs):  # 重写删除方法
        """
        删除一条点赞记录（`DELETE /api/forums/likes/{id}/`）。

        ⚠️ 第 106 批：同样删掉了视图里的 `F('like_count') - 1`。
        `Like.delete()`（`models_forum.py`）会精确重算计数，视图再减 1
        就是**重复递减** —— 与 create 那个 bug 是同一对孪生问题，
        表现为"取消点赞后数字比实际少 1"，越点越少甚至变负。
        """
        # 获取点赞记录
        try:  # 尝试获取点赞
            like = self.get_object()  # 获取点赞对象

            # 删除点赞记录（Like.delete 会重算 like_count，视图不再自己减）
            like.delete()  # 删除点赞

            return Response(status=status.HTTP_204_NO_CONTENT)  # 返回成功响应

        except Exception as e:  # 捕获异常
            return Response(  # 返回错误响应
                {'detail': str(e)},  # 设置错误详情
                status=status.HTTP_400_BAD_REQUEST  # 设置HTTP状态码
            )


# ============================================================================
# 第 149 批：软删除评论（农户端与控制台**共用**这一个实现）
# ============================================================================
#: 软删除后正文的占位文案（农户端与控制台都靠它识别"这条被删过"）
DELETED_PLACEHOLDER = '[已删除]'


def restore_comment(comment):
    """
    恢复一条被软删除的评论（第 152 批，**仅全权管理员**调用）

    把 `content` 放回 `original_content`，并清空这两样删除痕迹。没有原文的
    （本批之前删的、或硬删过的）**不在这里处理** —— 调用方先判断
    `comment.original_content`，否则"恢复"会恢复成 `[已删除]`，比不恢复更糟。

    返回值：恢复后的 comment（调用方负责记审计日志）。
    """
    comment.content = comment.original_content
    comment.is_deleted = False
    comment.original_content = ''
    comment.deleted_by = None
    comment.save(update_fields=['content', 'is_deleted', 'original_content',
                                'deleted_by', 'updated_at'])
    if comment.post_id:
        comment.post.update_comment_count()
    return comment


def soft_delete_comment(comment, by=None):
    """
    软删除一条评论：内容置为 `[已删除]`、`is_deleted=True`，并重算帖子的评论数

    为什么抽成模块级函数：农户端（`CommentViewSet.delete`）与控制台的评论管理
    （`views_comments_admin.py`）都要做这件事。**同一件事写两遍，迟早变成两套口径**
    —— 这个项目里已经栽过几次（第 16/17 批的评论数、第 128 批的双删除口径）。

    两个历史坑都在这里兜住（原注释保留）：
      · 软删除走的是 `update_fields` 保存，而 `Comment.save()` 里维护
        `post.comment_count` 的条件是「未删除且不是回复」—— 此时 `is_deleted=True`，
        该分支被跳过 → 帖子的评论数不会减少。所以这里**显式重算一次**。
      · 原代码还会去维护 `comment.parent.reply_count`，但 Comment 模型**没有这个字段**，
        `save(update_fields=[...])` 直接抛 ValueError → 删除评论接口稳定 500
        （而评论其实已经软删除了，属于"半成功"）。回复数是实时统计的，本不需要这个冗余字段。
    """
    # 第 152 批：**先把原文转存下来**，否则"删除"就是不可恢复的。
    # ⚠️ 只在"原本没删过"时才转存：重复点删除（接口是幂等的）不能把
    #    `[已删除]` 当成原文存进去 —— 那样「恢复」会把占位文案恢复成正文。
    if not comment.is_deleted and comment.content != DELETED_PLACEHOLDER:
        comment.original_content = comment.content or ''
        comment.deleted_by = by if getattr(by, 'is_authenticated', False) else None
    comment.content = DELETED_PLACEHOLDER
    comment.is_deleted = True
    comment.save(update_fields=['content', 'is_deleted', 'original_content',
                                'deleted_by', 'updated_at'])
    if comment.post_id:
        comment.post.update_comment_count()
    return comment
