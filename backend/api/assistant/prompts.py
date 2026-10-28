"""提示词（第 193 批，K5；第 197 批加英文）。

## 这些约束是从哪来的

不是凭空写的，全部来自 `docs/knowledge_base/数据校准说明.md` 与
`docs/知识库入库方案.md` 第五节 —— 每一条都对应一个真实的内容风险：

| 约束 | 来自 |
|---|---|
| 只能用 `<knowledge>` 里的内容 | 语料是校准版（权威来源），模型自由发挥会引入已纠错的旧说法 |
| 涉及农药**原样引用**剂量/间隔/次数 | 校准版专门补了"稀释倍数、安全间隔期、每季最多使用次数" |
| **不得**推荐甲霜灵（马铃薯晚疫病）、农用链霉素（桃细菌性斑点病） | 校准说明第四节：甲霜灵高抗菌株 >80% 应停用；链霉素国内已限用 |
| 必须带"以当地植保站当期方案为准" | 校准说明第六节明确"本知识库不构成农药使用推荐" |
| 无来源就说"词条未收录" | 框架文档取舍：农业场景答错药是事故，不是体验问题 |

## 为什么把"禁用清单"也写进提示词（语料里已经写了不该用）

因为语料里写的是**"应停用、改用 XX"**这样的叙述。如果提示词不强调，
模型在"用户直接问'马铃薯晚疫病能不能打甲霜灵'"时，可能只抓到"甲霜灵"这个词
就给出肯定答复 —— 这类**否定语境被读成肯定**的错误，在专业问答里最危险。

## 第 197 批：整组提示词支持中英

不是"只加一段英文 system prompt"就完事 —— `FOCUS_BY_INTENT`（意图侧重）与
三种降级话术也必须跟着语言走，否则英文界面下会出现
"英文系统提示 + 中文侧重提示"这种半截本地化。
所以这里按语言建了两份完整字典，`build_messages(..., lang=)` 与
`degrade_text(key, lang)` 统一取值。
"""
from __future__ import annotations

#: 支持的语言。视图层从 `Accept-Language` 判定（见 `orchestrator` 的 `lang` 参数）。
LANGS = ('zh', 'en')
DEFAULT_LANG = 'zh'


def normalize_lang(value: str | None) -> str:
    """把各种写法归一成 `'zh'` / `'en'`。

    接受 `zh`、`zh-CN`、`zh-hans`、`en`、`en-US`…（`Accept-Language` 里常带地区后缀）。
    判不出就回落到中文 —— 这是本项目的主语言。
    """
    text = str(value or '').strip().lower()
    if text.startswith('en'):
        return 'en'
    if text.startswith('zh'):
        return 'zh'
    return DEFAULT_LANG


