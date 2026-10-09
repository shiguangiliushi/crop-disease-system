"""检查（并可选修复）工作区里的行尾符是否符合 .gitattributes 的约定

为什么需要它
----------------------------------------------------------------------------
本仓库在 `.gitattributes` 里明确约定「**仓库里存 LF，工作区也检出 LF**」
（`* text=auto eol=lf`，`.bat` 例外），理由是同一份文件在不同机器上会 diff 出整文件差异。

但 Windows 上有些写入方式**默认写 CRLF**：
  · PowerShell 的 `Set-Content` / `Out-File`（本项目已经因此踩过两次坑：
    第 136 批的"8 个文件被写进 CRLF"、以及更早的 BOM 问题）；
  · 部分编辑器的默认设置。
于是工作区里会出现"某些文件 CRLF、某些 LF"的混合状态 ——
提交时 Git 会按 `.gitattributes` 归一化（所以 diff 未必难看），
但 `git status` 会一直刷 "CRLF will be replaced by LF" 警告，
而**混合行尾的文件**在别人的编辑器里可能整文件显示为改动。

用法：
    python docs/tools/check_line_endings.py            # 只检查（有 CRLF 就退出码 1）
    python docs/tools/check_line_endings.py --fix      # 就地转成 LF
    python docs/tools/check_line_endings.py --fix backend frontend/src
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: 按 .gitattributes 应当保持 LF 的扩展名
LF_EXTENSIONS = {
    '.py', '.js', '.mjs', '.cjs', '.ts', '.vue', '.json', '.md', '.txt',
    '.yml', '.yaml', '.html', '.css', '.scss', '.sql', '.conf', '.sh', '.toml',
}
#: 例外：批处理脚本用 CRLF 更稳妥（.gitattributes 末尾也是这么写的）
CRLF_EXTENSIONS = {'.bat', '.cmd'}

SKIP_DIRS = {
    'node_modules', '.git', 'venv', '.venv', '__pycache__', 'dist',
    'staticfiles', 'dsh-shots', 'backups', 'media', 'logs', '.idea',
    'playwright-report', 'test-results',
}


def iter_files(paths):
    for base in paths:
        full = os.path.join(ROOT, base) if not os.path.isabs(base) else base
        if os.path.isfile(full):
            yield full
            continue
        for dirpath, dirnames, filenames in os.walk(full):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                yield os.path.join(dirpath, name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('paths', nargs='*', default=['backend', 'frontend/src',
                                                     'frontend/scripts', 'frontend/e2e',
                                                     'docs', 'mobile/lib', 'deploy', 'tools'])
    parser.add_argument('--fix', action='store_true', help='就地转成 LF')
    args = parser.parse_args()

    crlf, mixed, fixed = [], [], []
    checked = 0

    for path in iter_files(args.paths):
        ext = os.path.splitext(path)[1].lower()
        if ext in CRLF_EXTENSIONS or ext not in LF_EXTENSIONS:
            continue
        try:
            with open(path, 'rb') as handle:
                raw = handle.read()
        except OSError:
            continue
        checked += 1
        if b'\r\n' not in raw:
            continue
        rel = os.path.relpath(path, ROOT)
        # 混合行尾：既有 CRLF 又有"裸 LF"
        only_lf = raw.replace(b'\r\n', b'')
        if b'\n' in only_lf:
            mixed.append(rel)
        else:
            crlf.append(rel)
        if args.fix:
            with open(path, 'wb') as handle:
                handle.write(raw.replace(b'\r\n', b'\n'))
            fixed.append(rel)

    print(f'检查了 {checked} 个文本文件（按 .gitattributes 应为 LF）')
    if fixed:
        print(f'\n✅ 已转成 LF：{len(fixed)} 个')
        for rel in fixed:
            print(f'  · {rel}')
        return 0
    if crlf or mixed:
        print(f'\n❌ 行尾不是 LF：{len(crlf) + len(mixed)} 个'
              f'（其中"混合行尾" {len(mixed)} 个 —— 这种最容易被别人看成整文件改动）')
        for rel in mixed:
            print(f'  · [混合] {rel}')
        for rel in crlf:
            print(f'  · [CRLF] {rel}')
        print('\n修法：python docs/tools/check_line_endings.py --fix')
        return 1
    print('\n✅ 全部是 LF')
    return 0


if __name__ == '__main__':
    sys.exit(main())
