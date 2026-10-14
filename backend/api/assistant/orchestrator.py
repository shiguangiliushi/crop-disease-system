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

import json
import logging
import time
from dataclasses import dataclass, field

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


def _fallback_body(hits, lang: str = prompts.DEFAULT_LANG) -> str:
    """降级时给"词条原文"：把命中条目的关键字段原样列出来。

    刻意**不做任何改写或总结** —— 没有 AI 的时候就老老实实给档案，
    让用户知道这不是 AI 的回答（正文前缀由 `prompts.degrade_text('no_llm')` 说明）。

    第 197 批：按语言取字段与标签（英文优先 `*_en`、为空回落中文），
    否则英文用户会拿到"英文提示 + 中文档案"的半截本地化。
    """
    from .context import (CARE_SECTIONS, DISEASE_SECTIONS, HEALTHY_SECTIONS,
                          PREVENTION_LABELS_EN, _localized_pair, field_text,
                          section_label)

    english = lang == 'en'
    blocks: list[str] = []
    for index, hit in enumerate(hits[:2], start=1):
        pest = hit.pest
        head = (f'[{index}] {pest.name_en or pest.name} (Crop: {pest.crop_type_en or pest.crop_type})'
                if english else f'【{index}】{pest.name}（作物：{pest.crop_type}）')
        lines = [head]
        latin = (pest.scientific_name or '').split('（')[0].strip()
        if latin:
            lines.append(f'{"Scientific name" if english else "学名"}: {latin}')
        if hit.is_healthy and hit.profile is not None:
            for title, attr in HEALTHY_SECTIONS + CARE_SECTIONS:
                value = _localized_pair(hit.profile, attr, f'{attr}_en', lang)
                if value:
                    lines.append(f'{section_label(title, lang)}: {value}' if english
                                 else f'{title}：{value}')
        else:
            for title, attr in DISEASE_SECTIONS:
                value = _localized_pair(pest, attr, f'{attr}_en', lang)
                if value:
                    lines.append(f'{section_label(title, lang)}: {value}' if english
                                 else f'{title}：{value}')
            for method in pest.prevention_methods.all().order_by('category'):
                en_value = field_text(method.measure_en or '', 'en')
                zh_value = field_text(method.measure or '', 'zh')
                value = (en_value or zh_value) if english else zh_value
                if not value:
                    continue
                title = (PREVENTION_LABELS_EN.get(method.category, method.category) if english
                         else method.get_category_display())
                lines.append(f'{title}: {value}' if english else f'{title}：{value}')
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)


def _guard_reply(result: guard.GuardResult, lang: str) -> tuple[str, str]:
    """把闸门结果翻译成 (回答文本, 降级原因)。话术按语言取（第 197 批）。"""
    if result.reason == 'empty':
        return prompts.degrade_text('empty', lang), 'empty'
    if result.reason == 'too_long':
        return prompts.degrade_text('too_long', lang, limit=guard.MAX_QUESTION_CHARS), 'too_long'
    if result.reason == 'sensitive':
        return prompts.degrade_text('sensitive', lang, words=result.detail), 'sensitive'
    if result.reason == 'rate_limited':
        return prompts.degrade_text('rate_limited', lang, limit=result.detail), 'rate_limited'
    return prompts.degrade_text('no_source', lang), 'no_source'


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


def _rate_limit() -> int:
    """配置统一从 settings 读（settings.py 已经做过 `int()` 转换与默认值，
    这里再用 os.environ 兜一遍只会让两处口径可能不一致）。"""
    from django.conf import settings as django_settings

    value = getattr(django_settings, 'ASSISTANT_RATE_PER_MINUTE', None)
    return guard.DEFAULT_RATE_PER_MINUTE if value is None else value


@dataclass
class Prepared:
    """同步与流式**共用**的"决策阶段"产物（第 195 批抽出）。

    为什么要有它：`ask()` 与 `ask_stream()` 的区别只在**怎么生成**（一次拿完 vs 逐字）。
    闸门 / 会话 / 检索 / 上下文 / 降级判定这五步必须完全一致 —— 否则会出现
    "同步说未收录、流式却说打某某药"这种自相矛盾。抽出来就只有一份实现可改。
    """

    session: AssistantSession
    question: str
    #: 归一化后的语言（`'zh'` / `'en'`）—— 提示词、降级话术、落库都跟着它走
    lang: str = prompts.DEFAULT_LANG
    #: 非空表示**不必生成**，直接把这段话当答案（降级）
    early_answer: str = ''
    early_reason: str = ''
    messages: list[dict] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    prompt_version: str = ''