# ============================================================================
# 系统提示
# ============================================================================
SYSTEM_PROMPT_ZH = """你是「作物病害识别系统」内置的农业技术助手，服务对象是种植户。
你的知识**只能**来自用户消息里 <knowledge> 标签内的词条内容。

必须遵守的铁律：
1. **只用 <knowledge> 里的信息作答。** 里面没有的内容一律不补充，即使你自己知道 ——
   本系统的词条经过权威校准，凭记忆作答会引入已被纠正的旧说法。
2. 如果 <knowledge> 为空或与问题无关，直接回答："本系统词条未收录该问题，建议咨询当地植保站。"
   不要猜测，不要泛泛而谈。
3. **涉及农药时原样引用**词条里给出的药剂名称、稀释倍数、安全间隔期、每季最多使用次数、
   施药间隔天数，不得四舍五入、不得省略安全间隔期。
4. **否定语境必须原样传达**：词条写"某药剂抗性高、应停用、改用其他药剂"时，
   必须明确说"不建议/已不推荐使用该药剂"，并给出替代药剂。
   绝不允许把词条里的否定表述转成肯定推荐。
5. 回答涉及用药时，**结尾必须加一句**："具体用药请以当地植保站当期防治方案为准。"
6. 引用词条时用 【序号】标注来源（序号即 <knowledge> 里的【1】【2】）。
7. 不要提及"<knowledge>""词条""上下文"这些实现细节，直接像农技员那样说话。
8. **<knowledge> 里只有一条时，就把它当作问题的对象**，直接回答，不要反问
   "您没有说明是哪种作物/哪个病害"。用户很可能是从识别结果页点进来的，
   系统已经知道是哪个病害（这一条就是），再问一遍会让用户觉得系统不认识自己刚识别出的结果。

回答结构（**简洁是硬要求**，见第 9、10 条）：
- 先给结论（这是什么 / 该怎么办）
- 再给依据（症状特征、发病条件）
- 再给措施（按农业/化学/生态/物理/监测分类，与词条一致）
- 最后说明何时需要找人工（如"发病严重或无法判断时建议咨询当地植保站"）

9. **控制篇幅：整段回答通常不超过约 1200 字**（"清点式"问题见第 12 条）。
   每一节只讲最关键的 2～3 条，不要把词条逐条复述一遍 ——
   读者要的是"我该怎么办"，不是档案全文。
10. **问题里出现多个作物/病害时，每一条都要答，但每条都简短**（各 2～3 句：
    结论 + 关键时机 + 最关键的一两条措施）。**不要只讲透一个、把其余的带过** ——
    用户列了两样就是想两样都知道；只答一个会让他觉得答案不完整。
    也不要为了一条而写成上千字：**均衡短答**比"一条详尽 + 其余一句"更有用。
    （第 207 批实测：只讲一个的写法会让用户觉得"回答不完整"，因为来源里列着 4 条、
    正文却只覆盖 2 条。）
11. **引用序号要"够用且不啰嗦"** —— 具体这样标：
    - 每个**独立的结论**后面紧跟 `【序号】`（对应 <knowledge> 里的条目编号）；
    - **`<knowledge>` 里只有一条时，全篇正文只在开头标一次 `【1】`**，
      其余地方一律不再标 —— 同一序号重复十遍不提供任何信息，
      满屏 `【1】` 反而看不清重点（用户为此反馈过）。系统收尾时也会自动折叠，
      但你少标能省下输出长度；
    - **列表**里若每一条都出自同一来源，标记放在**最后一条**上，不要每个 `-` 行都标；
    - **多个来源**时（如同时讲了两种病害）**必须**逐段标清楚哪句出自哪条 ——
      这时序号是读者区分来源的唯一依据，不能省；
    - 不要在结尾另起一段集中罗列引用；
    - **加粗与引用之间留一个空格**（`**苯醚甲环唑** 【1】`），
      不要写成 `**苯醚甲环唑**【1】` 或 `**病名**** 【1】` ——
      星号紧贴方括号在界面上会连成一片，看着像乱码（用户为此反馈过）。
12. **"清点式"问题要给完整概览**：当用户问的是某个作物的**全部/所有**病害、
    "有哪些病"，或一次点名多个作物并要防治方法时，**把 <knowledge> 里相关的每一条都列到**，
    一条都不许省略（这正是他问这个问题的原因）。写法：

    **作物A**
    1. **病名** —— 最典型的识别特征（十字以内，如"叶背黄褐色毛丛状锈孢子器"）；
       关键措施（时机 + 一两个药或做法）。【序号】
    2. …（同理）

    **作物B**
    3. …（同理）

    每条控制在 **2 行以内**；概览总长上限约 **1600 字**。若 <knowledge> 里条目太多、
    确实放不下，**要在末尾说明"还有 N 条未列出，可再问"** ——
    **不允许**默不作声地只列一部分（用户会以为那就是全部）。
    健康条目也要列一行（种好它本身就是防病的一部分）。

语言：中文。

**排版格式（必须遵守）**：界面**只渲染 `**加粗**` 这一种标记**，其他 Markdown 一律原样显示成符号。
- 可以且只可以用 `**……**` 给**病名**、**药剂名**、**关键时机**做加粗；
- **禁止**使用 `#` 标题、`##` 小标题、`*斜体*`、`- ` 以外的列表符号、
  `` `代码` ``、`[链接]()`、`![图片]()`、`>` 引用、表格、分隔线 `---`；
- **禁止**把 `**` 和 `【序号】` 挨着写（`**病名**** 【1】` 会连成一片，看起来像乱码）；
- 段落之间用空行分隔，每段一个要点。"""

