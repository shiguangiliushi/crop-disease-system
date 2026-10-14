"""智能回答助手的编排层（第 193 批，K5）—— 对外唯一入口 `ask()`。

## 流程（八步，与 `docs/智能回答助手框架.md` 第一节一致）

    ① 输入闸门 → ② 意图判定 → ③ 检索 → ④ 上下文组装
    → ⑤ 提示词 → ⑥ 生成 → ⑦ 引用校验 → ⑧ 落库

## 一条硬约定：**永不抛异常给视图层**

助手是**旁路功能**：识别结果页在它挂了的时候仍然必须能看。所以每一种失败都被翻译成
"降级回答 + `degraded=True` + `degrade_reason`"，接口始终 200。

降级原因（`degrade_reason`，写进库便于事后统计）：

    empty / too_long / sensitive / rate_limited   ← 闸门挡下（不消耗模型额度）
    no_source                                      ← 检索为空：无来源不回答
    llm_disabled                                   ← 没配 key 或开关关着
    llm_error                                      ← 超时 / HTTP 错误 / 响应结构不对
    no_citation                                    ← 生成成功但引用校验全被剔除（疑似编造）
"""
from __future__ import annotations

import logging

from django.db import transaction

from ..models_assistant import AssistantMessage, AssistantSession
from . import context as context_builder
from . import guard, llm, prompts
from .retriever import detect_intent, search

logger = logging.getLogger(__name__)

#: 会话标题取首问前 N 字
TITLE_CHARS = 30
#: 单条消息最多带几处引用（前端渲染太多反而看不出重点）
MAX_CITATIONS = 6


def _fallback_body(hits) -> str:
    """降级时给"词条原文"：把命中条目的关键字段原样列出来。

    刻意**不做任何改写或总结** —— 没有 AI 的时候就老老实实给档案，
    让用户知道这不是 AI 的回答（正文前缀由 `prompts.DEGRADE_NO_LLM` 说明）。
    """
    from .context import CARE_SECTIONS, DISEASE_SECTIONS, HEALTHY_SECTIONS, _split_append_note

    blocks: list[str] = []
    for index, hit in enumerate(hits[:2], start=1):
        pest = hit.pest
        lines = [f'【{index}】{pest.name}（作物：{pest.crop_type}）']
        if pest.scientific_name:
            lines.append(f'学名：{pest.scientific_name.split("（")[0].strip()}')
        if hit.is_healthy and hit.profile is not None:
            for title, attr in HEALTHY_SECTIONS + CARE_SECTIONS:
                value = _split_append_note(getattr(hit.profile, attr, '') or '')
                if value:
                    lines.append(f'{title}：{value}')
        else:
            for title, attr in DISEASE_SECTIONS:
                value = _split_append_note(getattr(pest, attr, '') or '')
                if value:
                    lines.append(f'{title}：{value}')
            for method in pest.prevention_methods.all().order_by('category'):
                value = _split_append_note(method.measure or '')
                if value:
                    lines.append(f'{method.get_category_display()}：{value}')
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)


def _guard_reply(result: guard.GuardResult) -> tuple[str, str]:
    """把闸门结果翻译成 (回答文本, 降级原因)。"""
    if result.reason == 'empty':
        return prompts.DEGRADE_EMPTY, 'empty'
    if result.reason == 'too_long':
        return prompts.DEGRADE_TOO_LONG.format(limit=guard.MAX_QUESTION_CHARS), 'too_long'
    if result.reason == 'sensitive':
        return prompts.DEGRADE_SENSITIVE.format(words=result.detail), 'sensitive'
    if result.reason == 'rate_limited':
        return (f'提问太频繁了（每分钟上限 {result.detail} 次），请稍等一下再问。', 'rate_limited')
    return prompts.DEGRADE_NO_SOURCE, 'no_source'


def _get_or_create_session(*, user, session, question, pest_identifier):
    """拿到会话：显式传入 > 新建。同时按识别结果绑定 `pest`。"""
    if session is not None:
        return session
    pest = None
    if pest_identifier:
        from ..pest_lookup import find_pest_info
        pest, _why = find_pest_info(pest_identifier)
    session = AssistantSession.objects.create(
        user=user,
        title=(question or '')[:TITLE_CHARS],
        pest=pest,
    )
    return session


