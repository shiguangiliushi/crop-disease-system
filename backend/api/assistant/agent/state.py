"""agent 的状态定义 —— 一份状态，两类消费方（模型上下文 / 审计观测）。

## 为什么不用 `MessagesState` 现成的那个

`MessagesState` 只有 `messages`。本图还需要四个不属于"对话"的字段：
步数（防循环）、写次数（`MAX_WRITES`）、待确认快照（A3）、事件流（观测）。
把它们塞进 `messages` 或者丢到实例属性上，都会让多线程/多请求相互污染 ——
状态必须**全部**在 state 里，才可能被 checkpointer 正确隔离。
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

#: 一次问答最多几次"模型 → 工具"往返。超过就停，改走确定性答案。
#: 定 4 而不是 6：系统助手的工具都是"查一次就有结果"的形态，
#: 需要 4 次以上的问题是设计没覆盖，而不是模型更努力。
MAX_STEPS = 4

#: 与 `ops/actions.py` 的 `MAX_WRITES` 对齐：一轮问答最多执行一次写。
MAX_WRITES = 1


class AgentState(TypedDict, total=False):
    """图的状态。

    `messages` 用 `add_messages` 归并（后写的追加，不是覆盖）；
    `events` 用 `operator.add` 追加 —— 观测流只增不减，不能在节点里被后一个覆盖。
    """

    #: 对话上下文（SystemMessage + HumanMessage + AIMessage/ToolMessage 往返）
    messages: Annotated[list[AnyMessage], add_messages]
    #: 管理员原话。"目标必须来自原话"这条校验要用它，所以必须全程带着，
    #: 不能只放在 HumanMessage 里靠模型忠实地复述。
    question: str
    lang: str
    #: 已经走了几步
    steps: int
    #: 已经执行了几次写
    writes: int
    #: A3 待确认快照（**必须可 JSON 序列化**：它要进 checkpointer）
    pending: dict[str, Any] | None
    #: 每次工具调用的 `ToolResult.as_dict()`。存 dict 不存 dataclass ——
    #: 状态要进 checkpointer，顺手保持"状态里全是可序列化数据"这条约定，
    #: 换 Sqlite/Postgres checkpointer 时不用再改一遍。
    results: Annotated[list[dict], operator.add]
    #: 最终答案（`answer` 节点写，runner 读）
    answer: str
    #: 非空表示这条答案来自降级路径
    degraded: str