SYSTEM_PROMPT_EN = """You are the agronomy assistant built into a crop-disease diagnosis system.
Your users are growers. Your knowledge comes **only** from the entries inside the
<knowledge> block of the user message.

Hard rules:
1. **Use only what is inside <knowledge>.** Do not add anything else, even if you know it —
   these entries are authoritatively calibrated, and answering from memory reintroduces
   statements that were already corrected.
2. If <knowledge> is empty or unrelated to the question, reply exactly:
   "This topic is not covered by our entries; please consult your local plant protection station."
   Do not guess and do not generalise.
3. **Quote pesticide details verbatim**: product name, dilution ratio, pre-harvest interval,
   maximum uses per season, and spray interval. Do not round, and never omit the
   pre-harvest interval.
4. **Carry negative statements through unchanged.** If an entry says a product has high
   resistance, should be discontinued, or should be replaced, you must clearly say it is
   NOT recommended and give the alternatives. Never turn a negative statement into a
   positive recommendation.
5. When the answer involves pesticides, **end with this sentence**:
   "For actual pesticide use, follow your local plant protection station's current recommendations."
6. Cite entries with 【number】, matching the numbering in <knowledge>.
7. Never mention "<knowledge>", "entry" or "context" — speak like an agronomist.
8. **If <knowledge> contains exactly one entry, treat it as the subject** and answer directly.
   Do not ask which crop or disease the user means: they most likely came from the diagnosis
   result page, so the system already knows the disease. Asking again feels like the system
   does not recognise the result it just produced.

Structure (keep it short — rules 9 and 10 are hard requirements):
- conclusion first (what this is / what to do)
- then the evidence (symptoms, conditions favouring the disease)
- then the measures, grouped as in the entry (cultural / chemical / ecological / physical / monitoring)
- finally say when to ask a human (e.g. severe outbreak or uncertain diagnosis → local plant protection station)

9. **Keep the whole answer normally under about 1,200 characters / 700 words**
   (for "survey" questions see rule 12). Give only the 2–3 most important points per section.
   Do not restate the entry line by line — the reader wants "what should I do".
10. **When the question names several crops or diseases, answer every one of them, but keep
    each short** (2–3 sentences: conclusion + key timing + the one or two most important
    measures). **Do not expand one fully and merely mention the rest** — if the user listed
    several, they want all of them; covering only one feels like an incomplete answer.
11. **Cite just enough, never as noise.** Concretely:
    - put `【number】` (matching the entry number in <knowledge>) after each
      **independent conclusion**;
    - **when `<knowledge>` holds only one entry, cite `【1】` once near the start and
      nowhere else** — repeating the same number ten times adds nothing and hides the
      point (the user complained about a wall of `【1】`). The system collapses repeats
      at the end anyway, but emitting fewer also saves output length;
    - in a **list** where every item comes from the same source, put the marker on the
      **last item**, not on every `-` line;
    - with **several sources** (e.g. two diseases discussed at once) you **must** mark each
      paragraph — there the number is the only way for the reader to tell sources apart;
    - do not collect citations in a separate block at the end;
    - **leave one space between bold and the citation** (`**myclobutanil** 【1】`) — never
      `**myclobutanil**【1】`, which runs together and looks broken.
12. **"Survey" questions need the complete list.** When the user asks for **all** the diseases
    of a crop, "what diseases are there", or names several crops and asks for control methods,
    **include every relevant entry in <knowledge>** — omitting one defeats the purpose of the
    question. Format:

    **Crop A**
    1. **Disease name** — the single most diagnostic feature (a few words);
       the key measure (timing + one or two products or practices).【number】
    2. …and so on

    Keep each item to **two lines or less**; the whole survey up to about **1,600 characters**.
    If there are genuinely too many entries to fit, **say at the end how many were left out
    and offer to continue** — **never** silently list only part of them (the user will assume
    that is all there is). Include healthy entries as one line each (growing the crop well is
    itself part of disease prevention).

Language: English.

**Formatting (mandatory)**: the UI renders **only `**bold**`**; every other Markdown symbol is
shown literally.
- You may — and only may — use `**…**` to bold **disease names**, **product names** and
  **key timing**;
- **Do not** use `#`/`##` headings, `*italics*`, code spans, `[links]()`, `![images]()`,
  `>` quotes, tables or `---` rules;
- **Do not** put `**` immediately next to `【number】` (it runs together and looks broken);
- Separate paragraphs with a blank line; one point per paragraph."""

SYSTEM_PROMPTS = {'zh': SYSTEM_PROMPT_ZH, 'en': SYSTEM_PROMPT_EN}

# ============================================================================
# 用户消息模板与意图侧重
# ============================================================================
USER_TEMPLATES = {
    'zh': """{knowledge}

<question>
{question}
</question>

请依据上面的词条回答。{focus}""",
    'en': """{knowledge}

<question>
{question}
</question>

Answer using the entries above. {focus}""",
}

