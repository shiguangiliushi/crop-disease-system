"""八个只读工具 —— 系统助手**读**侧的"手脚"。

写侧不在这里：第 423 批另开了 `actions.py`（三个可逆写工具 + 独立注册表）。
分开的理由见那个模块的说明 —— 这个文件的第一条铁律（只读）是被
`orchestrator._execute()` / 降级矩阵 / 六条单测共同信任的，不能靠"我记得别在这儿写"来维持。

契约见 `docs/系统助手框架.md` 第五节。三条铁律：

1. **只读**。不写库、不删文件、不改配置。要执行命令只能走 `run_check()` 的白名单，
   且白名单里只有诊断命令（它们都不写库）。
2. **复用唯一实现**。`check_env` / `_counts` / `_media_size` / `_history` /
   `_runtime_model_stats` 全部调既有函数，工具里不重写检查 ——
   "同一个检查写两份"正是本项目反复栽的坑（第 16/17、128、149 批）。
3. **出站脱敏**。所有字符串过 `redact.text()`；健康页 `runtime` 里那几个绝对路径字段
   **整份不返回**（它们会随请求发给外部模型，见框架文档 9.1）。

为什么每个工具都回结构化 JSON 而不是自然语言：答案里的数字必须能被 `verify.py` 机检，
自然语言没法核对（这就是 `citations.verify()` 在运维侧的等价物）。
"""
from __future__ import annotations

import functools
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from . import redact

logger = logging.getLogger(__name__)

#: `docs/` 目录（`settings.BASE_DIR` 是 `backend/`）
DOCS_ROOT = Path(settings.BASE_DIR).parent / 'docs'
#: 检索时跳过的 docs 子目录：知识库是农业语料，不是运维文档
DOCS_SKIP_DIRS = {'knowledge_base', 'images', 'backup'}
#: 单次检索最多读多少篇文档（防止 docs 膨胀后把一次问答拖成几十秒）
DOCS_MAX_FILES = 200
#: 工具输出里 checks 最多带多少条（check_env 现在约 40 条，超了就是被人加了东西）
CHECKS_LIMIT = 80

#: `run_check()` 的白名单。**只放诊断命令** —— 它们都不写库、不删文件。
READONLY_COMMANDS = {
    'check_env': '依赖 / 应用 / 运行时 / 生产开关自检',
    'check_model_labels': '权重类名与病害词条映射是否错位',
    'check_assistant': '智能回答助手的配置与语料（默认不联网）',
}


@dataclass
class ToolResult:
    """一个工具的执行结果。`data` 是给模型看的，`evidence` 是给人核对的。"""

    name: str = ''
    ok: bool = False
    data: dict = field(default_factory=dict)
    #: [{'title': str, 'source': 'file:line' | '命令', 'lines': [str]}]
    evidence: list = field(default_factory=list)
    ms: int = 0
    #: ok=False 时的人读原因。**会进上下文**，所以必须已脱敏。
    error: str = ''
    truncated: bool = False

    def as_dict(self) -> dict:
        return {
            'name': self.name, 'ok': self.ok, 'data': self.data, 'evidence': self.evidence,
            'ms': self.ms, 'error': self.error, 'truncated': self.truncated,
        }

    @property
    def metric(self) -> dict:
        """落库用：只留"调了什么、成不成、多久"（返回值不落库）"""
        return {'name': self.name, 'ok': self.ok, 'ms': self.ms, 'error': self.error}


# ══════════════════════════════════════════════════════════════════════
# 内部工具
# ══════════════════════════════════════════════════════════════════════

def _check_env_json() -> str | None:
    """跑 `check_env --json` 并取回原始 JSON 文本（**唯一**的环境检查实现）"""
    buffer = StringIO()
    try:
        call_command('check_env', as_json=True, stdout=buffer)
    except SystemExit:
        # `--strict` 且有 problems 才会抛；我们没传 strict，这里只是防御
        pass
    except Exception:  # noqa: BLE001 —— 诊断命令自身崩了，不该让问答跟着 500
        logger.exception('check_env 执行失败')
        return None
    return buffer.getvalue() or None


