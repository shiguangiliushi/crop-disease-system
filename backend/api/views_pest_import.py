"""
病害百科批量导入（第 44 批）

背景：管理员此前只能一条一条新增病害（百科页的「新增病害」表单），
要把几十上百条病害录进系统非常痛苦。

接口：
| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/pests/import-template/` | GET | 下载导入模板（xlsx，含表头与一行示例） |
| `/api/pests/import/` | POST | 上传 .xlsx / .csv 批量导入（仅管理员） |

导入规则：
  · 表头按**列名**匹配（中英文都认），列的顺序随意；
  · `english_identifier` 是唯一键：默认 **upsert**（存在则更新），也可指定 `create_only` 只新增；
  · **逐行校验**：某一行有问题只跳过该行并记录原因，不会让整批导入失败
    （批量导入最忌讳"第 87 行有问题 → 前 86 行也没进去"）；
  · 支持一列"防治方法"，多条措施用 `|` 分隔，可写成 `化学防治:措施内容`；
  · 单次上限 2000 行。
"""
import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import permissions
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PestInfo, PreventionMethod
from .xlsx import build_workbook, parse_table

logger = logging.getLogger(__name__)
User = get_user_model()

MAX_ROWS = 2000

#: 表头别名 → 内部字段（中英文都认，顺序随意）
HEADER_ALIASES = {
    'name': 'name', '病害名称': 'name', '名称': 'name', '病害': 'name', 'disease': 'name',
    'crop_type': 'crop_type', '作物类型': 'crop_type', '作物': 'crop_type', 'crop': 'crop_type',
    'english_identifier': 'english_identifier', '英文标识符': 'english_identifier',
    '英文标识': 'english_identifier', 'english': 'english_identifier', '标识符': 'english_identifier',
    'symptoms': 'symptoms', '症状': 'symptoms', '症状描述': 'symptoms',
    'description': 'description', '详细描述': 'description', '描述': 'description', '详情': 'description',
    'prevention_methods': 'prevention_methods', '防治方法': 'prevention_methods',
    '防治措施': 'prevention_methods', '防治建议': 'prevention_methods',
}

TEMPLATE_HEADERS = ['病害名称', '作物类型', '英文标识符', '症状', '详细描述', '防治方法']
TEMPLATE_EXAMPLE = [
    '番茄晚疫病', '番茄', 'Tomato___Late_blight',
    '叶片出现暗绿色水浸状病斑，迅速扩大为褐色大斑，潮湿时叶背有白霉。',
    '由致病疫霉引起，低温高湿条件下流行迅速，可造成大面积减产。',
    '农业防治:合理轮作，避免与茄科作物连作|化学防治:发病初期喷施烯酰吗啉或霜脲氰|监测预警:连续阴雨天气提前预防',
]

#: 防治类别中文 → 模型枚举
CATEGORY_MAP = {
    '农业防治': 'AGRICULTURAL', '化学防治': 'CHEMICAL', '生态防治': 'ECOLOGICAL',
    '物理防治': 'PHYSICAL', '监测预警': 'MONITORING',
    'agricultural': 'AGRICULTURAL', 'chemical': 'CHEMICAL', 'ecological': 'ECOLOGICAL',
    'physical': 'PHYSICAL', 'monitoring': 'MONITORING',
}


def _is_admin(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_staff or user.is_superuser or getattr(user, 'role', None) == 'ADMIN')
    )


