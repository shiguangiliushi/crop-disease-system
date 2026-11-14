"""schema 专用的请求/响应结构（第 388 批）。

## 为什么单独放一个模块

这些 serializer **只用于生成 OpenAPI 文档**，不参与任何运行时校验：
它们的字段描述的是"这个接口实际会收到/返回什么"，让 `/api/docs/` 里能看到真实结构，
而不是一片 `type: object`。

刻意不塞进 `serializers.py`：那会让"只读文档用"的结构混进运行时序列化器里，
以后有人改错地方很难发现。命名统一 `*Schema`（而不是 `*Serializer`）也是为了这个。

## 使用方式

    from .schema_serializers import AssistantAskRequestSchema, AssistantAskResponseSchema
    from drf_spectacular.utils import extend_schema

    @extend_schema(request=AssistantAskRequestSchema,
                   responses={200: AssistantAskResponseSchema})
    def post(self, request):
        ...

⚠️ 加了 `@extend_schema` 之后，schema 里就会出现这些结构；
**它们必须与实际行为一致**，否则文档比没有更糟。
每次改请求/响应字段，记得同步改这里。
"""
from __future__ import annotations

from rest_framework import serializers


# ══════════════════════════════════════════════════════════════════════
# 助手（assistant）
# ══════════════════════════════════════════════════════════════════════
class AssistantAskRequestSchema(serializers.Serializer):
    """`POST /api/assistant/ask/` 的请求体（见 `views_assistant._parse_request`）。"""

    question = serializers.CharField(help_text='用户问题，上限 500 字', max_length=500)
    session_id = serializers.IntegerField(
        required=False, allow_null=True, help_text='续问时带上一轮的会话 id')
    pest_identifier = serializers.CharField(
        required=False, allow_blank=True,
        help_text='识别结果直连的病害标识，如 tomato___late_blight')
    image = serializers.FileField(required=False, help_text='可选图片；给了会先用本地模型识别')
    allow_llm = serializers.BooleanField(
        required=False, default=True,
        help_text='隐私开关：false 时只返回词条原文，不产生任何外部模型请求')


class AssistantCitationSchema(serializers.Serializer):
    """回答里引用到的词条（前端据此显示"来源"）。"""

    pest_id = serializers.IntegerField(help_text='词条主键')
    label = serializers.CharField(help_text='词条名（已按语言本地化）')


class AssistantAskResponseSchema(serializers.Serializer):
    """`POST /api/assistant/ask/` 的响应（非流式）。"""

    session_id = serializers.IntegerField()
    message_id = serializers.IntegerField()
    answer = serializers.CharField()
    degraded = serializers.BooleanField(help_text='true 表示这是降级回答（非模型生成）')
    degrade_reason = serializers.CharField(
        required=False, allow_blank=True,
        help_text='no_source / llm_disabled / llm_error / user_opt_out / session_full 等')
    citations = AssistantCitationSchema(many=True)
    related = serializers.ListField(
        child=serializers.DictField(), help_text='同作物的其他病害（可能为空）')
    usage = serializers.DictField(required=False, help_text='模型 token 用量（降级时为空）')
    truncated = serializers.BooleanField(help_text='答案是否被长度上限截断')


class AssistantSuggestRequestSchema(serializers.Serializer):
    """`POST /api/assistant/suggest/`：追问建议（不调模型，纯模板）。"""

    question = serializers.CharField(required=False, allow_blank=True)
    pest_identifier = serializers.CharField(required=False, allow_blank=True)
    pest_name = serializers.CharField(required=False, allow_blank=True)


class AssistantSuggestResponseSchema(serializers.Serializer):
    suggestions = serializers.ListField(
        child=serializers.DictField(), help_text='[{label, text}] 形式的追问建议')


class AssistantFeedbackRequestSchema(serializers.Serializer):
    """`POST /api/assistant/messages/<pk>/feedback/`。"""

    verdict = serializers.ChoiceField(choices=['useful', 'useless'])
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class AssistantEscalateRequestSchema(serializers.Serializer):
    """`POST /api/assistant/sessions/<pk>/escalate/`：转人工（问专家）。"""

    question = serializers.CharField(required=False, allow_blank=True, max_length=500)
    contact = serializers.CharField(required=False, allow_blank=True, max_length=100)


class AssistantEscalateResponseSchema(serializers.Serializer):
    question_id = serializers.IntegerField(help_text='生成的咨询问题 id')
    created = serializers.BooleanField()


# ══════════════════════════════════════════════════════════════════════
# 日历（calendar）
# ══════════════════════════════════════════════════════════════════════
class CalendarTaskSchema(serializers.Serializer):
    """日历里的一条农事任务。"""

    id = serializers.IntegerField()
    crop_type = serializers.CharField()
    month = serializers.IntegerField()
    task_type = serializers.CharField()
    title = serializers.CharField()
    detail = serializers.CharField(required=False, allow_blank=True)


class CalendarPestStatSchema(serializers.Serializer):
    name = serializers.CharField()
    name_en = serializers.CharField(required=False, allow_blank=True)
    crop_type = serializers.CharField(required=False, allow_blank=True)
    crop_type_en = serializers.CharField(required=False, allow_blank=True)
    count = serializers.IntegerField()


class CalendarDaySchema(serializers.Serializer):
    date = serializers.DateField()
    count = serializers.IntegerField()


class CalendarResponseSchema(serializers.Serializer):
    """`GET /api/calendar/`：整页数据（月份任务 + 当季病害 + 我的历史）。"""

    month = serializers.IntegerField()
    year = serializers.IntegerField(required=False)
    tasks = CalendarTaskSchema(many=True)
    seasonal_pests = CalendarPestStatSchema(many=True)
    my_history = CalendarPestStatSchema(many=True, required=False)
    my_crops = serializers.ListField(child=serializers.CharField(), required=False)
    my_days = CalendarDaySchema(many=True, required=False)
    source_note = serializers.CharField(required=False, allow_blank=True,
                                        help_text='数据来源说明（模板 / 本站记录）')


class TaskReminderSchema(serializers.Serializer):
    """用户自建的任务提醒（`/api/calendar/reminders/`）。"""

    id = serializers.IntegerField()
    title = serializers.CharField()
    crop_type = serializers.CharField(required=False, allow_blank=True)
    remind_at = serializers.DateTimeField()
    note = serializers.CharField(required=False, allow_blank=True)
    done = serializers.BooleanField(required=False)


class TaskReminderRequestSchema(serializers.Serializer):
    title = serializers.CharField(max_length=100)
    crop_type = serializers.CharField(required=False, allow_blank=True, max_length=20)
    remind_at = serializers.DateTimeField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)
