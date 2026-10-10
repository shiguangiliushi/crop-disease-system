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

from .audit import log_admin_action  # 第 150 批：敏感词增删留痕
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

    def perform_create(self, serializer):
        # 第 150 批：敏感词决定哪些内容会被拦下/替换，增删都要留痕
        word = serializer.save()
        log_admin_action(
            self.request.user, 'word.create', target=word,
            detail=f'新增敏感词（分类 {getattr(word, "category", "") or "未分类"}）',
            request=self.request,
        )

    def perform_destroy(self, instance):
        # 删词比加词更值得记：加错了只是误伤，删错了等于放过违规内容
        preview = getattr(instance, 'word', '') or f'#{instance.pk}'
        log_admin_action(
            self.request.user, 'word.delete', target=instance,
            detail=f'删除敏感词（分类 {getattr(instance, "category", "") or "未分类"}）',
            request=self.request,
        )
        instance.delete()

    def get_queryset(self):
        queryset = SensitiveWord.objects.all()
        category = (self.request.query_params.get('category') or '').strip()
        if category:
            queryset = queryset.filter(category=category)
        return queryset
