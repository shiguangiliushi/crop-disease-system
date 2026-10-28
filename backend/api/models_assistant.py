"""智能回答助手的数据模型（第 193 批，K5）。

## 三张表 → 两张表：为什么合并了 `AssistantCitation`

框架文档（`docs/智能回答助手框架.md` 第三节）原本设计三张表，其中 `AssistantCitation`
独立成表。实现时改成 `AssistantMessage.citations` 一个 JSONField，理由：

  · **引用永远是"整条消息的一部分"** —— 没有任何场景需要"跨消息查某条词条被引用了多少次"。
    没有独立查询需求，就没有建表的理由（建了只会多一次 JOIN 与一次写入）；
  · 引用是**生成结果的快照**：词条日后被改，历史回答引用的仍是当时那段文字。
    独立成表并用外键指向 `PestInfo` 反而会让人误以为"引用会跟着词条更新"。

同样把 `usage`（prompt/completion tokens）也放进 JSONField：它只用于事后统计，
不需要被 WHERE 过滤。但 `degraded` / `latency_ms` **留成独立列** ——
排查"回答质量差"时要按它们筛选（"所有降级的回答"是最常用的查询）。

## 与 `ConsultQuestion`（专家咨询）的关系

兜底转人工时**写既有的 `ConsultQuestion`**，不另建工单表 ——
人工专家那条链路（`models_expert.py`）已经完整，助手只是它的一个入口。
"""
from __future__ import annotations

from django.conf import settings as django_settings
from django.db import models


class AssistantSession(models.Model):
    """一次连续对话。一个用户可以有很多个。"""

    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='assistant_sessions', verbose_name="用户",
    )
    title = models.CharField(max_length=80, blank=True, default='', verbose_name="会话标题")
    #: 从识别结果页进来时绑定：让"这个病"在整段会话里都作为检索锚点
    pest = models.ForeignKey(
        'PestInfo', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='assistant_sessions', verbose_name="关联病害",
    )
    detection = models.ForeignKey(
        'DetectionHistory', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='assistant_sessions', verbose_name="关联识别记录",
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    #: 是否已转人工（写进 ConsultQuestion 之后置 True，避免重复建单）
    escalated_at = models.DateTimeField('转人工时间', null=True, blank=True)
    #: 转人工产生的工单。**一拍一**（`OneToOneField`）：一次会话只该有一张工单 ——
    #: 用 FK 的话"点了两次转人工"会建出两张，专家看到重复问题。
    #: 方向是从会话指向工单（`models_expert` 不需要知道助手的存在）。
    consult_question = models.OneToOneField(
        'ConsultQuestion', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='assistant_session', verbose_name='转人工工单',
    )

    class Meta:
        verbose_name = "助手会话"
        verbose_name_plural = verbose_name
        indexes = [
            # 会话列表的唯一查询形态：按用户 + 最近活跃倒序
            models.Index(fields=['user', '-updated_at'], name='asst_session_user_idx'),
        ]

    def __str__(self):
        return f'{self.user_id}-{self.title or "未命名"}'


class AssistantMessage(models.Model):
    """一条消息。`role` 决定是用户说的还是助手说的。"""

    ROLE_CHOICES = (('user', '用户'), ('assistant', '助手'))

    session = models.ForeignKey(
        AssistantSession, on_delete=models.CASCADE,
        related_name='messages', verbose_name="会话",
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, verbose_name="角色")
    content = models.TextField(verbose_name="内容")
    #: 第 229 批：这条用户消息带了一张图片时，"看图的结论"一句话快照。
    #: 图片本身**不落盘**（见 `assistant/vision.py` 的说明：助手不是相册），但会话历史里
    #: 只留一个问题会让人莫名其妙 —— "我问了句'这张图怎么了'，图呢？"
    #: 存摘要而不是识别明细：明细（类名/置信度）进提示词与回答就够，重复存只会漂。
    image_summary = models.CharField(max_length=200, blank=True, default='', verbose_name="图片识别摘要")

    # ── 生成侧元数据（用户消息全为空/0）────────────────────────────────────
    model = models.CharField(max_length=60, blank=True, default='', verbose_name="实际使用的模型")
    #: True = 没走大模型（词条原文兜底 / 无来源 / 命中敏感词）
    degraded = models.BooleanField(default=False, verbose_name="是否降级")
    degrade_reason = models.CharField(max_length=30, blank=True, default='', verbose_name="降级原因")
    #: 答案是否被**长度上限**截断（端点回 `finish_reason == 'length'`）。第 204 批加。
    #: ⚠️ 与 `degraded` 是**两件不同的事**：降级是"没调用模型 / 调用失败"，
    #: 截断是"调用了模型、但它没说完"。用户看到的都是"这答案有问题"，
    #: 成因却完全不同 —— 分开记，否则事后排查会把两者混为一谈。
    truncated = models.BooleanField(default=False, verbose_name="回答是否被截断")
    latency_ms = models.PositiveIntegerField(default=0, verbose_name="耗时（毫秒）")
    #: 引用与用量都是**快照**，没有独立查询需求，所以放 JSON 而不建表（见模块 docstring）
    citations = models.JSONField(default=list, blank=True, verbose_name="引用来源")
    usage = models.JSONField(default=dict, blank=True, verbose_name="token 用量")
    prompt_version = models.CharField(max_length=20, blank=True, default='', verbose_name="提示词版本")
    #: 本条问答用的语言（`zh` / `en`）。第 197 批加：**英文回答的质量要能单独统计** ——
    #: 英文语料是后补的，混在一起看"整体满意度"会把英文侧的问题稀释掉。
    lang = models.CharField(max_length=5, blank=True, default='zh', verbose_name="回答语言")
    # ── 用户反馈（第 196 批）──────────────────────────────────────────────
    #: 用户对**这一条**回答的评价。放在消息上而不是会话上：一次会话里可能前几问答得好、
    #: 后几问答得差，只有逐条记才能定位"哪一类问题答不好"。
    verdict = models.CharField(
        max_length=10, blank=True, default='',
        choices=(('helpful', '有用'), ('useless', '没用')),
        verbose_name="用户评价",
    )
    #: `useless` 时用户补充的"哪里不对"（可选）。**这是最有价值的信号** ——
    #: 只统计"没用"的次数，无法知道该补什么内容。
    feedback_note = models.CharField(max_length=500, blank=True, default='', verbose_name="反馈说明")
    feedback_at = models.DateTimeField('反馈时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = "助手消息"
        verbose_name_plural = verbose_name
        indexes = [
            # 取某会话的消息：按主键正序就是时间正序（自增主键）
            models.Index(fields=['session', 'id'], name='asst_msg_session_idx'),
            # 限流要按 "某用户最近一分钟的用户消息数" 查，所以 role 与时间要能一起过滤
            models.Index(fields=['role', '-created_at'], name='asst_msg_role_time_idx'),
            # 统计"哪类回答被评没用"要按 verdict 过滤
            models.Index(fields=['verdict', '-created_at'], name='asst_msg_verdict_idx'),
        ]

    def __str__(self):
        return f'{self.session_id}-{self.role}-{self.content[:20]}'
