"""助手侧的业务服务（第 196 批）。

## 为什么单独一个模块，而不是写在视图里

"转人工"要同时做四件事：**建咨询工单 → 回填会话关联 → 置转人工时间 → 通知在岗专家**。
它需要事务、需要复用既有专家通知逻辑，还要能被后台命令/测试直接调用。
放在视图里会变成"只有 HTTP 请求才能触发" —— 而这是业务动作，不是 HTTP 动作。
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from ..models_assistant import AssistantMessage, AssistantSession
from ..models_expert import ConsultQuestion

logger = logging.getLogger(__name__)

#: 工单标题上限（与 `ConsultQuestion.title` 的 max_length 一致）
TITLE_MAX = 200
#: 工单正文里"AI 回答"最多抄多少字。太长专家也要读很久，而重点是用户的问题。
ANSWER_EXCERPT = 800


def _title_from(question: str) -> str:
    """把用户问题压成工单标题。

    优先在**标点处**截断，而不是硬切 —— 硬切会把"这个病打什么药？稀释倍数"切成
    "这个病打什么药？稀释倍"这种看着像乱码的标题。找不到合适标点才硬切并加省略号。
    """
    text = (question or '').strip().replace('\n', ' ')
    if len(text) <= TITLE_MAX:
        return text or '来自助手的提问'

    head = text[:TITLE_MAX]
    for mark in ('？', '?', '。', '！', '!', '；', ';', '，', ','):
        index = head.rfind(mark)
        # 只在"截得够长"时才用标点位置，否则标题会短得没信息量
        if index >= TITLE_MAX // 2:
            return head[:index + 1]
    return text[:TITLE_MAX - 1] + '…'


def _build_content(session: AssistantSession, last_question: str) -> str:
    """工单正文：用户问的 + AI 答的（含降级标注）。

    ⚠️ 一定要把"AI 当时答了什么"也带上：专家如果只看到问题，
    可能会给出用户已经试过的建议；看到 AI 的原答才能**补充**而不是**重复**。
    降级状态也如实写 —— 否则专家会以为"AI 给过建议了"，而实际上用户只拿到词条原文。
    """
    lines = [f'【用户问题】\n{last_question or "（未记录）"}']

    assistant_messages = list(
        AssistantMessage.objects.filter(session=session, role='assistant')
        .exclude(content='').order_by('-id')[:1]
    )
    if assistant_messages:
        last = assistant_messages[0]
        state = f'（降级：{last.degrade_reason}）' if last.degraded else ''
        answer = last.content[:ANSWER_EXCERPT]
        if len(last.content) > ANSWER_EXCERPT:
            answer += '…'
        lines.append(f'【AI 当时给的回答{state}】\n{answer}')
    else:
        lines.append('【AI 当时给的回答】\n（助手没有产出回答）')

    lines.append(
        '【说明】这是用户从「智能回答助手」转来的人工咨询。'
        '助手未能让用户满意，请结合上述信息补充解答（避免重复 AI 已经给过的内容）。'
    )
    return '\n\n'.join(lines)


def escalate(*, session: AssistantSession, user, note: str = '') -> tuple[ConsultQuestion, bool]:
    """把一次助手会话转成人工咨询工单。

    返回 `(工单, 是否新建)` —— **幂等**：同一会话重复调用只会返回同一张工单，
    不会建第二张。这一点很重要：用户在"没用"按钮旁边多点了两下，
    专家不该看到三条一模一样的提问。

    用 `OneToOneField` + 先查后建来保证幂等，而不是靠 `get_or_create`
    ——因为 `get_or_create` 的 default 里要现算标题与正文，写起来反而绕。
    """
    if session.consult_question_id:
        return session.consult_question, False

    last_question = (
        AssistantMessage.objects.filter(session=session, role='user')
        .order_by('-id').values_list('content', flat=True).first()
        or session.title
        or ''
    )

    source = note.strip()
    content = _build_content(session, last_question)
    if source:
        content += f'\n\n【用户补充】\n{source[:500]}'

    with transaction.atomic():
        question = ConsultQuestion.objects.create(
            asker=user,
            # 作物取会话绑定的病害（从识别结果页进来时一定有）
            crop_type=(session.pest.crop_type if session.pest_id else ''),
            title=_title_from(last_question),
            content=content,
        )
        session.consult_question = question
        session.escalated_at = timezone.now()
        session.save(update_fields=['consult_question', 'escalated_at', 'updated_at'])

    logger.info('助手转人工：session=%s -> consult_question=%s', session.pk, question.pk)

    # 通知放在事务外：通知失败不该回滚工单（工单本身已经建好了）
    try:
        from ..views_expert import notify_experts
        notify_experts(question)
    except Exception:  # noqa: BLE001
        logger.exception('转人工后通知专家失败 question=%s', question.pk)

    return question, True
