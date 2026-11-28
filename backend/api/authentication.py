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
from rest_framework.permissions import SAFE_METHODS

from .models_token import DeviceToken


#: 游客 token 能写的视图白名单（只是文档；真正的判定看视图上的 `guest_allowed`）
GUEST_WRITABLE_VIEWS = (
    'DetectView', 'AssistantAskView', 'AssistantAskStreamView',
    'DetectionHistoryClearView', 'LogoutView',
)


class DeviceTokenAuthentication(authentication.BaseAuthentication):
    """`Authorization: Token <key>` —— key 来自 `DeviceToken`。

    查不到这张 key 时**返回 None**（让 DRF 去试 `TokenAuthentication`），
    而不是抛 401；见模块开头的说明。
    """

    keyword = 'Token'

    def authenticate(self, request):
        """只对"确实是我发的 key、但用户已停用"抛异常；不认识的 key 一律返回 None。

        为什么不在这里抛 401：DRF 的认证链一收到 AuthenticationFailed 就中止，
        老 `Token` 的认证类永远轮不到（见模块开头的说明）。
        """
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


class GuestTokenAuthentication(DeviceTokenAuthentication):
    """游客试用 token 的**写权限闸门**（第 439 批）。

    ## 为什么要一层认证类，而不是在 `permission_classes` 上挂一道权限

    权限类会被视图自己声明的 `permission_classes = [...]` **整个覆盖**。
    本项目大量视图是显式声明的（`DetectView`、`AssistantAskView`、各种管理端视图），
    所以挂在 `DEFAULT_PERMISSION_CLASSES` 上的闸门对它们**根本不生效** ——
    等于"看起来设了防，实际只防住了没写 permission_classes 的那几个"。

    认证类不会被覆盖：它在 `APIView.initial()` 的 `perform_authentication()` 里调用，
    早于权限检查。所以闸门放在这里，**默认拒绝、逐处放行**。

    ## 规则

    - 非游客 → 原样放行（这条类对真实用户零影响）；
    - 游客 + 安全方法（GET/HEAD/OPTIONS）→ 放行（否则连百科、预警都看不了）；
    - 游客 + 写方法 → 只有视图上写了 `guest_allowed = True` 才放行。

    需要放行的只有四个视图（识别、问答同步/流式、清空自己的历史、登出），
    见各自类上的 `guest_allowed`。新增接口时**默认是拒绝**的：
    这正是我们要的默认值。
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if not result:
            return result

        user = result[0]
        if not getattr(user, 'is_guest', False):
            return result          # 真实用户，完全不受影响

        # 总开关关掉时，**已经开着页面的游客也一并失效** ——
        # 否则"关闭试用"只是关掉了入口，存量游客还能继续用，
        # 线上出事（例如额度被刷爆）时这个开关就起不到止血作用。
        from . import guest as guest_trial
        if not guest_trial.config()['enabled']:
            raise exceptions.PermissionDenied('试用功能已关闭，请注册后使用')

        if request.method in SAFE_METHODS:
            return result          # 读是安全的：游客和匿名访客能看的一样

        view = (request.parser_context or {}).get('view')
        if not getattr(view, 'guest_allowed', False):
            raise exceptions.PermissionDenied(
                '试用账号只能使用识别与问答，注册后可使用完整功能')
        return result
