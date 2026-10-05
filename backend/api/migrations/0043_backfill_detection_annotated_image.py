"""
第 106 批：把历史上"漏记"的标注图路径补回数据库
============================================================================
背景：`DetectionHistory.annotated_image` 这个字段**一直存在于模型里**，
但识别接口从来没往里写过值 —— 它把标注图落盘到
`media/detection_uploads/annotated_<uuid>.JPG`，却只在库里存了原图 `image`。

两个后果：
  1. 标注图**没有任何数据库引用** → 永远没人清理
     （第 104 批审计发现 media 里约 12.9 MB 无引用文件，这是主因之一）；
  2. 历史记录要显示标注图只能靠接口实时拼 URL，路径规则一变老图就失联。

本迁移负责**把已经漏掉的补回去**（新数据由 views.py 直接写字段，不再漏）。
能补的依据：标注图的文件名就是 `annotated_<原图文件名>`，与原图同目录，
所以可以从 `image` 推导出它应该在的位置 —— 但**必须确认文件真的存在**，
否则会把库指向不存在的文件（比留空更糟：前端会拿到 404 的图片而不是回退到原图）。

文件路径的两种形态都要处理：
  · `detection_uploads\\abc.JPG`（Windows 反斜杠，历史数据就是这样存的）；
  · `detection_uploads/abc.JPG`（正斜杠）。
"""
import os
from pathlib import Path

from django.conf import settings
from django.db import migrations


def backfill_annotated_image(apps, schema_editor):
    DetectionHistory = apps.get_model('api', 'DetectionHistory')
    media_root = Path(settings.MEDIA_ROOT)

    filled = 0
    missing = 0
    for row in DetectionHistory.objects.all().only('id', 'image', 'annotated_image'):
        if row.annotated_image:
            continue
        raw = str(row.image or '').replace('\\', '/')
        if not raw:
            continue
        directory, _, filename = raw.rpartition('/')
        candidate_rel = f'{directory}/annotated_{filename}' if directory else f'annotated_{filename}'

        if not (media_root / candidate_rel).is_file():
            missing += 1
            continue

        # 存回模型时沿用历史数据的反斜杠风格，避免同一列里出现两种分隔符
        row.annotated_image = candidate_rel.replace('/', '\\') if '\\' in str(row.image) else candidate_rel
        row.save(update_fields=['annotated_image'])
        filled += 1

    print(f'  [0043] 补回标注图路径 {filled} 条；文件不存在而跳过 {missing} 条')


def noop(apps, schema_editor):
    """回退时不做任何事。

    为什么不反向清空：这些路径**本来就该有值**，回退只是撤销这次补齐。
    清空会把新产生的正确数据一起抹掉（迁移无法区分"本迁移写的"与"接口写的"），
    那比留着更有害。
    """


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0042_user_deletion_grace'),
    ]

    operations = [
        migrations.RunPython(backfill_annotated_image, noop),
    ]
