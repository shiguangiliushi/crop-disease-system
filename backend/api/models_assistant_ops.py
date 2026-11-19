"""系统助手（管理端运维侧）的观测表。

## 为什么只有**一张**表，而且它不是"会话存储"

农户侧的 RAG 助手建了三张表（`models_assistant.py` 的 Session / Message / 引用 JSON），
因为那边要"会话列表 + 跨设备续聊 + 引用可点开"。运维侧三条都不成立：

  · 管理员只有一两个人，没有"会话列表"这种需求；
  · 上下文由前端持 `history`（最多 4 轮），服务端不需要读回来；
  · 引用是**工具返回值**，随答案一起返回即可，不需要按词条/文件去查"被引用过几次"。

所以这里的表只干一件事：**把这次问答的现场留下来**，好在事后回答
"最近系统助手的答案是不是变差了、哪一类意图答不上来"。这与 `AssistantMessage`
的 `degraded` / `latency_ms` / `usage` 是同一个用途，不是同一个对象。

## 为什么 `verified` 要单独一列

它与 `degraded` 是**两件不同的事**（与第 204 批把 `truncated` 从 `degraded` 里拆出来同理）：

  · `degraded=True` —— 没调模型，或调了但失败，答案是模板拼的；
  · `verified=False` —— 模型答了，但答案里的数字在工具返回值里找不到（可能编造）。

用户看到的都是"这答案不可信"，成因却完全不同：前者要查 provider，
后者要查提示词或工具返回。混成一列，排查时必然走错方向。

## 为什么不复用 `AssistantSession`

那个表带着 `pest` / `detection` / `consult_question` 三个字段，对运维会话恒为空；
而农户侧所有查询都要额外加 `scope` 过滤 —— 漏一处就会出现
"农户在自己的会话列表里看见管理员问的『数据库连不上怎么办』"。
这与第 193 批"不复用 `Conversation`（私信）"是同一条理由，不是洁癖。
"""
from __future__ import annotations

from django.conf import settings as django_settings
from django.db import models


class OpsAssistantTurn(models.Model):
    """系统助手的一次问答（一问一答一行）"""

    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='ops_assistant_turns', verbose_name='提问人',
    )
    question = models.TextField('问题')
    answer = models.TextField('答案', blank=True, default='')
    #: 组合意图写成 `health+howto`（与 `ops/intent.py` 的返回值一致）
    intent = models.CharField('意图', max_length=40, blank=True, default='')
    #: [{'name': 'get_system_health', 'ok': True, 'ms': 120, 'error': ''}]
    #: 只留"调了什么、成不成、多久"，**不留返回值** —— 返回值里有部署细节，
    #: 已经有脱敏后的答案与 evidence 可查，没必要再存一份原始数据。
    tool_calls = models.JSONField('工具调用', default=list, blank=True)
    degraded = models.BooleanField('是否降级', default=False)
    degrade_reason = models.CharField('降级原因', max_length=30, blank=True, default='')
    #: 答案里的数字是否**全部**能在工具返回值里找到（见 `ops/verify.py`）
    verified = models.BooleanField('数字已校验', default=True)
    latency_ms = models.PositiveIntegerField('耗时（毫秒）', default=0)
    usage = models.JSONField('token 用量', default=dict, blank=True)
    model = models.CharField('实际使用的模型', max_length=60, blank=True, default='')
    created_at = models.DateTimeField('时间', auto_now_add=True)

    class Meta:
        verbose_name = '系统助手问答'
        verbose_name_plural = verbose_name
        ordering = ['-created_at', '-id']
        indexes = [
            # 限流与"最近几天"都按时间倒序查
            models.Index(fields=['-created_at'], name='ops_turn_time_idx'),
            # 统计"哪类意图答不上来"要按 intent 分组
            models.Index(fields=['intent', '-created_at'], name='ops_turn_intent_idx'),
        ]

    def __str__(self):
        return f'{self.intent or "?"} · {(self.question or "")[:20]}'
