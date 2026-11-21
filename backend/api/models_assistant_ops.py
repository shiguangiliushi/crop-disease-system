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


class OpsPendingWrite(models.Model):
    """一条**待确认的不可逆写**（第 425 批）。

    ## 为什么这件事必须落库，而不是留在 agent 的会话状态里

    确认要跨两次 HTTP 请求（提议一轮、确认一轮）。若把"待确认"存在进程内存或
    图编排的 checkpointer 里，gunicorn 起多个 worker 时会出现：**提议落在 A 进程，
    确认请求进了 B 进程** —— 表现是"点了确认没反应"，而且进程重启后静默丢失，
    没人知道曾经请求过一条删除。

    落库还多出两件内存方案给不了的东西：

      · 管理员能在 `AdminAuditLog` 旁边看见"有一条操作卡在待确认"（可查询、可排查）；
      · 事故复盘时能回答"谁在什么时候提议删了什么、谁确认的、执行了没有"。

    ## 一行只被消费一次

    `consume()` 用 `UPDATE ... WHERE status='pending'` 的**返回值**判断是否抢到，
    不写"先 SELECT 再 save"。双击、两个页签同时点、重放请求三种情况，
    只有前者能挡住重复执行 —— 而重复执行在不可逆操作上等于二次删除。

    ## 为什么记 `args` 快照而不是重新问模型

    执行阶段没有模型参与（确认环节不能交给模型，见
    `docs/系统助手不可逆写状态机方案.md` 第五节）。执行只用这一行里的
    `action` + `args`，并且**再走一次 `actions.validate()`** 才落库 ——
    中间这段时间目标可能已被删掉、管理员可能已被降权。
    """

    STATUS = (
        ('pending', '待确认'),
        ('confirmed', '已确认'),
        ('cancelled', '已取消'),
        ('expired', '已过期'),
        ('failed', '执行失败'),
    )

    #: 凭据。**不可猜**（`uuid4().hex`），且是确认时的唯一依据 ——
    #: 不用"最近一条待确认"这种隐式指针，那会让两个管理员/两个页签互相串台。
    token = models.CharField('凭据', max_length=32, unique=True, db_index=True)
    #: `ops/actions.py` 的 `ACTIONS` 名字，执行前还要再核对一次白名单
    action = models.CharField('动作', max_length=64)
    #: `actions.validate()` 产出的**规范参数**（不是模型原始 arguments）
    args = models.JSONField('参数快照', default=dict)
    #: 人读目标："反馈 #12 番茄晚疫病"
    target = models.CharField('目标', max_length=200, blank=True, default='')
    #: 会改动的字段（提议时算好，执行时不再重算）
    changes = models.JSONField('会改动的字段', default=list, blank=True)
    status = models.CharField('状态', max_length=16, choices=STATUS,
                              default='pending', db_index=True)
    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='ops_pending_writes', verbose_name='提议人',
    )
    #: 提议时的管理员原话。确认时**重新校验要用它**："目标必须出自原话"这条不能跳
    question = models.TextField('提议时的原话', blank=True, default='')
    created_at = models.DateTimeField('提议时间', auto_now_add=True)
    #: 过期时间。过期后确认一律拒绝 —— 十分钟前的意图可能已经不是现在的意图
    expires_at = models.DateTimeField('过期时间', db_index=True)
    consumed_at = models.DateTimeField('消费时间', null=True, blank=True)

    class Meta:
        verbose_name = '系统助手待确认写操作'
        verbose_name_plural = verbose_name
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['user', 'status'], name='ops_pending_user_idx'),
            models.Index(fields=['status', 'expires_at'], name='ops_pending_exp_idx'),
        ]

    def __str__(self):
        return f'{self.action} · {self.target or "?"} · {self.status}'

    @property
    def is_open(self) -> bool:
        return self.status == 'pending'