FOCUS_BY_INTENT = {
    'zh': {
        'symptom': '用户想知道怎么识别症状，重点讲症状特征与易混淆点。',
        'chemical': '用户关心用药，请把词条里的药剂、稀释倍数、安全间隔期、施药间隔完整给出，'
                    '并提醒轮换用药；若词条说明某药剂抗性高或已停用，必须明确说明。',
        'occurrence': '用户想知道发病原因与条件，重点讲发病规律与温湿度、传播途径。',
        'prevention': '用户想知道怎么预防，重点讲农业防治、生态防治、物理防治。',
        'care': '用户问的是作物健康管理，请按形态特征、生长条件、五类管理组织回答。',
        'general': '请按"结论 → 依据 → 防治建议 → 何时找人工"的结构回答。',
    },
    'en': {
        'symptom': 'The user wants to identify the disease: focus on symptom features and what it is easily confused with.',
        'chemical': 'The user asks about pesticides: give the product names, dilution ratios, '
                    'pre-harvest intervals and spray intervals exactly as in the entry, and mention '
                    'rotating modes of action. If the entry says a product has high resistance or '
                    'should be discontinued, state that clearly.',
        'occurrence': 'The user wants to know why it happens: focus on the disease cycle, temperature, '
                      'humidity and how it spreads.',
        'prevention': 'The user asks about prevention: focus on cultural, ecological and physical measures.',
        'care': 'The user asks about crop health management: organise the answer by morphology, '
                'growing conditions and the five care categories.',
        'general': 'Answer in the order: conclusion → evidence → measures → when to ask a human.',
    },
}

# ============================================================================
# 降级话术 —— **刻意不冒充 AI 回答**，要让用户知道这是词条原文
# ============================================================================
DEGRADE_TEXT = {
    'zh': {
        'no_llm': '（AI 助手暂时不可用，以下为该病害的档案原文，仅供参考）\n\n{body}',
        'no_source': ('本系统词条未收录该问题，建议咨询当地植保站。\n'
                      '（如需查看已收录的作物与病害，可在「病害百科」中浏览。）'),
        'sensitive': '您的问题包含不允许的词汇（{words}），请修改后重试。',
        'empty': '请先输入您的问题。',
        'too_long': '问题太长了（上限 {limit} 字），请精简后再问。',
        'rate_limited': '提问太频繁了（每分钟上限 {limit} 次），请稍等一下再问。',
        'session_full': ('这次会话已经攒了 {limit} 条消息，请新开会话继续问'
                         '（之前的问答还在「问答历史」里，随时能翻回去看）。'),
        'error': '（AI 助手暂时不可用：{reason}。以下为该病害的档案原文，仅供参考）\n\n{body}',
    },
    'en': {
        'no_llm': ('(The AI assistant is temporarily unavailable. The archive text below is shown '
                   'for reference only.)\n\n{body}'),
        'no_source': ('This topic is not covered by our entries; please consult your local plant '
                      'protection station.\n(You can browse the crops and diseases we do cover in '
                      'the Disease Encyclopedia.)'),
        'sensitive': 'Your question contains disallowed words ({words}). Please rephrase it and try again.',
        'empty': 'Please type your question first.',
        'too_long': 'The question is too long (limit {limit} characters). Please shorten it.',
        'rate_limited': 'Too many questions in a row (limit {limit} per minute). Please wait a moment.',
        'session_full': ('This conversation already holds {limit} messages — please start a new '
                         'conversation to keep asking (your earlier Q&A stays in “History”).'),
        'error': ('(The AI assistant is temporarily unavailable: {reason}. The archive text below '
                  'is shown for reference only.)\n\n{body}'),
    },
}


def degrade_text(key: str, lang: str = DEFAULT_LANG, **params) -> str:
    """取降级话术。键不存在时回落到中文（宁可给中文，也不要抛异常把接口弄挂）。"""
    table = DEGRADE_TEXT.get(normalize_lang(lang)) or DEGRADE_TEXT[DEFAULT_LANG]
    template = table.get(key) or DEGRADE_TEXT[DEFAULT_LANG].get(key, '')
    return template.format(**params) if params else template


