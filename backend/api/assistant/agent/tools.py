"""工具适配 —— 把已有的两个注册表交给 LangGraph 用，**不新增第三个注册表**。

| 来源 | 用途 | 形状 |
|---|---|---|
| `ops/tools.py` 的 `TOOLS`（8 个只读函数） | 直接执行，安全 | schema 由**函数签名**生成 |
| `ops/actions.py` 的 `ACTIONS`（写动作） | **只能**经 `validate()` → 确认 → `execute()` | schema 用 `ActionSpec.schema()` |

## 两条不能省的红线

1. **只读工具进图、写动作不当作普通工具用。**
   如果写动作也当成"模型调一下就执行"的普通工具，那么 `execute()` 前的五道闸门
   （白名单 / 目标出自原话 / 先校验 / 一次一条 / 必落审计）就等于绕过了。
   本模块对写动作只提供 `prepare_write()`（校验 + 生成复述），执行发生在图里显式的
   `execute_pending()` 那一步，而它只在"确认"之后才被走到。

2. **工具参数 schema 只有一份来源。**
   只读工具的 schema 从签名生成，`ACTIONS` 的 schema 从 `ActionSpec` 生成 ——
   任何"手抄一份 JSON"的写法都会在某个字段改名后悄悄失配，
   而失配的表现是"模型总选不中工具"，不会报错。
"""
from __future__ import annotations

import logging

from langchain_core.utils.function_calling import convert_to_openai_tool

from ..ops import actions
from ..ops import tools as ops_tools

logger = logging.getLogger(__name__)

#: 只读工具名 → 可调用对象
READ_TOOLS = ops_tools.TOOLS

#: 写动作名（模型一旦选这几个，就必须走 validate → 确认 → execute）
WRITE_TOOLS = tuple(actions.ACTIONS)


def _fallback_schema(name: str) -> dict:
    """签名转换失败时的兜底：**不静默跳过**，让模型至少能看见这个工具存在"""
    logger.warning('只读工具 %s 的签名转换失败，退回空参数 schema', name)
    return {
        'type': 'function',
        'function': {
            'name': name,
            'description': '',
            'parameters': {'type': 'object', 'properties': {}, 'required': []},
        },
    }


def read_schemas() -> list[dict]:
    """八个只读工具的 OpenAI 格式 schema（从签名生成）"""
    schemas = []
    for name, func in READ_TOOLS.items():
        try:
            schema = convert_to_openai_tool(func)
        except Exception:  # noqa: BLE001 —— schema 生成失败不该让整条链路起不来
            logger.exception('只读工具 %s 的 schema 生成失败', name)
            schema = _fallback_schema(name)
        schema['function']['name'] = name  # 以注册表里的名字为准，别信函数名
        # 参数全有默认值时，`convert_to_openai_tool` 会把 `required` 整个省掉。
        # 统一补成空列表：形状固定，下游（与测试）不用到处写 `if 'required' in`。
        schema['function'].setdefault('parameters', {}).setdefault('required', [])
        schemas.append(schema)
    return schemas


def all_schemas() -> list[dict]:
    """交给模型的全集：只读 + 写（写的那几个带明确描述，模型才知道不能自己决定）"""
    return read_schemas() + list(actions.TOOL_SCHEMAS)


def run_read(name: str, args: dict, *, user=None) -> ops_tools.ToolResult:
    """执行一个只读工具。名字不在白名单里 → 不执行。**

    `run_check` 会额外写一条管理操作审计（与 `orchestrator._execute()` 一致：
    它是这套助手唯一"会执行东西"的路径）。
    """
    func = READ_TOOLS.get(name)
    if func is None:
        return ops_tools.ToolResult(name=name, ok=False, error='没有这个只读工具')

    try:
        result = func(**args)
    except TypeError as exc:
        # 参数拼错（把 days 写成 day）不是工具能自己发现的，在这里兜
        logger.warning('只读工具 %s 参数不对：%s', name, exc)
        return ops_tools.ToolResult(name=name, ok=False, error=str(exc))
    except Exception as exc:  # noqa: BLE001 —— 工具内部已兜过，这里是二道保险
        logger.exception('只读工具 %s 执行失败', name)
        return ops_tools.ToolResult(name=name, ok=False, error=type(exc).__name__)

    if name == 'run_check' and user is not None:
        # 延迟导入：避免 agent ←→ ops.orchestrator 的循环导入
        from ..ops.orchestrator import _audit_check
        _audit_check(user, str(args.get('name') or ''), result)
    return result


def prepare_write(name: str, args: dict, *, question: str):
    """校验一个写请求，**不执行**。

    :returns: `(Validated | None, error)`，语义与 `actions.validate()` 完全一致。
    """
    return actions.validate(name, args, question=question)


def execute_pending(validated, *, user) -> ops_tools.ToolResult:
    """执行一个**已确认**的写请求。

    这是全模块唯一会改数据的入口，而且只接受 `Validated`（不是裸 args）——
    `actions.validate()` 的返回值是它唯一的合法来源。
    """
    return actions.execute(validated, user=user)
