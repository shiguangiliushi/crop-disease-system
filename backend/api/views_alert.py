"""
病害预警接口（第 46 批）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/alerts/` | GET | 当前预警（登录用户会带个性化标注） |
| `/api/alerts/notify/` | POST | 把预警推送给全部用户（仅管理员，按"病害+日期"去重） |

数据来源说明：预警**只基于站内识别记录**推导（趋势 / 多点 / 同月历史），
没有接天气或植保站的第三方数据 —— 这一点在接口返回里也用 `source` 字段讲明，
避免前端把它包装成"气象预警"。
"""
import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .services_alert import (
    DEFAULT_BASELINE_DAYS,
    DEFAULT_DAYS,
    alert_diagnostics,
    alert_summary,
    compute_alerts,
)

logger = logging.getLogger(__name__)
User = get_user_model()

SOURCE_NOTE = '预警基于站内识别记录统计得出（趋势、多用户检出、同月历史），未接入外部气象数据'

#: 同一句话的英文版（第 79 批）。内容是"数据来源声明"，属于内容数据，
#: 与 SOURCE_NOTE 放在一起（同 views_calendar / views_offline 的做法）。
SOURCE_NOTE_EN = ('Alerts are derived from diagnosis records on this site '
                  '(trend, multiple users reporting, same month last year); '
                  'no external weather data is used.')


def _is_admin(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_staff or user.is_superuser or getattr(user, 'role', None) == 'ADMIN')
    )


class AlertListView(APIView):
    """当前病害预警"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            days = max(3, min(30, int(request.query_params.get('days', DEFAULT_DAYS))))
        except (TypeError, ValueError):
            days = DEFAULT_DAYS
        try:
            min_cases = max(1, min(10, int(request.query_params.get('min_cases', 2))))
        except (TypeError, ValueError):
            min_cases = 2

        alerts = compute_alerts(
            days=days,
            baseline_days=DEFAULT_BASELINE_DAYS,
            min_cases=min_cases,
            user=request.user,
        )
        payload = {
            'generated_at': timezone.now(),
            'days': days,
            'min_cases': min_cases,
            'source': SOURCE_NOTE,
            'source_en': SOURCE_NOTE_EN,
            'summary': alert_summary(alerts),
            'alerts': alerts,
        }
        # 没有预警时补一段"为什么没有"的量化说明（第 76 批）——
        # 否则空页面只写"近期没有异常上升的病害"，用户没法区分
        # "没数据 / 坏了 / 就差一点"，会合理怀疑功能没做。
        if not alerts:
            payload['diagnostics'] = alert_diagnostics(days=days, min_cases=min_cases)
        return Response(payload)


class AlertNotifyView(APIView):
    """
    把当前预警推送给全部用户（仅管理员）

    去重：同一天、同一病害只推一次 —— 靠"当天是否已存在标题包含该病害名的预警通知"判断，
    否则管理员点两次，用户就会收到两条一模一样的通知。
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not _is_admin(request.user):
            return Response({'detail': '只有管理员可以推送预警'}, status=403)

        alerts = compute_alerts(user=None)
        # 只推 medium / high，避免"什么小事都推"
        targets = [item for item in alerts if item['level'] in ('high', 'medium')]
        if not targets:
            return Response({
                'pushed': 0,
                'skipped': 0,
                'message': '当前没有需要推送的预警（仅推送"高发期"和"明显增多"两个级别）',
            })

        from .views_notify import notify
        from .models_notify import Notification

        today = timezone.localdate()
        recipients = list(User.objects.filter(is_active=True))
        pushed = 0
        skipped = 0

        for alert in targets:
            marker = alert['title']
            marker_en = alert.get('title_en') or marker
            already = Notification.objects.filter(
                type='system',
                title__contains=alert['pest']['name'],
                created_at__date=today,
            ).exists()
            if already:
                skipped += 1
                continue

            with transaction.atomic():
                for user in recipients:
                    notify(
                        user,
                        type='system',
                        title=f'病害预警：{marker}',
                        title_en=f'Disease alert: {marker_en}',
                        message=alert['message'],
                        message_en=alert.get('message_en', ''),
                        url='/alerts',
                        actor=request.user,
                        # 第 78 批：推送人自己也留一份，否则"我推了但我的通知中心是空的"
                        allow_self=True,
                    )
            pushed += 1

        logger.info('病害预警推送: 病害 %s 个，跳过 %s 个，接收人 %s', pushed, skipped, len(recipients))
        return Response({
            'pushed': pushed,
            'skipped': skipped,
            'recipients': len(recipients),
            'message': f'已推送 {pushed} 条预警给 {len(recipients)} 位用户'
                       + (f'，{skipped} 条今天已推送过' if skipped else ''),
        })
