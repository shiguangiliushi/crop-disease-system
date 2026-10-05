from django.db import migrations
from django.utils import timezone

def update_forum_boards(apps, schema_editor):
    ForumBoard = apps.get_model('api', 'ForumBoard')
    # 为所有版块设置初始值
    ForumBoard.objects.update(
        post_count=0,
        today_posts=0,
        last_updated_date=timezone.now().date()
    )

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_forumboard_post_count'),  # 更新为正确的依赖
    ]

    operations = [
        migrations.RunPython(update_forum_boards),
    ]