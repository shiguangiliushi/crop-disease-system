"""页面"空白量"体检工具（第 31 批）

背景
----
用户反馈"所有页面空白的地方还是太多了"。这类问题靠肉眼看长图很难比较，
于是把它变成一个可量化的指标：**长图里最长的连续空白竖带**。

原理
----
逐行计算灰度标准差：一行几乎均匀（std 很小）说明这一行既没有文字、
也没有卡片边框/色块边界 —— 就是视觉上的"空白带"。
统计连续空白行的最长一段，以及空白行占比。
改造前最长的空白带有 189px（首页）/163px（我的收藏）/142px（病害百科），
改造后全部降到 80px 以内（剩下的只是内容与页脚之间的正常间距）。

用法
----
1. 先用 Playwright 把各页面截成长图（fullPage），放在同一个目录里，例如：

       // _shot.mjs
       const page = await ctx.newPage();
       await page.goto('http://127.0.0.1:5173/detect');
       await page.waitForTimeout(2500);
       await page.screenshot({ path: 'shots/06-detect.png', fullPage: true });

   注意：一定要等页面数据加载完再截，否则会把骨架屏当成"内容"。

2. 运行本工具：

       python docs/tools/check_page_whitespace.py shots

   依赖 Pillow（crop_env 环境自带）；需要在项目根目录或 frontend 目录下运行。
"""
import glob
import os
import sys

from PIL import Image

# 灰度标准差小于此值即视为"该行没有内容"
THRESHOLD = 2.0
# 连续空白带短于这个像素数就不值得关注（属于正常留白）
MIN_BAND = 40


def analyse(path):
    img = Image.open(path).convert("L")
    width, height = img.size
    px = img.load()

    blank = []
    for y in range(height):
        vals = [px[x, y] for x in range(0, width, 4)]
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        blank.append(variance**0.5 < THRESHOLD)

    # 最长连续空白段
    best_len = best_start = run_len = run_start = 0
    for y, is_blank in enumerate(blank):
        if is_blank:
            if run_len == 0:
                run_start = y
            run_len += 1
            if run_len > best_len:
                best_len, best_start = run_len, run_start
        else:
            run_len = 0

    # 前 3 段值得关注的空白带
    bands, run_len, run_start = [], 0, 0
    for y, is_blank in enumerate(blank + [False]):
        if is_blank:
            if run_len == 0:
                run_start = y
            run_len += 1
        elif run_len:
            if run_len >= MIN_BAND:
                bands.append((run_start, run_len))
            run_len = 0
    bands.sort(key=lambda item: -item[1])

    return {
        "height": height,
        "blank_ratio": sum(blank) / height,
        "max_run": best_len,
        "max_run_at": best_start,
        "bands": bands[:3],
    }


def main():
    directory = sys.argv[1] if len(sys.argv) > 1 else "_vv"
    files = sorted(glob.glob(os.path.join(directory, "*.png")))
    if not files:
        print(f"没有在 {directory} 下找到 PNG 长图，请先截图。")
        return

    rows = [(os.path.basename(p)[:-4], analyse(p)) for p in files]
    rows.sort(key=lambda item: -item[1]["max_run"])

    print(f"{'页面':<24}{'高度':>7}{'最长空白':>10}{'位置':>8}{'空白占比':>10}   前3段空白带(起点,长度)")
    for name, r in rows:
        bands = "  ".join(f"({s},{l})" for s, l in r["bands"])
        print(
            f"{name:<24}{r['height']:>7}{r['max_run']:>10}{r['max_run_at']:>8}"
            f"{r['blank_ratio'] * 100:>9.1f}%   {bands}"
        )

    print(
        "\n判读：最长空白带 < 80px 基本就是「内容与页脚之间的正常间距」；"
        "超过 130px 说明页面底部有一段明显的空。"
    )


if __name__ == "__main__":
    main()
