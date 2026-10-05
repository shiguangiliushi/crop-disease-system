# -*- coding: utf-8 -*-
"""
Font Awesome 图标体检（第 28 批）

背景（真实故障）：`.fas fa-trash` / `fa-xmark` / `fa-reply` / `fa-sign-out-alt` 等图标
在页面上显示成"方框里一个叉"，而 `fa-bookmark` / `fa-paper-plane` 却正常。
根因不是类名写错，而是 **图标伪元素被解析成字重 400**（regular 字体只含少量图标），
详见 `src/assets/theme.css` 里那段修复说明。为了以后不再踩坑，本脚本做三层体检：

  1. **类名是否存在**：源码里用到的 `fa-*` 是否在 Font Awesome 的 CSS 里有定义
     （FA7 保留了部分旧别名；拼错的名字会被查出来）；
  2. **是不是 shim**：少数旧图标在 FA7 里改成"直接用某个普通字符"（如 `fa-percentage` → `%`）
     —— 这类不算缺失，但会在非图标字体下渲染；
  3. **字形是否存在**：把码点拿到对应字体文件（solid / regular / brands）的 cmap 里核对。
     这一步需要 `brotli` + `fontTools`（项目环境 crop_env 没有 brotli；
     可用 base anaconda：`C:\\Users\\zhx\\anaconda3\\python.exe`），缺少时自动跳过。

用法（项目根目录）：
    python docs\\tools\\check_fontawesome_icons.py
退出码 0 = 没问题；1 = 有缺失。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, 'frontend', 'src')
FA = os.path.join(ROOT, 'frontend', 'node_modules', '@fortawesome', 'fontawesome-free')
CSS = os.path.join(FA, 'css', 'all.min.css')

# 类名前缀 → 对应字体文件
STYLE_FONTS = {
    'fab': 'fa-brands-400.woff2',
    'fa-brands': 'fa-brands-400.woff2',
    'far': 'fa-regular-400.woff2',
    'fa-regular': 'fa-regular-400.woff2',
    'fas': 'fa-solid-900.woff2',
    'fa-solid': 'fa-solid-900.woff2',
    'fa': 'fa-solid-900.woff2',
    'fa-classic': 'fa-solid-900.woff2',
}
DEFAULT_FONT = 'fa-solid-900.woff2'

# 常见 FA5 → FA7 改名建议
RENAMES = {
    'fa-sign-out-alt': 'fa-right-from-bracket（FA7 仍保留该别名，注意字重修复即可）',
    'fa-search': 'fa-magnifying-glass',
    'fa-edit': 'fa-pen-to-square',
    'fa-trash-alt': 'fa-trash-can',
    'fa-times': 'fa-xmark',
    'fa-check-circle': 'fa-circle-check',
    'fa-exclamation-triangle': 'fa-triangle-exclamation（FA7 仍保留别名）',
    'fa-info-circle': 'fa-circle-info（FA7 仍保留别名）',
    'fa-question-circle': 'fa-circle-question',
    'fa-user-circle': 'fa-circle-user',
    'fa-map-marker-alt': 'fa-location-dot',
    'fa-sync-alt': 'fa-rotate',
    'fa-comment-alt': 'fa-comment-dots',
    'fa-file-alt': 'fa-file-lines',
    'fa-shield-alt': 'fa-shield-halved',
    'fa-calendar-alt': 'fa-calendar-days',
    'fa-percentage': 'fa-percent',
}

# 这些是尺寸/动效类，不是图标
SKIP = {
    'fa-fw', 'fa-lg', 'fa-xs', 'fa-sm', 'fa-2x', 'fa-3x', 'fa-4x', 'fa-5x', 'fa-6x',
    'fa-spin', 'fa-pulse', 'fa-rotate-90', 'fa-rotate-180', 'fa-rotate-270',
    'fa-flip-horizontal', 'fa-flip-vertical', 'fa-inverse', 'fa-border',
    'fa-pull-left', 'fa-pull-right', 'fa-stack', 'fa-stack-1x', 'fa-stack-2x',
    'fa-li', 'fa-ul', 'fa-beat', 'fa-fade', 'fa-bounce', 'fa-shake',
}

ICON_TOKEN = re.compile(r'\bfa-[a-z0-9-]+')
# 静态 class="fas fa-xxx" / class="fab fa-yyy"
CLASS_ATTR = re.compile(r'class="([^"]*)"')
# :class="{ ... 'fa-xxx': ... }" 等表达式里的字符串
QUOTED = re.compile(r"'([^']*)'|\"([^\"]*)\"")


def scan_source():
    """返回 {(style, icon): [位置]}；style 取 fas/fab/far 等（默认 fa-solid）"""
    found = {}
    for dirpath, _dirs, files in os.walk(SRC):
        if '_deprecated' in dirpath.split(os.sep):
            continue
        for name in files:
            if not name.endswith(('.vue', '.js', '.ts')):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding='utf-8', errors='replace') as handle:
                for lineno, line in enumerate(handle, start=1):
                    # 先看静态 class 属性
                    for attr in CLASS_ATTR.findall(line):
                        tokens = [t for t in attr.split() if t.startswith('fa')]
                        style = next((t for t in tokens if t in STYLE_FONTS), None)
                        icons = [t for t in tokens if ICON_TOKEN.fullmatch(t) and t not in SKIP]
                        for icon in icons:
                            found.setdefault((style or 'fa-solid', icon), []).append(
                                f'{os.path.relpath(path, ROOT)}:{lineno}')
                    # 再看表达式里的字符串（如 :class="{'fas fa-leaf': x}"）
                    for single, double in QUOTED.findall(line):
                        text = single or double
                        if 'fa-' not in text:
                            continue
                        tokens = text.split()
                        style = next((t for t in tokens if t in STYLE_FONTS), None)
                        for icon in tokens:
                            if ICON_TOKEN.fullmatch(icon) and icon not in SKIP:
                                found.setdefault((style or 'fa-solid', icon), []).append(
                                    f'{os.path.relpath(path, ROOT)}:{lineno}')
    return found


def parse_css():
    """返回 {icon: ('shape', 码点) | ('shim', 字符)}"""
    if not os.path.isfile(CSS):
        print(f'找不到 Font Awesome CSS: {CSS}')
        sys.exit(2)
    with open(CSS, encoding='utf-8', errors='replace') as handle:
        css = handle.read()

    mapping = {}
    for selectors, value in re.findall(r'([^{}]+)\{--fa:([^}]+)\}', css):
        value = value.strip().strip('"')
        is_shape = bool(re.fullmatch(r'\\[0-9a-fA-F]{4,5}', value))
        payload = int(value[1:], 16) if is_shape else value
        for selector in selectors.split(','):
            selector = selector.strip()
            if selector.startswith('.fa-'):
                mapping[selector[1:]] = ('shape' if is_shape else 'shim', payload)
    return mapping


def load_cmaps():
    """尽量加载三个字体文件的 cmap；缺少 brotli/fontTools 时返回 None"""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        print('（提示：当前 Python 没有 fontTools，跳过字形核对；'
              '可用 base anaconda：C:\\Users\\zhx\\anaconda3\\python.exe）\n')
        return None

    cmaps = {}
    for filename in set(STYLE_FONTS.values()):
        path = os.path.join(FA, 'webfonts', filename)
        try:
            font = TTFont(path)
        except ImportError as exc:  # 通常是缺 brotli
            print(f'（提示：{exc}，跳过字形核对）\n')
            return None
        codes = set()
        for table in font['cmap'].tables:
            codes |= set(table.cmap.keys())
        cmaps[filename] = codes
        font.close()
    return cmaps


def main():
    used = scan_source()
    css = parse_css()
    cmaps = load_cmaps()

    print(f'源码里用到 {len(used)} 个 (样式, 图标) 组合；CSS 里有 {len(css)} 个图标定义。\n')

    unknown, shims, missing = [], [], []
    for (style, icon), where in sorted(used.items()):
        entry = css.get(icon)
        if entry is None:
            unknown.append((icon, where))
            continue
        kind, payload = entry
        if kind == 'shim':
            shims.append((icon, payload, where))
            continue
        if cmaps is not None:
            font_file = STYLE_FONTS.get(style, DEFAULT_FONT)
            if payload not in cmaps.get(font_file, set()):
                missing.append((icon, payload, font_file, where))

    if unknown:
        print(f'❌ {len(unknown)} 个类名在 FA 的 CSS 里不存在（拼写错误或已被移除）：')
        for icon, where in unknown:
            tip = f'   → 建议：{RENAMES[icon]}' if icon in RENAMES else ''
            print(f'  {icon}{tip}')
            for item in where[:4]:
                print(f'      {item}')
        print()

    if shims:
        print(f'ℹ️  {len(shims)} 个图标在 FA7 里是 shim（直接用普通字符渲染，不是缺字形）：')
        for icon, payload, where in shims:
            print(f'  {icon} → "{payload}"   （{where[0]}）')
        print()

    if missing:
        print(f'❌ {len(missing)} 个图标在其所属字体文件里没有字形（会显示成方框）：')
        for icon, code, font_file, where in missing:
            print(f'  {icon}  U+{code:04X}  不在 {font_file} 里')
            for item in where[:4]:
                print(f'      {item}')
        print()

    if not unknown and not missing:
        print('✅ 所有用到的图标都正常（类名存在、字形存在）。')
        if shims:
            print('   （上面列出的 shim 图标用普通字符渲染，属 FA7 的正常行为）')
        return 0
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
