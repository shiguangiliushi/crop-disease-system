"""清掉一处术语重复：『斑疹病（speck，…）』（第 201 批）。

## 为什么要清

中文原文与英文译文都在括号里重复了一次术语：

```
中文：与番茄细菌性斑疹病（speck，Pseudomonas引起，病斑极小1mm左右、不隆起）不同
英文：unlike tomato bacterial speck (speck, caused by Pseudomonas, with very small lesions …)
```

`斑疹病` / `bacterial speck` 已经表达了 speck，括号里再写一次属于冗余。
**这是可读性问题，不是事实问题** —— 所以只删重复词，不动任何事实与剂量。

## 第二处：英文那条记录自称 spot 却用 "bacterial spot" 指代别的病

第 199 批已改掉 `pepper` 那条里"unlike tomato bacterial spot"（那是自指错误）。
本脚本顺带核对：三条记录里凡出现 "bacterial spot" 的地方，
必须是在**说本条自己**，不能是在鉴别语境里指别的病。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import shutil
import sys

KB = pathlib.Path(r"D:\新建文件夹\crop-disease-system\docs\knowledge_base")
JSON_PATH = KB / "作物病害知识库_校准版.json"
MD_PATH = KB / "作物病害知识库_校准版.md"
EN_PATH = KB / "kb_en_diseases.py"

PAIRS = [
    # (文件, 旧, 新)
    ("json", "与番茄细菌性斑疹病（speck，Pseudomonas引起", "与番茄细菌性斑疹病（Pseudomonas引起"),
    ("md", "与番茄细菌性斑疹病（speck，Pseudomonas引起", "与番茄细菌性斑疹病（Pseudomonas引起"),
    ("en", "(speck, caused by Pseudomonas", "(caused by Pseudomonas"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    texts = {
        "json": JSON_PATH.read_text(encoding="utf-8"),
        "md": MD_PATH.read_text(encoding="utf-8"),
        "en": EN_PATH.read_text(encoding="utf-8"),
    }

    print("=" * 94)
    print("清掉『斑疹病（speck，…）』的术语重复" + ("" if args.apply else "（预览）"))
    print("=" * 94)

    for key, old, new in PAIRS:
        count = texts[key].count(old)
        print(f"  {key}: 命中 {count} 处（应为 1）")
        if count != 1:
            raise SystemExit(f"{key} 命中数不符，中止")
        texts[key] = texts[key].replace(old, new)

    # 写前自检：JSON 仍可解析；英文里 speck 说法保留在"鉴别"处
    data = json.loads(texts["json"])
    checks = [
        ("JSON 可解析且 38 条", len(data["records"]) == 38),
        ("JSON 里斑疹病仍在（鉴别语境）", "番茄细菌性斑疹病" in texts["json"]),
        ("JSON 里已无冗余的（speck，", "（speck，" not in texts["json"]),
        ("MD 同改", "（speck，" not in texts["md"]),
        ("英文里已无冗余 (speck,", "(speck," not in texts["en"]),
        ("英文里 speck 仍保留（鉴别用）", "bacterial speck" in texts["en"]),
        ("英文里无自指错误", "distinguish it from bacterial spot" not in texts["en"]),
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

    for path in (JSON_PATH, MD_PATH, EN_PATH):
        shutil.copy2(path, str(path) + ".bak")

    def atomic_write(path: pathlib.Path, text: str):
        tmp = pathlib.Path(str(path) + ".tmp")
        tmp.write_bytes(text.encode("utf-8"))
        os.replace(tmp, path)

    atomic_write(JSON_PATH, texts["json"])
    atomic_write(MD_PATH, texts["md"])
    atomic_write(EN_PATH, texts["en"])
    print("\n  ✓ 已写入三个文件（各留 .bak）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
