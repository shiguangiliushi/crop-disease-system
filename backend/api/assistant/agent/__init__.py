"""系统助手的 agent 层（第 424 批）—— 用 LangGraph 管循环，闸门仍是普通 Python。

## 为什么这一层单独存在，而不是改写 `ops/orchestrator.py`

现有的 `ops/` 链路是"意图分类 → 固定映射工具 → 执行 → 数值校验 → 落库"，
每一步都有单测钉住，并且降级矩阵/限流/脱敏/审计都在里面。换成图编排如果**原地改**，
等于同时改动循环与闸门两件事，出问题时无法判断是哪一侧退化了。

所以先把图放在旁边：`agent/` 只依赖 `ops/tools.py`（只读）、`ops/actions.py`（写）、
`ops/prompts.py`（确定性答案），**不修改它们**。切流量的方式是"视图层改调
`run_agent()` 还是 `orchestrator.ask()`"，随时可以退回去。

## 三个不许在这一层"顺手实现"的东西

1. 只读/写工具的白名单 —— 在 `ops/` 里，这里只查表；
2. 写操作的五道闸门 —— 在 `actions.validate()` / `execute()` 里，这里只调用；
3. 脱敏 —— 在 `ops/redact.py` 里，工具返回值在进模型之前必须已经过它（`ops/tools.py`
   内部已做），agent 层**不再拼原始数据进提示词**。

## 依赖

只多 `langgraph`（+ 它自带的 `langchain-core`）。不装 `langchain-openai`：
模型调用仍走 `llm.chat()`，见 `agent/model.py` 的说明。
"""
from .graph import build_graph
from .runner import run_agent

__all__ = ['build_graph', 'run_agent']
