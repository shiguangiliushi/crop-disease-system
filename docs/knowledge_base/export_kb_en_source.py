"""导出 K4 待翻译清单（第 197 批）—— 给翻译环节提供**确定的输入**。

导出成 JSON 而不是让翻译方直接查库，原因有两个：
  1. 翻译产物可以**先变成文件**，再由 `apply_kb_en.py` 统一写库 —— 这一步可复核、可重放；
  2. 避免翻译环节对数据库有任何写权限（它只该产出文本）。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, r"D:\新建文件夹\crop-disease-system\backend")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crop_disease_backend.settings")

import django  # noqa: E402
django.setup()

from api.models import CropHealthProfile, PestInfo, PreventionMethod  # noqa: E402

OUT = str(Path(__file__).resolve().parent / "kb_en_source.json")


def blank(v):
    return not str(v or '').strip()


data = {'diseases': [], 'methods': [], 'profiles': []}

# ── 一、病害：症状与发病规律（英文侧目前只有旧的 PlantVillage 摘要，需按中文重写）──
for pest in PestInfo.objects.exclude(english_identifier__endswith='_healthy').order_by('id'):
    data['diseases'].append({
        'identifier': pest.english_identifier,
        'name': pest.name,
        'crop_type': pest.crop_type,
        'name_en': pest.name_en,
        'crop_type_en': pest.crop_type_en,
        'symptoms_zh': pest.symptoms or '',
        'description_zh': pest.description or '',
        'symptoms_en_old': pest.symptoms_en or '',
        'description_en_old': pest.description_en or '',
    })

# ── 二、防治措施：全部为空（130 条）──
for method in PreventionMethod.objects.select_related('pest').order_by('pest_id', 'category'):
    if not (method.pest.english_identifier or '').endswith('_healthy'):
        data['methods'].append({
            'pest_identifier': method.pest.english_identifier,
            'pest_name': method.pest.name,
            'category': method.category,
            'category_display': method.get_category_display(),
            'measure_zh': method.measure or '',
            'measure_en_old': method.measure_en or '',
        })

# ── 三、作物健康档案：7 个维度全空（12×7 = 84 项）──
DIMS = ('morphology', 'growing_conditions', 'care_agricultural', 'care_chemical',
        'care_ecological', 'care_physical', 'care_monitoring')
for profile in CropHealthProfile.objects.order_by('id'):
    item = {
        'crop_type': profile.crop_type,
        'name': profile.name,
        'crop_type_en': profile.crop_type_en,
        'scientific_name': profile.scientific_name,
    }
    for dim in DIMS:
        item[f'{dim}_zh'] = getattr(profile, dim, '') or ''
        item[f'{dim}_en_old'] = getattr(profile, f'{dim}_en', '') or ''
    data['profiles'].append(item)

with open(OUT, 'w', encoding='utf-8', newline='\n') as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)

print(f'已导出 {OUT}')
print(f'  病害     {len(data["diseases"])} 条（症状 + 发病规律）')
print(f'  防治措施 {len(data["methods"])} 条')
print(f'  健康档案 {len(data["profiles"])} 条 × 7 维度')
zh_chars = (
    sum(len(d['symptoms_zh']) + len(d['description_zh']) for d in data['diseases'])
    + sum(len(m['measure_zh']) for m in data['methods'])
    + sum(len(p[f'{dim}_zh']) for p in data['profiles'] for dim in DIMS)
)
print(f'  待翻译中文字数合计约 {zh_chars} 字')