def _prepare(*, user, question: str, session: AssistantSession | None,
             pest_identifier: str, lang: str = prompts.DEFAULT_LANG) -> Prepared | dict:
    """跑完"决策阶段"。返回 `Prepared`；对**空问题**直接返回响应字典（连会话都不建）。"""
    code = prompts.normalize_lang(lang)
    guard_result = guard.check(question, user=user, rate_per_minute=_rate_limit())

    # 空问题连会话都不该建（否则问答历史里会积一堆空会话）。
    if not guard_result.ok and guard_result.reason == 'empty':
        return {
            'session_id': getattr(session, 'pk', None),
            'message_id': None,
            'answer': prompts.degrade_text('empty', code),
            'degraded': True,
            'degrade_reason': 'empty',
            'citations': [],
            'usage': {},
        }

    session = _get_or_create_session(
        user=user, session=session, question=guard_result.question or question,
        pest_identifier=pest_identifier,
    )
    prepared = Prepared(session=session, question=guard_result.question or question, lang=code)

    if not guard_result.ok:
        prepared.early_answer, prepared.early_reason = _guard_reply(guard_result, code)
        return prepared

    intent = detect_intent(prepared.question)
    from django.conf import settings as django_settings

    hits = search(prepared.question, pest_identifier=pest_identifier,
                  top_k=getattr(django_settings, 'ASSISTANT_TOP_K', 5))
    built = context_builder.build(hits, lang=code)

    if built.is_empty:
        # 无来源不回答：农业场景答错药是事故，不是体验问题
        prepared.early_answer = prompts.degrade_text('no_source', code)
        prepared.early_reason = 'no_source'
    elif not llm.enabled():
        prepared.early_answer = prompts.degrade_text('no_llm', code, body=_fallback_body(hits, code))
        prepared.early_reason = 'llm_disabled'
    else:
        prepared.messages = prompts.build_messages(prepared.question, built.text, intent, code)
        prepared.citations = [c.as_dict() for c in built.citations[:MAX_CITATIONS]]
        prepared.prompt_version = prompts.PROMPT_VERSION
    return prepared


def _persist(session, question: str, *, answer: str, reason: str, model: str = '',
             latency_ms: int = 0, citations: list | None = None,
             usage: dict | None = None, prompt_version: str = '',
             lang: str = prompts.DEFAULT_LANG) -> AssistantMessage:
    """落库：用户消息 + 助手消息（单事务，要么都写要么都不写）。"""
    with transaction.atomic():
        AssistantMessage.objects.create(session=session, role='user', content=question)
        message = AssistantMessage.objects.create(
            session=session,
            role='assistant',
            content=answer,
            model=model,
            degraded=bool(reason),
            degrade_reason=reason,
            latency_ms=latency_ms,
            citations=citations or [],
            usage=usage or {},
            prompt_version=prompt_version,
            lang=prompts.normalize_lang(lang),
        )
        session.save(update_fields=['updated_at'])   # 触发 auto_now，让会话列表按活跃排序
    return message


