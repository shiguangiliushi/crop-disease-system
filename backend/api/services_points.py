"""
等级与积分（第 42 批）

`award_points()` 是业务代码唯一的入口：加分的同时写一条 `PointLog` 流水，
并把 `CustomUser.points` 冗余字段更新掉（列表/资料页直接读，不用聚合）。

接入点：
    · 发帖（PostViewSet.perform_create）      +5
    · 评论（CommentViewSet.perform_create）   +2
    · 帖子被点赞（PostViewSet.like）          +1（给作者）
    · 帖子被收藏（PostViewSet.favorite）      +2（给作者）
    · 被关注（FollowToggleView）              +1（给被关注者）
    · 每日首次登录（LoginView）               +1
"""
import logging

from django.db.models import F
from django.utils import timezone

from .models_points import POINT_RULES, PointLog, level_for_points

logger = logging.getLogger(__name__)


def award_points(user, reason, *, ref_type='', ref_id=None, description='', delta=None):
    """
    给用户加/减积分，并记录流水

    · `reason` 见 `POINT_RULES`；`delta` 不传时用规则里的分值；
    · 分值可能是 0（如管理员调整），仍然记账但不改余额；
    · 失败只记日志，绝不影响主流程（发帖/评论不该因为加分失败而失败）。
    """
    if user is None:
        return None

    rule_delta, rule_label = POINT_RULES.get(reason, (0, reason))
    value = rule_delta if delta is None else int(delta)
    label = description or f'{rule_label} {value:+d}'

    try:
        # 用 F() 原子更新，避免并发下丢失更新
        type(user).objects.filter(pk=user.pk).update(points=F('points') + value)
        user.refresh_from_db(fields=['points'])

        return PointLog.objects.create(
            user=user, delta=value, balance=user.points, reason=reason,
            description=label, ref_type=ref_type, ref_id=ref_id,
        )
    except Exception:
        logger.exception('记录积分失败 user=%s reason=%s', getattr(user, 'id', None), reason)
        return None


def award_daily_login(user):
    """每日首次登录 +1（同一天只加一次）"""
    if user is None:
        return None
    today = timezone.localdate()
    already = PointLog.objects.filter(
        user=user, reason='daily_login', created_at__date=today,
    ).exists()
    if already:
        return None
    return award_points(user, 'daily_login', description='每日登录 +1')


def points_summary(user):
    """给资料页用的汇总：积分、等级、下一级阈值、进度百分比"""
    points = int(getattr(user, 'points', 0) or 0)
    level, name, next_threshold = level_for_points(points)

    # 当前等级的下限（用于进度条起点）
    from .models_points import LEVEL_NAMES_EN, LEVELS
    current_floor = max((th for lv, th, _n, _e in LEVELS if lv == level), default=0)

    progress = 0
    if next_threshold:
        span = next_threshold - current_floor
        progress = int(min(100, max(0, (points - current_floor) / span * 100))) if span else 0
    else:
        progress = 100

    return {
        'points': points,
        'level': level,
        'level_name': name,
        # 第 79 批：英文等级名（英文界面下原来一直显示「Lv.1 新手」）
        'level_name_en': LEVEL_NAMES_EN.get(level, ''),
        'next_level_points': next_threshold,
        'progress': progress,
    }
