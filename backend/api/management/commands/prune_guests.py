"""删除"过期未活动"的游客试用账号（第 439 批）。

============================================================================
为什么需要这个命令
============================================================================
游客试用每有一个新访客就建一个 `CustomUser`（`is_guest=True`）。
不清理的话，`api_customuser` 表会**只增不减** —— 而且增长来源是"爬虫 + 面试官"，
既不能靠"用户自觉"控制，也不会自己停下来。

删除是**级联**的：识别历史、助手会话/消息、设备 token 会跟着走（外键都是 CASCADE）。
图片文件不在这里删 —— 删完用户后它们就没有 FileField 引用了，
由每天 04:00 的 `prune_media --min-age-days 7` 收走（见 docs/部署与运维.md）。

============================================================================
立场：默认什么都不删
============================================================================
与 `prune_media` 一致 —— 不给 `--yes` 只出报告。

用法：
    python manage.py prune_guests                  # 只报告（3 天未活动的游客）
    python manage.py prune_guests --yes            # 真删
    python manage.py prune_guests --days 0 --yes   # 连"刚建的"一起删（测试用）
    python manage.py prune_guests --json           # 机读报告
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from api import guest


class Command(BaseCommand):
    help = '删除超过 N 天没有活动的游客试用账号（默认 3 天，默认只报告不删）'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=3,
                            help='多少天没活动算过期（按 DeviceToken.last_seen，默认 3）')
        parser.add_argument('--yes', action='store_true',
                            help='真的删除。不加这个参数只打印报告')
        parser.add_argument('--json', action='store_true', dest='as_json',
                            help='输出机读 JSON')

    def handle(self, *args, **options):
        days = options['days']
        dry_run = not options['yes']

        result = guest.purge(days, dry_run=dry_run)

        if options['as_json']:
            self.stdout.write(json.dumps(result, ensure_ascii=False))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'[dry-run] {days} 天未活动的游客账号：{result["candidates"]} 个'))
            self.stdout.write('确认无误后加 --yes 才会真正删除。')
            return

        self.stdout.write(self.style.SUCCESS(
            f'已删除游客账号：{result["deleted"]} 个（候选 {result["candidates"]} 个）'))
        self.stdout.write(
            '图片文件没有在这里删 —— 它们现在已无引用，'
            '下一次 prune_media --min-age-days 7 会把它们收走。')
