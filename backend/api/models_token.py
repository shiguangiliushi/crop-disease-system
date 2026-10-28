"""**每设备一张** API Token（第 231 批）—— 让手机与桌面能同时在线。

## 为什么要另起一张表

DRF 自带的 `authtoken.Token` 是 `OneToOneField(user)`：**一个用户只能有一张**。
而 `LoginView` 在第 94 批改成了"登录即轮换"（先 `delete()` 再 `create()`，配合 7 天过期），
于是**后登录的一端必然把另一端挤下线**：
手机登录 → 桌面那张被删 → 桌面下次请求 401 → 被踢回登录页；反之亦然。

这不是 bug，是"一张 token + 登录即轮换"的必然结果。要两端同时在线，就得让
"一个用户多张 token"，而 DRF 的模型做不到（改了它就等于放弃 DRF 的 Token 表）。

## 设计要点

- **按设备轮换**：登录只作废**同一设备**的旧 token（同设备重复登录仍然"旧凭证立即失效"），
  其它设备不受影响；
- **兼容旧凭证**：`DEFAULT_AUTHENTICATION_CLASSES` 先认本表、再退回 DRF `Token`
  （老客户端/老数据仍能登录，且大量既有测试不用改）；
- **全局吊销**：改密码 / 被停用 / 注销 / 管理员重置密码时，`revoke_all()` 把
  **两种 token 一起清掉** —— "换密码后所有设备重新登录"这条语义不能因为多端而放松；
- **过期仍由 middleware 统一判**（`TOKEN_EXPIRED_AFTER_SECONDS`）：models 都带 `created`。

## 设备标识从哪来

前端登录时带一个 `device` 字段（`web` / `mobile` / `app`）。**不传默认 `web`**：
老前端、脚本、E2E 都不用改；伪造 `device` 最多让"同一账号多占一张 token"，
拿不到任何额外权限（真正的边界仍是用户本身与 capabilities）。
"""
from __future__ import annotations

import binascii
import os

from django.conf import settings
from django.db import models
from django.utils import timezone

#: 认得的设备名（登录页/客户端传什么就用什么，不认识的归一成 web）
DEVICES = ('web', 'mobile', 'app')
DEFAULT_DEVICE = 'web'


def normalize_device(raw) -> str:
    """把客户端传来的 `device` 归一成 `DEVICES` 里的一个（不认识就当 web）。"""
    value = str(raw or '').strip().lower()
    for known in DEVICES:
        if value.startswith(known):
            return known
    return DEFAULT_DEVICE


def device_of(request) -> str:
    """从请求里取设备名：`device` 字段 > `X-Client-Device` 头 > 默认 web。"""
    if request is None:
        return DEFAULT_DEVICE
    try:
        payload = request.data
    except Exception:  # noqa: BLE001 —— 非 DRF 请求或解析失败时退回 header
        payload = None
    if isinstance(payload, dict) and payload.get('device'):
        return normalize_device(payload.get('device'))
    header = ''
    try:
        header = request.META.get('HTTP_X_CLIENT_DEVICE', '')
    except Exception:  # noqa: BLE001
        header = ''
    return normalize_device(header)


class DeviceToken(models.Model):
    """一张**某设备**的登录凭证。同一用户可以有多行。"""

    key = models.CharField(max_length=40, primary_key=True, verbose_name="Token")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='device_tokens', on_delete=models.CASCADE,
        verbose_name="用户",
    )
    #: 设备名（web / mobile / app）—— 登录时只作废同名设备的旧 token
    device = models.CharField(max_length=20, default=DEFAULT_DEVICE, verbose_name="设备")
    created = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    #: 每次带 token 请求时刷新（排查"哪台设备还在线"用；不参与鉴权）
    last_seen = models.DateTimeField(auto_now=True, verbose_name="最近使用")

    class Meta:
        verbose_name = "设备Token"
        verbose_name_plural = verbose_name
        indexes = [
            # 登录时按 (用户, 设备) 查旧 token，这是唯一的高频查询
            models.Index(fields=['user', 'device'], name='devtoken_user_device_idx'),
            # 清理/统计按用户 + 时间
            models.Index(fields=['user', '-created'], name='devtoken_user_time_idx'),
        ]

    def __str__(self):
        return f'{self.user_id}-{self.device}-{self.key[:8]}'

    @classmethod
    def issue(cls, user, device: str = DEFAULT_DEVICE) -> 'DeviceToken':
        """签发一张新 token（40 位十六进制，与 DRF 的 `Token.generate_key` 同构）。"""
        key = binascii.hexlify(os.urandom(20)).decode()
        return cls.objects.create(key=key, user=user, device=normalize_device(device))

    def touch(self):
        """只更新 `last_seen`（用 update 避免干扰 auto_now 的其它字段）"""
        DeviceToken.objects.filter(pk=self.pk).update(last_seen=timezone.now())


def revoke_all(user) -> int:
    """把这个用户的**所有**登录凭证删掉（两种 token 一起）。

    用于"安全状态变了"的场景：改密码、重置密码、停用、注销。
    ⚠️ 这些场景**不能**因为支持多端而放松 —— 否则"改了密码，旧手机还开着"。
    """
    from rest_framework.authtoken.models import Token

    if user is None:
        return 0
    removed = DeviceToken.objects.filter(user=user).delete()[0]
    removed += Token.objects.filter(user=user).delete()[0]
    return removed