class PestImportTemplateView(APIView):
    """下载导入模板（仅管理员）"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not _is_admin(request.user):
            return Response({'detail': '只有管理员可以下载导入模板'}, status=403)

        content = build_workbook(
            TEMPLATE_HEADERS,
            [TEMPLATE_EXAMPLE],
            sheet_name='病害导入模板',
            column_widths=[18, 12, 26, 46, 40, 60],
        )
        from django.http import HttpResponse
        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="pest-import-template.xlsx"'
        return response


class PestImportView(APIView):
    """批量导入病害（仅管理员，.xlsx / .csv）"""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        if not _is_admin(request.user):
            return Response({'detail': '只有管理员可以批量导入病害'}, status=403)

        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': '请选择要导入的文件（.xlsx 或 .csv）'}, status=400)

        mode = (request.POST.get('mode') or 'upsert').strip()
        if mode not in ('upsert', 'create_only'):
            return Response({'detail': '导入模式不合法'}, status=400)

        try:
            rows = parse_table(upload.name, upload.read())
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        except Exception:
            logger.exception('解析导入文件失败: %s', upload.name)
            return Response({'detail': '文件解析失败，请确认是本系统提供的模板格式'}, status=400)

        if not rows:
            return Response({'detail': '文件里没有数据'}, status=400)
        if len(rows) - 1 > MAX_ROWS:
            return Response({'detail': f'单次最多导入 {MAX_ROWS} 行，当前 {len(rows) - 1} 行'}, status=400)

        header_map = self._map_headers(rows[0])
        missing = [key for key in ('name', 'crop_type', 'english_identifier') if key not in header_map.values()]
        if missing:
            labels = {'name': '病害名称', 'crop_type': '作物类型', 'english_identifier': '英文标识符'}
            return Response({
                'detail': '表头缺少必需列：' + '、'.join(labels[item] for item in missing),
                'hint': '可以下载导入模板，按模板表头填写',
            }, status=400)

        result = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': [], 'total': len(rows) - 1}

        for offset, raw_row in enumerate(rows[1:], start=2):  # 从 Excel 第 2 行开始
            data = self._row_to_dict(raw_row, header_map, rows[0])
            try:
                with transaction.atomic():
                    action = self._save_row(data, mode)
                if action == 'created':
                    result['created'] += 1
                elif action == 'updated':
                    result['updated'] += 1
                else:
                    result['skipped'] += 1
            except ValueError as exc:
                result['skipped'] += 1
                # 只保留前 50 条错误，避免响应体过大
                if len(result['errors']) < 50:
                    result['errors'].append({'row': offset, 'message': str(exc)})
            except Exception as exc:  # pragma: no cover - 兜底
                logger.exception('导入第 %s 行失败', offset)
                result['skipped'] += 1
                if len(result['errors']) < 50:
                    result['errors'].append({'row': offset, 'message': f'保存失败：{exc}'})

        logger.info('病害批量导入: user=%s %s', request.user.id, result)
        result['message'] = (
            f'导入完成：新增 {result["created"]} 条、更新 {result["updated"]} 条、'
            f'跳过 {result["skipped"]} 条'
        )
        return Response(result)

    # ------------------------------------------------------------------ 内部
    def _map_headers(self, header_row):
        """表头行 → {列下标: 字段名}"""
        mapping = {}
        for index, title in enumerate(header_row):
            key = (title or '').strip().lower().replace(' ', '')
            field = HEADER_ALIASES.get(key) or HEADER_ALIASES.get((title or '').strip())
            if field:
                mapping[index] = field
        return mapping

    def _row_to_dict(self, row, header_map, header_row):
        data = {}
        for index, field in header_map.items():
            value = row[index] if index < len(row) else ''
            data[field] = (value or '').strip()
        return data

    def _save_row(self, data, mode):
        name = data.get('name', '')
        crop_type = data.get('crop_type', '')
        identifier = data.get('english_identifier', '')

        if not name:
            raise ValueError('病害名称为空')
        if not crop_type:
            raise ValueError('作物类型为空')
        if not identifier:
            raise ValueError('英文标识符为空（它是唯一键，不能留空）')
        if len(identifier) > 255:
            raise ValueError('英文标识符过长（最多 255 字符）')

        existing = PestInfo.objects.filter(english_identifier=identifier).first()

        if existing and mode == 'create_only':
            raise ValueError(f'英文标识符「{identifier}」已存在（当前为只新增模式）')

        defaults = {
            'name': name,
            'crop_type': crop_type,
            'symptoms': data.get('symptoms') or '暂无症状描述',
            'description': data.get('description') or '暂无详细描述',
        }

        if existing:
            # 同名的另一条记录会违反 (name, crop_type) 唯一约束，提前拦下来给友好提示
            conflict = PestInfo.objects.filter(name=name, crop_type=crop_type).exclude(pk=existing.pk).exists()
            if conflict:
                raise ValueError(f'已存在同名同作物的病害「{crop_type} - {name}」')
            for field, value in defaults.items():
                setattr(existing, field, value)
            existing.save()
            pest, action = existing, 'updated'
        else:
            if PestInfo.objects.filter(name=name, crop_type=crop_type).exists():
                raise ValueError(f'已存在同名同作物的病害「{crop_type} - {name}」，请改用它的英文标识符更新')
            pest = PestInfo.objects.create(english_identifier=identifier, **defaults)
            action = 'created'

        methods = data.get('prevention_methods', '')
        if methods:
            self._replace_prevention_methods(pest, methods)

        return action

    def _replace_prevention_methods(self, pest, raw):
        """
        写入防治方法（多条用 | 分隔）

        写法：`化学防治:喷施烯酰吗啉` 或只写措施（默认归到"农业防治"）。
        同一病害的旧措施会被整体替换 —— 导入语义是"以表格为准"，避免重复累积。
        """
        entries = [item.strip() for item in raw.replace('｜', '|').split('|') if item.strip()]
        if not entries:
            return

        parsed = []
        for entry in entries:
            if ':' in entry or '：' in entry:
                category_text, measure = entry.replace('：', ':').split(':', 1)
                category = CATEGORY_MAP.get(category_text.strip().lower()) or CATEGORY_MAP.get(category_text.strip())
                if not category:
                    raise ValueError(f'防治类别「{category_text.strip()}」无法识别（可用：农业/化学/生态/物理防治、监测预警）')
                measure = measure.strip()
            else:
                category, measure = 'AGRICULTURAL', entry
            if not measure:
                raise ValueError('防治方法内容为空')
            parsed.append((category, measure))

        pest.prevention_methods.all().delete()
        PreventionMethod.objects.bulk_create([
            PreventionMethod(pest=pest, category=category, measure=measure)
            for category, measure in parsed
        ])
