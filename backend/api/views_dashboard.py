"""
管理员数据看板（第 39 批）

背景：清单里"管理员数据看板"此前只有零散的数字 ——
`/api/statistics/` 主要服务于"识别记录"页（个人维度 + 管理员切全部用户），
没有把**用户活跃、内容产出、待办事项**汇总到一处的地方。
这里给管理端一个聚合接口，一次请求拿齐看板需要的全部数据：

    GET /api/admin/dashboard/?days=14
    GET /api/admin/news-stats/?days=30   # 第 403 批：行业动态专属看板

返回：
    totals            总量与今日/近 7 日数字（用户、识别、帖子、评论、新闻、反馈）
    detection_trend   最近 N 天识别量
    user_trend        最近 N 天新增用户
    post_trend        最近 N 天新增帖子
    pest_distribution 病害分布 Top 8
    crop_distribution 作物分布 Top 8
    posts_by_status   帖子状态分布（含"待审核"，看板上要能一眼看到待办）
    feedback_by_status 反馈处理状态分布
    top_contributors  发帖/评论最多的用户 Top 5
    recent_users      最近注册的用户 Top 5

权限：仅管理员（is_staff / is_superuser / role=ADMIN，与项目其它管理端口径一致）。
"""
import logging
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDay
from django.utils import timezone
from rest_framework import permissions, serializers
from drf_spectacular.types import OpenApiTypes  # 第 389 批
from drf_spectacular.utils import (  # 第 389 批：OpenAPI 标注
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
# 第 124 批：能力判定统一收口（看板 = CONTENT 只读；样本统计 = BROADCAST）
from .capabilities import CAP_BROADCAST, CAP_CONTENT, has_capability, is_full_admin
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DetectionHistory, Feedback, News, PestInfo
from .models_forum import Comment, Post
from .models_report import Report
from .services_content_i18n import pest_en_maps  # 第 77 批：分布图的中英对照
# 第 403 批：标签云与新闻列表的标签筛选必须用**同一套**拆分口径，
# 否则"列表能按 A,B 筛出新闻、标签云却把 'A，B' 当成一个标签"。
# news_views 不 import 本模块，不存在循环导入。
from .news_views import TAG_SPLIT_RE

logger = logging.getLogger(__name__)
User = get_user_model()


def _can_view_dashboard(user):
    """
    能否查看管理端数据看板（`CONTENT` 能力，**只读**）

    第 124 批（产品决策 #1）：**信息编辑员可以看看板**（第 125 批起），
    但看板里"能定位到具体用户"的两块（贡献榜 / 最近注册）只给全权管理员，
    见 `AdminDashboardView.get` 里的 `include_user_detail`。
    """
    return has_capability(user, CAP_CONTENT)


def _can_view_dataset_stats(user):
    """
    能否查看识别反馈的样本统计（`BROADCAST` 能力）

    第 124 批口径：它属于"数据集/模型"这类系统级信息（不是内容、也不是账号），
    与公告/预警同组，**信息编辑员不可**。当前前端没有页面在用它（纯接口），
    若将来编辑员确实需要"哪类病害总被认错"来补词条，再单独放给 CONTENT。
    """
    return has_capability(user, CAP_BROADCAST)


def _daily_counts(queryset, field, days, end_date):
    """
    按天聚合最近 N 天的数量，并补齐空白的日期（否则折线会跳日期）

    `field` 是日期字段名（如 'timestamp'），`end_date` 是最后一天（date 对象）。
    """
    start = end_date - timedelta(days=days - 1)
    rows = (
        queryset.filter(**{f'{field}__date__gte': start, f'{field}__date__lte': end_date})
        .annotate(day=TruncDay(field))
        .values('day')
        .annotate(count=Count('id'))
    )
    counts = {row['day'].date(): row['count'] for row in rows if row['day']}

    series = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        series.append({'date': day.strftime('%m-%d'), 'count': counts.get(day, 0)})
    return series


class AdminFeedbackDatasetStatsView(APIView):
    """
    识别纠错样本的**闭环度量**（第 91 批）

        GET /api/admin/dataset-stats/

    回答三个问题（这也是"识别反馈闭环"能不能跑起来的判据）：

    1. **攒了多少可用的纠错样本**：`trainable`（识别错了 + 给了正确类别）、
       其中多少已经人工确认（`confirmed`）—— 只有 confirmed 才会进导出。
    2. **模型的误判率长什么样**：按 `is_correct` 统计正负反馈，并**下钻到病害类别**
       —— 光看一个总误判率没用，要知道"哪一类总被认错"才好定向补数据。
    3. **上次导出到哪了**：`exported_at` 非空即"已导出过"，便于判断增量。

    权限：仅管理员（与看板、用户管理同一口径）。
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT, 204: None},
    )
    def get(self, request):
        if not _can_view_dataset_stats(request.user):
            return Response({'detail': '只有管理员可以查看样本统计'}, status=403)

        recognitions = Feedback.objects.filter(category='recognition')

        # 只统计"明确表过态"的反馈：is_correct 为空的记录（历史数据里存在）不计入分母
        judged = recognitions.filter(is_correct__isnull=False)
        positive = judged.filter(is_correct=True).count()
        negative = judged.filter(is_correct=False).count()
        judged_total = positive + negative

        trainable = recognitions.filter(is_correct=False, corrected_pest__isnull=False)

        # 按病害下钻：只列"被认错最多"的 Top 10，并带上正确类别的分布
        wrong_by_disease = (
            recognitions.filter(is_correct=False)
            .exclude(disease_name='')
            .values('disease_name')
            .annotate(wrong=Count('id'))
            .order_by('-wrong')[:10]
        )
        corrected_by_pest = (
            trainable.filter(corrected_pest__isnull=False)
            .values('corrected_pest__name', 'corrected_pest__name_en')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )

        return Response({
            'feedback': {
                'recognition_total': recognitions.count(),
                'judged': judged_total,
                'positive': positive,
                'negative': negative,
                # 误判率：分母只算表过态的（没表态的不该拉低指标）
                'negative_rate': round(negative / judged_total, 4) if judged_total else None,
            },
            'samples': {
                'trainable': trainable.count(),
                'pending': trainable.filter(verify_status='pending').count(),
                'confirmed': trainable.filter(verify_status='confirmed').count(),
                'rejected': trainable.filter(verify_status='rejected').count(),
                'exported': trainable.filter(exported_at__isnull=False).count(),
                'by_corrected_pest': [
                    {
                        'name': row['corrected_pest__name'],
                        'name_en': row['corrected_pest__name_en'],
                        'count': row['count'],
                    }
                    for row in corrected_by_pest
                ],
            },
            'wrong_by_disease': [
                {'disease_name': row['disease_name'], 'wrong': row['wrong']}
                for row in wrong_by_disease
            ],
            'export_command': 'python manage.py export_feedback_dataset --out <目录>',
        })


class AdminDashboardView(APIView):
    """管理端数据看板（仅管理员）"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT, 204: None},
    )
    def get(self, request):
        if not _can_view_dashboard(request.user):
            return Response({'detail': '只有管理员可以查看数据看板'}, status=403)

        try:
            days = int(request.query_params.get('days', 14))
        except (TypeError, ValueError):
            days = 14
        days = max(7, min(days, 90))  # 限制在 7~90 天，避免一次拉太多

        now = timezone.now()
        # 第 69 批修正：`timezone.now()` 是 **UTC** 时间，`.date()` 得到 UTC 日期；
        # 而 `timestamp__date=...` 与 TruncDay 都按**本地时区（Asia/Shanghai）**换算。
        # 在本地 00:00–08:00 这段（UTC 仍是前一天），两者不一致 →
        # 看板「今日识别」恒为 0、趋势最后一天也是 0。改用 localdate() 取本地日期。
        today = timezone.localdate()
        week_ago = now - timedelta(days=7)

        detections = DetectionHistory.objects.all()
        users = User.objects.all()
        # 第 91 批：帖子与评论都要排除软删除的（否则"内容概览"会把删掉的帖子算成内容量）
        posts = Post.active.all()
        comments = Comment.objects.filter(is_deleted=False)
        feedback = Feedback.objects.all()
        news = News.objects.all()

        # ---------- 总量 ----------
        totals = {
            'users': users.count(),
            'new_users_7d': users.filter(date_joined__gte=week_ago).count(),
            'active_users_7d': users.filter(last_login__gte=week_ago).count(),
            'detections': detections.count(),
            'detections_today': detections.filter(timestamp__date=today).count(),
            'detections_7d': detections.filter(timestamp__gte=week_ago).count(),
            'posts': posts.count(),
            'pending_posts': posts.filter(status='pending').count(),
            'comments': comments.count(),
            'news': news.count(),
            'news_scheduled': news.filter(
                is_published=True, published_at__gt=now,
            ).count(),
            'pest_species': PestInfo.objects.count(),
            'feedback': feedback.count(),
            'feedback_pending': feedback.filter(status='pending').count(),
            # 第 41 批：待处理举报（看板待办条要算上）
            'reports_pending': Report.objects.filter(status='pending').count(),
        }

        # ---------- 趋势 ----------
        detection_trend = _daily_counts(detections, 'timestamp', days, today)
        user_trend = _daily_counts(users, 'date_joined', days, today)
        post_trend = _daily_counts(posts, 'created_at', days, today)

        # ---------- 分布 ----------
        # 第 77 批：看板的分布图也要能在英文界面下显示英文病害名/作物名
        pest_name_en_map, crop_name_en_map = pest_en_maps()

        pest_distribution = list(
            detections.filter(pest_info__isnull=False)
            .values('pest_info__name')
            .annotate(count=Count('id'))
            .order_by('-count')[:8]
        )
        pest_distribution = [
            {
                'name': row['pest_info__name'] or '未知',
                'name_en': pest_name_en_map.get(row['pest_info__name'], ''),
                'count': row['count'],
            }
            for row in pest_distribution
        ]

        crop_distribution = list(
            detections.filter(pest_info__isnull=False)
            .values('pest_info__crop_type')
            .annotate(count=Count('id'))
            .order_by('-count')[:8]
        )
        crop_distribution = [
            {
                'name': row['pest_info__crop_type'] or '未知作物',
                'name_en': crop_name_en_map.get(row['pest_info__crop_type'], ''),
                'count': row['count'],
            }
            for row in crop_distribution
        ]

        posts_by_status = {
            row['status']: row['count']
            for row in posts.values('status').annotate(count=Count('id'))
        }
        feedback_by_status = {
            row['status']: row['count']
            for row in feedback.values('status').annotate(count=Count('id'))
        }

        # ---------- 贡献榜 / 最近注册 ----------
        #
        # 第 124 批（产品决策 #1）：**数据看板对内容编辑开放，但"能定位到具体用户"的两块不给**
        #   · top_contributors：用户名 + 发帖/评论数
        #   · recent_users：id + 用户名 + 注册/登录时间 + 角色
        # 只有全权管理员（is_staff / is_superuser / role=ADMIN）才拿到这两块；
        # 内容编辑（EDITOR）拿到的是**聚合数字**（总量、趋势、分布），看不到人。
        # 前端也据此隐藏这两个区块，但**边界在这里**（前端只是体验）。
        include_user_detail = is_full_admin(request.user)

        top_contributors = []
        recent_users = []
        if include_user_detail:
            top_contributors = list(
                users.annotate(
                    post_count=Count('forum_posts', distinct=True),
                    comment_count=Count('forum_comments', distinct=True),
                )
                .filter(Q(post_count__gt=0) | Q(comment_count__gt=0))
                .order_by('-post_count', '-comment_count')[:5]
                .values('username', 'post_count', 'comment_count')
            )

            recent_users = list(
                users.order_by('-date_joined')[:5].values('id', 'username', 'date_joined', 'last_login', 'role')
            )

        return Response({
            'generated_at': now,
            'days': days,
            'totals': totals,
            'detection_trend': detection_trend,
            'user_trend': user_trend,
            'post_trend': post_trend,
            'pest_distribution': pest_distribution,
            'crop_distribution': crop_distribution,
            'posts_by_status': posts_by_status,
            'feedback_by_status': feedback_by_status,
            'top_contributors': top_contributors,
            'recent_users': recent_users,
            # 明确告诉前端"这两块有没有数据"，省得前端自己猜（空数组 ≠ 没有用户）
            'includes_user_detail': include_user_detail,
        })


