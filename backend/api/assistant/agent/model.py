"""LangChain/LangGraph 的 ChatModel 适配器 —— 底层仍然走 `llm.chat()`。

## 为什么不装 `langchain-openai`

`llm.py` 的模块说明里写过：*"不另引 SDK —— 少一个依赖，且 SDK 会自带重试/代理策略，
反而不便于精确控制超时"*。`langchain-openai` 会把 `openai` SDK 带回来，
等于把那条决定推翻一次。

所以这里用 40 行适配器把 `llm.chat()` 包成 `BaseChatModel`：

- 超时、降级、脱敏、用量统计、`tool_calls` 解析**全部复用已有实现**，一处不重写；
- 依赖只多 `langgraph`（它自己依赖 `langchain-core`），不引 `openai`；
- 测试里要假装模型时，替换的是这一个适配器，而不是网络层。

## 异常

`LLMError` **原样抛出**，不在适配器里吞掉。`llm.py` 的契约是"调用方必须接住并降级"，
吞在这里会让 `runner` 以为"模型答了个空"，把故障表现成"模型没话说"。
"""
from __future__ import annotations

import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration
from langchain_core.outputs import ChatResult as LangChainChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool

from .. import llm


def _text_of(content) -> str:
    """LangChain 的 `content` 可能是 str，也可能是 block 列表"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ''.join(str(part.get('text', '')) if isinstance(part, dict) else str(part)
                       for part in content)
    return '' if content is None else str(content)


def to_openai_message(message) -> dict:
    """LangChain 消息 → OpenAI 兼容的 messages 项（`llm.chat` 只认这个形状）"""
    if isinstance(message, ToolMessage):
        return {
            'role': 'tool',
            'tool_call_id': message.tool_call_id,
            'content': _text_of(message.content),
        }
    if isinstance(message, SystemMessage):
        return {'role': 'system', 'content': _text_of(message.content)}
    if isinstance(message, AIMessage):
        content = _text_of(message.content)
        calls = [
            {
                'id': call.get('id') or f'call_{index}',
                'type': 'function',
                'function': {
                    'name': call.get('name') or '',
                    'arguments': json.dumps(call.get('args') or {}, ensure_ascii=False),
                },
            }
            for index, call in enumerate(message.tool_calls or [])
        ]
        payload = {'role': 'assistant', 'content': content or None}
        if calls:
            payload['tool_calls'] = calls
        return payload
    if isinstance(message, HumanMessage):
        return {'role': 'user', 'content': _text_of(message.content)}
    return {'role': 'user', 'content': _text_of(message.content)}


class DjangoLLM(BaseChatModel):
    """把 `llm.chat()` 包成一个 LangChain 聊天模型。

    只暴露三个真正会被用到的旋钮：`temperature` / `max_tokens` / `timeout`。
    模型的选型全部来自 settings（`LLM_MODEL`），**不在这里再开一个口子** ——
    否则"配置的模型"与"agent 用的模型"会出现两个来源。
    """

    temperature: float = 0.0
    max_tokens: int = 600
    timeout: float = 15.0

    @property
    def _llm_type(self) -> str:
        return 'django-llm'

    # ── 工具绑定 ────────────────────────────────────────────────────────────
    def bind_tools(self, tools, **kwargs):
        """接受 **OpenAI 格式的 dict** 或 LangChain 可转换对象（函数/BaseTool）。

        本项目的 `ACTIONS[].schema()` 已经是 OpenAI 格式，直接透传；
        `tools.py` 里八个只读函数则交给 `convert_to_openai_tool` 从签名生成 ——
        这样参数表只有一份（函数签名），不会和手写 schema 漂移。
        """
        schemas = [item if isinstance(item, dict) else convert_to_openai_tool(item)
                   for item in tools]
        return self.bind(schemas=schemas, **kwargs)

    # ── 真正的调用 ──────────────────────────────────────────────────────────
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        schemas = kwargs.get('schemas')
        payload = [to_openai_message(message) for message in messages]

        # 不接 try/except：LLMError 原样上抛，由 runner 降级（见模块说明）
        result = llm.chat(
            payload,
            tools=schemas,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
        )

        tool_calls = [
            {'name': call.name, 'args': call.arguments, 'id': call.id or f'call_{index}'}
            for index, call in enumerate(result.tool_calls)
        ]
        usage = None
        if result.completion_tokens or result.prompt_tokens:
            usage = {
                'input_tokens': result.prompt_tokens,
                'output_tokens': result.completion_tokens,
                'total_tokens': result.prompt_tokens + result.completion_tokens,
            }

        message = AIMessage(
            content=result.text or '',
            tool_calls=tool_calls,
            response_metadata={
                'model': result.model,
                'finish_reason': result.finish_reason,
                'latency_ms': result.latency_ms,
                'truncated': result.truncated,
            },
            usage_metadata=usage,
        )
        return LangChainChatResult(generations=[ChatGeneration(message=message)])
