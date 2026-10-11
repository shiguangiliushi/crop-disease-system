"""
管理端「系统健康」接口（第 157 批）

    GET /api/admin/health/      —— 仅全权管理员

## 为什么要有它

`manage.py check_env` 已经能查出"依赖缺了 / 迁移没跑 / 模型文件没了 / 备份过期 /
注销到期任务没挂"这些**安静的故障** —— 但它只有命令行，
意味着**只有会 SSH 上服务器的人**才看得见；而这些问题里最要命的一条是"备份挂了没人知道，
直到真出事那天"。

这一页把同一套检查搬到界面上（第 117 批起管理端一直在做的事），顺带给出**数据量概览**，
让"这套系统现在什么状态"在一屏里说得清。

## 关键设计：**不重写检查**

接口直接调 `check_env --json`（第 157 批给那个命令加了 `--json` 与结构化 `results`），
而不是在视图里再写一遍检查逻辑 ——
"同一个检查写两份"正是本项目反复强调要避免的（第 16/17 批的计数、第 128 批的双删除口径、
第 149 批的软删除，都是栽在这上面）。

视图这里只补两样命令里没有的东西：**数据量概览**与**媒体目录体积**。
"""
import json
import sys
from io import StringIO
from pathlib import Path

import django
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import backup_utils as bu
from .capabilities import is_full_admin
from .models import DetectionHistory, Feedback
from .models_forum import Comment, Post

User = get_user_model()


def _counts():
    """数据量概览（都是 count()，几十毫秒级；管理端低频访问，不需要缓存）"""
    return {
        'users': User.objects.count(),
        'active_users': User.objects.filter(is_active=True, is_deleted=False).count(),
        'posts': Post.active.count(),
        'comments': Comment.objects.filter(is_deleted=False).count(),
        'detections': DetectionHistory.objects.count(),
        'feedback': Feedback.objects.count(),
        'feedback_pending': Feedback.objects.filter(status='pending').count(),
    }


def _media_size():
    """media 目录体积（备份该多大、磁盘够不够，看这个数最直观）"""
    media_root = Path(getattr(settings, 'MEDIA_ROOT', '') or '')
    if not media_root.exists():
        return {'files': 0, 'bytes': 0, 'mb': 0}
    files = total = 0
    for item in media_root.rglob('*'):
        if item.is_file():
            files += 1
            total += item.stat().st_size
    return {'files': files, 'bytes': total, 'mb': round(total / 1024 / 1024, 1)}


class AdminHealthView(APIView):
    """系统健康（仅全权管理员）"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # 与「操作日志」同档：它会暴露服务器路径、依赖版本、是否开了 HTTPS 等部署细节，
        # 不该给内容编辑员看。
        if not is_full_admin(request.user):
            return Response({'detail': '只有管理员可以查看系统健康'},
                            status=status.HTTP_403_FORBIDDEN)

        # 复用 check_env 的检查（唯一的实现），只取它的 JSON
        buffer = StringIO()
        call_command('check_env', as_json=True, stdout=buffer)
        payload = json.loads(buffer.getvalue() or '{}')

        results = payload.get('results') or []
        problems = payload.get('problems') or []
        warnings = payload.get('warnings') or []

        # 按节分组（保持命令里的顺序：依赖 → 应用 → 运行时 → 生产开关）
        sections = []
        for item in results:
            name = item.get('section') or '其它'
            if not sections or sections[-1]['title'] != name:
                sections.append({'title': name, 'items': []})
            sections[-1]['items'].append({
                'level': item.get('level') or 'ok',
                'text': item.get('text') or '',
            })

        return Response({
            'ok': bool(payload.get('ok')),
            'level': 'fail' if problems else ('warn' if warnings else 'ok'),
            'problems': problems,
            'warnings': warnings,
            'sections': sections,
            'counts': _counts(),
            'media': _media_size(),
            'history': _history(),
            'runtime': {
                'debug': bool(settings.DEBUG),
                'python': f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}',
                'django': django.get_version(),
                'database': settings.DATABASES['default']['ENGINE'].rsplit('.', 1)[-1],
                'cache': settings.CACHES['default']['BACKEND'].rsplit('.', 1)[-1],
                'media_root': str(getattr(settings, 'MEDIA_ROOT', '') or ''),
                'backup_root': str(bu.backup_root()),
            },
        })


#: 趋势取最近多少天
HISTORY_DAYS = 14


def _history():
    """
    最近 N 天的健康快照（第 158 批）

    为什么要趋势：环境类故障是**安静**的（定时任务挂了、备份没跑成），
    "最新备份是 3 天前"和"这 14 天一直在跑"是两种完全不同的安心程度。
    快照由 `manage.py health_snapshot` 每天记一条（建议挂定时任务）。
    """
    from datetime import timedelta

    from django.utils import timezone

    from .models_health import HealthSnapshot

    since = timezone.localdate() - timedelta(days=HISTORY_DAYS - 1)
    rows = list(HealthSnapshot.objects.filter(snapshot_date__gte=since))
    by_date = {row.snapshot_date: row for row in rows}

    # 补齐"没有快照的那几天" —— 缺的那天本身就是信息（说明定时任务没跑）
    days = []
    for offset in range(HISTORY_DAYS):
        day = since + timedelta(days=offset)
        row = by_date.get(day)
        days.append({
            'date': day.isoformat(),
            'recorded': row is not None,
            'level': (row.level if row else None),
            'problem_count': (row.problem_count if row else 0),
            'warning_count': (row.warning_count if row else 0),
            'counts': (row.counts if row else {}),
            'notes': (row.notes if row else ''),
        })
    return {
        'days': days,
        'recorded_days': sum(1 for day in days if day['recorded']),
        'window': HISTORY_DAYS,
        'latest_date': days[-1]['date'] if days else None,
        'hint': 'python manage.py health_snapshot  # 每天记一条（挂定时任务才有连续趋势）',
    }
