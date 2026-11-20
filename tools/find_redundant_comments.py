#!/usr/bin/env python
"""找出**翻译式注释**候选：只把下一行代码念一遍的那种（第 416 批）

    python tools/find_redundant_comments.py            # 列出候选
    python tools/find_redundant_comments.py --json     # 机读
    python tools/find_redundant_comments.py --path backend/api

## 为什么要单独一个工具

`tools/audit_comments.py` 查的是**覆盖率**（缺头注释 / 缺文档成员 / 长函数零注释），
不含"注释写得对不对"。而《注释覆盖审计报告》第八节早记过：这类注释的危害不是占地方，
是把真正说明"为什么"的那几条**稀释**掉 —— 但那个检测器当初是一次性脚本，没留下来。

这个工具刻意**只做高精度匹配**（宁可漏，不可误杀）：

  · `# 导入…` / `# 引入…`      —— import 行上的同义反复
  · `# 定义…方法|函数|类|字段`  —— def/class 行上的同义反复
  · `# 返回…` / `# 设置…`       —— 紧贴 `return` / 赋值语句的同义反复

只给候选，**不自动改**：有些 `# 返回…` 后面跟的是"返回 None 表示未登录"这种真信息，
工具判断不了，最终由人（或代理）逐条看下一行再决定。

与 `audit_comments.py` 一样只读文件，不改任何东西。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {'node_modules', 'venv', 'dist', 'staticfiles', 'dsh-shots', 'backups', '.git', '__pycache__'}

#: (正则, 说明) —— 都是"注释 ≈ 下一行代码"的高精度形状
PATTERNS = (
    (re.compile(r'^#\s*(导入|引入)'), 'import'),
    (re.compile(r'^#\s*(定义|声明)[^，。]{0,14}(方法|函数|类|字段|属性|变量)?\s*$'), 'definition'),
    (re.compile(r'^#\s*(返回|设置|赋值)'), 'statement'),
    (re.compile(r'^//\s*(导入|引入)'), 'import'),
    (re.compile(r'^//\s*(定义|声明)'), 'definition'),
    (re.compile(r'^\*\s*(导入|引入)'), 'import'),
)

#: 下一行是这些形状时，`# 返回…` / `# 导入…` 基本就是同义反复
IMPORT_LINE = re.compile(r'^\s*(from\s+\S+\s+import|import\s+\S+)')
DEF_LINE = re.compile(r'^\s*(async\s+def|def|class)\s')
RETURN_LINE = re.compile(r'^\s*return\b')
ASSIGN_LINE = re.compile(r'^\s*[A-Za-z_][\w.]*\s*=[^=]')

#: 注释里只要出现这些词就**不报**（它多半在讲原因，不是翻译）
WHY_WORDS = ('因为', '原因', '为什么', '否则', '避免', '防止', '注意', '⚠️', '坑',
             '批', '口径', '约定', '历史', '实测', '曾经', '故意', '刻意')

CODE_SUFFIXES = {'.py', '.js', '.mjs', '.vue', '.ts'}


def iter_files(target: Path):
    for path in target.rglob('*'):
        if path.suffix.lower() not in CODE_SUFFIXES or not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def scan_file(path: Path) -> list[dict]:
    """扫一个文件，返回"看着像同义反复"的注释候选。

    只在**下一行确是 import / def / return / 赋值**时才报（否则 `# 导入…` 也可能在讲
    一次迁移的历史）。含原因词的注释先被 `WHY_WORDS` 排除掉，所以这个函数宁可漏报。
    """
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return []

    hits = []
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        marker = ''
        if stripped.startswith('#'):
            marker = '#'
        elif stripped.startswith('//'):
            marker = '//'
        elif stripped.startswith('*') and not stripped.startswith('*/'):
            marker = '*'
        if not marker:
            continue

        text = stripped[len(marker):].strip()
        if not text or any(word in text for word in WHY_WORDS):
            continue

        kind = None
        for pattern, name in PATTERNS:
            if pattern.match(stripped):
                kind = name
                break
        if kind is None:
            continue

        # 找下一行非空代码，用来判断是不是"念代码"
        following = ''
        for offset in range(index + 1, min(index + 4, len(lines))):
            candidate = lines[offset].strip()
            if candidate and not candidate.startswith(('#', '//', '*')):
                following = candidate
                break
        if not following:
            continue

        matched = False
        if kind == 'import' and IMPORT_LINE.match(following):
            matched = True
        elif kind == 'definition' and DEF_LINE.match(following):
            matched = True
        elif kind == 'statement' and (RETURN_LINE.match(following) or ASSIGN_LINE.match(following)):
            matched = True
        if not matched:
            continue

        hits.append({
            'path': path.relative_to(ROOT).as_posix(),
            'line': index + 1,
            'text': stripped,
            'next': following[:80],
        })
    return hits


def main() -> int:
    """命令行入口：只打印候选（`--json` 给机读），**不修改任何文件**。

    删除与否必须人来判断 —— 紧贴 `return` 的注释有时是真信息
    （例如"返回 None 表示未登录"），工具无法区分。
    """
    parser = argparse.ArgumentParser(description='找出翻译式注释候选（只报告，不改）')
    parser.add_argument('--path', default='', help='只扫这个子目录（相对仓库根）')
    parser.add_argument('--json', action='store_true', help='输出 JSON')
    args = parser.parse_args()

    target = (ROOT / args.path) if args.path else ROOT
    if not target.exists():
        print(f'✗ 路径不存在：{target}')
        return 2

    results = []
    for path in sorted(iter_files(target)):
        results.extend(scan_file(path))

    by_file: dict[str, int] = {}
    for item in results:
        by_file[item['path']] = by_file.get(item['path'], 0) + 1

    if args.json:
        print(json.dumps({'total': len(results), 'by_file': by_file, 'items': results},
                         ensure_ascii=False, indent=2))
        return 0

    print(f'翻译式注释候选：{len(results)} 处，分布在 {len(by_file)} 个文件')
    for item in results:
        print(f"  {item['path']}:{item['line']}  {item['text']}")
        print(f"      下一行: {item['next']}")
    print('')
    print('⚠️ 只列候选：紧贴 return 的注释有时是真信息（例如"返回 None 表示未登录"），逐条看下一行再决定。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
