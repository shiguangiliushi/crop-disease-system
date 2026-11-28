"""游客试用的身份与额度（第 439 批）。

## 这个模块只做四件事

1. `create_guest()` —— 开一个临时用户并签发 token；
2. `consume()` —— 原子扣一次额度（识别 / 问答各一个计数器）；
3. `snapshot()` —— 剩余次数与重置时间（给前端画"还剩 N 次"）；
4. `purge()` —— 删掉 N 天没动过的游客账号（配套 `manage.py prune_guests`）。

## 三条设计约束（每一条都对应一个会真实发生的坑）

**① 额度必须落库，不能只靠限流。**
`settings.py` 里写明：生产环境没配 `DJANGO_CACHE_URL` 时缓存回落到 **LocMemCache**，
而 LocMem 是**进程内**的 —— gunicorn 起 N 个 worker，"3 次/天"就等于 N×3 次，
并且**没有任何报错**。所以权威计数在 `GuestTrialQuota` 表里。

**② 额度按 IP，不按 token。**
游客身份是随手可重建的（清 localStorage 再进一次就是新 token）。
只有把额度钉在 IP 上，"换身份"才不等于"换额度"。

**③ 扣减必须是一条 UPDATE。**
`先查再改` 在双击 / 重放 / 两个标签页同时点的情况下必然多扣或少扣。
这里用的是和 `OpsPendingWrite.consume()` 同一个套路：
`UPDATE ... WHERE detects < 上限`，`rowcount == 0` 就是"额度已用完"。
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from .audit import _client_ip as _request_ip  # 与审计日志同一个取 IP 口径（含 X-Forwarded-For）
from .models import CustomUser
from .models_guest import GuestTrialQuota
from .models_token import DeviceToken

#: 业务名 → 表里的计数器字段名
COUNTER_FIELD = {'detect': 'detects', 'ask': 'asks'}

#: 默认额度（可在 settings.GUEST_TRIAL 覆盖，见 settings.py）
DEFAULTS = {'enabled': True, 'detect_per_day': 3, 'ask_per_day': 5}


def config() -> dict:
    """读配置。**每次调用都读 settings**，不要在模块级缓存 —— 测试要能改它。"""
    cfg = getattr(settings, 'GUEST_TRIAL', None) or {}
    merged = {**DEFAULTS, **{k: v for k, v in cfg.items() if v is not None}}
    return {
        'enabled': bool(merged['enabled']),
        'detect': int(merged['detect_per_day']),
        'ask': int(merged['ask_per_day']),
    }


def limit_of(kind: str) -> int:
    return config()[kind]


def is_guest(user) -> bool:
    """是不是游客账号（AnonymousUser 也返回 False）。"""
    return bool(getattr(user, 'is_guest', False))


def ip_hash(request) -> str:
    """IP 的不可逆短哈希。

    为什么加 `SECRET_KEY`：不加盐的 IP 哈希可以被穷举还原（IPv4 空间只有 2^32），
    那这张表就等于存了明文 IP。
    """
    ip = _request_ip(request) or 'unknown'
    return hashlib.sha256(f'{settings.SECRET_KEY}:{ip}'.encode('utf-8')).hexdigest()[:16]


def today():
    """按项目时区算自然日（`TIME_ZONE`，不是 UTC —— 否则"今天"会在早上 8 点换日）。"""
    return timezone.localdate()


def reset_at():
    """额度重置时刻 = 明天 00:00（同一时区）。给前端显示"明天 0 点重置"。"""
    now = timezone.localtime()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return tomorrow


def _row(request, *, create=False):
    key, day = ip_hash(request), today()
    if create:
        GuestTrialQuota.objects.get_or_create(ip_hash=key, day=day)
        return GuestTrialQuota.objects.filter(ip_hash=key, day=day).first()
    return GuestTrialQuota.objects.filter(ip_hash=key, day=day).first()


def used(kind: str, request) -> int:
    row = _row(request)
    return getattr(row, COUNTER_FIELD[kind]) if row else 0


def remaining(kind: str, request) -> int:
    return max(limit_of(kind) - used(kind, request), 0)


def consume(kind: str, request) -> tuple[bool, int]:
    """扣一次额度。返回 `(是否放行, 扣完之后的剩余次数)`。

    放行与否只看那条 `UPDATE` 的 `rowcount` —— 不看"我刚才读到的值"。
    """
    if kind not in COUNTER_FIELD:
        raise ValueError(f'未知的试用类型: {kind!r}')
    field = COUNTER_FIELD[kind]
    limit = limit_of(kind)
    key, day = ip_hash(request), today()

    # 行不存在就先建（并发下可能两个请求同时走到，get_or_create 已经处理了竞争）
    GuestTrialQuota.objects.get_or_create(ip_hash=key, day=day)

    updated = (GuestTrialQuota.objects
               .filter(ip_hash=key, day=day, **{f'{field}__lt': limit})
               .update(**{field: F(field) + 1}))
    return bool(updated), remaining(kind, request)


def refund(kind: str, request) -> None:
    """把一次没用上的额度还回去（例如识别服务 503、根本没跑推理）。

    用 `F() - 1` 并且 `filter(field__gt=0)`：并发下最多还到 0，不会出现负数。
    """
    field = COUNTER_FIELD.get(kind)
    if not field:
        return
    GuestTrialQuota.objects.filter(**{
        'ip_hash': ip_hash(request), 'day': today(), f'{field}__gt': 0,
    }).update(**{field: F(field) - 1})


def snapshot(request, user=None) -> dict:
    """给前端的额度快照。登录用户不需要额度，返回 `unlimited`。

    `user` 参数是给"刚建出来、还没挂到 request 上"的场景用的
    （`POST /api/guest/session/` 里 `request.user` 还是匿名用户，不能拿它判身份）。
    """
    user = user if user is not None else getattr(request, 'user', None)
    payload = {
        'is_guest': is_guest(user),
        'unlimited': not is_guest(user),
        'resets_at': reset_at().isoformat(),
    }
    if payload['unlimited']:
        payload.update({'detect_left': None, 'ask_left': None,
                        'detect_limit': None, 'ask_limit': None})
        return payload
    payload.update({
        'detect_left': remaining('detect', request),
        'ask_left': remaining('ask', request),
        'detect_limit': limit_of('detect'),
        'ask_limit': limit_of('ask'),
    })
    return payload


def create_guest(device: str = 'web') -> tuple['CustomUser', 'DeviceToken']:
    """开一个临时游客身份。

    - `set_unusable_password()`：这张账号**永远不可能被登录**（不是"密码很复杂"，是不可用）；
    - 用户名带随机后缀：不可枚举，也不会和真实用户重名；
    - `is_guest=True`：统计口径、写权限闸门、清理任务都靠它；
    - `device`：与登录同口径（web / mobile / app），只影响"同设备旧 token 轮换"，
      这里没有轮换需求，保留是为了日志里能看出请求来自哪一端。
    """
    user = CustomUser(
        username=f'guest_{uuid.uuid4().hex[:10]}',
        email='',
        role='USER',
        is_guest=True,
    )
    user.set_unusable_password()
    user.save()
    token = DeviceToken.issue(user, device=device)
    return user, token


def purge(older_than_days: int, *, dry_run: bool = True) -> dict:
    """删掉"超过 N 天没有任何活动"的游客账号。

    "活动"取 `DeviceToken.last_seen` 的最大值（每次带 token 请求都会刷新它）。
    删除是 CASCADE：识别历史、助手会话/消息、设备 token 一起走，**不需要手写级联** ——
    前提是 `models_guest` 被 `models.py` 导入过，否则收集器不知道还有这张表。
    """
    from django.db.models import Max

    cutoff = timezone.now() - timedelta(days=max(int(older_than_days), 0))
    guests = (CustomUser.objects
              .filter(is_guest=True)
              .annotate(last_seen=Max('device_tokens__last_seen')))
    stale = [u for u in guests if not u.last_seen or u.last_seen < cutoff]

    result = {'candidates': len(stale), 'deleted': 0, 'dry_run': bool(dry_run)}
    if dry_run or not stale:
        return result

    for user in stale:
        user.delete()
        result['deleted'] += 1
    return result
