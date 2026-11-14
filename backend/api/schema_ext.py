"""drf-spectacular 扩展：让**自定义认证类**在 schema 里有对应的 securityScheme（第 386 批）。

## 为什么需要这个文件

`DeviceTokenAuthentication` 用的是与 DRF 自带 `TokenAuthentication` **完全相同的
header 形态**（`Authorization: Token <key>`），但 drf-spectacular 不认识这个类，
于是每遇到一次就记一条 warning：

    unable to guess serializer / could not resolve authenticator
    class DeviceTokenAuthentication(authentication.BaseAuthentication)

本项目的 schema 生成有 **93 条**这类 warning（去重后也占大头）。
注册一个扩展后：schema 里多出一个 `deviceTokenAuth` scheme，warning 归零。

## 为什么不是直接删掉自定义类

因为它是**主认证路径**（每设备一张 token，手机与桌面可同时在线）；
DRF 的 `TokenAuthentication` 只是兼容老客户端。两者必须共存，见
`api/authentication.py` 开头的说明。

## 生效方式

drf-spectacular 在生成 schema 时会**导入 `extensions` 模块**里声明的子类；
这里通过 `apps.py` 的 `ready()` 显式导入一次，确保被注册（不依赖 import 顺序）。
"""
from __future__ import annotations

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class DeviceTokenAuthenticationScheme(OpenApiAuthenticationExtension):
    """`DeviceTokenAuthentication` → `deviceTokenAuth`（apiKey in header）。"""

    target_class = 'api.authentication.DeviceTokenAuthentication'
    name = 'deviceTokenAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': (
                'DeviceToken 认证：`Authorization: Token <key>`。'
                '与 drf 自带的 tokenAuth 使用同一个 header —— '
                '服务端先按 DeviceToken 查，查不到再退回 drf Token（兼容老客户端）。'
            ),
        }
