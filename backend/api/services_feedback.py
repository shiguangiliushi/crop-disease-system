"""反馈的管理端写操作 —— HTTP 接口与系统助手**共用同一份实现**（第 423 批）。

## 为什么必须抽出来

第 423 批给系统助手加了三个可逆写工具（确认样本 / 流转状态 / 回复反馈），
它们的业务语义与 `views.py` 里 `feedback` 视图集的两个动作**完全重合**：

| 动作 | 原来的唯一实现 | 副作用 |
|---|---|---|
| 回复 / 流转状态 | `views.py` `reply()` 内联 ~40 行 | 写 `handled_at`、**自动翻译**、**给提交人发站内通知** |
| 确认 / 排除样本 | `views.py` `verify_sample()` 内联 | 校验 `is_trainable` |

如果助手那边照着写一遍，最迟下一次有人改"回复是否通知用户"时两边就会分叉。
这个仓库已经在"计数口径""双删除"上栽过两次同类问题（见 `系统完善记录.md` 第 16/17 批），
所以这里把**业务规则**收进来，两个调用方只剩"怎么接收参数、怎么回响应"的差异。

## 边界：这里只写业务，不写审计、不做权限

- **不写审计**：HTTP 接口从来不为回复反馈写操作日志，助手侧是**自己**记一条
  （`ops/actions.py`）—— 因为那一条的语义是"AI 替你动了系统"，与人工点击不是一回事；
- **不判权限**：`IsFeedbackEditor` / `is_full_admin` 由各自的入口判，这里假定调用方已经判过。

这两条都是刻意的：把权限和审计塞进服务层，会让"这个函数会不会越权"变成
每次调用都要重新推一遍的问题。
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from .models import Feedback

logger = logging.getLogger(__name__)

#: 回复正文的长度上限。系统助手会把回复拼进上下文与答案，超长会吃掉生成预算；
#: HTTP 接口原本没有上限（前端 textarea 自己限），这里给一个足够宽的天花板，
#: 只拦"把整篇文章粘进来"这种情况。
MAX_REPLY_CHARS = 1000


class FeedbackWriteError(ValueError):
    """写操作被拒绝（参数越界 / 目标不是可训练样本）。

    `field` 是**接口响应里该挂在哪个字段名下**：Django REST 的校验错误习惯是
    `{'字段': ['说明']}`，而"这条不是样本"是对象级错误（`detail`）。
    保留这个区别，是因为管理端前端按字段名把错误显示在对应输入框下方。
    """

    def __init__(self, message: str, field: str = 'detail'):
        super().__init__(message)
        self.field = field


def _status_values() -> set[str]:
    return {choice[0] for choice in Feedback.STATUS_CHOICES}


def _verify_values() -> set[str]:
    return {choice[0] for choice in Feedback.VERIFY_CHOICES}


def apply_reply(feedback: Feedback, *, status=None, admin_reply=None,
                actor=None, manual_reply_en='') -> Feedback:
    """管理员回复 / 流转处理状态（唯一实现）。

    :param status: `Feedback.STATUS_CHOICES` 之一；`None`/空表示"这次不改状态"
    :param admin_reply: `None` 表示**这次不动回复正文**（与"清空回复"是两件事）
    :param actor: 操作人（写日志、发通知用）
    :param manual_reply_en: 管理员手填的英文回复；给了就跳过自动翻译
    :raises FeedbackWriteError: 状态取值非法（**在写库之前**就拒绝）
    """
    value = (status or '').strip()
    if value and value not in _status_values():
        raise FeedbackWriteError('无效的处理状态', field='status')

    if value:
        feedback.status = value
    if admin_reply is not None:
        feedback.admin_reply = admin_reply

    # 只有"已处理"才记录处理时间；从已处理退回其它状态则清空
    # （否则"处理中"的记录会带着一个已处理的完成时间）
    if feedback.status == 'resolved':
        feedback.handled_at = feedback.handled_at or timezone.now()
    else:
        feedback.handled_at = None

    feedback.save(update_fields=['status', 'admin_reply', 'handled_at'])

    # 第 85 批：管理员回复是给用户看的中文，英文界面下需要英文版本。
    # 回复内容变了就重译一次（失败只记日志，不影响回复本身）；
    # 管理员若直接给了 admin_reply_en，则视为人工译文，跳过自动翻译。
    manual_en = (manual_reply_en or '').strip()
    if manual_en:
        feedback.admin_reply_en = manual_en
        feedback.mark_translated(feedback.SOURCE_MANUAL)
        feedback.save(update_fields=['admin_reply_en', 'translation_hash',
                                     'translation_source', 'translated_at'])
    elif getattr(settings, 'TRANSLATE_ON_WRITE', True):
        try:
            from .services_translate import safe_translate_instance
            safe_translate_instance(feedback)
        except Exception:  # noqa: BLE001 —— 翻译失败不能影响管理员处理反馈
            logger.exception('反馈回复翻译调度失败 feedback=%s', feedback.id)

    logger.info('管理员 %s 处理了反馈 id=%s -> %s',
                getattr(actor, 'username', '') or '系统', feedback.id, feedback.status)
    notify_replied(feedback, actor)
    return feedback


def apply_sample_verify(feedback: Feedback, verify_status) -> Feedback:
    """确认 / 排除一条识别纠错样本（唯一实现）。

    :raises FeedbackWriteError: 取值非法，或目标不是可训练样本
    """
    value = (verify_status or '').strip()
    if value not in _verify_values():
        raise FeedbackWriteError(f'只能取 {sorted(_verify_values())} 之一',
                                 field='verify_status')
    #: 只有"识别纠错 + 用户说错了 + 给了正确类别"才算训练样本（模型属性已定义好口径）。
    #: 对无关反馈点"确认"没有意义，而且会让统计里的"样本数"虚高。
    if not feedback.is_trainable:
        raise FeedbackWriteError(
            '这条反馈不是可训练样本（需要：类型为识别纠错、用户判定识别有误、'
            '并给出了正确病害）',
        )
    feedback.verify_status = value
    feedback.save(update_fields=['verify_status'])
    return feedback


def notify_replied(feedback: Feedback, actor) -> None:
    """标记「已处理」或写了回复时，给提交人发一条站内通知（失败只记日志）。

    ⚠️ 第 224 批：改前一次性回复完，用户那边**什么都收不到** —— 站内信体系里
    论坛回复、专家咨询、点赞都接了 `notify()`，唯独反馈的 reply 没接，
    用户必须自己再进一次"反馈中心"才看得到回复。
    系统助手的写工具**必须**走这里，否则"AI 替你回复"会变成"用户永远不知道"。
    """
    if feedback.user_id is None:
        return
    if feedback.status != 'resolved' and not (feedback.admin_reply or '').strip():
        return
    try:
        from .views_notify import notify

        snippet = (feedback.admin_reply or '').strip()
        if len(snippet) > 60:
            snippet = snippet[:60] + '…'
        who = getattr(actor, 'username', '') or '管理员'
        notify(
            feedback.user,
            type='feedback',
            title='你的反馈已有回复',
            message=(f'{who} 回复了你的反馈：{snippet}' if snippet
                     else f'{who} 已处理你的反馈'),
            title_en='Your feedback has a reply',
            message_en=(f'{who} replied to your feedback' if not snippet
                        else f'{who} replied to your feedback: {snippet}'),
            url='/feedback',
            actor=actor,
        )
    except Exception:  # noqa: BLE001 —— 通知失败绝不能影响管理员处理反馈
        logger.exception('反馈回复通知投递失败 feedback=%s', feedback.id)
