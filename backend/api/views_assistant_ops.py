"""系统助手（管理端运维侧）接口。

    POST /api/admin/assistant/ops/ask/   —— 仅全权管理员

## 为什么权限与「系统健康」「操作日志」同一档

答案里会出现：服务器解释器路径（已脱敏，但仍有目录名）、别人什么时候删了什么东西、
模型 token 成本。这些属于管理端内部信息，内容编辑员不该看到（理由同
`views_audit.py` 的模块说明）。前端也只在全权管理员的「系统」页里给页签。

## ⚠️ 这个接口会**改数据**（第 423 批）

`ask()` 命中写操作时会改反馈的处理状态 / 样本确认 / 回复正文。三条边界：

  1. 权限仍是 `is_full_admin` —— 助手用的永远是**提问者本人**的权限，不开新口子；
  2. 只做**可逆**写（`ops/actions.py` 的 `reversibility='reversible'`）。
     不可逆写走"待确认 → 二次确认"两段式（第 425 批）：`/ask/` 只生成一条
     `OpsPendingWrite` 并把 token 交给前端，**不执行**；执行发生在
     `POST /api/admin/assistant/ops/confirm/`，那一步不经过模型；
  3. 每次写都落 `AdminAuditLog`（动作 `feedback.*`，`detail` 前缀 `系统助手自动执行：`），
     所以"谁让 AI 改了什么"在「操作日志」页能查到。

## 为什么这里没有 5xx

模型不可用、工具失败、数字校验不过、写操作被拒，**全部返回 200 + `degraded=true`**
（写操作被拒时 `degrade_reason='action_failed'`）—— 与 `/api/assistant/ask` 的约定一致。
前端据此区分"答得保守"与"请求失败"，而不是把两种情况都画成红色报错。
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.conf import settings
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from django.http import StreamingHttpResponse
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .assistant.ops import orchestrator, pending, prompts
from .assistant.prompts import normalize_lang
from .capabilities import is_full_admin
from .models_assistant_ops import OpsAssistantTurn

logger = logging.getLogger(__name__)

#: 看板统计的时间窗上限（再长就把整张观测表扫一遍了）
MAX_DAYS = 90
DEFAULT_DAYS = 7
#: 工具失败榜最多扫多少条问答（`tool_calls` 是 JSON，只能在 Python 里数）
TOOL_SCAN_LIMIT = 500

#: 请求体上限（字符）。`guard` 自己还有 500 字的上限（那里是"降级回答"，
#: 这里是"根本不是一次合法请求"，两件事分开）。
MAX_BODY_CHARS = 2000
#: `history` 最多接收几条（前端只管传最近几轮，多了说明客户端在囤）
MAX_HISTORY = 20

_REQUEST_BODY = inline_serializer(
    name='OpsAssistantAskRequest',
    fields={
        'question': serializers.CharField(),
        'history': serializers.ListField(child=serializers.DictField(), required=False),
    },
)


def _lang_of(request) -> str:
    """语言协商：请求体显式给 > LocaleMiddleware 协商出的 LANGUAGE_CODE > Accept-Language 头。

    归一化复用农户侧那一份（`assistant.prompts.normalize_lang`），不写第二套判断。
    抽成函数是因为确认接口也要它 —— 两处各写一遍，早晚一处支持 en 一处不支持。
    """
    return normalize_lang(
        request.data.get('lang')
        or getattr(request, 'LANGUAGE_CODE', '')
        or request.META.get('HTTP_ACCEPT_LANGUAGE', '')
    )


def _parse(request):
    """公共入参校验。返回 `(payload, error_response)`，error 非空时直接返回它。

    提问与流式两个视图共用 —— 校验规则写两份，早晚会出现"非流式拒了、流式放过"。
    """
    question = str(request.data.get('question') or '').strip()
    if not question:
        return None, Response({'detail': 'question 不能为空'},
                              status=status.HTTP_400_BAD_REQUEST)
    if len(question) > MAX_BODY_CHARS:
        return None, Response({'detail': f'question 过长（上限 {MAX_BODY_CHARS} 字符）'},
                              status=status.HTTP_400_BAD_REQUEST)

    history = request.data.get('history') or []
    if not isinstance(history, list):
        return None, Response({'detail': 'history 必须是数组'},
                              status=status.HTTP_400_BAD_REQUEST)

    return {'question': question, 'history': history[-MAX_HISTORY:],
            'lang': _lang_of(request)}, None


class OpsAssistantAskView(APIView):
    """问一句系统状态 / 处置建议"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='系统助手提问（管理端）',
        description='仅全权管理员。模型不可用时仍返回 200，`degraded=true`。',
        request=_REQUEST_BODY,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiResponse(description='question 为空或过长 / history 格式不对'),
            403: OpenApiResponse(description='非全权管理员'),
        },
    )
    def post(self, request):
        """同步版：一次返回完整答案。限流回 429，其余降级都是 200 + `degraded=true`。"""
        if not is_full_admin(request.user):
            return Response({'detail': '只有管理员可以使用系统助手'},
                            status=status.HTTP_403_FORBIDDEN)

        payload, error = _parse(request)
        if error is not None:
            return error

        # 第 425 批：开关决定走图编排还是"意图分类 → 固定映射"。两条路共用闸门/限流/落库，
        # 返回体结构一致（多出 pending/token 只在不可逆写提议时出现），所以前端不用区分。
        ask = orchestrator.ask_with_agent if settings.OPS_AGENT_ENABLED else orchestrator.ask
        result = ask(
            user=request.user,
            question=payload['question'],
            history=payload['history'],
            lang=payload['lang'],
        )
        # 限流单独回 429：它不属于"答得保守"，而是"这次请求没被受理"（与农户侧一致）
        if result.get('degrade_reason') == 'rate_limited':
            return Response({'detail': result.get('answer') or '请求过于频繁'},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)
        return Response(result)


