"""
备份公共工具（第 102 批）

`backend_backup` / `backup_verify` / `backend_restore` 三个命令共用这里的常量与函数。

为什么单独抽一个模块而不是各写一份：**校验和的算法必须三处完全一致**，
否则"备份时算的"和"恢复时验的"对不上，会出现"备份明明没坏却拒绝恢复"
（比不校验更糟：它会让人以为备份不可用）。抽出来就不会有第二份实现。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

#: 备份格式版本。**恢复时要检查**：格式不兼容宁可明确报错，也不要猜着恢复。
BACKUP_FORMAT_VERSION = 1

#: 清单文件名（放在每个备份目录里）
MANIFEST_NAME = 'manifest.json'

#: 数据库副本文件名
DB_NAME = 'db.sqlite3'

#: 媒体文件压缩包名
MEDIA_ARCHIVE = 'media.tar.gz'

#: 模型权重的可选压缩包名
MODELS_ARCHIVE = 'models.tar.gz'

#: 分块大小（读大文件算校验和时用；4MB 在内存与 syscall 次数之间比较平衡）
CHUNK = 4 * 1024 * 1024


def sha256_file(path: Path, chunk: int = CHUNK) -> str:
    """流式计算文件 sha256（不把整个文件读进内存 —— 备份里可能有几百 MB 的媒体包）"""
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def human_size(num_bytes: int | float) -> str:
    """人类可读的体积（日志和命令输出都用它，避免到处写 /1024/1024）"""
    value = float(num_bytes or 0)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            return f'{value:.1f} {unit}' if unit != 'B' else f'{int(value)} B'
        value /= 1024
    return f'{value:.1f} TB'


def write_json(path: Path, payload: dict) -> None:
    """写 JSON（统一 utf-8 + 缩进，便于人工查看清单）"""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def list_backups(backup_root: Path) -> list[Path]:
    """
    列出备份根目录下的所有备份，**按时间从新到旧**。

    排序依据是清单里的 `created_at`（不是目录 mtime）：目录 mtime 会被"往里补文件"
    之类的操作改掉，而 `created_at` 是备份生成那一刻的事实。
    没有清单的目录排在最后（它们可能是手工放进去的，也可能是坏备份）。
    """
    if not backup_root.exists():
        return []
    entries = []
    for child in backup_root.iterdir():
        if not child.is_dir():
            continue
        manifest_path = child / MANIFEST_NAME
        created = ''
        if manifest_path.exists():
            try:
                created = str(read_json(manifest_path).get('created_at') or '')
            except Exception:  # noqa: BLE001  坏清单不影响"它是个目录"这个事实
                created = ''
        entries.append((created, child))
    entries.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in entries]


def default_backup_root() -> Path:
    """
    默认备份根目录：**项目根下的 backups/**，不在 media 里。

    为什么刻意不放在 media（`forum_backup` 就是这么干的）：
      · media 是"用户上传的内容、随部署一起被同步/清理"的目录，
        备份放进去容易被 rsync --delete、容器挂载覆盖、或被"清理上传目录"的操作连带删掉；
      · 备份的目的就是"防 media 出事"，放在 media 里等于把鸡蛋放在同一个篮子里。
    可用 `DJANGO_BACKUP_DIR` 覆盖（生产应当指向**另一块盘或网络存储**）。
    """
    from django.conf import settings
    configured = (os.environ.get('DJANGO_BACKUP_DIR') or '').strip()
    if configured:
        return Path(configured).expanduser()
    return Path(settings.BASE_DIR).parent / 'backups'


def backup_root() -> Path:
    return default_backup_root()
