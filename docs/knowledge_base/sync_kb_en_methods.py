"""补上 tomato_bacterial_spot/MONITORING 的英文（第 199 批）。

## 这一处是**校验脚本抓出来的**，不是我复查出来的

中文的监测预警改成了"高温高湿（25-30℃…）"与"与番茄细菌性斑疹病鉴别"，
但 `kb_en_methods.py` 里那条英文还是旧的"cool, rainy weather (16-24 °C)"与
"distinguish it from bacterial spot"。

`apply_kb_en.py` 的"数字对齐"检查当场报出：

    · tomato_bacterial_spot/MONITORING：英文缺少中文里的数字 ['25', '30']

这条正说明**三项校验里"数字对齐"最值钱** —— 语义错位（本条就是 spot 却叫人与 spot 鉴别）
它查不出来，但数字对不上能查出来，从而把整条拉进视野。

## 第二个坑：值是多行隐式拼接

`kb_en_methods.py` 的值形如：

    ("tomato_bacterial_spot", "MONITORING"): (
        "第一段"
        "第二段"
    ),

所以**不能用单行正则**匹配 `键: "值"`（第一版就是这么失败的：报"找不到该键"）。
改为**按行区间**替换：从键所在行到下一个同级键行之间整段换掉，
并沿用锚点自身的缩进（两种缩进在这份文件里都出现过，写死会踩坑）。
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
TARGET = KB / "kb_en_methods.py"

NEW_TEXT = (
    "1) Survey the leaves at regular intervals after transplanting and spray as soon as dark "
    "spots are first seen. 2) Spray preventively before spells of high temperature and high "
    "humidity (25-30 °C, continuous rain or high humidity). 3) Check the disease promptly "
    "after rain. 4) Take care to distinguish it from tomato bacterial speck and, where "
    "necessary, send samples for laboratory testing."
)

KEY_LINE = '("tomato_bacterial_spot", "MONITORING")'


def render_block(indent: str, text: str) -> list[str]:
    """把长文本渲染成"每行一段隐式拼接"，与文件既有风格一致。

    ⚠️ **拼接处必须补回空格**。Python 的相邻字符串字面量是**直接连接**（不插空格），
    所以按空格拆行之后，每段结尾要带一个空格，否则会得到
    `spotsare`、`todistinguish`、`laboratorytesting` 这种词 —— 而它**语法完全合法**，
    只有读内容才看得出来（第一版就是这样把英文写坏的，靠人工核验才发现）。
    """
    pieces, current = [], ""
    for word in text.split(" "):
        if current and len(current) + len(word) + 1 > 96:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        pieces.append(current)

    out = [f'{indent}{KEY_LINE}: (']
    for index, piece in enumerate(pieces):
        escaped = piece.replace("\\", "\\\\").replace('"', '\\"')
        # 最后一段不留尾空格；其余每段补一个，保证拼接后单词不粘在一起
        suffix = "" if index == len(pieces) - 1 else " "
        out.append(f'{indent}    "{escaped}{suffix}"')
    out.append(f"{indent}),")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    raw = TARGET.read_text(encoding="utf-8")
    lines = raw.split("\n")

    spec = importlib.util.spec_from_file_location("kb_en_methods", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old = module.EN[("tomato_bacterial_spot", "MONITORING")]

    # 允许两种起点：改之前（cool, rainy）与改之后但**词被粘住**的版本
    if "cool, rainy weather (16-24 °C" not in old and "spotsare" not in old:
        raise SystemExit(f"与预期不符（可能已改过）：{old[:80]!r}")

    # 按**行区间**替换该键的整个值块（值是多行隐式拼接，单行正则匹配不到 —— 第一版就栽在这）
    key_at = next((i for i, line in enumerate(lines) if KEY_LINE in line), None)
    if key_at is None:
        raise SystemExit("找不到该键所在行")
    indent = re.match(r"\s*", lines[key_at]).group(0)
    # 块尾 = 下一个**同级键行**（缩进 + `("`）。
    # ⚠️ 第一版写成 `startswith(indent + "(")` —— 那会匹配到**字典自身的收尾 `),`**，
    #    于是把字典的右括号切掉，临时文件直接 SyntaxError（"does not match opening '{'"）。
    #    判据必须窄到"键行"这一种形态。
    end_at = len(lines)
    for i in range(key_at + 1, len(lines)):
        if lines[i].startswith(indent + '("'):
            end_at = i
            break
    print(f"  键行 {key_at + 1}，块区间 {key_at + 1}–{end_at}（缩进 {len(indent)}）")
    print(f"  旧块首行: {lines[key_at].strip()}")
    print(f"  旧块末行: {lines[end_at - 1].strip()[:90]}")

    old_len = len(old)
    lines[key_at:end_at] = render_block(indent, NEW_TEXT)
    out = "\n".join(lines)
    print(f"  · MONITORING: {old_len} → {len(NEW_TEXT)} 字符")

    # 写前自检：临时文件重新导入并核对
    tmp = pathlib.Path(str(TARGET) + ".check.py")
    tmp.write_text(out, encoding="utf-8", newline="\n")
    try:
        loader = importlib.machinery.SourceFileLoader("kb_en_methods_check", str(tmp))
        spec2 = importlib.util.spec_from_loader("kb_en_methods_check", loader)
        mod2 = importlib.util.module_from_spec(spec2)
        loader.exec_module(mod2)
        after = mod2.EN[("tomato_bacterial_spot", "MONITORING")]
        total = len(mod2.EN)
    finally:
        sys.modules.pop("kb_en_methods_check", None)
        try:
            del mod2, loader, spec2
        except NameError:
            pass
        try:
            tmp.unlink(missing_ok=True)
        except PermissionError:
            pass

    checks = [
        # ⚠️ 判据用"数字在不在"，不要写死 `25-30 °C` 这种精确形态：
        #    中文源写的是半角连字符且 ° 前无空格（`25-30℃`），英文习惯写成 `25-30 °C`，
        #    两者本来就不同形态。第一版对着 `25-30 °C` 判，自检误报失败、拒绝写入。
        ("含 25 与 30", "25" in after and "30" in after),
        ("含摄氏度", "°C" in after),
        ("不再说 cool, rainy", "cool, rainy" not in after),
        # ⚠️ 这条是补出来的：拼接处漏空格会产生 `spotsare` 这类**合法但错误**的英文，
        #    语法检查、导入、键数校验全都发现不了 —— 只有读内容才看得出。
        #    判据要**具体**：宽泛的正则（如 `[a-z]{2}(are|to)\b`）会匹配到正常英文
        #    （"…that are first seen" 里的 are），那是误报。所以核对已知粘连词，
        #    并以"与目标文本逐字一致"作为主判据。
        ("无已知粘连词", not any(bad in after for bad in ("spotsare", "todistinguish", "laboratorytesting"))),
        ("与目标文本逐字一致", after == NEW_TEXT),
        ("改为与 speck 鉴别", "bacterial speck" in after),
        ("不再说与 bacterial spot 鉴别", "distinguish it from bacterial spot" not in after),
        ("无中文字符", not re.search(r"[\u4e00-\u9fff]", after)),
        ("130 条键未变", total == 130),
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
    print("\n  ✓ 已写入 kb_en_methods.py（留了 .bak）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
