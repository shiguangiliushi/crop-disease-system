"""
等级与积分（第 42 批）

背景：清单里"用户等级/积分系统"此前完全没有。

设计说明：
  · `CustomUser.points` 存**当前总积分**（冗余字段，列表/资料页直接读，避免每次聚合日志）；
  · `PointLog` 记每一笔变动（谁、加/减多少、因为什么、关联对象），
    既方便用户看"我的积分怎么来的"，也方便出问题时追溯；
  · 等级由积分阈值推导（`LEVELS`），不额外存字段 —— 改规则时不用刷数据。

积分规则（见 `POINT_RULES`，与产品约定一致）：
    发帖 +5、评论 +2、被点赞 +1、被收藏 +2、被关注 +1、每日首次登录 +1。
"""
from django.conf import settings
from django.db import models

#: 等级阈值（从高到低匹配；改这里即可调整等级体系）
#: 第 79 批：补英文等级名。等级是**固定枚举**（不是用户输入），
#: 英文界面下原来一直显示「Lv.1 新手」，所以中英各给一份，由接口下发两版。
LEVELS = (
    (5, 1000, '种植大师', 'Master Grower'),
    (4, 600, '农技专家', 'Crop Expert'),
    (3, 300, '种植老手', 'Seasoned Grower'),
    (2, 100, '进阶农户', 'Advanced Grower'),
    (1, 0, '新手', 'Novice'),
)

#: 等级中文名 → 英文名（按等级号索引，供 level_for_points 之外的场景使用）
LEVEL_NAMES_EN = {level: name_en for level, _threshold, _name, name_en in LEVELS}

#: 积分规则（`reason` → (分值, 说明)）
POINT_RULES = {
    'post': (5, '发布帖子'),
    'comment': (2, '发表评论'),
    'like_received': (1, '帖子被点赞'),
    'favorite_received': (2, '帖子被收藏'),
    'follow_received': (1, '被关注'),
    'daily_login': (1, '每日登录'),
    'admin_adjust': (0, '管理员调整'),
}


def level_for_points(points):
    """由积分推导等级，返回 (level, name, next_threshold 或 None)"""
    value = int(points or 0)
    for level, threshold, name, _name_en in LEVELS:
        if value >= threshold:
            # 下一个等级的阈值（用于进度条）
            higher = [(lv, th) for lv, th, _n, _e in LEVELS if th > threshold]
            next_threshold = min(higher, key=lambda item: item[1])[1] if higher else None
            return level, name, next_threshold
    return 1, '新手', None


class PointLog(models.Model):
    """积分变动流水"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='point_logs', verbose_name='用户',
    )
    delta = models.IntegerField('变动值')  # 可正可负
    balance = models.IntegerField('变动后积分', default=0)
    reason = models.CharField('原因', max_length=32)
    #: 展示用的一句话（如"发布帖子 +5"）
    description = models.CharField('说明', max_length=120, blank=True, default='')
    #: 关联对象（帖子/评论 id 之类），便于追溯
    ref_type = models.CharField('关联类型', max_length=20, blank=True, default='')
    ref_id = models.IntegerField('关联 id', null=True, blank=True)
    created_at = models.DateTimeField('时间', auto_now_add=True)

    class Meta:
        verbose_name = '积分流水'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', '-created_at'])]

    def __str__(self):
        return f'{self.user_id} {self.delta:+d}（{self.reason}）'
