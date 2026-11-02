"""智能回答助手接口（第 193 批，K5；第 195 批加流式）。

| 接口 | 方法 | 鉴权 | 说明 |
|---|---|---|---|
| `/api/assistant/ask/` | POST | 需登录 | 问一个问题，一次返回完整答案 + 来源引用；可附 `image`（图片问答，第 229 批） |
| `/api/assistant/ask/stream/` | POST | 需登录 | 同上，但用 SSE **逐字**返回（同样支持 `image`） |
| `/api/assistant/messages/<id>/feedback/` | POST | 需登录 | 给某条助手回答打分（有用 / 没用 + 可选说明） |
| `/api/assistant/sessions/<id>/escalate/` | POST | 需登录 | 把这次会话**转人工**（写进既有的专家咨询） |

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
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models_assistant import AssistantMessage, AssistantSession
from .assistant import orchestrator, prompts, vision
from .assistant.service import escalate
from .image_validation import ImageValidationError, validate_image_upload

logger = logging.getLogger(__name__)

#: 单次请求的问题长度硬上限（比闸门的 500 稍宽松，超了才判 400）——
#: 闸门负责"给可操作提示"，这里负责"别把超长 body 读进内存"。
MAX_BODY_CHARS = 2000


def _request_lang(request) -> str:
    """从请求判定回答语言（第 197 批）。

    用 `Accept-Language` 而不是请求体字段：它是 HTTP 标准做法，
    而且项目已经挂了 `django.middleware.locale.LocaleMiddleware`，
    `request.LANGUAGE_CODE` 就是协商结果 —— 不必自己解析头。

    取不到就回落中文（本项目主语言）。判定逻辑收口在 `prompts.normalize_lang`，
    视图这层只负责"从头里拿一个字符串"。
    """
    code = getattr(request, 'LANGUAGE_CODE', '') or request.META.get('HTTP_ACCEPT_LANGUAGE', '')
    return prompts.normalize_lang(code)


def _parse_request(request):
    """解析并校验公共入参。返回 `(payload, error_response)`；error_response 非空时直接返回它。"""
    question = str(request.data.get('question') or '')
    if len(question) > MAX_BODY_CHARS:
        return None, Response(
            {'detail': f'question 过长（上限 {MAX_BODY_CHARS} 字符）'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 第 229 批：**看图问答**。图片走 multipart 字段 `image`（JSON 请求里没有它，行为不变）。
    #
    # 校验复用 `image_validation`（识别页/头像/新闻图共用同一套：大小、格式、真实后缀），
    # 所以这里**不要**再写一份"5MB + jpg/png"的判断 —— 两处口径必然会漂。
    image = request.FILES.get('image') if request.FILES else None
    if image is not None:
        try:
            validate_image_upload(image, prefix='assistant_')
        except ImageValidationError as exc:
            return None, Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # 只传图、不打字：给一个默认问题。否则闸门按"空问题"拒掉，用户会觉得"这张图白传了"。
    if image is not None and not question.strip():
        question = vision.default_question(_request_lang(request))

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
        'lang': _request_lang(request),
        'image': image,
    }, None


#: 追问建议模板（第 305 批）。后端统一出，前端只渲染 —— 两套规则必然长歪。
_FOLLOWUP_TEMPLATES = {
    'symptom': {'zh': '{name}有哪些典型症状？', 'en': 'What are the typical symptoms of {name}?'},
    'chemical': {'zh': '{name}该用什么药？', 'en': 'Which pesticide should I use for {name}?'},
    'prevention': {'zh': '{name}怎么预防？', 'en': 'How do I prevent {name}?'},
    'cause': {'zh': '为什么会得{name}？', 'en': 'What causes {name}?'},
}


def _guess_intent(question: str) -> str:
    """从问题里粗判意图（只用于"跳过当前意图"，判错也只影响推荐顺序）。"""
    text = question or ''
    if any(word in text for word in ('药', '农药', '喷', 'pesticide', 'spray')):
        return 'chemical'
    if any(word in text for word in ('症状', '什么样', '表现', 'symptom')):
        return 'symptom'
    if any(word in text for word in ('预防', '防', 'prevent')):
        return 'prevention'
    if any(word in text for word in ('为什么', '原因', 'cause', 'why')):
        return 'cause'
    return 'general'


def _suggest_followups(result: dict, question: str, lang: str = 'zh') -> list[dict]:
    """从 citations 里取第一条词条名，给出 3 条"还能问什么"。

    没有 citation（降级/未命中）时返回空列表 —— 没词条时推荐问题等于乱猜。
    """
    citations = result.get('citations') or []
    if not citations:
        return []
    first = citations[0] or {}
    # ⚠️ 引用条目的键是 `label`（第 305 批实测：pest_id / prevention_id / label / snippet），
    # 不是 pest_name —— 照前端那种猜法会永远取不到名字，建议列表恒为空。
    name = first.get('label') or first.get('pest_name') or first.get('name') or ''
    if not name:
        return []
    current = _guess_intent(question)
    english = str(lang).startswith('en')
    out = []
    for intent, templates in _FOLLOWUP_TEMPLATES.items():
        if intent == current:
            continue
        out.append({'intent': intent, 'question': templates['en' if english else 'zh'].format(name=name)})
        if len(out) == 3:
            break
    return out


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
            lang=payload['lang'],
            image=payload['image'],
        )
        # 第 305 批：基于 citations 里的词条 + 当前意图，给出 3 条追问建议
        try:
            import re as _re

            _lang = 'en' if 'en' in str(request.META.get('HTTP_ACCEPT_LANGUAGE', '')).lower() else 'zh'
            result['suggestions'] = _suggest_followups(
                result, payload.get('question', ''), _lang)
        except Exception:  # noqa: BLE001 —— 推荐失败不能影响回答
            # 第 306 批：原来这里静默吞掉，导致"suggestions 恒为空"查不出原因。
            logger.exception('生成追问建议失败')
            result['suggestions'] = []

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
            lang=payload['lang'],
            image=payload['image'],
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


class AssistantSuggestView(APIView):
    """追问建议（第 312 批）—— **独立接口**，不经过 LLM、不依赖 SSE。

    ## 为什么另开接口

    前面 6 轮都在"把 suggestions 塞进流式 done 事件"上打转（守卫误命中、分支不命中、
    包装器没执行……）。这条链路只要有一环没对上，前端就永远拿不到数据。

    换个思路：**回答结束后单独要一次建议**。它只查库、不算模型，开销可以忽略，
    而且行为确定 —— 前端拿到回答后立刻调，不依赖流式事件的内部结构。

    请求：`POST /api/assistant/suggestions/`  `{question, pest_identifier, lang?}`
    返回：`{suggestions: [{intent, question}, …]}`
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .pest_lookup import find_pest_info

        question = str(request.data.get('question') or '')
        identifier = str(request.data.get('pest_identifier') or '')
        lang = 'en' if 'en' in str(request.data.get('lang') or '').lower() else 'zh'

        pest, _why = find_pest_info(identifier) if identifier else (None, '')
        if pest is None:
            # 第 312 批：前端问答页手里只有病害**名字**（currentPestName），没有模型类名，
            # 所以这里允许按名字回查 —— 比逼前端再传一个它没有的字段更实际。
            from .models import PestInfo

            name_hint = str(request.data.get('pest_name') or '').strip()
            if name_hint:
                pest = (PestInfo.objects.filter(name=name_hint).first()
                        or PestInfo.objects.filter(name_en=name_hint).first())
        if pest is None:
            # 第 312 批：前端手里可能既没有 identifier 也没有上下文名字
            # （新开一个问题时 currentPestName 为空），最后一招：**从问题文本里找词条名**。
            # 38 条词条，逐个 in 判断的代价可以忽略。
            from .models import PestInfo

            for candidate in PestInfo.objects.only('id', 'name', 'name_en'):
                if candidate.name and candidate.name in question:
                    pest = candidate
                    break
                if candidate.name_en and candidate.name_en.lower() in question.lower():
                    pest = candidate
                    break
        if pest is None:
            return Response({'suggestions': []})

        name = pest.name
        if lang == 'en':
            name = getattr(pest, 'name_en', '') or name

        current = _guess_intent(question)
        out = []
        for intent, templates in _FOLLOWUP_TEMPLATES.items():
            if intent == current:
                continue
            out.append({'intent': intent, 'question': templates[lang].format(name=name)})
            if len(out) == 3:
                break
        return Response({'suggestions': out})


