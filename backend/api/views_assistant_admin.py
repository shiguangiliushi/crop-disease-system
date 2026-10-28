"""助手质量看板（第 228 批）—— 把"都落库了、但没人看"的数据聚合成一页。

    GET /api/admin/assistant/stats/?days=14

## 为什么要它

第 193–212 批把整套可观测字段都记下来了：`degraded` / `degrade_reason` /
`latency_ms` / `usage`（token）/ `verdict` / `feedback_note` / `prompt_version`。
但这些字段**没有任何界面在读** —— 出了"助手最近答得不好"这种问题时，只能进
Django admin 一条条翻。看板回答的是四个一直没人能回答的问题：

  1. **降级率多少**？（`no_source` 是不是在涨）
  2. **哪类问题答不上来**？（`no_source` 的原始问题 Top 榜 = 知识库缺口清单）
  3. **用户说"没用"时在说什么**？（`verdict='useless'` 的 note —— 最有价值的信号）
  4. **成本与延迟什么水位**？（日均 token / 平均延迟）

## 口径（写给后来改的人）

  · 时间窗按**消息创建时间**过滤，不是会话创建时间 —— 一个会话可能跨好几天；
  · `degraded_rate` 的分母是**回答数**（不是问题数）：流式空行已被排除，
    "问答各一条"的实现决定了这两个数在正常情况下相等，但分母取回答更诚实；
  · **`no_source` 的"问题"取该条回答前最近的一条用户消息**（同一会话内按 id 找），
    而不是"会话标题"—— 一个会话里前面几问答得上、第 4 问才无来源，标题会误导；
  · 榜单对问题做**空白归一**后聚合（"番茄 晚疫病"与"番茄晚疫病"算一条），
    但显示用的是最近一次的原样文本。

**仅全权管理员**（`is_full_admin`，与系统健康 / 操作日志同一档）：
里面既有别人的提问原文，也有模型成本，属于管理端内部信息。
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .capabilities import is_full_admin
from .models import PestInfo
from .models_assistant import AssistantMessage

logger = logging.getLogger(__name__)

#: 时间窗上限（再长就把整库扫一遍了）
MAX_DAYS = 90
DEFAULT_DAYS = 14
#: 缺口榜单扫描多少条最近的 no_source（只影响榜单，不影响上面的统计）
GAP_SCAN_LIMIT = 200
#: 榜单显示几条
GAP_TOP = 10
#: "用户说没用"最多列几条
USELESS_LIMIT = 20
#: 引用统计最多扫多少条回答（防止一次请求把整库 citations 读进内存）
CITATION_SCAN_LIMIT = 2000


def _days_from(request) -> int:
    """解析 `?days=`：非法值一律回落默认（与其它管理端列表"非法筛选忽略"一致）。"""
    try:
        days = int(request.query_params.get('days', DEFAULT_DAYS))
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return max(1, min(MAX_DAYS, days))


def _normalize(text: str) -> str:
    """空白归一（"番茄  晚疫病 " → "番茄 晚疫病"）"""
    return ' '.join((text or '').split()).strip()


def _questions_before(answers) -> dict[int, str]:
    """给一批助手消息各找"上一条用户消息"（**一次查询**，不 N+1）。

    为什么按 id 而不是按时间：消息是同一个事务里顺序写入的，id 顺序就是对话顺序，
    而时间戳在 SQLite 上可能同一秒（`auto_now_add` 精度不够分先后）。
    """
    session_ids = {answer.session_id for answer in answers}
    rows = list(
        AssistantMessage.objects
        .filter(session_id__in=session_ids, role='user')
        .order_by('session_id', 'id')
        .values_list('id', 'session_id', 'content')
    )
    by_session: dict[int, list[tuple[int, str]]] = {}
    for message_id, session_id, content in rows:
        by_session.setdefault(session_id, []).append((message_id, content))

    result: dict[int, str] = {}
    for answer in answers:
        picked = ''
        for message_id, content in by_session.get(answer.session_id, []):
            if message_id >= answer.id:
                break
            picked = content
        result[answer.id] = picked
    return result


def _token_totals(answers) -> dict:
    """token 用量合计。

    先走数据库聚合（SQLite / PostgreSQL 都支持 JSONField 的键路径聚合）；
    个别环境不支持键路径 `Sum` 时退化为 Python 累加 —— 看板是只读页，
    宁可慢一点也不要 500。
    """
    try:
        row = answers.aggregate(
            prompt=Sum('usage__prompt_tokens'),
            completion=Sum('usage__completion_tokens'),
        )
        return {'prompt': int(row['prompt'] or 0), 'completion': int(row['completion'] or 0)}
    except Exception:  # noqa: BLE001 —— 见 docstring：不支持的库退化成 Python
        logger.info('助手看板：JSON 聚合不可用，改用 Python 累加')
        prompt = completion = 0
        for usage in answers.values_list('usage', flat=True):
            if isinstance(usage, dict):
                prompt += int(usage.get('prompt_tokens') or 0)
                completion += int(usage.get('completion_tokens') or 0)
        return {'prompt': prompt, 'completion': completion}


def _trend(questions, answers, days: int, today) -> list[dict]:
    """按天趋势（含没有数据的空白日 —— 前端要画连续折线，缺日会连成直线）。

    ⚠️ `today` 必须是**本地日期**（`timezone.localdate()`），不是 `timezone.now().date()`。
    第 233 批修过这个 bug：`TruncDate('created_at')` 按 `TIME_ZONE`（Asia/Shanghai）
    切成**本地日期**，而窗口末端原来取的是 UTC 日期 —— 本地时间 00:30 时两者差一天，
    刚问的问题落在"明天"那一桶里，`trend[-1]` 变成 0（`test_trend_fills_every_day` 在
    跨零点的那次全量测试里就红了）。
    """
    def _by_day(queryset):
        rows = (
            queryset.annotate(day=TruncDate('created_at'))
            .values('day').annotate(n=Count('id'))
        )
        return {row['day']: row['n'] for row in rows}

    questions_by_day = _by_day(questions)
    degraded_by_day = _by_day(answers.filter(degraded=True))
    no_source_by_day = _by_day(answers.filter(degrade_reason='no_source'))

    trend = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        trend.append({
            'date': day.isoformat(),
            'questions': questions_by_day.get(day, 0),
            'degraded': degraded_by_day.get(day, 0),
            'no_source': no_source_by_day.get(day, 0),
        })
    return trend


def _gap_questions(answers) -> list[dict]:
    """知识库缺口：`no_source` 回答对应的原始问题（归一后按次数排序）。"""
    recent = list(answers.order_by('-id')[:GAP_SCAN_LIMIT])
    questions = _questions_before(recent)

    counter: Counter = Counter()
    example: dict[str, str] = {}
    last_at: dict[str, object] = {}
    for answer in recent:
        raw = questions.get(answer.id) or ''
        key = _normalize(raw).lower()
        if not key:
            continue
        counter[key] += 1
        example.setdefault(key, _normalize(raw))
        if key not in last_at or answer.created_at > last_at[key]:
            last_at[key] = answer.created_at

    return [
        {'question': example[key], 'count': count,
         'last_at': last_at[key].isoformat() if last_at.get(key) else None}
        for key, count in counter.most_common(GAP_TOP)
    ]


def _useless_feedback(answers) -> list[dict]:
    """用户点了"没用"的回答：带上原问题、说明与回答开头 —— 这是最该被看的信号。"""
    recent = list(
        answers.filter(verdict='useless').order_by('-feedback_at', '-id')[:USELESS_LIMIT]
    )
    questions = _questions_before(recent)
    return [
        {
            'message_id': answer.id,
            'session_id': answer.session_id,
            'question': _normalize(questions.get(answer.id) or ''),
            'note': answer.feedback_note,
            'answer_preview': (answer.content or '').strip().replace('\n', ' ')[:120],
            'degraded': bool(answer.degraded),
            'degrade_reason': answer.degrade_reason,
            'lang': answer.lang,
            'feedback_at': (answer.feedback_at or answer.created_at).isoformat(),
        }
        for answer in recent
    ]


def _top_sources(answers) -> list[dict]:
    """被引用最多的词条（回答里 `citations[].pest_id`）。

    它回答的是"哪几条语料在撑回答"——如果某条词条被引用占比异常高，
    说明语料分布不均；如果某条被引用了却总被评没用，说明是语料写得不清楚。

    ⚠️ 词条名要**中英都回**（第 229 批补）：这里原来只查 `name`，于是英文界面下
    「Most cited entries」后面挂着一串中文病名 —— 数据本身有 `name_en`，是接口没给。
    这个项目的约定是"数据级双语由前端按当前语言选"（同 `result_en` / `crop_type_en`），
    所以返回两个字段，不在后端猜语言。
    """
    counter: Counter = Counter()
    for citations in answers.order_by('-id').values_list('citations', flat=True)[:CITATION_SCAN_LIMIT]:
        for item in citations or []:
            pest_id = item.get('pest_id') if isinstance(item, dict) else None
            if pest_id:
                counter[int(pest_id)] += 1
    if not counter:
        return []
    rows = {
        pk: (name, name_en)
        for pk, name, name_en in PestInfo.objects.filter(
            pk__in=counter.keys(),
        ).values_list('pk', 'name', 'name_en')
    }
    return [
        {
            'pest_id': pest_id,
            # 中文名兜底：`name_en` 允许为空（老词条没填）
            'name': rows.get(pest_id, (f'#{pest_id}', ''))[0],
            'name_en': rows.get(pest_id, ('', ''))[1],
            'count': count,
        }
        for pest_id, count in counter.most_common(GAP_TOP)
    ]


class AdminAssistantStatsView(APIView):
    """`GET /api/admin/assistant/stats/` —— 助手质量看板（仅全权管理员，只读）"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not is_full_admin(request.user):
            return Response(
                {'detail': '仅全权管理员可查看助手质量看板'},
                status=status.HTTP_403_FORBIDDEN,
            )

        days = _days_from(request)
        now = timezone.now()
        # 第 233 批：窗口按**本地日**对齐（与趋势桶同一把尺子）：
        #   · 统计窗口从"最早展示那天的 00:00 本地时间"开始 —— 原来的 now-days
        #     会在跨零点时让最早那天少算半天；
        #   · trend 的末端日期用 localdate()，不要用 now.date()（那是 UTC 日期）。
        today = timezone.localdate()
        start_day = today - timedelta(days=days - 1)
        since = datetime.combine(start_day, time.min)
        if settings.USE_TZ:
            since = timezone.make_aware(since)

        questions = AssistantMessage.objects.filter(role='user', created_at__gte=since)
        # 流式回答会先建空行再回填；统计里只算**有内容**的回答，
        # 否则一条失败的空行会把降级率的分母抬高。
        answers = (
            AssistantMessage.objects
            .filter(role='assistant', created_at__gte=since)
            .exclude(content='')
        )

        question_count = questions.count()
        answer_count = answers.count()
        degraded = answers.filter(degraded=True).count()
        helpful = answers.filter(verdict='helpful').count()
        useless = answers.filter(verdict='useless').count()

        latency = answers.filter(degraded=False).aggregate(avg=Avg('latency_ms'))['avg'] or 0

        payload = {
            'range': {'days': days, 'start': since.isoformat(), 'end': now.isoformat()},
            'totals': {
                'questions': question_count,
                'answers': answer_count,
                'degraded': degraded,
                'degraded_rate': round(degraded / answer_count, 4) if answer_count else 0.0,
                'no_source': answers.filter(degrade_reason='no_source').count(),
                'rate_limited': answers.filter(degrade_reason='rate_limited').count(),
                'session_full': answers.filter(degrade_reason='session_full').count(),
                'llm_error': answers.filter(degrade_reason__startswith='llm_error').count(),
                'llm_disabled': answers.filter(degrade_reason='llm_disabled').count(),
                'helpful': helpful,
                'useless': useless,
                'useless_rate': round(useless / (helpful + useless), 4) if (helpful + useless) else 0.0,
                'avg_latency_ms': int(latency),
                'tokens': _token_totals(answers),
            },
            'languages': {
                row['lang'] or 'zh': row['n']
                for row in answers.values('lang').annotate(n=Count('id'))
            },
            'trend': _trend(questions, answers, days, today),
            'gaps': {
                'no_source_questions': _gap_questions(answers.filter(degrade_reason='no_source')),
                'useless': _useless_feedback(answers),
            },
            'top_sources': _top_sources(answers),
        }
        return Response(payload)
