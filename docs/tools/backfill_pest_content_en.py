"""回填病害与防治措施的英文内容（第 72 批）

背景
----
第 69 批只给 `PestInfo.name` / `crop_type` 加了英文字段，于是英文界面下
「症状（Symptoms）」「发病规律（Development）」「防治方法（Treatment）」
三大段仍然是中文 —— 用户反馈"切换成英语还是没有完全翻译"。

这个脚本按 `english_identifier`（PlantVillage 标签，本身是英文）回填：
  · `PestInfo.symptoms_en`
  · `PestInfo.description_en`
  · `PreventionMethod.measure_en`（按中文措施文本查表）

翻译以**通用植物病理学表述**为准，不逐字硬译；管理员之后可在后台逐条校正。
脚本是幂等的：只填空字段，已有自定义英文的条目不会被覆盖（加 --force 可强制覆盖）。

用法：
    python docs/tools/backfill_pest_content_en.py
    python docs/tools/backfill_pest_content_en.py --force
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')

import django  # noqa: E402

django.setup()

from api.models import PestInfo, PreventionMethod  # noqa: E402

# 症状 / 发病规律：按 english_identifier 归类（同病同症状的多作物条目复用同一条）
HEALTHY_SYMPTOMS = 'Leaves are healthy green with no lesions and growth is normal.'
HEALTHY_DESC = 'A healthy plant with intact leaves and normal colouring.'

BY_IDENTIFIER = {
    # ---- Apple ----
    'Apple___Apple_scab': (
        'Circular to irregular dark brown spots appear on the leaves; the lesions enlarge and '
        'severe infections cause defoliation.',
        'Apple scab is a fungal disease that mainly damages leaves and fruit.',
    ),
    'Apple___Black_rot': (
        'Black rotting spots appear on the fruit and gradually enlarge until the fruit decays.',
        'Apple black rot is a serious fruit disease that can cause major economic losses.',
    ),
    'Apple___Cedar_apple_rust': (
        'Orange-yellow spots appear on the leaves, with rust-coloured spore clusters on the underside.',
        'Cedar apple rust needs juniper (cedar) as an alternate host to complete its life cycle.',
    ),
    'Apple___healthy': (HEALTHY_SYMPTOMS, HEALTHY_DESC),

    # ---- Blueberry / Cherry / Corn / Grape / Peach / Pepper / Potato / Raspberry / Soybean / Strawberry ----
    'Blueberry___healthy': (HEALTHY_SYMPTOMS, HEALTHY_DESC),
    'Cherry___healthy': (HEALTHY_SYMPTOMS, HEALTHY_DESC),
    'Cherry___Powdery_mildew': (
        'A white powdery fungal layer covers the leaf surface, and severely affected leaves become distorted.',
        'Cherry powdery mildew is a fungal disease that reduces photosynthesis in the leaves.',
    ),
    'Corn___Cercospora_leaf_spot Gray_leaf_spot': (
        'Greyish-brown, elongated oval lesions appear on the leaves with sharply defined margins.',
        'Corn cercospora leaf spot is a major disease of corn and can reduce yield.',
    ),
    'Corn___Common_rust': (
        'Small orange-red spots appear on the leaves and enlarge into rust-coloured spore pustules.',
        'Corn common rust is a fungal disease that impairs leaf function.',
    ),
    'Corn___healthy': (HEALTHY_SYMPTOMS, HEALTHY_DESC),
    'Corn___Northern_Leaf_Blight': (
        'Greyish-brown, elongated lesions appear on the leaves with wavy margins.',
        'Corn northern leaf blight is a major disease of corn that can cause serious yield loss.',
    ),
    'Grape___Black_rot': (
        'Black rotting spots appear on the fruit, with similar symptoms on the leaves.',
        'Grape black rot is a major grape disease that reduces fruit quality.',
    ),
    'Grape___Esca_(Black_Measles)': (
        'Small black spots appear on the leaves, resembling measles.',
        'Grape esca (black measles) is a systemic disease that affects the health of the whole vine.',
    ),
    'Grape___healthy': (HEALTHY_SYMPTOMS, HEALTHY_DESC),
    'Grape___Leaf_blight_(Isariopsis_Leaf_Spot)': (
        'Brown lesions appear on the leaves and gradually enlarge until the leaf dies.',
        'Grape leaf blight reduces photosynthesis and lowers yield.',
    ),
    'Orange___Haunglongbing_(Citrus_greening)': (
        'Leaves turn yellow, fruit becomes small and misshapen, and plant growth is stunted.',
        'Citrus greening (HLB) is a severe bacterial disease that can kill the tree.',
    ),
    'Peach___Bacterial_spot': (
        'Water-soaked specks appear on the leaves and enlarge into brown lesions.',
        'Peach bacterial spot is a bacterial disease that impairs leaf function.',
    ),
    'Peach___healthy': (HEALTHY_SYMPTOMS, HEALTHY_DESC),
    'Pepper,_bell___Bacterial_spot': (
        'Water-soaked specks appear on the leaves, with yellow halos around the lesions.',
        'Bell pepper bacterial spot reduces photosynthesis and fruit quality.',
    ),
    'Pepper,_bell___healthy': (HEALTHY_SYMPTOMS, HEALTHY_DESC),
    'Potato___Early_blight': (
        'Brown lesions with concentric rings appear on the leaves, giving a target-board appearance.',
        'Potato early blight is a major potato disease that can cause serious yield loss.',
    ),
    'Potato___healthy': (HEALTHY_SYMPTOMS, HEALTHY_DESC),
    'Potato___Late_blight': (
        'Water-soaked lesions appear on the leaves and spread rapidly under humid conditions.',
        'Potato late blight is a devastating disease that can destroy the whole crop.',
    ),
    'Raspberry___healthy': (HEALTHY_SYMPTOMS, HEALTHY_DESC),
    'Soybean___healthy': (HEALTHY_SYMPTOMS, HEALTHY_DESC),
    'Squash___Powdery_mildew': (
        'A white powdery fungal layer appears on the leaf surface; severely affected leaves die.',
        'Squash powdery mildew reduces photosynthesis and lowers yield.',
    ),
    'Strawberry___healthy': (HEALTHY_SYMPTOMS, HEALTHY_DESC),
    'Strawberry___Leaf_scorch': (
        'Leaf margins develop brown scorched areas that spread towards the centre of the leaf.',
        'Strawberry leaf scorch impairs leaf function and reduces plant vigour.',
    ),
    'Tomato___Bacterial_spot': (
        'Water-soaked specks appear on the leaves, with yellow halos around the lesions.',
        'Tomato bacterial spot reduces photosynthesis and fruit quality.',
    ),
    'Tomato___Early_blight': (
        'Brown lesions with concentric rings appear on the leaves, giving a target-board appearance.',
        'Tomato early blight is a major tomato disease that can cause serious yield loss.',
    ),
    'Tomato___healthy': (HEALTHY_SYMPTOMS, HEALTHY_DESC),
    'Tomato___Late_blight': (
        'Water-soaked lesions appear on the leaves and spread rapidly under humid conditions.',
        'Tomato late blight is a devastating disease that can destroy the whole crop.',
    ),
    'Tomato___Leaf_Mold': (
        'A greyish-brown mould grows on the underside of the leaf while yellow lesions appear on the upper side.',
        'Tomato leaf mould reduces photosynthesis and lowers yield.',
    ),
    'Tomato___Septoria_leaf_spot': (
        'Round brown lesions appear on the leaves with small black dots in the centre.',
        'Tomato septoria leaf spot is a common disease that impairs leaf function.',
    ),
    'Tomato___Spider_mites Two-spotted_spider_mite': (
        'Yellowish-white speckling appears on the leaves; severe infestations turn leaves yellow and cause them to drop.',
        'Two-spotted spider mite is a major pest that sucks sap from the leaves.',
    ),
    'Tomato___Target_Spot': (
        'Brown circular lesions appear on the leaves with concentric rings.',
        'Tomato target spot reduces photosynthesis and lowers yield.',
    ),
    'Tomato___Tomato_Yellow_Leaf_Curl_Virus': (
        'Leaves turn yellow and curl, the plant is stunted, and fruit develops poorly.',
        'Tomato yellow leaf curl virus is a severe viral disease that can destroy the crop.',
    ),
    'Tomato___Tomato_mosaic_virus': (
        'Leaves show a mosaic pattern, the plant is stunted, and fruit is deformed.',
        'Tomato mosaic virus is a viral disease that affects the growth of the whole plant.',
    ),
}

# 防治措施：按中文措施文本查表（78 条去重后只有二十来种表述）
MEASURES = {
    '及时清除病叶、病果，减少病原菌越冬基数':
        'Remove diseased leaves and fruit promptly to reduce the pathogen population that overwinters.',
    '发病初期喷施50%多菌灵可湿性粉剂800倍液或70%甲基托布津可湿性粉剂1000倍液':
        'At the first symptoms spray carbendazim 50% WP at 800× or thiophanate-methyl 70% WP at 1000×.',
    '合理密植，改善通风透光条件，降低田间湿度':
        'Use a sensible planting density, improve air movement and light penetration, and lower field humidity.',
    '及时清除病果、病枝，集中销毁':
        'Remove diseased fruit and branches promptly and destroy them away from the field.',
    '果实膨大期喷施50%多菌灵可湿性粉剂600倍液':
        'Spray carbendazim 50% WP at 600× during fruit enlargement.',
    '果实套袋，减少病菌侵染机会':
        'Bag the fruit to reduce the chance of infection.',
    '清除果园周围的雪松等中间寄主':
        'Remove juniper and other alternate hosts around the orchard.',
    '花前喷施1:2:200波尔多液或50%多菌灵可湿性粉剂800倍液':
        'Before flowering spray Bordeaux mixture 1:2:200 or carbendazim 50% WP at 800×.',
    '定期检查叶片背面锈色孢子堆，及时防治':
        'Inspect the underside of leaves regularly for rust pustules and treat promptly.',
    '及时清除病叶，改善通风条件':
        'Remove diseased leaves promptly and improve air movement.',
    '发病初期喷施25%三唑酮可湿性粉剂1000倍液':
        'At the first symptoms spray triadimefon 25% WP at 1000×.',
    '合理修剪，改善通风透光条件':
        'Prune sensibly to improve air movement and light penetration.',
    '选用抗病品种，合理轮作':
        'Use resistant varieties and follow a sensible crop rotation.',
    '选用抗病品种，及时清除病残体':
        'Use resistant varieties and remove diseased plant debris promptly.',
    '定期检查叶片锈色孢子堆':
        'Inspect leaves regularly for rust pustules.',
    '及时清除病果、病叶，集中销毁':
        'Remove diseased fruit and leaves promptly and destroy them away from the field.',
    '花前花后喷施50%多菌灵可湿性粉剂800倍液':
        'Spray carbendazim 50% WP at 800× before and after flowering.',
    '果实套袋，减少病菌侵染':
        'Bag the fruit to reduce infection.',
    '及时清除病枝，集中销毁':
        'Remove diseased branches promptly and destroy them away from the field.',
    '伤口涂抹50%多菌灵可湿性粉剂100倍液':
        'Treat pruning wounds with carbendazim 50% WP at 100×.',
    '定期检查枝干症状':
        'Inspect the trunk and branches regularly for symptoms.',
    '及时清除病树，防止病害扩散':
        'Remove diseased trees promptly to stop the disease spreading.',
    '防治木虱，喷施10%吡虫啉可湿性粉剂2000倍液':
        'Control the Asian citrus psyllid; spray imidacloprid 10% WP at 2000×.',
    '定期检查叶片黄化症状':
        'Inspect leaves regularly for yellowing symptoms.',
    '选用抗病品种，及时清除病叶':
        'Use resistant varieties and remove diseased leaves promptly.',
    '发病初期喷施72%农用链霉素可湿性粉剂3000倍液':
        'At the first symptoms spray agricultural streptomycin 72% WP at 3000×.',
    '合理密植，改善通风条件':
        'Use a sensible planting density and improve air movement.',
    '发病初期喷施25%甲霜灵可湿性粉剂800倍液':
        'At the first symptoms spray metalaxyl 25% WP at 800×.',
    '阴雨天气加强监测':
        'Monitor more closely during wet and overcast weather.',
    '喷施1.8%阿维菌素乳油3000倍液':
        'Spray abamectin 1.8% EC at 3000×.',
    '使用黄色粘虫板诱杀':
        'Use yellow sticky traps to catch the pests.',
    '选用抗病品种，及时清除病株':
        'Use resistant varieties and remove diseased plants promptly.',
    '防治烟粉虱，喷施10%吡虫啉可湿性粉剂2000倍液':
        'Control whitefly; spray imidacloprid 10% WP at 2000×.',
    '防治蚜虫，喷施10%吡虫啉可湿性粉剂2000倍液':
        'Control aphids; spray imidacloprid 10% WP at 2000×.',
    '定期检查病毒症状':
        'Inspect plants regularly for virus symptoms.',
    '合理密植，改善通风透光条件':
        'Use a sensible planting density and improve air movement and light penetration.',
    '合理修剪，改善通风条件':
        'Prune sensibly to improve air movement.',
    '发病初期喷施50%多菌灵可湿性粉剂800倍液':
        'At the first symptoms spray carbendazim 50% WP at 800×.',
}


def main():
    force = '--force' in sys.argv

    pests_done = 0
    for pest in PestInfo.objects.all():
        pair = BY_IDENTIFIER.get(pest.english_identifier)
        if not pair:
            print(f'  ! 未收录英文内容的标识符：{pest.english_identifier}（{pest.name}）')
            continue
        symptoms_en, description_en = pair
        fields = []
        if force or not pest.symptoms_en:
            pest.symptoms_en = symptoms_en
            fields.append('symptoms_en')
        if force or not pest.description_en:
            pest.description_en = description_en
            fields.append('description_en')
        if fields:
            pest.save(update_fields=fields)
            pests_done += 1

    methods_done = 0
    missing = set()
    for method in PreventionMethod.objects.all():
        en = MEASURES.get(method.measure)
        if not en:
            missing.add(method.measure)
            continue
        if force or not method.measure_en:
            method.measure_en = en
            method.save(update_fields=['measure_en'])
            methods_done += 1

    print(f'已回填病害 {pests_done} 条（症状/发病规律），防治措施 {methods_done} 条')
    print(f'病害仍缺英文症状：{PestInfo.objects.filter(symptoms_en="").count()}')
    print(f'防治措施仍缺英文：{PreventionMethod.objects.filter(measure_en="").count()}')
    if missing:
        print('以下措施文本没有对应译文（需补进 MEASURES）：')
        for m in sorted(missing):
            print('  -', m)


if __name__ == '__main__':
    main()
