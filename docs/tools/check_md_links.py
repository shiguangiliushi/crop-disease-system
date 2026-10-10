#!/usr/bin/env python
"""
检查所有 Markdown 里的**相对链接与图片**是否真实存在（第 153 批）

## 为什么要有它

这一批在"完善 .md"时踩到的两类问题，靠肉眼都很难发现：

1. `frontend/README.md` 一直是 **Vite 脚手架模板**，里面写着
   `npm run test:e2e -- tests/example.spec.ts` —— 而 `tests/` 这个目录在本项目里**根本不存在**
   （E2E 实际在 `e2e/*.spec.mjs`）。文字看着没问题，链接指的地方是空的。
2. 仓库里的截图一直放在 **gitignore** 的 `frontend/dsh-shots/`，README 引用的图
   **在 GitHub 上根本加载不出来** ✗ —— 这类问题（图片路径指向未入库目录）
   只有把"链接"与"是否被 git 跟踪"放在一起看才发现。

所以这个检查同时做两件事：**文件存在吗** + **它会被提交上去吗**。

用法：
    python docs/tools/check_md_links.py            # 检查仓库内所有 .md
    python docs/tools/check_md_links.py --verbose  # 连"跳过的外部链接"也列出来
退出码：0 = 全部可用；1 = 有断链或指向未入库文件。
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Markdown 链接 `[文字](目标)` 与 HTML `<img src="目标">`
MD_LINK = re.compile(r'!?\[[^\]]*\]\(([^)\s]+)', re.S)
HTML_SRC = re.compile(r'<(?:img|source)[^>]*\bsrc="([^"]+)"', re.I)
#: 围栏代码块（``` 或 ~~~）—— 里面的 `[x](y)` 与 `<img src>` 都是**示例**，不是真链接
FENCED = re.compile(r'^[ \t]*(```|~~~).*?^[ \t]*\1[ \t]*$', re.S | re.M)
#: 行内代码 `...` —— 同理（文档里常写 `` `src="x"` `` 举例）
INLINE_CODE = re.compile(r'`[^`\n]*`')

#: 不检查的东西
SKIP_PREFIXES = ('http://', 'https://', 'mailto:', '#', 'data:', 'tel:')
#: 目标里出现这些字符就**不是路径**（Vue 表达式、模板占位符、表格竖线等）
NOT_A_PATH = re.compile(r'[:|{}()<>?\s]')
#: 跳过这些目录里的 .md（第三方依赖/构建产物）
SKIP_DIRS = {'node_modules', 'venv', '.git', 'dist', 'staticfiles', 'dsh-shots', 'backups'}


def tracked_files():
    """git 跟踪的文件集合（用来判断"这文件会不会真的传上 GitHub"）"""
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                         text=True, encoding='utf-8', errors='replace')
    return {line.strip().replace('/', '\\') for line in (out.stdout or '').splitlines() if line.strip()}


def iter_markdown():
    for path in ROOT.rglob('*.md'):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def main():
    parser = argparse.ArgumentParser(description='检查 Markdown 里的相对链接')
    parser.add_argument('--verbose', action='store_true', help='连跳过的外部链接也打印')
    args = parser.parse_args()

    tracked = {name.lower() for name in tracked_files()}
    checked = skipped = 0
    problems = []

    for md in sorted(iter_markdown()):
        text = md.read_text(encoding='utf-8', errors='ignore')
        # 第 153 批修正：先去掉**代码块与行内代码**。
        # 文档里会举例写 `<img :src="slide.image">`、`? : @ | v-on:` 这类片段，
        # 它们是说明用的示例，不是真链接 —— 第一版因此报了 6 处假阳性。
        text = FENCED.sub('', text)
        text = INLINE_CODE.sub('', text)
        targets = [(m.group(1), '链接') for m in MD_LINK.finditer(text)]
        targets += [(m.group(1), '图片') for m in HTML_SRC.finditer(text)]

        for raw, kind in targets:
            target = raw.split('#')[0].strip()
            if not target or target.startswith(SKIP_PREFIXES):
                skipped += 1
                if args.verbose:
                    print(f'  （跳过外部/锚点）{md.relative_to(ROOT)} → {raw[:60]}')
                continue
            if NOT_A_PATH.search(target) or ('.' not in target and '/' not in target):
                # 看起来不是文件路径（Vue 绑定、模板占位符、纯锚点名等）
                skipped += 1
                if args.verbose:
                    print(f'  （跳过非路径）{md.relative_to(ROOT)} → {raw[:60]}')
                continue
            checked += 1
            # 相对当前 md 所在目录解析
            resolved = (md.parent / target.replace('/', '\\')).resolve()
            rel = md.relative_to(ROOT)
            if not resolved.exists():
                problems.append((str(rel), raw, kind, '文件不存在'))
                continue
            # 存在，但会不会被提交？（指向 gitignore 目录的图片在 GitHub 上是空图）
            try:
                rel_to_root = resolved.relative_to(ROOT)
            except ValueError:
                continue
            if str(rel_to_root).lower() not in tracked:
                problems.append((str(rel), raw, kind, '文件存在但**未入库**（GitHub 上会 404）'))

    print(f'检查了 {checked} 个相对链接/图片（跳过外部与锚点 {skipped} 个）')
    if problems:
        print(f'\n❌ 有 {len(problems)} 处问题：')
        for rel, raw, kind, why in problems:
            print(f'   · {rel} → {raw[:70]}（{kind}：{why}）')
        return 1
    print('✅ 所有相对链接与图片都存在，且都在 git 跟踪范围内')
    return 0


if __name__ == '__main__':
    sys.exit(main())
