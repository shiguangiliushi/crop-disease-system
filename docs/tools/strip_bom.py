#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
去掉源码文件里的 UTF-8 BOM（第 57 批）

为什么需要它：本会话里多次用 PowerShell 的 `Set-Content -Encoding UTF8` 写文件，
在 Windows PowerShell 5.1 语义下会**写入 BOM**（`EF BB BF`），
于是 oxlint 的 `no-irregular-whitespace` 报错、diff 里也会多出看不见的字符。
这个脚本把 `frontend/src`（以及可选的其它目录）下所有文本源码的 BOM 统一清掉。

用法：
    python docs/tools/strip_bom.py                 # 默认清理 frontend/src
    python docs/tools/strip_bom.py frontend/src docs
    python docs/tools/strip_bom.py --check         # 只检查不修改（退出码 1 表示有 BOM）
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DIRS = ['frontend/src']
SUFFIXES = ('.js', '.ts', '.vue', '.json', '.md', '.css', '.py')
BOM = b'\xef\xbb\xbf'


def iter_files(paths):
    for relative in paths:
        base = os.path.join(ROOT, relative)
        if os.path.isfile(base):
            yield base
            continue
        for current, _dirs, files in os.walk(base):
            for name in files:
                if name.endswith(SUFFIXES):
                    yield os.path.join(current, name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('paths', nargs='*', default=DEFAULT_DIRS)
    parser.add_argument('--check', action='store_true', help='只检查，不修改')
    args = parser.parse_args()

    found = []
    for path in iter_files(args.paths):
        try:
            with open(path, 'rb') as handle:
                raw = handle.read(3)
        except OSError:
            continue
        if raw == BOM:
            found.append(os.path.relpath(path, ROOT))
            if not args.check:
                with open(path, 'rb') as handle:
                    content = handle.read()
                with open(path, 'wb') as handle:
                    handle.write(content[len(BOM):])

    if not found:
        print('✅ 没有发现 BOM')
        return 0

    if args.check:
        print(f'❌ 发现 {len(found)} 个文件带 BOM：')
        for path in found:
            print('   ', path)
        return 1

    print(f'已去掉 {len(found)} 个文件的 BOM：')
    for path in found:
        print('   ', path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
