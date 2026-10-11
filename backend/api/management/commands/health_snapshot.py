"""
记一条系统健康快照（第 158 批）

    python manage.py health_snapshot              # 记今天这一条
    python manage.py health_snapshot --days 180   # 同时清理 180 天前的
    python manage.py health_snapshot --dry-run    # 只看会记什么，不写库

## 它存在的意义

环境类故障是**安静**的：定时任务挂了、磁盘快满了、注销到期任务没执行、备份没跑成 ——
都不会有人来报错。管理端「系统健康」页能看**当下**，但看不出**"这周备份跑了没有"**。
每天记一条之后，趋势能回答这个问题。

## 它**不重写**检查

与「系统健康」接口一样，调 `check_env --json`（唯一实现）。
"""
import json
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models_health import HealthSnapshot

#: 要点里最多留几条问题/提示（够事后回忆即可）
MAX_NOTES = 6


class Command(BaseCommand):
    help = '记一条系统健康快照（给管理端「系统健康」页画趋势用）'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=180,
                            help='保留天数，超过的旧快照会被清理（默认 180）')
        parser.add_argument('--dry-run', action='store_true', help='只显示会记什么，不写库')

    def handle(self, *args, **options):
        buffer = StringIO()
        call_command('check_env', as_json=True, stdout=buffer)
        data = json.loads(buffer.getvalue() or '{}')

        problems = data.get('problems') or []
        warnings = data.get('warnings') or []
        level = 'fail' if problems else ('warn' if warnings else 'ok')

        # 数据量概览（与健康接口同一套口径；这里只取关键几项，避免快照太胖）
        from ...models import DetectionHistory, Feedback
        from ...models_forum import Comment, Post
        from django.contrib.auth import get_user_model

        counts = {
            'users': get_user_model().objects.count(),
            'posts': Post.active.count(),
            'comments': Comment.objects.filter(is_deleted=False).count(),
            'detections': DetectionHistory.objects.count(),
            'feedback': Feedback.objects.count(),
        }

        notes_pool = [f'✗ {item}' for item in problems[:MAX_NOTES]]
        notes_pool += [f'⚠ {item}' for item in warnings[:MAX_NOTES - len(notes_pool)]]
        notes = '\n'.join(notes_pool)

        today = timezone.localdate()
        summary = (f'{today} 等级={level} 问题={len(problems)} 提示={len(warnings)} '
                   f'用户={counts["users"]} 帖子={counts["posts"]} 识别={counts["detections"]}')

        if options['dry_run']:
            self.stdout.write(f'（dry-run）会记：{summary}')
            if notes:
                self.stdout.write(notes)
            return

        snapshot, created = HealthSnapshot.objects.update_or_create(
            snapshot_date=today,
            defaults={
                'level': level,
                'problem_count': len(problems),
                'warning_count': len(warnings),
                'counts': counts,
                'notes': notes,
            },
        )
        action = '已记录' if created else '已更新（当天已有一条）'
        self.stdout.write(self.style.SUCCESS(f'✓ 健康快照{action}：{summary}'))

        # 清理过期快照
        days = max(1, int(options['days']))
        cutoff = today - timedelta(days=days)
        removed, _ = HealthSnapshot.objects.filter(snapshot_date__lt=cutoff).delete()
        if removed:
            self.stdout.write(f'（已清理 {removed} 条 {cutoff} 之前的快照）')
