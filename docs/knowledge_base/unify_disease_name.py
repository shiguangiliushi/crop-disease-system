"""统一病名说法：甜椒那条的「细菌性叶斑病」→「细菌性斑点病」（第 201 批）。

## 依据

数据集 `class_mapping.txt` 第 22 项：

```
22. Pepper,_bell___Bacterial_spot  - 甜椒细菌性斑点病
```

`Bacterial spot` 的规范中文名是「细菌性**斑点**病」（作物名 + 该名）。
而「甜椒细菌性斑点病」这条记录的 `scientific_name` 里写的是
「辣椒上细菌性**叶斑**病（bacterial spot）」—— 同一份记录里对同一种病用了两个名字。

## 为什么只改这一处

全库扫过（`audit_disease_naming.py`）：

- **「疮痂病」已无残留** —— 第 199 批把番茄那条的旧症状描述整段换掉时一并清掉了；
  现在全库只剩"**疮痂状**"（形容病斑表面，是症状词，不是病名，必须保留）。
- 其余「叶斑病」都**不是**指 bacterial spot：玉米尾孢叶斑病是另一个词条
  （`Corn___Cercospora_leaf_spot`），各健康档案里的「防治…叶斑病」是泛指；
  审计脚本对它们的 `★需统一` 标记属**误报**（它的"对照语境"判定只窗口取了 ±26 字，
  判不到"区别于"）—— 所以本批**不照审计脚本改**，逐条人工确认后才动手。
- **英文侧无需改**：`kb_en_diseases.py` 里没有 "bacterial leaf spot" / "bacterial scab"
  这类说法，`name_en` 本来就是类目表的 `Bacterial spot`。
- 番茄那条里的「斑疹病」都保留：要么就是 bacterial speck 的专业中文名，
  要么处在明确的对照语境（第 199 批已把"拿它指本条自己的病"改掉）。

用法：`python unify_disease_name.py`（预览）/ `--apply`
改完必须接着跑 `load_kb --apply`。
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

OLD = "辣椒上细菌性叶斑病（bacterial spot）"
NEW = "辣椒上细菌性斑点病（bacterial spot）"
RECORD = "甜椒细菌性斑点病"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    raw_json = JSON_PATH.read_text(encoding="utf-8")
    raw_md = MD_PATH.read_text(encoding="utf-8")

    counts = {"JSON": raw_json.count(OLD), "MD": raw_md.count(OLD)}
    print("=" * 94)
    print("统一病名：细菌性叶斑病 → 细菌性斑点病" + ("" if args.apply else "（预览）"))
    print("=" * 94)
    for label, count in counts.items():
        print(f"  {label}: 命中 {count} 处（应为 1）")
    if any(count != 1 for count in counts.values()):
        raise SystemExit("命中数与预期不符，改前请人工确认")

    # 定位所在记录，确认改的就是甜椒那条
    data = json.loads(raw_json)
    hit_records = [r.get("name") for r in data["records"]
                   if OLD in (r.get("scientific_name") or "")]
    print(f"  所在记录: {hit_records}（应为 ['{RECORD}']）")
    if hit_records != [RECORD]:
        raise SystemExit("所在记录与预期不符，中止")

    new_json = raw_json.replace(OLD, NEW)
    new_md = raw_md.replace(OLD, NEW)

    # 追加一条校准说明（这一版 JSON 有 calibration_notes 字段，改动要留痕）
    reparsed = json.loads(new_json)
    for rec in reparsed["records"]:
        if rec.get("name") == RECORD:
            note = rec.get("calibration_notes", "")
            addition = ("【第 201 批统一】`scientific_name` 里的「辣椒上细菌性叶斑病」改为"
                        "「辣椒上细菌性斑点病」，与数据集类目表第 22 项"
                        "（Pepper,_bell___Bacterial_spot - 甜椒细菌性斑点病）及本记录名称统一。"
                        "原写法属同物异名，易与番茄细菌性斑疹病（bacterial speck）混淆。")
            if "第 201 批统一" not in note:
                rec["calibration_notes"] = (note + " " + addition).strip()
                print("  · 已在 calibration_notes 追加统一说明")
            break
    new_json = json.dumps(reparsed, ensure_ascii=False, indent=2) + "\n"

    pepper_sci = next((r.get("scientific_name") or "") for r in reparsed["records"]
                      if r.get("name") == RECORD)
    checks = [
        ("JSON 已无旧说法", OLD not in new_json),
        ("JSON 有新说法", NEW in new_json),
        ("MD 已无旧说法", OLD not in new_md),
        ("MD 有新说法", NEW in new_md),
        ("记录数仍为 38", len(reparsed["records"]) == 38),
        # ⚠️ 判据改成**正向核对**。第一版写的是"全库不再含『细菌性叶斑病』" ——
        #    那条**逻辑上永远不可能通过**：要被替换的旧句 `辣椒上细菌性叶斑病`
        #    本身就含这个子串。查库得到的变化只能靠"旧句没了 + 新句在"来证明。
        ("甜椒学名里已是『细菌性斑点病』", "细菌性斑点病" in pepper_sci),
        # ⚠️ 判据只数"当病名用"的那一处。第一版写成 `count("细菌性") == 1` —— 不对：
        #    同一句里还有**鉴别语境**的「番茄细菌性斑疹病」（那是**正确且必须保留**的，
        #    bacterial speck 的专业中文名）。所以要看的是：
        #    「细菌性斑点病」恰好 1 次，且旧说法 0 次。
        ("甜椒学名里『细菌性斑点病』恰好 1 次", pepper_sci.count("细菌性斑点病") == 1),
        ("甜椒学名里旧说法已消失", "细菌性叶斑病" not in pepper_sci),
        ("鉴别语境的『番茄细菌性斑疹病』保留", "番茄细菌性斑疹病" in pepper_sci),
    ]
    print()
    ok = True
    for label, passed in checks:
        print(f"  {'✓' if passed else '✗'} {label}")
        ok = ok and passed

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
    atomic_write(MD_PATH, new_md)
    print("\n  ✓ 已写入两个文件（各留 .bak）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
