"""鉴权类（第 231 批）：先认"每设备一张"的 `DeviceToken`，再退回 DRF 的 `Token`。

为什么要两条：

  · `DeviceToken`（`models_token.py`）是新的主路径 —— 一个用户多张 token，手机与桌面
    可以同时在线，登录只轮换**同设备**的旧凭证；
  · DRF 的 `Token` 继续认 —— 老客户端缓存的凭证、既有测试里 `Token.objects.create()`
    造出来的凭证都还能用。不保留这条，几十条测试与线上老会话会同时失效。

## 为什么不能直接继承 `TokenAuthentication` 的 `authenticate()`

试过：`TokenAuthentication.authenticate()` 在查不到 key 时会**抛 `AuthenticationFailed`**，
而 DRF 的认证链一旦收到这个异常就**停止**、不会去试下一个认证类 —— 于是
"不认识这张 key" 变成了 401，老 Token 永远轮不到（实测：兼容用例直接红了）。
所以这里自己写 `authenticate()`：**查不到就 `return None`**（交给下一个认证类），
只有"确实是我发的 key、但用户不可用"才抛异常。

过期判定不在这里：`api/middleware.py` 按 `TOKEN_EXPIRED_AFTER_SECONDS` 统一处理
（两个模型都有 `created` 字段，同一套逻辑）。
"""
from __future__ import annotations

from rest_framework import authentication, exceptions
from rest_framework.authentication import get_authorization_header

from .models_token import DeviceToken


class DeviceTokenAuthentication(authentication.BaseAuthentication):
    """`Authorization: Token <key>` —— key 来自 `DeviceToken`。

    查不到这张 key 时**返回 None**（让 DRF 去试 `TokenAuthentication`），
    而不是抛 401；见模块开头的说明。
    """

    keyword = 'Token'

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() != self.keyword.lower().encode():
            return None

        if len(auth) == 1:
            raise exceptions.AuthenticationFailed(
                'Invalid token header. No credentials provided.')
        if len(auth) > 2:
            raise exceptions.AuthenticationFailed(
                'Invalid token header. Token string should not contain spaces.')

        try:
            token_key = auth[1].decode()
        except UnicodeError:
            raise exceptions.AuthenticationFailed(
                'Invalid token header. Token string should not contain invalid characters.')

        token = (
            DeviceToken.objects.select_related('user').filter(key=token_key).first()
        )
        if token is None:
            # 不是我发的 key —— 交给下一个认证类（DRF 的 Token）
            return None

        if not token.user.is_active:
            raise exceptions.AuthenticationFailed('User inactive or deleted.')

        # 顺手记"哪台设备还在用"（失败也不该影响请求）
        try:
            token.touch()
        except Exception:  # noqa: BLE001
            pass
        return token.user, token

    def authenticate_header(self, request):
        return self.keyword
