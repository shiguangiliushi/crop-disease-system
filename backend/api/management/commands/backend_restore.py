"""
从备份恢复（第 102 批）

==================================================================
这个命令的默认行为是"**换掉**"，不是"合并"
==================================================================
两种语义差别很大，必须说清楚（也让调用方显式选择）：

| 模式 | 行为 | 适用场景 |
|---|---|---|
| **replace（默认）** | 用备份里的库**整体替换**当前库；媒体默认解包**覆盖**同名文件 | "数据被删了/库坏了，回到备份那一刻" |
| **merge（`--merge`）** | 保留当前库，把备份里的行**按主键 upsert** 进去 | "只想把某些丢失的记录捞回来" |

为什么默认是 replace：备份的语义就是"那一刻的快照"。默认 merge 会让人以为
"恢复完成了"，实际库里是两批数据混在一起（主键冲突的被覆盖、没冲突的留着），
**比明确替换更难排查**。

==================================================================
四道安全网（缺一条都可能把事故扩大）
==================================================================
1. **必须显式 `--yes`**：没有它只打印计划就退出。
   （旧 `forum_backup restore` 用 `input()` 交互确认 —— 定时任务/管道里会直接卡死，
   而且任何人误敲回车就开删。）
2. **先校验备份**：直接复用 `backup_verify` 的逻辑。恢复一份损坏的备份 =
   用坏数据覆盖好数据，是**把事故从"数据丢了"升级成"数据彻底没了"**。
3. **恢复前自动做一份"恢复前快照"**：万一备份不是想要的那一份，还能退回来。
4. **数据库文件先另存为 `.pre-restore`**，再写新库：写一半失败也能人工救回。

==================================================================
用法
==================================================================
    python manage.py backend_restore --list                  # 列出可用备份
    python manage.py backend_restore <名字>                   # 只看计划（不写任何东西）
    python manage.py backend_restore <名字> --yes             # 真的恢复（库 + 媒体）
    python manage.py backend_restore <名字> --yes --db-only    # 只恢复数据库
    python manage.py backend_restore <名字> --yes --merge      # 按主键合并而不是替换
    python manage.py backend_restore <名字> --yes --yes-overwrite-media  # 媒体也覆盖

⚠️ 恢复后请**重启后端进程**：SQLite 连接与 Django 缓存里可能还留着旧状态。
"""
from __future__ import annotations

import shutil
import sqlite3
import tarfile
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from api import backup_utils as bu
from api.management.commands.backup_verify import COUNT_QUERIES


