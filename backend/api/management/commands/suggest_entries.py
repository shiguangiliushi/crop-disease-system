"""生成「待建词条清单」（第 372 批）

## 解决什么问题

管理端「建议补充的词条」只在页面上看得到，管理员要一条条抄下来再建词条。
这个命令把它导出成 **Markdown 清单 + CSV 模板**，可以直接照着补：

    python manage.py suggest_entries --days 30
    python manage.py suggest_entries --days 30 --out docs/待建词条清单.md
    python manage.py suggest_entries --csv 待建词条.csv

## 数据来源

`AssistantMessage.degrade_reason='no_source'` 的回答 → 找出它前面那条用户提问
（与 `views_assistant_admin._gap_questions` 同一口径），再复用 `_suggested_entries`
的聚类逻辑 —— **不另写一套规则**，否则页面和导出会给出不同的建议。

## CSV 模板

列与 `PestInfo` 的实际字段对齐（见 `backend/api/models.py`），
管理员填完可以直接被将来的导入命令吃进去。
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.views_assistant_admin import _gap_questions, _suggested_entries

#: CSV 列 —— 对齐 PestInfo 的必填/常用字段
CSV_COLUMNS = [
    'name', 'name_en', 'crop_type', 'english_identifier',
    'symptoms', 'description', '备注（来自哪些用户提问）',
]


class Command(BaseCommand):
    help = '按 no_source 反馈生成待建词条清单（Markdown / CSV）'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30, help='统计最近多少天（默认 30）')
        parser.add_argument('--limit', type=int, default=20, help='最多输出多少条建议')
        parser.add_argument('--out', type=str, default='', help='Markdown 输出路径（不填则打印到终端）')
        parser.add_argument('--csv', type=str, default='', help='同时导出 CSV 模板到该路径')

    def handle(self, *args, **options):
        from api.models_assistant import AssistantMessage

        since = timezone.now() - timezone.timedelta(days=options['days'])
        answers = AssistantMessage.objects.filter(
            role='assistant', degrade_reason='no_source', created_at__gte=since,
        ).select_related('session')

        if not answers.exists():
            self.stdout.write(self.style.WARNING(
                f'最近 {options["days"]} 天没有 no_source 记录 —— 说明这段时间没有"答不上来"的问题，'
                '或者助手还没被真实使用过。'))
            return

        gaps = _gap_questions(answers)
        suggestions = _suggested_entries(gaps)[: options['limit']]

        if not suggestions:
            self.stdout.write(self.style.WARNING('有 no_source 记录，但聚类没有提取出关键词'))
            return

        lines = [
            '# 待建词条清单',
            '',
            f'> 由 `manage.py suggest_entries` 生成于 {timezone.now():%Y-%m-%d %H:%M}，'
            f'统计最近 {options["days"]} 天的「答不上来」问题。',
            '>',
            '> 关键词出现次数越多，越说明用户真的在问、而库里没有。',
            '',
            '| 建议主题 | 出现次数 | 用户原话示例 |',
            '|---|---|---|',
        ]
        for item in suggestions:
            example = (item.get('examples') or [''])[0].replace('|', '／')
            lines.append(f'| {item["keyword"]} | {item["count"]} | {example} |')

        lines += [
            '',
            '## 怎么用这份清单',
            '',
            '1. 按「出现次数」从上往下补 —— 最高的那几条就是最值得写的；',
            '2. 补完跑一次 `python scripts/retrieval_baseline.py`，看 hit@1 有没有动；',
            '3. 再跑 `python manage.py suggest_entries --days 7` 确认该关键词从榜单上消失了。',
        ]
        markdown = '\n'.join(lines) + '\n'

        out_path = options['out']
        if out_path:
            target = Path(out_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(markdown, encoding='utf-8')
            self.stdout.write(self.style.SUCCESS(f'已写入 {target}（{len(suggestions)} 条建议）'))
        else:
            self.stdout.write(markdown)

        csv_path = options['csv']
        if csv_path:
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for item in suggestions:
                writer.writerow({
                    'name': item['keyword'],
                    '备注（来自哪些用户提问）': '；'.join(item.get('examples') or [])[:200],
                })
            target = Path(csv_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            # utf-8-sig：Excel 直接双击打开不乱码
            target.write_text(buffer.getvalue(), encoding='utf-8-sig')
            self.stdout.write(self.style.SUCCESS(f'CSV 模板已写入 {target}'))
