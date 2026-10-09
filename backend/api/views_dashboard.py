"""
管理员数据看板（第 39 批）

背景：清单里"管理员数据看板"此前只有零散的数字 ——
`/api/statistics/` 主要服务于"识别记录"页（个人维度 + 管理员切全部用户），
没有把**用户活跃、内容产出、待办事项**汇总到一处的地方。
这里给管理端一个聚合接口，一次请求拿齐看板需要的全部数据：

    GET /api/admin/dashboard/?days=14

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
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.db.models.functions import TruncDay
from django.utils import timezone
from rest_framework import permissions
# 第 124 批：能力判定统一收口（看板 = CONTENT 只读；样本统计 = BROADCAST）
from .capabilities import CAP_BROADCAST, CAP_CONTENT, has_capability, is_full_admin
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DetectionHistory, Feedback, News, PestInfo
from .models_forum import Comment, Post
from .models_report import Report
from .services_content_i18n import pest_en_maps  # 第 77 批：分布图的中英对照

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
