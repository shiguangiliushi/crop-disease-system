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
import re
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
#: 单条消息最多带几处引用（前端渲染太多反而看不出重点）。
#: ⚠️ 第 209 批从 6 提到 8：用户会问"苹果跟葡萄的**所有**病害"这类**按作物清点**的问题，
#:    而苹果 4 条 + 葡萄 4 条 = 8 条。上限卡在 6 时，上下文里明明有 8 条、来源却只给 6 条
#:    —— 又一次"来源少于实际用到的"，与本批刚修的 `_fallback_body` 是同一类问题。
MAX_CITATIONS = 8


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
    # ⚠️ 第 207 批：这里原来写死 `hits[:2]`，而引用列表给的是**全部命中** ——
    #    于是又出现"来源多于正文实际用到的"（正文 2 条、来源 5 条），
    #    与本批刚修掉的缺陷同源。降级正文就该把**它将会被引用的那几条**都列出来。
    for index, hit in enumerate(hits[:MAX_CITATIONS], start=1):
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


def _collapse_single_source(answer: str, citations: list) -> tuple[str, bool]:
    """只有一个来源时，正文里的 `【1】` 只留一次（第 212 批）。

    ## 为什么（用户反馈"为什么回答出来的答案后面都有【1】"）

    "番茄晚疫病怎么打药？"这类问题只命中**一个**词条，模型于是在每条措施后面都标 `【1】`——
    实测一条 842 字的回答里出现了 **10 次同一个 `【1】`**。

    但**同一个序号重复十遍不提供任何额外信息**：读者早就知道全部内容出自那一条。
    "可溯源"的真正要求是"**每个结论都能对应到某条来源**"，而这在只有一个来源时
    天然成立 —— 所以留一次（首次出现处）就够，其余删掉。

    ## 为什么在后端做，而不是前端显示时过滤

    前端过滤只改变"看起来"，**接口与库里仍留着十处重复**：
    以后做导出、做引用统计，或别的客户端来读，噪声还在。
    存进库里的就该是**最终要显示的那段话**。

    ## 边界（都有单测守着）

    - **只有单个来源时**才折叠；多来源（如"苹果跟葡萄"）必须保留序号，
      否则读者无法知道哪句出自哪条 —— 那才是序号真正起作用的地方；
    - 删标记可能留下连续空格或行尾空格，顺手收干净；
    - 不重排任何文字，只删标记本身。

    @returns (处理后的正文, 是否发生了折叠)
    """
    marker = '【1】'
    if len(citations) != 1 or marker not in answer:
        return answer, False

    head, sep, tail = answer.partition(marker)
    if not sep:
        return answer, False
    collapsed = head + marker + tail.replace(marker, '')
    collapsed = re.sub(r'[ \t]{2,}', ' ', collapsed)
    collapsed = re.sub(r'[ \t]+$', '', collapsed, flags=re.M)
    return collapsed, True


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
            'truncated': False,
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
                  top_k=getattr(django_settings, 'ASSISTANT_TOP_K', 8))
    hits = _trim_dominated_hits(hits)
    built = context_builder.build(hits, lang=code)

    if built.is_empty:
        # 无来源不回答：农业场景答错药是事故，不是体验问题
        prepared.early_answer = prompts.degrade_text('no_source', code)
        prepared.early_reason = 'no_source'
    elif not llm.enabled():
        prepared.early_answer = prompts.degrade_text('no_llm', code, body=_fallback_body(hits, code))
        prepared.early_reason = 'llm_disabled'
        # 第 207 批：降级给的是**档案原文**，出处就是这些命中 —— 必须带上引用
        prepared.citations = _citations_from_hits(hits, code)
    else:
        prepared.messages = prompts.build_messages(prepared.question, built.text, intent, code)
        prepared.citations = [c.as_dict() for c in built.citations[:MAX_CITATIONS]]
        prepared.prompt_version = prompts.PROMPT_VERSION
    return prepared


#: 命中分数低于"最高分 × 此比例"的条目在**单一主角**场景下被丢弃。
#: 0.5 的来历（第 209 批实测分数分布）：
#:   · 单一病害："番茄晚疫病怎么打药？" → 104 / 34 / 32 / 20 / 20 …
#:     次高只有最高分的 33%，`< 52` 被丢 → 上下文里只剩真正相关的那两条；
#:   · 按作物清点："苹果跟葡萄病害防治方法" → 20 / 20 / 19 / 19 / 19 / 19 / 18 / 18
#:     全是最高分的 90%~100%，**一条都不会被丢** → 8 条完整清单。
_DOMINANCE_RATIO = 0.5


