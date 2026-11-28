"""私有媒体的开关测试（第 441 批）。

## 背景

历史上传目录 `detection_uploads/` 一直是**公开可访问**的：知道文件名（或猜到）
就能看别人的识别图。要收紧有两条路：

1. 把 `detection_uploads/` 加进 `PRIVATE_PREFIXES` —— 一键生效，但**必须同时**
   在 nginx 里把该前缀回源给 Django（`views_media` 校验签名）；只改代码不改
   nginx，所有老图片会 404；
2. 所以做成了**开关**（`PRIVATE_DETECTION_UPLOADS`，默认关），两步一起改才打开。

这组用例钉住开关本身的行为：默认不签名、打开后签名、且不影响原本就私有的目录。
"""
from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from .media_sign import private_prefixes
from .storage_private import signed_media_storage

#: 一个"历史遗留"路径（早期版本 upload_to 写出来的）
LEGACY = 'detection_uploads/29e8e38b95264f138010f96a4d036e65.JPG'

#: 一个本来就在私有清单里的路径
PRIVATE = 'detection_history/whatever.jpg'


class PrivateDetectionUploadsSwitchTests(SimpleTestCase):
    def test_default_is_public(self):
        """默认关：历史目录不签名（否则 nginx 没配就会 404）。"""
        self.assertNotIn('detection_uploads/', private_prefixes())
        self.assertNotIn('sig=', signed_media_storage.url(LEGACY))

    @override_settings(PRIVATE_DETECTION_UPLOADS=True)
    def test_switch_adds_prefix_and_signature(self):
        self.assertIn('detection_uploads/', private_prefixes())
        self.assertIn('sig=', signed_media_storage.url(LEGACY))

    @override_settings(PRIVATE_DETECTION_UPLOADS=True)
    def test_existing_private_prefixes_unaffected(self):
        """打开开关不该改变原本私有的那几个目录的行为。"""
        self.assertIn('sig=', signed_media_storage.url(PRIVATE))

    def test_public_dirs_stay_public(self):
        """本来就不该私有的目录（头像 / 百科图 / 新闻图）永远不带签名。"""
        for name in ('avatars/a.png', 'pest_images/b.png', 'news_images/c.png'):
            with self.subTest(name=name):
                self.assertNotIn('sig=', signed_media_storage.url(name))
