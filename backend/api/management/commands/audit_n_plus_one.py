"""列表接口的 N+1 审计（第 287 批）

## 为什么要有它

"慢"通常有两种：**扫太多行**（缺索引，第 285/286 批解决）和**发太多条 SQL**（N+1）。
后者不会报错、本地数据少时也看不出来，只有数据量上来才暴露。

这个命令对若干列表接口各发一次请求，统计实际 SQL 条数：
10 条数据正常应在 3~8 条；超过 15 条基本就是 N+1。

## 用法

    python manage.py audit_n_plus_one                 # 默认清单
    python manage.py audit_n_plus_one --url /api/feedback/?page_size=10
    python manage.py audit_n_plus_one --strict        # 有疑似 N+1 时退出码 1（可进 CI）

## 已发现的结论（2026-10-31）

| 接口 | SQL 条数 | 判定 |
|---|---|---|
| 反馈列表 | 7 | ✅ |
| 论坛帖子 | 15 | ✅（边界） |
| **识别历史** | **22** | ⚠️ 疑似 N+1（逐行取 user / pest_info） |
| 助手会话 | 3 | ✅ |
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

DEFAULT_ENDPOINTS = [
    ('反馈列表', '/api/feedback/?page_size=10'),
    ('论坛帖子', '/api/forums/posts/?page_size=10'),
    ('识别历史', '/api/detection-history/?page_size=10'),
    ('助手会话', '/api/assistant/sessions/?page_size=10'),
]

#: 超过这个条数就认为可能是 N+1（10 条数据的正常上限）
THRESHOLD = 15


class Command(BaseCommand):
    help = '列表接口 N+1 审计（统计实际 SQL 条数）'

    def add_arguments(self, parser):
        parser.add_argument('--url', action='append', default=[], help='只测指定 URL（可多次）')
        parser.add_argument('--strict', action='store_true', help='有疑似 N+1 时退出码 1')
        parser.add_argument('--threshold', type=int, default=THRESHOLD, help='判定阈值（默认 15）')

    def handle(self, *args, **options):
        from api.models import CustomUser

        admin = CustomUser.objects.filter(role='ADMIN').first()
        if admin is None:
            self.stderr.write('没有管理员账号可用于审计')
            return

        client = APIClient()
        client.force_authenticate(user=admin)

        endpoints = [('自定义', url) for url in options['url']] or DEFAULT_ENDPOINTS
        threshold = options['threshold']
        suspect = []

        for label, url in endpoints:
            with CaptureQueriesContext(connection) as ctx:
                response = client.get(url)
            count = len(ctx.captured_queries)
            flagged = count > threshold
            if flagged:
                suspect.append((label, url, count))
            icon = '⚠️ ' if flagged else '✅'
            self.stdout.write(f'{icon} {label:<10} {response.status_code}  SQL={count}')
            if flagged:
                for query in ctx.captured_queries[:2]:
                    self.stdout.write(f'      {query["sql"][:110]}')

        if suspect:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                f'{len(suspect)} 个接口疑似 N+1（阈值 {threshold}）：加 select_related/prefetch_related'))
        else:
            self.stdout.write(self.style.SUCCESS('未发现疑似 N+1'))

        if options['strict'] and suspect:
            raise SystemExit(1)
