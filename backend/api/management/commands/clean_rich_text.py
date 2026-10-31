"""清洗存量富文本里的脏 HTML（第 274 批）

## 为什么需要它

第 256 批给 `Post.save()` / `Comment.save()` 加了**保存时净化**，但那只对新数据生效 ——
库里第 256 批之前的帖子/评论仍然保留着原始 HTML（可能带 `onerror`、`<script>`）。
这是一条**遗留风险**：只要有任何一处渲染点忘了净化，旧数据仍能触发 XSS。

## 用法

    # 只看会改哪些（默认 dry-run，不写库）
    python manage.py clean_rich_text

    # 真正写库（先备份！）
    python manage.py clean_rich_text --apply

    # 只处理某张表
    python manage.py clean_rich_text --model post
    python manage.py clean_rich_text --model comment

## 安全约定

- **默认 dry-run**：宁可多跑一次，也不要手滑改坏数据；
- 逐条打印差异摘要（前 80 字），便于人工核对；
- `--apply` 时用 `save(update_fields=['content'])`，只动这一列，
  不会触发无关的更新时间戳/计数逻辑（`update_fields` 限定）。
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from api.models_forum import Comment, Post
from api.utils_html import sanitize_html


class Command(BaseCommand):
    help = '清洗存量帖子/评论里的脏 HTML（默认 dry-run）'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='真正写库（默认只预览）')
        parser.add_argument('--model', choices=['post', 'comment'], default='',
                            help='只处理指定表')
        parser.add_argument('--limit', type=int, default=0, help='最多扫描多少条（0 表示全部）')

    def handle(self, *args, **options):
        apply_changes = options['apply']
        only = options['model']
        limit = options['limit']

        targets = []
        if only in ('', 'post'):
            targets.append(('Post', Post))
        if only in ('', 'comment'):
            targets.append(('Comment', Comment))

        total_changed = 0
        for label, model in targets:
            queryset = model.objects.all().only('id', 'content')
            if limit:
                queryset = queryset[:limit]

            changed = 0
            for row in queryset.iterator():
                raw = row.content or ''
                clean = sanitize_html(raw)
                if clean == raw:
                    continue
                changed += 1
                preview = raw.replace('\n', ' ')[:80]
                self.stdout.write(f'  [{label}#{row.id}] {preview}')
                if apply_changes:
                    row.content = clean
                    row.save(update_fields=['content'])

            mode = '已写入' if apply_changes else '待清洗（dry-run）'
            self.stdout.write(self.style.WARNING(f'{label}: {changed} 条 {mode}'))
            total_changed += changed

        if not apply_changes and total_changed:
            self.stdout.write('')
            self.stdout.write('确认无误后加 `--apply` 执行（建议先备份数据库）。')
        if apply_changes:
            self.stdout.write(self.style.SUCCESS(f'完成，共清洗 {total_changed} 条。'))
