"""
私信接口（第 42 批建立，第 114 批重做分页与已读反馈）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/messages/` | GET | 我的会话列表（对方、最后一条、未读数） |
| `/api/messages/with/<user_id>/` | GET | 与某人的聊天记录（打开即把收到的标记为已读） |
| `/api/messages/with/<user_id>/` | POST | 给某人发一条私信 |
| `/api/messages/with/<user_id>/` | DELETE | 删除我与他的整个会话（**只删我这一侧**） |
| `/api/messages/unread-count/` | GET | 我的未读私信总数（顶栏红点用） |

规则：
  · 不能给自己发私信；
  · 收件人必须存在且启用；
  · 发送后会走通知体系给收件人一条"XX 给你发了私信"（铃铛里能看到）。

============================================================================
第 114 批修掉的三个结构性缺陷
============================================================================
这三个都不是"缺个功能"，而是**设计上留了洞**（用户反馈"重新完善客户端私信功能"
时逐个查出来的）：

1. **聊天记录永远只能看最近 100 条。**
   原来 `get()` 是 `list(queryset)` 把**整个会话**读进内存、再 `messages[-100:]`。
   后果：更早的消息**没有任何接口能取到** —— 聊久了就等于丢失历史。
   现在改成 `before_id` 游标分页（见 `get()` 的说明）。

2. **发出去的消息没有已读反馈。**
   `read_at` 字段一直在写（打开会话时 `update(is_read=True, read_at=now)`），
   但序列化时**从不返回**，所以前端想显示"已读"也没有数据。
   现在 `_serialize` 带上了 `read_at`。

3. **会话删不掉。**
   `sender_deleted` / `recipient_deleted` 两个字段从第 42 批起就在，
   但**没有任何接口写它们** —— 死字段。现在补 `DELETE`。

另外把会话列表里的"最后一条"一起修了：原来用 `message.content[:60]`，
而 `content` 现在可能是一段"图片消息"的 JSON，直接截会露出原始 JSON。
见 `_preview_of()`。
"""
import json
import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models_message import DirectMessage, conversation_key_for

logger = logging.getLogger(__name__)
User = get_user_model()

#: 一次最多回多少条聊天记录（也用作默认值）
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


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
        # 第 114 批：`read_at` 原来只在库里写、从不返回，所以前端做不了"已读"标记。
        'read_at': message.read_at,
        'created_at': message.created_at,
        'sender': _brief(message.sender if message.sender_id else None, request),
        'recipient': _brief(message.recipient if message.recipient_id else None, request),
    }


def _preview_of(message):
    """
    会话列表里的"最后一条"摘要。

    ⚠️ 第 114 批：不能直接 `content[:60]`。图片消息的正文是一段 JSON
    （`{"type": "image", …}`，见 `views.py` 的图片上传），直接截会把
    `{"type":"image","url":"http…` 这种原始 JSON 显示在会话列表里。
    这里按类型给出可读摘要。
    """
    content = message.content or ''
    if content.lstrip().startswith('{'):
        try:
            payload = json.loads(content)
        except (ValueError, TypeError):
            pass
        else:
            if isinstance(payload, dict) and payload.get('type') == 'image':
                return '[图片]'
    return content[:60]


