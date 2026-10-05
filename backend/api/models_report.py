"""
举报模型（第 41 批）

背景：清单里"举报功能"此前完全没有 —— 用户看到广告/辱骂/与农业无关的内容，
除了在评论区吵架没有别的办法；管理员也无从知道哪些内容被用户反感。

设计说明：
  · 一个模型覆盖三类举报对象（帖子 / 评论 / 用户），用 `target_type` + 各自的可空外键，
    这样"谁举报了什么"在一条记录里就能看全，不必拆三张表；
  · `target_key`（如 `post:12`）是冗余出来的稳定标识，用于**同一用户对同一目标只能举报一次**
    （涉及可空外键时 `unique_together` 并不能可靠去重）；
  · 处理结果 `status`（待处理 / 已处理 / 已驳回）+ `handle_note` + 处理人/时间，
    并会给举报人发站内通知 —— 举报"有回音"才有人愿意继续举报。
"""
from django.conf import settings
from django.db import models


class Report(models.Model):
    """举报"""

    TARGET_CHOICES = (
        ('post', '帖子'),
        ('comment', '评论'),
        ('user', '用户'),
    )

    REASON_CHOICES = (
        ('spam', '广告/推广'),
        ('abuse', '辱骂/攻击'),
        ('politics', '违规内容'),
        ('irrelevant', '与农业无关'),
        ('other', '其它'),
    )

    STATUS_CHOICES = (
        ('pending', '待处理'),
        ('handled', '已处理'),
        ('rejected', '已驳回'),
    )

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='reports_made', verbose_name='举报人',
    )
    target_type = models.CharField('举报对象类型', max_length=10, choices=TARGET_CHOICES)
    #: 冗余的稳定标识（post:12 / comment:34 / user:5），用于去重
    target_key = models.CharField('举报对象标识', max_length=64, db_index=True)

    post = models.ForeignKey(
        'api.Post', on_delete=models.CASCADE, null=True, blank=True, related_name='reports',
    )
    comment = models.ForeignKey(
        'api.Comment', on_delete=models.CASCADE, null=True, blank=True, related_name='reports',
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
        related_name='reports_received',
    )

    reason = models.CharField('举报理由', max_length=20, choices=REASON_CHOICES, default='other')
    detail = models.TextField('补充说明', blank=True, default='')

    status = models.CharField('处理状态', max_length=10, choices=STATUS_CHOICES, default='pending')
    handler = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reports_handled', verbose_name='处理人',
    )
    handle_note = models.CharField('处理说明', max_length=300, blank=True, default='')
    handled_at = models.DateTimeField('处理时间', null=True, blank=True)

    created_at = models.DateTimeField('举报时间', auto_now_add=True)

    class Meta:
        verbose_name = '举报'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        # 同一用户对同一目标只能举报一次（防刷；真正的去重靠 target_key）
        unique_together = ('reporter', 'target_key')
        indexes = [
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f'{self.reporter_id} 举报 {self.target_key}（{self.get_status_display()}）'

    @property
    def target_label(self):
        """给管理端展示的一句话描述"""
        if self.post_id and self.post:
            return f'帖子：{self.post.title}'
        if self.comment_id and self.comment:
            content = (self.comment.content or '')[:30]
            return f'评论：{content}'
        if self.target_user_id and self.target_user:
            return f'用户：{self.target_user.username}'
        return '（内容已删除）'
