"""drf-spectacular 扩展（第 386 批）。

本模块只做一件事：`DeviceTokenAuthenticationScheme` —— 让自定义认证类在 schema 里有
对应的 securityScheme（否则每遇到一次就记一条 warning）。

## 为什么需要 TolerantAutoSchema

项目里有 80 个手写 `APIView`（管理端列表、助手问答、日历、积分……），它们没有
`serializer_class`，drf-spectacular 遇到就记一条 error 并**跳过整条 path**：

    Error [AdminAuditLogListView]: unable to guess serializer.

结果：`/api/docs/` 里看不到这些接口 —— 文档"看起来很小"，实际系统有一半接口没写进去。

逐个补 `@extend_schema` 当然更准确，但那是 80 个视图的工作量，必须分批做。
在此之前，**"接口存在、请求/响应是任意 JSON"** 远比"接口完全不存在"有用：
前端照着能看到 URL、方法、权限、参数；准确性后续按批提升。
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
