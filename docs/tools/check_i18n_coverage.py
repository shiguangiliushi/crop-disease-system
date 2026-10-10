#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
多语言覆盖率统计（第 48 批）

用途：把"还有多少界面文案没做多语言"变成一个**可测量的数字**，而不是凭感觉说"做完了"。

判定方式（简单但够用）：
  · 扫描 frontend/src 下的 .vue 文件；
  · 找出模板里"裸露的中文文本"（出现在标签之间、或 title/placeholder/label/description
    等属性值里）；
  · 排除已经被 {{ $t('...') }} / {{ t('...') }} / :label="t(...)" 包裹的位置；
  · 排除注释、以及 script 里 console/日志用的中文字符串。

用法：
    python docs/tools/check_i18n_coverage.py            # 汇总 + 未覆盖最多的文件
    python docs/tools/check_i18n_coverage.py --file X   # 只看某个文件里的具体行
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, 'frontend', 'src')

# 模板里需要翻译的属性
TRANSLATABLE_ATTRS = (
    'label', 'placeholder', 'title', 'description', 'alt', 'content',
    'confirm-button-text', 'cancel-button-text', 'empty-text',
)

CHINESE = re.compile(r'[\u4e00-\u9fff]')
# 已经用 t()/$t() 包裹的表达式
I18N_CALL = re.compile(r"(\$t|\bt)\(\s*['\"]([^'\"]+)['\"]")
# 属性写法：label="中文..." 或 :label="'中文'"
ATTR = re.compile(r'(?::)?([a-zA-Z-]+)\s*=\s*"([^"]*)"')
# 标签之间的文本（**跨行也要能匹配**：第 58 批修正）
# 原来用逐行匹配 `>文字<`，导致这种写法完全统计不到：
#     <h1>
#       上传农作物图片进行识别
#     </h1>
# 于是"待翻译条数"长期被低估（DetectView 实际远多于 4 条）。
TEXT_NODE = re.compile(r'>([^<>{}]*[\u4e00-\u9fff][^<>{}]*)<', re.S)

#: **必须保持中文**的文案（第 153 批补）
#:
#: 覆盖率报告长期停在"待翻译 2 条"，而那 2 条是页脚的 ICP 备案号与公网安备号 ——
#: 它们按法规必须显示中文，翻译成英文反而是错的。与其为了凑 100% 硬翻，
#: 不如把它列成**白名单**并在报告里说明：这样"0 条待翻译"才是诚实的。
ZH_ALLOWED = re.compile(r'ICP备|公网安备|备案号')


def strip_comments(text):
    """去掉 HTML 注释（只用于模板区间，见 analyse 的说明）"""
    return re.sub(r'<!--.*?-->', '', text, flags=re.S)


def analyse(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as handle:
        raw = handle.read()

    # 只看 template 部分（script 里的中文多数是日志/注释/异常文案，不属于界面）。
    #
    # ⚠️ 第 58 批修正：**先在原文上按"第一个 <template> 到最后一个 </template>"截区间**，
    # 再只去 HTML 注释。此前是"先去注释、再正则匹配模板"，而 JS 风格的 `/* ... */`
    # 规则会把模板里出现的 `/*` 一直删到后面 CSS 段的 `*/`，**连真正的 `</template>` 一起删掉**
    # —— 表现为 DetectView 明明有 7 处中文却只统计出 4 处（模板被截断在 787 字符）。
    start = raw.find('<template>')
    end = raw.rfind('</template>')
    template = raw[start + len('<template>'):end] if (start >= 0 and end > start) else ''
    template = strip_comments(template)

    hits = []

    # ① 属性里的中文：仍然逐行看（属性一定在同一行或紧邻的行内）
    for line_no, line in enumerate(template.splitlines(), start=1):
        if not CHINESE.search(line):
            continue
        if I18N_CALL.search(line):
            # 这一行已经有 t(...)，跳过（多行属性写法会有误差，属可接受的近似）
            continue
        for attr_name, attr_value in ATTR.findall(line):
            if attr_name.lower() in TRANSLATABLE_ATTRS and CHINESE.search(attr_value):
                if ZH_ALLOWED.search(attr_value):
                    continue      # 白名单：备案号一类必须保持中文的文案
                hits.append((line_no, attr_value.strip()[:60]))

    # ② 标签之间的中文：在**整段模板**上匹配，因此跨行写法也能抓到了
    for match_obj in TEXT_NODE.finditer(template):
        value = match_obj.group(1)
        if not CHINESE.search(value):
            continue
        if ZH_ALLOWED.search(value):
            continue              # 白名单：同上
        # 把匹配起点换算成行号，便于 --file 定位
        line_no = template.count('\n', 0, match_obj.start()) + 1
        cleaned = ' '.join(value.split())[:60]
        hits.append((line_no, cleaned))

    # 同一行/同一段文案可能被属性与文本两条规则各计一次，这里按 (行号, 文案) 去重
    unique = []
    seen = set()
    for line_no, value in hits:
        key = (line_no, value)
        if key in seen:
            continue
        seen.add(key)
        unique.append((line_no, value))
    return unique


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', help='只输出某个文件（路径关键字）的具体行')
    parser.add_argument('--top', type=int, default=15, help='列出未覆盖最多的前 N 个文件')
    args = parser.parse_args()

    results = []
    for base, _dirs, files in os.walk(SRC):
        # 第 53 批：跳过已废弃目录（里面的组件不再随应用发布，统计它们只会虚报工作量）
        if '_deprecated' in base.split(os.sep):
            continue
        for name in files:
            if not name.endswith('.vue'):
                continue
            path = os.path.join(base, name)
            hits = analyse(path)
            results.append((os.path.relpath(path, SRC), hits))

    total_files = len(results)
    covered = [item for item in results if not item[1]]
    total_hits = sum(len(hits) for _rel, hits in results)

    if args.file:
        for rel, hits in results:
            if args.file.lower() in rel.lower():
                print(f'\n=== {rel}（{len(hits)} 处未翻译）===')
                for line_no, value in hits:
                    print(f'  L{line_no}: {value}')
        return 0

    print('多语言覆盖统计（扫描前端的 .vue 模板）')
    print(f'  组件总数：{total_files}')
    print(f'  已无裸露中文的组件：{len(covered)}（{len(covered) / max(1, total_files) * 100:.1f}%）')
    print(f'  仍待翻译的文案条数：{total_hits}')

    pending = sorted([item for item in results if item[1]], key=lambda item: -len(item[1]))
    print(f'\n未覆盖最多的 {args.top} 个文件：')
    for rel, hits in pending[:args.top]:
        print(f'  {len(hits):>4}  {rel}')

    print('\n提示：本次多语言覆盖"主链路"（顶栏/页脚/登录/首页关键区块/病害预警/种植日历），')
    print('      其余页面按此表逐批推进；用 --file <关键字> 可查看具体待翻译行。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
