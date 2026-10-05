"""
私信模型（第 42 批）

背景：清单里"私信功能"此前完全没有 —— 用户之间只能靠公开回帖交流，
想私下问一句（比如留个联系方式、发个地块照片）没有办法。

设计说明：
  · 不做"会话表 + 成员表"那套重模型 —— 一对一私信直接用 `conversation_key`
    （两人的用户 id 排序后拼成 `min_max`）把消息归到同一个会话里，
    查会话列表时按这个键分组即可，实现简单且够用；
  · `is_read` 只标记"收件人是否已读"，配合 `/with/<user_id>/` 打开即标记已读；
  · 删除是**双方各自软删**（`sender_deleted` / `recipient_deleted`），
    一个人删掉不该让另一个人也看不到。
"""
from django.conf import settings
from django.db import models


def conversation_key_for(user_a_id, user_b_id):
    """把两个人的会话归一到同一个键（与谁发给谁无关）"""
    low, high = sorted([int(user_a_id), int(user_b_id)])
    return f'{low}_{high}'


class DirectMessage(models.Model):
    """一对一私信"""

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='messages_sent', verbose_name='发件人',
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='messages_received', verbose_name='收件人',
    )
    content = models.TextField('内容', max_length=1000)

    #: 两人的会话键（小 id 在前），用于把消息归到同一个会话
    conversation_key = models.CharField('会话键', max_length=32, db_index=True)

    is_read = models.BooleanField('收件人已读', default=False)
    read_at = models.DateTimeField('已读时间', null=True, blank=True)

    # 双方各自软删除
    sender_deleted = models.BooleanField('发件人已删除', default=False)
    recipient_deleted = models.BooleanField('收件人已删除', default=False)

    created_at = models.DateTimeField('发送时间', auto_now_add=True)

    class Meta:
        verbose_name = '私信'
        verbose_name_plural = verbose_name
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation_key', 'created_at']),
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f'{self.sender_id} → {self.recipient_id}: {self.content[:20]}'

    def save(self, *args, **kwargs):
        if not self.conversation_key and self.sender_id and self.recipient_id:
            self.conversation_key = conversation_key_for(self.sender_id, self.recipient_id)
        super().save(*args, **kwargs)
