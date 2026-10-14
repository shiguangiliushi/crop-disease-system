"""智能回答助手接口（第 193 批，K5；第 195 批加流式）。

| 接口 | 方法 | 鉴权 | 说明 |
|---|---|---|---|
| `/api/assistant/ask/` | POST | 需登录 | 问一个问题，一次返回完整答案 + 来源引用 |
| `/api/assistant/ask/stream/` | POST | 需登录 | 同上，但用 SSE **逐字**返回 |

## 五个刻意的约定

1. **需登录**：会话与限流都挂在用户上（匿名用户没有稳定标识，限流会被绕过）。
2. **LLM 不可用仍返回 200 且 `degraded=true`**：让前端能区分"答得保守"（词条原文）
   与"请求失败"。把降级当 500 会让识别结果页跟着出错 —— 而助手只是旁路功能。
3. **参数错误才 400**：问题为空/超长/命中敏感词/超频**都不是 HTTP 错误**，
   它们是有内容的回答（分别给出可操作提示），所以走 200 + `degrade_reason`。
4. **流式响应必须显式声明 `Content-Encoding: identity`**（第 195 批）：
   项目 MIDDLEWARE 里有 `GZipMiddleware`，它会把流式响应包进 `compress_sequence()`
   —— 实测 5 块被压成 2 块（"逐字"效果丢失）。该中间件见到已有的 Content-Encoding
   会直接放行，所以这一行是让流式真的流起来的关键，不是可选项。
5. **`X-Accel-Buffering: no`**：生产走 Nginx 时，反代会默认缓冲上游响应，
   同样会吞掉逐字效果（`proxy_buffering` 的响应头级开关）。

`degrade_reason` 取值见 `assistant/orchestrator.py` 的模块说明。
"""
from __future__ import annotations

import logging

from django.http import StreamingHttpResponse
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models_assistant import AssistantSession
from .assistant import orchestrator

logger = logging.getLogger(__name__)

#: 单次请求的问题长度硬上限（比闸门的 500 稍宽松，超了才判 400）——
#: 闸门负责"给可操作提示"，这里负责"别把超长 body 读进内存"。
MAX_BODY_CHARS = 2000


def _parse_request(request):
    """解析并校验公共入参。返回 `(payload, error_response)`；error_response 非空时直接返回它。"""
    question = str(request.data.get('question') or '')
    if len(question) > MAX_BODY_CHARS:
        return None, Response(
            {'detail': f'question 过长（上限 {MAX_BODY_CHARS} 字符）'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    session = None
    session_id = request.data.get('session_id')
    if session_id not in (None, ''):
        try:
            session_id = int(session_id)
        except (TypeError, ValueError):
            return None, Response({'detail': 'session_id 必须是整数'},
                                  status=status.HTTP_400_BAD_REQUEST)
        # 只允许续自己的会话：别人的 session_id 一律当"不存在"处理（不泄漏其存在性）
        session = AssistantSession.objects.filter(pk=session_id, user=request.user).first()
        if session is None:
            return None, Response({'detail': '会话不存在'},
                                  status=status.HTTP_404_NOT_FOUND)

    return {
        'question': question,
        'session': session,
        'pest_identifier': str(request.data.get('pest_identifier') or ''),
    }, None


class AssistantAskView(APIView):
    """问一个问题（一次返回完整答案）。"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        payload, error = _parse_request(request)
        if error is not None:
            return error

        result = orchestrator.ask(
            user=request.user,
            question=payload['question'],
            session=payload['session'],
            pest_identifier=payload['pest_identifier'],
        )
        return Response(result)


class AssistantAskStreamView(APIView):
    """问一个问题（SSE 逐字返回）。

    事件序列：`meta` → `delta`（多条）→ `citations` → `done`，
    详见 `orchestrator.ask_stream()` 的 docstring。
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        payload, error = _parse_request(request)
        if error is not None:
            return error

        stream = orchestrator.ask_stream(
            user=request.user,
            question=payload['question'],
            session=payload['session'],
            pest_identifier=payload['pest_identifier'],
        )
        response = StreamingHttpResponse(stream, content_type='text/event-stream; charset=utf-8')
        # ① 别让 GZipMiddleware 把流攒住（见模块 docstring 第 4 条）
        response['Content-Encoding'] = 'identity'
        # ② 别让反向代理缓冲（生产 Nginx）
        response['X-Accel-Buffering'] = 'no'
        response['Cache-Control'] = 'no-cache, no-store'
        # ⚠️ 这里**不要**设 `Connection`：它是**逐跳头（hop-by-hop）**，
        #    WSGI 规范禁止应用设置 —— 实测报
        #    `AssertionError: Hop-by-hop header, 'Connection: keep-alive', not allowed`
        #    并变成 500。连接复用/关闭由服务器与客户端协商，不该由视图决定。
        return response
