"""数据一致性自检 + 定时任务状态（第 448 批）。

## 为什么要有"对账"接口

管理端几处数字来自不同查询口径，并排看就像"统计坏了"：

| 位置 | 口径 | 线上真实值 |
|---|---|---|
| 管理端「用户总数」 | 全部账号（含游客） | 13 |
| 系统健康页「用户」 | `real_users()`（排除游客） | 11 |
| 侧栏「意见反馈」角标 | 全量待处理 | 31 |
| 反馈列表 | 跟随当前筛选（可能不是"待处理"） | 0 |

两个数往往都对，但界面上没交代口径 —— 演示时最先被问的就是这个。

与其一页页解释，不如提供**一个把同一指标在所有出现的地方都算一遍**的接口：
不一致就列出来，并给出可能的原因。这些原因大多是"口径"而不是"数据错误"，
所以接口返回的是 `note`（解释）而不是"错误"。

## 约定

- **不要**为了让数字相等而改查询 —— 先想清楚"这个指标应该表达什么"；
- 用户数/识别数统一按**真实用户**（排除游客）作为主口径，游客单独列出；
- 健康快照与健康页必须同一口径（第 448 批已统一 `health_snapshot`）。

## 任务状态

crontab 在宿主机上，容器里读不到；所以这里只报**能从数据里验证的**：
健康快照最近日期与缺失天数、备份目录最近一份、以及"期望的调度"（写死清单，
与 `docs/部署与运维.md` 的 crontab 一致）。前端据此显示"最近一次 / 下次预计"。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import backup_utils as bu
from .capabilities import is_full_admin
from .models import DetectionHistory, Feedback, News
from .models_health import HealthSnapshot

#: 期望的定时任务（与 docs/部署与运维.md §三·方式B / crontab 保持一致）
EXPECTED_TASKS = [
    ('backend_backup', '数据备份', '30 2 * * *'),
    ('backup_verify', '备份校验', '10 3 * * *'),
    ('health_snapshot', '健康快照', '40 3 * * *'),
    ('prune_media', '媒体清理', '10 4 * * *'),
    ('prune_guests', '游客账号清理', '0 5 * * *'),
    ('purge_deletion_requests', '注销请求清理', '5 * * * *'),
    ('notify_pending_news', '新闻通知补发', '20 * * * *'),
    ('cert_check', '证书到期检查', '0 9 * * *'),
]

#: 快照"应该几天一条"——超过这个天数没记录就标红
SNAPSHOT_GAP_DAYS = 2


def _value_or_none(value):
    return value if value is not None else None


class AdminConsistencyView(APIView):
    """`GET /api/admin/consistency/` —— 同一指标在不同位置的口径对账。"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        if not is_full_admin(request.user):
            return Response({'detail': '只有管理员可以查看数据对账'},
                            status=status.HTTP_403_FORBIDDEN)

        user_model = get_user_model()
        snapshot = HealthSnapshot.objects.order_by('-snapshot_date').first()
        snapshot_counts = (snapshot.counts if snapshot else {}) or {}

        checks = []

        def add(key, label, values, note):
            """`values` 是 [(来源, 数值), ...]；空值不参与比较（老快照可能没这个键）。"""
            present = [(name, value) for name, value in values if value is not None]
            distinct = {value for _name, value in present}
            checks.append({
                'key': key,
                'label': label,
                'values': [{'source': name, 'value': value} for name, value in present],
                'consistent': len(distinct) <= 1,
                'note': note,
            })

        # ① 用户数：列表(全部/真实) 与 健康快照
        add(
            'users', '用户数',
            [
                ('用户列表（全部账号）', user_model.objects.count()),
                ('用户列表（真实用户）', user_model.objects.filter(is_guest=False).count()),
                ('健康快照', _value_or_none(snapshot_counts.get('users'))),
            ],
            '健康页与快照排除游客试用账号；用户列表默认含游客（可用「仅真实用户」筛选）。'
            '两个口径都对，差异 = 试用账号数。',
        )

        # ② 识别记录：全部 vs 真实 vs 快照
        add(
            'detections', '识别记录',
            [
                ('识别历史（全部）', DetectionHistory.objects.count()),
                ('识别历史（真实用户）', DetectionHistory.objects.real_users().count()),
                ('健康快照', _value_or_none(snapshot_counts.get('detections'))),
            ],
            '游客试用产生的识别不计入健康页与快照的统计。',
        )

        # ③ 反馈：全部 / 待处理（侧栏角标用的就是"待处理"）
        add(
            'feedback', '意见反馈',
            [
                ('反馈总数', Feedback.objects.count()),
                ('待处理（侧栏角标）', Feedback.objects.filter(status='pending').count()),
            ],
            '角标统计的是「待处理」，而列表默认跟随当前筛选 —— '
            '如果列表筛选成了"已处理"或带了关键字，就会看到 0 条而角标仍有数字。',
        )

        # ④ 新闻：已发布 vs 全部（列表默认可能只看已发布）
        add(
            'news', '新闻',
            [
                ('已发布', News.objects.filter(is_published=True).count()),
                ('全部（含草稿）', News.objects.count()),
            ],
            '管理端列表默认展示全部（含草稿），前台只展示已发布 —— 不是同一种口径。',
        )

        return Response({
            'generated_at': timezone.now(),
            'ok': all(item['consistent'] for item in checks),
            'checks': checks,
        })


