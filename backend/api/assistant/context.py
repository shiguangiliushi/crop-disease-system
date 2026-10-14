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


def build(hits: list[Hit], *, max_chars: int = 6000) -> BuiltContext:
    """把命中拼成 `<knowledge>` 块 + 引用列表。

    `max_chars` 是硬上限：化学防治单条最长 353 字，5 条命中就能到 2000+ 字，
    再加发病规律会撑大输入（费钱且容易让模型跑题）。超限时**按条目顺序截断**
    并在文本里留一行说明，而不是静默丢弃 —— 让"答案为什么没提某一点"可复盘。
    """
    result = BuiltContext()
    blocks: list[str] = []
    budget = max_chars

    for index, hit in enumerate(hits, start=1):
        pest = hit.pest
        label = pest.name or f'词条#{pest.id}'
        part: list[str] = [f'【{index}】{label}（作物：{pest.crop_type}）']
        if pest.scientific_name:
            # 学名是拉丁文但很短，保留原样（它是身份标识，不是"英文正文"）
            part.append(f'学名：{pest.scientific_name.split("（")[0].strip()}')

        cit_parts: list[str] = []
        if hit.is_healthy:
            profile = hit.profile
            if profile is not None:
                for title, attr in HEALTHY_SECTIONS:
                    value = _split_append_note(getattr(profile, attr, '') or '')
                    if value:
                        part.append(f'{title}：{value}')
                for title, attr in CARE_SECTIONS:
                    value = _split_append_note(getattr(profile, attr, '') or '')
                    if value:
                        part.append(f'{title}：{value}')
                if profile.scientific_name:
                    part.append(f'（该作物学名：{profile.scientific_name.split("（")[0].strip()}）')
            else:
                # 健康词条但没档案：只能说清"没有管理资料"，不能编
                part.append('（本条暂无栽培管理档案）')
        else:
            for title, attr in DISEASE_SECTIONS:
                value = _split_append_note(getattr(pest, attr, '') or '')
                if value:
                    part.append(f'{title}：{value}')
                    cit_parts.append(f'{title}：{value[:80]}')
            # 防治措施按类别给出：这是"能照做"的部分，必须进上下文
            for method in pest.prevention_methods.all().order_by('category'):
                value = _split_append_note(method.measure or '')
                if not value:
                    continue
                title = method.get_category_display()
                part.append(f'{title}：{value}')
                cit_parts.append(f'{title}：{value[:80]}')

        block = '\n'.join(part)
        if len(block) > budget:
            blocks.append(f'（以下条目因上下文长度上限被省略，共 {len(hits) - index + 1} 条）')
            break
        budget -= len(block)
        blocks.append(block)

        snippet = ' ｜ '.join(cit_parts)[:200] if cit_parts else (label)
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
