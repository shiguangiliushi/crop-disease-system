"""
敏感词词库接口（第 38 批）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/sensitive-words/` | GET | 词库列表（仅管理员） |
| `/api/sensitive-words/` | POST | 新增（仅管理员） |
| `/api/sensitive-words/<id>/` | DELETE | 删除（仅管理员） |

词库变更会立即清掉缓存（见 `SensitiveWord.save/delete`），不用等 60 秒。
"""
from rest_framework import permissions, viewsets

from .models import SensitiveWord
from .serializers import SensitiveWordSerializer


class SensitiveWordViewSet(viewsets.ModelViewSet):
    """敏感词词库（仅管理员可读写）"""
    serializer_class = SensitiveWordSerializer
    permission_classes = [permissions.IsAdminUser]
    pagination_class = None  # 词库通常不多，一次返回全部

    def get_queryset(self):
        queryset = SensitiveWord.objects.all()
        category = (self.request.query_params.get('category') or '').strip()
        if category:
            queryset = queryset.filter(category=category)
        return queryset
