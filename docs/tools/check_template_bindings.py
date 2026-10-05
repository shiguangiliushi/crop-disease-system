# -*- coding: utf-8 -*-
"""模板/脚本一致性检查（第 16 批新增的校验工具）

用法：python docs/tools/check_template_bindings.py   （任意 Python 3 均可运行）

找出两类缺陷 —— 构建、lint、type-check 都不会报错，只在运行时才炸：
  A. 模板引用、但 <script> 中从未声明的标识符
     （本批真实案例：DetectionHistoryView 的 handleDelete、EditPostView 的 isDev）
  B. Options API + setup() 的组件里，模板引用、脚本也声明了、但**没有从 return 出去**
     的标识符（本批真实案例：PostDetailView 的 loadMoreReplies / loadingMoreReplies）
"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / 'frontend' / 'src'
SKIP = ('_deprecated',)

# 模板里可能出现的、非 setup 返回项的标识符（模板局部变量、内置对象等）
BUILTIN = {
    'true', 'false', 'null', 'undefined', 'this', 'new', 'typeof', 'in', 'of', 'instanceof',
    'NaN', 'Infinity', 'Math', 'Date', 'JSON', 'Object', 'Array', 'String', 'Number',
    'Boolean', 'RegExp', 'console', 'window', 'document', 'parseInt', 'parseFloat',
    'isNaN', 'encodeURIComponent', 'decodeURIComponent', 'setTimeout', 'clearTimeout',
    'item', 'index', 'key', 'value', 'props', 'attrs', 'slots', 'ref', 'emit',
    'el', 'event', 'e', 'n', 'i', 'x', 'v', 'row', 'scope', 'comment', 'reply', 'post',
    'board', 'pest', 'news', 'user', 'file', 'form', 'tab', 'node', 'option', 'opt',
    'crop', 'type', 'val', 'obj', 'result', 'res', 'data', 'error', 'err', 'msg',
    'text', 'str', 'num', 'id', 'label', 'name', 'title', 'content', 'date', 'day',
    'month', 'year', 'page', 'size', 'total', 'count', 'list', 'arr', 'map', 'set',
    'fn', 'cb', 'arg', 'args', 'payload', 'index1', 'entry',
    # Vue 模板内置
    '$event', '$refs', '$slots', '$attrs', '$props', '$emit', '$options', '$el', '$nextTick',
}


def strip_strings(expr):
    """去掉字符串/模板字面量内容，避免把里面的文本当成标识符"""
    expr = re.sub(r'`[^`]*`', ' ', expr, flags=re.S)
    expr = re.sub(r"'[^']*'", ' ', expr)
    expr = re.sub(r'"[^"]*"', ' ', expr)
    return expr


def balanced_block(text, start):
    """从 text[start] == '{' 开始，返回配对的整段（含首尾花括号）"""
    depth = 0
    for idx in range(start, len(text)):
        if text[idx] == '{':
            depth += 1
        elif text[idx] == '}':
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
    return text[start:]


def split_sfc(text):
    tpl = re.search(r'<template>(.*)</template>', text, re.S)
    scr = re.search(r'<script[^>]*>(.*?)</script>', text, re.S)
    return (tpl.group(1) if tpl else ''), (scr.group(1) if scr else '')


def template_expressions(tpl):
    tpl = re.sub(r'<!--.*?-->', ' ', tpl, flags=re.S)
    exprs = list(re.findall(r'\{\{(.*?)\}\}', tpl, re.S))
    exprs += re.findall(r'(?:v-[a-z-]+|:[a-zA-Z0-9_.-]+|@[a-zA-Z0-9_.-]+)="([^"]*)"', tpl)
    exprs += re.findall(r"'([A-Za-z_$][\w$]*)\s*\(", tpl)
    return exprs


def object_keys(block):
    """取出对象字面量的键名。

    按行解析（而不是靠前一个字符是不是 { 或 ,）——否则紧跟在注释行后面的
    简写属性（如 `// 方法` 换行后的 `handleLike,`）会被漏掉，产生假阳性。
    """
    keys = set()
    for raw in block.splitlines():
        line = re.sub(r'//.*$', '', raw).strip()
        if not line:
            continue
        m = re.match(r'^([A-Za-z_$][\w$]*)\s*[,}]?\s*$', line)  # 简写属性 / 最后一项
        if m:
            keys.add(m.group(1))
            continue
        m = re.match(r'^([A-Za-z_$][\w$]*)\s*[:(]', line)  # key: value / key(args)
        if m:
            keys.add(m.group(1))
    # 单行对象字面量 { a, b, c }
    for m in re.finditer(r'[{,]\s*([A-Za-z_$][\w$]*)\s*(?=[,}])', block):
        keys.add(m.group(1))
    return keys


def declared_names(script, tpl):
    names = set()
    for m in re.finditer(r'(?:const|let|var|function)\s+([A-Za-z_$][\w$]*)', script):
        names.add(m.group(1))
    for m in re.finditer(r'import\s+([A-Za-z_$][\w$]*)\s+from', script):
        names.add(m.group(1))
    for m in re.finditer(r'import\s*\{([^}]*)\}', script):
        for part in m.group(1).split(','):
            part = part.strip().split(' as ')[-1].strip()
            if part:
                names.add(part)
    for m in re.finditer(r'(?:setup|function\s+\w+)\s*\(([^)]*)\)', script):
        for part in m.group(1).split(','):
            part = part.strip().split('=')[0].strip()
            if re.fullmatch(r'[A-Za-z_$][\w$]*', part):
                names.add(part)
    # defineProps / props 声明
    for m in re.finditer(r'defineProps\s*(?:<[^>]*>)?\s*\(', script):
        brace = script.find('{', m.end())
        if brace != -1:
            names |= object_keys(balanced_block(script, brace))
    for m in re.finditer(r'props\s*:\s*\{', script):
        names |= object_keys(balanced_block(script, m.end() - 1))
    # Options API：data / computed / methods / watch 里的键也能在模板里用
    if not re.search(r'\bsetup\s*\(', script):
        for key in ('data', 'computed', 'methods', 'watch'):
            for m in re.finditer(key + r'\s*:\s*\{', script):
                names |= object_keys(balanced_block(script, script.find('{', m.end() - 1)))
            for m in re.finditer(key + r'\s*\(\s*[^)]*\)\s*\{', script):
                names |= object_keys(balanced_block(script, m.end() - 1))
    # v-for / v-slot / 作用域插槽引入的模板局部变量
    for m in re.finditer(r'v-for="\(?([^)"]*?)\)?\s+in\s', tpl):
        for part in m.group(1).split(','):
            part = part.strip()
            if re.fullmatch(r'[A-Za-z_$][\w$]*', part):
                names.add(part)
    for m in re.finditer(r'(?:v-slot(?::[^\s=]+)?|#\w+)="\{?([^}"]*)\}?"', tpl):
        for part in m.group(1).split(','):
            part = part.strip().split(':')[-1].strip()
            if re.fullmatch(r'[A-Za-z_$][\w$]*', part):
                names.add(part)
    return names


def free_identifiers(expr):
    expr = strip_strings(expr)
    found = set()
    for m in re.finditer(r'(?<![\w.$])([A-Za-z_$][\w$]*)', expr):
        ident = m.group(1)
        if ident in BUILTIN:
            continue
        before = expr[:m.start()]
        after = expr[m.end():]
        # a.b 里的 b 不是自由标识符
        if re.search(r'\.\s*$', before):
            continue
        # 对象字面量的键（形如 { key: 或 , key:）不是自由标识符
        if re.match(r'\s*:', after) and re.search(r'[{,]\s*$', before):
            continue
        found.add(ident)
    return found


problems = []
not_returned = []
files = [p for p in SRC.rglob('*.vue') if not any(s in p.parts for s in SKIP)]
for path in sorted(files):
    text = path.read_text(encoding='utf-8', errors='replace')
    tpl, scr = split_sfc(text)
    if not tpl:
        continue
    tpl = re.sub(r'<!--.*?-->', ' ', tpl, flags=re.S)
    names = declared_names(scr, tpl)

    used = set()
    for expr in template_expressions(tpl):
        used |= free_identifiers(expr)

    missing = sorted(i for i in used if i not in names)
    if missing:
        problems.append((path, missing))

    # B 类：setup() 的 return 是否覆盖模板用到的标识符
    if re.search(r'\bsetup\s*\(', scr):
        returned = set()
        for m in re.finditer(r'\breturn\s*\{', scr):
            brace = scr.find('{', m.end() - 1)
            block = balanced_block(scr, brace)
            returned |= object_keys(block)
            # 简写属性：return { foo, bar }
            for part in re.findall(r'(?:^|[{,])\s*([A-Za-z_$][\w$]*)\s*(?=[,}])', block):
                returned.add(part)
        for key in ('computed', 'methods', 'props', 'data'):
            for m in re.finditer(key + r'\s*:\s*\{', scr):
                returned |= object_keys(balanced_block(scr, scr.find('{', m.end() - 1)))
        lost = sorted(i for i in used if i in names and i not in returned)
        if lost:
            not_returned.append((path, lost))

print('检查文件数:', len(files))
if not problems and not not_returned:
    print('ALL CHECKS PASSED: 模板引用的标识符均已声明，且 setup 组件都已正确返回')
    sys.exit(0)
for path, missing in problems:
    print('  [未声明] %s -> %s' % (path.relative_to(SRC), ', '.join(missing)))
for path, lost in not_returned:
    print('  [未从 setup 返回] %s -> %s' % (path.relative_to(SRC), ', '.join(lost)))
sys.exit(1 if (problems or not_returned) else 0)