def ask(*, user, question: str, session: AssistantSession | None = None,
        pest_identifier: str = '', lang: str = prompts.DEFAULT_LANG) -> dict:
    """问一个问题，返回结构化结果。**永不抛异常给调用方**（见模块 docstring）。"""
    prepared = _prepare(user=user, question=question, session=session,
                        pest_identifier=pest_identifier, lang=lang)
    if isinstance(prepared, dict):
        return prepared

    answer, reason, citations, usage, actual_model, prompt_version = '', '', [], {}, '', ''
    latency_ms = 0

    try:
        if prepared.early_answer:
            answer, reason = prepared.early_answer, prepared.early_reason
        else:
            prompt_version = prepared.prompt_version
            try:
                result = llm.chat(prepared.messages)
            except llm.LLMError as exc:
                logger.warning('助手生成失败，降级：%s', exc)
                from .retriever import search as _search
                hits = _search(prepared.question, pest_identifier=pest_identifier)
                answer = prompts.degrade_text('error', prepared.lang, reason=exc,
                                             body=_fallback_body(hits, prepared.lang))
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
                # 候选引用来自 `_prepare`（那里已按【序号】顺序排好）。
                # 判断方式：答案里出现【i】就认为第 i 条被引用；一条都没标时
                # **不判失败**（模型可能只是忘了标序号，内容仍来自上下文），
                # 但把全部候选带上并在 usage 里如实记 `citation_marked=False`。
                marked = {
                    index for index in range(1, len(prepared.citations) + 1)
                    if f'【{index}】' in result.text
                }
                if marked:
                    citations = [c for index, c in enumerate(prepared.citations, start=1)
                                 if index in marked]
                    usage['citation_marked'] = True
                else:
                    citations = list(prepared.citations)
                    usage['citation_marked'] = False
                answer = (result.text or '').strip()
                if not answer:
                    answer, reason, citations = prompts.degrade_text('no_source', prepared.lang), 'no_source', []
    except Exception as exc:  # noqa: BLE001 —— 兜底：任何意外都要变成可读回答
        logger.exception('助手链路出现未预期错误')
        answer = f'（AI 助手暂时不可用：{exc}）'
        reason = 'llm_error'

    # ── ⑧ 落库（单事务：用户消息与助手消息要么都写、要么都不写）──────────
    message = _persist(
        prepared.session, prepared.question, answer=answer, reason=reason,
        model=actual_model, latency_ms=latency_ms, citations=citations,
        usage=usage, prompt_version=prompt_version, lang=prepared.lang,
    )

    return {
        'session_id': prepared.session.pk,
        'message_id': message.pk,
        'answer': answer,
        'degraded': bool(reason),
        'degrade_reason': reason,
        'citations': citations,
        'usage': usage,
    }


