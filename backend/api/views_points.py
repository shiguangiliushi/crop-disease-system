"""
等级积分接口（第 42 批）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/users/me/points/` | GET | 我的积分与等级（含下一级进度） |
| `/api/users/me/point-logs/` | GET | 我的积分流水（分页） |
| `/api/points/levels/` | GET | 等级体系说明（公开，用于"等级怎么算"提示） |
"""
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models_points import LEVELS, POINT_RULES, PointLog
from .services_points import points_summary


class MyPointsView(APIView):
    """我的积分与等级"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(points_summary(request.user))


class MyPointLogsView(APIView):
    """我的积分流水"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = PointLog.objects.filter(user=request.user)
        total = queryset.count()

        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = min(50, max(1, int(request.query_params.get('page_size', 20))))
        except (TypeError, ValueError):
            page_size = 20

        start = (page - 1) * page_size
        rows = queryset[start:start + page_size]
        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': [
                {
                    'id': row.id,
                    'delta': row.delta,
                    'balance': row.balance,
                    'reason': row.reason,
                    'description': row.description,
                    'created_at': row.created_at,
                }
                for row in rows
            ],
        })


class PointLevelsView(APIView):
    """等级体系与加分规则（公开）"""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({
            'levels': [
                {'level': level, 'threshold': threshold, 'name': name, 'name_en': name_en}
                for level, threshold, name, name_en in sorted(LEVELS, key=lambda item: item[1])
            ],
            'rules': [
                {'reason': reason, 'points': points, 'label': label}
                for reason, (points, label) in POINT_RULES.items()
            ],
        })
