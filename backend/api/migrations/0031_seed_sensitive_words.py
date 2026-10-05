"""
第 52 批：写入默认敏感词库

背景（冒烟回归发现）：敏感词过滤功能代码齐全，但**词库是空的** ——
也就是说开箱即用时这个功能等于没开（任何内容都能发）。
这里补一份**最小可用的默认词库**（广告/欺诈/违法类），管理员可在
「内容审核」页或 Django 后台继续增删（`SensitiveWord`）。

说明：只放明显该拦的词，不做"大而全"的清单 —— 过宽的词库会误伤正常农业讨论
（例如"药"、"杀虫"这类词绝不能进列表）。
"""
from django.db import migrations

#: (词, 分类, 备注)  —— 分类取值见 SensitiveWord.CATEGORY_CHOICES: ad/abuse/politics/other
DEFAULT_WORDS = [
    ('代开发票', 'ad', '发票类广告'),
    ('办证', 'ad', '证件类广告'),
    ('刷单', 'ad', '刷单返利'),
    ('兼职刷单', 'ad', '刷单返利'),
    ('加微信', 'ad', '导流到站外'),
    ('加QQ', 'ad', '导流到站外'),
    ('贷款秒批', 'ad', '金融诈骗广告'),
    ('高额返利', 'ad', '金融诈骗广告'),
    ('博彩', 'other', '赌博类'),
    ('赌场', 'other', '赌博类'),
    ('色情', 'other', '色情类'),
    ('枪支', 'other', '违法物品'),
    ('毒品', 'other', '违法物品'),
]


def seed_words(apps, schema_editor):
    SensitiveWord = apps.get_model('api', 'SensitiveWord')
    created = 0
    for word, category, note in DEFAULT_WORDS:
        _, is_new = SensitiveWord.objects.get_or_create(
            word=word,
            defaults={'category': category, 'note': note, 'is_active': True},
        )
        created += 1 if is_new else 0
    print(f'    默认敏感词库：新增 {created} 条，共 {len(DEFAULT_WORDS)} 条')


def unseed_words(apps, schema_editor):
    """回滚只删默认词，管理员自己加的保留"""
    SensitiveWord = apps.get_model('api', 'SensitiveWord')
    SensitiveWord.objects.filter(word__in=[word for word, _c, _n in DEFAULT_WORDS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0030_consultanswer_consultquestion_consultanswer_question_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_words, unseed_words),
    ]
