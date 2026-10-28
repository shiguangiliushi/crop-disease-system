"""助手会话的读取接口（第 198 批）。

## 为什么现在才需要

第 193–197 批只有"提问"一个入口：抽屉从识别结果页打开，问完就关，
**不需要列历史**。做独立问答页就必须能"看到以前问过什么、点回去接着问" ——
否则用户换个页面就找不回上一轮的答案。

## 与前端的边界

列表接口只返回**会话级摘要**（标题、条数、最后一条的预览、时间），
不返回完整消息 —— 会话多了以后整体返回会很大。完整消息由详情接口按需取。
"""
from __future__ import annotations

import logging

from django.db.models import Count, Max
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models_assistant import AssistantMessage, AssistantSession

logger = logging.getLogger(__name__)

#: 列表页每页条数上限（前端可以传更小，但不允许一次拉全库）
MAX_PAGE_SIZE = 50
DEFAULT_PAGE_SIZE = 20
#: 列表里"最后一条回答"的预览长度
PREVIEW_CHARS = 80


def _brief(session, last_message: AssistantMessage | None) -> dict:
    preview = ''
    degraded = False
    if last_message is not None:
        preview = (last_message.content or '').strip().replace('\n', ' ')[:PREVIEW_CHARS]
        degraded = bool(last_message.degraded)
    return {
        'id': session.pk,
        'title': session.title,
        'pest_id': session.pest_id,
        'pest_name': session.pest.name if session.pest_id else '',
        'message_count': getattr(session, 'message_count', 0),
        # ⚠️ `degraded` 在**消息**上，不在会话上（会话表没有这个字段）。
        # 列表里给的是"**最后一次回答**是否降级" —— 用户扫一眼历史时想知道的是
        # "这次问答有没有真的答上来"，而不是"整个会话历史上有没有降级过"。
        'degraded': degraded,
        'escalated': bool(session.consult_question_id),
        'consult_question_id': session.consult_question_id,
        'created_at': session.created_at,
        'updated_at': session.updated_at,
        'preview': preview,
    }


class AssistantSessionListView(APIView):
    """`GET /api/assistant/sessions/` —— 我的问答历史（倒序，分页）。"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(request.query_params.get('page_size', DEFAULT_PAGE_SIZE))
        except (TypeError, ValueError):
            page_size = DEFAULT_PAGE_SIZE
        page_size = max(1, min(MAX_PAGE_SIZE, page_size))

        # ⚠️ 只查自己的会话。别人的一律不出现在列表里 —— 这与详情接口的 404 是同一套口径。
        queryset = (
            AssistantSession.objects.filter(user=request.user)
            .select_related('pest')
            .annotate(
                message_count=Count('messages', distinct=True),
                last_at=Max('messages__created_at'),
            )
            .order_by('-updated_at')
        )

        total = queryset.count()
        start = (page - 1) * page_size
        sessions = list(queryset[start:start + page_size])

        # 每条取"最后一条含正文的助手消息"作预览。用一次查询批量取回再在内存里归组，
        # 避免每条会话一次查询（N+1）—— 20 条会话就是 20 次往返。
        # **过滤 content 非空**：流式回答会先建一条空行再回填，
        # 直接取 id 最大的那条可能拿到空内容（预览就成了空白）。
        ids = [s.pk for s in sessions]
        last_by_session: dict[int, AssistantMessage] = {}
        if ids:
            for message in (
                AssistantMessage.objects
                .filter(session_id__in=ids, role='assistant')
                .exclude(content='')
                .order_by('session_id', '-id')
            ):
                last_by_session.setdefault(message.session_id, message)

        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'has_more': start + len(sessions) < total,
            'results': [_brief(s, last_by_session.get(s.pk)) for s in sessions],
        })


class AssistantSessionDetailView(APIView):
    """`GET /api/assistant/sessions/<id>/` 取完整问答；`DELETE` 删除一次会话。"""

    permission_classes = [permissions.IsAuthenticated]

    def _get(self, request, pk):
        # 只允许访问自己的会话；别人的一律 404（不泄漏存在性）
        return AssistantSession.objects.filter(pk=pk, user=request.user).select_related('pest').first()

    def get(self, request, pk):
        session = self._get(request, pk)
        if session is None:
            return Response({'detail': '会话不存在'}, status=status.HTTP_404_NOT_FOUND)

        messages = AssistantMessage.objects.filter(session=session).order_by('id')
        # 流式回答在生成前会先建一条空行；历史里不该出现空气泡
        visible = [m for m in messages if (m.content or '').strip()]
        last_answer = next((m for m in reversed(visible) if m.role == 'assistant'), None)
        return Response({
            'id': session.pk,
            'title': session.title,
            'pest_id': session.pest_id,
            'pest_name': session.pest.name if session.pest_id else '',
            # 同上：会话级的"降级"取自最后一条回答
            'degraded': bool(last_answer.degraded) if last_answer else False,
            'degrade_reason': last_answer.degrade_reason if last_answer else '',
            'escalated': bool(session.consult_question_id),
            'consult_question_id': session.consult_question_id,
            'created_at': session.created_at,
            'messages': [
                {
                    'id': m.pk,
                    'role': m.role,
                    'content': m.content,
                    # 第 229 批：这条提问带了一张图时，"看图看到了什么"的一行摘要。
                    # 图片本身不落盘（助手不是相册），但没有这一行，历史里只会剩下
                    # 一句"这张图怎么了"—— 用户根本想不起当时问的是哪张。
                    'image_summary': m.image_summary or '',
                    'degraded': bool(m.degraded),
                    'degrade_reason': m.degrade_reason,
                    # 第 204 批：当初是否被长度上限截断 —— 历史里的回答也要一直提示，
                    # 不能只在刚生成那一瞬间提示（用户回头看时更需要知道它是半句话）
                    'truncated': bool(m.truncated),
                    'citations': m.citations or [],
                    'verdict': m.verdict,
                    'feedback_note': m.feedback_note,
                    'created_at': m.created_at,
                }
                for m in visible
            ],
        })

    def delete(self, request, pk):
        session = self._get(request, pk)
        if session is None:
            return Response({'detail': '会话不存在'}, status=status.HTTP_404_NOT_FOUND)
        # 消息随会话级联删除（`AssistantMessage.session` 是 CASCADE）
        session.delete()
        logger.info('删除助手会话 id=%s by=%s', pk, request.user.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)
