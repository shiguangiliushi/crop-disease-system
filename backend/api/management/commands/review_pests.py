"""标记病害词条"已复核"（第 243 批）

==================================================================
为什么需要它
==================================================================
`PestInfo` 第 243 批新增了 `reviewed_at`（最近一次人工复核时间），
但"怎么把时间写进去"要有入口。管理端的编辑表单也能改（`PestInfoWriteSerializer`
已接收该字段），可批量复核时一条条点太慢 —— 这个命令用来一次标记一批。

==================================================================
用法
==================================================================
    # 看哪些词条超期（不写库）
    python manage.py review_pests --stale

    # 标记全部已复核
    python manage.py review_pests --all

    # 只标记指定 id
    python manage.py review_pests --ids 1,3,7

    # 只标记超期的（配合定时任务）
    python manage.py review_pests --stale --apply
"""
from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.models import PestInfo

#: 超期阈值：文档写的是"每 1~2 年复核"，取上界 18 个月更宽容
STALE_DAYS = int(18 * 30)


class Command(BaseCommand):
    help = '标记病害词条的最近复核时间（reviewed_at）'

    def add_arguments(self, parser):
        parser.add_argument('--ids', default='', help='要标记的 id，逗号分隔')
        parser.add_argument('--all', action='store_true', help='标记全部词条')
        parser.add_argument('--stale', action='store_true', help='只处理超期（>18 个月未复核或从未复核）')
        parser.add_argument('--apply', action='store_true', help='与 --stale 搭配时才会真正写库（默认只打印）')

    def handle(self, *args, **options):
        now = timezone.now()
        queryset = PestInfo.objects.all()
        ids = [int(item) for item in (options.get('ids') or '').split(',') if item.strip().isdigit()]
        if ids:
            queryset = queryset.filter(id__in=ids)

        stale_before = now - dt.timedelta(days=STALE_DAYS)
        if options.get('stale'):
            queryset = queryset.filter(reviewed_at__isnull=True) | queryset.filter(reviewed_at__lt=stale_before)

        rows = list(queryset.order_by('id'))
        if not rows:
            self.stdout.write('没有匹配的词条')
            return

        if options.get('stale') and not options.get('apply') and not options.get('all'):
            self.stdout.write(self.style.WARNING(f'以下 {len(rows)} 条需要复核（加 --apply 才会写库）：'))
            for pest in rows:
                when = pest.reviewed_at.strftime('%Y-%m-%d') if pest.reviewed_at else '从未复核'
                self.stdout.write(f'  #{pest.id:<4} {pest.name:<20} 最近复核：{when}')
            return

        updated = queryset.update(reviewed_at=now)
        self.stdout.write(self.style.SUCCESS(
            f'已标记 {updated} 条词条为「{now.strftime("%Y-%m-%d %H:%M")} 已复核」'
        ))
