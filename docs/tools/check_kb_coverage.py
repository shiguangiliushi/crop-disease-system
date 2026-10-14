"""模型类名 ↔ PestInfo 词条 ↔ 校准版知识库 的**三方覆盖核对**。

## 为什么必须用显式映射表，而不是"英文词元模糊匹配"

这个脚本的前身用模糊匹配算覆盖率，**连续两次算错**，两次都得出错误结论：

  ① 第一次：`Apple___Apple_scab` 这类带 `___` 的类名没被识别，算出"11 个类无词条"；
  ② 第二次：把 `Squash___Powdery_mildew` 判成"库里没有的新病害"
     （其实库里叫 `pumpkin_powdery_mildew`，南瓜白粉病，只是 PlantVillage 用了 Squash 这个词），
     同时**漏掉** `Orange___Haunglongbing_(Citrus_greening)` —— orange 与 citrus
     没有共同词元，模糊匹配**必然**失败，而它恰恰是正常有词条的一类。

最后由这两个错误合成了"13 个模型类目无知识库内容"的结论，并写进了文档。
实测正确结果是 **38/38 全覆盖、0 个类缺词条**。

结论：**覆盖率不能靠模糊匹配算**。`MAPPING` 就是那张显式表 ——
人一眼能核对对错，脚本能重复验证（改错了立刻报出来）。

## 用法

    python docs/tools/check_kb_coverage.py

退出码：0 = 覆盖核对通过；1 = 有缺词条 / 映射写错 / 出现未映射的词条。
只依赖标准库，用系统 python 即可（不需要 backend/venv）。
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AI_SERVICE = ROOT / "backend" / "api" / "ai_service.py"
DB = ROOT / "backend" / "db.sqlite3"
KB = ROOT / "docs" / "knowledge_base" / "作物病害知识库_校准版.json"

#: 模型类名 → 库中 `english_identifier`。「说明」列只写"为什么是这个 identifier"，供人核对。
MAPPING: dict[str, tuple[str, str]] = {
    # ── 苹果 ──────────────────────────────────────────────────────────────
    "Apple___Apple_scab": ("apple_scab", "库名 apple_scab（类名里 apple 重复了一次）"),
    "Apple___Black_rot": ("apple_black_rot", ""),
    "Apple___Cedar_apple_rust": ("apple_cedar_apple_rust", ""),
    "Apple___healthy": ("apple_healthy", ""),
    # ── 蓝莓 / 樱桃 ───────────────────────────────────────────────────────
    "Blueberry___healthy": ("blueberry_healthy", ""),
    "Cherry___healthy": ("cherry_healthy", ""),
    "Cherry___Powdery_mildew": ("cherry_powdery_mildew", ""),
    # ── 玉米 ──────────────────────────────────────────────────────────────
    "Corn___Cercospora_leaf_spot Gray_leaf_spot": ("corn_gray_leaf_spot", "类名并列两个病名，库取 gray_leaf_spot"),
    "Corn___Common_rust": ("corn_common_rust", ""),
    "Corn___healthy": ("corn_healthy", ""),
    "Corn___Northern_Leaf_Blight": ("corn_northern_leaf_blight", ""),
    # ── 葡萄 ──────────────────────────────────────────────────────────────
    "Grape___Black_rot": ("grape_black_rot", ""),
    "Grape___Esca_(Black_Measles)": ("grape_black_measles", "库名 black_measles"),
    "Grape___healthy": ("grape_healthy", ""),
    "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)": ("grape_leaf_blight", ""),
    # ── 柑橘 ──────────────────────────────────────────────────────────────
    "Orange___Haunglongbing_(Citrus_greening)": ("citrus_greening", "orange 与 citrus 无共同词元，模糊匹配会漏掉它"),
    # ── 桃 ────────────────────────────────────────────────────────────────
    "Peach___Bacterial_spot": ("peach_bacterial_spot", ""),
    "Peach___healthy": ("peach_healthy", "库中文名「健康桃」，校准版写「健康桃子」→ 见 NAME_ALIAS"),
    # ── 甜椒（类名里带逗号，别按逗号切分）──────────────────────────────────
    "Pepper,_bell___Bacterial_spot": ("pepper_bacterial_spot", ""),
    "Pepper,_bell___healthy": ("pepper_healthy", ""),
    # ── 马铃薯 ────────────────────────────────────────────────────────────
    "Potato___Early_blight": ("potato_early_blight", ""),
    "Potato___healthy": ("potato_healthy", ""),
    "Potato___Late_blight": ("potato_late_blight", ""),
    # ── 树莓 / 大豆 / 南瓜 ────────────────────────────────────────────────
    "Raspberry___healthy": ("raspberry_healthy", ""),
    "Soybean___healthy": ("soybean_healthy", ""),
    "Squash___Powdery_mildew": ("pumpkin_powdery_mildew", "数据集写 Squash，库里写 pumpkin（同一种病：南瓜白粉病）"),
    # ── 草莓 ──────────────────────────────────────────────────────────────
    "Strawberry___healthy": ("strawberry_healthy", ""),
    "Strawberry___Leaf_scorch": ("strawberry_leaf_scorch", ""),
    # ── 番茄 ──────────────────────────────────────────────────────────────
    "Tomato___Bacterial_spot": ("tomato_bacterial_spot", ""),
    "Tomato___Early_blight": ("tomato_early_blight", ""),
    "Tomato___healthy": ("tomato_healthy", ""),
    "Tomato___Late_blight": ("tomato_late_blight", ""),
    "Tomato___Leaf_Mold": ("tomato_leaf_mold", ""),
    "Tomato___Septoria_leaf_spot": ("tomato_septoria_leaf_spot", ""),
    "Tomato___Spider_mites Two-spotted_spider_mite": ("tomato_two_spotted_spider_mite", ""),
    "Tomato___Target_Spot": ("tomato_target_spot", "库中文名「番茄靶斑病」，校准版写「番茄斑靶病」→ 见 NAME_ALIAS"),
    "Tomato___Tomato_mosaic_virus": ("tomato_mosaic_virus", ""),
    "Tomato___Tomato_Yellow_Leaf_Curl_Virus": ("tomato_yellow_leaf_curl_virus", ""),
}

#: 校准版中文名 → 库中中文名。**只有这两条不一致**，必须显式列出。
#: ⚠️ 方向是「校准版 → 库」；判断时要**反查**（见 KB_NAME_OF），
#: 写反了这两条会永远报"校准版无内容"——第一版就是这么错的。
NAME_ALIAS: dict[str, str] = {
    "番茄斑靶病": "番茄靶斑病",
    "健康桃子": "健康桃",
}

#: 库中中文名 → 校准版中文名（由 NAME_ALIAS 反转，避免两处手写不同步）
KB_NAME_OF: dict[str, str] = {db: kb for kb, db in NAME_ALIAS.items()}

#: 有词条、但不属于模型任何一类的词条（识别永远不命中，但百科/助手按名仍可检索到）
KNOWN_EXTRA_PEST = {"pumpkin_powdery_mildew"}


def load_model_classes() -> list[str]:
    """从 ai_service.py 读 class_names（不 import，避免加载 torch）。"""
    src = AI_SERVICE.read_text(encoding="utf-8")
    block = re.search(r"class_names\s*=\s*\[(.*?)\]", src, re.S)
    if not block:
        raise SystemExit("读不到 class_names，检查 backend/api/ai_service.py")
    return re.findall(r"'([^']+)'", block.group(1))


def main() -> int:
    classes = load_model_classes()
    conn = sqlite3.connect(DB)
    pests = {i: n for i, n in conn.execute("select english_identifier, name from api_pestinfo")}
    kb_names = {r["name"] for r in json.loads(KB.read_text(encoding="utf-8"))["records"]}

    problems: list[str] = []
    covered = aliased = 0
    print(f"模型类名 {len(classes)} 个 · 库中词条 {len(pests)} 个 · 校准版 {len(kb_names)} 条")
    print("=" * 92)

    for cls in classes:
        entry = MAPPING.get(cls)
        if entry is None:
            problems.append(f"类名不在映射表里：{cls}")
            print(f"  [!!] {cls:<46} 映射表里没有这一条")
            continue
        ident, _note = entry
        if ident not in pests:
            problems.append(f"映射的 identifier 在库里不存在：{cls} -> {ident}")
            print(f"  [!!] {cls:<46} -> {ident} 在库里不存在")
            continue
        cn = pests[ident]
        kb_name = KB_NAME_OF.get(cn, cn)
        if cn in kb_names:
            covered += 1
        elif kb_name in kb_names:
            aliased += 1
            print(f"  [别名] {cls:<46} 库「{cn}」→ 校准版「{kb_name}」")
        else:
            problems.append(f"校准版无内容：{cls} -> {cn}")
            print(f"  [无内容] {cls:<46} 词条={cn}，校准版里找不到")

    # 反向检查 ①：映射表里有没有模型不存在的类名（防止表写多了）
    for cls in MAPPING:
        if cls not in classes:
            problems.append(f"映射表多出类名（模型里没有）：{cls}")

    # 反向检查 ②：库里有没有完全没被映射到的词条
    mapped_idents = {i for i, _n in MAPPING.values()}
    unmapped = sorted(set(pests) - mapped_idents)
    print()
    print(f"覆盖：直接命中 {covered} 类 + 靠别名对齐 {aliased} 类 = {covered + aliased} / {len(classes)}")
    print(f"库中未被任何模型类映射的词条：{len(unmapped)} 条 -> {[pests[i] for i in unmapped]}")
    for ident in unmapped:
        if ident not in KNOWN_EXTRA_PEST:
            problems.append(f"未映射词条（且不在已知豁免名单 KNOWN_EXTRA_PEST 里）：{ident}")

    print()
    if problems:
        print(f"发现 {len(problems)} 个问题：")
        for item in problems:
            print("   -", item)
        return 1
    print("✅ 覆盖核对通过：每个模型类都有对应词条，且校准版都有内容")
    return 0


if __name__ == "__main__":
    sys.exit(main())
