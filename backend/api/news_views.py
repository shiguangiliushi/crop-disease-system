from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.pagination import PageNumberPagination
# 第 399 批：列表新增的查询参数是手写 query_params 的，drf-spectacular 推导不到，
# 必须显式登记，否则 docs/openapi.yaml 里看不到这些参数（前端只能靠口口相传）。
from drf_spectacular.types import OpenApiTypes  # 第 404 批：ai-assist 的 schema 标注
from drf_spectacular.utils import OpenApiParameter, extend_schema
from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.http import Http404
from django.utils import timezone
import json
import logging
import re

from .assistant import llm  # 第 404 批：AI 辅助复用助手链路的 LLM 调用层
from .models import News
from .serializers import NewsRelatedResponseSerializer, NewsSerializer
# 第 402 批：发布扇出（订阅了该分类/关联病害的用户收站内通知）。
# 本模块不反向依赖这里，不存在循环导入。
from .views_news_subscription import notify_news_subscribers
# 第 124 批：能力判定统一收口（新闻维护 = CONTENT，信息编辑员可）
from .capabilities import MODULE_NEWS, has_content_module
# 第 91 批：图片上传统一校验（大小上限 + 按文件头探测真实格式 + 随机文件名）
from .image_validation import (
    ALLOWED_FORMATS,
    ImageValidationError,
    validate_image_upload,
)

#: 新闻配图允许的格式（不含 BMP：编辑器插图用不到，且体积偏大）
NEWS_IMAGE_FORMATS = {k: v for k, v in ALLOWED_FORMATS.items() if k != 'BMP'}


# 第 399 批：`ordering` 的语义别名 → 实际排序字段。
# 为什么用白名单而不是把参数直接塞进 order_by()：不存在的字段会抛 FieldError
# 变成 500（recent 原实现正是如此），而且"任意字段都能排序"等于把模型结构
# 暴露给调用方。白名单之外的取值统一 400，并列出合法值方便前端自查。
ORDERING_ALIASES = {
    'recent': ('-created_at',),
    'hot': ('-views', '-created_at'),
    'oldest': ('created_at',),
}
#: 兼容"裸字段"（旧 recent 调用方会直接传 -created_at 这类字段名），可带 - 前缀。
ORDERING_FIELDS = {'created_at', 'views', 'published_at', 'updated_at'}
ORDERING_ERROR = (
    '排序参数不合法，合法取值：recent / hot / oldest，'
    '或字段 created_at / views / published_at / updated_at（可带 - 前缀）'
)

#: 第 399 批：标签分隔符 —— 中英文逗号、顿号、中英文分号都算（表单里手打很随意）。
TAG_SPLIT_RE = re.compile(r'[,，、;；]')
#: 第 399 批：标签筛选最多取前 5 个（AND 条件堆太多时查询计划会变差，前端也不该多选更多）。
MAX_TAG_FILTERS = 5

#: 第 399 批：时间范围参数 → 天数；'all' 表示不限。
DATE_RANGE_DAYS = {'7d': 7, '30d': 30}
DATE_RANGE_ERROR = '时间范围参数不合法，合法取值：7d / 30d / all'

#: 第 399 批：新增列表查询参数的 OpenAPI 登记（drf-spectacular 推导不到手写 query_params）
NEWS_LIST_OPENAPI_PARAMETERS = [
    OpenApiParameter(
        name='ordering', type=str, location=OpenApiParameter.QUERY, required=False,
        description='排序方式：recent（默认，最新） / hot（最热） / oldest（最早）；'
                    '也兼容裸字段 created_at / views / published_at / updated_at（可带 - 前缀）。',
    ),
    OpenApiParameter(
        name='tags', type=str, location=OpenApiParameter.QUERY, required=False,
        description='标签筛选，逗号分隔（中英文逗号 / 顿号 / 分号均可），最多取前 5 个；'
                    '多个标签是 AND（必须同时命中）。',
    ),
    OpenApiParameter(
        name='date_range', type=str, location=OpenApiParameter.QUERY, required=False,
        description='时间范围：7d（近 7 天） / 30d（近 30 天） / all（默认，不限）。'
                    '按"有效发布时间"筛：published_at 为空时用 created_at。',
    ),
    OpenApiParameter(
        name='featured', type=str, location=OpenApiParameter.QUERY, required=False,
        description='传 1 / true / yes 时，在响应里额外返回 featured 段'
                    '（is_featured=True 的前 3 条，已从普通列表与 count 中剔除）；默认不返回该键。',
    ),
    OpenApiParameter(
        name='pest', type=int, location=OpenApiParameter.QUERY, required=False,
        description='按关联病害 id 过滤（第 401 批新增）；非数字 / 非正数 id 返回 400。',
    ),
]

#: 第 399 批：热门标签聚合接口的可选参数（同样推导不到，需显式登记）
NEWS_TAGS_OPENAPI_PARAMETERS = [
    OpenApiParameter(
        name='category', type=str, location=OpenApiParameter.QUERY, required=False,
        description='只聚合该分类下的标签（policy / tech / market / report / notice）。',
    ),
    OpenApiParameter(
        name='limit', type=int, location=OpenApiParameter.QUERY, required=False,
        description='返回条数，默认 30，有效范围 1..100；非法值回退默认值。',
    ),
]

