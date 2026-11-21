"""意图判定 —— 关键词规则，纯函数，可单测。

## 为什么读操作仍然用规则路由，不交给 function calling

`assistant/llm.py` 第 423 批已经支持 `tools` / `tool_calls`（写操作要用），
但**读操作仍然先走规则**，理由没变：模型不可用时必须还能按规则选出工具、给出表格答案，
而"规则路由"本身就是那条降级路径。先上 function calling 的话，等于把同一件事
写两遍（一遍模型、一遍规则），本项目在计数、双删除口径上都栽过这种重复。

所以分工是：

| 路径 | 谁决定 | 为什么 |
|---|---|---|
| 读（查状态 / 查样本） | 规则 | 六个意图就是六个工具，规则命中率实测 26/26，模型只多花一次调用 |
| 写（改状态 / 确认样本 / 回复） | **模型优先，规则兜底** | 参数（哪条 ID、改成什么）不适合再堆规则；但模型不可用时仍要能执行 |

两条路都过 `actions.validate()` —— 校验只有一份（见 `actions.py` 的五条安全约束第 3 条）。

## 为什么最多两个意图

三个以上工具的输出拼起来必然超 `LLM_MAX_TOKENS`（现配 2000），而且模型会开始
混用口径（"7 天识别量"和"14 天反馈准确率"读成同一件事）。两个足够覆盖
`health + howto`（"健康有红项，怎么修"）这与唯一的跨类组合。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

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


# ══════════════════════════════════════════════════════════════════════
# 写操作意图（第 423 批）—— 规则兜底
# ══════════════════════════════════════════════════════════════════════
#
# 与读意图**分开**，不进 `KEYWORDS` / `INTENT_TOOLS`：那两张表是"读工具路由"，
# 混进写意图以后 `_plan()` 会按读工具的默认时间窗给写操作塞一个 `days` 参数。
#
# 这一层的目标不是"覆盖所有说法"，而是**安全兜底**：
#   · 模型可用时，说法自由的问题交给模型选工具（`orchestrator._run_action`）；
#   · 模型不可用时，只有**明确的命令句**才执行（本模块）；
#   · 两句都不是的情况一律不写 —— 少做一件该做的事，比改错一条记录便宜得多。

#: 目标 ID 在**管理员原话**里的写法。**只认这五种**，不做"问题里随便一个数字"的兜底：
#: "近 30 天确认样本有多少" 里的 30 不是 ID，猜错了就是改错记录。
#:
#: ⚠️ 这张表同时被 `find_feedback_id()`（判断"这是不是写请求"）与
#: `id_in_question()`（判断"这个 ID 是不是管理员说的"）使用 —— **必须是同一张**。
ID_PATTERNS = (
    re.compile(r'#\s*(\d{1,7})'),
    re.compile(r'反馈\s*(?:id\s*[=:：]?\s*)?(\d{1,7})', re.IGNORECASE),
    re.compile(r'feedback\s*(?:id\s*[=:：]?\s*)?(\d{1,7})', re.IGNORECASE),
    re.compile(r'编号\s*[=:：]?\s*(\d{1,7})'),
    re.compile(r'(\d{1,7})\s*号\s*(?:那条)?\s*(?:反馈|样本|记录)'),
)

#: 疑问标记。命中任一就**不执行写操作** ——
#: "确认一下反馈 #12 是不是已经处理了" 是查询，照字面执行会把一条反馈改成已确认。
#: `几` / `哪` 也在这里：`已处理的反馈有几条` 是读问题，不该因为句子里有"已处理"就变成写。
QUESTION_MARKERS = (
    '吗', '是不是', '有没有', '怎么样', '怎么', '如何', '为什么', '什么', '多少', '几', '哪',
    '？', '?',
)

#: 回复类动词（`回复 #12：已修复` / `反馈 #12 回复：…`）
REPLY_VERBS = ('回复', '答复')
#: 赋值类动词（`标为` / `改成`）—— 后面必须跟一个值词
SET_VERBS = ('标记为', '标记成', '标为', '设为', '设成', '改成', '改为', '流转为', '转为')
#: 值词 → (工具名, 参数)。**长词排前面**（"已排除"必须先于"排除"匹配）
VALUE_WORDS: tuple[tuple[str, str, dict], ...] = (
    ('已确认', 'verify_feedback_sample', {'verify_status': 'confirmed'}),
    ('已排除', 'verify_feedback_sample', {'verify_status': 'rejected'}),
    ('待确认', 'verify_feedback_sample', {'verify_status': 'pending'}),
    ('已处理', 'mark_feedback_handled', {'status': 'resolved'}),
    ('处理中', 'mark_feedback_handled', {'status': 'processing'}),
    ('待处理', 'mark_feedback_handled', {'status': 'pending'}),
    # 裸动词只在前置位置认（`确认反馈 #12` / `排除 #12`），见 detect_action 第 ③ 步
    ('确认', 'verify_feedback_sample', {'verify_status': 'confirmed'}),
    ('核实', 'verify_feedback_sample', {'verify_status': 'confirmed'}),
    ('排除', 'verify_feedback_sample', {'verify_status': 'rejected'}),
    ('剔除', 'verify_feedback_sample', {'verify_status': 'rejected'}),
)
#: 只认"前置动词"的那几个值词（裸用时不带方向，必须靠句式确认：
#: "确认反馈 #12" 是命令，"反馈 #12 确认" 读不通）
LEADING_VERBS = ('确认', '核实', '排除', '剔除')

#: 句首出现这些词 = 在吩咐我做事（"确认这条反馈" / "回复一下"）
IMPERATIVE_STARTS = ('回复', '答复') + SET_VERBS + LEADING_VERBS + ('标记', '改成', '设为', '流转')
#: 句中出现这些词 = 也是吩咐（"帮我 / 请 / 把 / 将 / 给" 都是祈使标记）
IMPERATIVE_MARKERS = ('把', '将', '帮', '请', '给')

#: 问题里出现这些词，说明**像是**要动手（决定要不要请模型选工具）
ACTION_WORDS = tuple(word for word, _tool, _args in VALUE_WORDS) + REPLY_VERBS + \
    ('标记', '改成', '设为', '流转', '处理一下', '改一下')

#: 回复正文的抽取：`回复 #12：xxx` / `回复反馈 12 "xxx"`
_REPLY_TEXT = re.compile(r'(?:回复|答复)\s*(?:反馈)?\s*(?:#?\s*\d{1,7})?\s*[:：,，]?\s*(.+)$')
#: 正文两头的引号（管理员常写「已修复」）
_QUOTES = '「」“”"\'`'
#: 去掉 head/tail 两端的分隔符，便于判断"动词是不是紧挨着 ID"
_SEPARATORS = ' \u3000:：,，。.!！-—、;；\n\t'


@dataclass
class ActionHint:
    """规则层对"这次想改什么"的判断。

    `tool is None` 表示**识别出是写请求、但没读懂要做什么**（缺 ID / 缺动作词），
    编排层据此回一句引导，而不是把问题丢给读工具 —— 那会答非所问。
    """

    tool: str | None
    args: dict
    #: 人读原因（缺什么：`missing_id` / `missing_verb` / `missing_value`）
    reason: str = ''


def _find_span(question: str):
    """返回 `(序号, 起, 止)`：**最早出现**的那个 ID（head/tail 要按位置切）"""
    text = question or ''
    best = None
    for pattern in ID_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            value = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        if best is None or match.start() < best[1]:
            best = (value, match.start(), match.end())
    return best


def find_feedback_id(question: str) -> int | None:
    """从问题里抽反馈 ID（找不到返回 None）"""
    span = _find_span(question)
    return span[0] if span else None


def id_in_question(feedback_id: int, question: str) -> bool:
    """这个 ID 是否**以 `ID_PATTERNS` 的写法**出现在管理员原话里。

    为什么必须校验：模型幻觉一个 id 就能改到无关记录。这类事故不报错、不告警，
    只表现为"某条反馈莫名其妙变成已处理" —— 复盘时连从哪来的都不知道。
    """
    for pattern in ID_PATTERNS:
        for match in pattern.finditer(question or ''):
            try:
                if int(match.group(1)) == int(feedback_id):
                    return True
            except (TypeError, ValueError):
                continue
    return False


def _reply_text(question: str) -> str:
    """抽回复正文；抽不到返回空串（**绝不代写**）"""
    match = _REPLY_TEXT.search(question or '')
    if not match:
        return ''
    text = (match.group(1) or '').strip().strip(_QUOTES).strip()
    # 只剩标点/单个字符时当作"没给正文"
    return text if len(text) >= 2 else ''


def _value_in(body: str, *, allow_leading: bool = False):
    """从一段文本里认出"目标值"→ `(工具名, 参数)`；认不出返回 None"""
    for word, tool, args in VALUE_WORDS:
        if word not in body:
            continue
        if word in LEADING_VERBS and not allow_leading:
            # "反馈 #12 确认" 读不通：裸动词只在前置/赋值句式里认
            continue
        return tool, dict(args)
    return None


def _head_verb(head: str):
    """`head` 末尾是不是一个前置动词（`确认反馈 #12` → `确认`）"""
    stripped = (head or '').rstrip(_SEPARATORS)
    for verb in LEADING_VERBS:
        if stripped.endswith(verb):
            return verb
    return ''


def looks_like_action(question: str) -> bool:
    """问题里有没有"动手"的词（用来决定要不要请模型选写工具）"""
    text = question or ''
    return any(word in text for word in ACTION_WORDS)


def is_command(question: str) -> bool:
    """**像一条命令**：有动手的词，且不是疑问句。

    疑问句一律不写（见 `QUESTION_MARKERS`）：`确认一下反馈 #12 是不是已经处理了`
    是查询，照字面执行会把一条反馈改成已确认。`detect_action()` 与编排层的
    "请模型选工具"判定都用这一条 —— 两处分别判一次，早晚会出现一处放行、一处拦住。
    """
    text = (question or '').strip()
    if not text or not looks_like_action(text):
        return False
    return not any(marker in text for marker in QUESTION_MARKERS)


def is_imperative(question: str) -> bool:
    """**在吩咐我做事**（而不是在说某类东西）。

    为什么需要它：`已处理的反馈列表` 里有动作词"已处理"、也不是疑问句，
    但它是一个**名词短语**（要的是列表），不是"把某条改成已处理"。
    只看动作词的话它会掉进"要改哪一条反馈？"的引导里 —— 答非所问。
    """
    text = (question or '').strip()
    if any(marker in text for marker in IMPERATIVE_MARKERS):
        return True
    return any(text.startswith(verb) for verb in IMPERATIVE_STARTS)


def detect_action(question: str) -> ActionHint | None:
    """写操作意图。返回 None 表示"这不是一条写命令"，调用方按读流程走。

    判据（**全部满足**才执行）：
      1. 有"动手"的词、也有带明确指向的 ID；
      2. **不是疑问句**（见 `is_command`）；
      3. 句式是命令：要么"ID 后紧跟动词/值词"（`把反馈 #12 标为已处理`），
         要么"动词紧挨 ID 之前"（`确认反馈 #12`）。

    只有动作词没 ID 时返回 `ActionHint(tool=None, reason='missing_id')` ——
    让编排层回一句"请指明哪一条"，而不是猜一个最近的反馈。
    """
    text = (question or '').strip()
    if not is_command(text):
        return None

    span = _find_span(text)
    if span is None:
        # 没有目标：只有"像在吩咐我"的句子才回引导。
        # `已处理的反馈列表` 这种名词短语交回读路径（它要的是列表，不是"改一条"）。
        if not is_imperative(text):
            return None
        return ActionHint(tool=None, args={}, reason='missing_id')

    feedback_id, start, end = span
    tail = text[end:].lstrip(_SEPARATORS)
    head = text[:start]

    # ① 回复：动词紧挨 ID 之后（`反馈 #12 回复：…`）或紧挨之前（`回复 #12：…`）
    for verb in REPLY_VERBS:
        if tail.startswith(verb) or head.rstrip(_SEPARATORS).endswith(verb):
            args = {'feedback_id': feedback_id}
            reply = _reply_text(text)
            if reply:
                args['reply'] = reply
            # 抽不到正文也照样返回：`actions.validate()` 会给出"没有给出回复正文"的
            # 明确拒绝理由，比在这里返回 None（然后被当成读请求）清楚得多。
            return ActionHint(tool='reply_feedback', args=args, reason=verb)

    # ② 赋值句式：`标为/设为/改成` + 值词
    for verb in SET_VERBS:
        if tail.startswith(verb):
            mapped = _value_in(tail, allow_leading=True)
            if mapped is None:
                return ActionHint(tool=None, args={'feedback_id': feedback_id},
                                  reason='missing_value')
            tool, args = mapped
            args['feedback_id'] = feedback_id
            return ActionHint(tool=tool, args=args, reason=verb)

    # ③ 值词直接跟在 ID 后（`反馈 #12 已处理` / `反馈 #12 的样本已排除`）
    mapped = _value_in(tail)
    if mapped is not None:
        tool, args = mapped
        args['feedback_id'] = feedback_id
        return ActionHint(tool=tool, args=args, reason='value')

    # ④ 前置动词（`确认反馈 #12`）
    verb = _head_verb(head)
    if verb:
        tool, args = _value_in(verb, allow_leading=True)
        args['feedback_id'] = feedback_id
        return ActionHint(tool=tool, args=args, reason=verb)

    # 有 ID、有动词，但句式读不出要做什么
    return ActionHint(tool=None, args={'feedback_id': feedback_id}, reason='missing_verb')


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
