"""把番茄细菌性斑点病的修正同步到 MD 人工阅读版（第 199 批）。

## 为什么要单独一步

`作物病害知识库_校准版.md` 是同一内容的人工阅读版，**七个维度都在里面**。
所以只改 JSON 会让两个文件脱节 —— 而这份 MD 正是给人看的那一份，
不同步的话，后来的人会照 MD 里"番茄斑点病 = Pseudomonas"继续错下去。

本脚本**从已修正的 JSON 取值**，只做行级替换（不重建整节），
这样 diff 最小、也不会碰到无关内容。
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

RECORD = "番茄细菌性斑点病"
#: 维度中文名 → MD 小节标题
SECTION_OF = {"症状描述": "症状描述", "发病规律": "发病规律", "监测预警": "监测预警"}


def md_section_bounds(lines: list[str], start: int) -> tuple[int, int]:
    """给定 `## <记录名>（病害）` 的行号，返回该节的行区间 [起, 止)。"""
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return start, end


def replace_section_body(lines: list[str], bounds: tuple[int, int], title: str, body: str) -> bool:
    """把 `### <title>` 与下一个 `### `/`**` 之间的正文换成 `body`（单段）。"""
    start, end = bounds
    header = f"### {title}"
    try:
        header_at = next(i for i in range(start, end) if lines[i].strip() == header)
    except StopIteration:
        raise SystemExit(f"{RECORD} 节里找不到小节 {header!r}")
    # 找这一小节的结束（下一个 ### 或 ** 开头的行，或节末）
    body_end = end
    for i in range(header_at + 1, end):
        if lines[i].startswith("### ") or lines[i].startswith("**"):
            body_end = i
            break
    old = "\n".join(lines[header_at + 1:body_end])
    if body in old:
        return False
    # 保留原有格式：标题行 + 空行 + 正文 + 空行
    lines[header_at + 1:body_end] = ["", body, ""]
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    record = next((r for r in data["records"] if r.get("name") == RECORD), None)
    if record is None:
        raise SystemExit(f"JSON 里找不到 {RECORD}")
    dims = record["dimensions"]

    md = MD_PATH.read_text(encoding="utf-8")
    lines = md.split("\n")

    head_at = next((i for i, line in enumerate(lines) if line.strip() == f"## {RECORD}（病害）"), None)
    if head_at is None:
        raise SystemExit(f"MD 里找不到 `## {RECORD}（病害）`")
    bounds = md_section_bounds(lines, head_at)

    changes = []

    # ── 学名那一行 ──
    sci_at = next((i for i in range(*bounds) if lines[i].startswith("- **学名**：")), None)
    if sci_at is None:
        raise SystemExit("MD 里找不到 `- **学名**：` 行")
    new_sci_line = f"- **学名**：{record['scientific_name']}"
    if lines[sci_at] != new_sci_line:
        changes.append(("学名", lines[sci_at][:50], new_sci_line[:50]))
        lines[sci_at] = new_sci_line

    # ── 三个维度 ──
    for dim, title in SECTION_OF.items():
        if replace_section_body(lines, bounds, title, dims[dim]):
            changes.append((f"### {title}", "旧正文", f"{len(dims[dim])} 字"))

    # ── 修正说明：追加在 数据来源 之前 ──
    note = ("**第 199 批修正**：本条此前按 bacterial speck（Pseudomonas syringae pv. tomato）编写，"
            "与模型类目不一致 —— 数据源 `class_mapping.txt` 第 29 项为 `Tomato___Bacterial_spot`"
            "（番茄细菌性斑点病），而 Bacterial spot 的病原是 Xanthomonas 属。"
            "原校准说明中「初稿将病原误写为黄单胞杆菌，更正为 Pseudomonas」这一步方向相反，"
            "已改回 Xanthomonas euvesicatoria；症状、发病规律、监测预警三处一并改回 spot 描述，"
            "事实取自本项目同病异寄主的「甜椒细菌性斑点病」记录。"
            "bacterial speck（番茄细菌性斑疹病）是本条的易混病害，鉴别要点已保留在症状描述中。")
    if "第 199 批修正" not in md:
        src_at = next((i for i in range(*bounds) if lines[i].startswith("**数据来源")), None)
        if src_at is None:
            raise SystemExit("MD 里找不到 `**数据来源`")
        lines[src_at:src_at] = [note, ""]
        changes.append(("追加修正说明", "—", "1 段"))

    new_md = "\n".join(lines)

    print("=" * 92)
    print(f"同步 {RECORD} 的修正到 MD" + ("" if args.apply else "（预览）"))
    print("=" * 92)
    if not changes:
        print("  无改动（MD 已与 JSON 一致）")
        return 0
    for item in changes:
        print("  · " + " | ".join(str(x) for x in item))

    checks = [
        ("MD 里已无 speck 病原", "Pseudomonas syringae pv. tomato (Okabe)" not in new_md),
        ("MD 学名已是 Xanthomonas", "Xanthomonas euvesicatoria" in new_md),
        ("MD 里已无「不隆起」的 speck 特征", "病斑不呈油渍状、不隆起、不穿孔" not in new_md),
        ("其余 37 条记录的小节数未变", new_md.count("\n## ") == md.count("\n## ")),
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

    shutil.copy2(MD_PATH, str(MD_PATH) + ".bak")
    tmp = pathlib.Path(str(MD_PATH) + ".tmp")
    tmp.write_bytes(new_md.encode("utf-8"))
    os.replace(tmp, MD_PATH)
    print("\n  ✓ 已写入 MD（留了 .bak）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