def _text_of(content: str) -> str:
    """
    从一条私信正文里取出"应该被敏感词检查的文字"。

    图片消息的正文是 JSON，必须剥出说明文字再查 ——
    否则敏感词藏在 JSON 结构里就绕过去了（虽然目前图片消息不带说明文字，
    但这个口子不该留）。JSON 解析失败时按原文查（宁可多查一遍）。
    """
    if not content.lstrip().startswith('{'):
        return content
    try:
        payload = json.loads(content)
    except (ValueError, TypeError):
        return content
    if isinstance(payload, dict) and payload.get('type') == 'image':
        return str(payload.get('caption') or '')
    return content


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
                    'last_message': _preview_of(message),
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
    """与某人的聊天记录（GET）/ 发私信（POST）/ 删除会话（DELETE）"""
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

    def _my_messages(self, me, other):
        """
        我这一侧能看到的消息（把**我删掉的**那部分排除）。

        一个人的删除不该影响另一个人 ——
        `sender_deleted` / `recipient_deleted` 是两侧独立的软删标记。
        """
        key = conversation_key_for(me.id, other.id)
        return (
            DirectMessage.objects
            .filter(conversation_key=key)
            .filter(Q(sender=me, sender_deleted=False) | Q(recipient=me, recipient_deleted=False))
            .select_related('sender', 'recipient')
        )

    def get(self, request, user_id):
        me = request.user
        other, error = self._get_other(user_id, me)
        if error:
            code = status.HTTP_400_BAD_REQUEST if other is None and '自己' in error else status.HTTP_404_NOT_FOUND
            return Response({'detail': error}, status=code)

        queryset = self._my_messages(me, other)

        # ------------------------------------------------------------------
        # 分页：`before_id` 游标（第 114 批）
        # ------------------------------------------------------------------
        # ⚠️ 原来是 `list(queryset)` 把整个会话读进内存再切最后 N 条 ——
        #    后果是**更早的消息永远取不到**（没有任何接口能翻页），聊久了等于丢历史。
        #
        # 现在：默认回**最新的一页**；带 `before_id=<某条消息的 id>` 时，
        # 回**比它更早的一页**（前端往上滚时用）。
        # 用 id 而不是 offset 作游标：聊天时随时会插入新消息，
        # offset 分页会因为插入而错位/重复（经典坑）。
        #
        # 排序：先按 `-created_at` 取一页（数据库层 LIMIT，不把全表读进内存），
        # 再在 Python 里反转成"从旧到新" —— 这是聊天记录该有的顺序。
        # ID 与时间可能不同序（同一秒内多条、或时钟回拨），所以游标用
        # `(created_at, id)` 组合比较，光比 id 会漏或多。
        try:
            page_size = int(request.query_params.get('page_size', DEFAULT_PAGE_SIZE))
        except (TypeError, ValueError):
            page_size = DEFAULT_PAGE_SIZE
        page_size = min(MAX_PAGE_SIZE, max(1, page_size))

        before_id = request.query_params.get('before_id')
        cursor_message = None
        if before_id:
            cursor_message = queryset.filter(pk=before_id).first()
            if cursor_message is None:
                # 游标无效（被删了/不是这个会话的）→ 当成"没有游标"，
                # 回最新一页而不是报错：前端滚动时正好有人删消息也不该炸
                logger.info('私信分页游标无效 user=%s before_id=%s', me.id, before_id)

        page_queryset = queryset
        if cursor_message is not None:
            page_queryset = queryset.filter(
                Q(created_at__lt=cursor_message.created_at)
                | Q(created_at=cursor_message.created_at, id__lt=cursor_message.id)
            )

        # ------------------------------------------------------------------
        # 打开会话即把"发给我的未读"标记为已读。
        # ------------------------------------------------------------------
        # ⚠️ 第 114 批踩的坑：这一步**必须在取数据之前**做。
        #    原来我先取了一页（`list(page_queryset…)`，那一刻 QuerySet 已经被
        #    求值并缓存），再 `update()` 改库 —— 于是返回的 JSON 里
        #    `is_read` 还是旧的 `False`，而库里已经是 `True`。
        #    测试 `test_send_and_read_conversation` 正好钉住了这一点
        #    （断言 `results[0].is_read` 为真），所以它红了 —— 红得对。
        #
        # ⚠️ 而且只在**打开最新一页**时标记：往上翻历史不该把新消息标成已读
        #    （用户还没看到那些消息，标了会让未读红点凭空消失）。
        marked_read = 0
        read_at = None
        if cursor_message is None:
            unread = queryset.filter(recipient=me, is_read=False)
            marked_read = unread.count()
            if marked_read:
                read_at = timezone.now()
                unread.update(is_read=True, read_at=read_at)

        # 多取一条，用来判断"还有没有更早的"（比 count() 便宜）
        fetched = list(page_queryset.order_by('-created_at', '-id')[:page_size + 1])
        has_more = len(fetched) > page_size
        page = list(reversed(fetched[:page_size]))
        oldest_id = page[0].id if page else None

        # 标记已读的那几条，序列化时要用新状态（上面已说明为什么不能只靠库里的值：
        # `page` 里的对象是在 update 之前查出来的，内存里仍是 is_read=False）
        serialized = []
        for item in page:
            payload = _serialize(item, request)
            if read_at is not None and item.recipient_id == me.id and not payload['is_read']:
                payload['is_read'] = True
                payload['read_at'] = read_at
            serialized.append(payload)

        return Response({
            'other': _brief(other, request),
            'count': len(serialized),
            'marked_read': marked_read,
            'has_more': has_more,
            # 下一次往上翻时把它原样回传（`?before_id=`）
            'oldest_id': oldest_id,
            'results': serialized,
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

        # 敏感词过滤（与帖子/评论一套规则）。
        # 图片消息的正文是 JSON，剥出里面的文字再查 —— 否则敏感词藏在
        # JSON 里就绕过去了（虽然目前图片消息不带文字，但别留下这个口子）。
        from .sensitive import check_text
        try:
            check_text(_text_of(content), field_label='私信')
        except Exception as exc:
            detail = getattr(exc, 'detail', None)
            message = detail.get('detail') if isinstance(detail, dict) else '私信包含不允许的词汇'
            return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)

        message = DirectMessage.objects.create(
            sender=me, recipient=other, content=content,
            conversation_key=conversation_key_for(me.id, other.id),
        )

        # 第 114 批：发新消息要把**收件人那一侧**的软删标记清掉。
        # 否则会出现"对方删过会话 → 我又发了一条 → 对方那边仍然看不到"，
        # 从他的视角看就是**这条消息凭空消失**。
        #
        # ⚠️ 只清 `recipient_deleted`，**不能连 `sender_deleted` 一起清** ——
        #    后者是"这条消息的发件人不想要它了"，与收件人无关；
        #    一起清会把发件人自己删过的消息又恢复出来。
        DirectMessage.objects.filter(
            conversation_key=message.conversation_key, recipient=other, recipient_deleted=True,
        ).update(recipient_deleted=False)

        # 通知收件人（铃铛里能看到，点进去就是私信页）
        try:
            from .views_notify import notify
            notify(
                other,
                type='message',
                title=f'{me.username} 给你发了私信',
                title_en=f'{me.username} sent you a private message',
                message=_preview_of(message),
                url=f'/messages?with={me.id}',
                actor=me,
            )
        except Exception:
            logger.exception('发送私信通知失败 message=%s', message.id)

        logger.info('私信: %s → %s', me.id, other.id)
        return Response(_serialize(message, request), status=status.HTTP_201_CREATED)

    def delete(self, request, user_id):
        """
        删除与某人的整个会话（第 114 批）。

        **只删我这一侧**：把该会话里我是发件人的那些标 `sender_deleted`、
        我是收件人的标 `recipient_deleted`。对方那边完全不受影响 ——
        这是 `models_message.py` 里就定好的设计（"一个人删掉不该让另一个人也看不到"），
        只是一直没有接口去写这两个字段。

        为什么是"整个会话"而不是"一条消息"：一对一的聊天界面里，
        逐条删除几乎没有产品价值（对方本来就还有），而整会话删除
        才是用户真正会做的动作（"这段对话我不想留了"）。
        """
        me = request.user
        other, error = self._get_other(user_id, me)
        if error:
            return Response({'detail': error},
                            status=status.HTTP_400_BAD_REQUEST if '自己' in error else status.HTTP_404_NOT_FOUND)

        key = conversation_key_for(me.id, other.id)
        with transaction.atomic():
            as_sender = DirectMessage.objects.filter(
                conversation_key=key, sender=me, sender_deleted=False,
            ).update(sender_deleted=True)
            as_recipient = DirectMessage.objects.filter(
                conversation_key=key, recipient=me, recipient_deleted=False,
            ).update(recipient_deleted=True)

        total = as_sender + as_recipient
        logger.info('私信会话已删除（单侧） user=%s other=%s 共 %s 条', me.id, other.id, total)
        return Response({'deleted': total}, status=status.HTTP_200_OK)


class MessageUnreadCountView(APIView):
    """我的未读私信总数"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = DirectMessage.objects.filter(
            recipient=request.user, is_read=False, recipient_deleted=False,
        ).count()
        return Response({'unread': count})
