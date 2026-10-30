"""安全响应头（第 255 批）—— 目前只补 **CSP**。

## 为什么单独写一个中间件

Django 自带 `SecurityMiddleware` 已经给了 `X-Content-Type-Options`、
`Referrer-Policy`、HSTS 这些，但**没有 CSP**。CSP 是"XSS 已经发生了"之后的最后一道防线：
移动端 token 存在 localStorage，一旦执行了注入的脚本，token 就能被读走。

## 策略为什么这么写

- `default-src 'self'`：默认只允许同源；
- `script-src 'self'`：**不放开 `unsafe-inline`**（Vite 产物是外链脚本）；
- `style-src 'self' 'unsafe-inline'`：Element Plus / Vant 运行时注入 `<style>`，只能放开；
- `img-src 'self' data: blob:`：上传预览与图表用 data/blob；
- `connect-src`：默认 `'self'`，前后端分域时用 `DJANGO_CSP_CONNECT_SRC` 追加；
- `frame-ancestors 'self'`：禁止被别的站嵌（等价于 X-Frame-Options）；
- `object-src 'none'` / `base-uri 'self'`：老式注入面直接关掉。

## 开关

- `DJANGO_CSP_ENABLED`（默认 **随 DEBUG 走**：开发关、生产开）—— 开发时 Vite HMR 会注入
  内联脚本，硬套 CSP 只会让人调不通页面；
- `DJANGO_CSP_REPORT_ONLY=1`：只上报不拦截，用于上线前观察。
"""
from __future__ import annotations

import os

DEFAULT_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src {connect}; "
    "frame-ancestors 'self'; "
    "object-src 'none'; "
    "base-uri 'self'"
)


def _enabled(debug: bool) -> bool:
    raw = os.environ.get('DJANGO_CSP_ENABLED')
    if raw is None:
        return not debug
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


class ContentSecurityPolicyMiddleware:
    """给每个响应补 `Content-Security-Policy`（可用环境变量关闭）。

    放在 MIDDLEWARE 末尾：只改响应头，不参与请求阶段。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        from django.conf import settings

        if not _enabled(bool(settings.DEBUG)):
            return response
        if 'Content-Security-Policy' in response:
            return response

        connect = os.environ.get('DJANGO_CSP_CONNECT_SRC') or "'self'"
        policy = getattr(settings, 'CONTENT_SECURITY_POLICY', None) or DEFAULT_POLICY.format(connect=connect)
        header = (
            'Content-Security-Policy-Report-Only'
            if os.environ.get('DJANGO_CSP_REPORT_ONLY', '').strip().lower() in ('1', 'true', 'yes', 'on')
            else 'Content-Security-Policy'
        )
        response[header] = policy
        return response
