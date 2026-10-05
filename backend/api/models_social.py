"""
社交关系模型（第 40 批）：关注 / 粉丝

背景：清单里"用户关注/粉丝系统"此前完全没有 —— 既不能关注别人，
用户资料页也没有任何社交关系数据。

设计说明：
  · 单向关注（像微博/GitHub），不是好友申请制 —— 农业社区里"关注某位种植能手"
    是典型需求，双向确认会增加无谓的摩擦；
  · `unique_together(follower, following)` 保证不会重复关注（接口做成 toggle 幂等）；
  · 自关注在模型 `clean()` 与接口两层都拦（数据库约束写不了"两列不相等"这种条件，
    但接口层必须拦，否则会出现"自己出现在自己的粉丝里"）。
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Follow(models.Model):
    """关注关系：follower 关注了 following"""

    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='following_relations', verbose_name='关注者',
    )
    following = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='follower_relations', verbose_name='被关注者',
    )
    created_at = models.DateTimeField('关注时间', auto_now_add=True)

    class Meta:
        verbose_name = '关注关系'
        verbose_name_plural = verbose_name
        unique_together = ('follower', 'following')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['following', '-created_at']),
            models.Index(fields=['follower', '-created_at']),
        ]

    def __str__(self):
        return f'{self.follower_id} → {self.following_id}'

    def clean(self):
        if self.follower_id and self.following_id and self.follower_id == self.following_id:
            raise ValidationError('不能关注自己')
