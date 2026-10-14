"""用 English identifier 推导出病害名/作物名的英文写法（第 69 批 · C 阶段）

数据来源：`english_identifier`（如 `Apple___Apple_scab`、`Corn___Common_rust`），
它是 PlantVillage 数据集的标签，天然是英文。把它拆成
「作物 + 病害」两段并做可读化处理，即可得到合理的英文名，
避免手工为 38 条数据逐个填写。管理员之后可在后台校正个别不理想的翻译。

用法：
    python manage.py shell < docs/tools/backfill_pest_en.py
或（推荐，作为一次性脚本执行）：
    python docs/tools/backfill_pest_en.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')

import django  # noqa: E402

django.setup()

from api.models import PestInfo  # noqa: E402

# 数据集里作物段的取值 → 更自然的英文作物名
CROP_ALIASES = {
    'apple': 'Apple',
    'blueberry': 'Blueberry',
    'cherry': 'Cherry',
    'corn': 'Corn',
    'grape': 'Grape',
    'orange': 'Orange',
    'peach': 'Peach',
    'pepper_bell': 'Bell pepper',
    'potato': 'Potato',
    'raspberry': 'Raspberry',
    'soybean': 'Soybean',
    'squash': 'Squash',
    'strawberry': 'Strawberry',
    'tomato': 'Tomato',
    # 站内自建数据可能用的中文作物名
    '苹果': 'Apple',
    '草莓': 'Strawberry',
    '柑橘': 'Citrus',
    '番茄': 'Tomato',
    '葡萄': 'Grape',
    '葫芦': 'Squash',
    '马铃薯': 'Potato',
    '玉米': 'Corn',
    '樱桃': 'Cherry',
    # 第 190 批：作物名从「桃」改成「桃子」（与库里的 crop_type 对齐）
    '桃子': 'Peach',
    '大豆': 'Soybean',
    '蓝莓': 'Blueberry',
    '树莓': 'Raspberry',
    '甜椒': 'Bell pepper',
}

# 数据集里病害段的常见写法 → 更自然的英文病名（其余按通用规则处理）
DISEASE_ALIASES = {
    'healthy': 'Healthy',
    'apple_scab': 'Apple scab',
    'black_rot': 'Black rot',
    'cedar_apple_rust': 'Cedar apple rust',
    'bacterial_spot': 'Bacterial spot',
    'early_blight': 'Early blight',
    'late_blight': 'Late blight',
    'leaf_blight': 'Leaf blight',
    'leaf_scorch': 'Leaf scorch',
    'leaf_rust': 'Leaf rust',
    'common_rust': 'Common rust',
    'northern_leaf_blight': 'Northern leaf blight',
    'cercospora_leaf_spot': 'Cercospora leaf spot',
    'gray_leaf_spot': 'Gray leaf spot',
    'esca': 'Esca (black measles)',
    'black_measles': 'Black measles',
    'haunglongbing': 'Citrus greening (HLB)',
    'powdery_mildew': 'Powdery mildew',
    'target_spot': 'Target spot',
    'mosaic_virus': 'Mosaic virus',
    'yellow_leaf_curl_virus': 'Yellow leaf curl virus',
    'septoria_leaf_spot': 'Septoria leaf spot',
    'spider_mites': 'Spider mites',
    'two_spotted_spider_mite': 'Two-spotted spider mite',
}


def prettify(token: str) -> str:
    token = token.replace('_', ' ').strip()
    token = re.sub(r'\s+', ' ', token)
    return token[:1].upper() + token[1:] if token else token


def split_identifier(identifier: str):
    if '___' not in (identifier or ''):
        return None, None
    crop, disease = identifier.split('___', 1)
    return crop.strip(), disease.strip()


def english_crop(crop: str, fallback: str) -> str:
    if not crop:
        return fallback or ''
    key = crop.lower()
    if key in CROP_ALIASES:
        return CROP_ALIASES[key]
    if crop in CROP_ALIASES:
        return CROP_ALIASES[crop]
    return prettify(crop)


def english_disease(disease: str, crop_en: str) -> str:
    if not disease:
        return ''
    key = disease.lower()
    if key in DISEASE_ALIASES:
        return DISEASE_ALIASES[key]

    # 数据集中有些标签是「两个病名拼在一起」（如
    # `Corn___Cercospora_leaf_spot Gray_leaf_spot`）——按**最长别名前缀**匹配，
    # 取更具体的那一个，避免生成 "Cercospora leaf spot Gray leaf spot" 这种半成品。
    for alias in sorted(DISEASE_ALIASES, key=len, reverse=True):
        if alias != 'healthy' and (key == alias or key.startswith(alias + ' ')):
            return DISEASE_ALIASES[alias]

    # 通用规则：下划线转空格 + 首字母大写
    return prettify(disease)


def main():
    updated = 0
    for pest in PestInfo.objects.all():
        crop_raw, disease_raw = split_identifier(pest.english_identifier)
        crop_en = english_crop(crop_raw, '')
        name_en = english_disease(disease_raw, crop_en)

        changed = False
        if name_en and pest.name_en != name_en:
            pest.name_en = name_en
            changed = True
        if crop_en and pest.crop_type_en != crop_en:
            pest.crop_type_en = crop_en
            changed = True
        if changed:
            pest.save(update_fields=['name_en', 'crop_type_en'])
            updated += 1

    print(f'已回填 {updated} 条病害的英文名/作物名')
    missing = PestInfo.objects.filter(name_en='').count()
    print(f'仍未填写英文名的条目：{missing}')


if __name__ == '__main__':
    main()
