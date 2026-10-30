"""会话标题（第 251 批）—— 从"首问前 30 字"改成"病害 + 意图"。

## 为什么改

`AssistantSession.title` 原来直接截问题前 30 字。于是列表里全是
「马铃薯晚疫病为什么不能用甲霜灵？」这种长句，或者「这个病用什么药？」这种
**完全看不出是哪条病害**的标题 —— 识别的上下文（`session.pest`）根本没被利用。

## 为什么用规则而不是让模型总结

模型总结要**多花一次调用**（延迟 + 成本 + 可能失败降级）。而这条信息其实
在检索阶段就已经有了：命中的词条（病害名）+ 意图分类。拼一下就够了：

    番茄晚疫病 · 用药
    苹果黑星病 · 症状

## 边界

  · 没有命中词条（"怎么写诗"）→ 回落成问题前 30 字，与旧行为一致；
  · 英文会话用英文意图词（`use` / `symptoms`），与 `lang` 对齐；
  · 标题长度不超过 `MAX_CHARS`（与库字段 80 一致，留够余量）。
"""
from __future__ import annotations

MAX_CHARS = 30

#: 意图 → 短标签（zh / en）。键来自 `retriever.detect_intent()`。
INTENT_LABELS = {
    'symptom': ('症状', 'symptoms'),
    'chemical': ('用药', 'treatment'),
    'prevention': ('防治', 'prevention'),
    'cause': ('原因', 'causes'),
    'compare': ('区分', 'differences'),
    'general': ('', ''),
}


def build_title(question: str, pest=None, intent: str = 'general',
                lang: str = 'zh') -> str:
    """拼一个"病害 · 意图"的标题；没有词条时回落成问题的前 `MAX_CHARS` 字。"""
    text = (question or '').strip()
    name = (getattr(pest, 'name', '') or '').strip() if pest is not None else ''
    if not name:
        return text[:MAX_CHARS]

    zh_label, en_label = INTENT_LABELS.get(intent, INTENT_LABELS['general'])
    label = en_label if str(lang).startswith('en') else zh_label
    title = f'{name} · {label}' if label else name
    return title[:MAX_CHARS]
