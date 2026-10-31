"""后端用户可见文案的多语言（第 275 批，第一步只覆盖登录/验证码）。

## 为什么只做一小块

后端有 100+ 接口，返回文案大多是中文硬编码。全量重写风险大、收益分散。
这里先把**登录链路**（用户每天都会遇到、英文界面下最容易暴露）做完，
其它接口后续按同一模式增补。

## 语言从哪来

优先 `?lang=`，其次 `Accept-Language` 头里的第一段，默认中文。
不引入 gettext / 编译流程：文案就几十条，字典更直观、也便于测试断言。
"""
from __future__ import annotations

DEFAULT_LANG = 'zh'

MESSAGES = {
    'login.credentials_required': {
        'zh': '用户名和密码不能为空',
        'en': 'Username and password are required',
    },
    'login.invalid_payload': {
        'zh': '请求体格式错误：应为合法的 JSON',
        'en': 'Invalid request body: expected valid JSON',
    },
    'login.invalid_payload_object': {
        'zh': '请求体格式错误：应为 JSON 对象',
        'en': 'Invalid request body: expected a JSON object',
    },
    'login.wrong_password': {
        'zh': '密码错误，还可尝试 {remaining} 次',
        'en': 'Incorrect password, {remaining} attempt(s) left',
    },
    'login.locked': {
        'zh': '登录失败次数过多，账号已被锁定，请 {minutes} 分钟后再试',
        'en': 'Too many failed attempts. Account locked for {minutes} minute(s)',
    },
    'login.just_locked': {
        'zh': '密码错误次数过多，账号已锁定 {minutes} 分钟',
        'en': 'Too many wrong passwords. Account locked for {minutes} minute(s)',
    },
    'captcha.required': {
        'zh': '验证码错误或已过期，请刷新后重试',
        'en': 'Verification code is wrong or expired, please refresh and retry',
    },
}


def request_lang(request) -> str:
    """从 `?lang=` 或 `Accept-Language` 取语言码（zh / en），取不到回中文。"""
    explicit = ''
    try:
        explicit = str(request.query_params.get('lang') or '').strip()
    except AttributeError:
        explicit = str(request.GET.get('lang') or '').strip()
    header = explicit or str(request.META.get('HTTP_ACCEPT_LANGUAGE') or '')
    code = (header.split(',')[0] if header else '').strip().lower()
    return 'en' if code.startswith('en') else DEFAULT_LANG


def msg(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    """取文案并渲染占位符；未知 key 原样返回（不抛异常，避免文案问题把接口打挂）。"""
    entry = MESSAGES.get(key)
    if not entry:
        return key
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError):
        return text
