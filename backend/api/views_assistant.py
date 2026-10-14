"""智能回答助手接口（第 193 批，K5）。

| 接口 | 方法 | 鉴权 | 说明 |
|---|---|---|---|
| `/api/assistant/ask/` | POST | 需登录 | 问一个问题，返回答案 + 来源引用 |

## 三个刻意的约定

1. **需登录**：会话与限流都挂在用户上（匿名用户没有稳定标识，限流会被绕过）。
2. **LLM 不可用仍返回 200 且 `degraded=true`**：让前端能区分"答得保守"（词条原文）
   与"请求失败"。把降级当 500 会让识别结果页跟着出错 —— 而助手只是旁路功能。
3. **参数错误才 400**：问题为空/超长/命中敏感词/超频**都不是 HTTP 错误**，
   它们是有内容的回答（分别给出可操作提示），所以走 200 + `degrade_reason`。

`degrade_reason` 取值见 `assistant/orchestrator.py` 的模块说明。
"""
from __future__ import annotations

import logging

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models_assistant import AssistantSession
from .assistant import orchestrator

logger = logging.getLogger(__name__)

#: 单次请求的问题长度硬上限（比闸门的 500 稍宽松，超了才判 400）——
#: 闸门负责"给可操作提示"，这里负责"别把超长 body 读进内存"。
MAX_BODY_CHARS = 2000


class AssistantAskView(APIView):
    """问一个问题。"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        question = str(request.data.get('question') or '')
        if len(question) > MAX_BODY_CHARS:
            return Response(
                {'detail': f'question 过长（上限 {MAX_BODY_CHARS} 字符）'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pest_identifier = str(request.data.get('pest_identifier') or '')
        session = None
        session_id = request.data.get('session_id')
        if session_id not in (None, ''):
            try:
                session_id = int(session_id)
            except (TypeError, ValueError):
                return Response({'detail': 'session_id 必须是整数'},
                                status=status.HTTP_400_BAD_REQUEST)
            # 只允许续自己的会话：别人的 session_id 一律当"不存在"处理（不泄漏其存在性）
            session = AssistantSession.objects.filter(pk=session_id, user=request.user).first()
            if session is None:
                return Response({'detail': '会话不存在'}, status=status.HTTP_404_NOT_FOUND)

        result = orchestrator.ask(
            user=request.user,
            question=question,
            session=session,
            pest_identifier=pest_identifier,
        )
        return Response(result)
