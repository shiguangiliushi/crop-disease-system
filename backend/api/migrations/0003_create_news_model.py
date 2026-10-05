"""
说明（2025 修复）：
    本迁移原本再次 CreateModel('News')，但 0002_alter_feedback_options_and_more
    已经创建过 News 表、且中间从未删除，因此这条操作是完全重复的。
    后果：全新数据库上执行 migrate / 运行测试时会报
        django.db.utils.OperationalError: table "api_news" already exists
    （即 make test 无法建库）。

处理方式：
    0002 已经完成 News 的建表与状态登记，两者的字段、选项完全一致，
    所以这里改为“空操作”：
      - 新库：表由 0002 创建，本迁移不再重复建表 → 建库成功；
      - 已有库：本迁移早已记录为 applied，不会重新执行 → 数据与状态零影响；
      - 迁移最终状态与修复前完全一致（makemigrations --check 仍为 No changes detected）。
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0002_alter_feedback_options_and_more"),
    ]

    # News 表已由 0002 创建，这里不再重复执行任何数据库/状态操作
    operations = []