# ============================================================================
# 第 403 批（行业动态清单 P2-12）：行业动态数据看板
# ============================================================================
# 下面这组 Serializer **只用于 OpenAPI 文档**（不参与实际序列化）：这个接口返回的是
# 手工拼的 dict，drf-spectacular 推导不出结构；不显式声明的话 schema 里只有
# `type: object`，前端拿不到字段名。字段顺序与响应保持一致。
class NewsStatsTotalsSchema(serializers.Serializer):
    """totals 段：总量与阅读量"""

    all = serializers.IntegerField()
    published = serializers.IntegerField()
    draft = serializers.IntegerField()
    featured = serializers.IntegerField()
    scheduled = serializers.IntegerField()
    views_total = serializers.IntegerField()
    views_avg = serializers.FloatField()


class NewsStatsTrendPointSchema(serializers.Serializer):
    """发布趋势的一天（date 为本地日期 YYYY-MM-DD）"""

    date = serializers.CharField()
    count = serializers.IntegerField()


class NewsStatsCategoryCountSchema(serializers.Serializer):
    """分类分布的一行（固定输出 5 个分类，无数据 count=0）"""

    category = serializers.CharField()
    count = serializers.IntegerField()


class NewsStatsTopViewedSchema(serializers.Serializer):
    """阅读量 Top 榜的一行（created_at 为 ISO 字符串）"""

    id = serializers.IntegerField()
    title = serializers.CharField()
    title_en = serializers.CharField()
    views = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class NewsStatsTagCountSchema(serializers.Serializer):
    """标签云的一行"""

    name = serializers.CharField()
    count = serializers.IntegerField()


