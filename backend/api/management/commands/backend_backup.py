"""
完整后端备份（第 102 批）

==================================================================
为什么需要它（以及为什么不是"再加一个脚本"）
==================================================================
在此之前，项目里**没有任何可用的完整备份手段**：
  · 唯一存在的 `forum_backup` 命令**一跑就崩**（`NameError: timezone`，
    见该命令第 84 行；还引用了 `Post.is_featured` / `Post.is_locked` 两个
    **模型里根本不存在的字段**）；
  · 就算它能跑，也只覆盖论坛的 5 张表 —— 识别记录、意见反馈、新闻、积分、
    通知、私信全都不在里面；
  · 它还把备份文件写进 `MEDIA_ROOT/forum_backups/`，也就是**和要保护的数据放在同一个
    目录里** —— media 被误删/被 rsync --delete 带走时，备份一起没。
  · 文档里唯一的相关约定是"别删 media"。

这个命令做的是**整库 + 全部上传文件**的备份，并且**自带可验证性**：
每个备份目录里有 `manifest.json`（记录体积、条数、sha256 校验和），
配套的 `backup_verify` 能把"这份备份到底能不能用"验证到"能读出 N 条业务数据"。

==================================================================
用法
==================================================================
    python manage.py backend_backup                      # 默认：库 + media
    python manage.py backend_backup --include-models      # 连模型权重一起（+20MB）
    python manage.py backend_backup --keep 14             # 只留最近 14 份
    python manage.py backend_backup --out D:\\backups\\crop   # 指定目录
    python manage.py backend_backup --no-media             # 只备数据库（很快）

设计要点（每一条都对应一种真实的翻车方式）：

1. **用 SQLite 的在线备份 API 拷库，不是直接复制文件。**
   直接 `copy db.sqlite3` 在服务运行中可能拿到**写到一半**的库（WAL/写事务），
   恢复后表损坏。`sqlite3.Connection.backup()` 会拿一致性快照。
2. **媒体文件打成 tar.gz 并逐个记 sha256**，而不是复制目录：
   复制目录在文件多时容易"复制到一半就以为完事"（971 个文件 / 19MB）；
   打成一个包 + 校验和，才能让 `backup_verify` 说出"这份包是完好的"。
3. **清单里记业务条数**（用户/帖子/识别记录/反馈…）：恢复后要能对比，
   否则"恢复完成"只是句口号。
4. **Django 数据摘要（dumpdata）可选但默认开**：它是**跨数据库可读**的文本，
   在"sqlite 文件损坏但想抢救数据"这种场景下是最后一道救命绳。
   `--no-data-dump` 可关掉（大库会慢）。
5. 默认备份目录在**项目根/backups**，不在 media 里（见 backup_utils 的说明）。
"""
from __future__ import annotations

import os
import sqlite3
import tarfile
import tempfile
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from api import backup_utils as bu


