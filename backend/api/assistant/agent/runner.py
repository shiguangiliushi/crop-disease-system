"""对外入口 —— 给视图层/测试用的唯一函数。

## 与视图层的关系

`runner` 不碰 HTTP、不落 `OpsAssistantTurn`、不拼 SSE：那些仍然是
`ops/orchestrator.py` 的事。这里只负责"跑完图、把结果整理成字典"，
这样渐进替换时（先把某条路径切到 agent，其余照旧）两边可以并存。

## 待确认状态不在这里

第 425 批起，"不可逆写要确认"这件事**不靠图的挂起**：图只负责算出
"想做什么"（`state.pending`），落库、过期、认领、执行全在 `ops/pending.py`。
所以这里不传 checkpointer、也没有 `resume` —— 图是一次性跑完的纯函数式流程，
多 worker 部署下天然安全。

（第 424 批曾用 `interrupt()` + `InMemorySaver` 做挂起，已废弃：
状态在进程内存里，gunicorn 多 worker 时确认请求会落到另一个进程。）
"""
from __future__ import annotations

import logging
import uuid

from ..llm import LLMError
from ..ops import actions
from ..ops import pending as pending_store
from .graph import build_graph
from .state import MAX_STEPS

logger = logging.getLogger(__name__)


def confirmation_text(pending: dict, token: str, *, lang: str = 'zh') -> str:
    """"我要做 X，确认吗？"的复述文本。

    必须把**动作 + 目标 + 会改什么**都说出来 —— 只说"确认删除吗"等于让管理员
    在没有信息的情况下点确定，那不叫二次确认，叫走流程。
    有效期也写出来：过期的确认会被拒绝，不提前说就不会有人知道为什么。
    """
    label = pending.get('label') or pending.get('action') or '写操作'
    target = pending.get('target') or ''
    changes = pending.get('changes') or []
    minutes = pending_store.TTL_SECONDS // 60

    if lang == 'en':
        lines = [f'About to run: **{label}**']
        if target:
            lines.append(f'Target: {target}')
        if changes:
            lines.append('Fields to change: ' + ', '.join(map(str, changes)))
        lines += [
            '',
            'This operation **cannot be undone**.',
            f'Reply "confirm" to run it, or "cancel" to abandon. Valid for {minutes} minutes.',
            f'Confirmation token: `{token}`',
        ]
        return '\n'.join(lines)

    lines = [f'准备执行：**{label}**']
    if target:
        lines.append(f'目标：{target}')
    if changes:
        lines.append('会改动：' + '、'.join(map(str, changes)))
    lines += [
        '',
        '这一步**不可逆**，执行后无法撤销。',
        f'回复「确认」执行，或「取消」放弃。{minutes} 分钟内有效。',
        f'确认凭据：`{token}`',
    ]
    return '\n'.join(lines)


def run_agent(*, question: str, user=None, lang: str = 'zh',
              thread_id: str | None = None, model=None, checkpointer=None) -> dict:
    """跑一次系统助手 agent。返回统一的结果字典（字段见各分支）。

    不可逆写不会被执行：这一轮只会**生成一条待确认记录**，并把 token 交回来，
    由确认接口（`OpsAssistantConfirmView`）在另一次请求里决定要不要做。
    """
    thread_id = thread_id or uuid.uuid4().hex
    graph = build_graph(user=user, model=model, checkpointer=checkpointer)
    config = {'configurable': {'thread_id': thread_id}}

    initial = {
        'messages': [],
        'question': question,
        'lang': lang,
        'steps': 0,
        'writes': 0,
        'results': [],
        'pending': None,
    }

    try:
        result = graph.invoke(initial, config)
    except LLMError as exc:
        # llm.py 的契约：调用方必须接住并降级。这里**不重试** ——
        # 写操作的重试可能变成"提两条一样的待确认"。
        logger.warning('agent 调用模型失败：%s', exc)
        return _fail(thread_id, '抱歉，模型暂时不可用，这条问题没能查成。可以稍后再问，或者换个说法。',
                     degraded='model_unavailable')

    base = {
        'thread_id': thread_id,
        'interrupted': False,
        'steps': int(result.get('steps') or 0),
        'events': _events(result),
        'results': list(result.get('results') or []),
    }

    pending = result.get('pending')
    if not pending:
        return {**base, 'answer': str(result.get('answer') or ''),
                'degraded': str(result.get('degraded') or ''), 'pending': None, 'token': ''}

    # ── 不可逆写：只落"待确认"，不执行 ────────────────────────────────────
    validated, error = actions.validate(
        pending.get('action') or '', pending.get('args') or {}, question=question)
    if validated is None:
        logger.warning('待确认操作在落库前校验失败：%s', error)
        return {**base, 'answer': error, 'degraded': 'action_failed',
                'pending': None, 'token': ''}

    row, reason = pending_store.propose(user=user, validated=validated, question=question)
    if row is None:
        return {**base, 'answer': reason, 'degraded': 'action_failed',
                'pending': None, 'token': ''}

    return {
        **base,
        'answer': confirmation_text(pending, row.token, lang=lang),
        'degraded': 'needs_confirmation',
        'pending': {**pending, 'token': row.token, 'expires_at': row.expires_at.isoformat()},
        'token': row.token,
    }


def _events(result) -> list:
    """观测用：每个工具调用的 `metric`（名字 / 成不成 / 耗时）"""
    return [
        {'name': item.get('name', ''), 'ok': bool(item.get('ok')),
         'ms': int(item.get('ms') or 0), 'error': item.get('error', '')}
        for item in (result.get('results') or [])
    ]


def _fail(thread_id: str, answer: str, *, degraded: str) -> dict:
    return {
        'thread_id': thread_id,
        'answer': answer,
        'degraded': degraded,
        'interrupted': False,
        'pending': None,
        'token': '',
        'results': [],
        'steps': 0,
        'events': [],
    }


def max_steps() -> int:
    return MAX_STEPS
