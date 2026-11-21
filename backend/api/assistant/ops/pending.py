"""待确认写操作的**状态机**（第 425 批）—— A3 的安全边界就落在这里。

## 这个模块只做四件事

| 函数 | 语义 | 谁调用 |
|---|---|---|
| `propose()` | 记下"想做什么"，**不动数据** | agent 的 `guard` 节点走完之后 |
| `consume()` | 原子认领一行（只能成功一次） | 确认请求与取消请求 |
| `confirm()` | 认领 + **重新校验** + 执行 | 确认接口 |
| `cancel()` | 认领 + 标记取消 | 取消接口 |

## 三条不能妥协的地方

1. **认领靠 `UPDATE ... WHERE status='pending'` 的返回值。**
   写 `if row.status == 'pending': row.save()` 的话，双击/两个页签/重放请求会各执行一次 ——
   而不可逆操作执行两次就是"删了两次"，没有第二次机会。

2. **执行前重新走 `actions.validate()`。**
   提议与确认之间可能隔了几分钟：目标可能已被删除，管理员可能已被降权，
   参数也可能因为模型当初就理解错了而不合法。这三件事都只有重校验能拦住。

3. **确认的判定是纯函数，不是模型。**
   若让模型判断"这句话算不算确认"，模型就能确认自己刚才的提议（提示注入的经典入口）。
   见 `docs/系统助手不可逆写状态机方案.md` 第五节。
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ...models_assistant_ops import OpsPendingWrite
from . import actions
from .tools import ToolResult

logger = logging.getLogger(__name__)

#: 待确认的有效期。十分钟：够管理员读完复述再决定，又不至于让一个"昨天的意图"复活。
TTL_SECONDS = 600

#: 一个管理员最多同时挂几条待确认。防"连点提议把库刷满"，也逼着一次只做一件危险事。
MAX_OPEN = 3

#: `consume()` 的失败原因 → 人读说明。**不区分"不存在"与"不是你的"** ——
#: 区分了就等于给攻击者一个探测 token 是否存在的接口。
REASON_TEXT = {
    'not_found': '这个待确认操作不存在，或者不属于你。',
    'expired': '这条确认已经过期（有效期 10 分钟），请重新说一次要做什么。',
    'consumed': '这条操作已经处理过了，不会重复执行。',
    'empty': '缺少确认凭据。',
    'too_many': f'待确认操作太多了（上限 {MAX_OPEN} 条），请先处理或等它们过期。',
}

#: "这句话算不算确认"。只接确认词表 —— **不接模型生成的自然语言**。
CONFIRM_WORDS = frozenset({
    'confirm', 'confirmed', 'yes', 'y', 'ok',
    '确认', '确定', '已确认', '执行', '确认执行',
})


def is_confirm(value) -> bool:
    """这件事该不该执行。`True` 与确认词表之外的一切都算"没有确认"。"""
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in CONFIRM_WORDS
    return False


def mark_expired(now=None) -> int:
    """把已过期的行标出来。**惰性调用**（确认/统计时顺手跑），不依赖定时任务。"""
    now = now or timezone.now()
    return (OpsPendingWrite.objects
            .filter(status='pending', expires_at__lte=now)
            .update(status='expired'))


def propose(*, user, validated, question: str) -> tuple['OpsPendingWrite | None', str]:
    """记下一条待确认操作，返回 `(行, 错误说明)`。**不执行任何写**。

    `validated` 必须是 `actions.validate()` 的返回值 —— 本函数不接受裸参数，
    否则"先校验后执行"这条约定就在入口处破了。
    """
    if validated is None or not getattr(validated, 'name', ''):
        # 入口处兜一下：没有 `Validated` 就等于"没校验过"，而没校验过的参数
        # 不许进待确认表 —— 否则确认时会拿着未校验的裸参数去执行。
        return None, '需要一个已通过校验的写请求（Validated）'
    if user is None:
        return None, '需要登录的管理员才能提议写操作'

    now = timezone.now()
    open_count = (OpsPendingWrite.objects
                  .filter(user=user, status='pending', expires_at__gt=now).count())
    if open_count >= MAX_OPEN:
        return None, REASON_TEXT['too_many']

    row = OpsPendingWrite.objects.create(
        token=uuid.uuid4().hex,
        action=validated.name,
        args=dict(validated.args or {}),
        target=(validated.target or '')[:200],
        changes=list(validated.changes or []),
        user=user,
        question=question or '',
        expires_at=now + timedelta(seconds=TTL_SECONDS),
    )
    return row, ''


def consume(token: str, *, user, now=None) -> tuple['OpsPendingWrite | None', str]:
    """原子认领。返回 `(行, 失败原因)`；行非空表示**这次请求抢到了**。

    两种人能拿到同一个 token 的概率视为零，所以 token 绑定 `user` 是复核而不是主键 ——
    但**必须绑**：否则 A 管理员拿到 B 的 token 就能替 B 确认。
    """
    now = now or timezone.now()
    token = str(token or '').strip()
    if not token:
        return None, 'empty'

    row = (OpsPendingWrite.objects.filter(token=token, user=user).first())
    if row is None:
        return None, 'not_found'

    if row.status == 'pending' and row.expires_at <= now:
        # 顺手落一下状态，别让"过期"只体现在内存判断里
        OpsPendingWrite.objects.filter(pk=row.pk, status='pending').update(status='expired')
        return None, 'expired'

    claimed = (OpsPendingWrite.objects
               .filter(pk=row.pk, status='pending', expires_at__gt=now)
               .update(status='confirmed', consumed_at=now))
    if not claimed:
        return None, 'consumed'

    row.refresh_from_db()
    return row, ''


def cancel(token: str, *, user) -> tuple[bool, str]:
    """取消一条待确认。返回 `(是否真的取消了, 说明)`。

    取消**不执行**任何东西，所以这里的"认领"允许先查后改 —— 没有副作用，
    并发下最坏情况是两个人同时取消、其中一人看到"已处理过"，无害。
    """
    now = timezone.now()
    token = str(token or '').strip()
    if not token:
        return False, REASON_TEXT['empty']

    updated = (OpsPendingWrite.objects
               .filter(token=token, user=user, status='pending')
               .update(status='cancelled', consumed_at=now))
    if updated:
        return True, '已取消，本次没有执行任何操作。'

    # 没取消成功：把原因说清楚（过期了要提示重新提议，而不是含糊的"失败"）
    row = OpsPendingWrite.objects.filter(token=token, user=user).first()
    if row is None:
        return False, REASON_TEXT['not_found']
    if row.status == 'expired':
        return False, REASON_TEXT['expired']
    return False, REASON_TEXT['consumed']


def confirm(token: str, *, user) -> tuple[ToolResult, str, 'OpsPendingWrite | None']:
    """确认并执行。返回 `(工具结果, 失败原因, 行)`。

    顺序刻意写成"认领 → 重校验 → 执行 → 记终态"：

    · 认领在前：抢不到就什么都不做，绝不"先执行再标记已消费"；
    · 重校验：挡住"提议时的目标已经不在了 / 管理员已被降权 / 参数本来就不对"；
    · 执行失败要落 `failed`：不可逆操作**不自动重试**（重试等于二次删除）。
    """
    row, reason = consume(token, user=user)
    if row is None:
        return ToolResult(name='', ok=False, error=REASON_TEXT.get(reason, '无法确认')), reason, None

    validated, error = actions.validate(row.action, row.args, question=row.question)
    if validated is None:
        _finish(row, 'failed')
        logger.warning('待确认操作在确认时不再合法：%s / %s', row.action, error)
        return ToolResult(name=row.action, ok=False, error=error), 'invalid', row

    try:
        with transaction.atomic():
            # `confirmed=True` 是**唯一**的放行方式：它证明这条不可逆操作
            # 已经过"认领 token → 重新校验"。别处（尤其老的关键词路径）调
            # `execute()` 时拿不到这个参数，所以结构上绕不过二次确认。
            result = actions.execute(validated, user=user, confirmed=True)
    except Exception as exc:  # noqa: BLE001 —— 执行失败必须落终态，不能留一条"已确认"的假记录
        _finish(row, 'failed')
        logger.exception('确认后执行失败 action=%s pk=%s', row.action, row.pk)
        return ToolResult(name=row.action, ok=False, error=str(exc)), 'exec_failed', row

    _finish(row, 'confirmed' if result.ok else 'failed')
    return result, '', row


def _finish(row, status: str) -> None:
    """落终态。`consume()` 已经把它标成 `confirmed`，这里只改"执行成不成"。"""
    OpsPendingWrite.objects.filter(pk=row.pk).update(status=status)


def open_rows(*, user=None):
    """当前还开着的待确认（给统计/管理界面用，已过期的不返回）"""
    mark_expired()
    query = OpsPendingWrite.objects.filter(status='pending')
    if user is not None:
        query = query.filter(user=user)
    return query
