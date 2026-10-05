"""
病害预警（第 46 批）

背景：清单里"病害预警"此前完全没有。

**先说清楚数据来源**：本系统没有接天气/植保站的第三方数据，
所以预警**只基于站内真实数据**推导，不假装有气象信息：
    ① trend（趋势）—— 近 N 天的检出量 vs 之前 4 周的周均量，明显抬升说明正在流行；
    ② community（多点）—— 同一病害被**多个不同用户**检出，说明不是一个人的偶然；
    ③ seasonal（同月历史）—— 去年同月的检出量也偏高，说明这是该病害的常发期。

输出按严重程度分级（high / medium / low），并带上百科里的防治方法作为行动建议。
对登录用户还会标注 `is_personal`：他自己或他种过的作物命中过这个病害时，
预警会给出更直接的提醒（"你 12 天前识别出过番茄早疫病，近期该病检出上升"）。

对外接口见 `views_alert.py`；首页与 `/alerts` 页展示。
"""
import logging
from datetime import timedelta

from django.db.models import Count, Max, Q
from django.utils import timezone

from .models import DetectionHistory, PestInfo
from .services_content_i18n import pest_en_maps  # 第 77 批：诊断信息的中英对照

logger = logging.getLogger(__name__)

#: 达到这些条件才值得提醒（避免"1 条记录就报警"的狼来了）
DEFAULT_DAYS = 7
DEFAULT_BASELINE_DAYS = 28
DEFAULT_MIN_CASES = 2


def _alert_level(recent, weekly_avg, distinct_users, signals, min_cases=DEFAULT_MIN_CASES):
    """
    分级规则（顺序即优先级）

    注意：门槛要用**调用方传进来的 min_cases**，不能写死模块默认值 ——
    否则接口允许 `?min_cases=1`，分级那一步却仍然要求 2 次，参数等于失效。
    """
    ratio = recent / weekly_avg if weekly_avg > 0 else None
    rising = ratio is None or ratio >= 2  # 基线为 0 时视为显著上升

    if recent >= max(3, min_cases) and rising and distinct_users >= 2:
        return 'high'
    if recent >= min_cases and (rising or distinct_users >= 2):
        return 'medium'
    if recent >= 1 and ('seasonal' in signals or distinct_users >= 2):
        return 'low'
    return None


