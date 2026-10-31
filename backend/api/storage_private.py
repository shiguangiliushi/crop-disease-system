"""私有目录的存储类（第 259 批）—— `.url` 自动带签名。

## 为什么放在存储层，而不是改 5 处序列化器

图片 URL 的出口有 5 处（`serializers.py` 的 432/485/779/821/991），还有 admin、
导出脚本、邮件模板。挨个包一层总会漏。而**所有**出口最终都走 `FieldFile.url`
→ `storage.url(name)`。在这一层加签名，等于一次覆盖全部出口，且新增页面不会再漏。

## 公开目录不受影响

`avatars/`、`pest_images/`、`news_images/` 不在 `PRIVATE_PREFIXES` 里，`url()` 原样返回。
"""
from __future__ import annotations

from django.core.files.storage import FileSystemStorage

from .media_sign import DEFAULT_TTL, PRIVATE_PREFIXES, sign_path


class SignedMediaStorage(FileSystemStorage):
    """私有目录返回带 `?sig=&exp=` 的 URL，公开目录保持原样。

    ## 为什么 location/base_url 是**动态属性**（第 293 批）

    `FileSystemStorage.location` 是 `cached_property`：第一次访问时把当时的
    `settings.MEDIA_ROOT` 记下来，之后不再变。而测试会把 `MEDIA_ROOT` 换到临时目录 ——
    于是「写文件用这个 storage」和「断言用 `default_storage`」拿到的根目录可能不同，
    表现为 `AssistantVisionTests.test_deleting_the_session_removes_the_image_file`
    这种"文件明明删了、断言却说还在"的怪失败（该用例单跑也红）。

    这里把 location / base_url 改成**每次读 settings**，让本 storage 与 `default_storage`
    在任何时刻都指向同一个根目录。
    """

    @property
    def location(self):
        from django.conf import settings as _settings

        stored = getattr(self, '_location', None)
        return stored or str(_settings.MEDIA_ROOT)

    @location.setter
    def location(self, value):
        self._location = value

    @property
    def base_url(self):
        from django.conf import settings as _settings

        stored = getattr(self, '_base_url', None)
        return stored or str(_settings.MEDIA_URL)

    @base_url.setter
    def base_url(self, value):
        self._base_url = value

    def url(self, name: str) -> str:
        base = super().url(name)
        normalized = str(name or '').replace('\\', '/')
        if any(normalized.startswith(prefix) for prefix in PRIVATE_PREFIXES):
            separator = '&' if '?' in base else '?'
            return f'{base}{separator}{sign_path(normalized, DEFAULT_TTL)}'
        return base


#: 单例：模型字段用 `storage=signed_media_storage`
signed_media_storage = SignedMediaStorage()
