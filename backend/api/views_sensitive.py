"""
敏感词词库接口（第 38 批）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/sensitive-words/` | GET | 词库列表（BROADCAST 能力） |
| `/api/sensitive-words/` | POST | 新增（BROADCAST 能力） |
| `/api/sensitive-words/<id>/` | DELETE | 删除（BROADCAST 能力） |

词库变更会立即清掉缓存（见 `SensitiveWord.save/delete`），不用等 60 秒。
"""
from rest_framework import viewsets

from .capabilities import IsBroadcastManager  # 第 124 批：能力口径统一（原为 DRF IsAdminUser）
from .models import SensitiveWord
from .serializers import SensitiveWordSerializer


class SensitiveWordViewSet(viewsets.ModelViewSet):
    """
    敏感词词库

    第 124 批：权限从 DRF 的 `IsAdminUser`（**只认 is_staff**）换成 `IsBroadcastManager`
    （BROADCAST 能力）—— 敏感词是**全站内容策略开关**，与公告、预警同一类；
    **信息编辑员（EDITOR）不可**。
    """
    serializer_class = SensitiveWordSerializer
    permission_classes = [IsBroadcastManager]
    pagination_class = None  # 词库通常不多，一次返回全部

    def get_queryset(self):
        queryset = SensitiveWord.objects.all()
        category = (self.request.query_params.get('category') or '').strip()
        if category:
            queryset = queryset.filter(category=category)
        return queryset