def compute_alerts(days=DEFAULT_DAYS, baseline_days=DEFAULT_BASELINE_DAYS,
                   min_cases=DEFAULT_MIN_CASES, user=None, limit=20):
    """
    计算当前预警列表（按严重程度、检出量排序）

    :param days: 观察窗口（默认近 7 天）
    :param baseline_days: 基线窗口（默认之前 4 周）
    :param min_cases: 窗口内最少检出数，低于它不提醒
    :param user: 传入登录用户时会标注 `is_personal` / `my_count` / `my_last_at`
    """
    now = timezone.now()
    recent_start = now - timedelta(days=days)
    baseline_start = recent_start - timedelta(days=baseline_days)

    # ---------- 窗口内：按病害统计 ----------
    recent_rows = (
        DetectionHistory.objects
        .filter(timestamp__gte=recent_start, pest_info__isnull=False)
        .values('pest_info_id')
        .annotate(
            count=Count('id'),
            users=Count('user', distinct=True),
            latest=Max('timestamp'),
        )
    )
    recent_map = {row['pest_info_id']: row for row in recent_rows}
    if not recent_map:
        return []

    # ---------- 基线窗口：周均量 ----------
    baseline_rows = (
        DetectionHistory.objects
        .filter(timestamp__gte=baseline_start, timestamp__lt=recent_start, pest_info__isnull=False)
        .values('pest_info_id')
        .annotate(count=Count('id'))
    )
    baseline_map = {row['pest_info_id']: row['count'] for row in baseline_rows}
    baseline_weeks = max(1.0, baseline_days / 7.0)

    # ---------- 去年同月：季节性 ----------
    seasonal_map = set(
        DetectionHistory.objects
        .filter(
            timestamp__month=now.month,
            timestamp__year=now.year - 1,
            pest_info__isnull=False,
        )
        .values_list('pest_info_id', flat=True)
    )

    # ---------- 我与这些病害的关系 ----------
    my_counts = {}
    my_last = {}
    my_crops = set()
    if user is not None and getattr(user, 'is_authenticated', False):
        for row in (
            DetectionHistory.objects
            .filter(user=user, pest_info__isnull=False)
            .values('pest_info_id')
            .annotate(count=Count('id'), latest=Max('timestamp'))
        ):
            my_counts[row['pest_info_id']] = row['count']
            my_last[row['pest_info_id']] = row['latest']
        my_crops = set(
            DetectionHistory.objects
            .filter(user=user, pest_info__isnull=False)
            .values_list('pest_info__crop_type', flat=True)
        )

    pest_ids = list(recent_map.keys())
    pests = {pest.id: pest for pest in PestInfo.objects.filter(id__in=pest_ids)}
    # 一次查完防治方法，避免 N+1
    methods = {}
    from .models import PreventionMethod
    for method in PreventionMethod.objects.filter(pest_id__in=pest_ids).order_by('category'):
        methods.setdefault(method.pest_id, []).append({
            'category': method.category,
            'category_display': method.get_category_display(),
            'measure': method.measure,
            'measure_en': method.measure_en,
        })

    alerts = []
    for pest_id, row in recent_map.items():
        pest = pests.get(pest_id)
        if not pest:
            continue

        count = row['count']
        # 注意：这里**没有** `if count < min_cases: continue` 这道闸。
        # `recent_map` 里的病害天然都至少有 1 次，门槛完全交给下面的
        # `_alert_level()` 判断 —— 它还会看趋势与检出人数，
        # 所以"1 次但由 2 位用户检出"是可以成立的（low 级）。
        # （此前这里写的是 `if count < min_cases and count < 1`，
        #   因为 count 恒 ≥1，那个条件永远为假，属于误导性死代码。）

        weekly_avg = baseline_map.get(pest_id, 0) / baseline_weeks
        signals = []
        if weekly_avg == 0 or count / max(weekly_avg, 0.01) >= 1.5:
            signals.append('trend')
        if row['users'] >= 2:
            signals.append('community')
        if pest_id in seasonal_map:
            signals.append('seasonal')

        level = _alert_level(count, weekly_avg, row['users'], signals, min_cases)
        if not level:
            continue

        ratio = round(count / weekly_avg, 1) if weekly_avg > 0 else None
        is_personal = pest_id in my_counts or (pest.crop_type in my_crops)
        alerted = pest_id in my_counts

        # 文案：把"为什么提醒"讲清楚，而不是只丢一个红点
        # 第 72 批：同时生成英文版本（title_en / message_en）——
        # 预警句子是后端拼的，前端文案表管不到，只给中文会导致英文界面整块是中文。
        crop_en = pest.crop_type_en or pest.crop_type
        name_en = pest.name_en or pest.name
        if level == 'high':
            title = f'{pest.crop_type}·{pest.name} 进入高发期'
            title_en = f'{crop_en} · {name_en} is at outbreak level'
        elif level == 'medium':
            title = f'{pest.crop_type}·{pest.name} 检出明显增多'
            title_en = f'{crop_en} · {name_en} detections rising sharply'
        else:
            title = f'{pest.crop_type}·{pest.name} 需留意'
            title_en = f'{crop_en} · {name_en} worth watching'

        reasons = []
        reasons_en = []
        if 'trend' in signals:
            if weekly_avg > 0:
                reasons.append(f'近 {days} 天检出 {count} 次，约为之前 4 周周均（{weekly_avg:.1f} 次）的 {ratio} 倍')
                reasons_en.append(
                    f'{count} cases in the last {days} days — about {ratio}× the previous '
                    f'4-week average of {weekly_avg:.1f} per week'
                )
            else:
                reasons.append(f'之前 4 周没有检出，近 {days} 天突然出现 {count} 次')
                reasons_en.append(
                    f'no cases in the previous 4 weeks, then {count} in the last {days} days'
                )
        if 'community' in signals:
            reasons.append(f'{row["users"]} 位用户先后检出，不是个例')
            reasons_en.append(f'{row["users"]} different users reported it, so it is not an isolated case')
        if 'seasonal' in signals:
            reasons.append('去年同月也有检出，属于该病害的常发期')
            reasons_en.append('it was also detected in the same month last year, so this is a recurring season')

        if alerted:
            my_days = (now - my_last[pest_id]).days
            prefix = f'你 {my_days} 天前识别出过这个病害，' if my_days >= 0 else '你识别出过这个病害，'
            prefix_en = (
                f'You identified this disease {my_days} days ago; '
                if my_days >= 0
                else 'You have identified this disease before; '
            )
        elif is_personal:
            prefix = f'你种过{pest.crop_type}，'
            prefix_en = f'You grow {crop_en}, and '
        else:
            prefix = ''
            prefix_en = ''

        message = prefix + '；'.join(reasons) + '。建议尽快巡田检查。'
        message_en = prefix_en + '; '.join(reasons_en) + '. Check your fields soon.'

        alerts.append({
            'pest': {
                'id': pest.id,
                'name': pest.name,
                'name_en': pest.name_en,
                'crop_type': pest.crop_type,
                'crop_type_en': pest.crop_type_en,
                'english_identifier': pest.english_identifier,
                'symptoms': (pest.symptoms or '')[:120],
                'symptoms_en': (pest.symptoms_en or '')[:120],
            },
            'level': level,
            'recent_count': count,
            'baseline_weekly_avg': round(weekly_avg, 2),
            'ratio': ratio,
            'distinct_users': row['users'],
            'latest_at': row['latest'],
            'signals': signals,
            'title': title,
            'title_en': title_en,
            'message': message,
            'message_en': message_en,
            'advice': methods.get(pest_id, [])[:3],
            'is_personal': is_personal,
            'alerted_before': alerted,
            'my_count': my_counts.get(pest_id, 0),
            'url': f'/pests/{pest.english_identifier}',
        })

    order = {'high': 0, 'medium': 1, 'low': 2}
    alerts.sort(key=lambda item: (order.get(item['level'], 3), -item['recent_count'], item['pest']['name']))
    return alerts[:limit]