def _trim_dominated_hits(hits):
    """有明确主角时，丢掉被主角压制的弱命中。

    ## 为什么需要它（第 209 批）

    为了让"苹果跟葡萄的**所有**病害"能列全，`ASSISTANT_TOP_K` 从 5 提到 8。
    但这是一个**全局**值 —— 副作用是**单一病害问题也拖进 7 条弱命中**：
    "番茄晚疫病怎么打药？"的上下文从约 3000 字涨到 8151 字，
    而且模型会顺手去讲番茄早疫病、斑枯病等**用户根本没问**的病（第一批就踩过这个污染）。

    判据用**分数落差**而不是关键词：一个词条分数远高于其他，说明问题指向它；
    分数扁平（都靠"作物命中"拿分）说明用户在**清点整个作物**。
    这样"清点"与"单点"两类问题各自得到合适的上下文，不需要额外的意图分类器。
    """
    if len(hits) < 2:
        return hits
    top = max(hit.score for hit in hits)
    if top <= 0:
        return hits
    kept = [hit for hit in hits if hit.score >= top * _DOMINANCE_RATIO]
    # 全部被丢（不可能，因为最高分自己一定 >= 阈值）时保底返回原列表
    return kept or hits


def _citations_from_hits(hits, lang: str = prompts.DEFAULT_LANG) -> list[dict]:
    """从检索命中直接造引用列表（**降级路径用**）。

    ## 为什么需要它（第 207 批补的一个真缺陷）

    降级（`llm_disabled` / `llm_error`）时给的是 `_fallback_body(hits)` 生成的
    **档案原文**（形如"【1】番茄晚疫病（作物：番茄）症状描述：…"）——
    这段话的出处**就是这些词条**，可原来两条降级路径都**没填 `citations`**，
    于是界面上"来源"是空的：**明明在引用档案，却不标出处**。
    而引用校验里那句"降级文本保留候选来源是对的"因此从未生效过 —— 因为压根没有候选。

    `snippet` 取与 `context.build()` 同源的字段文本（英文优先 `*_en`、为空回落中文），
    这样降级回答的来源展示与非降级时一致。
    """
    from .context import (DISEASE_SECTIONS, PREVENTION_LABELS_EN, _localized_pair,
                          field_text, section_label)

    english = lang == 'en'
    out: list[dict] = []
    for hit in hits[:MAX_CITATIONS]:
        pest = hit.pest
        label = pest.name or f'词条#{pest.pk}'
        parts: list[str] = []
        for title, attr in DISEASE_SECTIONS:
            value = _localized_pair(pest, attr, f'{attr}_en', lang)
            if value:
                shown = section_label(title, lang) if english else title
                sep = ': ' if english else '：'
                parts.append(f'{shown}{sep}{value[:80]}')
        for method in pest.prevention_methods.all().order_by('category'):
            en_value = field_text(method.measure_en or '', 'en')
            zh_value = field_text(method.measure or '', 'zh')
            value = (en_value or zh_value) if english else zh_value
            if not value:
                continue
            title = (PREVENTION_LABELS_EN.get(method.category, method.category) if english
                     else method.get_category_display())
            sep = ': ' if english else '：'
            parts.append(f'{title}{sep}{value[:80]}')
        joiner = ' | ' if english else ' ｜ '
        out.append({
            'pest_id': pest.pk,
            'label': label,
            'snippet': joiner.join(parts)[:200] if parts else label,
        })
    return out