class Command(BaseCommand):
    help = '从备份恢复数据库与媒体（默认整体替换；带校验与恢复前快照）'

    def add_arguments(self, parser):
        parser.add_argument('name', nargs='?', default='', help='备份目录名；用 --list 查看')
        parser.add_argument('--dir', type=str, default='', help='备份根目录（默认同 backend_backup）')
        parser.add_argument('--list', action='store_true', help='列出所有备份后退出')
        parser.add_argument('--yes', action='store_true', help='确认执行（没有它只打印计划）')
        parser.add_argument('--db-only', action='store_true', help='只恢复数据库，不动媒体')
        parser.add_argument('--media-only', action='store_true', help='只恢复媒体，不动数据库')
        parser.add_argument('--merge', action='store_true',
                            help='按主键合并备份里的行（保留当前库中更新的记录），而不是整体替换')
        parser.add_argument('--overwrite-media', action='store_true',
                            help='解包媒体时覆盖同名文件（默认**不覆盖**，只补缺失的 —— 更安全）')
        parser.add_argument('--no-safety-backup', action='store_true',
                            help='不做"恢复前快照"（不推荐；磁盘紧张时才用）')
        parser.add_argument('--skip-verify', action='store_true',
                            help='跳过校验和检查（不推荐；只在备份确实完好但清单丢失时用）')

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        root = Path(options['dir']).expanduser() if options['dir'] else bu.backup_root()

        if options['list']:
            return self._list(root)

        if not options['name']:
            raise CommandError('请给出备份目录名（用 --list 查看），例如：'
                               'python manage.py backend_restore 20261004-024456 --yes')

        target = root / options['name']
        if not target.exists():
            raise CommandError(f'找不到备份目录：{target}')

        do_db = not options['media_only']
        do_media = not options['db_only']

        # ---------- 1) 先校验（安全网 2） ----------
        manifest = self._load_manifest(target)
        if not options['skip_verify']:
            self.stdout.write('先校验备份……')
            problems = self._verify(target, manifest)
            if problems:
                self.stdout.write(self.style.ERROR('备份校验未通过，已中止（不拿坏数据覆盖好数据）：'))
                for item in problems:
                    self.stdout.write(self.style.ERROR(f'  · {item}'))
                self.stdout.write('如确认备份可用（例如清单丢失），可加 --skip-verify，风险自负。')
                raise SystemExit(1)
            self.stdout.write(self.style.SUCCESS('  ✓ 校验通过'))

        # ---------- 2) 打印计划 ----------
        db_path = Path(settings.DATABASES['default']['NAME'])
        media_root = Path(settings.MEDIA_ROOT)
        counts = manifest.get('counts') or {}
        mode = '合并（--merge）' if options['merge'] else '整体替换'
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('恢复计划'))
        self.stdout.write(f'  备份      ：{target}')
        self.stdout.write(f'  创建时间  ：{str(manifest.get("created_at"))[:19]}'
                          f'（{self._age_text(manifest)}）')
        self.stdout.write(f'  备份条数  ：' + '、'.join(f'{k}={v}' for k, v in counts.items()))
        if do_db:
            self.stdout.write(f'  数据库    ：{db_path}  ←  {mode}')
        if do_media:
            self.stdout.write(
                f'  媒体目录  ：{media_root}  ←  '
                + ('覆盖同名文件' if options['overwrite_media'] else '只补缺失文件（不覆盖）')
            )
        if not options['yes']:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                '以上只是计划，**没有修改任何数据**。确认无误后加 --yes 执行。'
            ))
            return

        # ---------- 3) 恢复前快照（安全网 3） ----------
        if not options['no_safety_backup']:
            self.stdout.write('')
            self.stdout.write('生成恢复前快照（万一恢复错了可以退回来）……')
            safety_dir = self._safety_backup(db_path, media_root, do_db=do_db, do_media=do_media)
            if safety_dir:
                self.stdout.write(self.style.SUCCESS(f'  ✓ 快照：{safety_dir}'))
            else:
                self.stdout.write(self.style.WARNING(
                    '  ⚠ 快照生成失败（继续恢复，但你现在没有回头路）'
                ))

        # ---------- 4) 执行 ----------
        self.stdout.write('')
        started = time.perf_counter()
        if do_db:
            self._restore_db(target, db_path, merge=options['merge'])
        if do_media:
            self._restore_media(target, media_root, overwrite=options['overwrite_media'])

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'恢复完成（耗时 {time.perf_counter() - started:.1f}s）'
        ))
        self.stdout.write(self.style.WARNING(
            '⚠️ 请**重启后端进程**：SQLite 连接与 Django 缓存里可能还留着旧状态。'
        ))
        if do_db:
            self._print_counts(db_path)

    # ------------------------------------------------------------------
    def _list(self, root: Path) -> None:
        backups = bu.list_backups(root)
        if not backups:
            self.stdout.write(f'{root} 下没有任何备份')
            return
        self.stdout.write(f'备份目录：{root}')
        for path in backups:
            manifest = {}
            if (path / bu.MANIFEST_NAME).exists():
                try:
                    manifest = bu.read_json(path / bu.MANIFEST_NAME)
                except Exception:  # noqa: BLE001
                    manifest = {}
            size = bu.human_size(manifest.get('total_bytes') or 0)
            counts = manifest.get('counts') or {}
            self.stdout.write(
                f'  {path.name}  {str(manifest.get("created_at", "?"))[:19]}  {size}  '
                f'帖 {counts.get("posts", "?")} / 识别 {counts.get("detections", "?")} '
                f'/ 用户 {counts.get("users", "?")}'
            )

    def _load_manifest(self, target: Path) -> dict:
        manifest_path = target / bu.MANIFEST_NAME
        if not manifest_path.exists():
            raise CommandError(f'备份缺少 {bu.MANIFEST_NAME}：{target}（无法确认里面有什么）')
        return bu.read_json(manifest_path)

    def _verify(self, target: Path, manifest: dict) -> list[str]:
        """只做"能不能安全恢复"必需的检查：校验和 + 库可读"""
        problems: list[str] = []
        for rel, info in (manifest.get('artifacts') or {}).items():
            path = target / rel
            if not path.exists():
                # data.json 缺失不影响恢复（它只是补充）
                if rel == 'data.json':
                    continue
                problems.append(f'{rel} 缺失')
                continue
            if info.get('sha256') and bu.sha256_file(path) != info['sha256']:
                problems.append(f'{rel} 校验和不符（备份已损坏）')

        db_file = target / bu.DB_NAME
        if db_file.exists():
            try:
                conn = sqlite3.connect(f'file:{db_file}?mode=ro', uri=True)
                try:
                    row = conn.execute('PRAGMA integrity_check').fetchone()
                    if not row or row[0] != 'ok':
                        problems.append(f'备份里的数据库完整性检查失败：{row[0] if row else "无返回"}')
                finally:
                    conn.close()
            except Exception as exc:  # noqa: BLE001
                problems.append(f'无法打开备份里的数据库：{exc}')
        else:
            problems.append(f'缺少 {bu.DB_NAME}')
        return problems

    def _age_text(self, manifest: dict) -> str:
        """"这是多久以前的备份" —— 恢复前最该看一眼的信息"""
        raw = manifest.get('created_at')
        if not raw:
            return '时间未知'
        try:
            from datetime import datetime
            created = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
            delta = timezone.now() - created
            hours = delta.total_seconds() / 3600
            if hours < 1:
                return f'{int(delta.total_seconds() // 60)} 分钟前'
            if hours < 48:
                return f'{hours:.1f} 小时前'
            return f'{delta.days} 天前'
        except Exception:  # noqa: BLE001
            return '时间解析失败'

    # ------------------------------------------------------------------
    def _safety_backup(self, db_path: Path, media_root: Path, *, do_db: bool, do_media: bool):
        """
        恢复前快照：调用同一个 backend_backup 命令（复用而不是另写一套）。

        失败**不阻断**恢复（磁盘满时也要允许人先把数据救回来），但要明确告知。
        """
        from io import StringIO

        from django.core.management import call_command

        try:
            buffer = StringIO()
            call_command(
                'backend_backup',
                label='pre-restore',
                no_media=not do_media,
                no_data_dump=True,     # 快照只求快，不需要文本摘要
                quiet=True,
                stdout=buffer,
            )
            line = buffer.getvalue().strip().splitlines()[-1] if buffer.getvalue().strip() else ''
            return line.replace('OK ', '', 1) if line.startswith('OK ') else line
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(f'  快照失败：{exc}')
            return None

    # ------------------------------------------------------------------
    def _restore_db(self, target: Path, db_path: Path, *, merge: bool) -> None:
        source = target / bu.DB_NAME
        if merge:
            self._merge_db(source, db_path)
            return

        # 安全网 4：先把现有库另存，再写新库
        if db_path.exists():
            keep = db_path.with_suffix(db_path.suffix + '.pre-restore')
            shutil.copy2(db_path, keep)
            self.stdout.write(f'  旧库已另存：{keep.name}')

        # 用 SQLite 在线备份 API **写回**（而不是 copy2）：
        # 这样即使有连接开着，也会以事务方式替换内容，避免"复制到一半的库"
        src = sqlite3.connect(f'file:{source}?mode=ro', uri=True)
        try:
            dst = sqlite3.connect(str(db_path))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        self.stdout.write(self.style.SUCCESS(f'  ✓ 数据库已从备份替换（{bu.human_size(source.stat().st_size)}）'))

    def _merge_db(self, source: Path, db_path: Path) -> None:
        """
        合并模式：把备份库里**当前库也有的表的行**按主键 upsert 进去。

        为什么用原始 SQL 而不是 Django ORM：
          · 备份是**另一个文件**，ORM 只认 settings 里那一个连接；
          · `ATTACH DATABASE` 是 SQLite 的标准做法，一条 SQL 就能把整表并进来，
            比"读出来再逐行 update_or_create"快几个数量级，也不受模型定义变化影响。
        仍然**保留当前库中更新的记录**：冲突时取 `excluded`（备份值）还是现值，
        这里选择**备份值优先但只覆盖"当前库缺失的行"** —— 用 WHERE NOT EXISTS 判断。
        """
        self.stdout.write('  合并模式：只补齐当前库**缺失**的行（不覆盖已有记录）')
        conn = sqlite3.connect(str(db_path))
        merged = {}
        try:
            conn.execute('ATTACH DATABASE ? AS backup', (str(source),))
            current_tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'api_%'"
                )
            }
            backup_tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM backup.sqlite_master WHERE type='table' AND name LIKE 'api_%'"
                )
            }
            for table in sorted(current_tables & backup_tables):
                try:
                    cursor = conn.execute(
                        f'INSERT OR IGNORE INTO main."{table}" '
                        f'SELECT * FROM backup."{table}"'
                    )
                    if cursor.rowcount:
                        merged[table] = cursor.rowcount
                except Exception as exc:  # noqa: BLE001
                    # 单表失败（例如两边列不一致）不该让整次合并回滚，但要说出来
                    self.stderr.write(self.style.WARNING(f'  ⚠ 合并 {table} 失败：{exc}'))
            conn.commit()
            conn.execute('DETACH DATABASE backup')
        finally:
            conn.close()

        if merged:
            summary = '、'.join(f'{k}={v}' for k, v in sorted(merged.items()))
            self.stdout.write(self.style.SUCCESS(f'  ✓ 合并补齐行数：{summary}'))
        else:
            self.stdout.write('  （当前库没有缺失的行，未改动任何记录）')

    def _restore_media(self, target: Path, media_root: Path, *, overwrite: bool) -> None:
        archive = target / bu.MEDIA_ARCHIVE
        if not archive.exists():
            self.stdout.write(self.style.WARNING('  ⚠ 备份里没有媒体包，跳过'))
            return

        media_root.mkdir(parents=True, exist_ok=True)
        extracted = skipped = 0
        with tarfile.open(archive, 'r:gz') as tar:
            for member in tar:
                if not member.isfile():
                    continue
                destination = media_root / member.name
                # 防目录穿越：备份包的成员名理论上是我们自己写的，
                # 但恢复是"读外部文件"的操作，必须按不可信输入处理。
                try:
                    destination.resolve().relative_to(media_root.resolve())
                except ValueError:
                    self.stderr.write(self.style.WARNING(f'  ⚠ 跳过可疑路径：{member.name}'))
                    continue

                if destination.exists() and not overwrite:
                    skipped += 1
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                handle = tar.extractfile(member)
                if handle is None:
                    continue
                with open(destination, 'wb') as out:
                    shutil.copyfileobj(handle, out, length=bu.CHUNK)
                extracted += 1

        self.stdout.write(self.style.SUCCESS(
            f'  ✓ 媒体已恢复：写入 {extracted} 个文件'
            + (f'，跳过已存在的 {skipped} 个（需要覆盖请加 --overwrite-media）' if skipped else '')
        ))

    def _print_counts(self, db_path: Path) -> None:
        """恢复后立刻把条数打出来 —— 这是"数据真的回来了"最直接的证据"""
        try:
            conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
            try:
                parts = []
                for key, sql in COUNT_QUERIES.items():
                    try:
                        parts.append(f'{key}={conn.execute(sql).fetchone()[0]}')
                    except Exception:  # noqa: BLE001
                        parts.append(f'{key}=?')
                self.stdout.write('恢复后条数：' + '、'.join(parts))
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(f'  读取恢复后条数失败：{exc}')
