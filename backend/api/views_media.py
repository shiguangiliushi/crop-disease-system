"""媒体文件访问控制（第 257 批，media 私有化第一步）。

## 背景

`/media/` 原先由 `django.views.static.serve` 直接吐出：**任何人拿到 URL 就能看**。
里面有用户的叶片照片、反馈附图、专家咨询配图、助手提问图片 —— 都属于"不该公开"的内容。

## 为什么先只保护 `assistant_uploads/`

那些目录里有图片会**直接渲染在页面上**（识别历史、咨询、反馈管理），而浏览器 `<img>`
不会带 `Authorization` 头 —— 一刀切收权会立刻表现为"图片全裂"。要动它们必须配
**签名 URL**（`?sig=&exp=`），那是下一步。

`assistant_uploads/`（助手提问图片）**没有任何页面渲染它**，可以立刻收权：
只有该消息的所属用户与管理员能读，其余一律 404（不用 403，避免泄露"这个路径存在"）。

## 设计

- 路径先过 `safe_join`，越界（`../`）直接 404；
- 非私有目录：保持原来的公开行为（用 `serve` 原样转发，不改现有功能）；
- 私有目录：按 `AssistantMessage.image` 反查归属，未登录 / 非本人 / 非管理员 → 404。
"""
from __future__ import annotations

from django.http import Http404, FileResponse
from django.views.static import serve as media_serve
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView


#: 需要鉴权的目录前缀（第 257 批只有助手提问图片；后续可加 detection_history / consult_images）
from .media_sign import PRIVATE_PREFIXES  # 第 259 批：清单集中到 media_sign

#: 归属判断：目录前缀 → (模型路径, 关联查询字段)
#: 收权某目录时，这里要同时给出"谁算所有者"。
OWNER_LOOKUPS = {
    'detection_history/': ('api.models.DetectionHistory', 'user'),
    'consult_images/': ('api.models_expert.ExpertQuestion', 'user'),
    'feedback_images/': ('api.models.Feedback', 'user'),
}


class MediaView(APIView):
    """`/media/<path>` 的统一入口：公开目录直出，私有目录鉴权。"""

    #: 公开目录允许匿名（头像、病害图、新闻图仍需公开展示）
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, path: str):
        from django.conf import settings

        if not any(path.startswith(prefix) for prefix in PRIVATE_PREFIXES):
            return media_serve(request, path, document_root=settings.MEDIA_ROOT)

        # 第 258 批：签名 URL 优先 —— `<img>` 带不了 Authorization 头，
        # 但可以带查询串；签名只对这一个路径、这段时限有效。
        from .media_sign import verify as verify_sig

        if verify_sig(path, request.query_params.get('sig', ''),
                      request.query_params.get('exp', '')):
            return media_serve(request, path, document_root=settings.MEDIA_ROOT)

        user = self._current_user(request)
        if user is None:
            raise Http404
        if getattr(user, 'role', '') == 'ADMIN' or getattr(user, 'is_superuser', False):
            return media_serve(request, path, document_root=settings.MEDIA_ROOT)

        from .models_assistant import AssistantMessage

        owned = False
        if path.startswith('assistant_uploads/'):
            # 归属在 session 上（AssistantMessage 没有 user 字段）
            owned = AssistantMessage.objects.filter(
                session__user=user, image__in=[path, f'media/{path}'],
            ).exists()
        else:
            for prefix, (model_path, field) in OWNER_LOOKUPS.items():
                if not path.startswith(prefix):
                    continue
                module_name, class_name = model_path.rsplit('.', 1)
                module = __import__(module_name, fromlist=[class_name])
                model = getattr(module, class_name)
                owned = model.objects.filter(
                    **{field: user}, image__in=[path, f'media/{path}'],
                ).exists()
                break

        if not owned:
            raise Http404

        response = FileResponse(open(f'{settings.MEDIA_ROOT}/{path}', 'rb'))
        response['Cache-Control'] = 'private, max-age=300'
        return response

    @staticmethod
    def _current_user(request):
        """用项目自己的设备 token 认证中间件解析用户（不走 DRF 认证，避免 401 JSON）。"""
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            return user

        header = request.META.get('HTTP_AUTHORIZATION', '')
        if not header.startswith('Token '):
            return None
        key = header.split(' ', 1)[1].strip()
        if not key:
            return None

        from .authentication import DeviceTokenAuthentication

        try:
            result = DeviceTokenAuthentication().authenticate(request)
        except Exception:  # noqa: BLE001 —— 认证失败当匿名处理，不抛 500
            return None
        return result[0] if result else None