#: 第 401 批：相关推荐接口的可选参数
NEWS_RELATED_OPENAPI_PARAMETERS = [
    OpenApiParameter(
        name='limit', type=int, location=OpenApiParameter.QUERY, required=False,
        description='返回条数，默认 4，有效范围 1..10；非法值回退默认值。',
    ),
]

#: 第 401 批：`pest` 参数（按关联病害 id 过滤）的错误文案
PEST_PARAM_ERROR = '病害参数不合法，必须是数字 id'

#: 第 401 批：相关推荐打分权重 —— 病害重合最"硬"（同一作物/病害的资讯更相关），
#: 同分类次之，标签重叠最弱；标签分最多累计 3 分，避免"标签多"的新闻通吃。
RELATED_PEST_WEIGHT = 3
RELATED_CATEGORY_WEIGHT = 2
RELATED_TAG_WEIGHT = 1
RELATED_TAG_WEIGHT_CAP = 3
#: 自身标签最多取前 3 个参与"候选筛选 / 打分"，与清单里"最多取前 3 个"一致
RELATED_SELF_TAG_LIMIT = 3
#: 候选集上限：打分在 Python 侧做，先按上限截断避免大数据量下把整表拉进内存
RELATED_CANDIDATE_LIMIT = 200
#: limit 默认 4、范围 1..10（首页"相关推荐"卡片一屏放不下更多）
RELATED_DEFAULT_LIMIT = 4
RELATED_MAX_LIMIT = 10


class InvalidQueryParam(Exception):
    """第 399 批：列表查询参数非法 —— 统一转成 400，而不是落进 500 兜底。"""


# ============================================================================
# 第 404 批（P2-10 内容生产半自动化）：新闻编辑 AI 辅助
# ============================================================================
#: 支持的 AI 动作（summary=摘要 / title=改标题 / tags=标签建议 / translate=中英翻译）
AI_ACTIONS = ('summary', 'title', 'tags', 'translate')
#: 摘要/标题动作要求正文至少有 20 个字，否则模型只能瞎编
AI_MIN_CONTENT_LENGTH = 20
#: 传给模型的正文最多取前 4000 字（再长既费 token、又超出小模型的有效上下文）
AI_INPUT_CONTENT_LIMIT = 4000
#: 每用户每小时的 AI 调用上限（防止脚本把付费接口刷爆）
AI_RATE_LIMIT_PER_HOUR = 30
AI_RATE_LIMIT_WINDOW = 3600
#: 翻译动作 content_en 的截断长度（模型偶尔不听话，返回整篇长文）
AI_TRANSLATE_CONTENT_LIMIT = 1500
#: 中文 system 提示：模型爱加解释/Markdown/引号，这里明确三条禁令
AI_SYSTEM_PROMPT = (
    '你是农业行业资讯编辑助手。只输出结果本身，不要解释、不要 Markdown、不要加引号。'
)


def _clean_ai_text(text):
    """
    清洗模型输出：去 ``` 围栏、去整体包裹的成对引号、去首尾空白。

    为什么必须做：小模型经常把纯文本也包成 ```…``` 或加一对引号；这些字符
    直接回填到"摘要/标题"输入框会很难看（编辑还得手动删）。
    """
    value = (text or '').strip()
    value = re.sub(r'^```[a-zA-Z0-9_-]*\s*', '', value)
    value = re.sub(r'\s*```$', '', value).strip()
    if len(value) >= 2:
        quote_pairs = {'"': '"', "'": "'", '“': '”', '「': '」', '『': '』'}
        if value[0] in quote_pairs and value[-1] == quote_pairs[value[0]]:
            value = value[1:-1].strip()
    return value


