"""
行业动态订阅（第 402 批 P2-11）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/news-subscriptions/` | GET | 我的订阅（分页；只能看到自己的） |
| `/api/news-subscriptions/` | POST | 新建订阅 `{target_type, category?, pest?}` |
| `/api/news-subscriptions/<id>/` | DELETE | 删除自己的订阅（别人的 → 404） |
| `/api/news-subscriptions/check/` | GET | 我是否已订阅某分类 / 某病害 |

以及一个给业务代码用的扇出函数 `notify_news_subscribers()`：
新闻发布（新建即发布、草稿→发布、定时到点后由管理命令补发）时，
给订阅了该分类或该新闻关联病害的用户各投递一条 `type='news'` 站内通知。

设计取舍：
  · 订阅目标只有"分类 / 病害"两种，且各自只用一个字段（category 或 pest），
    另一字段置空 —— 避免同一行出现"既像分类又像病害"的脏数据；
  · 唯一性在序列化器层显式查重（NULL 在数据库里互不相等，DB 唯一约束不可靠）；
  · 扇出失败只记日志，绝不影响新闻保存主流程（通知是锦上添花，不是主链路）。
"""
import html
import logging
import re

from django.contrib.auth import get_user_model
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from .models import NewsSubscription
from .serializers import NewsSubscriptionSerializer

logger = logging.getLogger(__name__)
User = get_user_model()

#: 通知标题里新闻标题的截断长度（通知 title 上限 200，给"行业动态："前缀留余量）
NEWS_TITLE_LIMIT = 60
#: 通知摘要里正文清洗后的截断长度（通知 message 上限 500，100 字足够"点开前看一眼"）
NEWS_MESSAGE_LIMIT = 100


def _plain_text(value, limit):
    """
    把富文本正文压成一行纯文本（通知摘要用）。

    为什么在通知侧清洗而不是存库时清洗：新闻正文是富文本（编辑器 HTML），
    存库保持原文，列表 / 通知各自按需清洗；直接截 HTML 会得到半截标签。
    """
    text = re.sub(r'<[^>]+>', ' ', value or '')
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit]


def _news_notification_message(news):
    """通知摘要：优先用手工摘要，为空才回退正文清洗后的前 100 字"""
    summary = (getattr(news, 'summary', '') or '').strip()
    if summary:
        return summary
    return _plain_text(getattr(news, 'content', ''), NEWS_MESSAGE_LIMIT)


def news_subscriber_ids(news):
    """
    取"应该收到这条新闻通知"的用户 id 集合。

    独立成函数的原因：扇出与「管理命令 dry-run 预览」要共用同一口径；
    用 set 去重 —— 同一用户同时订阅了该分类与关联病害时只算一次（每人只发一条）。
    """
    recipient_ids = set(
        NewsSubscription.objects.filter(
            user__is_active=True, target_type='category', category=news.category,
        ).values_list('user_id', flat=True)
    )
    pest_ids = list(news.related_pests.values_list('id', flat=True))
    if pest_ids:
        recipient_ids.update(
            NewsSubscription.objects.filter(
                user__is_active=True, target_type='pest', pest_id__in=pest_ids,
            ).values_list('user_id', flat=True)
        )
    return recipient_ids


def notify_news_subscribers(news, actor=None):
    """
    行业动态发布扇出：给订阅了该新闻分类 / 关联病害的活跃用户各发一条通知。

    触发点见 `news_views.create` / `news_views.update`（草稿→发布）；
    定时发布到点时没有保存动作，由 `manage.py notify_pending_news` 补发。

    为什么整体 try/except：通知是"锦上添花"的旁路，一旦扇出出错（缓存/DB 抖动、
    某个接收人数据异常）绝不能把"新闻保存成功"变成 500 —— 那才是主流程。

    返回成功投递的通知条数（管理命令用它统计）。
    """
    try:
        recipient_ids = news_subscriber_ids(news)
        if not recipient_ids:
            return 0

        title = f'行业动态：{(news.title or "")[:NEWS_TITLE_LIMIT]}'
        title_en = (
            f'Industry news: {((news.title_en or news.title) or "")[:NEWS_TITLE_LIMIT]}'
        )
        message = _news_notification_message(news)
        url = f'/news/{news.pk}'

        # 延迟导入：避免 urls → news_views → 本模块 的导入链在启动期与
        # views_notify 的依赖互相等待。
        from .views_notify import notify

        sent = 0
        for user in User.objects.filter(pk__in=recipient_ids, is_active=True).only('id'):
            notification = notify(
                user, type='news', title=title, title_en=title_en,
                message=message, url=url, actor=actor, allow_self=True, news=news,
            )
            if notification is None:
                continue
            sent += 1
        return sent
    except Exception:
        logger.exception('行业动态订阅通知扇出失败 news=%s', getattr(news, 'pk', None))
        return 0


class NewsSubscriptionViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    我的行业动态订阅。

    - 权限：仅登录用户；queryset 强制 `filter(user=request.user)`，
      所以"看/删别人的订阅"在数据库层就查不到（404，不泄露是否存在）；
    - 分页：不显式设置分页类 → 走全局 `CustomPagination`，
      响应是标准 `{count, next, previous, current_page, total_pages, results}`。
    """

    serializer_class = NewsSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    #: ⚠️ 真正生效的查询在下面的 `get_queryset()`（强制 filter(user=request.user)）。
    #: 这个类属性只给 drf-spectacular 推导详情路由的 pk 类型用 —— 不写的话
    #: openapi 会把 `/api/news-subscriptions/{id}/` 的 id 当字符串并报 warning。
    queryset = NewsSubscription.objects.all()

    def get_queryset(self):
        return NewsSubscription.objects.filter(
            user=self.request.user,
        ).select_related('pest')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=['get'])
    def check(self, request):
        """
        查询"我是否已订阅某个分类 / 某病害"（前端订阅按钮的状态用）。

        参数缺失 / 非法时按"未订阅"返回 200，而不是 400：这个接口只服务于
        按钮状态，不该让订阅页因为一个拼错的查询参数整块报错。
        """
        target_type = (request.query_params.get('target_type') or 'category').strip()
        subscription = None

        if target_type == 'category':
            category = (request.query_params.get('category') or '').strip()
            if category:
                subscription = self.get_queryset().filter(
                    target_type='category', category=category,
                ).first()
        elif target_type == 'pest':
            try:
                pest_id = int(request.query_params.get('pest'))
            except (TypeError, ValueError):
                pest_id = None
            if pest_id:
                subscription = self.get_queryset().filter(
                    target_type='pest', pest_id=pest_id,
                ).first()

        return Response({
            'subscribed': subscription is not None,
            'id': subscription.id if subscription else None,
        })