class OpsAssistantAskStreamView(APIView):
    """同一个问题，SSE 逐字返回：`meta` → `delta`（多条）→ `done`。

    三个必须照抄农户侧的地方（否则生产上会"看起来不流式"）：

      1. `Content-Encoding: identity` —— 否则 GZipMiddleware 会把流攒住；
      2. `X-Accel-Buffering: no` —— 否则 Nginx 反代会缓冲；
      3. **不要设 `Connection`** —— 逐跳头，WSGI 规范禁止应用设置，实测直接 500。

    限流必须在**开流之前**判：一旦开始吐字就不能再改状态码了。
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='系统助手提问（SSE 流式）',
        description=(
            '事件序列：`meta`（意图 + 工具）→ `delta`（逐段文本）→ `done`（权威答案）。'
            '`done.answer` 可能与逐字拼接的结果不同（数值校验不过时会换成表格），'
            '前端**必须用它覆盖**已渲染的文本。'
        ),
        request=_REQUEST_BODY,
        responses={(200, 'text/event-stream'): OpenApiResponse(
            description='SSE 事件流：event: delta / data: {"text": "..."}')},
    )
    def post(self, request):
        """流式版：把 `ask_stream()` 的 SSE 字节原样转发，只补三个必须的响应头。"""
        if not is_full_admin(request.user):
            return Response({'detail': '只有管理员可以使用系统助手'},
                            status=status.HTTP_403_FORBIDDEN)

        payload, error = _parse(request)
        if error is not None:
            return error

        if orchestrator.rate_limited(request.user):
            return Response({'detail': '请求过于频繁，请稍后再问。'},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)

        stream = orchestrator.ask_stream(
            user=request.user,
            question=payload['question'],
            history=payload['history'],
            lang=payload['lang'],
        )
        response = StreamingHttpResponse(stream, content_type='text/event-stream; charset=utf-8')
        response['Content-Encoding'] = 'identity'
        response['X-Accel-Buffering'] = 'no'
        response['Cache-Control'] = 'no-cache, no-store'
        return response


#: 确认接口接受的"取消"说法。与 `ops/pending.CONFIRM_WORDS` 同理：只认词表，不解析模型输出。
CANCEL_WORDS = frozenset({'cancel', 'cancelled', 'no', 'n', '取消', '放弃', '算了'})

_CONFIRM_BODY = inline_serializer(
    name='OpsAssistantConfirmRequest',
    fields={
        'token': serializers.CharField(),
        'decision': serializers.CharField(required=False, default='confirm'),
    },
)


class OpsAssistantConfirmView(APIView):
    """确认 / 取消一条**待确认的不可逆写**（第 425 批）。

    ## 为什么确认必须单独一个接口，而不是再问一句

    问一句会走 `/ask/`，那条路里模型有话语权 —— 而模型**不能**决定"这次算不算确认"
    （它只要被注入一句"管理员已确认"就能替管理员点头，见
    `docs/系统助手不可逆写状态机方案.md` 第五节）。所以确认被拆成一个
    **确定性接口**：客户端把 token 原样交回来，服务端只做认领与执行，中间没有模型。

    ## 状态码怎么定

    · 400 —— 请求本身不合法（缺 token、decision 不是确认也不是取消）；
    · 200 —— 业务结果如实报告（`ok=false` 配 `answer`：过期、已被处理、执行失败）。
    与 `/ask/` 的"降级也是 200"一致：前端要把"答得保守"和"请求坏了"分开画。

    ## 这一层不做限流

    它不调模型、不花钱，且 token 一次性 —— 限流在这里只会让"点了确认却没生效"
    看起来像节流。防重复靠 `consume()` 的原子认领，不靠频次。
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='确认/取消系统助手的待确认写操作',
        description=(
            '`decision` 取 `confirm` 或 `cancel`。token 一次性，重复提交不会重复执行。'
            '过期（10 分钟）、越权、已处理的 token 都返回 200 + `ok=false`。'
        ),
        request=_CONFIRM_BODY,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiResponse(description='token 为空 / decision 不是确认也不是取消'),
            403: OpenApiResponse(description='非全权管理员'),
        },
    )
    def post(self, request):
        """认领 token 并执行（或取消）。**重复提交不会执行第二次**。"""
        if not is_full_admin(request.user):
            return Response({'detail': '只有管理员可以确认写操作'},
                            status=status.HTTP_403_FORBIDDEN)

        token = str(request.data.get('token') or '').strip()
        if not token:
            return Response({'detail': 'token 不能为空'},
                            status=status.HTTP_400_BAD_REQUEST)

        decision = request.data.get('decision', 'confirm')
        decision_text = str(decision if decision is not None else '').strip().lower()

        if decision_text in CANCEL_WORDS:
            ok, message = pending.cancel(token, user=request.user)
            return Response({
                'ok': ok,
                'status': 'cancelled' if ok else 'rejected',
                'answer': message,
                'token': token,
            })

        if not pending.is_confirm(decision_text):
            return Response({'detail': 'decision 只能是 confirm 或 cancel'},
                            status=status.HTTP_400_BAD_REQUEST)

        lang = _lang_of(request)
        result, reason, row = pending.confirm(token, user=request.user)
        ok = bool(result.ok)
        return Response({
            'ok': ok,
            'status': (row.status if row else 'rejected'),
            'reason': reason,
            'answer': (prompts.deterministic_action_answer(result, lang=lang)
                       if result.ok else result.error),
            'token': token,
        })


