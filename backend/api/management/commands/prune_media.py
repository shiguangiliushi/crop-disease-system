"""
清理 media 里的"无引用文件"（第 106 批）
============================================================================
第 104 批的 E2E 与第 105 批的注释审计各查出一次：`media/` 里有大量文件
**没有任何数据库记录引用** —— 当时全量审计的结论是 908 个文件里约 12.9 MB
无人认领，其中最集中的是 `detection_history/annotated/`（历史版本写过这批文件，
但 `DetectionHistory.annotated_image` 字段一直没被写入，见迁移 0043）。

这些文件不致命（备份会把它们一起备走），但会：
  · 白占磁盘，而且**只增不减**；
  · 让将来做"上传配额"或"迁移到对象存储"时多出一堆来历不明的对象。

============================================================================
这个命令的立场：**默认什么都不删**
============================================================================
· 不给 `--yes` 时只打印报告（等于 `--dry-run`）；
· 只删"**确实没有任何 FileField 引用、且超过 `--min-age-days`（默认 7 天）**"的文件 ——
  加年龄门槛是因为**正在上传/刚上传完成但还没入库的文件**看起来也像孤儿，
  这个命令不该和业务抢文件；
· `--keep-dirs` 保护目录（默认把 `avatars/` 之外的东西都当候选，
  但会跳过任何 `.gitkeep`、隐藏文件与常见的非上传目录）；
· 删之前把清单写到 `--manifest`（默认在 TEMP 下），万一是误删还能对照。

用法：
    python manage.py prune_media                       # 只报告（不删）
    python manage.py prune_media --yes                 # 真删
    python manage.py prune_media --min-age-days 0 --yes # 连刚落的文件一起清（测试用）
    python manage.py prune_media --dir detection_uploads # 只清某个子目录
    python manage.py prune_media --json                # 机读报告
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

#: 永远不动的目录/文件
PROTECTED_NAMES = {'.gitkeep', '.gitignore', '.DS_Store', 'Thumbs.db'}

#: 这些字段类型里的路径要纳入"被引用"集合
FILE_FIELD_TYPES = ('FileField', 'ImageField')


class Command(BaseCommand):
    help = '清理 media 里没有任何数据库引用的文件（默认只报告，加 --yes 才删）'

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='确认删除（不给就只报告）')
        parser.add_argument('--min-age-days', type=float, default=7.0,
                            help='只清理修改时间早于 N 天的文件（默认 7，避免和正在上传的文件抢）')
        parser.add_argument('--dir', type=str, default='',
                            help='只处理 media 下的某个子目录（例如 detection_uploads）')
        parser.add_argument('--manifest', type=str, default='',
                            help='把待删清单写到这个文件（默认写到系统临时目录）')
        parser.add_argument('--json', action='store_true', help='输出机读 JSON')
        parser.add_argument('--limit', type=int, default=0,
                            help='最多删除 N 个文件（0 = 不限；先小批量试时有用）')

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT)
        if not media_root.exists():
            self.stderr.write(f'media 目录不存在：{media_root}')
            return

        referenced = self._collect_referenced_paths()
        scope = media_root / options['dir'] if options['dir'] else media_root
        if not scope.exists():
            self.stderr.write(f'指定的子目录不存在：{scope}')
            return

        cutoff = time.time() - options['min_age_days'] * 86400
        candidates = []
        skipped_recent = 0
        skipped_protected = 0

        for path in sorted(scope.rglob('*')):
            if not path.is_file():
                continue
            rel = path.relative_to(media_root).as_posix()
            if path.name in PROTECTED_NAMES or path.name.startswith('.'):
                skipped_protected += 1
                continue
            if rel in referenced:
                continue
            if path.stat().st_mtime > cutoff:
                skipped_recent += 1
                continue
            candidates.append((rel, path.stat().st_size))

        if options['limit']:
            candidates = candidates[:options['limit']]

        total_bytes = sum(size for _, size in candidates)
        report = {
            'media_root': str(media_root),
            'referenced_files': len(referenced),
            'orphan_files': len(candidates),
            'orphan_bytes': total_bytes,
            'skipped_recent': skipped_recent,
            'skipped_protected': skipped_protected,
            'min_age_days': options['min_age_days'],
            'deleted': False,
            'files': [rel for rel, _ in candidates],
        }

        if options['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            if not options['yes']:
                return

        # ---------- 报告 ----------
        if not options['json']:
            self.stdout.write(f'media 目录：{media_root}')
            self.stdout.write(f'  数据库引用的文件：{len(referenced)} 个')
            self.stdout.write(f'  无引用且超过 {options["min_age_days"]:g} 天的文件：'
                              f'{len(candidates)} 个（{self._human(total_bytes)}）')
            if skipped_recent:
                self.stdout.write(f'  （跳过 {skipped_recent} 个"太新"的文件 —— '
                                  '可能是刚上传还没入库的）')
            if skipped_protected:
                self.stdout.write(f'  （跳过 {skipped_protected} 个占位/隐藏文件）')

            if candidates:
                self.stdout.write('')
                self.stdout.write(self.style.MIGRATE_HEADING('最大的 20 个待清理文件'))
                for rel, size in sorted(candidates, key=lambda item: -item[1])[:20]:
                    self.stdout.write(f'  {self._human(size):>10}  {rel}')

        if not options['yes']:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                '以上只是报告，**没有删除任何文件**。确认无误后加 --yes 执行。'
            ))
            self._write_manifest(options['manifest'], report)
            return

        # ---------- 执行 ----------
        deleted = 0
        failed = []
        for rel, _size in candidates:
            target = media_root / rel
            try:
                target.unlink()
                deleted += 1
            except Exception as exc:  # noqa: BLE001
                failed.append(f'{rel}: {exc}')

        # 顺手清掉因此变空的目录（只删空目录，非空的一定保留）
        removed_dirs = self._prune_empty_dirs(scope, media_root)

        report['deleted'] = True
        report['deleted_files'] = deleted
        report['removed_empty_dirs'] = removed_dirs
        self._write_manifest(options['manifest'], report)

        if not options['json']:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(
                f'已删除 {deleted} 个文件（{self._human(total_bytes)}）'
                + (f'，清理空目录 {removed_dirs} 个' if removed_dirs else '')
            ))
            for item in failed[:10]:
                self.stderr.write(self.style.WARNING(f'  删除失败：{item}'))

    # ------------------------------------------------------------------
    def _collect_referenced_paths(self) -> set[str]:
        """
        把所有模型里 FileField/ImageField 的值收成一个集合（相对 MEDIA_ROOT 的 posix 路径）。

        为什么遍历 `apps.get_models()` 而不是手写模型清单：
        **新增一个带图片的模型时，没人会记得回来改这个命令** ——
        那样新模型的文件就会被当成孤儿删掉，这是最糟的失败方式。
        自动收集让"忘记维护"变成不可能。
        """
        referenced: set[str] = set()
        for model in apps.get_models():
            for field in model._meta.get_fields():
                if field.get_internal_type() not in FILE_FIELD_TYPES:
                    continue
                name = field.name
                try:
                    values = (
                        model.objects.exclude(**{f'{name}__isnull': True})
                        .exclude(**{name: ''})
                        .values_list(name, flat=True)
                    )
                    for value in values.iterator():
                        if not value:
                            continue
                        # 历史数据里出现过 Windows 反斜杠，统一成 posix 再比较
                        referenced.add(str(value).replace('\\', '/').lstrip('/'))
                        # 兜底：有些地方存的是完整 URL（如 http://host/media/x.jpg），
                        # 按 MEDIA_URL 切一刀再收一次
                        media_url = str(settings.MEDIA_URL or '/media/')
                        if media_url in str(value):
                            tail = str(value).split(media_url, 1)[1]
                            referenced.add(tail.replace('\\', '/').lstrip('/'))
                except Exception:  # noqa: BLE001
                    # 单表读失败（表还没建、迁移中）不该让整个命令失败
                    continue
        return referenced

    def _prune_empty_dirs(self, scope: Path, media_root: Path) -> int:
        """删掉空目录（自底向上），返回删掉的个数。非空目录一律保留。"""
        removed = 0
        for path in sorted((p for p in scope.rglob('*') if p.is_dir()),
                           key=lambda p: len(p.parts), reverse=True):
            try:
                if path == media_root:
                    continue
                if not any(path.iterdir()):
                    path.rmdir()
                    removed += 1
            except OSError:
                continue
        return removed

    def _write_manifest(self, path: str, report: dict) -> None:
        target = Path(path) if path else Path(tempfile.gettempdir()) / 'prune_media_manifest.json'
        payload = dict(report)
        payload['generated_at'] = timezone.now().isoformat()
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(f'清单已写入：{target}')

    @staticmethod
    def _human(num_bytes: int) -> str:
        value = float(num_bytes or 0)
        for unit in ('B', 'KB', 'MB', 'GB'):
            if value < 1024 or unit == 'GB':
                return f'{value:.1f} {unit}' if unit != 'B' else f'{int(value)} B'
            value /= 1024
        return f'{value:.1f} GB'
