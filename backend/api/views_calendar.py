"""
种植日历接口（第 47 批）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/calendar/?month=&crop=` | GET | 某月的农事任务 + 该月站内真实病害统计（登录后按"我种过的作物"聚焦） |
| `/api/calendar/tasks/` | GET / POST | 任务列表 / 新增（写操作仅管理员） |
| `/api/calendar/tasks/<id>/` | PATCH / DELETE | 修改 / 删除（仅管理员） |
| `/api/calendar/crops/` | GET | 可选作物列表（来自病害百科里真实存在的作物） |

内容来源在返回体的 `source_note` 里讲明，前端原样展示。
"""
import logging

from django.db.models import Count, Q
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DetectionHistory, PestInfo
from .models_calendar import CalendarTask
from .services_content_i18n import crop_en, pest_en_maps  # 第 77 批：内容数据中英对照

logger = logging.getLogger(__name__)

TASK_TYPE_ORDER = ['nursery', 'sowing', 'planting', 'fertilizer', 'pruning',
                   'pest_control', 'harvest', 'winter', 'other']

SOURCE_NOTE = ('农事任务来自通用农事模板（管理员可维护）；'
               '"本月需重点防范"完全来自本站识别记录的统计，未使用外部农情数据')

#: 同一句话的英文版（第 77 批）。内容是"数据来源声明"，属于内容数据，
#: 所以跟 SOURCE_NOTE 放在一起，而不是塞进前端文案表。
SOURCE_NOTE_EN = ('Field tasks come from the general farming template (maintainable by admins); '
                  '"Watch out for" is derived entirely from diagnosis records on this site — '
                  'no external agronomic data is used.')

#: 任务来源的稳定标识（第 77 批）。`source` 是中文可读文本（'通用模板'/'管理员录入'），
#: 前端原来用 `source !== '通用模板'` 判断"要不要显示来源标签" —— 英文界面下这句
#: 中文比较仍然成立，但一旦文案调整就会失效。这里额外给出语言无关的 source_key。
SOURCE_KEYS = {
    '通用模板': 'template',
    '管理员录入': 'admin',
}


def _source_key(source):
    return SOURCE_KEYS.get(source, 'custom')


def _is_admin(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_staff or user.is_superuser or getattr(user, 'role', None) == 'ADMIN')
    )


def _serialize_task(task):
    return {
        'id': task.id,
        'crop_type': task.crop_type,
        'crop_type_en': _crop_en(task.crop_type),
        'month': task.month,
        'task_type': task.task_type,
        'task_type_display': task.get_task_type_display(),
        'title': task.title,
        'title_en': task.title_en,
        'detail': task.detail,
        'detail_en': task.detail_en,
        'source': task.source,
        # 第 77 批：来源的英文写法 + 语言无关的标识
        'source_key': _source_key(task.source),
        'source_en': 'Admin entry' if _source_key(task.source) == 'admin' else (
            'General template' if _source_key(task.source) == 'template' else task.source
        ),
        'is_active': task.is_active,
    }


#: 中文作物名 → 英文（与百科里的 crop_type_en 保持一致，这里作为兜底）
_CROP_EN = {
    '柑橘': 'Citrus', '玉米': 'Corn', '番茄': 'Tomato', '苹果': 'Apple',
    '草莓': 'Strawberry', '葡萄': 'Grape', '马铃薯': 'Potato',
}


def _crop_en(crop_type):
    """作物英文名：优先取百科里同一作物的 crop_type_en，取不到用内置表兜底"""
    if not crop_type:
        return ''
    cached = _CROP_EN.get(crop_type)
    if cached:
        return cached
    value = (
        PestInfo.objects.filter(crop_type=crop_type)
        .exclude(crop_type_en='')
        .values_list('crop_type_en', flat=True)
        .first()
    )
    return value or ''


def _crop_options():
    """可选作物：直接用百科里真实存在的作物类型，避免出现"系统里没有的作物" """
    return sorted(
        {value for value in PestInfo.objects.values_list('crop_type', flat=True) if value}
    )


