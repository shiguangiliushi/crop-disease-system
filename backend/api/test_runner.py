"""
测试专用的 runner（第 110 批）
============================================================================
**解决什么问题**：跑一次 `manage.py test` 会在**真实 `backend/media/`** 里留下文件。

实测（第 110 批）：
  · `media/news_images/news_<随机>.png` —— `ImageUploadValidationTests` 里
    那条"合法 PNG 能上传成功"的用例真的落盘了（它必须落盘才测得出上传成功）；
  · `media/uploads/<随机>.jpg` —— 同类的通用图片上传用例。

这些文件是**孤儿**（没有任何数据库记录引用），而且每跑一次测试就多几份。
更糟的是 `git add -A` 会把它们收进仓库 —— 首次提交时就是这么混进 98 个的。

`api/tests.py` 开头其实立过规矩（第 21 批）：

    本文件的测试**不写任何媒体文件**。
    …… 测试里的一次"清空封面"会真的删掉业务文件，事务回滚救不了文件系统。

但"靠每个测试作者记得遵守"不是可靠的做法 —— 总会有人（包括我）写出落盘的用例。
所以这里把规矩变成**默认行为**：整轮测试的 `MEDIA_ROOT` 指向临时目录。

============================================================================
为什么要自定义 runner，而不是在 settings 里判断 `_IS_TESTING`
============================================================================
1. `_IS_TESTING` 是靠 `'test' in sys.argv` 判断的，**不可靠**：
   用 `manage.py test` 跑没问题，但 pytest / IDE / `django.test.runner` 直接调用时
   判不出来。runner 是 Django 官方的扩展点，一定会被调到。
2. 更要紧的是**顺序与范围**：runner 的 `setup_test_environment()` 在所有测试之前、
   `teardown_test_environment()` 在所有测试之后 —— 正好是"整轮测试"的边界，
   而 `settings` 里的判断只是一个静态值，管不到 `override_settings` 的交互。

用法：`settings.TEST_RUNNER` 已指向本类，`manage.py test` 自动生效，无需任何参数。
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.test.runner import DiscoverRunner


class MediaIsolatedTestRunner(DiscoverRunner):
    """
    把整轮测试的 `MEDIA_ROOT` 指到临时目录，跑完删掉。

    行为约定：
      · 临时目录里**按原目录结构**创建（`detection_uploads/`、`news_images/` 等），
        因为有些代码会直接往子目录写，子目录不存在就会失败；
      · 跑完无论成败都清理（`finally`）；
      · 若临时目录不可用（极少数受限环境），**回落到真实 media 但打印警告** ——
        宁可污染也不要让整套测试跑不起来，但必须让人看见。
    """

    #: 测试期间会被用到的子目录（与 `upload_to` 保持一致，多建几个没有副作用）
    SUBDIRS = (
        'detection_uploads',
        'detection_history',
        'detection_history/annotated',
        'pest_images',
        'news_images',
        'feedback_images',
        'avatars',
        'consult_images',
        'uploads',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._media_dir: Path | None = None
        self._original_media_root = None

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        try:
            self._media_dir = Path(tempfile.mkdtemp(prefix='zz_test_media_'))
            for sub in self.SUBDIRS:
                (self._media_dir / sub).mkdir(parents=True, exist_ok=True)
            self._original_media_root = settings.MEDIA_ROOT
            settings.MEDIA_ROOT = str(self._media_dir)
        except OSError as exc:
            # 受限环境（临时目录不可写）——不阻断测试，但要说清楚
            self._media_dir = None
            print(f'\n⚠️ 无法创建临时 MEDIA_ROOT（{exc}）；'
                  '本轮测试会写真实 media，跑完请用 prune_media 清理\n')

    def teardown_test_environment(self, **kwargs):
        try:
            if self._original_media_root is not None:
                settings.MEDIA_ROOT = self._original_media_root
            if self._media_dir is not None:
                shutil.rmtree(self._media_dir, ignore_errors=True)
        finally:
            super().teardown_test_environment(**kwargs)
