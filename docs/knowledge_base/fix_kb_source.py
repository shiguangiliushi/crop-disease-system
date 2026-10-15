"""按数据集类目表修正三处源数据（第 199 批）。

## 修正依据

系统数据源 `D:\\新建文件夹\\Plant_leave_diseases_dataset_with_augmentation` 是模型训练集，
它的 `class_mapping.txt` 是**权威类目表**：

```
29. Tomato___Bacterial_spot        - 番茄细菌性斑点病
22. Pepper,_bell___Bacterial_spot  - 甜椒细菌性斑点病
13. Peach___Bacterial_spot         - 桃细菌性斑点病
```

`Bacterial spot` 的病原是 **Xanthomonas**；而校准版给 `番茄细菌性斑点病` 配的病原是
**Pseudomonas syringae pv. tomato**（那引起的是 bacterial **speck**，中文"斑疹病"，
是**另一种病**）。也就是说：**名称与模型类目一致（对），出错的是病原与正文**。

推论链：
  ① 模型类目 = spot（数据集的 2127 张图归属此类）；
  ② spot 的病原 = Xanthomonas（同项目**甜椒那条**已校准）；
  ③ 番茄那条正文却在描述 speck（"不隆起""直径1-3mm""prefer 16-24℃"）；
  ④ 甜椒那条写 spot **在辣椒上**，番茄那条却写 speck"**不侵害辣椒**" —— 两条互斥。

所以把番茄那条**改回 spot**，且**事实全部取自同项目已校准的甜椒记录**，不自由发挥。

## 三处改动

| # | 记录 | 改动 |
|---|---|---|
| 1 | 番茄花叶病毒 | `寄主植物田间分值` → `…病株`（错字） |
| 2 | 番茄细菌性斑点病 | 学名 + 2 个维度 + 1 处交叉引用：由 speck 改回 spot |
| 3 | 健康葡萄 | `排水转渍` → `排水排渍`（错字） |

用法：`python fix_kb_source.py --dry-run`（默认）/ `--apply`
改完必须接着跑：`load_kb --apply` 与 `apply_kb_en.py`（中文源与英文译稿不能脱节）。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys

KB = pathlib.Path(r"D:\新建文件夹\crop-disease-system\docs\knowledge_base")
JSON_PATH = KB / "作物病害知识库_校准版.json"
MD_PATH = KB / "作物病害知识库_校准版.md"

# ---------------------------------------------------------------------------
# 改动 2：番茄细菌性斑点病 —— 由 speck 改回 spot
# 事实来源：同项目 `甜椒细菌性斑点病` 记录（已校准）与数据集类目表
# ---------------------------------------------------------------------------
SCIENTIFIC_OLD = "Pseudomonas syringae pv. tomato (Okabe) Young, Dye & Wilkie"
SCIENTIFIC_NEW = (
    "Xanthomonas euvesicatoria（旧分类名 X. axonopodis pv. vesicatoria；"
    "番茄细菌性斑点病旧称 X. campestris pv. vesicatoria），"
    "黄单胞杆菌属，革兰氏阴性细菌；区别于番茄细菌性斑疹病"
    "（bacterial speck, Pseudomonas syringae pv. tomato，病斑更小、不隆起）"
)

SYMPTOM_OLD_PREFIX = "主要危害叶片，亦侵害茎和果实。"
SYMPTOM_NEW = (
    "主要危害叶片、茎和果实。叶片初现水渍状黄绿色小圆点，后扩大为不规则形至角形坏死斑，"
    "直径1-4mm（较斑疹病大），中央淡褐色稍凹陷，边缘暗褐色略隆起，"
    "病斑粗糙呈疮痂状（木栓化隆起），周围有黄色晕圈；区别于番茄细菌性斑疹病"
    "（bacterial speck, Pseudomonas syringae pv. tomato）：斑疹病病斑极小（1-3mm）、"
    "不隆起、果实上为微小黑点而不粗糙开裂。严重时多个病斑融合成不规则枯死大斑，"
    "叶片变黄、干枯脱落。茎上初生水渍状不规则条斑，后木栓化隆起、纵裂呈疮痂状。"
    "青果病斑初为黑色或暗褐色隆起小点，扩大为1-3mm圆形或长圆形黑色疮痂状病斑，边缘有裂口。"
)

CAUSE_OLD_PREFIX = "病原为假单胞杆菌属细菌（革兰氏阴性），"
CAUSE_NEW = (
    "病原为黄单胞杆菌属细菌（Xanthomonas euvesicatoria 等，革兰氏阴性），"
    "可侵染番茄与辣椒等茄科作物；在种子表面和内部越冬，种子带菌是最主要初侵染源，"
    "也可在病残体和土壤中存活。病菌借雨水反溅、风雨、灌溉水和农事操作传播，"
    "从气孔、皮孔或伤口侵入。高温高湿（气温25-30℃）、多雨大风、叶面结露时间长时发病重；"
    "连作田、排水不良、偏施氮肥的田块发病重；保护地内通风不良时发病重。"
)

MONITOR_OLD = "④ 注意与bacterial spot鉴别，必要时采样送检。"
MONITOR_NEW = "④ 注意与番茄细菌性斑疹病（bacterial speck）鉴别，必要时采样送检。"

# ---------------------------------------------------------------------------
# 改动 1 / 3：错字
# ---------------------------------------------------------------------------
TYPO_FIXES = [
    ("寄主植物田间分值和烟草制品是重要毒源", "寄主植物田间病株和烟草制品是重要毒源"),
    ("雨季及时排水转渍", "雨季及时排水排渍"),
]


def patch_record(records, name, field, old_startswith=None, old_exact=None, new=None):
    """按记录名与维度名做**精确**替换，返回 (是否改动, 旧值, 新值)。

    刻意要求 `old_startswith` 或 `old_exact` 命中，避免"看起来差不多就替换" ——
    文本里只要有一处对不上，就该报错让人看，而不是改出个半截东西。
    """
    for rec in records:
        if rec.get("name") != name:
            continue
        container = rec["dimensions"] if field in rec.get("dimensions", {}) else rec
        current = container.get(field, "")
        if old_exact is not None:
            if current != old_exact:
                raise SystemExit(f'{name}.{field} 与预期不符：\n  预期 {old_exact[:60]!r}\n  实际 {current[:60]!r}')
            container[field] = new
            return True, current, new
        if old_startswith is not None:
            if not current.startswith(old_startswith):
                raise SystemExit(f'{name}.{field} 开头与预期不符：\n  预期以 {old_startswith[:40]!r} 开头\n'
                                 f'  实际 {current[:60]!r}')
            container[field] = new
            return True, current, new
    raise SystemExit(f'找不到记录 {name} 的字段 {field}')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="真正写入（默认只预览）")
    args = parser.parse_args()

    raw_json = JSON_PATH.read_text(encoding="utf-8")
    raw_md = MD_PATH.read_text(encoding="utf-8")
    json_lines_before = raw_json.count("\n") + 1

    changes = []

    # ⚠️ 顺序很重要：**先改错字，再解析 JSON**。
    #    第一版反过来 —— 先 json.loads 再对 raw_json 做替换，
    #    结果 `data`（也就是真正写出去的对象）里根本没有错字修复，
    #    只有 raw_json 变量变了，而它随后被丢弃。**这种错会静默丢改动。**
    for old, new in TYPO_FIXES:
        for label, text in (("JSON", raw_json), ("MD", raw_md)):
            count = text.count(old)
            if count != 1:
                raise SystemExit(f'错字「{old}」在 {label} 里出现 {count} 次（预期 1 次）—— 需人工确认')
            changes.append((f'错字 → 「{new[-12:]}」', label, count))
        raw_json = raw_json.replace(old, new)
        raw_md = raw_md.replace(old, new)

    data = json.loads(raw_json)   # 解析的是"错字已修"的文本

    # ── 改动 2：番茄细菌性斑点病（结构字段 + 维度）──
    for rec in data["records"]:
        if rec.get("name") != "番茄细菌性斑点病":
            continue
        if rec.get("scientific_name") != SCIENTIFIC_OLD:
            raise SystemExit(f'学名与预期不符：{rec.get("scientific_name")!r}')
        rec["scientific_name"] = SCIENTIFIC_NEW
        break
    else:
        raise SystemExit("找不到 番茄细菌性斑点病 记录")

    for field, kwargs in (
        ("症状描述", {"old_startswith": SYMPTOM_OLD_PREFIX, "new": SYMPTOM_NEW}),
        ("发病规律", {"old_startswith": CAUSE_OLD_PREFIX, "new": CAUSE_NEW}),
        ("监测预警", {"old_exact": "① 定植后定期调查叶片，初见暗色小点即喷药；"
                                  "② 冷凉多雨（16-24℃、连续降雨）天气来临前预防性喷药；"
                                  "③ 雨后及时检查病情；" + MONITOR_OLD,
                      "new": "① 定植后定期调查叶片，初见暗色小点即喷药；"
                             "② 高温高湿（25-30℃、连续降雨或高湿）天气来临前预防性喷药；"
                             "③ 雨后及时检查病情；" + MONITOR_NEW}),
    ):
        _ok, old_value, new_value = patch_record(data["records"], "番茄细菌性斑点病", field, **kwargs)
        changes.append((f'番茄细菌性斑点病.{field}', "JSON", 1,
                        f'{len(old_value)}字 → {len(new_value)}字'))

    for rec in data["records"]:
        if rec.get("name") == "番茄细菌性斑点病":
            note = rec.get("calibration_notes", "")
            addition = (
                "【第 199 批修正】本条此前按 bacterial speck（Pseudomonas syringae pv. tomato）编写，"
                "与模型类目不一致：数据源 class_mapping.txt 第 29 项为 Tomato___Bacterial_spot"
                "（番茄细菌性斑点病），而 Bacterial spot 的病原是 Xanthomonas 属。"
                "原校准说明中“初稿将病原误写为黄单胞杆菌，更正为 Pseudomonas”这一步方向相反，"
                "已改回 Xanthomonas euvesicatoria；症状、发病规律、监测预警三处一并改回 spot 描述，"
                "事实取自本项目同病异寄主的「甜椒细菌性斑点病」记录（已校准）。"
                "附注：bacterial speck（番茄细菌性斑疹病）是本条的易混病害，已在症状中保留鉴别要点。"
            )
            if "第 199 批修正" not in note:
                rec["calibration_notes"] = (note + " " + addition).strip()
                changes.append(("番茄细菌性斑点病.calibration_notes", "JSON", 1, "追加修正说明"))
            break

    new_json = json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    print("=" * 96)
    print("按数据集类目表修正源数据" + ("" if args.apply else "（预览，未写入）"))
    print("=" * 96)
    for item in changes:
        print("  · " + " | ".join(str(x) for x in item))

    # 写出去之前自检：能被解析、且关键改动**真的在最终文本里**
    reparsed = json.loads(new_json)
    checks = [
        ("错字已修（分值）", "分值" not in new_json),
        ("错字已修（转渍）", "转渍" not in new_json),
        ("PYTHON 已验证：无 speck 病原", "Pseudomonas syringae pv. tomato (Okabe)" not in new_json),
        ("学名已改 Xanthomonas", any("Xanthomonas euvesicatoria" in (r.get("scientific_name") or "")
                                    and r.get("name") == "番茄细菌性斑点病" for r in reparsed["records"])),
        ("记录数仍为 38", len(reparsed["records"]) == 38),
        ("MD 错字也已修", "分值" not in raw_md and "转渍" not in raw_md),
    ]
    print()
    ok = True
    for label, passed in checks:
        print(f"  {'✓' if passed else '✗'} {label}")
        ok = ok and passed

    print(f"\n  JSON 行数 {json_lines_before} → {new_json.count(chr(10)) + 1}")
    print(f"  MD   行数 {raw_md.count(chr(10)) + 1}")

    if not ok:
        print("\n  ✗ 自检未通过，拒绝写入")
        return 1
    if not args.apply:
        print("\n  未写入。确认无误后加 --apply")
        return 0

    for path in (JSON_PATH, MD_PATH):
        shutil.copy2(path, str(path) + ".bak")

    def atomic_write(path: pathlib.Path, text: str):
        tmp = pathlib.Path(str(path) + ".tmp")
        tmp.write_bytes(text.encode("utf-8"))
        os.replace(tmp, path)

    atomic_write(JSON_PATH, new_json)
    atomic_write(MD_PATH, raw_md)

    print("\n  ✓ 已写入两个文件，并各留一份 .bak（确认无误后删）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