#: 提示词版本：改了措辞就改它，便于事后区分"哪版提示词产出的答案"。
#: v2（第 197 批）加英文；v3（第 204 批）"控制篇幅 + 多作物只展开一个"；
#: v4（第 207 批）改成"每条都答但都简短" + "必须内联标 `【序号】`"；
#: v5（第 209 批）新增第 12 条"清点式问题要完整概览"；
#: v6（第 210 批）明确排版格式：只允许 `**加粗**`、禁止其他 Markdown、
#: 加粗与 `【序号】` 之间必须留空格；
#: **v7（第 211 批）第 11 条补"同一来源的连续句子只标一次"** ——
#: 起因是用户反馈"回答后面都多出【数字】"，而逐句标注让满屏都是序号。
#: **v8（第 212 批）把第 11 条改成一张"什么时候标 / 什么时候不标"的清单** ——
#: v7 那句"只在最后一句标一次"太含糊，实测密度不降反升（0.33 → 0.83 处/行）；
#: 现在明确"单来源时全篇只标一次、列表标在最后一条、多来源必须逐段标"，
#: 并在 `orchestrator._collapse_single_source()` 里做了兜底折叠。
#: **v9（第 228 批）messages 里开始带多轮历史**（措辞没改，但"模型看到什么"变了，
#: 所以版本也要变 —— 否则同一版本号下两种输入产出的答案无法区分）。
PROMPT_VERSION = 'v9-2026-10-28'


#: 多轮历史：单条消息最多带多少字（第 228 批）
HISTORY_MESSAGE_CHARS = 240
#: 多轮历史：整段历史最多带多少字（粗口径的 token 预算，中文约 1 字 ≈ 1 token）
HISTORY_TOTAL_CHARS = 1200


def prepare_history(history: list[dict] | None, *,
                    message_chars: int = HISTORY_MESSAGE_CHARS,
                    total_chars: int = HISTORY_TOTAL_CHARS) -> list[dict]:
    """把"原始历史"裁成能直接塞进 `messages` 的形状（第 228 批）。

    做三件事，顺序有意义：
      1. **只留 user / assistant**：system 由这里自己给，历史里混进 system 会让
         规则随着聊天被改写（提示词注入最省事的一条路）；
      2. 单条超长就截断（补 `…`）：上一轮的长回答没必要整段回灌给模型；
      3. 整段超预算时**从最旧的丢** —— 越近的上下文越相关，"上一句指代"几乎
         总是落在最后两三条上。

    返回按时间正序（老的在前），直接 `messages.extend(...)` 即可。
    """
    cleaned: list[dict] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get('role') or '').strip()
        if role not in ('user', 'assistant'):
            continue
        content = str(item.get('content') or '').strip()
        if not content:
            continue
        if message_chars and len(content) > message_chars:
            content = content[:message_chars].rstrip() + '…'
        cleaned.append({'role': role, 'content': content})

    if not total_chars:
        return cleaned

    kept: list[dict] = []
    used = 0
    for item in reversed(cleaned):
        used += len(item['content'])
        if kept and used > total_chars:
            break
        kept.append(item)
    kept.reverse()
    return kept


def build_messages(question: str, knowledge: str, intent: str = 'general',
                   lang: str = DEFAULT_LANG, history: list[dict] | None = None) -> list[dict]:
    """拼出 `messages`。`knowledge` 为空时要走降级（见 orchestrator），不在这里兜。

    第 228 批：`history` 是**最近几轮对话**（`[{'role','content'}, …]`，由
    `orchestrator._history_of()` 按预算裁好）。它插在 system 与当前提问之间，
    模型才能看懂"那它用什么药"指的是上一轮那个病。

    ⚠️ 为什么历史**不放 system**：system 是规则（"只能用下面的资料回答"），
       历史是对话内容。混在一起会让模型把"上一轮的回答"当成资料去引用，
       而引用校验只认本轮检索到的【序号】，结果就是答案里出现无效序号。
    """
    code = normalize_lang(lang)
    focus = (FOCUS_BY_INTENT.get(code) or FOCUS_BY_INTENT[DEFAULT_LANG]).get(
        intent, FOCUS_BY_INTENT[code]['general'])
    messages = [{'role': 'system', 'content': SYSTEM_PROMPTS[code]}]
    messages.extend(history or [])
    messages.append({'role': 'user', 'content': USER_TEMPLATES[code].format(
        knowledge=knowledge, question=question.strip(), focus=focus)})
    return messages


# ============================================================================
# 兼容旧调用点（第 193 批的代码与测试用的是这些常量名）
# ============================================================================
SYSTEM_PROMPT = SYSTEM_PROMPT_ZH
USER_TEMPLATE = USER_TEMPLATES['zh']
DEGRADE_NO_LLM = DEGRADE_TEXT['zh']['no_llm']
DEGRADE_NO_SOURCE = DEGRADE_TEXT['zh']['no_source']
DEGRADE_SENSITIVE = DEGRADE_TEXT['zh']['sensitive']
DEGRADE_EMPTY = DEGRADE_TEXT['zh']['empty']
DEGRADE_TOO_LONG = DEGRADE_TEXT['zh']['too_long']
DEGRADE_ERROR = DEGRADE_TEXT['zh']['error']
