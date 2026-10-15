"""上下文组装（第 193 批，K5）—— 把检索到的词条拼成给模型看的 `<knowledge>` 块。

## 关于 `chinese_only()` 的存在理由（**曾经的误判，已更正**）

这个函数的注释最初写的是"K3 把英文拼进了 `symptoms` / `description`，必须切掉"。
**那个说法是错的**，实测数据里没有这回事：

    · 38 条词条的 `symptoms` / `description` 里**没有成段英文**（按"连续 40+ 字符
      且拉丁字母占比 >75%"扫描，命中 0 条）；
    · `symptoms_en` / `description_en` 仍是原有的 PlantVillage 摘要，未被改写。

当初误判的原因：中文行文里有**学名夹注**，例如
"病斑上散生黑色小粒点（分生孢子器 pycnidia）"、"急性发作（apoplexy）" ——
看到拉丁字母就以为"英文段被拼进来了"。实际它们是正文的一部分，**必须保留**。

所以这个函数现在的定位是**防御性措施**，不是对已知污染的修补：
它保证"万一将来英文字段被错误地并进主字段，也不会漏到提示词与引用片段里"。
判据写得很保守 —— 只在"整段几乎不含中文"时才截断，因此对学名夹注零副作用。

（保留而不是删掉的理由：它的成本是几次正则，而一旦真出现字段污染，
提示词与用户看到的引用片段会同时串味，排查成本远高于留着它。）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .retriever import Hit

#: 中文字符（判定"这段是不是中文"）
CJK = re.compile(r'[\u4e00-\u9fff]')
#: 拉丁单词（判定"这段是不是英文"）
LATIN_WORD = re.compile(r'[A-Za-z]{3,}')


def chinese_only(text: str) -> str:
    """从"中文段 + 空格 + 英文段"里只取中文段。

    判据：把文本按空行/句号切段后，**第一个以拉丁字母为主的段**之后的内容全部丢掉。
    这样处理的是"拼接"这一种形态，不会误伤正常的中文里夹的专业词
    （如 `Phytophthora infestans`，它出现在句子中间，不会自成一段）。
    """
    raw = (text or '').strip()
    if not raw:
        return ''
    # 如果整段几乎不含中文，说明这就是英文内容 —— 直接返回空，避免把英文喂给中文回答
    if not CJK.search(raw):
        return ''
    pieces = re.split(r'(?<=[。；！？.!?;])\s+|\n{2,}', raw)
    kept: list[str] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        latin_ratio = len(LATIN_WORD.findall(piece)) / max(1, len(piece.split()))
        if not CJK.search(piece) and latin_ratio > 0.4:
            break          # 从这里开始是英文段，后面全不要
        kept.append(piece)
    return ' '.join(kept).strip() or raw


def _split_append_note(text: str) -> str:
    """K3 的拼接痕迹：`…初侵染源。          Apple scab overwinters in fallen leaves.`

    上面 `chinese_only` 已能切掉；这里额外把切完残留的多余空白压平。
    """
    return re.sub(r'\s{2,}', ' ', chinese_only(text)).strip()


def field_text(value: str, lang: str = 'zh') -> str:
    """按语言取字段文本。

    ⚠️ 英文界面下**不能**再走 `chinese_only` —— 那个函数是给中文主字段用的
    （它会把成段英文切掉）。英文取自 `*_en` 字段，本身就该是英文，
    若为空则**回落中文原文**：宁可给用户看中文，也不要给一个空段落。
    """
    text = str(value or '').strip()
    if not text:
        return ''
    return re.sub(r'\s{2,}', ' ', text).strip() if lang == 'en' else _split_append_note(text)


@dataclass
class Citation:
    """引用来源。`snippet` 会展示给用户，所以必须是干净的中文片段。"""

    pest_id: int
    label: str
    snippet: str
    prevention_id: int | None = None

    def as_dict(self) -> dict:
        return {
            'pest_id': self.pest_id,
            'prevention_id': self.prevention_id,
            'label': self.label,
            'snippet': self.snippet,
        }


@dataclass
class BuiltContext:
    """组装结果。`text` 进提示词，`citations` 进接口响应。"""

    text: str = ''
    citations: list[Citation] = field(default_factory=list)
    used_labels: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


#: 维度 → 展示名（与校准版 JSON 的键名一致，便于对照）
DISEASE_SECTIONS = (
    ('症状描述', 'symptoms'),
    ('发病规律', 'description'),
)
HEALTHY_SECTIONS = (
    ('健康形态特征', 'morphology'),
    ('健康生长条件', 'growing_conditions'),
)
CARE_SECTIONS = (
    ('农业健康管理', 'care_agricultural'),
    ('化学保护', 'care_chemical'),
    ('生态健康管理', 'care_ecological'),
    ('物理保护', 'care_physical'),
    ('健康监测', 'care_monitoring'),
)

#: 英文展示名（第 197 批）。键与上面三张表一一对应；
#: `(*_en)` 后缀表示该维度在数据库里有独立的 `*_en` 字段（健康档案有，防治措施有）。
SECTION_LABELS_EN = {
    '症状描述': 'Symptoms',
    '发病规律': 'Disease cycle',
    '健康形态特征': 'Healthy morphology',
    '健康生长条件': 'Growing conditions',
    '农业健康管理': 'Cultural care',
    '化学保护': 'Chemical protection',
    '生态健康管理': 'Ecological care',
    '物理保护': 'Physical protection',
    '健康监测': 'Health monitoring',
    '农业防治': 'Cultural control',
    '化学防治': 'Chemical control',
    '生态防治': 'Ecological control',
    '物理防治': 'Physical control',
    '监测预警': 'Monitoring and forecasting',
}

#: 防治类别代码 → 英文展示名（`PreventionMethod.get_category_display()` 只有中文）
PREVENTION_LABELS_EN = {
    'AGRICULTURAL': 'Cultural control',
    'CHEMICAL': 'Chemical control',
    'ECOLOGICAL': 'Ecological control',
    'PHYSICAL': 'Physical control',
    'MONITORING': 'Monitoring and forecasting',
}

#: 词条头部与说明的英文（降级文本要用，不能中英混排）
LABELS_EN = {
    'crop': 'Crop',
    'scientific_name': 'Scientific name',
    'no_profile': '(no cultivation profile for this entry yet)',
}


def section_label(zh_label: str, lang: str) -> str:
    return SECTION_LABELS_EN.get(zh_label, zh_label) if lang == 'en' else zh_label


def _localized_pair(item, zh_attr: str, en_attr: str, lang: str) -> str:
    """按语言取一对字段（如 `symptoms` / `symptoms_en`）。

    英文优先取 `*_en`；**为空就回落中文**并加一句标注 —— 让用户知道这段是没有译文的，
    而不是以为系统答错了语言。这比"显示空白"或"静默给中文"都更诚实。
    """
    if lang == 'en':
        en_value = field_text(getattr(item, en_attr, '') or '', 'en')
        if en_value:
            return en_value
        zh_value = field_text(getattr(item, zh_attr, '') or '', 'en')
        return zh_value
    return field_text(getattr(item, zh_attr, '') or '', 'zh')


def _disease_en_attrs(attr: str) -> str:
    """`symptoms` → `symptoms_en`（第 197 批：英文优先取 `*_en` 字段）。"""
    return f'{attr}_en'


def _condensed_entry(pest, hit, head: str, lang: str) -> str:
    """把一条词条压缩成"够列清单"的两三行（第 209 批加）。

    ## 为什么要它

    `build()` 的预算装不下全部命中时，原来直接 `break` —— 后面的条目**整块消失**，
    于是"苹果跟葡萄的所有病害"永远只能答出前 4 条（8 条档案 ≈ 9 450 字 > 6 000 字预算）。
    清点式问题要的是"**都有哪些**"，不是"某一条的全部细节"，
    所以给每条保留最核心的两项就足够模型列出完整清单。

    ## 取什么

    - 疾病条目：`症状描述`（识别用）+ 第一条防治措施（能照做的最小信息）；
    - 健康条目：`健康生长条件` + 第一条栽培管理。
      健康条目在"某作物都有哪些"里必须**占一行** —— 种好它本身就是防病的一部分，
      漏掉会让用户觉得清单少了东西。
    """
    english = lang == 'en'
    sep = ': ' if english else '：'
    lines = [head]
    first_ok = False  # 只取第一条措施，避免又变成全文

    if hit.is_healthy and hit.profile is not None:
        for title, attr in HEALTHY_SECTIONS + CARE_SECTIONS:
            value = _localized_pair(hit.profile, attr, f'{attr}_en', lang)
            if not value:
                continue
            if not first_ok or title in ('健康生长条件', '农业健康管理'):
                shown = section_label(title, lang) if english else title
                lines.append(f'{shown}{sep}{value[:120]}')
                first_ok = True
            if len(lines) >= 3:
                break
    else:
        symptoms = _localized_pair(pest, 'symptoms', _disease_en_attrs('symptoms'), lang)
        if symptoms:
            shown = section_label('症状描述', lang) if english else '症状描述'
            lines.append(f'{shown}{sep}{symptoms[:120]}')
        for method in pest.prevention_methods.all().order_by('category'):
            en_value = field_text(method.measure_en or '', 'en')
            zh_value = field_text(method.measure or '', 'zh')
            value = (en_value or zh_value) if english else zh_value
            if not value:
                continue
            title = (PREVENTION_LABELS_EN.get(method.category, method.category) if english
                     else method.get_category_display())
            lines.append(f'{title}{sep}{value[:120]}')
            break  # 只要一条措施
    return '\n'.join(lines)


def build(hits: list[Hit], *, max_chars: int = 9000, lang: str = 'zh') -> BuiltContext:
    """把命中拼成 `<knowledge>` 块 + 引用列表。

    `max_chars` 是硬上限：化学防治单条最长 353 字，5 条命中就能到 2000+ 字，
    再加发病规律会撑大输入（费钱且容易让模型跑题）。
    超限时**不再丢弃条目**，而是把装不下的条目改成"精简版"（见 `_condensed_entry`）——
    第 209 批的修正：原来直接 `break`，导致"按作物清点"类问题只能答出前几条。
    真实清点需求是 8 条（苹果 4 + 葡萄 4）≈ 9 450 字，所以预算从 6 000 提到 9 000。

    `lang='en'` 时（第 197 批）：维度名与防治类别名换成英文，字段优先取 `*_en`，
    **该字段为空则回落中文原文** —— 宁可让用户看到中文，也不要给一个空段落。
    西文里的分隔符也跟着换（`（作物：…）` → `(Crop: …)`），否则会是中英混排。
    """
    english = lang == 'en'
    result = BuiltContext()
    blocks: list[str] = []
    budget = max_chars

    def wrap(text: str) -> str:
        return f'({text})' if english else f'（{text}）'

    for index, hit in enumerate(hits, start=1):
        pest = hit.pest
        label = pest.name or ('entry #' if english else '词条#') + str(pest.id)
        head = (f'[{index}] {label} (Crop: {pest.crop_type_en or pest.crop_type})' if english
                else f'【{index}】{label}（作物：{pest.crop_type}）')
        part: list[str] = [head]
        if pest.scientific_name:
            # 学名是拉丁文、不分语言，保留原样（它是身份标识，不是"英文正文"）
            latin = pest.scientific_name.split('（')[0].strip()
            part.append(f'{LABELS_EN["scientific_name"] if english else "学名"}：{latin}')

        cit_parts: list[str] = []
        if hit.is_healthy:
            profile = hit.profile
            if profile is not None:
                for title, attr in HEALTHY_SECTIONS + CARE_SECTIONS:
                    value = _localized_pair(profile, attr, f'{attr}_en', lang)
                    if not value:
                        continue
                    shown = section_label(title, lang) if english else title
                    part.append(f'{shown}: {value}' if english else f'{shown}：{value}')
                    # ⚠️ 第 209 批补：健康条目**从来没往 `cit_parts` 里写过**，
                    #    于是界面上"来源"里健康条目的摘要只剩名字（"健康苹果"四个字）。
                    #    疾病条目一直有摘要、健康条目没有 —— 纯属漏写，不是有意。
                    cit_parts.append(f'{shown}{": " if english else "："}{value[:80]}')
                if profile.scientific_name:
                    latin = profile.scientific_name.split('（')[0].strip()
                    part.append(wrap(f'this crop: {latin}' if english else f'该作物学名：{latin}'))
            else:
                # 健康词条但没档案：只能说清"没有管理资料"，不能编
                part.append(wrap('no cultivation profile for this entry' if english
                                 else '本条暂无栽培管理档案'))
        else:
            for title, attr in DISEASE_SECTIONS:
                value = _localized_pair(pest, attr, _disease_en_attrs(attr), lang)
                if value:
                    shown = section_label(title, lang) if english else title
                    sep = ': ' if english else '：'
                    part.append(f'{shown}{sep}{value}')
                    cit_parts.append(f'{shown}{sep}{value[:80]}')
            # 防治措施按类别给出：这是"能照做"的部分，必须进上下文
            for method in pest.prevention_methods.all().order_by('category'):
                en_value = field_text(method.measure_en or '', 'en')
                zh_value = field_text(method.measure or '', 'zh')
                value = ((en_value or zh_value) if english else zh_value)
                if not value:
                    continue
                title = (PREVENTION_LABELS_EN.get(method.category, method.category) if english
                         else method.get_category_display())
                sep = ': ' if english else '：'
                part.append(f'{title}{sep}{value}')
                cit_parts.append(f'{title}{sep}{value[:80]}')

        block = '\n'.join(part)
        if len(block) > budget:
            # ⚠️ 第 209 批：这里原来是 `break` —— **把剩下的条目整块丢掉**，
            #    只留一行"共 N 条被省略"。后果是"清点式"问题（"苹果跟葡萄的所有病害"）
            #    永远答不全：8 条档案约 9 450 字、预算 6 000 字，于是只有前 4 条进上下文，
            #    模型**看不到**另外 4 条 —— 无论提示词怎么写都列不全。
            #    而且引用也跟着只有 4 条（用户看到的"来源"比实际条数少）。
            #
            #    现在的做法：**预算内先给全文，装不下的条目改成"简短但一条不落"**。
            #    清点式问题要的是"都有哪些病"，不是"某一条的全部细节" ——
            #    每条给"症状要点 + 一条最关键措施"就够模型列出完整清单，
            #    而且这几条的 snippet 也用这段精简文本（**展示与依据一致**）。
            short = _condensed_entry(pest, hit, head, lang)
            if len(short) <= budget:
                block = short
            elif blocks:
                # 连精简都放不下：到此为止，并**明确说清**省略了几条（不许静默）
                omitted = len(hits) - index + 1
                blocks.append(
                    f'({omitted} more entries omitted: context length limit)' if english
                    else f'（以下条目因上下文长度上限被省略，共 {omitted} 条）')
                break
            else:
                # 第一条就超预算（预算被调得极小）：保留原文，不要交白卷
                pass
        budget -= len(block)
        blocks.append(block)

        # 精简过的条目：引用摘要用同一段精简文本，避免"依据"与"展示"两张皮
        if block.startswith(head) and len(block) < len('\n'.join(part)):
            cit_parts = [block[len(head):].strip()]
        joiner = ' | ' if english else ' ｜ '
        snippet = joiner.join(cit_parts)[:200] if cit_parts else label
        result.citations.append(Citation(
            pest_id=pest.pk,
            label=label,
            snippet=snippet,
            prevention_id=None,
        ))
        result.used_labels.append(label)

    if blocks:
        result.text = '<knowledge>\n' + '\n\n'.join(blocks) + '\n</knowledge>'
    return result
