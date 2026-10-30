"""富文本净化（第 256 批）—— 在**保存**时执行，不再只靠前端。

## 为什么后端也要做

论坛 `Post.content` / `Comment.content` 是裸 `TextField`，此前后端**完全信任输入**，
只有前端渲染前净化。任何一处新页面忘了净化、或者有人直接 `POST /api/posts/` 写入
`<img src=x onerror="...">`，脚本就会执行 —— 而移动端 token 存在 `localStorage`，
被 XSS 读到就等于账号被接管。属于"防线只剩一层"。

## 为什么不用 bleach

项目环境里没有装 `bleach` / `nh3`，为这一处引入第三方依赖要动 `requirements` 与部署。
这里用标准库 `html.parser` 做**白名单重建**：只保留已知安全的标签与属性，
其余标签**丢弃但保留其文本**，属性值统一转义，`javascript:` / `data:` 这类协议直接拒收。

## 取舍

- 富文本编辑器（Quill）产出的 `p/strong/em/u/ul/ol/li/blockquote/a/img/h3/h4/code/pre/br` 全部保留；
- 会丢掉的：内联 `style`、`class`、`iframe`、`video`、自定义标签 —— 编辑器里本来也不产生这些；
- 幂等：净化过的内容再净化一次结果不变（不会出现 `&amp;amp;` 越滚越多）。
"""
from __future__ import annotations

import html
from html.parser import HTMLParser

#: 允许保留的标签
ALLOWED_TAGS = {
    'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'del',
    'ul', 'ol', 'li', 'blockquote', 'a', 'img',
    'h1', 'h2', 'h3', 'h4', 'code', 'pre', 'span', 'hr',
}

#: 允许保留的属性（只用这些，其余一律丢弃）
ALLOWED_ATTRS = {
    'a': {'href', 'title'},
    'img': {'src', 'alt', 'title'},
}

#: 自闭合标签
VOID_TAGS = {'br', 'img', 'hr'}

#: 允许的 URL 协议
ALLOWED_PROTOCOLS = ('http://', 'https://', 'mailto:', '/', '#', 'tel:')


def _safe_url(value: str) -> bool:
    candidate = (value or '').strip().lower()
    if not candidate:
        return False
    return candidate.startswith(ALLOWED_PROTOCOLS)


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []

    # -- 标签 ---------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            return  # 丢弃标签本身，文本由 handle_data 保留
        kept = []
        for name, value in attrs:
            if name not in ALLOWED_ATTRS.get(tag, set()):
                continue
            if name in ('href', 'src') and not _safe_url(value or ''):
                continue
            kept.append(f'{name}="{html.escape(value or "", quote=True)}"')
        suffix = f' {" ".join(kept)}' if kept else ''
        self.parts.append(f'<{tag}{suffix}>')

    def handle_startendtag(self, tag, attrs):
        if tag in VOID_TAGS or tag in ALLOWED_TAGS:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        self.parts.append(f'</{tag}>')

    # -- 文本与实体 ---------------------------------------------------------
    def handle_data(self, data):
        self.parts.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        self.parts.append(f'&{name};')

    def handle_charref(self, name):
        self.parts.append(f'&#{name};')

    def handle_comment(self, data):
        return  # 注释直接丢

    def handle_decl(self, decl):
        return

    def handle_pi(self, data):
        return


def sanitize_html(raw: str | None) -> str:
    """白名单重建；空输入返回空字符串。"""
    if not raw:
        return ''
    parser = _Sanitizer()
    parser.feed(str(raw))
    parser.close()
    return ''.join(parser.parts)