class AssistantFeedbackView(APIView):
    """给某条助手回答打分（有用 / 没用）。

    为什么挂在**消息**上而不是会话上：一次会话里可能前几问答得好、后几问答得差，
    只有逐条记才能定位"哪一类问题答不好"。

    `useless` 时的 `note` 是最有价值的信号 —— 只统计次数无法知道该补什么内容。
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        # 只允许评价**自己的**会话里的**助手**消息（别人的一律 404，不泄漏存在性）
        message = AssistantMessage.objects.filter(
            pk=pk, session__user=request.user, role='assistant',
        ).first()
        if message is None:
            return Response({'detail': '消息不存在'}, status=status.HTTP_404_NOT_FOUND)

        verdict = str(request.data.get('verdict') or '').strip()
        if verdict not in ('helpful', 'useless'):
            return Response({'detail': 'verdict 只能是 helpful 或 useless'},
                            status=status.HTTP_400_BAD_REQUEST)

        note = str(request.data.get('note') or '').strip()
        if len(note) > 500:
            return Response({'detail': '补充说明最多 500 字'}, status=status.HTTP_400_BAD_REQUEST)

        message.verdict = verdict
        # 允许改主意（用户点错了会再点一次）；`feedback_at` 记的是最后一次评价的时间
        message.feedback_note = note
        message.feedback_at = timezone.now()
        message.save(update_fields=['verdict', 'feedback_note', 'feedback_at'])

        logger.info('助手反馈：message=%s verdict=%s', message.pk, verdict)
        return Response({
            'message_id': message.pk,
            'verdict': message.verdict,
            'note': message.feedback_note,
            'feedback_at': message.feedback_at,
        })


class AssistantEscalateView(APIView):
    """把这次会话转人工 —— 写进既有的专家咨询链路（`ConsultQuestion`）。

    **幂等**：同一会话重复调用返回同一张工单（用户多点两下不该产生三条提问）。
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        session = AssistantSession.objects.filter(pk=pk, user=request.user).first()
        if session is None:
            return Response({'detail': '会话不存在'}, status=status.HTTP_404_NOT_FOUND)

        note = str(request.data.get('note') or '').strip()
        if len(note) > 500:
            return Response({'detail': '补充说明最多 500 字'}, status=status.HTTP_400_BAD_REQUEST)

        question, created = escalate(session=session, user=request.user, note=note)
        return Response({
            'consult_question_id': question.pk,
            'session_id': session.pk,
            'title': question.title,
            'created': created,
            'detail': ('已转人工，专家会看到你的问题和 AI 当时的回答'
                       if created else '这次会话已经转过人工了，无需重复提交'),
        })