class CalendarView(APIView):
    """某月的种植日历"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.utils import timezone
        today = timezone.localdate()

        try:
            month = int(request.query_params.get('month', today.month))
        except (TypeError, ValueError):
            month = today.month
        month = max(1, min(12, month))

        crop = (request.query_params.get('crop') or '').strip()
        crops = _crop_options()

        # 第 77 批：所有"内容数据"里的中文名一次性给出英文对照。
        # 作物下拉、作物分组标题、"你种过的作物"按钮、右侧榜单都用它，
        # 免得前端为每个字段各写一套兜底。
        pest_name_en_map, crop_en_map = pest_en_maps()

        # ---------- ① 农事任务（通用模板 / 管理员维护） ----------
        task_query = CalendarTask.objects.filter(month=month, is_active=True)
        if crop and crop != 'all':
            task_query = task_query.filter(crop_type=crop)
        tasks = [_serialize_task(task) for task in task_query]

        # ---------- ② 我种过的作物（真实数据：我识别过的作物） ----------
        my_crops = []
        my_history = []
        if getattr(request.user, 'is_authenticated', False):
            my_crops = sorted({
                value for value in DetectionHistory.objects
                .filter(user=request.user, pest_info__isnull=False)
                .values_list('pest_info__crop_type', flat=True) if value
            })
            # 去年同期我自己识别出过什么（给"去年这个时候"的对照）
            for row in (
                DetectionHistory.objects
                .filter(user=request.user, timestamp__month=month, pest_info__isnull=False)
                .values('pest_info__name', 'pest_info__crop_type')
                .annotate(count=Count('id'))
                .order_by('-count')[:5]
            ):
                my_history.append({
                    'name': row['pest_info__name'],
                    'name_en': pest_name_en_map.get(row['pest_info__name'], ''),
                    'crop_type': row['pest_info__crop_type'],
                    'crop_type_en': crop_en_map.get(row['pest_info__crop_type'], ''),
                    'count': row['count'],
                })

        # 未指定作物时，默认聚焦"我种过的作物"；没有历史就展示全部
        scope_crops = [crop] if (crop and crop != 'all') else (my_crops or crops)

        # ---------- ③ 本月需重点防范（站内真实统计） ----------
        seasonal_pests = []
        if scope_crops:
            rows = (
                DetectionHistory.objects
                .filter(
                    timestamp__month=month,
                    pest_info__isnull=False,
                    pest_info__crop_type__in=scope_crops,
                )
                .values('pest_info__name', 'pest_info__crop_type', 'pest_info__english_identifier')
                .annotate(count=Count('id'))
                .order_by('-count')[:8]
            )
            seasonal_pests = [
                {
                    'name': row['pest_info__name'],
                    'name_en': pest_name_en_map.get(row['pest_info__name'], ''),
                    'crop_type': row['pest_info__crop_type'],
                    'crop_type_en': crop_en_map.get(row['pest_info__crop_type'], ''),
                    'identifier': row['pest_info__english_identifier'],
                    'count': row['count'],
                    'url': f'/pests/{row["pest_info__english_identifier"]}',
                }
                for row in rows
            ]

        # ---------- ④ 按作物分组（前端直接渲染） ----------
        grouped = {}
        for task in tasks:
            grouped.setdefault(task['crop_type'], []).append(task)
        for items in grouped.values():
            items.sort(key=lambda item: TASK_TYPE_ORDER.index(item['task_type'])
                       if item['task_type'] in TASK_TYPE_ORDER else 99)

        # 第 77 批：给"作物中文名 → 英文名"的完整对照表，前端下拉/标签统一取它。
        # 覆盖范围：可选作物 + 我种过的作物 + 任务涉及的作物（后者已在 _serialize_task 里带过）。
        crop_names_en = {
            name: crop_en_map.get(name) or _crop_en(name)
            for name in {*crops, *my_crops, *(task['crop_type'] for task in tasks if task['crop_type'])}
        }
        crop_names_en = {name: en for name, en in crop_names_en.items() if en}

        return Response({
            'month': month,
            'year': today.year,
            'is_current_month': month == today.month,
            'crop_filter': crop or 'all',
            'crops': crops,
            'my_crops': my_crops,
            'crop_names_en': crop_names_en,
            'scope_crops': scope_crops,
            'task_groups': [
                {'crop_type': key, 'crop_type_en': crop_names_en.get(key, ''), 'tasks': value}
                for key, value in grouped.items()
            ],
            'task_total': len(tasks),
            'seasonal_pests': seasonal_pests,
            'my_history': my_history,
            'source_note': SOURCE_NOTE,
            'source_note_en': SOURCE_NOTE_EN,
        })


class CalendarTaskListView(APIView):
    """任务列表（所有人可看）/ 新增（仅管理员）"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = CalendarTask.objects.all()
        crop = (request.query_params.get('crop') or '').strip()
        month = (request.query_params.get('month') or '').strip()
        if crop:
            queryset = queryset.filter(crop_type=crop)
        if month.isdigit():
            queryset = queryset.filter(month=int(month))
        return Response({
            'count': queryset.count(),
            'results': [_serialize_task(task) for task in queryset[:500]],
        })

    def post(self, request):
        if not _is_admin(request.user):
            return Response({'detail': '只有管理员可以维护种植日历'}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        crop_type = (data.get('crop_type') or '').strip()
        title = (data.get('title') or '').strip()
        try:
            month = int(data.get('month'))
        except (TypeError, ValueError):
            return Response({'detail': '月份不合法'}, status=status.HTTP_400_BAD_REQUEST)

        if not crop_type:
            return Response({'detail': '请填写作物'}, status=status.HTTP_400_BAD_REQUEST)
        if not title:
            return Response({'detail': '请填写任务标题'}, status=status.HTTP_400_BAD_REQUEST)
        if not 1 <= month <= 12:
            return Response({'detail': '月份必须在 1~12 之间'}, status=status.HTTP_400_BAD_REQUEST)

        task_type = data.get('task_type') or 'other'
        if task_type not in {choice[0] for choice in CalendarTask.TASK_TYPES}:
            task_type = 'other'

        if CalendarTask.objects.filter(crop_type=crop_type, month=month, title=title).exists():
            return Response({'detail': f'{crop_type} {month} 月已经有同名任务了'},
                            status=status.HTTP_400_BAD_REQUEST)

        task = CalendarTask.objects.create(
            crop_type=crop_type, month=month, task_type=task_type, title=title,
            detail=(data.get('detail') or '').strip(),
            source=(data.get('source') or '管理员录入').strip(),
            is_active=bool(data.get('is_active', True)),
            created_by=request.user,
        )
        return Response(_serialize_task(task), status=status.HTTP_201_CREATED)


class CalendarTaskDetailView(APIView):
    """修改 / 删除任务（仅管理员）"""
    permission_classes = [permissions.IsAuthenticated]

    def _get(self, pk):
        return CalendarTask.objects.filter(pk=pk).first()

    def patch(self, request, pk):
        if not _is_admin(request.user):
            return Response({'detail': '只有管理员可以维护种植日历'}, status=status.HTTP_403_FORBIDDEN)
        task = self._get(pk)
        if not task:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        if 'title' in data and not (data.get('title') or '').strip():
            return Response({'detail': '任务标题不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        if 'month' in data:
            try:
                month = int(data.get('month'))
            except (TypeError, ValueError):
                return Response({'detail': '月份不合法'}, status=status.HTTP_400_BAD_REQUEST)
            if not 1 <= month <= 12:
                return Response({'detail': '月份必须在 1~12 之间'}, status=status.HTTP_400_BAD_REQUEST)
            task.month = month

        for field in ('crop_type', 'title', 'detail', 'source'):
            if field in data:
                setattr(task, field, (data.get(field) or '').strip())
        if 'task_type' in data and data.get('task_type') in {c[0] for c in CalendarTask.TASK_TYPES}:
            task.task_type = data.get('task_type')
        if 'is_active' in data:
            task.is_active = bool(data.get('is_active'))

        task.save()
        return Response(_serialize_task(task))

    def delete(self, request, pk):
        if not _is_admin(request.user):
            return Response({'detail': '只有管理员可以维护种植日历'}, status=status.HTTP_403_FORBIDDEN)
        task = self._get(pk)
        if not task:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)
        task.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CalendarCropOptionsView(APIView):
    """可选作物（来自百科里真实存在的作物）"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({'crops': _crop_options()})
