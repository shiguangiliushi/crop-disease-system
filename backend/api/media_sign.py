"""私有 media 的签名 URL（第 258 批）。

## 为什么需要签名

`/media/` 里的识别照片、咨询配图、反馈附图会**直接渲染在 `<img>` 上**，而 `<img>` 不会带
`Authorization` 头。想给这些图收权，只能把"凭什么允许你读"这一信息放进 URL ——
也就是**签名 URL**：`?sig=<HMAC>&exp=<过期时间戳>`。

## 为什么用时间戳 + HMAC 而不是直接塞 device token

把 token 放进 URL 会被写进 Nginx 访问日志、浏览器历史、Referer（`Referrer-Policy` 只能减少
不能消除）。签名是**只对这个路径、这段时限**有效的凭据：泄露的影响面小得多。
"""
from __future__ import annotations

import hashlib
import hmac
import time

DEFAULT_TTL = 3600  # 1 小时：足够一次页面浏览，又不会长期可用


def _secret() -> bytes:
    from django.conf import settings

    return str(settings.SECRET_KEY).encode('utf-8')


def _digest(path: str, exp: int) -> str:
    message = f'{path}|{exp}'.encode('utf-8')
    return hmac.new(_secret(), message, hashlib.sha256).hexdigest()


def sign_path(path: str, ttl: int = DEFAULT_TTL) -> str:
    """返回 `?sig=…&exp=…` 形式的查询串（不带 `?` 由调用方决定）。"""
    exp = int(time.time()) + max(1, ttl)
    return f'sig={_digest(path, exp)}&exp={exp}'


def verify(path: str, sig: str, exp: str) -> bool:
    """校验签名与有效期。任何解析失败一律返回 False（调用方回 404）。"""
    try:
        exp_int = int(exp)
    except (TypeError, ValueError):
        return False
    if exp_int < int(time.time()):
        return False
    if not sig or len(sig) > 128:
        return False
    return hmac.compare_digest(_digest(path, exp_int), sig)
