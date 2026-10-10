#!/usr/bin/env python
"""
刷新《注释覆盖审计报告》里由脚本生成的段落（第 155 批）

## 为什么要有它

`docs/注释覆盖审计报告.md` 是第 105 批写的，开头就写着"用来看趋势"——
但它的数字与清单**是手抄进文档的**，于是到第 153 批核查时已经全面过期
（文档里 251 文件 / 88372 行 / 9.0%，实测 271 / 106173 / 10.9%；
三节的清单更是换了大半）。

手抄的东西一定会过期。这个脚本把"刷新"变成一条命令：
它调 `tools/audit_comments.py` 拿最新结果，再替换文档里三处**标记之间**的内容：

    <!-- AUDIT:SUMMARY:BEGIN -->  … <!-- AUDIT:SUMMARY:END -->    总体表（按模块）
    <!-- AUDIT:LONGFN:BEGIN -->   … <!-- AUDIT:LONGFN:END -->     内部零注释的长函数
    <!-- AUDIT:NOHEADER:BEGIN --> … <!-- AUDIT:NOHEADER:END -->   缺头注释的文件

标记外面的人写文字（结论、解读、历史对比）**不会被碰**。

用法：
    python docs/tools/refresh_audit_report.py            # 刷新（就地改文档）
    python docs/tools/refresh_audit_report.py --check    # 只检查是否需要刷新（给 CI 用）
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / 'docs' / '注释覆盖审计报告.md'
TOOL = ROOT / 'tools' / 'audit_comments.py'

#: 需要跳过的模块（第三方/环境，出现在 --summary 里但与本项目无关）
SKIP_MODULES = ('venv', 'node_modules', '.git')


def run_tool(*args):
    result = subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    if result.returncode != 0:
        raise SystemExit(f'审计工具执行失败：{result.stderr[-400:]}')
    return result.stdout


def summary_table():
    """把 `--summary` 的定宽表格转成 Markdown"""
    rows = []
    for line in run_tool('--summary').splitlines():
        parts = re.split(r'\s{2,}', line.strip())
        if len(parts) < 7 or parts[0] in ('模块', '') or set(parts[0]) <= {'-'}:
            continue
        if any(skip in parts[0] for skip in SKIP_MODULES):
            continue
        module, files, lines, comments, density, no_header, no_doc, *_ = parts
        rows.append((module, files, lines, comments, density, no_header, no_doc))
    if not rows:
        raise SystemExit('解析 --summary 失败：没抓到任何数据行')
    # 最后一行是"合计"，单独取出来加粗
    markdown = ['| 模块 | 文件 | 行数 | 注释行 | 密度 | 缺头注释 | 缺文档成员 |',
                '|---|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        module, files, lines, comments, density, no_header, no_doc = row
        if module.startswith('合计') or module == 'total':
            module = f'**{module}**'
        markdown.append(
            f'| {module} | {files} | {lines} | {comments} | {density} | {no_header} | {no_doc} |')
    return '\n'.join(markdown)


def markdown_sections():
    """从 `--markdown` 输出里取出三张表"""
    out = run_tool('--markdown')
    blocks = {'longfn': [], 'noheader': []}
    mode = None
    for line in out.splitlines():
        if line.startswith('### 文件顶部没有模块说明'):
            mode = 'noheader'
            continue
        if line.startswith('### 长函数内部 0 条注释'):
            mode = 'longfn'
            continue
        if line.startswith('### 缺文档字符串最多'):
            mode = None
            continue
        if mode and (line.startswith('|') or line.strip() == ''):
            if line.startswith('|'):
                blocks[mode].append(line)
    return {key: '\n'.join(value) for key, value in blocks.items()}


def replace_region(text, name, body):
    begin = f'<!-- AUDIT:{name}:BEGIN -->'
    end = f'<!-- AUDIT:{name}:END -->'
    if begin not in text or end not in text:
        raise SystemExit(f'文档里找不到标记 {begin} / {end}，请先补上标记')
    pattern = re.compile(re.escape(begin) + r'.*?' + re.escape(end), re.S)
    return pattern.sub(f'{begin}\n{body}\n{end}', text)


def main():
    parser = argparse.ArgumentParser(description='刷新注释覆盖审计报告里由脚本生成的部分')
    parser.add_argument('--check', action='store_true', help='只检查是否需要刷新（不改文件）')
    args = parser.parse_args()

    original = REPORT.read_text(encoding='utf-8')
    sections = markdown_sections()
    updated = replace_region(original, 'SUMMARY', summary_table())
    updated = replace_region(updated, 'LONGFN', sections['longfn'] or '（无）')
    updated = replace_region(updated, 'NOHEADER', sections['noheader'] or '（无）')

    if updated == original:
        print('✅ 报告已是最新（三处标记内的内容与脚本输出一致）')
        return 0

    if args.check:
        print('❌ 报告与脚本输出不一致 —— 请跑：python docs/tools/refresh_audit_report.py')
        return 1

    REPORT.write_text(updated, encoding='utf-8', newline='\n')   # 显式 LF（第 152 批的教训）
    print('✅ 已刷新 docs/注释覆盖审计报告.md 的三处生成段落')
    print('   （标记外的解读文字未改动；如需保留旧数字做对比，请写在标记外面）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
