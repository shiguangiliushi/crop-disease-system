"""
离线资料包（第 50 批）

背景：清单里"离线识别"。

**先把能力边界说清楚**：识别模型跑在后端（Python + 深度学习模型），
浏览器里**不可能**离线跑这个模型 —— 声称"离线也能识别"是骗人的。
本系统能给的真实离线能力是：

  ① 识别记录/图片在断网时**存入本地离线队列**，联网后**自动补传识别**（`utils/offlineQueue`）；
  ② 病害百科与防治方法**缓存到本地**，断网时仍可查阅（本接口提供"资料包"）；
  ③ 应用外壳（HTML/JS/CSS）由 Service Worker 缓存，断网也能打开页面。

本接口只提供 ② 需要的**精简资料包**：字段少、体积小、可缓存。
"""
import hashlib
import logging

from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PestInfo

logger = logging.getLogger(__name__)

SOURCE_NOTE = ('离线资料包只包含病害百科的文字信息（症状与防治方法）；'
               '图片识别需要联网，断网时拍的照片会进入本地队列，联网后自动识别')

#: 同一句话的英文版（第 77 批）
SOURCE_NOTE_EN = ('The offline pack only contains the text of the disease encyclopedia '
                  '(symptoms and prevention methods). Photo diagnosis needs a connection: '
                  'photos taken offline are queued locally and diagnosed once you are back online.')


class PestOfflinePackView(APIView):
    """
    病害百科离线资料包

    GET /api/pests/offline-pack/?since=<version>
    · 返回精简字段（名称/作物/症状/描述/防治方法/英文标识），供前端缓存；
    · 带 `version`（内容指纹）与 `count`；
    · 若请求带 `since` 且与当前 version 相同，返回 `unchanged=true` 且不带 items
      —— 前端每次联网只需传一个短参数就能判断要不要重新下载。
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        pests = (
            PestInfo.objects
            .prefetch_related('prevention_methods')
            .order_by('crop_type', 'name')
        )

        items = []
        for pest in pests:
            items.append({
                'id': pest.id,
                'name': pest.name,
                # 第 77 批：断网缓存也要能出英文 —— 百科页正是用这份 items 直接渲染的
                'name_en': pest.name_en or '',
                'crop_type': pest.crop_type,
                'crop_type_en': pest.crop_type_en or '',
                'english_identifier': pest.english_identifier,
                'symptoms': pest.symptoms or '',
                'symptoms_en': pest.symptoms_en or '',
                'description': pest.description or '',
                'description_en': pest.description_en or '',
                'prevention_methods': [
                    {
                        'category': method.category,
                        'category_display': method.get_category_display(),
                        'measure': method.measure,
                        'measure_en': method.measure_en or '',
                    }
                    for method in pest.prevention_methods.all()
                ],
            })

        # 内容指纹：名称+症状+防治方法条目数参与计算，内容变了版本就变
        # 第 77 批：英文名也纳入指纹，否则"只补了英文名"的改动不会让客户端重新下载
        digest = hashlib.md5()
        for item in items:
            digest.update(f"{item['id']}|{item['name']}|{item['name_en']}|{item['symptoms']}|{len(item['prevention_methods'])}".encode())
        version = digest.hexdigest()[:12]

        since = (request.query_params.get('since') or '').strip()
        if since and since == version:
            return Response({
                'version': version,
                'count': len(items),
                'unchanged': True,
                'generated_at': timezone.now(),
                'source_note': SOURCE_NOTE,
                'source_note_en': SOURCE_NOTE_EN,
            })

        return Response({
            'version': version,
            'count': len(items),
            'unchanged': False,
            'generated_at': timezone.now(),
            'source_note': SOURCE_NOTE,
            'source_note_en': SOURCE_NOTE_EN,
            'items': items,
        })
