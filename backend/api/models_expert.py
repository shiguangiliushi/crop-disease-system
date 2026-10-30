"""
专家咨询模型（第 49 批）

背景：清单里"专家咨询"此前没有。论坛是**开放讨论**（谁都能发、谁都能答），
而"咨询"需要的是：**能指定专家回答、能采纳一个最佳答案、有明确的问答状态**。
所以这里单独建一套轻量问答模型，但**复用**已有的通知体系与敏感词校验，
不重复造轮子。

三个模型：
  · `ExpertProfile`  —— 谁被认定为专家（管理员授予），带职称/擅长领域；
  · `ConsultQuestion` —— 用户提问（作物、标题、内容、可选图片、状态）；
  · `ConsultAnswer`  —— 专家/管理员作答，可有且仅有一个被提问者采纳。

状态机：`open`（待回答）→ `answered`（有专家回答）→ `closed`（已关闭）；
提问者采纳某个回答时置为 `answered` 并记录 `accepted_answer`。
"""
from django.conf import settings
from django.db import models
from .storage_private import signed_media_storage  # 第 259 批：私有图自动签名


class ExpertProfile(models.Model):
    """专家身份（由管理员授予）"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='expert_profile', verbose_name='用户',
    )
    title = models.CharField('职称/头衔', max_length=80, blank=True, default='')
    #: 擅长领域，逗号分隔（如"番茄,草莓,设施栽培"）
    specialties = models.CharField('擅长领域', max_length=200, blank=True, default='')
    bio = models.TextField('简介', blank=True, default='')
    is_active = models.BooleanField('在岗', default=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='granted_experts', verbose_name='授予人',
    )
    created_at = models.DateTimeField('授予时间', auto_now_add=True)

    class Meta:
        verbose_name = '专家'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username}（{self.title or "专家"}）'

    @property
    def specialty_list(self):
        return [item.strip() for item in (self.specialties or '').replace('，', ',').split(',') if item.strip()]


class ConsultQuestion(models.Model):
    """咨询提问"""

    STATUS_CHOICES = (
        ('open', '待回答'),
        ('answered', '已解答'),
        ('closed', '已关闭'),
    )

    asker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='consult_questions', verbose_name='提问者',
    )
    crop_type = models.CharField('作物', max_length=100, blank=True, default='', db_index=True)
    title = models.CharField('问题标题', max_length=200)
    content = models.TextField('问题描述')
    image = models.ImageField(upload_to='consult_images/', blank=True, null=True,
                              storage=signed_media_storage, verbose_name='配图')

    status = models.CharField('状态', max_length=10, choices=STATUS_CHOICES, default='open')
    accepted_answer = models.ForeignKey(
        'ConsultAnswer', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='accepted_for', verbose_name='已采纳回答',
    )
    answer_count = models.PositiveIntegerField('回答数', default=0)
    view_count = models.PositiveIntegerField('浏览数', default=0)

    created_at = models.DateTimeField('提问时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    last_answer_at = models.DateTimeField('最近回答时间', null=True, blank=True)

    class Meta:
        verbose_name = '咨询提问'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['asker', '-created_at']),
        ]

    def __str__(self):
        return f'{self.crop_type}·{self.title}'

    def refresh_answer_stats(self):
        """重算回答数（避免每次聚合）"""
        self.answer_count = self.answers.count()
        latest = self.answers.order_by('-created_at').values_list('created_at', flat=True).first()
        self.last_answer_at = latest
        if self.answer_count and self.status == 'open':
            self.status = 'answered'
        self.save(update_fields=['answer_count', 'last_answer_at', 'status', 'updated_at'])


class ConsultAnswer(models.Model):
    """专家回答"""

    question = models.ForeignKey(
        ConsultQuestion, on_delete=models.CASCADE, related_name='answers', verbose_name='问题',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='consult_answers', verbose_name='回答人',
    )
    content = models.TextField('回答内容')
    #: 回答时的身份快照（专家职称），回答之后即使撤销专家身份也保留当时的头衔
    author_title = models.CharField('回答时头衔', max_length=80, blank=True, default='')
    is_accepted = models.BooleanField('已采纳', default=False)
    created_at = models.DateTimeField('回答时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '咨询回答'
        verbose_name_plural = verbose_name
        ordering = ['-is_accepted', 'created_at']

    def __str__(self):
        return f'{self.author.username} → {self.question_id}'