def _persist(session, question: str, *, answer: str, reason: str, model: str = '',
             latency_ms: int = 0, citations: list | None = None,
             usage: dict | None = None, prompt_version: str = '',
             lang: str = prompts.DEFAULT_LANG, truncated: bool = False) -> AssistantMessage:
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
            # 第 204 批：被 max_tokens 截断时如实记下来（界面据此提示"回答可能不完整"）
            truncated=truncated,
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
    truncated = False
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
                # 同上：这段是档案原文，出处必须带上（原来这里是空的）
                citations = _citations_from_hits(hits, prepared.lang)
            else:
                latency_ms = result.latency_ms
                actual_model = result.model
                # 第 204 批：触到 max_tokens 时 finish_reason='length'，答案被截断
                truncated = result.truncated
                usage = {
                    'prompt_tokens': result.prompt_tokens,
                    'completion_tokens': result.completion_tokens,
                    'latency_ms': result.latency_ms,
                    'configured_model': llm.model_name(),
                    'finish_reason': result.finish_reason,
                }
                # ── ⑦ 引用校验：模型必须真的引用了上下文里的条目 ──────
                # 候选引用来自 `_prepare`（那里已按【序号】顺序排好）。
                # 判断方式：答案里出现【i】就认为第 i 条被引用。
                #
                # ⚠️ 第 207 批改了"一条都没标"时的处置。原来是**照单全带上全部候选**，
                #    理由是"模型可能只是忘了标序号，内容仍来自上下文"——
                #    但实测（20 条回答里 4 条）这会造出一种误导：
                #    问"苹果跟葡萄"检索到 4 条、正文只覆盖 2 条，而来源区列着 4 条，
                #    用户以为"答全了"，实际另外两条根本没写。
                #    **来源区是"这段回答依据了什么"的承诺**，不能拿它当候选清单用。
                #    现在的处置：宁可**不显示来源**（并在系统里标记 unmarked），
                #    也不显示可能没被用到的来源。
                marked = {
                    index for index in range(1, len(prepared.citations) + 1)
                    if f'【{index}】' in result.text
                }
                if marked:
                    citations = [c for index, c in enumerate(prepared.citations, start=1)
                                 if index in marked]
                    usage['citation_marked'] = True
                elif prepared.citations and not reason:
                    # 有候选、却一个都没标：不冒充"有来源"，让界面如实提示。
                    # ⚠️ `not reason` 是必需的：**降级文本**（`no_llm`/`llm_error` 那种
                    #     "档案原文"）不是模型生成的，本来就不带 `【n】`，此时保留候选来源
                    #     是正确的 —— 那确实是这段话的出处。
                    citations = []
                    usage['citation_marked'] = False
                    usage['citation_candidates'] = len(prepared.citations)
                else:
                    citations = list(prepared.citations) if reason else []
                    usage['citation_marked'] = False
                answer = (result.text or '').strip()
                # 第 212 批：只有一个来源时，正文里的 `【1】` 只留一次
                answer, collapsed = _collapse_single_source(answer, citations)
                if collapsed:
                    usage['single_source_collapsed'] = True
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
        truncated=truncated,
    )

    return {
        'session_id': prepared.session.pk,
        'message_id': message.pk,
        'answer': answer,
        'degraded': bool(reason),
        'degrade_reason': reason,
        'citations': citations,
        'usage': usage,
        # 第 204 批：答案是否被长度上限截断（前端据此提示"回答可能不完整"）
        'truncated': truncated,
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
        yield _sse('done', {'usage': {}, 'degraded': True, 'degrade_reason': 'empty',
                            'truncated': False})
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
    # 第 204 批：`finish_reason == 'length'` = 被 max_tokens 截断，答案不完整
    truncated = False
    # 第 207 批：降级成"档案原文"时的出处（重新检索命中的那些词条）
    degrade_citations: list[dict] = []
    try:
        for event in llm.chat_stream(prepared.messages):
            if 'text' in event:
                pieces.append(event['text'])
                yield _sse('delta', {'text': event['text']})
            elif 'usage' in event:
                usage.update(event['usage'])
            elif 'model' in event:
                actual_model = event['model']
                # 与 `model` 同一个事件（流的最后一个），见 llm.chat_stream 的 docstring
                truncated = event.get('finish_reason') == 'length'
                if event.get('finish_reason'):
                    usage['finish_reason'] = event['finish_reason']
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
            # 第 207 批：这段是档案原文，出处必须带上（与同步路径一致）
            degrade_citations = _citations_from_hits(hits, prepared.lang)
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
    # 第 207 批：降级成"档案原文"时，出处是**重新检索到的那些命中**，
    # 而不是首次检索的候选（两者可能不同：失败后是按问题重查的）。
    citations = degrade_citations if degrade_citations else list(prepared.citations)

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
        # 第 212 批：只有一个来源时，正文里的 `【1】` 只留一次。
        # ⚠️ 必须放在**算出 citations 之后**（判定依据是"最终有几个来源"），
        #    并且要在 `answer` 定型之后、`message.content = answer` 之前 ——
        #    这样流式界面与落库内容一致。流式时用户此前已看到带 10 处标记的增量文本，
        #    收尾会整体替换成折叠后的版本（前端本来就是"最后以 done 的内容为准"）。
        answer, collapsed = _collapse_single_source(answer, citations)
        if collapsed:
            usage['single_source_collapsed'] = True
    else:
        # 与同步路径同一处置（第 207 批）：有候选却一个都没标 → **不冒充有来源**。
        # 但**降级文本**（`no_llm` / `llm_error` 那种"档案原文"）不同：它不是模型生成的，
        # 本来就不会带 `【n】`，此时保留候选来源是正确的，不该被清掉。
        if prepared.citations and not reason:
            citations = []
            usage['citation_candidates'] = len(prepared.citations)
        usage['citation_marked'] = False

    message.content = answer
    message.model = actual_model
    message.degraded = bool(reason)
    message.degrade_reason = reason
    message.latency_ms = latency_ms
    message.citations = citations
    message.usage = usage
    # 第 204 批：被截断这件事要落库 —— 否则"历史里的回答为什么是半句"永远查不清
    message.truncated = truncated
    message.save(update_fields=['content', 'model', 'degraded', 'degrade_reason',
                               'latency_ms', 'citations', 'usage', 'truncated'])

    yield _sse('citations', {'citations': citations})
    yield _sse('done', {'usage': usage, 'degraded': bool(reason), 'degrade_reason': reason,
                        'model': actual_model, 'latency_ms': latency_ms,
                        # 前端据此在气泡下方提示"回答可能不完整"
                        'truncated': truncated,
                        # 第 212 批：带上**最终正文**（可能与逐字增量略有不同 ——
                        # 单来源时 `【1】` 被折叠成一处）。前端在 done 时用它替换气泡内容，
                        # 这样"流式看到的"与"落库/历史里的"完全一致；
                        # 否则刷新前后是两副样子（用户会以为数据变了）。
                        'answer': answer})