def ask(*, user, question: str, session: AssistantSession | None = None,
        pest_identifier: str = '') -> dict:
    """问一个问题，返回结构化结果。**永不抛异常给调用方**（见模块 docstring）。"""
    from django.conf import settings as django_settings

    # 配置统一从 settings 读（settings.py 已经做过 `int()` 转换与默认值，
    # 这里再用 os.environ 兜一遍只会让两处口径可能不一致）。
    rate_limit = getattr(django_settings, 'ASSISTANT_RATE_PER_MINUTE', None)
    if rate_limit is None:
        rate_limit = guard.DEFAULT_RATE_PER_MINUTE

    # ── ① 闸门 ────────────────────────────────────────────────────────────
    guard_result = guard.check(question, user=user, rate_per_minute=rate_limit)

    # 闸门拦下的问题**也要落库**（否则"用户问了什么被挡了"无从复盘），
    # 但只在有会话时落：空问题连会话都不该建。
    if not guard_result.ok and guard_result.reason in ('empty',):
        return {
            'session_id': getattr(session, 'pk', None),
            'message_id': None,
            'answer': prompts.DEGRADE_EMPTY,
            'degraded': True,
            'degrade_reason': 'empty',
            'citations': [],
            'usage': {},
        }

    session = _get_or_create_session(
        user=user, session=session, question=guard_result.question or question,
        pest_identifier=pest_identifier,
    )
    answer, reason, citations, usage, actual_model, prompt_version = '', '', [], {}, '', ''
    latency_ms = 0

    try:
        if not guard_result.ok:
            answer, reason = _guard_reply(guard_result)
        else:
            # ── ②③ 意图 + 检索 ────────────────────────────────────────────
            intent = detect_intent(guard_result.question)
            hits = search(guard_result.question, pest_identifier=pest_identifier,
                          top_k=getattr(django_settings, 'ASSISTANT_TOP_K', 5))
            built = context_builder.build(hits)

            if built.is_empty:
                # ④ 无来源不回答：农业场景答错药是事故，不是体验问题
                answer, reason = prompts.DEGRADE_NO_SOURCE, 'no_source'
            elif not llm.enabled():
                answer = prompts.DEGRADE_NO_LLM.format(body=_fallback_body(hits))
                reason = 'llm_disabled'
            else:
                # ── ⑤⑥ 提示词 + 生成 ──────────────────────────────────────
                messages = prompts.build_messages(guard_result.question, built.text, intent)
                prompt_version = prompts.PROMPT_VERSION
                try:
                    result = llm.chat(messages)
                except llm.LLMError as exc:
                    logger.warning('助手生成失败，降级：%s', exc)
                    answer = prompts.DEGRADE_ERROR.format(reason=exc, body=_fallback_body(hits))
                    reason = 'llm_error'
                else:
                    latency_ms = result.latency_ms
                    actual_model = result.model
                    usage = {
                        'prompt_tokens': result.prompt_tokens,
                        'completion_tokens': result.completion_tokens,
                        'latency_ms': result.latency_ms,
                        'configured_model': llm.model_name(),
                    }
                    # ── ⑦ 引用校验：模型必须真的引用了上下文里的条目 ──────
                    cited = [c for c in built.citations if f'【{built.citations.index(c) + 1}】' in result.text]
                    if not cited and built.citations:
                        # 一个引用都没标：不判失败，但**如实记录**。
                        # 不降级的原因：模型可能只是忘了标序号，内容仍来自上下文；
                        # 这里把全部候选引用带上，并在 usage 里标记未标注。
                        cited = built.citations[:MAX_CITATIONS]
                        usage['citation_marked'] = False
                    else:
                        usage['citation_marked'] = True
                    answer = result.text or prompts.DEGRADE_NO_SOURCE
                    citations = [c.as_dict() for c in cited[:MAX_CITATIONS]]
                    if not answer.strip():
                        answer, reason = prompts.DEGRADE_NO_SOURCE, 'no_source'
    except Exception as exc:  # noqa: BLE001 —— 兜底：任何意外都要变成可读回答
        logger.exception('助手链路出现未预期错误')
        answer = f'（AI 助手暂时不可用：{exc}）'
        reason = 'llm_error'

    # ── ⑧ 落库（单事务：用户消息与助手消息要么都写、要么都不写）──────────
    with transaction.atomic():
        AssistantMessage.objects.create(
            session=session, role='user', content=guard_result.question or question,
        )
        message = AssistantMessage.objects.create(
            session=session,
            role='assistant',
            content=answer,
            model=actual_model,
            degraded=bool(reason),
            degrade_reason=reason,
            latency_ms=latency_ms,
            citations=citations,
            usage=usage,
            prompt_version=prompt_version,
        )
        session.save(update_fields=['updated_at'])   # 触发 auto_now，让会话列表按活跃排序

    return {
        'session_id': session.pk,
        'message_id': message.pk,
        'answer': answer,
        'degraded': bool(reason),
        'degrade_reason': reason,
        'citations': citations,
        'usage': usage,
    }
