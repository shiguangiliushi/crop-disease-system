"""同步英文译稿：番茄细菌性斑点病由 speck 改回 spot（第 199 批）。

## 为什么这一步不能省

中文源改了、库里中文也改了，但**英文译稿还是旧中文的译文** ——
于是英文界面下助手仍会告诉英文用户"番茄斑点病是 Pseudomonas、病斑 1-3mm 不隆起"，
也就是**中文已纠正、英文仍在传播错误**。`apply_kb_en.py` 的三项校验里
"数字对齐"能发现数字对不上，但这类**语义错位**它查不出来（新旧文本数字相似）。
所以这里必须显式重写，并在脚本里留痕。

## 事实来源

同项目已校准的「甜椒细菌性斑点病」英文（`kb_en_methods.py` / 中文源）与
数据集 `class_mapping.txt` 第 29 项 `Tomato___Bacterial_spot`。
"""
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import os
import pathlib
import re
import shutil
import sys

KB = pathlib.Path(r"D:\新建文件夹\crop-disease-system\docs\knowledge_base")
TARGET = KB / "kb_en_diseases.py"

NEW = {
    "symptoms_en": (
        "Mainly attacks leaves, stems and fruit. On leaves, small water-soaked yellow-green "
        "spots appear first and enlarge into irregular to angular necrotic lesions 1–4 mm in "
        "diameter (larger than bacterial speck), with a pale brown slightly sunken centre, a "
        "dark brown slightly raised margin, a rough corky (scabby) surface and a yellow halo. "
        "It differs from tomato bacterial speck (Pseudomonas syringae pv. tomato), whose "
        "lesions are very small (1–3 mm), not raised, and appear on fruit as tiny black dots "
        "that do not crack. In severe cases lesions merge into irregular dead patches and the "
        "leaves turn yellow and dry up. On stems, water-soaked irregular streaks appear first "
        "and later become corky, raised and split lengthwise in a scabby pattern. On green "
        "fruit the first lesions are black or dark brown raised dots that enlarge into round "
        "or oval black scabby lesions 1–3 mm across with cracked margins."
    ),
    "description_en": (
        "The pathogen is a Xanthomonas bacterium (Xanthomonas euvesicatoria and related "
        "species; Gram-negative) that can infect tomato and pepper and other solanaceous "
        "crops. It overwinters on the seed surface and inside the seed, and seed-borne "
        "inoculum is the most important source of primary inoculum; it can also survive in "
        "crop debris and in soil. The bacterium is spread by rain splash, wind and rain, "
        "irrigation water and farming operations, and enters through stomata, lenticels or "
        "wounds. Disease is severe under high temperature and high humidity (air temperature "
        "25–30 °C), with frequent rain and strong wind and long periods of leaf wetness; it is "
        "also severe in continuously cropped fields, in fields with poor drainage and in "
        "fields given excessive nitrogen, and in poorly ventilated greenhouses."
    ),
}

MARKER = "# 第 199 批修正"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    raw = TARGET.read_text(encoding="utf-8")

    # 用 importlib 取旧值（确认要改的就是那两条，避免改错记录）
    spec = importlib.util.spec_from_file_location("kb_en_diseases", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old = module.EN["tomato_bacterial_spot"]

    problems = []
    if "Pseudomonas bacterium (Gram-negative) that attacks tomato specifically" not in old["description_en"]:
        problems.append("description_en 与预期不符（可能已改过）")
    if "not raised" not in old["symptoms_en"]:
        problems.append("symptoms_en 与预期不符（可能已改过）")
    if problems:
        raise SystemExit("拒绝修改：\n  · " + "\n  · ".join(problems))

    # 定位该条目的两个字段并整块替换（用 Python 字面量片段精确定位）
    out = raw
    for field, value in NEW.items():
        pattern = re.compile(
            rf'("tomato_bacterial_spot": \{{.*?"{field}": )"((?:[^"\\]|\\.)*)"',
            re.S,
        )
        match = pattern.search(out)
        if not match:
            raise SystemExit(f"在 kb_en_diseases.py 里找不到 tomato_bacterial_spot.{field}")
        replacement = match.group(1) + repr(value).replace("'", '"', 0)
        # 用显式拼接避免 repr 的引号/转义问题
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        new_literal = f'"{escaped}"'
        out = out[:match.start(2) - 1] + new_literal + out[match.end(2) + 1:]
        print(f"  · {field}: {len(match.group(2))} → {len(value)} 字符")

    # 留痕：注明这批改了什么、为什么
    if MARKER not in out:
        note = (
            f"\n\n{MARKER}：`tomato_bacterial_spot` 的两条英文由 bacterial speck 改回 bacterial spot。\n"
            f"# 原因：中文源此前把病原写成 Pseudomonas syringae pv. tomato（那是 speck），\n"
            f"# 而模型类目（数据集 class_mapping.txt 第 29 项 Tomato___Bacterial_spot）是 spot，\n"
            f"# 其病原为 Xanthomonas。事实取自同项目已校准的「甜椒细菌性斑点病」。\n"
            f"# 中文已同步修正，见 fix_kb_source.py / sync_kb_md.py。\n"
        )
        out = out.rstrip("\n") + note

    # 写前自检：重新解析，确认改动真的在最终文本里。
    # ⚠️ 两个坑都踩过：
    #   ① 临时文件名用 `.check` 后缀 —— `spec_from_file_location` 对未知后缀返回 None
    #      （它没有 loader），于是 `module_from_spec(None)` 报 AttributeError；
    #   ② 导入后文件句柄仍被占用，Windows 上 unlink 报 WinError 32。
    #      所以用**显式 SourceFileLoader** + 先 `sys.modules.pop`，文件名保持 `.py`。
    tmp = pathlib.Path(str(TARGET) + ".check.py")
    tmp.write_text(out, encoding="utf-8", newline="\n")
    try:
        loader = importlib.machinery.SourceFileLoader("kb_en_diseases_check", str(tmp))
        spec2 = importlib.util.spec_from_loader("kb_en_diseases_check", loader)
        mod2 = importlib.util.module_from_spec(spec2)
        loader.exec_module(mod2)
        after = mod2.EN["tomato_bacterial_spot"]
        total = len(mod2.EN)          # 先取值：finally 里会 del mod2（第一版就是这里报 UnboundLocalError）
    finally:
        sys.modules.pop("kb_en_diseases_check", None)
        try:
            del mod2, loader, spec2
        except NameError:
            pass
        try:
            tmp.unlink(missing_ok=True)
        except PermissionError:
            pass   # 句柄偶尔晚一拍释放；它在 .gitignore 之外但会被 git status 看到，下面再清

    checks = [
        ("不含 Pseudomonas 作病原描述", "Pseudomonas bacterium" not in after["description_en"]),
        ("含 Xanthomonas", "Xanthomonas euvesicatoria" in after["description_en"]),
        ("含 25–30 °C", "25–30 °C" in after["description_en"]),
        ("含 1–4 mm", "1–4 mm" in after["symptoms_en"]),
        ("仍保留与 speck 的鉴别", "bacterial speck" in after["symptoms_en"]),
        ("无中文字符", not re.search(r"[\u4e00-\u9fff]", after["symptoms_en"] + after["description_en"])),
        ("其余 25 条未受影响", total == 26),
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

    shutil.copy2(TARGET, str(TARGET) + ".bak")
    tmp2 = pathlib.Path(str(TARGET) + ".tmp")
    tmp2.write_text(out, encoding="utf-8", newline="\n")
    os.replace(tmp2, TARGET)
    print("\n  ✓ 已写入 kb_en_diseases.py（留了 .bak）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
