"""`user` 响应体的**唯一**构造点（第 439 批）。

## 为什么要单独一个文件

登录、`/api/check-auth/`、游客开试用返回的是**同一坨**用户对象，
而它曾被抄了三份（`LoginView`、`CheckAuthView`、以及注册用的序列化器）。

抄多份的代价不是"代码不好看"，而是**前端按这套字段初始化**：
`stores/auth.js` 直接拿 `data.user` 往本地存。少一个 `role` 或 `capabilities`，
前端的菜单/路由守卫就会静默失效（第 17 批真实踩过：登录不返回 role，
前端所有 `role === 'ADMIN'` 的分支成了死代码，管理员被挡在管理页外面）。

所以这里收敛成一份，三处都调用 `build()`。**加字段/删字段都在这里改。**
"""
from __future__ import annotations

from . import serializers
from .capabilities import capabilities_of, content_modules_of


def build(user, request=None) -> dict:
    """当前用户对前端可见的全部字段（键名是前端契约，勿改）。"""
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'avatar': serializers._user_avatar_url(user, request),
        'role': getattr(user, 'role', 'USER'),
        # 能力清单：前端据此决定"能不能进管理后台、菜单显示哪几项"
        'capabilities': capabilities_of(user),
        # 内容模块：内容侧按模块显示（勾了新闻才给新闻管理）
        'content_modules': content_modules_of(user),
        # 第 439 批：游客标记。前端据此显示"试用中"、隐藏需要注册的入口
        'is_guest': bool(getattr(user, 'is_guest', False)),
    }
