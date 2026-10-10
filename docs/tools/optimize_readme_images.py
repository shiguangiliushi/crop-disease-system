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

农户端那几张由 `frontend/scripts/capture-readme-shots.mjs` 直接生成到同一目录
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
ADMIN_SHOTS = {
    'admin-console-dashboard.png': 'admin-dashboard',
    'admin-forum.png': 'admin-forum',
    'admin-audit-log.png': 'admin-audit-log',
    'admin-comment-restore.png': 'admin-comment-restore',
}

#: 农户端（由 capture-readme-shots.mjs 生成，这里只负责缩放与转码）
FARMER_SHOTS = (
    'farmer-home',
    'farmer-detect-result',
    'farmer-forum',
    'farmer-wiki',
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

    missing = []
    for source_name, target_stem in ADMIN_SHOTS.items():
        source = SHOTS / source_name
        if not source.exists():
            missing.append(str(source.relative_to(ROOT)))
            continue
        target = OUT / f'{target_stem}.{args.format}'
        before, after = save_as(source, target, args.max_width, args.format)
        written.add(target)
        print(f'  · {target.name}：{before:.0f} KB → {after:.0f} KB')

    for stem in FARMER_SHOTS:
        source = OUT / f'{stem}.png'          # 采集脚本产出的是 PNG
        if not source.exists():
            missing.append(str(source.relative_to(ROOT)))
            continue
        if args.format == 'png':
            before, after = save_as(source, source, args.max_width, 'png')
            target = source
        else:
            target = OUT / f'{stem}.{args.format}'
            before, after = save_as(source, target, args.max_width, args.format)
        written.add(target)
        print(f'  · {target.name}：{before:.0f} KB → {after:.0f} KB')

    # 转码完成后再清理：把上一次留下的其它格式（例如换成 WebP 后残留的 PNG）删掉
    for stale in OUT.glob('*'):
        if stale in written or not stale.is_file():
            continue
        if stale.suffix.lstrip('.').lower() in FORMAT_ARGS:
            stale.unlink()
            print(f'  · 清理旧格式：{stale.name}')

    total = sum(f.stat().st_size for f in OUT.glob('*') if f.is_file()) / 1024
    print(f'\ndocs/images/ 现在有 {len(list(OUT.glob("*")))} 个文件，合计 {total:.0f} KB')

    if missing:
        print('\n⚠️ 下列文件不存在（先跑 frontend/scripts/capture-readme-shots.mjs，或检查截图名）：')
        for item in missing:
            print('   ·', item)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