class Command(BaseCommand):
    help = '完整备份：SQLite 数据库 + media 上传文件（含清单与校验和）'

    def add_arguments(self, parser):
        parser.add_argument('--out', type=str, default='',
                            help='备份根目录（默认 项目根/backups，可设 DJANGO_BACKUP_DIR）')
        parser.add_argument('--label', type=str, default='',
                            help='给这次备份起个后缀名（例如 before-upgrade）')
        parser.add_argument('--no-media', action='store_true', help='不备份 media（只备数据库，很快）')
        parser.add_argument('--include-models', action='store_true',
                            help='把模型权重（*.pt，约 20MB）也打包进去')
        parser.add_argument('--no-data-dump', action='store_true',
                            help='不生成 dumpdata JSON（可跨库读取的文本备份）')
        parser.add_argument('--keep', type=int, default=0,
                            help='只保留最近 N 份备份（在**本次备份成功后**清理旧的；0 = 不清理）')
        parser.add_argument('--quiet', action='store_true', help='少输出（给定时任务用）')

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        started = time.perf_counter()
        out_root = Path(options['out']).expanduser() if options['out'] else bu.backup_root()
        label = (options['label'] or '').strip()
        include_media = not options['no_media']
        include_models = options['include_models']
        with_data_dump = not options['no_data_dump']
        quiet = options['quiet']

        def say(message, style=None):
            if quiet:
                return
            self.stdout.write(self.style.SUCCESS(message) if style == 'ok' else message)

        db_path = Path(settings.DATABASES['default']['NAME'])
        engine = settings.DATABASES['default']['ENGINE']
        if 'sqlite' not in engine:
            raise CommandError(
                f'当前数据库是 {engine}，本命令只支持 sqlite。\n'
                'PostgreSQL/MySQL 请用 pg_dump / mysqldump，并用 --no-media 之外的方式管 media。'
            )
        if not db_path.exists():
            raise CommandError(f'找不到数据库文件：{db_path}')

        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        name = f'{stamp}-{label}' if label else stamp
        target = out_root / name
        if target.exists():
            # 同一秒内跑两次（定时任务重叠、或同一个进程里连跑多个测试用例）不要覆盖，
            # 也不要因为"目录已存在"直接失败。
            # ⚠️ 兜底不能只用 PID：同一个进程里连跑两次时 PID 相同 —— 实测测试里
            #    连续调用就撞成 `FileExistsError`。用微秒时间戳保证唯一。
            target = out_root / f'{name}-{int(time.time() * 1_000_000) % 1_000_000_000}'
        target.mkdir(parents=True, exist_ok=False)

        say(f'备份目标：{target}')
        manifest = {
            'format_version': bu.BACKUP_FORMAT_VERSION,
            'created_at': timezone.now().isoformat(),
            'label': label or None,
            'hostname': os.environ.get('COMPUTERNAME') or os.environ.get('HOSTNAME') or '',
            'debug': settings.DEBUG,
            'db_engine': engine,
            'artifacts': {},
            'counts': {},
            'media': {},
            'models': {},
        }

        # ---------------- 1) 数据库（在线备份 API） ----------------
        db_target = target / bu.DB_NAME
        self._backup_sqlite(db_path, db_target)
        manifest['artifacts'][bu.DB_NAME] = {
            'bytes': db_target.stat().st_size,
            'sha256': bu.sha256_file(db_target),
        }
        say(f'  ✓ 数据库  {bu.human_size(db_target.stat().st_size)}')

        # ---------------- 2) 媒体文件 ----------------
        if include_media:
            media_root = Path(settings.MEDIA_ROOT)
            if media_root.exists():
                archive = target / bu.MEDIA_ARCHIVE
                count = self._make_tar(media_root, archive)
                manifest['artifacts'][bu.MEDIA_ARCHIVE] = {
                    'bytes': archive.stat().st_size,
                    'sha256': bu.sha256_file(archive),
                    'files': count,
                }
                manifest['media'] = {'root': str(media_root), 'files': count}
                say(f'  ✓ 媒体    {bu.human_size(archive.stat().st_size)}（{count} 个文件）')
            else:
                say(f'  ⚠ 跳过媒体：{media_root} 不存在')

        # ---------------- 3) 模型权重（可选） ----------------
        if include_models:
            model_files = self._find_model_files()
            if model_files:
                archive = target / bu.MODELS_ARCHIVE
                count = self._make_tar_from_list(model_files, Path(settings.BASE_DIR), archive)
                manifest['artifacts'][bu.MODELS_ARCHIVE] = {
                    'bytes': archive.stat().st_size,
                    'sha256': bu.sha256_file(archive),
                    'files': count,
                }
                manifest['models'] = {'files': [str(p.relative_to(settings.BASE_DIR)) for p in model_files]}
                say(f'  ✓ 模型    {bu.human_size(archive.stat().st_size)}（{count} 个文件）')

        # ---------------- 4) 文本数据摘要（可跨库读取） ----------------
        if with_data_dump:
            dump_path = target / 'data.json'
            try:
                self._dumpdata(dump_path)
                manifest['artifacts']['data.json'] = {
                    'bytes': dump_path.stat().st_size,
                    'sha256': bu.sha256_file(dump_path),
                }
                say(f'  ✓ 数据摘要 {bu.human_size(dump_path.stat().st_size)}')
            except Exception as exc:  # noqa: BLE001
                # 摘要失败**不该让整个备份失败** —— 库副本才是主力，摘要是补充。
                self.stderr.write(self.style.WARNING(f'  ⚠ 生成 data.json 失败（不影响库副本）：{exc}'))

        # ---------------- 5) 业务条数（恢复后要对比） ----------------
        manifest['counts'] = self._collect_counts()
        say('  ✓ 条数：' + '、'.join(f'{k}={v}' for k, v in manifest['counts'].items()))

        manifest['elapsed_seconds'] = round(time.perf_counter() - started, 1)
        manifest['total_bytes'] = sum(
            item.get('bytes', 0) for item in manifest['artifacts'].values()
        )
        bu.write_json(target / bu.MANIFEST_NAME, manifest)

        say(self.style.SUCCESS(
            f'备份完成：{target}（合计 {bu.human_size(manifest["total_bytes"])}，'
            f'耗时 {manifest["elapsed_seconds"]}s）'
        ))

        # ---------------- 6) 保留策略 ----------------
        keep = max(0, options['keep'])
        if keep:
            self._prune(out_root, keep, quiet=quiet)

        # 定时任务里最需要的两行：让日志能直接看出"这次备份在哪、多大"
        if quiet:
            self.stdout.write(f'OK {target} {manifest["total_bytes"]}')

    # ------------------------------------------------------------------
    def _backup_sqlite(self, source: Path, target: Path) -> None:
        """
        用 SQLite 的**在线备份 API** 拷库。

        为什么不能 `shutil.copy2`：服务运行中时，库文件可能正处于写事务中间，
        直接复制会拿到**不一致的快照**（恢复时报 "database disk image is malformed"）。
        `Connection.backup()` 是 SQLite 官方的在线备份接口，保证一致性。
        """
        src = sqlite3.connect(f'file:{source}?mode=ro', uri=True)
        try:
            dst = sqlite3.connect(str(target))
            try:
                src.backup(dst)
                # 顺带把完整性检查跑在源库上：备份一个已经损坏的库没有意义
                row = src.execute('PRAGMA integrity_check').fetchone()
                if row and row[0] != 'ok':
                    raise CommandError(f'源数据库完整性检查失败：{row[0]}')
            finally:
                dst.close()
        finally:
            src.close()

    def _make_tar(self, source_dir: Path, archive: Path) -> int:
        """把目录打成 tar.gz，返回文件个数"""
        count = 0
        with tarfile.open(archive, 'w:gz') as tar:
            for path in sorted(source_dir.rglob('*')):
                if not path.is_file():
                    continue
                tar.add(path, arcname=str(path.relative_to(source_dir)))
                count += 1
        return count

    def _make_tar_from_list(self, files: list[Path], base: Path, archive: Path) -> int:
        """把指定文件列表打成 tar.gz（保留相对 base 的路径）"""
        count = 0
        with tarfile.open(archive, 'w:gz') as tar:
            for path in files:
                tar.add(path, arcname=str(path.relative_to(base)))
                count += 1
        return count

    def _find_model_files(self) -> list[Path]:
        base = Path(settings.BASE_DIR)
        return sorted(
            path for path in base.rglob('*.pt')
            if 'site-packages' not in str(path) and 'node_modules' not in str(path)
        )

    def _dumpdata(self, target: Path) -> None:
        """生成 dumpdata JSON（只读、不碰网络）"""
        from io import StringIO

        from django.core.management import call_command

        buffer = StringIO()
        call_command(
            'dumpdata',
            '--natural-foreign', '--natural-primary',
            '--exclude', 'contenttypes', '--exclude', 'auth.permission',
            '--exclude', 'sessions',
            '--indent', '1',
            stdout=buffer,
        )
        target.write_text(buffer.getvalue(), encoding='utf-8')

    def _collect_counts(self) -> dict:
        """各业务表的条数（恢复后要拿它对比，所以键名要稳定、只增不改）"""
        from django.contrib.auth import get_user_model
        from api.models import Feedback, DetectionHistory, PestInfo, News
        from api.models_forum import Comment, ForumBoard, Post

        User = get_user_model()
        return {
            'users': User.objects.count(),
            'detections': DetectionHistory.objects.count(),
            'pests': PestInfo.objects.count(),
            'posts': Post.objects.count(),
            'comments': Comment.objects.count(),
            'boards': ForumBoard.objects.count(),
            'feedback': Feedback.objects.count(),
            'news': News.objects.count(),
        }

    def _prune(self, out_root: Path, keep: int, *, quiet: bool = False) -> None:
        """
        只保留最近 `keep` 份。

        安全约束：**只删"有清单的目录"**。备份根目录是用户给的路径（`--out`），
        万一指到了一个还有别的东西的目录，宁可不清理也不能删错。
        """
        backups = [p for p in bu.list_backups(out_root) if (p / bu.MANIFEST_NAME).exists()]
        removed = []
        for old in backups[keep:]:
            try:
                for child in old.rglob('*'):
                    if child.is_file():
                        child.unlink()
                for child in sorted(old.rglob('*'), reverse=True):
                    if child.is_dir():
                        child.rmdir()
                old.rmdir()
                removed.append(old.name)
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(self.style.WARNING(f'  ⚠ 清理旧备份失败 {old}：{exc}'))
        if removed and not quiet:
            self.stdout.write(f'  已清理 {len(removed)} 份旧备份：{", ".join(removed)}')
