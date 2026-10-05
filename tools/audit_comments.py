"""
注释覆盖审计（第 105 批）
============================================================================
回答一个具体问题：**这个项目的代码里，还有哪些地方没有注释？**

为什么值得做成脚本而不是"看一遍"：
  · 90k+ 行的项目靠翻是翻不完的，而且翻完也没有可对比的基线；
  · "有没有注释"必须用**可重复的判据**，否则每次结论都不一样；
  · 这个脚本可以在每次改动后重跑，看的是"趋势"而不是"感觉"。

判据（刻意简单、可解释，不追求"注释质量"打分那种玄学）：
  1. **模块/类/函数是否有文档字符串**（Python 用 AST，Vue/JS 用头部块注释）；
  2. **注释密度** = 注释行 / 代码行（低于阈值就列出来看一眼）；
  3. **魔法数字**：代码里出现却没有任何注释解释的裸数字
     （0/1/2/-1/100 等常见值不算；这是"最该有注释却没注释"的典型）；
  4. **长文件/长函数**：超过阈值又几乎没有注释的，通常是"逻辑复杂但没人写为什么"。

用法：
    python tools/audit_comments.py                 # 全量摘要 + 问题清单
    python tools/audit_comments.py --top 40        # 只看最差的 40 个文件
    python tools/audit_comments.py --json          # 机读输出（给 CI/对比用）
    python tools/audit_comments.py --path frontend/src/views
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: 只审这些目录（依赖、构建产物、迁移文件不审 —— 迁移是自动生成的）
SCAN_DIRS = [
    'backend/api',
    'backend/crop_disease_backend',
    'frontend/src',
    'mobile/src',
    'frontend/e2e',
    'frontend/scripts',
    'mobile/scripts',
    'tools',
]

SKIP_PARTS = {
    'node_modules', 'dist', '__pycache__', 'migrations', '.git',
    'venv', 'site-packages', 'test-results', 'playwright-report',
    # `_deprecated/` 是**已退役**的代码（前端早期的脚手架残留与旧页面），
    # 它没有维护价值，计入总量只会稀释/污染"现存代码"的注释覆盖率。
    # 单独统计更诚实：跑 `--path frontend/src/_deprecated` 就能看到它自己有多差。
    '_deprecated',
}

SOURCE_SUFFIXES = {'.py', '.vue', '.js', '.mjs', '.ts'}

#: 不需要解释的裸数字（下标、布尔、常见倍数、HTTP 状态码等）
BENIGN_NUMBERS = {
    '0', '1', '2', '3', '-1', '100', '10', '1000', '60', '24', '7', '30',
    '200', '201', '400', '401', '403', '404', '500', '10000',
}

#: 注释密度低于这个值就"值得看一眼"
LOW_DENSITY = 0.05
#: 超过这个行数又没有文档字符串的文件，单独点出来
LONG_FILE = 300


@dataclass
class FileReport:
    path: str
    lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    inline_comments: int = 0
    docstrings: int = 0
    undocumented: list[str] = field(default_factory=list)   # 缺文档字符串的类/函数
    module_has_docstring: bool = False
    magic_numbers: list[str] = field(default_factory=list)  # "第 N 行: 数字"
    long_functions: list[str] = field(default_factory=list)

    @property
    def density(self) -> float:
        if not self.code_lines:
            return 1.0
        return self.comment_lines / self.code_lines

    def to_dict(self) -> dict:
        data = self.__dict__.copy()
        data['density'] = round(self.density, 3)
        return data


# ---------------------------------------------------------------------------
# "值不值得写文档字符串"的判据
# ---------------------------------------------------------------------------
#: 名字本身就说明一切的（getter/setter/序列化钩子/测试方法…）
SELF_DOCUMENTING = re.compile(
    r'^(?:'
    r'get_|set_|is_|has_|can_|to_|as_|__\w+__|test_\w+|handle_|visit_|validate_\w+'
    r')'
)


def worth_documenting(name: str, span: int, node=None) -> bool:
    """
    这个成员"值不值得"写文档字符串？

    ⚠️ 审计脚本第一版把所有 ≥8 行、没文档字符串的函数都报了出来，
    结果 `tests.py` 一个文件就贡献了 213 个"问题" —— 那**不是问题**：
    Django 的 `test_xxx` 方法名本身就是说明（`test_admin_cannot_delete_self`
    再写一句 docstring 只是重复），Django 的 `handle()` 也只可能有一个。

    判据：
      · 名字自解释（`get_*` / `test_*` / `__init__` …）→ 不算问题；
      · 行数 ≥ 25 → 一定有值得写的东西（分支、边界、为什么这么写）；
      · 或者体里有 ≥3 个分支且 ≥12 行 → 逻辑够复杂，值得说明。
    """
    short = name.rsplit('.', 1)[-1]
    if SELF_DOCUMENTING.match(short):
        return False
    # Django/DRF 的约定名：写 docstring 只是重复框架文档，不算"缺注释"
    #   · `class Command` + `handle()` —— 管理命令的固定入口
    #   · `class XxxAdmin`           —— admin 注册类
    #   · `class ApiConfig`          —— AppConfig
    if short in {'Command', 'handle', 'ApiConfig', 'Meta'}:
        return False
    if short.endswith('Admin'):
        return False
    if span >= 25:
        return True
    if node is not None and span >= 12:
        branches = sum(
            1 for child in ast.walk(node)
            if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler))
        )
        return branches >= 3
    return False


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------
def audit_python(path: Path) -> FileReport:
    text = path.read_text(encoding='utf-8', errors='replace')
    lines = text.splitlines()
    report = FileReport(path=str(path))
    report.lines = len(lines)

    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith('#'):
            report.comment_lines += 1
        else:
            report.code_lines += 1
            # 行尾注释也算注释（但记在另一个桶里，便于分辨"块注释"与"顺手说明"）
            if '#' in raw and not stripped.startswith('#'):
                before = raw.split('#', 1)[0]
                if before.count('"') % 2 == 0 and before.count("'") % 2 == 0:
                    report.inline_comments += 1

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        report.undocumented.append(f'(语法错误，跳过 AST 分析: {exc})')
        return report

    report.module_has_docstring = bool(ast.get_docstring(tree))

    def walk(node, prefix=''):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f'{prefix}{child.name}'
                body = getattr(child, 'body', [])
                has_doc = bool(
                    body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                )
                if has_doc:
                    report.docstrings += 1
                else:
                    span = (child.end_lineno or child.lineno) - child.lineno + 1
                    kind = 'class' if isinstance(child, ast.ClassDef) else 'def'
                    if worth_documenting(name, span, child):
                        report.undocumented.append(f'{kind} {name}() (第 {child.lineno} 行, {span} 行)')
                walk(child, f'{name}.')
            elif isinstance(child, ast.ClassDef):
                walk(child, f'{prefix}{child.name}.')

    walk(tree)

    # 长函数：定义行数 ≥ 60 且函数内部没有注释
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = node.end_lineno or node.lineno
            span = end - node.lineno + 1
            if span < 60:
                continue
            segment = lines[node.lineno - 1:end]
            inner_comments = sum(
                1 for s in segment
                if s.strip().startswith('#') or ('#' in s and not s.strip().startswith('#'))
            )
            if inner_comments == 0:
                report.long_functions.append(f'{node.name}() {span} 行、内部 0 条注释')

    report.magic_numbers = find_magic_numbers(lines)
    return report


# ---------------------------------------------------------------------------
# Vue / JS / TS
# ---------------------------------------------------------------------------
BLOCK_COMMENT = re.compile(r'/\*.*?\*/', re.S)
LINE_COMMENT = re.compile(r'^\s*//')
TEMPLATE_COMMENT = re.compile(r'<!--.*?-->', re.S)

NUMBER_TOKEN = re.compile(r'(?<![\w.$])(\d{2,})(?![\w.])')


def is_placeholder(code: str) -> bool:
    """占位/跳过统计的代码行（注释里的内容、纯符号行等）"""
    stripped = code.strip()
    if not stripped:
        return True
    return stripped in {'{', '}', '};', ');', ']', '})', '>', '</template>'}


def count_js_comments(text: str) -> tuple[int, int, int]:
    """
    逐行判断注释与代码，返回 (注释行, 代码行, 块注释数)。

    ⚠️ 这里**必须逐行扫**，不能用 `re.findall(r'/\\*.*?\\*/', text, re.S)`：
    非贪婪匹配遇到"`/*` 开头但很久以后才有 `*/`"时会把中间**所有代码都算成注释行** ——
    实测 `frontend/src/router/index.js` 因此得出 51400% 的注释密度（注释行比总行数还多）。
    逐行状态机不会犯这种错，代价只是多几行代码。
    """
    in_block = False
    comment_lines = 0
    code_lines = 0
    blocks = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if in_block:
            comment_lines += 1
            if '*/' in line:
                in_block = False
            continue
        if line.startswith('/*'):
            blocks += 1
            comment_lines += 1
            # 同一行就闭合的情况（`/* x */`）
            if '*/' not in line[2:]:
                in_block = True
            continue
        if line.startswith('//'):
            comment_lines += 1
            continue
        if line.startswith('<!--'):
            comment_lines += 1
            continue
        code_lines += 1
        # 行尾块注释也算（比如 `page_size = 6  /* 默认每页 */`）
    return comment_lines, code_lines, blocks


def has_script_header_comment(text: str) -> bool:
    """
    `.vue` 文件有没有"能让人一眼知道这组件是干什么的"说明？

    ⚠️ 判据必须落在**脚本区或模板顶部**，而不是"文件第一个字符"：
      · 一个 2615 行的 `HistoryView.vue`，`<script>` 在第 363 行 ——
        在文件开头找注释，当然是找不到，于是它被误报成"无头注释"（实测 64 个误报）；
      · 反过来也不能只看"文件前 2500 字符里有没有块注释"，
        因为模板里的 `<!-- -->` 或样式里的注释都会被算进去。

    ⚠️ 还有一处**判据本身的错**（第 107 批修）：很多组件的说明
    **写在模板顶部的 `<!-- -->` 里**（`PestImportDialog`、`OfflineIndicator`
    都是这样，而且写得相当完整）。
    只看 `<script>` 之后会把它们误报成"零注释组件" —— 实测这两个组件的
    模板说明在全项目里都算好的，报出来纯属噪音。
    所以现在两条都认：**模板顶部有说明，或者脚本区开头有说明**。
    """
    # 1) 模板顶部的说明注释（`<template>` 之后的前 15 行内有 `<!-- ... -->`）
    template = re.search(r'<template[^>]*>', text)
    if template:
        head = '\n'.join(text[template.end():].split('\n')[:15])
        if '<!--' in head:
            return True

    # 2) 脚本区的说明（跳过 import 块 —— `App.vue` 的说明写在 14 行 import 之后）
    marker = re.search(r'<script[^>]*>', text)
    if not marker:
        return bool(BLOCK_COMMENT.search(text[:2000]))
    lines = text[marker.end():].split('\n')
    for raw in lines[:40]:
        line = raw.strip()
        if not line:
            continue
        if line.startswith(('/*', '//')):
            return True
        if line.startswith('import ') or line.startswith('} from '):
            continue
        # 走到第一行真正的代码了，还没见到注释 → 判定没有头注释
        return False
    return False


def audit_web(path: Path) -> FileReport:
    text = path.read_text(encoding='utf-8', errors='replace')
    lines = text.splitlines()
    report = FileReport(path=str(path))
    report.lines = len(lines)

    report.comment_lines, report.code_lines, _ = count_js_comments(text)
    report.code_lines = max(report.code_lines, 1)
    report.inline_comments = len(TEMPLATE_COMMENT.findall(text))

    # `.vue` 看脚本区开头；纯 js/ts 看文件开头
    if path.suffix == '.vue':
        report.module_has_docstring = has_script_header_comment(text)
    else:
        report.module_has_docstring = bool(BLOCK_COMMENT.search(text[:2000]))

    # "文档字符串"口径的文件级 JSDoc（`/** ... */`）
    report.docstrings = len(re.findall(r'/\*\*', text))

    # 缺注释的函数：定义前**紧邻**没有 `/** */` 或 `//` 说明
    for match in re.finditer(
        r'^(?P<indent>[ \t]*)(?:export\s+)?(?:async\s+)?function\s+(?P<fname>\w+)'
        r'|^(?P<indent2>[ \t]*)(?:export\s+)?const\s+(?P<cname>\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>',
        text, re.M,
    ):
        name = match.group('fname') or match.group('cname')
        if not name:
            continue
        start_line = text[:match.start()].count('\n')
        above = lines[max(0, start_line - 3):start_line]
        has_doc = any(s.strip().startswith(('//', '/*', '*')) for s in above)
        rest = lines[start_line:]
        depth = 0
        end_line = start_line
        for index, raw in enumerate(rest):
            depth += raw.count('{') - raw.count('}')
            end_line = start_line + index
            if index > 0 and depth <= 0:
                break
        span = end_line - start_line + 1
        segment = lines[start_line:end_line + 1]
        inner = sum(1 for s in segment if s.strip().startswith('//') or '/*' in s)

        if has_doc:
            report.docstrings += 1
        elif span >= 25 and inner == 0 and not SELF_DOCUMENTING.match(name):
            report.undocumented.append(f'function {name}() (第 {start_line + 1} 行, {span} 行)')

        if span >= 60 and inner == 0:
            report.long_functions.append(f'{name}() {span} 行、内部 0 条注释')

    report.magic_numbers = find_magic_numbers(lines)
    return report


# ---------------------------------------------------------------------------
# 公共
# ---------------------------------------------------------------------------
#: 明显是"展示/样式"而不是"业务阈值"的数字所在的关键字（命中就跳过）
COSMETIC_HINTS = re.compile(
    r'rgba?\(|#[0-9a-fA-F]{3,8}|var\(--|font-weight|margin|padding|width|height'
    r'|border|shadow|radius|opacity|z-index|blur|translate|scale|rotate'
    r'|font-size|line-height|top:|left:|right:|bottom:|gap:|flex:|grid'
    r'|rgb\(|hsl\(|deg\b|ms\b|px\b|rem\b|em\b|vh\b|vw\b|%\)',
    re.I,
)
#: SVG `path` 的 `d=` 属性里全是数字，不该算
SVG_HINT = re.compile(r'\sd="[MmLlHhVvCcSsQqTtAaZz0-9 .,\-]+"')
#: 中文说明性的"第 N 批"之类出现在字符串里
BATCH_HINT = re.compile(r'第\s*\d+\s*批')
#: 这些行里的数字是**协议/约定**而不是可调参数（HTTP 状态码、年份版本…）
CODE_HINT = re.compile(r'\bstatus\b|\bHTTP\b|\bcode\s*=|状态码')


def strip_string_literals(line: str) -> str:
    """
    把字符串字面量挖空，只留下"代码本身"。

    为什么必须这么做：1798 处噪音里很大一部分是**字符串里的数字** ——
    密码 `'SmokeTest!2026'`、时间 `'周一至周五 9:00-18:00'`、
    演示数据 `timestamp: '2026-09-27T10:20:00+08:00'`、法务文案里的"15 天"。
    这些是**内容**，不是"没人解释的魔法值"，报出来只会让报告失去意义。
    """
    out = []
    quote = None
    index = 0
    while index < len(line):
        char = line[index]
        if quote:
            if char == '\\':
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in ('"', "'", '`'):
            quote = char
            index += 1
            continue
        out.append(char)
        index += 1
    return ''.join(out)


def find_magic_numbers(lines: list[str]) -> list[str]:
    """
    找"裸数字且没有任何注释解释"的地方 —— 只报**可能真的是业务阈值**的。

    ⚠️ 这个检查最容易变成噪音源。第一版直接扫所有 ≥2 位数字，得出 1798 处，
    其中绝大多数是：
      · CSS 值（`rgba(255, 255, 255, 0.88)`、`font-weight: 700`、`blur(14px)`）
      · SVG 路径（`d="M12 2C6.48 2 2 6.48…"`）
      · 字符串里的内容（密码、时间、法务文案、演示数据）
      · 图表用的数据数组（`count: 125`）
    这些报出来只会让人不再看这份报告。现在逐层过滤：
    样式/SVG/注释文案 → 数据行 → **字符串字面量** → 协议码，剩下的才报。
    """
    found = []
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith(('#', '//', '*', '/*', '<!--')):
            continue
        # 行尾已有注释 → 认为解释过了
        if '#' in raw or '//' in raw or '/*' in raw:
            continue
        previous = lines[index - 1].strip() if index else ''
        if previous.startswith(('#', '//', '*', '/*', '<!--')):
            continue
        if COSMETIC_HINTS.search(stripped) or SVG_HINT.search(stripped) or BATCH_HINT.search(stripped):
            continue
        if CODE_HINT.search(stripped):
            continue
        # 整行是数据字面量（`{ name: '苹果黑星病', count: 125 }`）→ 不算"没人解释的阈值"
        if re.match(r'^[{\[]', stripped) and not re.search(r'(if|for|while|return|=\s*\w+\()', stripped):
            continue
        # 关键一步：挖掉字符串，只对代码部分找数字
        code_only = strip_string_literals(raw)
        for token in NUMBER_TOKEN.findall(code_only):
            if token in BENIGN_NUMBERS or token.startswith('0'):
                continue
            # 200~599 视作 HTTP 状态码
            if 200 <= int(token) <= 599:
                continue
            found.append(f'第 {index + 1} 行: {token}   │ {stripped[:70]}')
            break   # 一行只报一个，避免刷屏
    return found


def iter_source_files(root: Path, only: str | None = None):
    dirs = [only] if only else SCAN_DIRS
    for directory in dirs:
        base = root / directory
        if not base.exists():
            continue
        for path in sorted(base.rglob('*')):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            yield path


def badness(report: FileReport) -> float:
    """缺注释"严重度"：只用来排序，不用来做结论 —— 数字背后的清单才是要看的东西"""
    score = 0.0
    if not report.module_has_docstring:
        score += 2
    score += len(report.undocumented) * 0.6
    score += len(report.magic_numbers) * 0.05
    score += len(report.long_functions) * 1.5
    if report.lines >= LONG_FILE and report.density < LOW_DENSITY:
        score += 2
    return score


def print_summary(reports: list[FileReport]) -> int:
    """按目录分组：一眼看出"哪个模块整体缺注释"，而不是陷在单个文件里"""
    groups: dict[str, list[FileReport]] = {}
    for report in reports:
        parts = report.path.split('/')
        key = '/'.join(parts[:2]) if len(parts) > 1 else parts[0]
        groups.setdefault(key, []).append(report)

    print('=' * 84)
    print('按模块分组的注释覆盖')
    print('=' * 84)
    print(f"{'模块':<28}{'文件':>5}{'行数':>8}{'注释行':>8}{'密度':>8}{'无头注释':>9}{'缺文档成员':>11}{'长函数':>7}")
    print('-' * 84)
    for key, items in sorted(groups.items(), key=lambda kv: -sum(r.lines for r in kv[1])):
        lines = sum(r.lines for r in items)
        comments = sum(r.comment_lines for r in items)
        headless = sum(1 for r in items if not r.module_has_docstring)
        members = sum(len(r.undocumented) for r in items)
        longf = sum(len(r.long_functions) for r in items)
        print(f'{key:<28}{len(items):>5}{lines:>8}{comments:>8}'
              f'{comments / max(lines, 1):>7.1%}{headless:>9}{members:>11}{longf:>7}')
    print('-' * 84)
    lines = sum(r.lines for r in reports)
    comments = sum(r.comment_lines for r in reports)
    print(f"{'合计':<28}{len(reports):>5}{lines:>8}{comments:>8}{comments / max(lines, 1):>7.1%}"
          f"{sum(1 for r in reports if not r.module_has_docstring):>9}"
          f"{sum(len(r.undocumented) for r in reports):>11}"
          f"{sum(len(r.long_functions) for r in reports):>7}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='注释覆盖审计')
    parser.add_argument('--path', help='只审某个子目录')
    parser.add_argument('--top', type=int, default=25, help='列出最差的 N 个文件')
    parser.add_argument('--json', action='store_true', help='输出 JSON')
    parser.add_argument('--min-lines', type=int, default=60, help='小于这个行数的文件不列入问题清单')
    parser.add_argument('--members', action='store_true', help='列出所有缺文档字符串的成员')
    parser.add_argument('--members-file', help='只列这个文件里的缺失成员')
    parser.add_argument('--summary', action='store_true', help='按目录分组给摘要')
    args = parser.parse_args()

    reports: list[FileReport] = []
    for path in iter_source_files(PROJECT_ROOT, args.path):
        try:
            report = audit_python(path) if path.suffix == '.py' else audit_web(path)
        except Exception as exc:  # noqa: BLE001
            print(f'!! 审计失败 {path}: {exc}', file=sys.stderr)
            continue
        report.path = str(path.relative_to(PROJECT_ROOT)).replace('\\', '/')
        reports.append(report)

    if args.json:
        print(json.dumps([r.to_dict() for r in reports], ensure_ascii=False, indent=2))
        return 0

    if args.members or args.members_file:
        for report in reports:
            if args.members_file and args.members_file not in report.path:
                continue
            if not report.undocumented:
                continue
            print(f'\n=== {report.path} （{len(report.undocumented)} 个）===')
            for item in report.undocumented:
                print(f'  · {item}')
        return 0

    if args.summary:
        return print_summary(reports)

    total_lines = sum(r.lines for r in reports)
    total_comments = sum(r.comment_lines for r in reports)
    no_docstring = [r for r in reports if not r.module_has_docstring]
    with_undocumented = [r for r in reports if r.undocumented]

    print('=' * 78)
    print(f'注释覆盖审计 —— {len(reports)} 个源文件 / {total_lines} 行')
    print('=' * 78)
    print(f'  注释行合计      : {total_comments}（整体密度 {total_comments / max(total_lines, 1):.1%}）')
    print(f'  文件顶部无头注释: {len(no_docstring)} 个')
    print(f'  含未注释类/函数 : {len(with_undocumented)} 个文件')
    print(f'  缺文档字符串成员: {sum(len(r.undocumented) for r in reports)} 个')

    ranked = sorted(
        (r for r in reports if r.lines >= args.min_lines),
        key=badness, reverse=True,
    )

    print('\n' + '─' * 78)
    print(f'最需要补注释的 {args.top} 个文件（行数 ≥ {args.min_lines}）')
    print('─' * 78)
    for report in ranked[:args.top]:
        flags = []
        if not report.module_has_docstring:
            flags.append('无头注释')
        if report.undocumented:
            flags.append(f'{len(report.undocumented)} 个成员无文档')
        if report.long_functions:
            flags.append(f'{len(report.long_functions)} 个长函数无注释')
        if report.magic_numbers:
            flags.append(f'{len(report.magic_numbers)} 处魔法数')
        print(f'{badness(report):5.1f}  {report.density:5.1%}  {report.lines:5}行  '
              f'{report.path}')
        print(f'          └─ {"; ".join(flags)}')

    # 分组明细
    print('\n' + '─' * 78)
    print('明细：文件顶部没有头注释（只列 ≥ 60 行的）')
    print('─' * 78)
    for report in sorted(no_docstring, key=lambda r: -r.lines):
        if report.lines >= args.min_lines:
            print(f'  {report.lines:5}行  {report.path}')

    print('\n' + '─' * 78)
    print('明细：长函数内部 0 条注释（≥60 行且无说明）')
    print('─' * 78)
    for report in sorted(reports, key=lambda r: -len(r.long_functions)):
        for item in report.long_functions:
            print(f'  {report.path}  →  {item}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
