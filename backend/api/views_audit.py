"""
管理操作日志的读取接口（第 146 批）

    GET /api/admin/audit-logs/?action=user.suspend&actor=3&target_type=user&page=1&page_size=20

**仅全权管理员**（`is_full_admin`）可读：这张表会显示"谁在什么时候对谁做了什么"，
属于管理端的内部信息，内容编辑员不该看到别的管理员的操作记录。

为什么不给编辑员留一个"只看自己的"：日志的价值在于**对账**，
而只看得见自己那部分的话，对账时反而会得出错误结论（"没人删过"）。
"""
from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_date
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .capabilities import is_full_admin
from .models_audit import AdminAuditLog
from .pagination import CustomPagination

User = get_user_model()


def _parse_date(raw):
    """
    把 `YYYY-MM-DD` 解析成 date；非法值返回 None（**忽略**，不让筛选条件把页面打成 500）

    ⚠️ 必须自己兜住异常：Django 的 `parse_date` 对**格式**不对的值返回 None，
    但对**取值越界**的值（如 `2026-13-45`）会直接抛 `ValueError: month must be in 1..12`
    —— 第一版没兜，于是地址栏上手拼一个日期就把接口打成了 500（测试抓到的）。
    "非法筛选值一律忽略"是管理端所有列表页的统一约定，这里也不能例外。
    """
    if not raw:
        return None
    try:
        return parse_date(str(raw).strip())
    except (ValueError, TypeError):
        return None


def _serialize(log):
    return {
        'id': log.id,
        'actor': log.actor_id,
        # 快照优先：账号被删（actor 变成 null）时仍然读得懂
        'actor_name': log.actor_repr or (log.actor.username if log.actor else '系统'),
        'action': log.action,
        'action_display': log.get_action_display(),
        'target_type': log.target_type,
        'target_id': log.target_id,
        'target_name': log.target_repr,
        'detail': log.detail,
        'ip': log.ip,
        'created_at': log.created_at,
    }


class AdminAuditLogListView(APIView):
    """管理操作日志列表（只读，仅全权管理员）"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not is_full_admin(request.user):
            return Response({'detail': '只有管理员可以查看操作日志'},
                            status=status.HTTP_403_FORBIDDEN)

        queryset = AdminAuditLog.objects.select_related('actor')

        # 与其它管理列表一样：非法筛选值**忽略**，不让页面 500
        action = (request.query_params.get('action') or '').strip()
        if action:
            queryset = queryset.filter(action=action)

        actor = (request.query_params.get('actor') or '').strip()
        if actor.isdigit():
            queryset = queryset.filter(actor_id=int(actor))

        target_type = (request.query_params.get('target_type') or '').strip()
        if target_type:
            queryset = queryset.filter(target_type=target_type)

        # 第 148 批：时间范围（审计最常见的问法就是"上周谁停用过账号"）。
        # 收 `start` / `end` 两个 **YYYY-MM-DD**；end 补到当天 23:59:59，
        # 否则"查 3 月 1 日到 3 月 2 日"会把 3 月 2 日白天的记录漏掉（半年后才有人发现）。
        start = _parse_date(request.query_params.get('start'))
        if start:
            queryset = queryset.filter(created_at__date__gte=start)
        end = _parse_date(request.query_params.get('end'))
        if end:
            queryset = queryset.filter(created_at__date__lte=end)

        search = (request.query_params.get('search') or '').strip()
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(actor_repr__icontains=search) | Q(target_repr__icontains=search)
                | Q(detail__icontains=search)
            )

        paginator = CustomPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        rows = [_serialize(log) for log in (page if page is not None else queryset)]
        if page is not None:
            return paginator.get_paginated_response(rows)
        return Response({'count': len(rows), 'results': rows})


class AdminAuditLogActionsView(APIView):
    """可选的动作清单（给前端下拉用；与模型里的 choices 保持单一来源）"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not is_full_admin(request.user):
            return Response({'detail': '只有管理员可以查看操作日志'},
                            status=status.HTTP_403_FORBIDDEN)
        return Response([
            {'value': value, 'label': label} for value, label in AdminAuditLog.ACTION_CHOICES
        ])
