#!/usr/bin/env python
"""
整理 README 用的截图（第 153 批）

## 为什么要有这个脚本

仓库里 33 张界面截图全在 `frontend/dsh-shots/` —— 那个目录是 **gitignore** 的
（几十 MB，不该入库）。于是 GitHub 上的 README **一张图都没有**，
而 README 恰恰是简历链接点进来的首屏。

这个脚本把**选定的**几张：① 从 `frontend/dsh-shots/` 复制过来（管理端）；
② 缩放到宽度 ≤ 1200；③ 转成 WebP 后写入 `docs/images/`（**入库**目录）。

**为什么是 WebP**：第一版我存 PNG（还开了 `optimize=True`），结果 8 张图合计 2.8 MB，
其中两张**反而更大**了（PNG 对"照片 + 界面"这种内容本来就压不动）。
换 WebP（quality 88）后同样清晰、体积降到约三分之一，GitHub 的 Markdown 也支持。

农户端那几张由 `frontend/scripts/capture-docs-shots.mjs` 生成（第 160 批起；
它用**真实管理员账号 admin** 一次截全 8 张，旧的 capture-readme-shots.mjs 已被它取代）
（它们原本不存在 —— 33 张截图里全是管理端与登录页）。

用法：
    python docs/tools/optimize_readme_images.py                 # 整理 + 缩放 + 转 WebP
    python docs/tools/optimize_readme_images.py --max-width 1000
    python docs/tools/optimize_readme_images.py --format png     # 需要 PNG 时
"""
import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / 'frontend' / 'dsh-shots'
OUT = ROOT / 'docs' / 'images'

#: 要入库的管理端截图：源文件名 → 目标文件名（不含扩展名）
#:
#: ⚠️ 第 189 批：`admin-health`（「系统 · 系统健康」）是**新增**的一张 ——
#: README 的图说里一直有"系统健康"，但那张图从来没进过库（第 185 批把它并进「系统」页之后
#: 更是连入口都变了）。源文件由 `frontend/scripts/capture-docs-shots.mjs` 生成；
#: 其余几张的地址也在这一批从旧地址（/admin/forum、/admin/audit-logs…）改成了页签地址。
ADMIN_SHOTS = {
    'admin-console-dashboard.png': 'admin-dashboard',
    'admin-forum.png': 'admin-forum',
    'admin-audit-log.png': 'admin-audit-log',
    'admin-comment-restore.png': 'admin-comment-restore',
    'admin-health.png': 'admin-health',
    # 第 229 批新增：**助手质量看板**（降级率 / 知识库缺口 / 没用反馈 / token 与延迟）
    'admin-assistant-quality.png': 'admin-assistant-quality',
}

#: 农户端（由 capture-docs-shots.mjs 生成，这里只负责缩放与转码）
FARMER_SHOTS = (
    'farmer-home',
    'farmer-detect-result',
    'farmer-forum',
    'farmer-wiki',
    # 第 202 批新增：智能问答页（第 198 批做的独立问答页）。
    # 它此前**没有截图** —— README 的界面一览里因此看不出这个功能存在。
    'farmer-assistant',
    # 第 229 批新增：问答页"选好图还没发"的状态（说明能传图）
    'farmer-assistant-answer',
)

FORMAT_ARGS = {
    'webp': {'format': 'WEBP', 'quality': 88, 'method': 6},
    'png': {'format': 'PNG', 'optimize': True},
    'jpg': {'format': 'JPEG', 'quality': 90, 'optimize': True},
}


def save_as(source: Path, target: Path, max_width: int, fmt: str):
    """缩放 + 转码；返回 (原大小KB, 新大小KB)"""
    before = source.stat().st_size / 1024
    with Image.open(source) as image:
        if image.mode in ('RGBA', 'P') and fmt in ('jpg',):
            image = image.convert('RGB')
        if image.width > max_width:
            ratio = max_width / image.width
            image = image.resize((max_width, round(image.height * ratio)), Image.LANCZOS)
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, **FORMAT_ARGS[fmt])
    return before, target.stat().st_size / 1024


def main():
    parser = argparse.ArgumentParser(description='整理 README 用的截图')
    parser.add_argument('--max-width', type=int, default=1200)
    parser.add_argument('--format', choices=sorted(FORMAT_ARGS), default='webp')
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    # ⚠️ 清理旧格式必须放在**转码之后**：第一版放在最前面，于是把农户端那几张 PNG
    #    （它们正是本次的输入）当成"旧格式"删掉了，脚本接着报"文件不存在"。
    written = set()
    written_stems = set()      # 本次真正重新生成过的文件名（不含扩展名）

    missing = []
    for source_name, target_stem in ADMIN_SHOTS.items():
        source = SHOTS / source_name
        if not source.exists():
            missing.append(str(source.relative_to(ROOT)))
            continue
        target = OUT / f'{target_stem}.{args.format}'
        before, after = save_as(source, target, args.max_width, args.format)
        written.add(target)
        written_stems.add(target.stem)
        print(f'  · {target.name}：{before:.0f} KB → {after:.0f} KB')

    for stem in FARMER_SHOTS:
        # ⚠️ 源文件在两个地方都找一遍：第 153 批那版采集脚本直接写进 docs/images/，
        #    第 160 批的 capture-docs-shots.mjs 写在 frontend/dsh-shots/。
        #    只认一个目录的话，另一边跑完就会被当成"源文件不存在"，接着在清理阶段
        #    把已经入库的 WebP 删掉 —— 第 160 批就这么误删过 4 张 README 图。
        source = next(
            (candidate for candidate in (SHOTS / f'{stem}.png', OUT / f'{stem}.png')
             if candidate.exists()),
            None,
        )
        if source is None:
            missing.append(f'{stem}.png（frontend/dsh-shots/ 与 docs/images/ 下都没有）')
            continue
        if args.format == 'png':
            before, after = save_as(source, source, args.max_width, 'png')
            target = source
        else:
            target = OUT / f'{stem}.{args.format}'
            before, after = save_as(source, target, args.max_width, args.format)
        written.add(target)
        written_stems.add(target.stem)
        print(f'  · {target.name}：{before:.0f} KB → {after:.0f} KB')

    # 转码完成后再清理：把上一次留下的其它格式（例如换成 WebP 后残留的 PNG）删掉。
    #
    # ⚠️⚠️ 只删"本次确实重新生成过同名文件"的旧格式。
    # 第一版是"凡是本目录里其它图片格式一律删" —— 于是只要某个源文件缺失，
    # 它对应的那张**已经入库的图**就会被顺手删掉（README 立刻变成断链）。
    # 删除是不可逆的，宁可留下一个多余文件，也不要删掉一张还有用的图。
    for stale in OUT.glob('*'):
        if stale in written or not stale.is_file():
            continue
        if stale.suffix.lstrip('.').lower() not in FORMAT_ARGS:
            continue
        if stale.stem not in written_stems:
            print(f'  · 保留（本次没有重新生成同名文件）：{stale.name}')
            continue
        stale.unlink()
        print(f'  · 清理旧格式：{stale.name}')

    total = sum(f.stat().st_size for f in OUT.glob('*') if f.is_file()) / 1024
    print(f'\ndocs/images/ 现在有 {len(list(OUT.glob("*")))} 个文件，合计 {total:.0f} KB')

    if missing:
        print('\n⚠️ 下列文件不存在（先跑 frontend/scripts/capture-docs-shots.mjs，或检查截图名）：')
        for item in missing:
            print('   ·', item)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