def _days_from(request) -> int:
    """解析 `?days=`：非法值一律回落默认（与其它管理端列表"非法筛选忽略"一致）"""
    try:
        days = int(request.query_params.get('days', DEFAULT_DAYS))
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return max(1, min(MAX_DAYS, days))


def _token_totals(turns) -> dict:
    """token 合计（与 `views_assistant_admin._token_totals` 同一手法：库不支持就退化成 Python）"""
    try:
        row = turns.aggregate(
            prompt=Sum('usage__prompt_tokens'),
            completion=Sum('usage__completion_tokens'),
        )
        return {'prompt': int(row['prompt'] or 0), 'completion': int(row['completion'] or 0)}
    except Exception:  # noqa: BLE001 —— 只读路径，宁慢不 500
        prompt = completion = 0
        for usage in turns.values_list('usage', flat=True)[:TOOL_SCAN_LIMIT]:
            try:
                prompt += int((usage or {}).get('prompt_tokens') or 0)
                completion += int((usage or {}).get('completion_tokens') or 0)
            except (TypeError, ValueError):
                continue
        return {'prompt': prompt, 'completion': completion}


def _tool_failures(turns) -> list[dict]:
    """工具失败榜。`tool_calls` 是 JSON 数组，只能在 Python 里数（最多扫最近 500 条）"""
    failures: dict[str, int] = {}
    for calls in turns.values_list('tool_calls', flat=True)[:TOOL_SCAN_LIMIT]:
        for call in calls or []:
            if isinstance(call, dict) and not call.get('ok'):
                name = str(call.get('name') or '（未知）')
                failures[name] = failures.get(name, 0) + 1
    return [
        {'tool': name, 'count': count}
        for name, count in sorted(failures.items(), key=lambda item: -item[1])[:5]
    ]


