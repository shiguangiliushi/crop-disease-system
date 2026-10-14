"""知识检索（第 193 批，K5）。

## 为什么先做关键词检索，而不是向量检索

38 条语料这个规模，向量检索**没有收益**：
  · 关键词/别名检索在"问某个已知病害"时准确率就是 100%（词条名精确命中）；
  · 向量要引入 embedding 模型（CPU 上 1~2 GB 依赖 + 推理延迟），换来的只是
    "同义改写"的召回 —— 而那类问题（"我的番茄叶子卷了"）需要的是**更厚的语料**，
    不是更花的检索。

所以 `search()` 的签名先定死，v2 换实现时调用方不用改（框架文档 P6）。

## 打分口径（可解释、可调）

每条命中给出 `score` 与 `why`，`why` 直接写"靠什么命中的"（词条名/别名/作物/正文），
这样"为什么答的是这一条"在日志里能复盘 —— 而不是一个无法解释的浮点数。

分数刻意做成**整数加权**而不是 TF-IDF：38 条语料里，可调权重比统计模型更实用，
且不会被长文本（化学防治 353 字）带偏。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import CropHealthProfile, PestInfo

#: 查询里的虚词/疑问词 —— 去掉后剩下的才是"实体词"
STOPWORDS = {
    '的', '了', '是', '在', '有', '和', '与', '及', '这', '那', '个', '我', '你', '他',
    '怎么', '怎样', '如何', '什么', '哪些', '哪个', '为什么', '多少', '多久', '几天',
    '请问', '一下', '可以', '能否', '需要', '应该', '要不要', '吗', '呢', '啊', '吧',
    '病', '病害', '虫子', '虫害', '这个', '这种', '我的', '我家',
}

#: 意图词 → 提示（用来告诉模型"用户到底想问哪一类"，影响提示词里的侧重）
INTENT_HINTS = {
    '症状': ('symptom', ('症状', '什么样', '长什么样', '表现', '识别', '怎么看', '斑', '霉', '枯')),
    '用药': ('chemical', ('打药', '用药', '喷什么', '什么药', '药剂', '农药', '防治', '治', '喷施', '浓度', '稀释')),
    '规律': ('occurrence', ('为什么', '原因', '发病', '规律', '条件', '什么时候', '天气', '温湿度')),
    '预防': ('prevention', ('预防', '防止', '避免', '提前', '防住', '怎么防')),
    '管理': ('care', ('管理', '栽培', '养护', '种植', '施肥', '浇水', '修剪')),
}

#: 作物别名 —— 用户口语与库中 `crop_type` 不一致时靠它兜住
CROP_ALIASES = {
    '西红柿': '番茄', '圣女果': '番茄', '小番茄': '番茄',
    '土豆': '马铃薯', '洋芋': '马铃薯',
    '辣子': '甜椒', '青椒': '甜椒', '菜椒': '甜椒', '灯笼椒': '甜椒', '辣椒': '甜椒',
    '苞米': '玉米', '棒子': '玉米',
    '提子': '葡萄',
    '柑子': '柑橘', '橘子': '柑橘', '橙子': '柑橘', '柚子': '柑橘',
    '地瓜': '马铃薯',
}


@dataclass
class Hit:
    """一条命中。`pest` 一定有；`profile` 只在健康词条上有。"""

    pest: PestInfo
    score: int = 0
    why: str = ''
    matched_terms: list[str] = field(default_factory=list)
    profile: CropHealthProfile | None = None
    is_healthy: bool = False


def _tokens(text: str) -> list[str]:
    """把查询切成候选词：中文按 2~4 字滑窗 + 英数词，去掉虚词。

    不做分词器依赖（jieba 会再加一个包），滑窗对这个规模够用：
    "番茄晚疫病怎么打药" → 番茄/茄晚/晚疫/疫病/怎么/打药 …
    其中"番茄""晚疫"能命中词条，"怎么"被虚词表去掉。
    """
    text = (text or '').strip().lower()
    if not text:
        return []
    tokens: list[str] = []
    # 英数串整体保留
    tokens += re.findall(r'[a-z0-9_]{2,}', text)
    # 中文连续段做 2~4 字滑窗
    for run in re.findall(r'[\u4e00-\u9fff]{2,}', text):
        for size in (2, 3, 4):
            for i in range(0, len(run) - size + 1):
                tokens.append(run[i:i + size])
    seen, result = set(), []
    for token in tokens:
        if token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def detect_intent(question: str) -> str:
    """粗判意图（symptom / chemical / occurrence / prevention / care / general）。"""
    text = (question or '')
    for _label, (code, keywords) in INTENT_HINTS.items():
        if any(word in text for word in keywords):
            return code
    return 'general'


def normalize_crops(question: str) -> list[str]:
    """查询里提到的作物（含别名归一）。"""
    text = (question or '')
    found = []
    for alias, canonical in CROP_ALIASES.items():
        if alias in text and canonical not in found:
            found.append(canonical)
    for crop in PestInfo.objects.values_list('crop_type', flat=True).distinct():
        if crop and crop in text and crop not in found:
            found.append(crop)
    return found


def search(question: str, *, pest_identifier: str = '', top_k: int = 5) -> list[Hit]:
    """检索最相关的词条。

    参数 `pest_identifier` 是"识别结果直接带过来的病害"（如 `tomato___late_blight`）——
    命中时**直接置顶**，因为那是模型刚判定的结果，比任何文本匹配都确定。
    """
    question = (question or '').strip()
    tokens = _tokens(question)
    crops = normalize_crops(question)

    # 识别结果直连：优先级最高
    anchor: PestInfo | None = None
    if pest_identifier:
        from ..pest_lookup import find_pest_info
        anchor, _strategy = find_pest_info(pest_identifier)
        if anchor is None:
            anchor = PestInfo.objects.filter(english_identifier=pest_identifier).first()

    hits: list[Hit] = []
    for pest in PestInfo.objects.all():
        score, why, matched = 0, [], []

        if anchor is not None and pest.pk == anchor.pk:
            score += 100
            why.append('识别结果直连')

        name = pest.name or ''
        name_hit = [t for t in tokens if t in name]
        if name_hit:
            score += 10 * len(name_hit) + len(max(name_hit, key=len))
            why.append(f'词条名命中（{"/".join(name_hit[:3])}）')
            matched += name_hit

        if pest.english_identifier and pest.english_identifier.lower() in question.lower():
            score += 30
            why.append('英文标识符命中')
            matched.append(pest.english_identifier)

        if pest.crop_type and pest.crop_type in question:
            score += 6
            why.append(f'作物命中（{pest.crop_type}）')
            matched.append(pest.crop_type)
        elif pest.crop_type and pest.crop_type in crops:
            score += 4
            why.append(f'作物（别名）命中（{pest.crop_type}）')

        # 正文命中：只做弱加权。长字段（化学防治 353 字）靠长度刷分是不对的，
        # 所以每个命中的词最多贡献 2 分，且整个正文字段封顶 8 分。
        body_score = 0
        for token in tokens:
            if len(token) < 2:
                continue
            if token in (pest.symptoms or ''):
                body_score += 1
                matched.append(token)
            if token in (pest.description or ''):
                body_score += 1
                matched.append(token)
            if body_score >= 8:
                break
        if body_score:
            score += body_score
            why.append(f'正文命中（{body_score} 处）')

        if score <= 0:
            continue
        hits.append(Hit(pest=pest, score=score, why='；'.join(why),
                        matched_terms=list(dict.fromkeys(matched)),
                        is_healthy=(pest.english_identifier or '').endswith('_healthy')))

    hits.sort(key=lambda h: (-h.score, h.pest.id))

    # ── 弱命中过滤（第 193 批实测后补）─────────────────────────────────────
    # 问题：「这个病用什么药？」配识别锚点时，除了锚点（score=100）还会捞出
    #       score=1 的"路人词条"（正文里恰好含"用药"两个字）。这些条目会：
    #         · 污染上下文（模型看到 4 条不相关词条，可能答错方向）；
    #         · 污染降级文本（没 AI 时用户会看到一堆无关病害的档案）。
    # 判据：保留锚点；其余条目要求 score ≥ 阈值的下限，且不低于最高分非锚点的 1/3。
    #       阈值取相对值而不是绝对值 —— 不同问法的分数尺度差很多
    #       （"番茄晚疫病怎么打药" 最高 104，"我的西红柿叶子卷了" 最高才 4）。
    floor = max(4, int(max((h.score for h in hits if h.score < 100), default=0) / 3))
    hits = [h for h in hits if h.score >= 100 or h.score >= floor][:max(1, top_k)]

    # 健康词条：把栽培档案一起带出来（助手要能回答"健康番茄该怎么管"）
    ids = [hit.pest.pk for hit in hits if hit.is_healthy]
    if ids:
        profiles = {p.pest_id: p for p in CropHealthProfile.objects.filter(pest_id__in=ids)}
        for hit in hits:
            if hit.is_healthy:
                hit.profile = profiles.get(hit.pest.pk)
    return hits
