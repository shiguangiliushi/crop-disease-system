"""意图判定 —— 关键词规则，纯函数，可单测。

## 为什么不用 function calling（v1）

`assistant/llm.py` 目前只有 `chat()` / `chat_stream()`，请求体里不带 `tools`
（见 `docs/系统助手框架.md` 的"三条前置事实"）。就算扩了，**降级路径依然要存在**：
模型不可用时必须还能按规则选出工具、给出表格答案。

而"规则路由"本身就是那条降级路径。先上 function calling 的话，等于把同一件事
写两遍（一遍模型、一遍规则），本项目在计数、双删除口径上都栽过这种重复。

## 为什么最多两个意图

三个以上工具的输出拼起来必然超 `LLM_MAX_TOKENS`（现配 2000），而且模型会开始
混用口径（"7 天识别量"和"14 天反馈准确率"读成同一件事）。两个足够覆盖
`health + howto`（"健康有红项，怎么修"）这与唯一的跨类组合。
"""
from __future__ import annotations

import re

#: 意图 → 关键词。**顺序即优先级**（同分时排前面的先入选）。
KEYWORDS: dict[str, tuple[str, ...]] = {
    'health': (
        '健康', '自检', '报错', '检查', '红项', '红了', '挂了', '挂掉', '异常',
        '起不来', '连不上', '过期', '状态', '故障',
        # 黄金问题集第 2/4/5/6 条暴露的缺口：这几类问法都很常见，原先一个都没命中
        '先修', '解释器', '依赖', '版本', '检查项',
        'check_env', 'check_model_labels', 'check_assistant',
    ),
    'trend': (
        '趋势', '最近几天', '这几天', '连续', '快照', '一直', '每天', '缺了几天', '缺失',
    ),
    'audit': (
        '谁删', '删了', '谁改', '谁停', '停用', '操作日志', '审计', '谁动', '谁封',
        '角色', '改角色',
    ),
    'stats': (
        '识别量', '准确率', '置信度', '降级', 'token', '成本', '延迟', '多少张', '统计', '用了多少',
    ),
    'samples': (
        '样本', '核验', '纠错', '待确认', '已排除', '可训练', '数据集', '导出',
    ),
    'errors': (
        '误判', '认错', '识别错', '不准', '最常错', '错得最多', '低置信',
    ),
    'howto': (
        '怎么恢复', '怎么部署', '怎么备份', '怎么回滚', '怎么导出',
        '如何恢复', '如何部署', '如何备份', '如何回滚', '如何排查',
        '哪一步', '命令', '部署', '备份', '回滚', '恢复', '迁移',
        '该跑', '跑什么', '换模型', '导出', '在哪看', '矩阵',
    ),
}

#: 最多选几个意图（见模块说明）
MAX_INTENTS = 2


def detect(question: str) -> list[str]:
    """返回命中的意图（按相关度降序，最多 `MAX_INTENTS` 个）；未命中返回 `[]`"""
    text = (question or '').lower()
    if not text:
        return []

    scored: list[tuple[float, int, str]] = []
    for order, (intent, words) in enumerate(KEYWORDS.items()):
        score = 0.0
        for word in words:
            # 长关键词更具体，权重更高（"操作日志"该比"检查"更管用）
            score += text.count(word) * (1 + len(word) / 10)
        if score > 0:
            scored.append((score, -order, intent))

    scored.sort(reverse=True)
    return [intent for _score, _order, intent in scored[:MAX_INTENTS]]


def join(intents: list[str]) -> str:
    """落库用的意图串（`health+howto`）"""
    return '+'.join(intents)


#: 问题里出现的时间说法 → 天数。**顺序即优先级**，长说法排前面
#: （"三个月"必须先于"一个月"，否则会被截成 30）。
WINDOWS: tuple[tuple[str, int], ...] = (
    ('今天', 1),
    ('昨天', 2),
    ('三天', 3),
    ('一周', 7),
    ('七天', 7),
    ('本周', 7),
    ('这个星期', 7),
    ('两周', 14),
    ('半个月', 14),
    ('14 天', 14),
    ('14天', 14),
    ('三个月', 90),
    ('90 天', 90),
    ('90天', 90),
    ('一个月', 30),
    ('这个月', 30),
    ('当月', 30),
    ('30 天', 30),
    ('30天', 30),
)


def window_days(question: str, default: int) -> int:
    """从问题里读出时间窗（天）；读不到就用该工具的默认窗。

    ## 为什么必须读

    "这个月识别了多少张"如果仍按默认 7 天跑，模型会照着问题说"30 天"，
    而这个 30 不在返回值里 → 被 `verify_numbers` 判成编造、整段答案换成表格。
    更糟的是反过来：模型老老实实说"近 7 天" —— 管理员问的是本月，
    拿到的却是另一种口径，**数字是对的、意思是错的**，比编造更难发现。
    """
    text = question or ''
    for token, days in WINDOWS:
        if token in text:
            return days
    # 兼容"最近 21 天"这类自由写法：数字 + 天，限制在 1..90
    match = re.search(r'(\d{1,2})\s*天', text)
    if match:
        return max(1, min(90, int(match.group(1))))
    return default