def alert_summary(alerts):
    """给前端顶部用的汇总（第 72 批：同时给出英文 headline）"""
    counts = {'high': 0, 'medium': 0, 'low': 0}
    for alert in alerts:
        counts[alert['level']] = counts.get(alert['level'], 0) + 1

    if counts['high']:
        headline = f'有 {counts["high"]} 个病害进入高发期，建议尽快巡田'
        headline_en = f'{counts["high"]} disease(s) at outbreak level — check your fields soon'
    elif counts['medium']:
        headline = f'有 {counts["medium"]} 个病害检出明显增多，注意防范'
        headline_en = f'{counts["medium"]} disease(s) with rising detections — keep watch'
    elif counts['low']:
        headline = f'有 {counts["low"]} 个病害需要留意'
        headline_en = f'{counts["low"]} disease(s) worth watching'
    else:
        headline = '近期没有异常上升的病害，保持日常巡田即可'
        headline_en = 'No unusual increase recently — routine field checks are enough'
    return {'counts': counts, 'total': len(alerts), 'headline': headline, 'headline_en': headline_en}


def alert_diagnostics(days=DEFAULT_DAYS, min_cases=DEFAULT_MIN_CASES):
    """
    "为什么现在没有预警"的量化说明（第 76 批）

    背景（真实困惑）：预警页默认窗口是 7 天，而本系统的阈值是
    **同一病害**在窗口内累计 ≥ `min_cases` 次（或 ≥2 位不同用户检出）才提醒。
    数据少的时候页面只显示一句"近期没有异常上升的病害" —— 用户看到的是空白，
    无从判断"是没数据 / 是坏了 / 还是就差一点"，于是合理地怀疑功能没做。

    这里把判断依据直接算出来给前端，让空状态能说清：
      · 窗口内全站一共多少次识别、涉及几种病害；
      · 门槛是多少；
      · 最接近门槛的是哪个病害、还差几次。

    ⚠️ 只在"没有预警"时由接口调用（有预警时前端不显示这段话），避免白跑查询。
    """
    now = timezone.now()
    recent_start = now - timedelta(days=days)

    rows = list(
        DetectionHistory.objects
        .filter(timestamp__gte=recent_start, pest_info__isnull=False)
        .values('pest_info_id', 'pest_info__name', 'pest_info__crop_type')
        .annotate(count=Count('id'), users=Count('user', distinct=True))
        .order_by('-count', 'pest_info__name')
    )

    closest = None
    if rows:
        top = rows[0]
        # 第 77 批：诊断信息里的病害名/作物名也要能在英文界面显示英文
        pest_name_en_map, crop_name_en_map = pest_en_maps()
        closest = {
            'pest_id': top['pest_info_id'],
            'name': top['pest_info__name'],
            'name_en': pest_name_en_map.get(top['pest_info__name'], ''),
            'crop_type': top['pest_info__crop_type'],
            'crop_type_en': crop_name_en_map.get(top['pest_info__crop_type'], ''),
            'count': top['count'],
            'users': top['users'],
            # 还差几次才够"同病害累计 min_cases 次"这条最基本的门槛
            'needed': max(0, min_cases - top['count']),
        }

    return {
        'window_days': days,
        'threshold': min_cases,
        'recent_detections': sum(row['count'] for row in rows),
        'diseases_in_window': len(rows),
        'closest': closest,
    }
