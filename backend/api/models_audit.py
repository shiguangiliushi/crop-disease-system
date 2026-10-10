"""
管理操作日志（第 146 批）

## 为什么要有它

在此之前，管理端的敏感动作（停用/恢复账号、改角色、开通编辑员、删用户、
批量删反馈、版块启停与排序、敏感词增删…）**只写 `logger.info`**：
   · 日志文件会轮转、会丢，翻旧账靠 grep；
   · 出事后没法回答"这条是**谁**、**什么时候**、**改成了什么**"；
   · 更没法做界面展示或按操作人筛选。

这一批把这些动作落进一张表，并且刻意做了两个设计（都是"不这么做就会后悔"的类型）：

1. **存快照（actor_repr / target_repr），不只存外键**
   `actor` 用 `SET_NULL`：账号真被删了，日志不能跟着消失。
   但只留一个空外键的话，日志就变成"某人对某人做了某事" —— 谁也读不懂。
   所以写日志时把**当时的用户名/标题**一并存进 `*_repr` 字段。

2. **绝不记录凭证**
   重置密码链接里带着一次性 token —— 把整条链接写进日志，等于把凭证抄进了数据库
   （谁有读权限谁就能改别人的密码）。所以这类动作的 detail 只写"已签发（1 小时有效）"。
   测试里有一条断言专门盯这个（`test_reset_link_token_is_not_logged`）。

读取入口有两个：Django admin（只读、可搜索筛选）与 `GET /api/admin/audit-logs/`
（仅全权管理员）。
"""
from django.conf import settings
from django.db import models


class AdminAuditLog(models.Model):
    """一条管理操作记录"""

    #: 常用动作取值（`域.动作`，便于筛选与统计）
    ACTION_CHOICES = (
        ('user.suspend', '停用账号'),
        ('user.restore', '恢复账号'),
        ('user.role_change', '调整角色'),
        ('user.create_editor', '开通编辑员'),
        ('user.delete', '删除账号'),
        ('user.bulk_delete', '批量删除账号'),
        ('user.reset_link', '签发密码重置链接'),
        ('feedback.bulk_status', '批量流转反馈状态'),
        ('feedback.bulk_delete', '批量删除反馈'),
        ('board.create', '新建版块'),
        ('board.update', '编辑版块'),
        ('board.set_status', '版块启停'),
        ('board.update_order', '版块排序'),
        ('word.create', '新增敏感词'),
        ('word.delete', '删除敏感词'),
        ('announcement.create', '发布公告'),
        ('announcement.delete', '删除公告'),
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='audit_logs', verbose_name='操作人',
    )
    #: 操作人用户名**快照**（账号被删后仍能读懂）
    actor_repr = models.CharField('操作人（快照）', max_length=150, blank=True, default='')

    action = models.CharField('动作', max_length=40, db_index=True, choices=ACTION_CHOICES)
    #: 目标类型（user / feedback / board / word / announcement）
    target_type = models.CharField('目标类型', max_length=40, blank=True, default='')
    target_id = models.CharField('目标 ID', max_length=40, blank=True, default='')
    #: 目标名称/标题**快照**（同上：目标改名或删除后日志仍可读）
    target_repr = models.CharField('目标（快照）', max_length=200, blank=True, default='')

    #: 补充说明（**不要放凭证**：重置链接的 token、密码、密钥都不许进这里）
    detail = models.TextField('说明', blank=True, default='')
    ip = models.GenericIPAddressField('来源 IP', null=True, blank=True)
    created_at = models.DateTimeField('时间', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = '管理操作日志'
        verbose_name_plural = verbose_name
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['actor', '-created_at']),
        ]

    def __str__(self):
        return f'{self.actor_repr or "系统"} {self.get_action_display()} {self.target_repr}'
