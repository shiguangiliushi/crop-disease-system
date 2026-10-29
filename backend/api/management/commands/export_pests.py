"""导出病害百科（PestInfo + 防治方法）为 CSV / XLSX（第 242 批）

==================================================================
为什么需要它
==================================================================
百科的批量**导入**早就有了（`kb` 系列命令），但**没有导出**：

  · 想把 38 条词条交给老师/同伴校对，只能进 Django admin 一条条看；
  · 改了内容想留一份"改动前快照"，没有现成手段；
  · 论文/答辩材料里要附"知识库清单"，得手抄。

这个命令把词条（含防治方法条数、来源链接）导出成表格，可直接用 Excel 打开。

==================================================================
用法
==================================================================
    # 默认导出 CSV（UTF-8 BOM，Excel 双击不乱码）到 backend/exports/
    python manage.py export_pests

    # 导出 Excel
    python manage.py export_pests --format xlsx

    # 指定输出路径
    python manage.py export_pests --format xlsx --out D:/百科清单.xlsx

    # 只导某类作物
    python manage.py export_pests --crop 番茄

==================================================================
⚠️ 与 i18n 的关系
==================================================================
每一列都是**数据**（name / name_en 各一列），不是界面文案 —— 导出的是原始字段，
不按当前界面语言过滤（否则中英对照的信息就丢了）。
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from api.models import PestInfo
from api.xlsx import build_workbook

HEADERS = [
    'id', 'name', 'name_en', 'crop_type', 'crop_type_en', 'english_identifier',
    'symptoms', 'description', 'prevention_count', 'sources_count', 'sources',
]


class Command(BaseCommand):
    help = '导出病害百科（PestInfo）为 CSV / XLSX'

    def add_arguments(self, parser):
        parser.add_argument('--format', choices=('csv', 'xlsx'), default='csv', help='导出格式')
        parser.add_argument('--out', default='', help='输出文件路径（默认 backend/exports/pests_<时间>.<格式>）')
        parser.add_argument('--crop', default='', help='只导某类作物（按 crop_type 或 crop_type_en 包含匹配）')

    def handle(self, *args, **options):
        queryset = PestInfo.objects.all().prefetch_related('prevention_methods').order_by('id')
        crop = (options.get('crop') or '').strip()
        if crop:
            queryset = queryset.filter(crop_type__icontains=crop) | queryset.filter(crop_type_en__icontains=crop)

        rows = [self._row(pest) for pest in queryset]
        fmt = options['format']
        out_path = self._resolve_out(options.get('out'), fmt)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if fmt == 'xlsx':
            content = build_workbook(
                HEADERS,
                rows,
                sheet_name='病害百科',
                column_widths=[6, 26, 26, 14, 16, 26, 60, 60, 10, 10, 60],
            )
            out_path.write_bytes(content)
        else:
            # utf-8-sig：不加 BOM 时 Excel 打开中文全是乱码（Windows 上最常踩的坑）
            with out_path.open('w', encoding='utf-8-sig', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(HEADERS)
                writer.writerows(rows)

        self.stdout.write(self.style.SUCCESS(
            f'导出完成：{len(rows)} 条 → {out_path}（{fmt.upper()}）'
        ))
        return str(out_path)

    @staticmethod
    def _row(pest: PestInfo) -> list:
        prevention = list(pest.prevention_methods.all())
        sources = pest.sources if isinstance(pest.sources, list) else []
        return [
            pest.id,
            pest.name,
            pest.name_en,
            pest.crop_type,
            pest.crop_type_en,
            pest.english_identifier,
            pest.symptoms,
            pest.description,
            len(prevention),
            len(sources),
            '; '.join(str(item) for item in sources),
        ]

    @staticmethod
    def _resolve_out(raw: str, fmt: str) -> Path:
        if raw:
            return Path(raw).expanduser().resolve()
        stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        return Path(settings.BASE_DIR) / 'exports' / f'pests_{stamp}.{fmt}'
