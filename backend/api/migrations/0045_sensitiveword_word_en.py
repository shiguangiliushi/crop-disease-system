"""第 135 批：敏感词加"英文对照"字段，并给默认词库补上英文

为什么加这个字段
----------------------------------------------------------------------------
词条是**被拦截的字面串**，所以中文词库在英文界面下就是一串中文
（代开发票 / 兼职刷单 / 博彩…）。英文管理员看得见列表，却不知道每条拦的是什么，
于是会报"这里没翻译"。给它一个**只用于显示**的英文对照，问题就没了。

⚠️ 匹配仍然只看 `word`（见 api/sensitive.py）：想拦英文垃圾词请新增一条英文词条，
   不要写进 word_en —— 写那里不会生效。
"""
from django.db import migrations, models

#: 第 52 批种下的默认词库 → 英文对照
DEFAULT_WORD_EN = {
    '代开发票': 'fake invoices',
    '办证': 'fake certificates',
    '刷单': 'paid fake orders',
    '兼职刷单': 'part-time fake-order jobs',
    '加微信': 'moving users to WeChat',
    '加QQ': 'moving users to QQ',
    '贷款秒批': 'instant loan approval scams',
    '高额返利': 'high-rebate scams',
    '博彩': 'gambling',
    '赌场': 'casinos',
    '色情': 'pornography',
    '枪支': 'firearms',
    '毒品': 'drugs',
}


def fill_word_en(apps, schema_editor):
    """只补"自己种下的、且对照还为空的"记录 —— 不覆盖管理员填过的"""
    SensitiveWord = apps.get_model('api', 'SensitiveWord')
    updated = 0
    for word, word_en in DEFAULT_WORD_EN.items():
        updated += SensitiveWord.objects.filter(word=word, word_en='').update(word_en=word_en)
    print(f'    敏感词英文对照：补了 {updated} 条')


def clear_word_en(apps, schema_editor):
    """回滚：把默认词库的对照清空（管理员自己加的留着）"""
    SensitiveWord = apps.get_model('api', 'SensitiveWord')
    SensitiveWord.objects.filter(word__in=list(DEFAULT_WORD_EN)).update(word_en='')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0044_editor_module_grant'),
    ]

    operations = [
        migrations.AddField(
            model_name='sensitiveword',
            name='word_en',
            field=models.CharField(blank=True, default='', max_length=80, verbose_name='英文对照'),
        ),
        migrations.RunPython(fill_word_en, clear_word_en),
    ]
