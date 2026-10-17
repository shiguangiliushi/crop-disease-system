"""
通知与公告模型（第 37 批）

背景：用户反馈的"通知与提醒"一块此前**完全不存在** ——
   · 帖子被人回复/点赞/收藏，作者收不到任何提示；
   · 没有站内通知中心；
   · 系统公告只能发成一条普通新闻。
（`views_forum.py` 里甚至留着一句 `self.send_like_notification(...)` 死调用，
  说明当初想做但没做，第 35 批已把那个必然 500 的调用移除。）

设计取舍：
  · `Notification` 是**每人一条**的收件箱记录（被回复/被点赞/被收藏/系统公告）；
    外键用 SET_NULL，删帖删评论不会连带删掉通知（否则用户的消息列表会莫名少东西）。
  · `Announcement` 是管理员发布的公告本体；发布时给全体用户各投递一条 Notification，
    这样铃铛里能看到、也能点进公告详情。用户量很大时应改成就读时合并，当前规模（个位数账号）直接扇出即可。
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """站内通知（收件箱）"""

    TYPE_CHOICES = (
        ('reply', '有人回复了你'),
        ('like', '有人点赞了你'),
        ('favorite', '有人收藏了你'),
        ('comment_like', '有人点赞了你的评论'),
        ('follow', '有人关注了你'),  # 第 40 批：关注/粉丝
        ('message', '有人给你发了私信'),  # 第 42 批：私信
        ('announcement', '系统公告'),
        ('system', '系统消息'),
        #: ⚠️ 第 224 批：反馈回复原来借用 `system`（显示成「系统消息」）；
        #: 反馈是**人和人之间**的往来，和系统通知混在一起会让用户找不到。
        ('feedback', '反馈回复'),
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='notifications', verbose_name='接收人',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sent_notifications', verbose_name='触发人',
    )
    type = models.CharField('类型', max_length=20, choices=TYPE_CHOICES, default='system')
    title = models.CharField('标题', max_length=200)
    # 第 72 批：通知标题/摘要由后端拼装（如"xxx 回复了你的帖子：yyy"），
    # 英文界面下必须给出英文版本，否则通知列表整块是中文。
    title_en = models.CharField('标题（英文）', max_length=200, blank=True, default='')
    message = models.CharField('内容摘要', max_length=500, blank=True, default='')
    message_en = models.CharField('内容摘要（英文）', max_length=500, blank=True, default='')

    # 跳转目标：前端路径（如 /forum/post/12），点通知直接过去
    url = models.CharField('跳转地址', max_length=300, blank=True, default='')

    # 关联对象（可为空：删帖后通知仍保留）
    post = models.ForeignKey(
        'api.Post', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notifications', verbose_name='相关帖子',
    )
    comment = models.ForeignKey(
        'api.Comment', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notifications', verbose_name='相关评论',
    )
    announcement = models.ForeignKey(
        'api.Announcement', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notifications', verbose_name='相关公告',
    )

    is_read = models.BooleanField('已读', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '通知'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f'{self.recipient_id} ← {self.get_type_display()}: {self.title}'


class Announcement(models.Model):
    """系统公告（管理员发布，可置顶、可设过期时间）"""

    title = models.CharField('标题', max_length=200)
    content = models.TextField('正文')
    is_active = models.BooleanField('是否生效', default=True)
    is_pinned = models.BooleanField('置顶', default=False)
    #: 为空表示长期有效
    expires_at = models.DateTimeField('过期时间', null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='announcements', verbose_name='发布人',
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '系统公告'
        verbose_name_plural = verbose_name
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return self.title

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def is_visible(self):
        return self.is_active and not self.is_expired
