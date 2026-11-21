"""系统助手编排 —— 对外唯一入口 `ask()`。

链路：闸门 → 限流 → （写操作 / 意图）→ 工具 → 上下文 → 生成 → 命令审计 → 数值校验 → 落库

## 三条不能破的规矩

1. **永不抛异常给视图层**。任何失败都转成 `degraded=True` + 可读答案（与农户侧一致：
   助手是旁路，不能反向拖垮页面 —— 而人正是在"系统已经不对劲"的时候才会来问它）。
2. **降级不是次要路径，是常备路径**。`LLM_ENABLED=False` 时接口照样 200，
   答案是把工具返回值摊开（`prompts.deterministic_answer`），并明确标注"未经归纳"。
3. **不落库失败不影响回答**。`OpsAssistantTurn` 是观测用的，写不进去只记日志。

## 与农户侧编排的区别（别把两份合并）

  · 那边是"检索 → 拼知识 → 生成"，这边是"选工具 → 跑工具 → 拼结果 → 生成"；
  · 那边失败要**保守**（无来源不回答），这边失败要**照样给数据**（表格本身就有用）；
  · 那边多一轮"引用校验"，这边是"数值校验 + 命令白名单"。

## 写操作是**独占的一轮**（第 423 批）

命中写操作时：不跑读工具、不再判断读意图、**不让模型转述结果**，直接返回
`prompts.deterministic_action_answer()` 的确认文案。理由：这一轮的产品是
"到底改没改成、改成了什么"，模型转述错一个字，管理员就以为操作失败或成功了。
模型的角色只剩下**选工具、填参数**（`_run_action` 里那一次 `tools=` 调用）。

`degraded` 在这一轮的含义也顺带澄清了：**成功执行不算降级**（答案是准确的，
只是不经模型），只有"拒绝执行 / 执行失败"才 `degraded=True` + `action_failed`。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from ...models_assistant_ops import OpsAssistantTurn
from .. import guard, llm
from ..llm import LLMError
from . import actions as action_tools
from . import intent as intent_mod
from . import prompts, redact, tools, verify

logger = logging.getLogger(__name__)

#: 一次问答最多跑几个工具（见 `docs/系统助手框架.md` 四、核心取舍）
MAX_TOOLS = 2

#: 落库用的写操作意图名（`OpsAssistantTurn.intent`）
ACTION_INTENT = 'action'

#: 意图 → 工具计划。`query` 占位符表示"用管理员原话当检索词"。
INTENT_TOOLS: dict[str, tuple[tuple[str, dict], ...]] = {
    'health': (('get_system_health', {}),),
    'trend': (('get_health_trend', {}),),
    'audit': (('get_audit_summary', {}),),
    'stats': (('get_ops_stats', {}),),
    'samples': (('get_feedback_samples', {}),),
    'errors': (('get_detection_errors', {}),),
    'howto': (('search_ops_docs', {'query': None}),),
}

#: 未命中意图时的引导（文案在 `prompts` 里，中英各一份 —— 这里不再抄一遍）
def _can_ask(lang: str) -> str:
    return prompts.CAN_ASK_EN if lang == 'en' else prompts.CAN_ASK


def _rate_limit() -> int:
    try:
        return int(getattr(settings, 'ASSISTANT_RATE_PER_MINUTE', 10))
    except (TypeError, ValueError):
        return 10


def rate_limited(user) -> bool:
    """限流自己算。`guard.check()` 内部查的是农户侧的 `AssistantMessage`，不能复用。

    公开这个名字是因为**流式视图要在开流之前**先判一次（一旦开始吐字就不能再回 429 了）。
    """
    limit = _rate_limit()
    if limit <= 0 or user is None or not getattr(user, 'is_authenticated', False):
        return False
    since = timezone.now() - timedelta(minutes=1)
    return OpsAssistantTurn.objects.filter(user=user, created_at__gte=since).count() >= limit


#: 每个工具默认的时间窗（问题里没说时间时用）
DEFAULT_WINDOWS = {
    'get_ops_stats': 7,
    'get_health_trend': 14,
    'get_audit_summary': 7,
    'get_feedback_samples': 30,
    'get_detection_errors': 30,
}


def _plan(intents: list[str], question: str) -> list[tuple[str, dict]]:
    """意图 → [(工具名, 参数)]，最多 `MAX_TOOLS` 个"""
    plan: list[tuple[str, dict]] = []
    names: set[str] = set()
    for item in intents:
        for name, kwargs in INTENT_TOOLS.get(item, ()):
            if name in names:
                continue
            args = dict(kwargs)
            if args.get('query', '') is None:
                args['query'] = question
            if name in DEFAULT_WINDOWS:
                # 时间窗跟问题走："这个月" => 30 天。否则口径与问题不符（见 intent.window_days）
                args['days'] = intent_mod.window_days(question, DEFAULT_WINDOWS[name])
            plan.append((name, args))
            names.add(name)

    # 问题里**点名**了白名单命令时，顺手把它跑一遍（"check_env 现在什么结果"）
    for command in tools.READONLY_COMMANDS:
        if command in question and 'run_check' not in names:
            plan.append(('run_check', {'name': command}))
            names.add('run_check')
            break

    return plan[:MAX_TOOLS]


# ══════════════════════════════════════════════════════════════════════
# 写操作（第 423 批）—— 独占一轮
# ══════════════════════════════════════════════════════════════════════

def _refuse(name: str, message: str) -> tools.ToolResult:
    """一次**没有发生**的写操作。`ok=False` 是关键：编排层据此不入生成路径。"""
    return tools.ToolResult(name=name or 'action', ok=False, error=message)


def _model_may_plan(question: str) -> bool:
    """要不要请模型来选写工具。

    三个条件同时成立才请 —— 缺一条就不请，宁可回一句引导：

      1. 问题**像一条命令**（`intent.is_command`，疑问句一律不写）；
      2. 里面有一个**带明确指向的 ID**（`intent.find_feedback_id`，与校验同一套写法）；
      3. 模型可用。

    第 1、2 条是安全闸门，不是优化："近 30 天确认样本有多少" 里也有"确认"和数字，
    只靠模型自觉不调用工具是不保险的 —— 模型每次都可能"这次想帮个忙"。
    """
    return bool(llm.enabled()
                and intent_mod.is_command(question)
                and intent_mod.find_feedback_id(question) is not None)


def _merge_guide(message: str, *, lang: str) -> str:
    """在拒绝原因后面补一句"该怎么说"，避免只回一句冷冰冰的"已拒绝"。"""
    return f'{message}\n\n{prompts.action_guide("missing_verb", lang=lang)}'


def _run_action(*, user, question: str, history=None, lang: str = 'zh'):
    """判断并执行写操作。

    :returns: `(是否写请求, ToolResult)`。`ok=True` 表示**真的改了库**；
        其余情况（拒绝、参数不合法、目标不存在、模型挂了）都是 `ok=False`，
        且此时**没有任何写入发生**。
    """
    hint = intent_mod.detect_action(question)

    # ① 规则读懂了句式 → 直接执行（模型不可用时这是唯一路径）
    if hint is not None and hint.tool is not None:
        validated, error = action_tools.validate(hint.tool, hint.args, question=question)
        if validated is None:
            return True, _refuse(hint.tool, error)
        return True, action_tools.execute(validated, user=user)

    # ② 句式是命令、但规则没读懂 → 请模型选工具（只这一次调用，不循环）
    if _model_may_plan(question):
        messages = prompts.build_action_messages(question=question, history=history, lang=lang)
        try:
            chat = llm.chat(messages, tools=action_tools.tool_schemas(),
                            temperature=0, max_tokens=300, timeout=15)
        except LLMError as exc:
            logger.warning('写操作规划调用失败：%s', exc)
            return True, _refuse('', _merge_guide(
                f'没能解析这条写命令（模型调用失败：{exc}）。', lang=lang))

        calls = chat.tool_calls or []
        if not calls:
            # 模型也觉得这不是一条能执行的命令。**不执行任何事**，回引导。
            return True, _refuse('', _merge_guide(
                '没能从这句话里确定要改哪一条反馈、改成什么。', lang=lang))
        if len(calls) > 1:
            # 一次要求多个写操作：这是模型没读懂，不是它更聪明。全部拒绝。
            return True, _refuse('', prompts.action_guide('missing_verb', lang=lang))

        call = calls[0]
        validated, error = action_tools.validate(call.name, call.arguments, question=question)
        if validated is None:
            return True, _refuse(call.name, _merge_guide(error, lang=lang))
        return True, action_tools.execute(validated, user=user)

    # ③ 看得出是写请求、但连目标都没说清 → 回一句引导，**什么都不改**
    if hint is not None:
        feedback_id = (hint.args or {}).get('feedback_id')
        return True, _refuse('', prompts.action_guide(
            hint.reason, lang=lang, feedback_id=feedback_id))

    return False, None


def _action_payload(result: tools.ToolResult, *, user, question: str, started: float,
                    lang: str = 'zh') -> dict:
    """写操作这一轮的完整返回体（**不经模型**，见模块说明）。"""
    answer = prompts.deterministic_action_answer(result, lang=lang)
    return _respond(
        user=user, question=question, answer=answer, intents=[ACTION_INTENT],
        results=[result],
        # 成功执行**不算降级**：答案是准确的，只是不经模型（见模块说明）
        degraded=not result.ok, reason='' if result.ok else 'action_failed',
        verified=True, started=started,
    )


def _audit_check(user, command: str, result: tools.ToolResult) -> None:
    """把"真的执行了一条诊断命令"写进管理操作日志。

    `run_check` 是这套助手唯一会**执行东西**的路径（其余都是查询），
    所以它该在 `/admin/health?tab=audit` 里留痕；普通问答不记 ——
    助手每天被问十几次，把问答也写进去会把审计表淹掉，
    而问答本身在 `OpsAssistantTurn` 里有更细的记录（工具名 / 耗时 / 降级原因）。
    """
    from ...audit import log_admin_action

    log_admin_action(
        user, 'assistant.ops_check',
        detail=f'系统助手执行只读诊断命令 {command}（{"成功" if result.ok else "失败"}）',
        target_type='command', target_id=command, target_repr=command,
    )


def _execute(plan: list[tuple[str, dict]], *, user=None) -> list[tools.ToolResult]:
    """按计划跑工具，逐个兜异常；`run_check` 额外写一条管理操作审计。

    工具内部（`tools._tool`）已经兜过一层，这里是二道保险 —— 参数拼错（比如把
    `days` 写成 `day`）会在**调用处**抛 `TypeError`，那不是工具能自己发现的。
    """
    results: list[tools.ToolResult] = []
    for name, args in plan:
        func = tools.TOOLS.get(name)
        if func is None:
            continue
        try:
            result = func(**args)
        except Exception as exc:  # noqa: BLE001 —— 工具内部已经兜过，这里是二道保险
            logger.exception('系统助手工具调用失败 name=%s', name)
            result = tools.ToolResult(
                name=name, ok=False, error=redact.text(str(exc) or type(exc).__name__))
        results.append(result)
        if name == 'run_check':
            _audit_check(user, str(args.get('name') or ''), result)
    return results


def _guard_text(result: guard.GuardResult, *, lang: str = 'zh') -> str:
    words = prompts.GUARD_TEXT.get(lang) or prompts.GUARD_TEXT['zh']
    if result.reason == 'empty':
        return words['empty'] + _can_ask(lang)
    if result.reason == 'too_long':
        return words['too_long'].format(limit=result.detail)
    if result.reason == 'sensitive':
        return words['sensitive']
    return words['other']


def _respond(*, user, question: str, answer: str, intents: list[str],
             results: list[tools.ToolResult], degraded: bool, reason: str,
             verified: bool, started: float, usage: dict | None = None,
             model: str = '', persist: bool = True) -> dict:
    """统一出口：算耗时、落库、拼返回体"""
    latency = int((time.time() - started) * 1000)
    payload = {
        'answer': answer,
        'intent': intent_mod.join(intents),
        'tools': [result.metric for result in results],
        'degraded': degraded,
        'degrade_reason': reason,
        'verified': verified,
        'evidence': [item for result in results for item in (result.evidence or [])],
        'usage': usage or {},
        'latency_ms': latency,
    }
    if persist and user is not None:
        try:
            OpsAssistantTurn.objects.create(
                user=user,
                question=question,
                answer=answer,
                intent=payload['intent'],
                tool_calls=payload['tools'],
                degraded=degraded,
                degrade_reason=reason,
                verified=verified,
                latency_ms=latency,
                usage=payload['usage'],
                model=model,
            )
        except Exception:  # noqa: BLE001 —— 观测写不进去不该让回答失败
            logger.exception('系统助手问答落库失败')
    return payload


#: agent 路径的意图标识（`OpsAssistantTurn.intent`）。与关键词意图区分开，
#: 统计里能直接看出"这条是图编排答的"，不用靠猜。
AGENT_INTENT = 'agent'


def ask_with_agent(*, user, question: str, history=None, lang: str = 'zh') -> dict:
    """走 agent 层（LangGraph）的问答入口（第 425 批）—— 由开关决定是否启用。

    ## 为什么开关放在这里，不放在视图里

    闸门（`guard.check`）、限流（`rate_limited`）、落库（`_respond`）三件事都在这条链路上。
    放到视图里就要么复制这三件事，要么把它们的私有实现搬出去 ——
    两条路都会长出第二套口径，而"两份实现早晚分叉"是这个仓库反复吃过的亏。

    ## 为什么延迟导入 `run_agent`

    `agent/` 依赖 `ops/`（工具注册表、校验、确定性答案）。在模块顶层导入会成环。
    延迟导入还有一个好处：**没装 langgraph 的环境仍能 import 本模块**，
    只是这条路径在调用时才报错 —— 这也让"不启用 agent"的部署不需要多一个依赖。

    ## 与 `ask()` 的差别

    `ask()` 是"意图分类 → 固定映射工具"，`ask_with_agent()` 是"模型自主选工具"。
    两者共用闸门、限流、落库与返回体结构，所以**前端不需要改**：
    多出来的只有 `pending` / `token` 两个字段（只在不可逆写提议时出现）。
    """
    from ..agent.runner import run_agent  # 延迟导入，见上面的说明

    started = time.time()

    gate = guard.check(question, user=None)
    if not gate.ok:
        return _respond(
            user=user, question=question, answer=_guard_text(gate, lang=lang),
            intents=[], results=[], degraded=True, reason=gate.reason,
            verified=True, started=started, persist=gate.reason != 'rate_limited',
        )

    if rate_limited(user):
        words = prompts.GUARD_TEXT.get(lang) or prompts.GUARD_TEXT['zh']
        return _respond(
            user=user, question=question,
            answer=words['rate_limited'].format(limit=_rate_limit()),
            intents=[], results=[], degraded=True, reason='rate_limited',
            verified=True, started=started, persist=False,
        )

    outcome = run_agent(question=question, user=user, lang=lang)
    results = [tools.ToolResult(**item) for item in (outcome.get('results') or [])]
    reason = str(outcome.get('degraded') or '')

    payload = _respond(
        user=user, question=question, answer=str(outcome.get('answer') or ''),
        intents=[AGENT_INTENT], results=results,
        degraded=bool(reason), reason=reason, verified=True, started=started,
    )
    if outcome.get('pending'):
        # 不可逆写的提议：把 token 交给前端，执行发生在 /confirm/（不经过模型）
        payload['pending'] = outcome.get('pending')
        payload['token'] = outcome.get('token') or ''
    return payload


def _degrade(*, user, question, intents, results, reason, started, note='',
             verified: bool = True, persist: bool = True, lang: str = 'zh') -> dict:
    answer = prompts.deterministic_answer(results, reason=reason, note=note, lang=lang)
    return _respond(
        user=user, question=question, answer=answer, intents=intents, results=results,
        degraded=True, reason=reason, verified=verified,
        started=started, persist=persist,
    )


def _prepare(*, user, question: str, started: float, lang: str = 'zh', history=None):
    """闸门 → 限流 → 写操作 → 意图 → 工具 → 能不能调模型。

    :returns: `(early, intents, results)`。`early` 非空表示"这条路已经走完了" ——
        它是一份完整的返回体（已落库），调用方直接返回/直接发一个 delta 即可。
        把这段单独抽出来，是为了让 `ask()` 与 `ask_stream()` **共用同一条判定链** ——
        两份实现早晚会分叉（比如"限流要不要落库"这种细节）。
    """
    # ① 闸门（不传 user：限流自己算，见 _rate_limited）
    gate = guard.check(question, user=None)
    if not gate.ok:
        return _respond(
            user=user, question=question, answer=_guard_text(gate, lang=lang), intents=[], results=[],
            degraded=True, reason=gate.reason, verified=True, started=started,
            persist=gate.reason != 'rate_limited',
        ), [], []

    # ①' 限流（被拦下的请求**不落库**，否则重试会把自己锁得更久）
    if rate_limited(user):
        words = prompts.GUARD_TEXT.get(lang) or prompts.GUARD_TEXT['zh']
        return _respond(
            user=user, question=question,
            answer=words['rate_limited'].format(limit=_rate_limit()),
            intents=[], results=[], degraded=True, reason='rate_limited',
            verified=True, started=started, persist=False,
        ), [], []

    # ② 写操作（第 423 批）—— **独占这一轮**：命中就不再看读意图、不跑读工具。
    #    理由见模块说明：这一轮的产品是"改没改成"，混进读工具会让答案变成两份结论。
    is_action, action_result = _run_action(user=user, question=question,
                                           history=history, lang=lang)
    if is_action:
        payload = _action_payload(action_result, user=user, question=question,
                                  started=started, lang=lang)
        return payload, [ACTION_INTENT], [action_result]

    # ③ 意图
    intents = intent_mod.detect(question)
    if not intents:
        words = prompts.GUARD_TEXT.get(lang) or prompts.GUARD_TEXT['zh']
        return _respond(
            user=user, question=question,
            answer=words['no_intent'] + _can_ask(lang),
            intents=[], results=[], degraded=True, reason='no_intent',
            verified=True, started=started,
        ), [], []

    # ③ 工具
    results = _execute(_plan(intents, question), user=user)
    if results and not any(result.ok for result in results):
        return _degrade(user=user, question=question, intents=intents, results=results,
                        reason='tool_failed', started=started, lang=lang), intents, results
    if all(_is_empty(result) for result in results):
        return _degrade(user=user, question=question, intents=intents, results=results,
                        reason='empty', started=started, lang=lang), intents, results

    # ④ 模型不可用就降级，不报错（助手是旁路，不能反过来拖垮页面）
    if not llm.enabled():
        return _degrade(user=user, question=question, intents=intents, results=results,
                        reason='llm_disabled', started=started, lang=lang), intents, results

    return None, intents, results


def _postprocess(raw: str, results, intents: list[str],
                 lang: str = 'zh') -> tuple[str, bool, str, bool, str]:
    """命令白名单审计 + 数值校验（两档）。

    :returns: `(最终答案, 是否降级, 降级原因, 是否通过校验, 备注)`

    两档策略（框架文档 9.3）：
      · 问数字（health/trend/audit/stats/samples/errors）—— 严格：整段换成表格，
        绝不把编造的统计念给人听；
      · 问步骤（howto）—— 宽松：保留原文，只把没核对上的数字标出来。
        指引的价值在步骤，一个没被问到的"14 天"不该把整段操作建议丢掉，
        而这个数字已经被单独点出来了，不会冒充事实。
    """
    answer, blocked = verify.block_commands(raw)
    if blocked:
        # 只报条数，**不把命令名念回去** —— 念回去等于把刚隐藏的东西又贴了一遍
        answer += f'\n\n（另有 {len(blocked)} 条建议命令不在只读白名单内，已隐藏）'

    ok, unmatched = verify.verify_numbers(answer, results)
    if ok:
        return answer, False, '', True, ''

    if set(intents) <= {'howto'}:
        answer += ('\n\n（提示：以下数字未在工具返回值中出现，请自行核对：'
                   + '、'.join(unmatched[:5]) + '）')
        return answer, False, '', False, ''

    note = '未核对上的数字：' + '、'.join(unmatched[:5])
    return (prompts.deterministic_answer(results, reason='verify_failed', note=note, lang=lang),
            True, 'verify_failed', False, note)


def ask(*, user, question: str, history=None, lang: str = 'zh') -> dict:
    """系统助手的唯一入口（一次返回完整答案）。返回体见框架文档第八节。"""
    started = time.time()

    early, intents, results = _prepare(user=user, question=question, started=started,
                                       lang=lang, history=history)
    if early is not None:
        return early

    messages = prompts.build_messages(
        question=question, context=prompts.build_context(results), history=history, lang=lang,
    )
    try:
        # temperature=0：这条链路是**复述数据**，不是写文案。
        # 0.2 会让同一道题两次答出不同的数字取舍（实测：一次说了个没被问到的
        # "14 天"、另一次没有），而评分与"数字必须可核对"都建立在可复现上。
        chat = llm.chat(messages, temperature=0)
    except LLMError as exc:
        logger.warning('系统助手模型调用失败：%s', exc)
        reason = 'timeout' if '超时' in str(exc) else 'llm_error'
        return _degrade(user=user, question=question, intents=intents, results=results,
                        reason=reason, started=started, lang=lang)

    answer, degraded, reason, verified, note = _postprocess(chat.text, results, intents, lang)
    if degraded:
        return _degrade(user=user, question=question, intents=intents, results=results,
                        reason=reason, started=started, verified=verified, note=note, lang=lang)

    usage = {
        'prompt_tokens': chat.prompt_tokens,
        'completion_tokens': chat.completion_tokens,
        'latency_ms': chat.latency_ms,
    }
    return _respond(
        user=user, question=question, answer=answer, intents=intents, results=results,
        degraded=False, reason='', verified=verified, started=started,
        usage=usage, model=chat.model,
    )


# ══════════════════════════════════════════════════════════════════════
# 流式（SSE）
# ══════════════════════════════════════════════════════════════════════

def _sse(event: str, data: dict) -> bytes:
    """一条 SSE 事件。事件名走 `event:`，负载走 `data:`（都是 JSON）"""
    return f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'.encode('utf-8')


def _meta(payload: dict) -> dict:
    """`meta` 事件：模型开口之前先把"这次查了什么"告诉前端"""
    return {
        'intent': payload.get('intent') or '',
        'tools': payload.get('tools') or [],
        'degraded': bool(payload.get('degraded')),
        'degrade_reason': payload.get('degrade_reason') or '',
    }


def _done(payload: dict) -> dict:
    """`done` 事件：**权威答案**在这里。

    流式下数值校验只能在结束时做（前面已经吐字了）。校验不过时 `answer` 是降级后的
    表格，前端要**整体替换**已渲染的文本 —— 这条约定写在框架文档第八节。
    """
    return {
        'answer': payload.get('answer') or '',
        'intent': payload.get('intent') or '',
        'tools': payload.get('tools') or [],
        'degraded': bool(payload.get('degraded')),
        'degrade_reason': payload.get('degrade_reason') or '',
        'verified': bool(payload.get('verified')),
        'evidence': payload.get('evidence') or [],
        'usage': payload.get('usage') or {},
        'latency_ms': payload.get('latency_ms') or 0,
        #: 第 426 批：不可逆写的提议（`pending` 非空 + 一次性 `token`）。
        #: 没有提议时是 `None` / `''` —— 字段恒定存在，前端不用判断"有没有这个键"。
        'pending': payload.get('pending') or None,
        'token': payload.get('token') or '',
    }


def ask_stream(*, user, question: str, history=None, lang: str = 'zh'):
    """流式版 `ask()`：`meta` → `delta`（多条）→ `done`。

    事件序列与农户侧一致（前端可以共用一套解析），差别只有两点：
      · `meta` 里带 `tools`（本次调了哪些工具、成没成、多久）；
      · `done` 里带**权威答案**，前端必须用它覆盖已渲染的文本。

    降级时**不装成流式**：一次 delta 把整段确定性答案发完。假装逐字吐字只会让人以为
    模型在思考，实际是模板。

    ## 第 426 批：打开 agent 开关时，流式也必须走 agent

    否则**确认入口是死代码**：页面只用 SSE，而 agent 路径（唯一会产出
    `pending` / `token` 的那条）原先只挂在非流式 `ask_with_agent()` 上。
    agent 一次返回完整答案，所以这里只发一个 `delta` 再发 `done` ——
    与"降级时不装成流式"是同一条理由：没有真正的逐字生成，就不该假装有。
    """
    if getattr(settings, 'OPS_AGENT_ENABLED', False):
        payload = ask_with_agent(user=user, question=question, history=history, lang=lang)
        yield _sse('meta', _meta(payload))
        yield _sse('delta', {'text': payload.get('answer') or ''})
        yield _sse('done', _done(payload))
        return

    started = time.time()

    early, intents, results = _prepare(user=user, question=question, started=started,
                                       lang=lang, history=history)
    if early is not None:
        yield _sse('meta', _meta(early))
        yield _sse('delta', {'text': early.get('answer') or ''})
        yield _sse('done', _done(early))
        return

    messages = prompts.build_messages(
        question=question, context=prompts.build_context(results), history=history, lang=lang,
    )

    # meta 要在**模型开口之前**发出去：工具已经跑完（这里是毫秒级），
    # 前端可以立刻显示"查了哪些东西"，而不是只显示一个转圈。
    yield _sse('meta', {
        'intent': intent_mod.join(intents),
        'tools': [result.metric for result in results],
        'degraded': False,
        'degrade_reason': '',
    })

    chunks: list[str] = []
    model = ''
    usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'latency_ms': 0}

    try:
        # temperature=0（理由见 ask()：复述数据，不要发挥）
        for event in llm.chat_stream(messages, temperature=0):
            if 'text' in event:
                text = event.get('text') or ''
                if text:
                    chunks.append(text)
                    yield _sse('delta', {'text': text})
            elif 'usage' in event:
                raw_usage = event.get('usage') or {}
                usage['prompt_tokens'] = int(raw_usage.get('prompt_tokens') or 0)
                usage['completion_tokens'] = int(raw_usage.get('completion_tokens') or 0)
            elif 'model' in event:
                model = str(event.get('model') or '')
                usage['latency_ms'] = int(event.get('latency_ms') or 0)
    except LLMError as exc:
        # 流已经开了，**不能再回 4xx**：把已有内容发完，再补一句降级说明
        logger.warning('系统助手流式调用中断：%s', exc)
        reason = 'timeout' if '超时' in str(exc) else 'llm_error'
        payload = _degrade(
            user=user, question=question, intents=intents, results=results,
            reason=reason, started=started, lang=lang,
        )
        interrupted = ('\n\n（模型调用中断，以下是工具查到的原始结果）\n' if lang != 'en'
                       else '\n\nThe model call was interrupted. Raw tool output follows.\n')
        yield _sse('delta', {'text': interrupted})
        yield _sse('done', _done({**payload, 'answer': payload.get('answer') or ''}))
        return

    answer, degraded, reason, verified, note = _postprocess(''.join(chunks), results, intents, lang)
    if degraded:
        payload = _degrade(user=user, question=question, intents=intents, results=results,
                           reason=reason, started=started, verified=verified, note=note, lang=lang)
    else:
        payload = _respond(
            user=user, question=question, answer=answer, intents=intents, results=results,
            degraded=False, reason='', verified=verified, started=started,
            usage=usage, model=model,
        )
    yield _sse('done', _done(payload))



def _is_empty(result: tools.ToolResult) -> bool:
    """工具成功、但**确实什么都没查到**（目前只有文档检索会这样）。

    刻意只看 `hits`：健康检查"0 项问题"、审计"0 条操作"都是**正常的答案**，
    不是"没数据"。把它们当空的后果是——系统一切正常时反而降级成一张表。
    """
    if not result.ok:
        return False
    data = result.data or {}
    if 'hits' in data:
        return not data['hits']
    return False