class AdminTaskStatusView(APIView):
    """`GET /api/admin/task-status/` —— 定时任务的"最近一次 / 是否缺天"。"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        if not is_full_admin(request.user):
            return Response({'detail': '只有管理员可以查看定时任务状态'},
                            status=status.HTTP_403_FORBIDDEN)

        today = timezone.localdate()
        snapshots = {
            row.snapshot_date: row
            for row in HealthSnapshot.objects.filter(
                snapshot_date__gte=today - dt.timedelta(days=13),
            )
        }
        last_snapshot = HealthSnapshot.objects.order_by('-snapshot_date').first()

        # 最近 14 天里缺哪几天（今天还没跑不算缺 —— 凌晨 3:40 才跑）
        missing = [
            (today - dt.timedelta(days=offset)).isoformat()
            for offset in range(13, -1, -1)
            if (today - dt.timedelta(days=offset)) not in snapshots
            and (today - dt.timedelta(days=offset)) < today
        ]

        backup_dir = bu.backup_root()
        backups = sorted(bu.list_backups(backup_dir), key=lambda p: p.name)
        last_backup = backups[-1] if backups else None

        def _mtime(path: Path | None):
            if not path:
                return None
            try:
                return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.get_current_timezone())
            except OSError:
                return None

        tasks = []
        for key, label, schedule in EXPECTED_TASKS:
            last_run = None
            if key == 'health_snapshot':
                last_run = last_snapshot.created_at if last_snapshot else None
            elif key == 'backend_backup':
                last_run = _mtime(last_backup)
            tasks.append({
                'key': key,
                'label': label,
                'schedule': schedule,
                'last_run': last_run,
                'tracked': last_run is not None,
            })

        return Response({
            'generated_at': timezone.now(),
            'snapshot': {
                'last_date': last_snapshot.snapshot_date.isoformat() if last_snapshot else None,
                'last_created_at': last_snapshot.created_at if last_snapshot else None,
                'days_in_window': len(snapshots),
                'missing_dates': missing,
                'gap_days': SNAPSHOT_GAP_DAYS,
                'stale': (last_snapshot is None
                          or (today - last_snapshot.snapshot_date).days > SNAPSHOT_GAP_DAYS),
            },
            'backup': {
                'dir': str(backup_dir),
                'last_name': last_backup.name if last_backup else None,
                'last_at': _mtime(last_backup),
                'count': len(backups),
            },
            'tasks': tasks,
        })
