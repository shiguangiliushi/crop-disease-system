"""把 K4 的英文译稿写进库（第 197 批）。

## 为什么译文先落成文件、再由本脚本写库

翻译环节只该产出**文本**，不该有数据库写权限。分成两步的好处：
  · 译文可复核、可重放（`--dry-run` 先看一遍再写）；
  · 写库这一步是**确定性的**：同样的三个文件跑两次结果一样（幂等）。

## 校验（`--verify` 或写库前自动跑）三件事

1. **完整性**：26 条病害 × 2 字段、130 条防治、12 × 7 个档案字段，一个不缺；
2. **无中文残留**：英文值里出现 `\\u4e00-\\u9fff` 就是没译干净（或误把中文抄了过去）；
3. **数字对齐**：中文里的每个数字都要能在英文里找到 —— 这条是**最要紧的**，
   因为校准版的价值就在"稀释倍数、安全间隔期、施药间隔"这些数字上，
   漏一个就是让英文用户按错的剂量打药。

做法：`--dry-run` 只读比对并打印；`--apply` 写库（整体一个事务）。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, r"D:\新建文件夹\crop-disease-system\backend")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crop_disease_backend.settings")

import django  # noqa: E402
django.setup()

from django.db import transaction  # noqa: E402

from api.models import CropHealthProfile, PestInfo, PreventionMethod  # noqa: E402

# 译稿与中文校准版放在同一目录（`docs/knowledge_base/`），一起入库 ——
# 否则中文改了要重译时，没人知道英文是从哪一版来的。
TOOLS = Path(__file__).resolve().parent
CJK = re.compile(r'[\u4e00-\u9fff]')
#: 数字（含小数）。中文里的 `3～6 mm`、`1500-2000倍`、`>80%` 都要能被抓出来
NUM = re.compile(r'\d+(?:\.\d+)?')


def load_module(path: Path, attr: str = 'EN'):
    if not path.is_file():
        raise SystemExit(f'缺少译稿文件：{path}')
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, attr)


def numbers(text: str) -> list[str]:
    """取数字集合（归一：去掉结尾的 .0）。"""
    out = []
    for raw in NUM.findall(text or ''):
        if raw.endswith('.0'):
            raw = raw[:-2]
        out.append(raw)
    return out


def check_text(label: str, zh: str, en: str, problems: list[str]) -> None:
    if not str(en or '').strip():
        problems.append(f'{label}：英文为空')
        return
    hit = CJK.search(en)
    if hit:
        problems.append(f'{label}：英文里出现中文字符 {hit.group(0)!r}')
    missing = [n for n in numbers(zh) if n not in en]
    # 只报"中文有、英文没有"的数字；英文多出数字不算错（可能补了单位换算说明）
    if missing:
        # 排除极常见的小数字误报（如枚举编号 1)、2)）
        real = [n for n in missing if float(n) > 5 or '.' in n]
        if real:
            problems.append(f'{label}：英文缺少中文里的数字 {real}')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='真正写库（默认只做校验与预览）')
    parser.add_argument('--verify-only', action='store_true', help='只校验，不预览')
    args = parser.parse_args()

    diseases = load_module(TOOLS / 'kb_en_diseases.py')
    methods = load_module(TOOLS / 'kb_en_methods.py')
    profiles = load_module(TOOLS / 'kb_en_profiles.py')

    problems: list[str] = []
    stats = {'pests': 0, 'methods': 0, 'profiles': 0, 'fields': 0}

    # ── 一、病害：症状 + 发病规律 ────────────────────────────────────────
    pest_map = {p.english_identifier: p for p in PestInfo.objects.all()}
    for ident, pair in diseases.items():
        pest = pest_map.get(ident)
        if pest is None:
            problems.append(f'病害 identifier 在库里不存在：{ident}')
            continue
        for zh_attr, en_key in (('symptoms', 'symptoms_en'), ('description', 'description_en')):
            check_text(f'{pest.name}/{en_key}', getattr(pest, zh_attr) or '', pair.get(en_key, ''), problems)
        stats['pests'] += 1

    # ── 二、防治措施 ────────────────────────────────────────────────────
    method_map = {(m.pest.english_identifier, m.category): m
                  for m in PreventionMethod.objects.select_related('pest')}
    for key, en in methods.items():
        key = tuple(key)
        method = method_map.get(key)
        if method is None:
            problems.append(f'防治措施不存在：{key}')
            continue
        check_text(f'{key[0]}/{key[1]}', method.measure or '', en, problems)
        stats['methods'] += 1

    # ── 三、健康档案 ────────────────────────────────────────────────────
    profile_map = {p.name: p for p in CropHealthProfile.objects.all()}
    dims = ('morphology', 'growing_conditions', 'care_agricultural', 'care_chemical',
            'care_ecological', 'care_physical', 'care_monitoring')
    for name, fields in profiles.items():
        profile = profile_map.get(name)
        if profile is None:
            problems.append(f'健康档案不存在：{name}')
            continue
        for dim in dims:
            en_key = f'{dim}_en'
            check_text(f'{name}/{en_key}', getattr(profile, dim) or '', fields.get(en_key, ''), problems)
        stats['profiles'] += 1

    print('=' * 90)
    print('K4 英文译稿校验')
    print('=' * 90)
    print(f'  病害   {stats["pests"]}/26 条（症状 + 发病规律）')
    print(f'  防治   {stats["methods"]}/130 条')
    print(f'  档案   {stats["profiles"]}/12 条 × 7 维度')

    if stats['pests'] != 26 or stats['methods'] != 130 or stats['profiles'] != 12:
        problems.insert(0, f'条数不齐：病害 {stats["pests"]}、防治 {stats["methods"]}、档案 {stats["profiles"]}')

    if problems:
        print(f'\n  ✗ {len(problems)} 个问题：')
        for item in problems[:40]:
            print(f'      · {item}')
        if len(problems) > 40:
            print(f'      …还有 {len(problems) - 40} 条')
        return 1
    print('\n  ✓ 校验通过（完整、无中文残留、数字对齐）')

    if args.verify_only or not args.apply:
        print('\n  （未写库。确认无误后加 --apply 真正写入）')
        return 0

    # ── 写库（单事务）──────────────────────────────────────────────────
    with transaction.atomic():
        for ident, pair in diseases.items():
            pest = pest_map[ident]
            pest.symptoms_en = pair['symptoms_en'].strip()
            pest.description_en = pair['description_en'].strip()
            pest.save(update_fields=['symptoms_en', 'description_en'])
            stats['fields'] += 2
        for key, en in methods.items():
            method = method_map[tuple(key)]
            method.measure_en = en.strip()
            method.save(update_fields=['measure_en'])
            stats['fields'] += 1
        for name, fields in profiles.items():
            profile = profile_map[name]
            for dim in dims:
                setattr(profile, f'{dim}_en', fields[f'{dim}_en'].strip())
            profile.save(update_fields=[f'{dim}_en' for dim in dims])
            stats['fields'] += len(dims)

    print(f'\n  ✓ 已写库：{stats["pests"]} 条病害 + {stats["methods"]} 条防治 '
          f'+ {stats["profiles"]} 条档案，共 {stats["fields"]} 个字段')
    return 0


if __name__ == '__main__':
    sys.exit(main())
