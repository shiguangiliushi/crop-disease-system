from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db.models import Q
import logging

from .models import DetectionHistory

logger = logging.getLogger(__name__)

class DetectionPestTypesView(APIView):
    """
    从检测历史中获取唯一的病害类型
    - 支持按搜索词和作物类型筛选
    - 返回格式: {"status": "success", "count": 10, "results": ["病害1", "病害2", ...]}
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        try:
            # 获取查询参数
            search = request.query_params.get('search', '')
            crop_type = request.query_params.get('crop_type', '')
            
            # 基础查询
            queryset = DetectionHistory.objects.all()
            
            # 应用权限过滤
            if not (request.user.is_staff or request.user.is_superuser):
                queryset = queryset.filter(user=request.user)
            
            # 应用搜索条件
            # 注意：DetectionHistory 的字段是 detection_result；PestInfo 只有
            # name / english_identifier，原来的 disease_name、name_zh、name_en
            # 字段并不存在，会直接抛 FieldError 导致 500。
            if search:
                queryset = queryset.filter(
                    Q(detection_result__icontains=search) |
                    Q(pest_info__name__icontains=search) |
                    Q(pest_info__english_identifier__icontains=search)
                )
            
            # 应用作物类型过滤
            if crop_type:
                queryset = queryset.filter(pest_info__crop_type=crop_type)
            
            # 获取唯一的病害名称
            pest_names = set()
            for item in queryset.values('detection_result', 'pest_info__name').distinct():
                if item['pest_info__name']:
                    pest_names.add(item['pest_info__name'])
                elif item['detection_result']:
                    pest_names.add(item['detection_result'])
            
            # 转换为列表并排序
            pest_list = sorted(list(pest_names))
            
            return Response({
                'status': 'success',
                'count': len(pest_list),
                'results': pest_list
            })
                
        except Exception as e:
            logger.error(f'获取病害类型失败: {str(e)}', exc_info=True)
            return Response(
                {'status': 'error', 'message': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