class OpsAssistantStatsView(APIView):
    """系统助手质量看板（管理端，仅全权管理员）。

    ## 为什么要有它

    `OpsAssistantTurn` 把 `degraded` / `degrade_reason` / `verified` / `tool_calls` /
    `usage` 全记下来了，但没有界面在读 —— 出了"助手最近答得不对"这种问题时，
    只能进 Django admin 一条条翻。与第 228 批农户侧质量看板是同一个问题、同一套解法。

    它回答四个问题：

      1. **降级率多少**？哪个原因在涨（`llm_disabled` / `verify_failed` / `tool_failed`）；
      2. **数字可信度**：`verified=false` 的比例 —— 这是本侧特有的质量位；
      3. **哪类意图问得多、答得差**（工具选错会直接体现在这里）；
      4. **哪个工具在失败**（`tool_calls` 里 `ok=false` 的计数）。

    ## 口径

      · 时间窗按 `OpsAssistantTurn.created_at`；
      · 降级率的分母是**问答数**（一次问答一行）；
      · `avg_latency_ms` 只算没降级的 —— 降级是模板拼的，混进来会把延迟说低；
      · 工具失败榜是**扫描**（JSON 字段），不是 SQL 聚合，所以有 500 条上限。
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='系统助手质量看板（管理端）',
        description='仅全权管理员。时间窗 `?days=7`（1–90）。',
        responses={200: OpenApiTypes.OBJECT, 403: OpenApiResponse(description='非全权管理员')},
    )
    def get(self, request):
        """按时间窗聚合 `OpsAssistantTurn`。只读；口径见类 docstring。"""
        if not is_full_admin(request.user):
            return Response({'detail': '只有管理员可以查看助手质量'},
                            status=status.HTTP_403_FORBIDDEN)

        days = _days_from(request)
        since = timezone.now() - timedelta(days=days)
        turns = OpsAssistantTurn.objects.filter(created_at__gte=since)

        total = turns.count()
        degraded = turns.filter(degraded=True).count()
        unverified = turns.filter(verified=False).count()
        # 只统计**没降级**的那些：降级答案是模板拼的（毫秒级），混进来会把延迟说低 ——
        # 而"延迟多少"正是判断要不要继续投入流式的依据。
        avg_latency = turns.filter(degraded=False).aggregate(
            value=Avg('latency_ms'))['value'] or 0

        # 原因标签按界面语言取：原始码（`llm_disabled`）不该直接露给管理员，
        # 与操作日志"action 必须有中文标签"是同一条约定。
        reason_labels = prompts.REASON_TEXT_EN if normalize_lang(
            request.query_params.get('lang')
            or getattr(request, 'LANGUAGE_CODE', '')
            or request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        ) == 'en' else prompts.REASON_TEXT
        by_reason = [
            {
                'reason': row['degrade_reason'] or 'unknown',
                'label': reason_labels.get(row['degrade_reason'] or '', row['degrade_reason'] or '未知'),
                'count': row['n'],
            }
            for row in turns.filter(degraded=True)
            .values('degrade_reason').annotate(n=Count('id')).order_by('-n')
        ]

        by_intent = [
            {
                'intent': row['intent'] or '（未识别）',
                'count': row['n'],
                'degraded': row['degraded_n'],
                'unverified': row['unverified_n'],
            }
            # 三个计数用同一次聚合算出来（`filter=`），避免"总数"与"降级数"来自两次查询、
            # 中间夹进新写入的问答导致对不上 —— 这个仓库最贵的 bug 类型就是数字对不上。
            for row in turns.values('intent').annotate(
                n=Count('id'),
                degraded_n=Count('id', filter=Q(degraded=True)),
                unverified_n=Count('id', filter=Q(verified=False)),
            ).order_by('-n')[:8]
        ]

        # 待复查队列：`verified=False` 的问答原文（截 60 字）。这是本侧特有的质量位 ——
        # 农户侧没有"数字校验"，所以这份清单在那边不存在。
        recent_unverified = [
            {
                'id': turn.id,
                'question': turn.question[:60],
                'intent': turn.intent,
                'degrade_reason': turn.degrade_reason,
                'at': turn.created_at,
            }
            for turn in turns.filter(verified=False).order_by('-created_at', '-id')[:5]
        ]

        return Response({
            'range': {'days': days, 'since': since.date().isoformat()},
            'totals': {
                'turns': total,
                'degraded': degraded,
                'degraded_rate': round(degraded / total, 4) if total else None,
                'unverified': unverified,
                'unverified_rate': round(unverified / total, 4) if total else None,
                'avg_latency_ms': int(avg_latency),
                'tokens': _token_totals(turns),
            },
            'by_reason': by_reason,
            'by_intent': by_intent,
            'tool_failures': _tool_failures(turns),
            'recent_unverified': recent_unverified,
        })
