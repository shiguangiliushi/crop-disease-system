"""
"模型类名 → 病害词条"的匹配（第 159 批）

## 这个模块解决什么

识别接口拿到的是 **AI 模型给出的类名**，界面要显示的是**病害词条的中文内容**
（名称、主要症状、防治建议）。这两者之间的匹配原来写在 `views.py` 里，而且是**两份**
（构建结果时一份、落库时一份），匹配规则只有一条"去掉空格后精确相等"。

于是当前模型（PlantVillage 风格类名 `Apple___Apple_scab`）与库里的
`apple_scab` **永远对不上** —— 后果是界面显示英文类名（`Apple   Apple Scab`，
三个空格就是 `_ → 空格` 留下的）、主要症状与防治建议全是占位文字，
而**管理后台里明明有内容**（第 159 批用户报的就是这个）。

## 匹配顺序（从强到弱，命中即返回，并把"命中方式"一起返回）

1. `english_identifier` **精确**相等（都规范化后）—— 最可靠；
2. `name_en` **精确**相等 —— 词条里写了英文名的情形；
3. **`english_identifier` 是类名的一部分**（取最长命中）——
   解决 `Apple___Apple_scab → apple_scab`、`Tomato___Spider_mites Two-spotted_spider_mite
   → tomato_two_spotted_spider_mite`、`Orange___Haunglongbing_(Citrus_greening)
   → citrus_greening` 这类"类名里多了作物名或括号注解"；
4. **`name_en` 是类名的一部分**（取最长命中）——
   解决 `Corn___Cercospora_leaf_spot Gray_leaf_spot → corn_gray_leaf_spot`
   （词条的 `name_en` 是 `Cercospora leaf spot`）；
5. 显式别名表 `ALIASES` —— 前四步都覆盖不到的少数情况，写在这里并配测试。

命中不了就返回 `None`，由调用方回落（并**记一条 warning 日志**，
把原始类名打出来 —— 这种"安静的降级"必须有痕迹，否则又会变成"后台有内容、界面却没有"）。

## 为什么不用数据库做模糊匹配

`PestInfo` 只有几十条，取回内存里比最直观、也最好测；
而且 `annotate(Replace(...))` 之类的写法在不同数据库上行为不一致（SQLite / PostgreSQL），
没必要为几十行数据引入这种依赖。
"""
from __future__ import annotations

import re

from .models import PestInfo

#: 类名/标识里的"非字母数字"一律当成分隔符（`___`、空格、`-`、`(`、`)`、`,` 都是）
_SEPARATOR = re.compile(r'[^0-9a-z]+')

def normalize(text: str | None) -> str:
    """规范化：小写 + 非字母数字折叠成单个下划线（`Apple___Apple_scab` → `apple_apple_scab`）"""
    if not text:
        return ''
    return _SEPARATOR.sub('_', str(text).lower()).strip('_')


#: 显式别名：`规范化后的模型类名 → english_identifier`
#: 前四条规则能覆盖的就不写进来（这一表越短越好维护）
ALIASES: dict[str, str] = {}

#: 作物别名：模型类名里的作物写法 → 词条里的作物写法
#:
#: `Squash___Powdery_mildew` 在词条里叫 `pumpkin_powdery_mildew`（南瓜），
#: 光靠字符串匹配对不上；`Pepper,_bell` 归一后是 `pepper_bell`，而词条前缀是 `pepper`
#: （后者能被"前缀取作物"自动覆盖，所以不必写在这里）。
CROP_ALIASES: dict[str, str] = {
    'squash': 'pumpkin',
    'bell_pepper': 'pepper',
}


def _crop_set(rows) -> set:
    """词条里出现过的作物前缀（从 `english_identifier` 的第一段取，动态得到，不写死）"""
    crops = set()
    for row in rows:
        identifier = normalize(row.english_identifier)
        if identifier:
            crops.add(identifier.split('_')[0])
    return crops