def _parse_translate_payload(text):
    """
    从模型输出里解析翻译 JSON（容错：```json 围栏、前后说明文字）。

    返回 dict 或 None。调用方只认 `title_en` / `content_en` 两个键，其余忽略。
    """
    raw = (text or '').strip()
    candidates = []
    fenced = re.search(r'```(?:json)?\s*(.*?)```', raw, flags=re.S)
    if fenced:
        candidates.append(fenced.group(1).strip())
    candidates.append(_clean_ai_text(raw))
    # 模型常加一句"以下是翻译："再跟 JSON，从第一个 { 到最后一个 } 再试一次
    if '{' in raw and '}' in raw:
        candidates.append(raw[raw.find('{'):raw.rfind('}') + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _ai_messages(action_name, *, title='', summary='', content='', tags=''):
    """按动作拼中文 system + user prompt（输入统一截断到 4000 字）"""
    content = (content or '')[:AI_INPUT_CONTENT_LIMIT]
    if action_name == 'summary':
        user = (
            '请为下面这篇农业资讯写一段 80~120 字的中文摘要（最多不超过 200 字），'
            f'只输出摘要：\n\n{content}'
        )
    elif action_name == 'title':
        user = (
            f'原标题：{title or "（未提供）"}\n\n正文：\n{content}\n\n'
            '请输出一个更清晰准确的新闻标题（不超过 60 字），只输出标题。'
        )
    elif action_name == 'tags':
        user = (
            f'标题：{title}\n摘要：{summary}\n正文：\n{content}\n\n'
            '请输出 3~6 个中文标签，用逗号分隔，只输出标签。'
        )
    else:  # translate
        user = (
            f'标题：{title}\n\n正文：\n{content}\n\n'
            '请输出 JSON（不要解释、不要 Markdown）：'
            '{"title_en": "英文标题", "content_en": "英文正文纯文本段落，最多 1500 字"}'
        )
    return [
        {'role': 'system', 'content': AI_SYSTEM_PROMPT},
        {'role': 'user', 'content': user},
    ]


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
    #: 第 399 批：头条段最多 3 条 —— 前端大卡片横排放不下更多，也避免头条区喧宾夺主
    FEATURED_LIMIT = 3
    #: 第 399 批：阅读量按"浏览者"去重的时间窗；6 小时内的重复打开只算一次
    VIEW_DEDUPE_SECONDS = 6 * 3600

    def get_serializer_context(self):
        """确保 request 对象被传入序列化器（用于拼接完整图片地址）"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    @staticmethod
    def _can_manage_news(user):
        """
        能否维护新闻（`CONTENT` 能力）

        第 124 批：判定统一收口到 `capabilities.py`（本方法原来叫 `_is_admin`，
        自己抄了一份 `is_staff or is_superuser or role=='ADMIN'`）。
        语义不变；第 125 批起**信息编辑员（EDITOR）也能维护新闻** ——
        新闻与病害百科同属内容生产。
        """
        return has_content_module(user, MODULE_NEWS)

    def get_permissions(self):
        """
        权限划分：
        - 列表 / 详情 / 热门标签 / 相关推荐：任何人可读
        - 新增：仅内容维护者
        - 修改 / 删除：**内容维护者**或该新闻作者
        """
        # 只读动作对所有人开放（含旧版兼容接口 legacy_detail、tags 聚合与第 401 批的 related）
        if self.action in ['list', 'retrieve', 'recent', 'legacy_detail', 'tags', 'related']:
            return [permissions.AllowAny()]

        user = self.request.user
        if not user or not user.is_authenticated:
            return [permissions.IsAdminUser()]

        if self._can_manage_news(user):
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
        内容维护者可看到全部新闻（含未发布 / 等待定时发布），其他人只能看到"已发布且到点"的。

        判定统一走 `_can_manage_news`，避免与 `get_permissions`、前端能力口径
        出现"三处口径不一"（本项目历史上已因此踩过坑，见完善记录第 17 批）。

        第 38 批：新增**定时发布** —— `published_at` 为空或已到点才对外可见；
        设成未来时间的新闻在到点前只有管理员能看到（管理页会显示"定时"状态）。
        """
        from django.db.models import Q
        from django.utils import timezone

        # 第 401 批：列表 / 详情都会带出 related_pest_details（关联病害 chip），
        # 不预取的话每篇新闻多一次查询（列表一页 10 条就是 10 次 N+1）。
        queryset = News.objects.all().prefetch_related('related_pests').order_by('-created_at')
        if self._can_manage_news(self.request.user):
            return queryset
        return queryset.filter(is_published=True).filter(
            Q(published_at__isnull=True) | Q(published_at__lte=timezone.now())
        )

    # ------------------------------------------------------------------
    # 第 399 批：列表公共筛选 / 排序（list 与 recent 共用，避免两个列表接口参数同名不同行为）
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_flag(value):
        """第 399 批：开关型查询参数的口径 —— 1 / true / yes 视为开启（与 is_published 一致）"""
        return str(value or '').strip().lower() in ('1', 'true', 'yes')

    @staticmethod
    def _parse_tags(raw):
        """
        第 399 批：把 `tags` 参数拆成标签名列表。

        分隔符同时认中英文逗号、顿号、中英文分号：标签是编辑手打的，
        「小麦,病害」「小麦，病害」「小麦、病害」都要能拆开，不然前端只能
        强迫用户记住某一种写法。最多取前 5 个，其余忽略（AND 条件堆太多没意义）。
        """
        if not raw:
            return []
        names = [name.strip() for name in TAG_SPLIT_RE.split(raw)]
        return [name for name in names if name][:MAX_TAG_FILTERS]

    @staticmethod
    def _apply_ordering(queryset, ordering, title_rank_field=None):
        """
        第 399 批：把 `ordering`（语义别名或裸字段）翻译成 order_by，非法值抛 400。

        为什么不再直接 `queryset.order_by(ordering)`：recent 以前就是这么写的，
        传一个不存在的字段会抛 FieldError 变成 500；白名单之外统一 400，
        前端拼错参数时能看到原因，也不会把模型字段结构暴露给调用方。

        第 401 批：`title_rank_field` 非空时（搜索场景）把它插到第一排序键 ——
        "标题命中"比"只有正文/摘要命中"更相关，必须优先；同组内再按用户选的
        recent / hot / oldest / 裸字段排（这个"组内排序"是需求明确保留的）。
        """
        raw = (ordering or '').strip()
        if not raw:
            order_fields = ('-created_at',)
        elif raw in ORDERING_ALIASES:
            order_fields = ORDERING_ALIASES[raw]
        else:
            field = raw[1:] if raw.startswith('-') else raw
            if field not in ORDERING_FIELDS:
                raise InvalidQueryParam(ORDERING_ERROR)
            order_fields = (raw,)

        if title_rank_field:
            order_fields = (title_rank_field,) + order_fields
        return queryset.order_by(*order_fields)

    @staticmethod
    def _apply_date_range(queryset, date_range):
        """
        第 399 批：时间快捷筛选（近 7 天 / 近 30 天 / 全部）。

        "有效发布时间" = `published_at` 有值就用它，否则回退 `created_at`：
        新闻有"立即发布（published_at=NULL）"与"定时发布"两种形态，只按
        published_at 过滤会把**所有立即发布**的新闻漏掉 —— 用户看到的是
        "近 7 天一条都没有"，而列表里明明有昨天刚发的。

        必须显式写 null 分支：SQL 里 `NULL >= 时间` 的结果是 NULL（不命中），
        单靠 `published_at__gte=cutoff` 天然漏掉立即发布的新闻。
        """
        value = (date_range or '').strip().lower() or 'all'
        if value == 'all':
            return queryset
        if value not in DATE_RANGE_DAYS:
            raise InvalidQueryParam(DATE_RANGE_ERROR)
        cutoff = timezone.now() - timezone.timedelta(days=DATE_RANGE_DAYS[value])
        return queryset.filter(
            Q(published_at__gte=cutoff)
            | Q(published_at__isnull=True, created_at__gte=cutoff)
        )

    def _apply_common_filters(self, queryset, params):
        """
        第 399 批：list 与 recent 共用的筛选（搜索 / 分类 / 发布状态 / 标签 / 时间范围）。

        抽出来的原因：recent 是给旧前端留的列表接口，如果只有 list 认识新参数，
        同一个 `tags` 在 recent 上会被静默忽略 —— 这种"参数名对、行为不对"
        的问题最难排查。公共筛选 + 公共排序后，两个接口的口径完全一致。

        params 既可能是 QueryDict（list 直接传 request.query_params），
        也可能是 recent 解析出来的 dict，统一用 `.get()` 读取。

        第 401 批：
          · 搜索纳入 `summary`（P0 新增了摘要字段，用户按正文里的词搜不到
            写在摘要里的内容会显得"搜索失灵"）；
          · 搜索非空时给查询集加 `title_hit` 注解并返回（标题命中=0、其余=1），
            由 `_apply_ordering` 拼成第一排序键 —— 相关度优先于用户选的排序；
          · 新增 `pest` 参数：按关联病害 id 过滤（M2M，必须 distinct 防重复行）。

        返回值：(queryset, title_rank_field)；未搜索时 title_rank_field 为 None。
        """
        search_query = params.get('search', '')
        search_type = params.get('search_type', 'title')
        title_rank_field = None

        if search_query:
            if search_type == 'title':
                queryset = queryset.filter(title__icontains=search_query)
            elif search_type == 'content':
                # 第 401 批：正文搜索同时覆盖摘要（摘要也是"内容"的一部分）
                queryset = queryset.filter(
                    Q(content__icontains=search_query) | Q(summary__icontains=search_query)
                )
            else:
                queryset = queryset.filter(
                    Q(title__icontains=search_query)
                    | Q(content__icontains=search_query)
                    | Q(summary__icontains=search_query)
                )

            # 第 401 批：标题命中优先。注解值 0 排在 1 前面（升序），
            # 排序在 _apply_ordering 里完成，这里只负责把"是否命中标题"算出来。
            queryset = queryset.annotate(
                title_hit=Case(
                    When(title__icontains=search_query, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            )
            title_rank_field = 'title_hit'

        category = params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        is_published = params.get('is_published')
        if is_published not in (None, ''):
            queryset = queryset.filter(
                is_published=str(is_published).lower() in ('true', '1', 'yes')
            )

        # 第 401 批：按关联病害过滤。合法 id 才进查询；非整数 / 非正数 / 超出
        # 32 位整型范围一律 400 —— 让前端知道参数拼错了，而不是静默返回全表。
        raw_pest = params.get('pest')
        if raw_pest not in (None, ''):
            try:
                pest_id = int(raw_pest)
            except (TypeError, ValueError):
                raise InvalidQueryParam(PEST_PARAM_ERROR)
            if pest_id <= 0 or pest_id > 2147483647:
                raise InvalidQueryParam(PEST_PARAM_ERROR)
            # M2M 过滤会按"命中的关联行"给出重复新闻，必须 distinct
            queryset = queryset.filter(related_pests__id=pest_id).distinct()

        # 第 399 批：标签筛选是 **AND** —— 多个标签要同时命中，逐次 filter
        #（tags 是单个逗号分隔的字符串字段，没法用一条 SQL 干净地做多值匹配）。
        for tag in self._parse_tags(params.get('tags')):
            queryset = queryset.filter(tags__icontains=tag)

        queryset = self._apply_date_range(queryset, params.get('date_range'))
        return queryset, title_rank_field

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
        # 第 402 批：新建即"对公众可见"才通知订阅者；草稿 / 定时未到点的不发
        #（它们要等 publish 动作或定时补发命令，见 update / notify_pending_news）。
        if serializer.instance.is_visible_to_public:
            notify_news_subscribers(serializer.instance, actor=request.user)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        """自动把当前用户设为发布人"""
        serializer.save(author=self.request.user)

    @extend_schema(parameters=NEWS_LIST_OPENAPI_PARAMETERS)
    def list(self, request, *args, **kwargs):
        """
        新闻列表
        - 支持分页
        - 支持按标题 / 内容 / 全部搜索（search + search_type；第 401 批起 content/all
          也会搜摘要，且标题命中的条目整体排在前面）
        - 支持按分类筛选（category）
        - 支持按发布状态筛选（is_published=true/false，仅对管理员有意义）
        - 第 399 批：支持排序（ordering）、标签（tags）、时间范围（date_range），
          以及仅在 featured=1 时返回的"头条精选"段（featured）
        - 第 401 批：支持按关联病害过滤（pest=<id>）
        """
        queryset = self.get_queryset()

        try:
            queryset, title_rank_field = self._apply_common_filters(
                queryset, request.query_params,
            )
            queryset = self._apply_ordering(
                queryset, request.query_params.get('ordering', 'recent'), title_rank_field,
            )
        except InvalidQueryParam as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # 第 399 批：只有显式 featured=1 才注入头条段 —— 默认关闭是为了让旧客户端
        #（管理页 / 移动端 / 旧版前端缓存）拿到的响应结构与改版前**完全一致**：
        # 凭空多一个 featured 键，可能让按结构解析的旧代码误判。
        featured_enabled = self._parse_flag(request.query_params.get('featured'))
        featured_data = None
        if featured_enabled:
            # 头条从"经过全部筛选与可见性"的查询集里取：草稿 / 未到点 / 被分类或
            # 搜索筛掉的精选不能出现在头条区（普通用户看不到，管理员传
            # is_published=false 时也不该再冒出来）。
            featured_items = list(
                queryset.filter(is_featured=True).order_by('-created_at')[:self.FEATURED_LIMIT]
            )
            if featured_items:
                # 头条已经单独展示，普通列表里必须剔除，否则同一篇会被渲染两次；
                # 分页器的 count 也要同步，否则"共 N 条"和实际能翻到的条目对不上。
                queryset = queryset.exclude(pk__in=[item.pk for item in featured_items])
            featured_data = self.get_serializer(featured_items, many=True).data

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            if featured_enabled:
                response.data['featured'] = featured_data
            return response

        # 非分页兜底分支（pagination_class 被置空时才会走到）：列表型响应塞不下
        # 自定义键，改用与分页一致的 results/count 形状，保证 featured 一定带得出去。
        serializer = self.get_serializer(queryset, many=True)
        if not featured_enabled:
            return Response(serializer.data)
        return Response({
            'count': queryset.count(),
            'next': None,
            'previous': None,
            'results': serializer.data,
            'featured': featured_data,
        })

    def _record_view(self, instance):
        """
        第 399 批：详情阅读量 +1，同一浏览者 6 小时内只计一次。

        为什么去重：详情页每次打开（F5、返回再进、分享链接被反复点）都 +1 的话，
        阅读量就成了"谁刷新得多"，用它排"最热"毫无意义。

        用 `cache.add()` 判"这个浏览者是不是 6 小时内第一次看"：add 只在 key
        不存在时写入并返回 True，本地内存 / Redis 后端下都是原子操作，并发也不会
        重复计数，不需要额外加锁。

        浏览者标识优先级（同一账号换设备也应只算一次，所以登录用户优先用 pk）：
          · 登录用户 → user.pk；
          · 匿名 → session_key（同一浏览器会话内去重；
            未登录访客首次请求还没有会话，回退 REMOTE_ADDR）。
        """
        request = self.request
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            viewer = f'user:{user.pk}'
        else:
            session_key = getattr(getattr(request, 'session', None), 'session_key', None)
            viewer = f'anon:{session_key or request.META.get("REMOTE_ADDR") or "unknown"}'

        try:
            if not cache.add(
                f'news:view:{instance.pk}:{viewer}', 1, self.VIEW_DEDUPE_SECONDS,
            ):
                return
            # 用 F() 在数据库层自增，避免"读-改-写"在并发下丢计数
            News.objects.filter(pk=instance.pk).update(views=F('views') + 1)
            instance.refresh_from_db(fields=['views'])
        except Exception as exc:
            # 阅读量只是展示数据：缓存/统计出错不该把"读新闻"这条主路径变成 500。
            logger.warning('新闻阅读量计数失败（pk=%s）: %s', instance.pk, exc)

    @staticmethod
    def _brief_news(obj):
        """第 401 批：上一篇 / 下一篇只需要跳转用的最小信息，不返回整条新闻"""
        if obj is None:
            return None
        return {'id': obj.pk, 'title': obj.title, 'title_en': obj.title_en}

    def _get_neighbors(self, instance):
        """
        第 401 批：详情页的"上一篇 / 下一篇"。

        口径：
          · 只在 `get_queryset()` 里找 —— 匿名不能通过"上一篇"点进一篇草稿
            或还没到点的定时新闻（可见性必须与列表完全一致）；
          · 按 created_at 排序，created_at 相同用 pk 兜底（批量导入常出现同秒）；
          · prev = 更早的一条里最近的那条（`-created_at, -pk` 取 1），
            next = 更晚的一条里最近的那条（`created_at, pk` 取 1）。
        """
        # get_queryset() 的 related_pests 预取是给序列化用的；这里只要标题三件套，
        # 清掉预取避免每次上一篇/下一篇都多查一次多对多表。
        base = self.get_queryset().prefetch_related(None)
        older = base.filter(
            Q(created_at__lt=instance.created_at)
            | Q(created_at=instance.created_at, pk__lt=instance.pk)
        ).order_by('-created_at', '-pk').first()
        newer = base.filter(
            Q(created_at__gt=instance.created_at)
            | Q(created_at=instance.created_at, pk__gt=instance.pk)
        ).order_by('created_at', 'pk').first()
        return self._brief_news(older), self._brief_news(newer)

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
            # 第 399 批：确认对象可见后才计阅读量（404 的请求不该刷量）
            self._record_view(instance)
            serializer = self.get_serializer(instance)
            # 第 401 批：上一篇 / 下一篇只加在详情响应里（列表不加 —— 每页 N 条
            # 各算两次邻居查询，而列表页用不到这两个字段）。
            payload = dict(serializer.data)
            prev_news, next_news = self._get_neighbors(instance)
            payload['prev_news'] = prev_news
            payload['next_news'] = next_news
            return Response(payload)
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
        # 第 402 批：先记编辑前的可见状态 —— 只有"不可见 → 可见"（草稿发布、
        # 定时到点后再保存、下架→重新发布）才通知订阅者；已发布新闻的普通编辑
        # 不重复打扰（管理端 toggleNewsPublished 走的正是这个 PATCH 路径）。
        was_visible = instance.is_visible_to_public
        serializer = self.get_serializer(instance, data=request.data, partial=partial or True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        if not was_visible and instance.is_visible_to_public:
            notify_news_subscribers(instance, actor=request.user)
        return Response(serializer.data)

    def perform_update(self, serializer):
        serializer.save()

    @action(detail=False, methods=['get'])
    def recent(self, request):
        """
        新闻列表（兼容旧版接口）
        - 支持 params[key]=value 与 key=value 两种参数写法
        - 第 399 批：筛选 / 排序复用 list 的公共实现 —— recent 上 tags / date_range /
          ordering 同样生效；非法 ordering 由原来的 500 改为 400
        """
        params = {}
        for key in request.query_params:
            if key.startswith('params[') and key.endswith(']'):
                params[key[7:-1]] = request.query_params[key]
            else:
                params[key] = request.query_params[key]

        page_size = int(params.get('page_size', 12))
        is_published = params.get('is_published', 'true').lower() == 'true'

        queryset = self.get_queryset()

        # 原实现用的是 `request.user.is_staff`，与 get_queryset 的判定不一致
        # （role=ADMIN 但 is_staff=False 的账号会走到"非管理员"分支）。
        # 这里统一到 _can_manage_news，且非内容维护者无论如何都只返回已发布。
        if self._can_manage_news(request.user):
            queryset = queryset.filter(is_published=is_published)
        else:
            queryset = queryset.filter(is_published=True)

        # 第 399 批：is_published 已按上面的管理员/非管理员分支处理 —— 非管理员
        # 无论如何只能看已发布；若再把它交给公共筛选，"非管理员传
        # is_published=false"就会从"已发布列表"变成空列表，与旧 recent 行为不符。
        # search_type 固定 'all'：recent 历史上一直是标题 + 正文一起搜。
        filter_params = {key: value for key, value in params.items() if key != 'is_published'}
        filter_params['search_type'] = 'all'

        try:
            queryset, title_rank_field = self._apply_common_filters(queryset, filter_params)
            queryset = self._apply_ordering(
                queryset, params.get('ordering', '-created_at'), title_rank_field,
            )
        except InvalidQueryParam as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        paginator = self.pagination_class()
        paginator.page_size = page_size
        page = paginator.paginate_queryset(queryset, request)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(parameters=NEWS_TAGS_OPENAPI_PARAMETERS)
    @action(detail=False, methods=['get'])
    def tags(self, request):
        """
        第 399 批：热门标签聚合（`GET /api/news/tags/`）

        为什么由后端聚合：`tags` 是编辑手打的逗号分隔字符串，前端要自己统计就得
        先把整个列表拉下来遍历一遍；而且"哪些算一个标签、按什么分隔"会散落在
        每个客户端里，口径迟早不一致。

        可见性直接沿用 `get_queryset()`：匿名 / 普通用户只统计"已发布且到点"的
        新闻 —— 否则草稿里的标签会出现在筛选条上，用户点进去却一条都看不到。
        可选 `category` 让标签条跟着当前分类走。

        `limit` 默认 30、有效范围 1..100，非法值**回退默认值**而不是报 400：
        标签条是装饰性筛选，参数写错不该让整页报错（与 ordering 那种"语义错误
        必须让调用方知道"的取舍不同）。
        """
        queryset = self.get_queryset()

        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        try:
            limit = int(request.query_params.get('limit', 30))
        except (TypeError, ValueError):
            limit = 30
        if not 1 <= limit <= 100:
            limit = 30

        counter = {}
        # 只取 tags 列（不实例化整条新闻），大数据量下内存占用可控。
        # get_queryset() 为列表带出了 related_pests 预取，而预取与 values_list().iterator()
        # 冲突（ValueError: chunk_size must be provided...），这里清掉 —— 本接口只读 tags。
        tags_qs = queryset.prefetch_related(None).values_list('tags', flat=True)
        for raw_tags in tags_qs.iterator():
            seen = set()
            for name in TAG_SPLIT_RE.split(raw_tags or ''):
                name = name.strip()
                if not name or name in seen:
                    continue
                # 同一篇新闻里重复写同一个标签只算一次，否则编辑复制粘贴一下
                # 就能把这个标签刷到榜首，聚合结果就失真了。
                seen.add(name)
                counter[name] = counter.get(name, 0) + 1

        # 先按出现次数降序，次数相同按名称升序（保证同一份数据每次返回顺序稳定）
        rows = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
        return Response({
            'tags': [{'name': name, 'count': count} for name, count in rows],
            'count': len(rows),
        })

    @staticmethod
    def _consume_ai_quota(user):
        """
        第 404 批：每用户每小时的 AI 调用限额（默认 30 次）。

        为什么用 cache 而不是数据库计数：这是"防刷"的软限制，不需要精确审计；
        用 `add` 抢第一次、后续 `incr` 的写法在本地内存 / Redis 后端上都够用。
        缓存后端不支持 `incr` 或临时不可用时**放行**（AI 是旁路功能，不该因为
        限流器故障把编辑挡在门外），只记一条 warning。

        返回 True=允许本次调用，False=超限。
        """
        hour_key = timezone.localtime().strftime('%Y%m%d%H')
        cache_key = f'news:ai:{user.pk}:{hour_key}'
        try:
            if cache.add(cache_key, 1, AI_RATE_LIMIT_WINDOW):
                return True
            try:
                count = cache.incr(cache_key)
            except (ValueError, NotImplementedError):
                # key 刚好过期 / 后端不支持 incr：退回"重置为 1 并放行"
                cache.set(cache_key, 1, AI_RATE_LIMIT_WINDOW)
                return True
            return count <= AI_RATE_LIMIT_PER_HOUR
        except Exception as exc:
            logger.warning('AI 限流缓存不可用，放行本次调用: %s', exc)
            return True

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            429: OpenApiTypes.OBJECT,
            503: OpenApiTypes.OBJECT,
        },
    )
    @action(detail=False, methods=['post'], url_path='ai-assist')
    def ai_assist(self, request):
        """
        第 404 批（P2-10）：新闻编辑 AI 辅助（`POST /api/news/ai-assist/`）

        入参：`{action: summary|title|tags|translate, title?, summary?, content?, tags?}`

        为什么放在新闻接口里而不是另开一套 AI 接口：四个动作都是"编辑一篇新闻时的
        辅助工具"，权限与新闻维护完全一致（CONTENT），复用 `get_permissions()` 与
        `_can_manage_news` 就不会出现"看新闻的人能调 AI、能改新闻的人反而不能"的错位。

        失败语义（前端按状态码区分即可）：
          · 503 + `AI 服务未启用或未配置`：没配 LLM 环境变量（不是 bug，先关掉入口）；
          · 503 + `AI 服务暂不可用：…`：网络/超时/HTTP 错误（可重试）；
          · 429：本小时调用次数超限（稍后再试）；
          · 500：其它未预期错误（后端看日志）。
        """
        # get_permissions() 已把非只读 action 收敛到内容维护者；这里再兜一道，
        # 防止将来有人把 ai_assist 加进只读白名单后接口裸奔。
        if not self._can_manage_news(request.user):
            return Response({'detail': '没有权限使用 AI 辅助'}, status=403)

        data = request.data if hasattr(request.data, 'get') else {}
        action_name = (data.get('action') or '').strip()
        if action_name not in AI_ACTIONS:
            return Response(
                {'error': '不支持的 AI 动作，合法取值：summary / title / tags / translate'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        title = (data.get('title') or '').strip()
        summary = (data.get('summary') or '').strip()
        content = (data.get('content') or '').strip()
        tags = (data.get('tags') or '').strip()

        # 摘要 / 改标题都依赖正文：太短的正文让模型只能编，直接告诉调用方
        if action_name in ('summary', 'title') and len(content) < AI_MIN_CONTENT_LENGTH:
            return Response(
                {'error': '正文太短，至少需要 20 个字'}, status=status.HTTP_400_BAD_REQUEST,
            )
        if action_name == 'tags' and not (title or summary or content):
            return Response(
                {'error': '请至少提供标题、摘要或正文'}, status=status.HTTP_400_BAD_REQUEST,
            )
        if action_name == 'translate' and not (title or content):
            return Response(
                {'error': '翻译至少需要标题或正文'}, status=status.HTTP_400_BAD_REQUEST,
            )

        # 先扣配额再查 LLM 是否启用：服务未配置时也不该被脚本无限打（429 先于 503）
        if not self._consume_ai_quota(request.user):
            return Response(
                {'error': 'AI 调用过于频繁，请稍后再试'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if not llm.enabled():
            return Response(
                {'error': 'AI 服务未启用或未配置，请联系管理员'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        messages = _ai_messages(
            action_name, title=title, summary=summary, content=content, tags=tags,
        )
        try:
            result = llm.chat(messages, max_tokens=600, temperature=0.3)
        except llm.LLMError as exc:
            logger.warning('新闻 AI 辅助调用失败（action=%s）: %s', action_name, exc)
            return Response(
                {'error': f'AI 服务暂不可用：{exc}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception:
            # 不把内部异常信息回给前端（可能带配置/密钥线索），只记日志
            logger.exception('新闻 AI 辅助未预期错误（action=%s）', action_name)
            return Response(
                {'error': 'AI 服务内部错误'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        model = llm.model_name()
        if action_name == 'translate':
            payload = _parse_translate_payload(result.text) or {}
            title_en = str(payload.get('title_en') or '').strip()
            content_en = str(payload.get('content_en') or '').strip()
            if not title_en or not content_en:
                return Response(
                    {'error': 'AI 返回格式异常，请稍后重试'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            return Response({
                'action': 'translate',
                'title_en': title_en[:200],
                'content_en': content_en[:AI_TRANSLATE_CONTENT_LIMIT],
                'model': model,
            })

        text = _clean_ai_text(result.text)
        if action_name == 'tags':
            # 去掉模型爱加的 #，并统一分隔符为中文逗号，方便前端 split
            parts = [part for part in re.split(r'[,，、;；\s]+', text.replace('#', ' ')) if part]
            text = '，'.join(parts)
        if action_name in ('summary', 'title'):
            text = text[:200]
        return Response({'action': action_name, 'text': text, 'model': model})

    @extend_schema(
        parameters=NEWS_RELATED_OPENAPI_PARAMETERS,
        responses={200: NewsRelatedResponseSerializer},
    )
    @action(detail=True, methods=['get'])
    def related(self, request, pk=None):
        """
        第 401 批：相关推荐（`GET /api/news/{pk}/related/`）

        为什么放在后端：相关推荐要综合"同病害 / 同分类 / 标签重叠"三类信号，
        前端要自己算就得先把整库新闻拉下来；打分权重也会随运营策略调整，
        收口在后端才能一处改、全端生效。

        口径：
          · 候选从 `self.get_queryset()` 出发并排除自身 —— 匿名拿不到草稿 / 未到点；
          · SQL 只做**候选初筛**（同分类 | 关联病害命中 | 自身前 3 个标签命中）
            并 distinct，最多取 200 条；精排在 Python 侧做 —— "病害重合几个、
            标签重合几个"用 SQL 表达既别扭又难维护；
          · 打分：每重合 1 个关联病害 +3、同分类 +2、每重合 1 个标签 +1（最多 +3）；
          · 只返回 score>0 的，按 (-score, -created_at) 排序，limit 默认 4、范围 1..10。
        """
        news = self.get_object()

        news_pest_ids = set(news.related_pests.values_list('id', flat=True))
        # 自身标签最多取前 3 个参与候选筛选与打分（与清单口径一致）
        self_tags = self._parse_tags(news.tags)[:RELATED_SELF_TAG_LIMIT]

        candidate_q = Q(category=news.category)
        if news_pest_ids:
            # 注意：related_pests__in=[] 不会产生匹配，这里显式判断，避免生成
            # 一个恒假条件（也避免让人误以为"没有关联病害就查不到候选"）。
            # 用子查询而不是直接 Q(related_pests__in=...)：直接写 M2M 条件时，
            # 它和 tags/category 的 OR 会退化成 INNER JOIN，把"仅标签重合"的候选
            # 整个丢掉（实测过）；换成 pk 子查询后所有条件都是本表单列条件。
            candidate_q |= Q(pk__in=News.objects.filter(
                related_pests__in=news_pest_ids,
            ).values('pk'))
        for tag in self_tags:
            candidate_q |= Q(tags__icontains=tag)

        candidates = list(
            self.get_queryset()
            .exclude(pk=news.pk)
            .filter(candidate_q)
            .distinct()
            .order_by('-created_at', '-pk')[:RELATED_CANDIDATE_LIMIT]
        )

        scored = []
        for candidate in candidates:
            candidate_pest_ids = {pest.pk for pest in candidate.related_pests.all()}
            score = RELATED_PEST_WEIGHT * len(news_pest_ids & candidate_pest_ids)
            if candidate.category == news.category:
                score += RELATED_CATEGORY_WEIGHT
            candidate_tags = set(self._parse_tags(candidate.tags))
            tag_overlap = len(set(self_tags) & candidate_tags)
            score += min(tag_overlap, RELATED_TAG_WEIGHT_CAP) * RELATED_TAG_WEIGHT
            if score > 0:
                scored.append((score, candidate))

        # 先按创建时间倒序、再按分数倒序（两次稳定排序）：同分时新的在前。
        # 不用单次 key=(-score, -timestamp) 是为了保留 datetime 精度、不依赖时区换算。
        scored.sort(key=lambda item: (item[1].created_at, item[1].pk), reverse=True)
        scored.sort(key=lambda item: item[0], reverse=True)

        try:
            limit = int(request.query_params.get('limit', RELATED_DEFAULT_LIMIT))
        except (TypeError, ValueError):
            limit = RELATED_DEFAULT_LIMIT
        if not 1 <= limit <= RELATED_MAX_LIMIT:
            limit = RELATED_DEFAULT_LIMIT

        results = [candidate for _, candidate in scored[:limit]]
        return Response({
            'results': self.get_serializer(results, many=True).data,
            'count': len(results),
        })

    @action(detail=True, methods=['get'], url_path='detail')
    def legacy_detail(self, request, pk=None):
        """
        获取新闻详情（兼容旧版接口 `GET /api/news/{pk}/detail/`）

        第 399 批：本接口**不**计阅读量 —— 它只为老客户端保留，纯读；
        若这里也计数，同一次阅读（前端轮询主详情 + 触发兼容接口）会被算两次。

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
