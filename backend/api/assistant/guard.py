"""输入闸门（第 193 批，K5）—— 在**动模型之前**把不该进模型的问题挡住。

顺序很重要，这里是刻意的：
  1. 空 / 超长 —— 最便宜，先挡；
  2. 敏感词（复用既有的 `sensitive.find_sensitive_words`）—— 与论坛同一套词库，
     不另建一份，否则管理员改一处、另一处漏；
  3. 频率 —— 需要查 `AssistantMessage`，最贵，放最后。

为什么不在视图层做：视图层只管 HTTP，闸门规则要能被单元测试直接调用，
且**检索之前**就必须知道该不该继续（避免为一个会被拒的问题花检索开销）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from ..sensitive import find_sensitive_words

logger = logging.getLogger(__name__)

#: 问题长度上限（字符）。够写一段话，又不至于把上下文预算挤爆。
MAX_QUESTION_CHARS = 500
#: 每分钟最大提问次数（配置项 ASSISTANT_RATE_PER_MINUTE 优先）
DEFAULT_RATE_PER_MINUTE = 10


@dataclass
class GuardResult:
    ok: bool
    reason: str = ''      # empty / too_long / sensitive / rate_limited
    detail: str = ''      # 给用户看的细节（如命中的词）
    question: str = ''    # 归一化后的问题（去空白）


def check(question: str, *, user=None, rate_per_minute: int | None = None) -> GuardResult:
    """检查一个问题是否允许进入链路。**不抛异常**（调用方按 reason 决定话术）。"""
    text = (question or '').strip()
    if not text:
        return GuardResult(ok=False, reason='empty')

    limit = MAX_QUESTION_CHARS
    if len(text) > limit:
        return GuardResult(ok=False, reason='too_long', detail=str(limit))

    hits = find_sensitive_words(text)
    if hits:
        return GuardResult(ok=False, reason='sensitive', detail='、'.join(hits[:5]),
                           question=text)

    limit_per_min = rate_per_minute or DEFAULT_RATE_PER_MINUTE
    if user is not None and getattr(user, 'is_authenticated', False) and limit_per_min > 0:
        from ..models_assistant import AssistantMessage
        since = timezone.now() - timedelta(minutes=1)
        recent = AssistantMessage.objects.filter(
            session__user=user, role='user', created_at__gte=since,
        ).count()
        if recent >= limit_per_min:
            logger.info('助手限流：用户 %s 一分钟内已提问 %s 次', getattr(user, 'pk', '?'), recent)
            return GuardResult(ok=False, reason='rate_limited', detail=str(limit_per_min),
                               question=text)

    return GuardResult(ok=True, question=text)
