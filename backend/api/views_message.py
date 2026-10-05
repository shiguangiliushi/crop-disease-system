"""
私信接口（第 42 批）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/messages/` | GET | 我的会话列表（对方、最后一条、未读数） |
| `/api/messages/with/<user_id>/` | GET | 与某人的聊天记录（打开即把收到的标记为已读） |
| `/api/messages/with/<user_id>/` | POST | 给某人发一条私信 |
| `/api/messages/unread-count/` | GET | 我的未读私信总数（顶栏红点用） |

规则：
  · 不能给自己发私信；
  · 收件人必须存在且启用；
  · 发送后会走通知体系给收件人一条"XX 给你发了私信"（铃铛里能看到）。
"""
import logging

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models_message import DirectMessage, conversation_key_for

logger = logging.getLogger(__name__)
User = get_user_model()


def _brief(user, request=None):
    if user is None:
        # 账号已注销
        return {'id': None, 'username': '已注销用户', 'avatar': None}
    avatar = None
    if getattr(user, 'avatar', None):
        try:
            avatar = user.avatar.url
            if request is not None:
                avatar = request.build_absolute_uri(avatar)
        except Exception:  # pragma: no cover
            avatar = None
    return {'id': user.id, 'username': user.username, 'avatar': avatar}


def _serialize(message, request=None):
    return {
        'id': message.id,
        'content': message.content,
        'is_read': message.is_read,
        'created_at': message.created_at,
        'sender': _brief(message.sender if message.sender_id else None, request),
        'recipient': _brief(message.recipient if message.recipient_id else None, request),
    }


class ConversationListView(APIView):
    """我的会话列表（按最后一条消息时间倒序）"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        me = request.user
        # 与我相关、且我没有删除的消息
        queryset = (
            DirectMessage.objects
            .filter(Q(sender=me, sender_deleted=False) | Q(recipient=me, recipient_deleted=False))
            .select_related('sender', 'recipient')
            .order_by('-created_at')
        )

        conversations = {}
        for message in queryset:
            other = message.recipient if message.sender_id == me.id else message.sender
            key = message.conversation_key
            entry = conversations.get(key)
            if entry is None:
                conversations[key] = {
                    'other': _brief(other, request),
                    'last_message': message.content[:60],
                    'last_time': message.created_at,
                    'unread': 0,
                }
                entry = conversations[key]
            # 未读：发给我的、还没读的
            if message.recipient_id == me.id and not message.is_read:
                entry['unread'] += 1

        ordered = sorted(conversations.values(), key=lambda item: item['last_time'], reverse=True)
        return Response({'count': len(ordered), 'results': ordered})


class ConversationDetailView(APIView):
    """与某人的聊天记录（GET）/ 发私信（POST）"""
    permission_classes = [permissions.IsAuthenticated]

    def _get_other(self, user_id, me):
        if int(user_id) == me.id:
            return None, '不能给自己发私信'
        other = User.objects.filter(pk=user_id).first()
        if not other:
            return None, '用户不存在'
        if not other.is_active:
            return None, '该账号已被禁用'
        return other, None

    def get(self, request, user_id):
        me = request.user
        other, error = self._get_other(user_id, me)
        if error:
            code = status.HTTP_400_BAD_REQUEST if other is None and '自己' in error else status.HTTP_404_NOT_FOUND
            return Response({'detail': error}, status=code)

        key = conversation_key_for(me.id, other.id)
        queryset = (
            DirectMessage.objects
            .filter(conversation_key=key)
            # 各自删除的不再展示
            .filter(Q(sender=me, sender_deleted=False) | Q(recipient=me, recipient_deleted=False))
            .select_related('sender', 'recipient')
            .order_by('created_at')
        )

        # 打开会话即把"发给我的未读"标记为已读
        now = timezone.now()
        unread = queryset.filter(recipient=me, is_read=False)
        unread_count = unread.count()
        if unread_count:
            unread.update(is_read=True, read_at=now)
            queryset = queryset  # 对象已更新，重新序列化即可

        messages = list(queryset)
        try:
            page_size = min(200, max(1, int(request.query_params.get('page_size', 100))))
        except (TypeError, ValueError):
            page_size = 100
        messages = messages[-page_size:]

        return Response({
            'other': _brief(other, request),
            'count': len(messages),
            'marked_read': unread_count,
            'results': [_serialize(item, request) for item in messages],
        })

    def post(self, request, user_id):
        me = request.user
        other, error = self._get_other(user_id, me)
        if error:
            return Response({'detail': error},
                            status=status.HTTP_400_BAD_REQUEST if '自己' in error else status.HTTP_404_NOT_FOUND)

        content = (request.data.get('content') or '').strip()
        if not content:
            return Response({'detail': '私信内容不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        if len(content) > 1000:
            return Response({'detail': '私信内容不能超过 1000 字'}, status=status.HTTP_400_BAD_REQUEST)

        # 敏感词过滤（与帖子/评论一套规则）
        from .sensitive import check_text
        try:
            check_text(content, field_label='私信')
        except Exception as exc:
            detail = getattr(exc, 'detail', None)
            message = detail.get('detail') if isinstance(detail, dict) else '私信包含不允许的词汇'
            return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)

        message = DirectMessage.objects.create(
            sender=me, recipient=other, content=content,
            conversation_key=conversation_key_for(me.id, other.id),
        )

        # 通知收件人（铃铛里能看到，点进去就是私信页）
        try:
            from .views_notify import notify
            notify(
                other,
                type='message',
                title=f'{me.username} 给你发了私信',
                title_en=f'{me.username} sent you a private message',
                message=content[:60],
                url=f'/messages?with={me.id}',
                actor=me,
            )
        except Exception:
            logger.exception('发送私信通知失败 message=%s', message.id)

        logger.info('私信: %s → %s', me.id, other.id)
        return Response(_serialize(message, request), status=status.HTTP_201_CREATED)


class MessageUnreadCountView(APIView):
    """我的未读私信总数"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = DirectMessage.objects.filter(
            recipient=request.user, is_read=False, recipient_deleted=False,
        ).count()
        return Response({'unread': count})