def _tool(func):
    """给每个工具套上「计时 + 兜异常」的壳。

    失败一律变成 `ok=False`（带脱敏后的原因）而**不向上抛** —— 编排层按"某个工具挂了"
    处理，其余工具照常（框架文档 6.2 的降级矩阵）。
    装饰器而不是再包一层函数：一个工具只该有一份签名与一份文档（第 415 批收的）。
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        started = time.time()
        try:
            result = func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.exception('系统助手工具失败 name=%s', func.__name__)
            result = ToolResult(
                name=func.__name__, ok=False,
                error=redact.text(str(exc) or type(exc).__name__),
            )
        result.name = func.__name__
        result.ms = int((time.time() - started) * 1000)
        return result

    return wrapper


# ══════════════════════════════════════════════════════════════════════
# 1. 系统健康
# ══════════════════════════════════════════════════════════════════════

@_tool
def get_system_health() -> ToolResult:
    """四节环境检查 + 数据量 + media 体积（与管理端「系统健康」同一套检查）。

    ⚠️ 只回 `level` / `text`（脱敏后），**不返回** `runtime` —— 那个字典全是绝对路径。
    """
    from ...views_system_health import _counts, _media_size

    raw = _check_env_json()
    if not raw:
        return ToolResult(ok=False, error='check_env 没有返回结果')
    try:
        payload = json.loads(raw)
    except ValueError:
        return ToolResult(ok=False, error='check_env 的输出不是合法 JSON')

    checks = []
    for item in (payload.get('results') or [])[:CHECKS_LIMIT]:
        checks.append({
            'level': item.get('level') or 'ok',
            'text': redact.text(item.get('text') or ''),
            'section': item.get('section') or '',
        })

    problems = [redact.text(text) for text in (payload.get('problems') or [])]
    warnings = [redact.text(text) for text in (payload.get('warnings') or [])]
    level = 'fail' if problems else ('warn' if warnings else 'ok')

    counts: dict = {}
    media: dict = {}
    try:
        counts = _counts()
    except Exception:  # noqa: BLE001 —— 数据量概览查不出来不影响检查结论
        logger.exception('健康页数据量概览失败')
    try:
        media = _media_size()
    except Exception:  # noqa: BLE001
        logger.exception('健康页 media 体积统计失败')

    data = {
        'level': level,
        'ok': bool(payload.get('ok')),
        #: 现成的计数。**必须有** —— 否则模型只能自己数列表长度，
        #: 数错一个就会被 `verify_numbers` 判成编造、整段答案被换成表格
        #: （实测 30 条问题里有 5 条栽在这里）。
        'problem_count': len(problems),
        'warning_count': len(warnings),
        'check_count': len(checks),
        'problems': problems,
        'warnings': warnings,
        'checks': checks,
        'counts': counts,
        'media': media,
        'source': 'check_env --json（与管理端「系统健康」同一套检查）',
    }
    evidence = [{
        'title': '环境自检',
        'source': 'python manage.py check_env --json',
        'lines': (problems or warnings or ['✓ 四节检查全部通过'])[:5],
    }]
    return ToolResult(ok=True, data=data, evidence=evidence,
                      truncated=len(payload.get('results') or []) > CHECKS_LIMIT)


# ══════════════════════════════════════════════════════════════════════
# 2. 健康趋势（快照）
# ══════════════════════════════════════════════════════════════════════

@_tool
def get_health_trend(days: int = 14) -> ToolResult:
    """最近 N 天健康快照；**缺快照的那天本身就是答案**（说明定时任务没跑）。

    口径复用 `views_system_health._history()`，不在这里重查一遍 `HealthSnapshot`。
    """
    from ...views_system_health import _history

    try:
        days = max(1, min(60, int(days)))
    except (TypeError, ValueError):
        days = 14

    payload = redact.payload(_history(days))
    missing = days - int(payload.get('recorded_days') or 0)
    data = {
        'window': days,
        'recorded_days': payload.get('recorded_days'),
        'missing_days': missing,
        'latest_date': payload.get('latest_date'),
        'days': payload.get('days'),
        'source': 'HealthSnapshot（health_snapshot 命令每天记一条）',
        'note': '缺快照的那天本身就是信息：说明定时任务没跑',
    }
    evidence = [{
        'title': f'近 {days} 天健康快照',
        'source': 'AdminHealthView._history()',
        'lines': [f'记录了 {payload.get("recorded_days")} / {days} 天',
                  f'最新一天：{payload.get("latest_date") or "无"}'],
    }]
    return ToolResult(ok=True, data=data, evidence=evidence)


# ══════════════════════════════════════════════════════════════════════
# 3. 操作日志摘要
# ══════════════════════════════════════════════════════════════════════

@_tool
def get_audit_summary(days: int = 7, action: str | None = None,
                      include_detail: bool = False) -> ToolResult:
    """管理操作聚合（按动作/操作人）+ 最近 10 条。

    默认**不返回 `detail` 原文**：那是管理员自由书写的文本，属用户可控内容
    （框架文档 9.2 的注入面）。要原文请显式 `include_detail=True`，且仍会脱敏。
    """
    from ...models_audit import AdminAuditLog

    try:
        days = max(1, min(90, int(days)))
    except (TypeError, ValueError):
        days = 7

    since = timezone.now() - timedelta(days=days)
    queryset = AdminAuditLog.objects.filter(created_at__gte=since)
    if action:
        queryset = queryset.filter(action=str(action))

    labels = dict(AdminAuditLog.ACTION_CHOICES)
    by_action = [
        {'action': row['action'], 'label': labels.get(row['action'], row['action']), 'count': row['n']}
        for row in queryset.values('action').annotate(n=Count('id')).order_by('-n')
    ]
    by_actor = [
        {'actor': redact.text(row['actor_repr'] or '（未知）'), 'count': row['n']}
        for row in queryset.values('actor_repr').annotate(n=Count('id')).order_by('-n')[:5]
    ]

    recent = []
    for log in queryset.order_by('-created_at', '-id')[:10]:
        item = {
            'action': log.action,
            'label': labels.get(log.action, log.action),
            'actor': redact.text(log.actor_repr or (log.actor.username if log.actor else '系统')),
            'target_type': log.target_type,
            'target': redact.text(log.target_repr),
            'at': log.created_at.isoformat(),
        }
        if include_detail:
            # ⚠️ detail 是管理员自由书写的文本，属于**用户可控内容**。
            # 只在显式要求时给，且截断 + 脱敏；提示词里也声明它是数据不是指令。
            item['detail'] = redact.text(log.detail)[:200]
        else:
            item['detail_len'] = len(log.detail or '')
        recent.append(item)

    total = queryset.count()
    data = {
        'window': {'days': days, 'since': since.date().isoformat()},
        'action_filter': action or '',
        'total': total,
        'by_action': by_action,
        'by_actor': by_actor,
        'recent': recent,
        'detail_included': bool(include_detail),
        'source': 'AdminAuditLog（与「操作日志」页同一张表）',
    }
    evidence = [{
        'title': f'近 {days} 天管理操作',
        'source': 'GET /api/admin/audit-logs/ 的同一数据源',
        'lines': [f'共 {total} 条' + (f'，最多的是 {by_action[0]["label"]}（{by_action[0]["count"]} 次）'
                                     if by_action else '')],
    }]
    return ToolResult(ok=True, data=data, evidence=evidence)


# ══════════════════════════════════════════════════════════════════════
# 4. 运行数据（识别 + 助手质量）
# ══════════════════════════════════════════════════════════════════════

def _assistant_quality(days: int) -> dict:
    """近 N 天 RAG 助手的降级率 / 延迟 / token（系统助手自己另算）"""
    from ...models_assistant import AssistantMessage

    since = timezone.now() - timedelta(days=days)
    answers = AssistantMessage.objects.filter(role='assistant', created_at__gte=since)
    total = answers.count()
    degraded = answers.filter(degraded=True).count()
    no_source = answers.filter(degrade_reason='no_source').count()

    latency = answers.filter(degraded=False).aggregate(
        value=Avg('latency_ms'),
    )['value'] or 0

    prompt_tokens = completion_tokens = 0
    try:
        # 与 `views_assistant_admin._token_totals()` 同一手法：键路径聚合先在数据库里试，
        # 库不支持就退化成 Python 累加（这是只读路径，宁慢一点也不要 500）
        row = answers.aggregate(
            prompt=Sum('usage__prompt_tokens'),
            completion=Sum('usage__completion_tokens'),
        )
        prompt_tokens = int(row['prompt'] or 0)
        completion_tokens = int(row['completion'] or 0)
    except Exception:  # noqa: BLE001
        for usage in answers.values_list('usage', flat=True)[:2000]:
            try:
                prompt_tokens += int((usage or {}).get('prompt_tokens') or 0)
                completion_tokens += int((usage or {}).get('completion_tokens') or 0)
            except (TypeError, ValueError):
                continue

    return {
        'answers': total,
        'degraded': degraded,
        'degraded_rate': round(degraded / total, 4) if total else None,
        'no_source': no_source,
        'avg_latency_ms': int(latency),
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
    }


@_tool
def get_ops_stats(days: int = 7) -> ToolResult:
    """识别量 / 置信度 / 反馈准确率 / 助手降级率；返回值**带口径**（`window` / `comparable`）。"""
    from ...views_system_health import _runtime_model_stats

    try:
        days = max(1, min(90, int(days)))
    except (TypeError, ValueError):
        days = 7

    recognition = _runtime_model_stats(days)
    assistant = _assistant_quality(days)

    data = {
        'window': {'days': days},
        'recognition': recognition,
        'assistant': assistant,
        #: 置信度分桶的**阈值**本身也是数据：模型说"90% 以上有 N 张"时，
        #: 那个 90 必须能在返回值里找到，否则会被判成编造。
        'bucket_thresholds': [50, 70, 90],
        'source': 'DetectionHistory + Feedback(category=recognition) + AssistantMessage',
        # ⚠️ 口径声明不是装饰：管理端「模型使用数据」固定 30 天，
        # 这里按问题取 7 或 30 天，两边数字不能直接对读。
        'comparable': ('识别侧与 /admin/health 的「模型使用数据」同源，但时间窗按问题而定；'
                       '助手侧与 /admin/assistant 的看板同源，同样注意窗口'),
    }
    evidence = [{
        'title': f'近 {days} 天运行数据',
        'source': 'AdminHealthView._runtime_model_stats() + AssistantMessage',
        'lines': [f'识别 {recognition.get("total")} 次，平均置信度 {recognition.get("avg_confidence")}',
                  f'助手回答 {assistant["answers"]} 条，降级率 {assistant["degraded_rate"]}'],
    }]
    return ToolResult(ok=True, data=data, evidence=evidence)


# ══════════════════════════════════════════════════════════════════════
# 5. 训练样本与误判
# ══════════════════════════════════════════════════════════════════════

def _trainable_queryset(days: int):
    """`Feedback` 里"能当训练样本"的那批（与 `Feedback.is_trainable` 同口径）。

    ⚠️ `is_trainable` 是属性，**不能用于 filter**，所以这里把它的三个条件抄了一遍。
    为防两边漂移，单测 `test_trainable_filter_matches_model_property` 会逐条比对
    "查询集的数量"与"用属性数出来的数量" —— 改条件时两边一起改，否则会红。
    """
    from ...models import Feedback

    since = timezone.now() - timedelta(days=days)
    return Feedback.objects.filter(
        category='recognition',
        is_correct=False,
        corrected_pest__isnull=False,
        timestamp__gte=since,
    )


@_tool
def get_feedback_samples(days: int = 30) -> ToolResult:
    """识别纠错样本池：三态分布、可训练数、导出情况、待核验前 5 条。

    **不回 `contact` / `suggestion`** —— 联系方式与用户正文都是农户自己填的，
    进上下文等于发给外部模型（框架文档 9.1）。
    """
    from ...models import Feedback

    try:
        days = max(1, min(180, int(days)))
    except (TypeError, ValueError):
        days = 30

    since = timezone.now() - timedelta(days=days)
    trainable = _trainable_queryset(days)

    states = {value: 0 for value, _label in Feedback.VERIFY_CHOICES}
    for row in trainable.order_by().values('verify_status').annotate(n=Count('id')):
        if row['verify_status'] in states:
            states[row['verify_status']] = row['n']

    pending = []
    for item in (trainable.filter(verify_status='pending')
                 .select_related('corrected_pest').order_by('-timestamp')[:5]):
        pending.append({
            'id': item.id,
            # ⚠️ 只回病害名与状态，**不回 `contact` / `suggestion`** ——
            # 联系方式是农户自己填的，进上下文等于发给外部模型（框架文档 9.1）
            'disease': redact.text(item.disease_name)[:60],
            'corrected_to': redact.text(item.corrected_pest.name)[:60] if item.corrected_pest else '',
            'at': item.timestamp.isoformat(),
        })

    total = Feedback.objects.filter(category='recognition', timestamp__gte=since).count()
    data = {
        'window': {'days': days, 'since': since.date().isoformat()},
        'recognition_feedback': total,
        'trainable': trainable.count(),
        'sample_states': states,
        'exported': trainable.filter(exported_at__isnull=False).count(),
        'pending_samples': pending,
        'source': 'Feedback(category=recognition, corrected_pest 非空)',
        'comparable': ('与 /admin/feedback 的「训练样本三态」统计卡同源（那边是**筛选后的全量**，'
                       '这里是按时间窗），两边数字不可直接对读'),
    }
    evidence = [{
        'title': f'近 {days} 天识别纠错样本',
        'source': 'GET /api/feedback/stats/ 的同一数据源',
        'lines': [f'可训练 {data["trainable"]} 条；'
                  f'待确认 {states.get("pending", 0)} / 已确认 {states.get("confirmed", 0)} / '
                  f'已排除 {states.get("rejected", 0)}；已导出 {data["exported"]} 条'],
    }]
    return ToolResult(ok=True, data=data, evidence=evidence)


@_tool
def get_detection_errors(days: int = 30, threshold: float = 0.5, top: int = 5) -> ToolResult:
    """误判线索：低置信度占比、"不准确"的病害分布、纠错去向、与识别记录的关联率。

    阈值兼容 `0.5` 与 `50` 两种写法，输出统一成百分数；置信度在库里有 0–1 与 0–100
    两套量纲，按值归一（与 `_runtime_model_stats` 同一处理方式）。
    """
    from ...models import DetectionHistory, Feedback

    try:
        days = max(1, min(180, int(days)))
    except (TypeError, ValueError):
        days = 30
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        threshold = 0.5
    # 兼容两种写法：0.5 与 50 都表示"置信度低于 50%"
    threshold_pct = threshold * 100 if threshold <= 1 else threshold
    threshold_pct = max(1.0, min(100.0, threshold_pct))
    try:
        top = max(1, min(10, int(top)))
    except (TypeError, ValueError):
        top = 5

    since = timezone.now() - timedelta(days=days)
    detections = DetectionHistory.objects.filter(timestamp__gte=since)
    total = detections.count()

    low = 0
    for value in detections.values_list('confidence', flat=True):
        # 置信度在库里有两套量纲（0–1 与 0–100），与 `_runtime_model_stats` 同一处理方式
        pct = float(value or 0)
        if pct <= 1:
            pct *= 100
        if pct < threshold_pct:
            low += 1

    inaccurate = Feedback.objects.filter(
        category='recognition', is_correct=False, timestamp__gte=since)
    inaccurate_total = inaccurate.count()
    linked = inaccurate.filter(detection__isnull=False).count()

    by_disease = [
        {'disease': redact.text(row['disease_name'] or '（未填）')[:60], 'count': row['n']}
        for row in inaccurate.values('disease_name')
        .annotate(n=Count('id')).order_by('-n')[:top]
    ]
    corrected_pairs = [
        {
            'disease': redact.text(row['disease_name'] or '（未填）')[:60],
            'corrected_to': redact.text(row['corrected_pest__name'] or '')[:60],
            'count': row['n'],
        }
        for row in inaccurate.filter(corrected_pest__isnull=False)
        .values('disease_name', 'corrected_pest__name')
        .annotate(n=Count('id')).order_by('-n')[:top]
    ]

    data = {
        'window': {'days': days, 'since': since.date().isoformat()},
        'threshold_pct': round(threshold_pct, 1),
        'detections': {
            'total': total,
            'low_confidence': low,
            'low_confidence_rate': round(low / total, 4) if total else None,
        },
        'feedback': {
            'inaccurate': inaccurate_total,
            'linked_to_detection': linked,
            'linked_rate': round(linked / inaccurate_total, 4) if inaccurate_total else None,
        },
        'top_misdetected': by_disease,
        'corrected_pairs': corrected_pairs,
        'source': 'DetectionHistory + Feedback(category=recognition, is_correct=False)',
        'comparable': (f'低置信度阈值 {round(threshold_pct, 1)}%；'
                       '识别总数与 /admin/health 的「模型使用数据」同源，但时间窗按问题而定'),
    }
    evidence = [{
        'title': f'近 {days} 天识别与纠错',
        'source': 'AdminHealthView._runtime_model_stats() + Feedback',
        'lines': [f'识别 {total} 次，其中置信度低于 {round(threshold_pct, 1)}% 的 {low} 次',
                  f'用户点"不准确" {inaccurate_total} 条，'
                  f'其中 {linked} 条已关联到具体识别记录'],
    }]
    return ToolResult(ok=True, data=data, evidence=evidence)


# ══════════════════════════════════════════════════════════════════════
# 6. 运维文档检索
# ══════════════════════════════════════════════════════════════════════

def _doc_files() -> list[Path]:
    if not DOCS_ROOT.exists():
        return []
    files = []
    for path in DOCS_ROOT.rglob('*.md'):
        if any(part in DOCS_SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
        if len(files) >= DOCS_MAX_FILES:
            break
    return files


def _query_grams(query: str) -> list[str]:
    """把问题切成检索单元：英文/数字按词，中文按 2-gram。

    为什么中文要 2-gram：`docs/` 里的标题是"备份与恢复""部署与运维"，
    用户问的是"备份为什么过期了" —— 整串匹配永远不命中，单字匹配噪音又太大。
    """
    text = re.sub(r'[^\w\u4e00-\u9fff]+', ' ', (query or '').lower())
    grams: list[str] = []
    for token in text.split():
        if re.fullmatch(r'[a-z0-9_.\-]{2,}', token):
            grams.append(token)
            continue
        if re.fullmatch(r'[\u4e00-\u9fff]+', token):
            if len(token) == 1:
                continue
            grams.extend(token[i:i + 2] for i in range(len(token) - 1))
    # 去重保序，并限制条数（长问题不该把匹配变成 O(n·m)）
    seen, result = set(), []
    for gram in grams:
        if gram not in seen:
            seen.add(gram)
            result.append(gram)
        if len(result) >= 40:
            break
    return result


def _heading_before(text: str, pos: int) -> str:
    best = ''
    for line in text[:pos].splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            best = stripped.lstrip('#').strip()
    return best


def _snippet(text: str, pos: int, width: int = 90) -> str:
    start = max(0, pos - width // 2)
    return ' '.join(text[start:start + width].split())


@_tool
def search_ops_docs(query: str, top_k: int = 5) -> ToolResult:
    """在 `docs/` 里检索运维知识（关键词 + 标题加权；v1 不建向量库）。

    中文没有空格，所以按 2-gram 切；每个检索单元最多计 5 次命中 ——
    `系统完善记录.md` 有 1.4 MB，不封顶它永远排第一。
    """
    grams = _query_grams(query)
    if not grams:
        return ToolResult(ok=True, data={'query': query, 'hits': [], 'reason': '问题里没有可检索的词'})
    try:
        top_k = max(1, min(10, int(top_k)))
    except (TypeError, ValueError):
        top_k = 5

    scored = []
    for path in _doc_files():
        try:
            content = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        lowered = content.lower()
        head = lowered[:400]          # 标题区，命中权重更高
        score = 0.0
        first_pos = -1
        for gram in grams:
            # 每个检索单元最多计 5 次命中：`系统完善记录.md` 有 1.4 MB，
            # 不封顶的话它靠"出现次数多"永远排第一，把真正对口的那一篇挤掉。
            hits = min(lowered.count(gram), 5)
            if not hits:
                continue
            score += hits
            if gram in head:
                score += 3
            pos = lowered.find(gram)
            if first_pos < 0 or pos < first_pos:
                first_pos = pos
        if score > 0 and first_pos >= 0:
            scored.append((score, path, content, first_pos))

    scored.sort(key=lambda item: -item[0])
    hits = []
    for score, path, content, pos in scored[:top_k]:
        hits.append({
            'path': path.relative_to(DOCS_ROOT.parent).as_posix(),
            'title': _heading_before(content, pos) or path.stem,
            'line': content.count('\n', 0, pos) + 1,
            'snippet': redact.text(_snippet(content, pos), limit=200),
            'score': round(score, 1),
        })

    data = {'query': query, 'hits': hits, 'source': 'docs/**/*.md（关键词 + 标题加权，未建向量库）'}
    evidence = [{
        'title': hit['title'],
        'source': f'{hit["path"]}:{hit["line"]}',
        'lines': [hit['snippet']],
    } for hit in hits]
    return ToolResult(ok=True, data=data, evidence=evidence)


# ══════════════════════════════════════════════════════════════════════
# 7. 白名单诊断命令
# ══════════════════════════════════════════════════════════════════════

@_tool
def run_check(name: str) -> ToolResult:
    """执行**白名单内**的只读诊断命令；白名单外的名字直接拒绝，**不执行**。

    不抛异常：让编排层把"被拒绝"也写进答案 —— 这本身就是有用的信息。
    """
    if name not in READONLY_COMMANDS:
        # 不抛异常：让编排层看到"被拒绝"并把它写进答案（这本身就是有用的信息）
        return ToolResult(ok=False, error=f'命令 {name} 不在只读白名单内，已拒绝执行')

    buffer = StringIO()
    kwargs: dict = {'stdout': buffer}
    if name == 'check_env':
        kwargs['as_json'] = True
    try:
        call_command(name, **kwargs)
    except SystemExit:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.exception('只读命令执行失败 name=%s', name)
        return ToolResult(ok=False, error=redact.text(str(exc) or type(exc).__name__))

    raw = buffer.getvalue() or ''
    payload = None
    if raw.lstrip().startswith('{'):
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None

    lines = [redact.text(line) for line in raw.strip().splitlines() if line.strip()][:40]
    data = {
        'command': name,
        'about': READONLY_COMMANDS[name],
        'json': redact.payload(payload) if payload else None,
        'lines': lines,
    }
    evidence = [{
        'title': f'manage.py {name}',
        'source': f'python manage.py {name}',
        'lines': lines[:6],
    }]
    return ToolResult(ok=True, data=data, evidence=evidence)


# ══════════════════════════════════════════════════════════════════════
# 工具注册表
# ══════════════════════════════════════════════════════════════════════

#: 编排层按名字取；顺序即默认展示顺序（也是"能问什么"的清单）
TOOLS = {
    'get_system_health': get_system_health,
    'get_health_trend': get_health_trend,
    'get_audit_summary': get_audit_summary,
    'get_ops_stats': get_ops_stats,
    'get_feedback_samples': get_feedback_samples,
    'get_detection_errors': get_detection_errors,
    'search_ops_docs': search_ops_docs,
    'run_check': run_check,
}
