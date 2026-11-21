"""状态图 —— 框架负责循环，闸门仍然在普通 Python 里。

## 图长什么样

```
START → plan ─┬─ 没有工具调用 ─────────────────────────→ answer → END
              ├─ 只读工具 ──→ read ──→ plan          （可以来回几次，上限 MAX_STEPS）
              └─ 写工具 ────→ guard ─┬─ 可逆写 → 执行 → answer
                                     └─ 不可逆写 → 只提议（不执行）→ answer
```

## 三个"框架管不着、必须自己写"的地方

1. **写动作不走"模型调一下就执行"的通用工具路径。**
   图里给写动作单独一个 `guard` 节点：它先 `validate()`，可逆的才直接执行，
   不可逆的**只生成待确认记录**。这条边是硬编码的 ——
   模型没有能力把写操作"绕开"到 `read` 节点。

2. **不可逆写不在这里挂起。**
   第 424 批曾用 `interrupt()` 实现"提议 → 确认"，第 425 批换掉了：
   `interrupt` 的状态存在 checkpointer 里（默认 `InMemorySaver` 在进程内存），
   gunicorn 多 worker 时**确认请求会落到另一个进程**，表现为"点了确认没反应"；
   进程重启则静默丢失，没人知道曾经提议过一条删除。
   现在待确认状态落在 `OpsPendingWrite` 表里（`ops/pending.py`），
   图只负责"提出这件事"，确认是另一个确定性的请求，不经过图、也不经过模型。

3. **确认的判定是规则，不是模型。**
   如果把"这句话算不算确认"交给模型，模型就能确认自己刚提的议。见
   `ops/pending.py` 的 `is_confirm()` —— 一个纯函数。
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from ..ops import actions
from ..ops import prompts as ops_prompts
from ..ops.tools import ToolResult
from . import tools as agent_tools
from .model import DjangoLLM
from .prompts import system_prompt
from .state import MAX_STEPS, MAX_WRITES, AgentState

logger = logging.getLogger(__name__)


def _tool_message(call_id: str, name: str, result: ToolResult) -> ToolMessage:
    return ToolMessage(
        content=json.dumps(result.as_dict(), ensure_ascii=False, default=str),
        tool_call_id=call_id or '',
        name=name,
    )


def repair_unanswered(messages) -> list:
    """给"没有 tool 回复的 tool_call"补一条占位回复。

    ## 为什么必须有这一步（真机踩到的）

    OpenAI 兼容端点对 `tool_calls` 的配对是**强约束**：一条带 `tool_calls` 的 assistant
    消息，后面必须跟齐每个 `tool_call_id` 的 tool 消息，否则下一次请求直接

        HTTP 400: An assistant message with 'tool_calls' must be followed by
                  tool messages responding to each 'tool_call_id'

    而报错发生在**下一轮** —— 失败的那次调用看起来与出问题的那次无关，排查成本很高。

    图里有三条路径可能留下"没人回复的调用"：模型一次给多个 tool_call 但只有写操作进了
    `guard`、中断挂起后只回复了写那一条、以及 `read` 节点里遇到写操作名时我们要不要回。
    与其在每条边上各记一次账，不如在**调用模型之前**统一补齐 —— 这是一条结构性保证，
    而不是三处 if。
    """
    answered = {message.tool_call_id for message in messages
                if isinstance(message, ToolMessage)}
    missing = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in (message.tool_calls or []):
            call_id = call.get('id')
            if call_id and call_id not in answered:
                missing.append(ToolMessage(
                    content=json.dumps({'ok': False, 'error': '这一步没有执行'},
                                       ensure_ascii=False),
                    tool_call_id=call_id,
                    name=call.get('name') or '',
                ))
    return missing


def build_graph(*, user=None, model=None, checkpointer=None):
    """编译一张图。`user` 被闭包捕获 —— **不进 state**（要可序列化）。"""
    bound_model = (model or DjangoLLM()).bind_tools(agent_tools.all_schemas())

    def plan(state: AgentState) -> dict:
        messages = list(state.get('messages') or [])
        if not messages:
            messages = [
                SystemMessage(content=system_prompt(state.get('lang', 'zh'))),
                HumanMessage(content=state.get('question', '')),
            ]
        # 见 repair_unanswered 的说明：调用模型前先把配对补齐，否则这一轮必然 400
        repairs = repair_unanswered(messages)
        response = bound_model.invoke(messages + repairs)
        return {
            'messages': repairs + [response],
            'steps': int(state.get('steps') or 0) + 1,
        }

    def route(state: AgentState) -> str:
        last = (state.get('messages') or [None])[-1]
        calls = list(getattr(last, 'tool_calls', None) or [])
        if not calls:
            return 'answer'
        if int(state.get('steps') or 0) > MAX_STEPS:
            return 'answer'
        if int(state.get('writes') or 0) >= MAX_WRITES:
            # 已经写过一次：再要写就停，改走确定性答案（不静默执行第二次）
            return 'answer'
        if any((call.get('name') or '') in agent_tools.WRITE_TOOLS for call in calls):
            return 'guard'
        return 'read'

    def read(state: AgentState) -> dict:
        last = state['messages'][-1]
        messages, results = [], []
        for call in last.tool_calls or []:
            name = call.get('name') or ''
            args = call.get('args') or {}
            if name in agent_tools.WRITE_TOOLS:
                # 混在只读节点里的写请求：不执行，回一条明确的错误
                result = ToolResult(name=name, ok=False, error='写操作不能在只读节点执行')
            else:
                result = agent_tools.run_read(name, args, user=user)
            results.append(result.as_dict())
            messages.append(_tool_message(call.get('id') or '', name, result))
        return {'messages': messages, 'results': results}

    def guard(state: AgentState) -> dict:
        last = state['messages'][-1]
        calls = [call for call in (last.tool_calls or [])
                 if (call.get('name') or '') in agent_tools.WRITE_TOOLS]
        question = state.get('question', '')

        if len(calls) > 1:
            # 一次要求多个写：这是模型没读懂，不是它更聪明（与 orchestrator 一致）
            messages, results = [], []
            for call in calls:
                name = call.get('name') or ''
                result = ToolResult(name=name, ok=False, error='一次只能提出一个写操作')
                results.append(result.as_dict())
                messages.append(_tool_message(call.get('id') or '', name, result))
            # 配额用尽，避免它换个说法再试一次
            return {'messages': messages, 'results': results, 'writes': MAX_WRITES}

        call = calls[0]
        name = call.get('name') or ''
        call_id = call.get('id') or ''
        validated, error = agent_tools.prepare_write(
            name, call.get('args') or {}, question=question)

        if validated is None:
            result = ToolResult(name=name, ok=False, error=error)
            return {
                'messages': [_tool_message(call_id, name, result)],
                'results': [result.as_dict()],
            }

        if validated.spec.reversibility == 'reversible':
            # L2：可逆写，校验通过即执行（与既有 ops 链路的分级一致）
            result = agent_tools.execute_pending(validated, user=user)
            return {
                'messages': [_tool_message(call_id, name, result)],
                'results': [result.as_dict()],
                'writes': int(state.get('writes') or 0) + 1,
            }

        # A3：不可逆写 —— 只生成"待确认"，绝不在这里执行。
        # 落到哪张表、什么时候过期、谁有权确认，全在 ops/pending.py；图不碰这些。
        return {
            'pending': {
                'action': validated.name,
                'args': validated.args,
                'target': validated.target,
                'changes': list(validated.changes),
                'label': validated.spec.label,
                'call_id': call_id,
            },
        }

    def answer(state: AgentState) -> dict:
        # 待确认优先：这一轮没有执行任何东西，答案由 runner 补上 token 后再给出
        if state.get('pending'):
            return {'answer': '', 'degraded': 'needs_confirmation'}

        last = (state.get('messages') or [None])[-1]
        if isinstance(last, AIMessage):
            text = (last.content or '').strip() if isinstance(last.content, str) else ''
            if text:
                return {'answer': text}

        rebuilt = [ToolResult(**item) for item in (state.get('results') or [])]
        lang = state.get('lang', 'zh')
        if not rebuilt:
            return {'answer': '（这次没有拿到任何工具结果）', 'degraded': 'empty'}

        writes = [item for item in rebuilt if item.name in agent_tools.WRITE_TOOLS]
        if writes:
            # 写操作的结果**不经模型**复述：它就是它，多一层转述只会失真
            return {
                'answer': ops_prompts.deterministic_action_answer(writes[-1], lang=lang),
                'degraded': '' if writes[-1].ok else 'action_failed',
            }

        return {
            'answer': ops_prompts.deterministic_answer(rebuilt, lang=lang),
            'degraded': 'model_silent',
        }

    graph = StateGraph(AgentState)
    graph.add_node('plan', plan)
    graph.add_node('read', read)
    graph.add_node('guard', guard)
    graph.add_node('answer', answer)

    graph.add_edge(START, 'plan')
    graph.add_conditional_edges(
        'plan', route, {'read': 'read', 'guard': 'guard', 'answer': 'answer'})
    graph.add_edge('read', 'plan')
    # 写操作一律直接收尾：可逆的已经执行完，不可逆的已经生成了待确认。
    # 不再回到 plan —— 让模型复述一次写结果只会引入失真（与 ops 链路一致）。
    graph.add_edge('guard', 'answer')
    graph.add_edge('answer', END)

    return graph.compile(checkpointer=checkpointer)