def _crop_of(key: str, crops: set) -> str:
    """
    从规范化类名里取"作物"。

    `pepper_bell_bacterial_spot` → `pepper`（前缀在已知作物集里）
    `squash_powdery_mildew` → `pumpkin`（先查别名表）
    """
    tokens = key.split('_')
    for size in (2, 1):                       # 先试两段（pepper_bell），再试一段
        prefix = '_'.join(tokens[:size])
        if prefix in crops:
            return prefix
        if prefix in CROP_ALIASES and CROP_ALIASES[prefix] in crops:
            return CROP_ALIASES[prefix]
    if tokens and tokens[0] in CROP_ALIASES:
        return CROP_ALIASES[tokens[0]]
    return ''


def _tokens(key: str) -> list:
    """把规范化后的字符串切成词元（丢掉空段）"""
    return [token for token in key.split('_') if token]


def _stem(token: str) -> str:
    """
    极轻量的词干化：只处理单复数（`mites` → `mite`）。

    PlantVillage 的类名写法很不一致（`Tomato___Spider_mites Two-spotted_spider_mite`
    前半用复数、后半用单数），不做这一步这条规则就漏掉它。
    """
    return token[:-1] if len(token) > 3 and token.endswith('s') else token


def find_pest_info(raw_identifier: str, extra_names: tuple = ()):
    """
    按类名找病害词条。

    :param raw_identifier: 模型给出的类名（如 `Apple___Apple_scab`）或任何英文名
    :param extra_names: 额外的候选写法（如模型文件里的 class name、用户传来的英文名）
    :returns: `(PestInfo 或 None, 命中方式说明)`

    ⚠️ 第 159 批的教训：第 ④⑤ 条规则（"包含于类名"）**必须限定在同一作物内**。
    第一版没限定，于是 `Pepper,_bell___healthy` 匹配到了**健康苹果**、
    `Squash___Powdery_mildew` 匹配到了**樱桃白粉病** ——
    因为库里好几条词条的 `name_en` 都叫 `Healthy` / `Powdery mildew`。
    **匹配错比匹配不上更糟**：界面会理直气壮地显示另一种病害的防治建议。
    """
    candidates = [raw_identifier, *extra_names]
    normalized = [normalize(item) for item in candidates if item]
    if not normalized:
        return None, '空类名'

    rows = list(PestInfo.objects.all())
    if not rows:
        return None, '病害库为空'

    crops = _crop_set(rows)
    # 预算好每行的两种写法
    table = [(row, normalize(row.english_identifier), normalize(row.name_en)) for row in rows]

    # ① 精确匹配 english_identifier
    for key in normalized:
        for row, identifier, _ in table:
            if identifier and identifier == key:
                return row, f'english_identifier 精确匹配（{row.english_identifier}）'

    # ② 精确匹配 name_en（同样要求唯一，避免通用英文名撞车）
    for key in normalized:
        hits = [row for row, _, name_en in table if name_en and name_en == key]
        if len(hits) == 1:
            return hits[0], f'name_en 精确匹配（{hits[0].name_en}）'

    # ②b 去掉所有下划线后相等（`AppleScab` / `apple scab` / `Apple Scab`）
    #
    # 老代码里那句 `disease_identifier.replace(' ', '')` 想处理的正是这种"连写"形态，
    # 但它拿去比的是**库里的** snake_case 值，所以从来没成功过。这里补成一条真正的规则。
    for key in normalized:
        squeezed = key.replace('_', '')
        hits = [row for row, identifier, _ in table
                if identifier and identifier.replace('_', '') == squeezed]
        if len(hits) == 1:
            return hits[0], f'去下划线后相等（{hits[0].english_identifier}）'

    # ③ 别名表
    for key in normalized:
        target = ALIASES.get(key)
        if target:
            for row, identifier, _ in table:
                if identifier == normalize(target):
                    return row, f'别名表命中（{key} → {target}）'

    # ④ 作物内"词条的词元 ⊆ 类名的词元"（不依赖 name_en —— 全新安装时词条里没有 name_en）
    #
    # 例：`Corn___Cercospora_leaf_spot Gray_leaf_spot` 与 `corn_gray_leaf_spot`
    # （双向都不"包含"，但词元完全覆盖）；
    # `Pepper,_bell___Bacterial_spot` 与 `pepper_bacterial_spot`；
    # `Squash___Powdery_mildew` 与 `pumpkin_powdery_mildew`（先把 squash 按别名当 pumpkin）。
    # 词元比较带一点单复数容忍（`mite` / `mites`），因为 PlantVillage 的写法很不一致。
    for key in normalized:
        crop = _crop_of(key, crops)
        label_tokens = {_stem(token) for token in _tokens(key)}
        if crop:
            # 作物别名统一：squash → pumpkin
            label_tokens |= {_stem(crop)}
        hits = []
        for row, identifier, _ in table:
            if not identifier or (crop and not identifier.startswith(f'{crop}_')):
                continue
            row_tokens = {_stem(token) for token in _tokens(identifier)}
            if row_tokens and row_tokens <= label_tokens:
                hits.append((len(row_tokens), row, identifier))
        if hits:
            hits.sort(key=lambda item: item[0], reverse=True)
            if len(hits) > 1 and hits[0][0] == hits[1][0]:
                return None, f'词元匹配歧义（{hits[0][2]} 与 {hits[1][2]}）'
            _, row, identifier = hits[0]
            return row, f'词元覆盖（{identifier} ⊆ {key}，作物 {crop or "未定"}）'

    # ⑤ english_identifier 是类名的一部分 —— 同样限定同一作物，取最长命中
    for key in normalized:
        crop = _crop_of(key, crops)
        hits = [(len(identifier), row, identifier) for row, identifier, _ in table
                if identifier and identifier in key
                and (not crop or identifier.startswith(f'{crop}_'))]
        if hits:
            # ⚠️ 只按长度排：元组里还有 PestInfo 对象，它不是可比较类型 ——
            # `hits.sort(reverse=True)` 在长度相同的两个候选上会抛 TypeError。
            hits.sort(key=lambda item: item[0], reverse=True)
            _, row, identifier = hits[0]
            return row, f'english_identifier 包含于类名（{identifier} ⊂ {key}，作物 {crop or "未定"}）'

    # ⑥ name_en 是类名的一部分 —— 同样限定作物，且**必须唯一**
    for key in normalized:
        crop = _crop_of(key, crops)
        hits = [(len(name_en), row, name_en) for row, _, name_en in table
                if name_en and name_en in key
                and (not crop or normalize(row.english_identifier).startswith(f'{crop}_'))]
        if hits:
            hits.sort(key=lambda item: item[0], reverse=True)
            if len(hits) > 1 and hits[0][0] == hits[1][0]:
                # 同样长（例如同一作物下两条都叫 "Bacterial spot"）→ 宁可不匹配
                return None, f'name_en 歧义（{hits[0][2]} 与 {hits[1][2]} 长度相同）'
            _, row, name_en = hits[0]
            return row, f'name_en 包含于类名（{name_en} ⊂ {key}，作物 {crop or "未定"}）'

    return None, f'没有匹配（类名 {raw_identifier!r}）'


def link_history(history, raw_identifier: str):
    """
    给一条识别记录补上病害词条关联（落库后调用）。

    与构建结果用的是**同一个** `find_pest_info` ——
    以前这两处各写一份匹配逻辑，规则一改就会打架。
    """
    pest_info, strategy = find_pest_info(raw_identifier)
    if pest_info and history.pest_info_id != pest_info.id:
        history.pest_info = pest_info
        history.save(update_fields=['pest_info'])
    return pest_info, strategy
