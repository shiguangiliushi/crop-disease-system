"""
通知与公告接口（第 37 批）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/notifications/` | GET | 我的通知（分页；`?unread=1` 只看未读） |
| `/api/notifications/unread-count/` | GET | 未读数（铃铛红点用） |
| `/api/notifications/<id>/read/` | POST | 标记单条已读（只能操作自己的） |
| `/api/notifications/read-all/` | POST | 全部标记已读 |
| `/api/notifications/<id>/` | DELETE | 删除自己的某条通知 |
| `/api/announcements/` | GET | 当前生效的公告列表（所有人可见） |
| `/api/announcements/` | POST | 发布公告（仅管理员）→ 同时给全体用户投递通知 |
| `/api/announcements/<id>/` | PATCH/DELETE | 修改 / 删除（仅管理员） |

以及一个给业务代码用的投递函数 `notify()`（被回复/点赞/收藏时调用）。
"""
import logging

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, viewsets
# 第 124 批：能力判定统一收口（公告 = BROADCAST，信息编辑员不可）
from .capabilities import CAP_BROADCAST, IsBroadcastManager, has_capability
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models_notify import Announcement, Notification
from .serializers_notify import AnnouncementSerializer, NotificationSerializer

logger = logging.getLogger(__name__)
from .audit import log_admin_action  # noqa: E402  第 150 批：管理操作日志
User = get_user_model()

#: 生效中的公告：已启用 且（没有过期时间 或 还没到期）
VISIBLE_ANNOUNCEMENT_Q = Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())


def notify(recipient, *, type, title, message='', url='', actor=None, post=None, comment=None,
           announcement=None, title_en='', message_en='', allow_self=False):
    """
    投递一条站内通知（业务代码调用；失败只记日志，绝不影响主流程）

    规则：**互动类不给自己发通知**（自己回复自己、给自己点赞都没有意义），
    默认 `allow_self=False` 就是这条规则。

    第 78 批新增 `allow_self`：**广播类**（系统公告、病害预警推送）要传 `True`。
    背景（真实反馈）："通知中心为什么之前发过信息，然后又看不到信息发过来的" ——
    管理员推送预警后，`123456`/`12345678`/`dsh_tester` 都收到了（库里 8 条实证），
    唯独推送人自己的通知中心**永远是空的**：不光看不到自己发过什么，
    连"这次到底推成功没有、推给了谁"都无从核对。
    广播是**运营动作**，不是"自己跟自己互动"，所以发送者应当留一份自己的副本。

    第 72 批：新增 `title_en` / `message_en` —— 通知标题是后端按模板拼的
    （"xxx 回复了你的帖子：yyy"），前端文案表管不到；不给英文版本的话，
    英文界面下通知中心与铃铛下拉整块是中文。
    """
    if recipient is None:
        return None
    if not allow_self and actor is not None and getattr(actor, 'id', None) == getattr(recipient, 'id', None):
        return None

    try:
        return Notification.objects.create(
            recipient=recipient, actor=actor, type=type, title=title,
            message=(message or '')[:500], url=url or '',
            title_en=(title_en or '')[:200], message_en=(message_en or '')[:500],
            post=post, comment=comment, announcement=announcement,
        )
    except Exception:
        logger.exception('投递通知失败 recipient=%s type=%s', getattr(recipient, 'id', None), type)
        return None


class NotificationViewSet(viewsets.GenericViewSet,
                          viewsets.mixins.ListModelMixin,
                          viewsets.mixins.DestroyModelMixin):
    """我的通知（只能看到/操作自己的）"""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Notification.objects.filter(recipient=self.request.user).select_related('actor')
        unread = (self.request.query_params.get('unread') or '').strip().lower()
        if unread in ('1', 'true', 'yes'):
            queryset = queryset.filter(is_read=False)
        return queryset

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'unread': count})

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        return Response({'id': notification.id, 'is_read': True})

    @action(detail=False, methods=['post'], url_path='read-all')
    def read_all(self, request):
        updated = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'updated': updated})


class AnnouncementViewSet(viewsets.ModelViewSet):
    """
    系统公告

    · 读取：所有人（只返回生效中的公告；有 BROADCAST 能力的账号可带 `?all=1` 看全部含过期/停用）
    · 写入：仅具备 BROADCAST 能力的账号

    第 124 批：判定统一收口到 `capabilities.py`（这里原来用 DRF 自带的 `IsAdminUser`，
    它**只认 is_staff** —— 于是 `role=ADMIN` 但 `is_staff=False` 的账号在列表里
    是"管理员"、却发不了公告）。**信息编辑员（EDITOR）不可**：公告是对全体发声。
    """
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsBroadcastManager()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        queryset = Announcement.objects.select_related('created_by')
        user = self.request.user
        want_all = (self.request.query_params.get('all') or '').strip().lower() in ('1', 'true', 'yes')
        if want_all and has_capability(user, CAP_BROADCAST):
            return queryset
        return queryset.filter(is_active=True).filter(VISIBLE_ANNOUNCEMENT_Q)

    def perform_create(self, serializer):
        announcement = serializer.save(created_by=self.request.user)
        # 发布即给全体用户投递一条通知（当前用户规模很小，直接扇出；量大时应改为合并读取）
        # 第 78 批：**包含发布人自己** —— 否则管理员发完公告，自己的通知中心里
        # 什么都看不到，无法确认"发出去了没有"。广播不是自娱自乐，见 notify() 的说明。
        recipients = User.objects.filter(is_active=True)
        created = 0
        for user in recipients.iterator():
            if notify(
                user,
                type='announcement',
                title=announcement.title,
                message=announcement.content[:120],
                url='/notifications',
                actor=self.request.user,
                announcement=announcement,
                allow_self=True,
            ):
                created += 1
        logger.info('公告已发布 id=%s，投递通知 %s 条', announcement.id, created)
        # 第 150 批：公告是**面向全体用户**的广播，必须留痕（谁发的、发了几条通知）
        log_admin_action(
            self.request.user, 'announcement.create', target=announcement,
            detail=f'发布公告，投递站内通知 {created} 条',
            request=self.request,
        )

    def perform_destroy(self, instance):
        """
        删除公告时，**连带清掉这次扇出的通知**

        设计说明：一般的通知（被回复/点赞/收藏）用 SET_NULL —— 帖子被删了通知还留着，
        用户至少知道"发生过这件事"。但公告不一样：公告删了之后，
        通知里点进去什么也没有，留着只会让人困惑，所以这里一并删除。
        """
        # 第 150 批：删除公告会**连带清掉**这次扇出的通知（见下方说明），
        # 属于不可逆动作，先记日志再删。
        log_admin_action(
            self.request.user, 'announcement.delete', target=instance,
            detail=f'删除公告（连带清理 {Notification.objects.filter(announcement=instance).count()} 条通知）',
            request=self.request,
        )
        removed = Notification.objects.filter(announcement=instance).delete()[0]
        logger.info('删除公告 id=%s，连带清理通知 %s 条', instance.id, removed)
        instance.delete()


class AnnouncementLatestView(APIView):
    """
    首页横幅用的"最靠前的一条生效公告"（没有则返回 null）

    GET /api/announcements/latest/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        announcement = (
            Announcement.objects
            .filter(is_active=True)
            .filter(VISIBLE_ANNOUNCEMENT_Q)
            .order_by('-is_pinned', '-created_at')
            .first()
        )
        if not announcement:
            return Response({'announcement': None})
        return Response({'announcement': AnnouncementSerializer(announcement).data})
