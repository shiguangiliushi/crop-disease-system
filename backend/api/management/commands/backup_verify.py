"""
备份校验（第 102 批）

==================================================================
为什么"备份存在"不等于"备份可用"
==================================================================
最常见的灾难不是"没做备份"，而是**"以为有备份，真出事时发现恢复不了"**：
  · 文件在拷贝途中被截断（磁盘满、进程被杀、网络中断）；
  · 媒体包只打了一半；
  · 库文件是服务运行中直接 `copy` 的，内部不一致；
  · 备份目录里那份其实是几年前的，或者干脆是空目录。

所以这个命令不做"看一眼文件在不在"这种事，而是**真的把它读一遍**：
  1. 清单在不在、格式版本对不对；
  2. 每个产物的 **sha256 与清单是否一致**（这一条能抓出截断/篡改/静默损坏）；
  3. **把备份里的库打开**，跑 `PRAGMA integrity_check`，并**读出真实条数**；
  4. 媒体包的 gzip/tar 结构是否完整；
  5. 顺带对比"备份时记的条数"与"现在库里读出来的条数"。

==================================================================
用法
==================================================================
    python manage.py backup_verify                        # 校验最近一份
    python manage.py backup_verify --all                  # 校验全部（慢，媒体包要解压）
    python manage.py backup_verify 20261004-024456        # 校验指定的一份
    python manage.py backup_verify --skip-media           # 跳过媒体包校验（快）
    python manage.py backup_verify --strict                # 有任何问题就退出码 1（给定时任务用）
"""
from __future__ import annotations

import gzip
import sqlite3
import tarfile
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api import backup_utils as bu

#: 备份里的库打开后要读的表 → 输出用的人类可读名
#:
#: ⚠️ 表名**不要靠猜**：论坛模型放在 `models_forum.py`（不是 `models.py`），
#: 它们的表名是 `api_post` / `api_comment` / `api_forumboard`，**不是**
#: `api_forum_post` 之类。第一版就是猜的，校验时 3 张表报"表不存在"——
#: 而那是**校验脚本自己写错**，不是备份有问题。这里的名字都核对过
#: （`Model._meta.db_table`），要改请先核对再改。
COUNT_QUERIES = {
    'users': 'SELECT COUNT(*) FROM api_customuser',
    'detections': 'SELECT COUNT(*) FROM api_detectionhistory',
    'pests': 'SELECT COUNT(*) FROM api_pestinfo',
    'posts': 'SELECT COUNT(*) FROM api_post',
    'comments': 'SELECT COUNT(*) FROM api_comment',
    'boards': 'SELECT COUNT(*) FROM api_forumboard',
    'feedback': 'SELECT COUNT(*) FROM api_feedback',
    'news': 'SELECT COUNT(*) FROM api_news',
}


