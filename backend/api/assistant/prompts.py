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

回答结构（简洁，不要长篇大论）：
- 先给结论（这是什么 / 该怎么办）
- 再给依据（症状特征、发病条件）
- 再给措施（按农业/化学/生态/物理/监测分类，与词条一致）
- 最后说明何时需要找人工（如"发病严重或无法判断时建议咨询当地植保站"）

语言：中文。不要输出 Markdown 表格；用短段落和编号列表。"""

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

Structure (keep it short):
- conclusion first (what this is / what to do)
- then the evidence (symptoms, conditions favouring the disease)
- then the measures, grouped as in the entry (cultural / chemical / ecological / physical / monitoring)
- finally say when to ask a human (e.g. severe outbreak or uncertain diagnosis → local plant protection station)

Language: English. No Markdown tables; use short paragraphs and numbered lists."""

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
#: 第 197 批加英文时升到 v2 —— 同一批数据在 v1/v2 下的答案不具备可比性。
PROMPT_VERSION = 'v2-2026-10-15'


def build_messages(question: str, knowledge: str, intent: str = 'general',
                   lang: str = DEFAULT_LANG) -> list[dict]:
    """拼出 `messages`。`knowledge` 为空时要走降级（见 orchestrator），不在这里兜。"""
    code = normalize_lang(lang)
    focus = (FOCUS_BY_INTENT.get(code) or FOCUS_BY_INTENT[DEFAULT_LANG]).get(
        intent, FOCUS_BY_INTENT[code]['general'])
    return [
        {'role': 'system', 'content': SYSTEM_PROMPTS[code]},
        {'role': 'user', 'content': USER_TEMPLATES[code].format(
            knowledge=knowledge, question=question.strip(), focus=focus)},
    ]


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