class NewsStatsResponseSchema(serializers.Serializer):
    """`GET /api/admin/news-stats/` 的完整响应结构"""

    days = serializers.IntegerField()
    totals = NewsStatsTotalsSchema()
    publish_trend = NewsStatsTrendPointSchema(many=True)
    category_distribution = NewsStatsCategoryCountSchema(many=True)
    top_viewed = NewsStatsTopViewedSchema(many=True)
    tag_cloud = NewsStatsTagCountSchema(many=True)
    generated_at = serializers.DateTimeField()


class AdminNewsStatsView(APIView):
    """
    管理端「行业动态数据看板」（第 403 批 P2-12）

        GET /api/admin/news-stats/?days=30

    为什么单独一个接口而不塞进总看板：新闻运营（发多少、哪些火、标签生态）
    与"用户 / 识别 / 论坛"看板是不同角色关心的东西；独立接口也方便前端在
    行业动态页里把图表区块按需加载，不必为了几张图把总看板拖慢。

    口径说明（容易踩的地方都写在这里）：
      · `published` / `draft` / `featured` / `scheduled` 都按**全部新闻**计数，
        其中 scheduled 只算"已发布且 published_at 还在未来"的；
      · `views_total` / `views_avg` 同样按**全部新闻**统计 —— 下架新闻的历史阅读量
        也是真实发生过的，不该因为当前发布状态被抹掉；没有新闻时 views_avg=0.0；
      · 趋势 / 分类分布 / Top 阅读 / 标签云 只统计**已发布**（草稿对外不可见，
        算进"发布趋势"会让人误判内容产出）；
      · 趋势按**有效发布时间**（published_at 优先，空则回退 created_at）分桶，
        且按**本地时区**取日期 —— 第 69 批踩过"UTC 日期与本地日期差 8 小时"的坑。
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='days', type=int, location=OpenApiParameter.QUERY, required=False,
                description='统计最近 N 天（含今天），默认 30；合法范围 7..180，'
                            '非法 / 越界回退默认值 30。',
            ),
        ],
        responses={200: NewsStatsResponseSchema},
    )
    def get(self, request):
        if not _can_view_dashboard(request.user):
            return Response({'detail': '没有权限查看新闻数据看板'}, status=403)

        try:
            days = int(request.query_params.get('days', 30))
        except (TypeError, ValueError):
            days = 30
        # 7..180：少于 7 天看不出趋势；多于 180 天图表放不下、查询也变慢
        if not 7 <= days <= 180:
            days = 30

        now = timezone.now()
        today = timezone.localdate()
        start_date = today - timedelta(days=days - 1)
        # 区间是"本地日期 [start_date, today]"，换算成 aware datetime 给 DB 粗筛用
        start_dt = timezone.make_aware(datetime.combine(start_date, time.min))

        all_news = News.objects.all()
        published_news = all_news.filter(is_published=True)

        # ---------- 总量 ----------
        totals = {
            'all': all_news.count(),
            'published': published_news.count(),
            'draft': all_news.filter(is_published=False).count(),
            'featured': all_news.filter(is_featured=True).count(),
            'scheduled': published_news.filter(published_at__gt=now).count(),
            # 阅读量按全部新闻统计（见类说明的取舍）
            'views_total': all_news.aggregate(total=Sum('views'))['total'] or 0,
            'views_avg': round(all_news.aggregate(avg=Avg('views'))['avg'] or 0, 1),
        }

        # ---------- 发布趋势（有效发布时间口径） ----------
        # 先用粗筛把"可能落在区间内"的已发布新闻取出来（published_at 为空时看
        # created_at），再在 Python 里按本地日期分桶：两个时间字段选一个用 OR 表达，
        # 在 SQL 里按"有效时间"trunc 既难读、又容易在 SQLite 上碰时区问题。
        effective_rows = published_news.filter(
            Q(published_at__gte=start_dt)
            | Q(published_at__isnull=True, created_at__gte=start_dt)
        ).values_list('published_at', 'created_at')
        day_counts = {}
        for published_at, created_at in effective_rows:
            effective_at = published_at or created_at
            day = timezone.localtime(effective_at).date()
            # 上界用 <= today 再兜一道：published_at 在未来的定时新闻不该进趋势
            if start_date <= day <= today:
                day_counts[day] = day_counts.get(day, 0) + 1
        publish_trend = []
        for offset in range(days):
            day = start_date + timedelta(days=offset)
            publish_trend.append({
                'date': day.isoformat(),
                'count': day_counts.get(day, 0),
            })

        # ---------- 分类分布（固定 5 类，无数据补 0） ----------
        category_counts = {
            row['category']: row['count']
            for row in published_news.values('category').annotate(count=Count('id'))
        }
        category_distribution = [
            {'category': value, 'count': category_counts.get(value, 0)}
            for value, _label in News.CATEGORY_CHOICES
        ]

        # ---------- 阅读量 Top 10 ----------
        top_viewed = [
            {
                'id': row['id'],
                'title': row['title'],
                'title_en': row['title_en'],
                'views': row['views'],
                'created_at': row['created_at'].isoformat(),
            }
            for row in published_news.order_by('-views', '-created_at').values(
                'id', 'title', 'title_en', 'views', 'created_at',
            )[:10]
        ]

        # ---------- 标签云 Top 20 ----------
        tag_counter = {}
        for raw_tags in published_news.values_list('tags', flat=True).iterator():
            seen = set()
            for name in TAG_SPLIT_RE.split(raw_tags or ''):
                name = name.strip()
                if not name or name in seen:
                    continue
                # 同一篇新闻里重复写同一个标签只算一次（否则会把自己刷上榜首）
                seen.add(name)
                tag_counter[name] = tag_counter.get(name, 0) + 1
        tag_cloud = [
            {'name': name, 'count': count}
            for name, count in sorted(
                tag_counter.items(), key=lambda item: (-item[1], item[0]),
            )[:20]
        ]

        return Response({
            'days': days,
            'totals': totals,
            'publish_trend': publish_trend,
            'category_distribution': category_distribution,
            'top_viewed': top_viewed,
            'tag_cloud': tag_cloud,
            'generated_at': now.isoformat(),
        })