class Command(BaseCommand):
    help = '校验备份的完整性（校验和 + 库完整性 + 真实条数 + 媒体包结构）'

    def add_arguments(self, parser):
        parser.add_argument('name', nargs='?', default='',
                            help='备份目录名（默认校验最近一份）')
        parser.add_argument('--dir', type=str, default='',
                            help='备份根目录（默认同 backend_backup）')
        parser.add_argument('--all', action='store_true', help='校验全部备份')
        parser.add_argument('--skip-media', action='store_true', help='跳过媒体包校验（更快）')
        parser.add_argument('--strict', action='store_true',
                            help='发现任何问题就以退出码 1 结束（定时任务/CI 用）')

    def handle(self, *args, **options):
        root = Path(options['dir']).expanduser() if options['dir'] else bu.backup_root()

        if options['all']:
            targets = bu.list_backups(root)
            if not targets:
                raise CommandError(f'{root} 下没有任何备份目录')
        elif options['name']:
            targets = [root / options['name']]
            if not targets[0].exists():
                raise CommandError(f'找不到备份：{targets[0]}')
        else:
            targets = bu.list_backups(root)[:1]
            if not targets:
                raise CommandError(f'{root} 下没有任何备份目录（先跑 backend_backup）')

        total_problems = 0
        for target in targets:
            total_problems += self._verify_one(target, skip_media=options['skip_media'])
            self.stdout.write('')

        if total_problems:
            self.stdout.write(self.style.ERROR(f'共发现 {total_problems} 个问题'))
            if options['strict']:
                raise SystemExit(1)
        else:
            self.stdout.write(self.style.SUCCESS('全部校验通过：备份可用'))

    # ------------------------------------------------------------------
    def _verify_one(self, target: Path, *, skip_media: bool) -> int:
        problems = 0
        name = target.name
        self.stdout.write(self.style.MIGRATE_HEADING(f'校验 {name}'))

        def ok(text):
            self.stdout.write(f'  ✓ {text}')

        def bad(text):
            nonlocal problems
            problems += 1
            self.stdout.write(self.style.ERROR(f'  ✗ {text}'))

        def warn(text):
            self.stdout.write(self.style.WARNING(f'  ⚠ {text}'))

        # ---------- 1) 清单 ----------
        manifest_path = target / bu.MANIFEST_NAME
        if not manifest_path.exists():
            bad(f'缺少 {bu.MANIFEST_NAME} —— 这份备份不完整，无法校验')
            return problems
        try:
            manifest = bu.read_json(manifest_path)
        except Exception as exc:  # noqa: BLE001
            bad(f'{bu.MANIFEST_NAME} 解析失败：{exc}')
            return problems

        version = manifest.get('format_version')
        if version != bu.BACKUP_FORMAT_VERSION:
            bad(f'格式版本不匹配：清单是 {version}，当前支持 {bu.BACKUP_FORMAT_VERSION}')
        else:
            ok(f'清单可读（格式 v{version}，创建于 {manifest.get("created_at", "?")[:19]}）')

        artifacts = manifest.get('artifacts') or {}
        if not artifacts:
            bad('清单里没有记录任何产物')
            return problems

        # ---------- 2) 产物的存在性 + 校验和 + 体积 ----------
        for rel, info in artifacts.items():
            path = target / rel
            if not path.exists():
                bad(f'{rel} 缺失')
                continue
            actual_bytes = path.stat().st_size
            expected_bytes = info.get('bytes')
            if expected_bytes is not None and actual_bytes != expected_bytes:
                bad(f'{rel} 体积不符：期望 {bu.human_size(expected_bytes)}，实际 {bu.human_size(actual_bytes)}'
                    '（典型的拷贝被截断）')
                continue
            if info.get('sha256'):
                started = time.perf_counter()
                actual = bu.sha256_file(path)
                if actual != info['sha256']:
                    bad(f'{rel} 校验和不符（文件已损坏或被改动）')
                else:
                    ok(f'{rel} 校验和一致（{bu.human_size(actual_bytes)}，'
                       f'{time.perf_counter() - started:.1f}s）')
            else:
                warn(f'{rel} 清单里没有校验和（旧格式备份），只核对了体积')

        # ---------- 3) 打开备份里的库，读真实条数 ----------
        db_path = target / bu.DB_NAME
        if db_path.exists():
            counts, db_problems = self._verify_db(db_path, manifest)
            for text in db_problems:
                bad(text)
            if not db_problems:
                ok('库完整性 OK，条数：' + '、'.join(f'{k}={v}' for k, v in counts.items()))
        else:
            bad(f'缺少 {bu.DB_NAME}（没有数据库副本的备份不能用于恢复）')

        # ---------- 4) 媒体包结构 ----------
        media_archive = target / bu.MEDIA_ARCHIVE
        if media_archive.exists() and not skip_media:
            started = time.perf_counter()
            files, media_problems = self._verify_tar(media_archive)
            for text in media_problems:
                bad(text)
            if not media_problems:
                expected = (manifest.get('artifacts', {}).get(bu.MEDIA_ARCHIVE, {}) or {}).get('files')
                ok(f'媒体包结构 OK（{files} 个文件'
                   + (f'，清单记录 {expected}' if expected else '')
                   + f'，{time.perf_counter() - started:.1f}s）')
                if expected is not None and files != expected:
                    warn(f'媒体文件数与清单不一致（清单 {expected}，实际 {files}）')

        return problems

    # ------------------------------------------------------------------
    def _verify_db(self, db_path: Path, manifest: dict) -> tuple[dict, list[str]]:
        """打开备份里的库，做完整性检查并读出条数"""
        problems: list[str] = []
        counts: dict[str, int] = {}
        try:
            conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        except Exception as exc:  # noqa: BLE001
            return counts, [f'无法打开备份中的数据库：{exc}']
        try:
            row = conn.execute('PRAGMA integrity_check').fetchone()
            if not row or row[0] != 'ok':
                problems.append(f'库完整性检查未通过：{row[0] if row else "无返回"}')
                return counts, problems

            for key, sql in COUNT_QUERIES.items():
                try:
                    counts[key] = conn.execute(sql).fetchone()[0]
                except Exception as exc:  # noqa: BLE001
                    problems.append(f'读 {key} 条数失败（表可能不存在）：{exc}')

            # 与清单对比：这是"备份到底有没有内容"的硬证据
            recorded = manifest.get('counts') or {}
            for key, value in counts.items():
                if key in recorded and recorded[key] != value:
                    problems.append(
                        f'{key} 条数与清单不符：清单 {recorded[key]}，备份里 {value}'
                    )
        finally:
            conn.close()
        return counts, problems

    # ------------------------------------------------------------------
    def _verify_tar(self, archive: Path) -> tuple[int, list[str]]:
        """
        校验 tar.gz 的结构完整性。

        为什么用"边读边数"而不是 `tarfile.getmembers()`：`getmembers()` 只读索引，
        **不会解压数据流** —— 一个被截断的包照样能列出成员名。逐块 `extractfile().read()`
        才会真的把 gzip 流走完，从而发现截断。
        """
        problems: list[str] = []
        files = 0
        try:
            with tarfile.open(archive, 'r:gz') as tar:
                for member in tar:
                    if not member.isfile():
                        continue
                    handle = tar.extractfile(member)
                    if handle is None:
                        problems.append(f'{member.name} 无法读取')
                        continue
                    while True:
                        block = handle.read(bu.CHUNK)
                        if not block:
                            break
                    files += 1
        except (tarfile.TarError, gzip.BadGzipFile, EOFError, OSError) as exc:
            problems.append(f'媒体包损坏（读到第 {files} 个文件时失败）：{exc}')
        return files, problems