def _sse(event: str, data: dict) -> bytes:
    """拼一个 SSE 事件。

    ⚠️ `ensure_ascii=False` + UTF-8 编码：中文若被转义成 `\\uXXXX`，前端能解析但
    体积大且调试时看不懂；直接发 UTF-8 更直观（SSE 规范本身就是 UTF-8）。
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f'event: {event}\ndata: {payload}\n\n'.encode('utf-8')


def ask_stream(*, user, question: str, session: AssistantSession | None = None,
               pest_identifier: str = '', lang: str = prompts.DEFAULT_LANG):
    """流式问答：yield SSE 事件字节串。

    事件序列（与 `docs/智能回答助手框架.md` 第五节一致）：

        meta       {session_id, message_id?, degraded, degrade_reason, citations}
        delta      {text}                     ← 多条（降级时只有一条，整段给）
        citations  {citations}                ← 生成结束后的校验结果
        done       {usage, degraded, degrade_reason, model, latency_ms}

    ## 落库时机（这里刻意与"先答完再存"不同）

    助手消息**在开始流式之前就建好**（内容为空、`degraded` 先按"是否降级"填），
    生成结束后再 update。理由：这样 `meta` 事件里能立刻带上 `message_id`，
    前端断流后仍能定位这条消息；而如果等流完再存，中途刷新就什么都没留下。
    代价是"空内容的助手消息"会短暂存在 —— 但它必然被同一个请求补全。
    """
    prepared = _prepare(user=user, question=question, session=session,
                        pest_identifier=pest_identifier, lang=lang)
    if isinstance(prepared, dict):
        # 空问题：不落库，只把同一套响应翻译成 SSE
        yield _sse('meta', {'session_id': prepared['session_id'], 'message_id': None,
                            'degraded': True, 'degrade_reason': 'empty', 'citations': []})
        yield _sse('delta', {'text': prepared['answer']})
        yield _sse('done', {'usage': {}, 'degraded': True, 'degrade_reason': 'empty'})
        return

    started = time.time()

    # ── 降级路径：不调模型，整段一次给 ────────────────────────────────────
    if prepared.early_answer:
        message = _persist(prepared.session, prepared.question,
                           answer=prepared.early_answer, reason=prepared.early_reason,
                           citations=[], prompt_version=prepared.prompt_version,
                       lang=prepared.lang)
        yield _sse('meta', {'session_id': prepared.session.pk, 'message_id': message.pk,
                            'degraded': True, 'degrade_reason': prepared.early_reason,
                            'citations': []})
        yield _sse('delta', {'text': prepared.early_answer})
        yield _sse('done', {'usage': {}, 'degraded': True,
                            'degrade_reason': prepared.early_reason,
                            'latency_ms': message.latency_ms})
        return

    # ── 生产路径：先建消息行（内容待补），拿到 id 后再开始流 ─────────────
    with transaction.atomic():
        AssistantMessage.objects.create(session=prepared.session, role='user',
                                        content=prepared.question)
        message = AssistantMessage.objects.create(
            session=prepared.session, role='assistant', content='', degraded=False,
            prompt_version=prepared.prompt_version, lang=prepared.lang,
        )
        prepared.session.save(update_fields=['updated_at'])

    yield _sse('meta', {'session_id': prepared.session.pk, 'message_id': message.pk,
                        'degraded': False, 'degrade_reason': '',
                        'citations': prepared.citations})

    pieces: list[str] = []
    usage: dict = {}
    actual_model = ''
    error_reason = ''
    try:
        for event in llm.chat_stream(prepared.messages):
            if 'text' in event:
                pieces.append(event['text'])
                yield _sse('delta', {'text': event['text']})
            elif 'usage' in event:
                usage.update(event['usage'])
            elif 'model' in event:
                actual_model = event['model']
    except llm.LLMError as exc:
        # ⚠️ 关键判断：**已经吐出去的字不能收回**。
        #    如果已经有内容，就保留它并如实标记中途出错；只有"一个字都没发出去"时
        #    才整段降级成档案原文。
        #    第一版没做这个区分 —— 直接把部分回答替换成降级文本，
        #    结果是"用户已经看到的半句话凭空消失"（被单测抓出来）。
        logger.warning('助手流式生成失败：%s', exc)
        error_reason = 'llm_error'
        if not pieces:
            hits = search(prepared.question, pest_identifier=pest_identifier)
            text = prompts.degrade_text('error', prepared.lang, reason=exc,
                                                body=_fallback_body(hits, prepared.lang))
            pieces = [text]
            yield _sse('delta', {'text': text})
        else:
            error_reason = 'llm_error_partial'
    except Exception as exc:  # noqa: BLE001
        logger.exception('助手流式链路出现未预期错误')
        error_reason = 'llm_error'
        if not pieces:
            text = f'（AI 助手暂时不可用：{exc}）'
            pieces = [text]
            yield _sse('delta', {'text': text})
        else:
            # 同上：已有内容就保留，只标记中途出错
            error_reason = 'llm_error_partial'

    answer = ''.join(pieces).strip()
    latency_ms = int((time.time() - started) * 1000)
    reason = error_reason
    citations = list(prepared.citations)

    if not answer:
        # 模型一个字都没吐（例如上下文过长被拒）：按"未收录"处理并如实记录
        answer, reason, citations = prompts.degrade_text('no_source', prepared.lang), 'no_source', []

    usage['latency_ms'] = latency_ms
    if actual_model:
        usage['configured_model'] = llm.model_name()
    marked = {i for i in range(1, len(prepared.citations) + 1) if f'【{i}】' in answer}
    if marked:
        citations = [c for i, c in enumerate(prepared.citations, start=1) if i in marked]
        usage['citation_marked'] = True
    else:
        usage['citation_marked'] = False

    message.content = answer
    message.model = actual_model
    message.degraded = bool(reason)
    message.degrade_reason = reason
    message.latency_ms = latency_ms
    message.citations = citations
    message.usage = usage
    message.save(update_fields=['content', 'model', 'degraded', 'degrade_reason',
                               'latency_ms', 'citations', 'usage'])

    yield _sse('citations', {'citations': citations})
    yield _sse('done', {'usage': usage, 'degraded': bool(reason), 'degrade_reason': reason,
                        'model': actual_model, 'latency_ms': latency_ms})
