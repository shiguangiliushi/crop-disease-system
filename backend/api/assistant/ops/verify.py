"""数值校验 + 命令白名单审计 —— `citations.verify()` 在运维侧的等价物。

## 为什么需要它

RAG 侧靠"引用必须真实存在"防编造；系统助手没有引用，只有**工具返回值**，
所以等价物是"答案里的数字必须能在返回值里找到"。

为什么非做不可：这个项目最贵的 bug 类型就是"数字不对但不报错" ——
`views.py:1804-1811` 那个 `GROUP BY` 带上 `timestamp` 的问题让统计卡永远显示 1/1，
不崩溃、不告警。页面上的错数字还能靠上下文看出来，聊天框里的不能。

## 只校验"统计型数字"，不校验"结构型数字"

"第 2 条""三点结论"里的数字属于行文结构，校验它们只会制造误报。
所以只挑两类：**带单位的数**（3 项 / 77.5% / 2 天）与**小数**（0.83）。
其余整数一律不查 —— 宁可漏一个，也不要让助手因为"第 3 点"而降级。

## 命令审计

提示注入的一种落法是"让模型建议一条危险命令"。答案里出现的
`python manage.py xxx` 必须都在只读白名单内，否则就地隐藏那条命令。
"""
from __future__ import annotations

import re

#: 答案里允许出现的 `manage.py` 命令（与 `tools.READONLY_COMMANDS` 同一口径，外加两个"只读/干跑"
#: 的运维命令：`backup_verify` 只校验备份文件，`export_feedback_dataset --dry-run` 只统计）。
COMMAND_WHITELIST = {
    'check_env', 'check_model_labels', 'check_assistant',
    'health_snapshot', 'backup_verify', 'export_feedback_dataset',
}

_COMMAND = re.compile(r'manage\.py\s+([a-z_][a-z0-9_]*)')
#: 带单位的统计数字（单位表与这些场景相关，别乱加：加错会引入误报）
_UNIT_NUMBER = re.compile(
    r'(\d+(?:\.\d+)?)\s*(%|％|个|条|项|天|次|张|人|小时|分钟|秒|毫秒|MB|GB|KB)'
)
_DECIMAL = re.compile(r'(?<![\d.])(\d+\.\d+)')
_DATE = re.compile(r'\d{4}-\d{1,2}-\d{1,2}|\d{1,2}:\d{2}(?::\d{2})?')
_ANY_NUMBER = re.compile(r'-?\d+(?:\.\d+)?')

#: 浮点比较的容差：覆盖"0.775 说成 0.78""91.5 说成 91.50"
TOLERANCE = 0.051


def find_commands(answer: str) -> list[str]:
    """答案里提到的 `manage.py` 命令名"""
    return _COMMAND.findall(answer or '')


def block_commands(answer: str) -> tuple[str, list[str]]:
    """把不在白名单里的命令就地隐藏，返回 (清理后的答案, 被隐藏的命令名)"""
    blocked: list[str] = []

    def _replace(match):
        name = match.group(1)
        if name in COMMAND_WHITELIST:
            return match.group(0)
        if name not in blocked:
            blocked.append(name)
        return 'python manage.py <未授权的命令，已隐藏>'

    return _COMMAND.sub(_replace, answer or ''), blocked


def numbers_in(text: str) -> list[tuple[str, float]]:
    """抽出需要校验的统计型数字（见模块说明：只取带单位的与小数）"""
    raw = _DATE.sub(' ', text or '')
    found: list[tuple[str, float]] = []
    seen: set[tuple[str, float]] = set()

    for match in _UNIT_NUMBER.finditer(raw):
        key = (match.group(0).strip(), float(match.group(1)))
        if key not in seen:
            seen.add(key)
            found.append(key)
    for match in _DECIMAL.finditer(raw):
        key = (match.group(0), float(match.group(1)))
        if key not in seen:
            seen.add(key)
            found.append(key)
    return found


def _walk_numbers(value, out: set[float]) -> None:
    """递归收集一个 JSON 结构里出现过的所有数字（含字符串里的、含列表长度）。

    列表长度也算，是因为"9 项问题"这种结论来自 `problems` 的**条数** ——
    不算它，正确结论会被判成编造（`test_list_length_counts_as_number` 钉着）。
    """
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        number = float(value)
        # 百分比 / 倍数三种写法都放行：0.775 ↔ 77.5 ↔ 0.00775
        out.update({round(number, 4), round(number * 100, 4), round(number / 100, 4)})
        return
    if isinstance(value, str):
        for token in _ANY_NUMBER.findall(value):
            try:
                _walk_numbers(float(token), out)
            except ValueError:
                continue
        return
    if isinstance(value, dict):
        for item in value.values():
            _walk_numbers(item, out)
        return
    if isinstance(value, (list, tuple, set)):
        # **列表长度本身也是数字**：`problems` 有 9 条，答案就会说"9 项问题"。
        # 不把长度算进去的话，正确结论会被判成"数字对不上"——这就是第一版的表现：
        # 模型答对了，却被校验误杀成降级。宁可放宽一点，也不能误伤。
        out.add(round(float(len(value)), 4))
        for item in value:
            _walk_numbers(item, out)
        return


def allowed_numbers(results) -> set[float]:
    """工具返回值里出现过的所有数字（含 evidence 的行）"""
    out: set[float] = set()
    for result in results:
        _walk_numbers(getattr(result, 'data', None), out)
        _walk_numbers(getattr(result, 'evidence', None), out)
        _walk_numbers(getattr(result, 'error', ''), out)
    return out


def _matches(value: float, allowed: set[float]) -> bool:
    for candidate in allowed:
        if abs(value - candidate) <= TOLERANCE:
            return True
        if round(value, 1) == round(candidate, 1):
            return True
    return False


def verify_numbers(answer: str, results) -> tuple[bool, list[str]]:
    """答案里的统计型数字是否全部来自工具返回值。

    :returns: `(是否通过, 未核对上的原样文本)`
    """
    allowed = allowed_numbers(results)
    unmatched: list[str] = []
    for raw, value in numbers_in(answer):
        if not _matches(value, allowed):
            unmatched.append(raw)
    return (not unmatched, unmatched)
