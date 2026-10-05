import logging  # 导入日志模块

from django.conf import settings  # 第 94 批：读 Token 有效期
from django.utils import timezone  # 第 94 批：判断 Token 是否过期
from rest_framework.authentication import TokenAuthentication  # 导入DRF Token认证类
from rest_framework.exceptions import AuthenticationFailed  # 导入认证失败异常
from rest_framework.authtoken.models import Token  # 导入Token模型
from django.utils.deprecation import MiddlewareMixin  # 导入中间件基类

logger = logging.getLogger(__name__)  # 获取日志记录器


def token_ttl_seconds():
    """
    Token 有效期（秒）；0 或负数表示不过期（第 94 批）

    这个设置（`settings.TOKEN_EXPIRED_AFTER_SECONDS`）此前**只定义、没人读** ——
    DRF 的 `TokenAuthentication` 不校验创建时间，本中间件也没读它，
    所以"7 天过期"只是一句注释：凭证泄露出去就是**永久有效**。
    """
    try:
        return int(getattr(settings, 'TOKEN_EXPIRED_AFTER_SECONDS', 0) or 0)
    except (TypeError, ValueError):
        return 0


def is_token_expired(token, now=None):
    """Token 是否已过期（ttl<=0 时恒为 False，即不过期）"""
    ttl = token_ttl_seconds()
    if ttl <= 0:
        return False
    now = now or timezone.now()
    return (now - token.created).total_seconds() > ttl


class TokenAuthenticationMiddleware(MiddlewareMixin):  # 定义Token认证中间件类
    """
    自定义Token认证中间件
    处理API请求的Token认证

    说明（本轮清理）：原先这里还有一段"动态会话名"逻辑 —— 对每个没有会话 Cookie 的请求
    调用 request.session.save() 来新建会话，并把 request.session.cookie_name 设成一个
    动态名字。实测后果有两个：
      1. 数据库 django_session 表被灌到 **8056 行**（每个匿名 API 请求都会新增一行；
         匿名请求没有 Cookie，所以永远命中"没有 session_key"这个分支）；
      2. 那个 cookie_name 赋值其实**不生效** —— Django 的 SessionMiddleware 用的是
         settings.SESSION_COOKIE_NAME，不看 request.session.cookie_name。
    全项目除本文件外没有任何地方使用 request.session（已 grep 确认），
    因此删除该逻辑不影响 Token 认证、也不影响 Django admin 的正常会话
    （admin 登录时 Django 会按标准流程自行创建会话）。
    """

    def __init__(self, get_response=None):  # 初始化方法
        self.get_response = get_response  # 设置响应处理器
        super().__init__(get_response)  # 调用父类初始化

    def __call__(self, request):  # 调用方法，处理请求
        # 预检请求（OPTIONS）直接通过，不进行认证
        if request.method == 'OPTIONS':  # 检查是否为OPTIONS请求
            return self.get_response(request)  # 直接返回响应

        # 对API请求进行Token认证
        if request.path.startswith('/api/'):  # 检查是否为API请求
            # 从请求头获取Token
            auth_header = request.META.get('HTTP_AUTHORIZATION', '').split()  # 获取认证头并分割

            if len(auth_header) == 2 and auth_header[0].lower() == 'token':  # 检查认证头格式
                token_key = auth_header[1]  # 获取Token值
                try:  # 尝试验证Token
                    token = Token.objects.select_related('user').get(key=token_key)  # 获取Token及相关用户

                    # 第 94 批：**真正执行有效期**。
                    # 过期就当作"没有凭证"处理（删掉这张 Token + 不做身份认证），
                    # 于是后续 DRF 会正常返回 401 → 前端（桌面/移动端）接管跳登录页。
                    # 为什么不在这里直接返回 401：本中间件跑在 DRF 之前，直接返 401 会绕过
                    # CORS/异常处理，响应形状和别处不一致；交给 DRF 更统一。
                    expired = is_token_expired(token)
                    # 用 debug 级：每个带 Token 的请求都会走到这里，info 级会把日志刷满
                    logger.debug(
                        "token 检查 path=%s ttl=%s age=%ss expired=%s",
                        request.path, token_ttl_seconds(),
                        round((timezone.now() - token.created).total_seconds()),
                        expired,
                    )
                    if expired:
                        logger.info(
                            "Token 已过期，按未认证处理（user=%s path=%s）",
                            token.user_id, request.path,
                        )
                        token.delete()  # 顺手清理，避免过期 Token 长期堆在库里
                        response = self.get_response(request)
                        response['X-Token-Expired'] = '1'  # 给客户端一个明确信号
                        return response

                    request.user = token.user  # 设置请求用户
                    request.auth = token  # 设置认证Token
                    logger.debug("User %s authenticated with token", request.user.username)  # 记录认证成功信息
                except Token.DoesNotExist:  # 捕获Token不存在异常
                    # 🔒 不要把 token 明文写进日志（哪怕它是无效的：它可能只是过期/被截断的真实凭证，
                    #    而且这行是 WARNING 级，会稳定落盘）。只记录"收到无效 token"这个事实。
                    logger.warning("Invalid token presented for %s", request.path)  # 记录警告信息
                    pass  # 继续执行，让DRF的认证类处理

            # 记录请求信息用于调试
            # 🔒 安全提示：原代码这里有一行
            #     logger.debug(f"Auth header: {request.META.get('HTTP_AUTHORIZATION')}")
            #   它会为**每一个 API 请求**把完整的 `Token xxxxxxxx` 写进 logs/debug.log，
            #   等于把用户凭证持久化到磁盘。已删除，且不得再加回。
            logger.debug("Request path: %s", request.path)  # 记录请求路径
            logger.debug(
                "User authenticated: %s",
                request.user.is_authenticated if hasattr(request, 'user') else 'No user',
            )  # 记录用户认证状态

        response = self.get_response(request)  # 获取响应
        return response  # 返回响应