import { marked } from 'marked';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js';
import 'highlight.js/styles/github.css';

// 配置 marked
marked.setOptions({
  highlight: function(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(lang, code).value;
    }
    return hljs.highlightAuto(code).value;
  },
  breaks: true,
  gfm: true,
  smartLists: true,
  smartypants: true
});

// 自定义渲染器
const renderer = new marked.Renderer();

// 重写链接渲染，添加target="_blank"
renderer.link = function(href, title, text) {
  const link = marked.Renderer.prototype.link.call(this, href, title, text);
  return link.replace('<a', '<a target="_blank" rel="noopener noreferrer"');
};

// 重写图片渲染，添加懒加载和响应式
renderer.image = function(href, title, text) {
  return `
    <div class="markdown-image">
      <img 
        src="${href}" 
        alt="${text || ''}" 
        title="${title || ''}" 
        loading="lazy"
        class="img-fluid"
      >
      ${title ? `<div class="image-caption">${title}</div>` : ''}
    </div>`;
};

// 解析 Markdown 为 HTML
export const parseMarkdown = (markdown) => {
  if (!markdown) return '';
  
  // 处理图片链接，确保使用正确的域名
  const processedMarkdown = markdown.replace(
    /!\[([^\]]*)\]\(([^)]+)\)/g,
    (match, alt, src) => {
      // 这里可以添加图片处理逻辑，比如添加CDN域名等
      return `![${alt}](${src})`;
    }
  );
  
  const html = marked(processedMarkdown, { renderer });
  return DOMPurify.sanitize(html, {
    ADD_ATTR: ['target'],
    ALLOWED_TAGS: [
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'p', 'br', 'hr', 'pre', 'code',
      'blockquote', 'ol', 'ul', 'li', 'dl', 'dt', 'dd',
      'strong', 'em', 'del', 'a', 'img',
      'table', 'thead', 'tbody', 'tr', 'th', 'td',
      'div', 'span', 'section', 'article', 'figure', 'figcaption'
    ],
    ALLOWED_ATTR: [
      'class', 'id', 'src', 'alt', 'title', 'href', 'target', 'rel',
      'width', 'height', 'loading'
    ]
  });
};

// 获取Markdown的纯文本（用于预览）
export const getPlainText = (markdown) => {
  if (!markdown) return '';
  // 移除Markdown标记
  return markdown
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1') // 图片
    .replace(/\[(.*?)\]\([^)]+\)/g, '$1') // 链接
    .replace(/#{1,6}\s*/g, '') // 标题
    .replace(/[*_]{1,3}([^*_]*)[*_]{1,3}/g, '$1') // 粗体、斜体
    .replace(/~~(.*?)~~/g, '$1') // 删除线
    .replace(/`{1,3}([^`]*)`{1,3}/g, '$1') // 代码
    .replace(/^[\s\t]*([*\-+]|\d+\.)\s+/gm, '') // 列表
    .replace(/\n{3,}/g, '\n\n') // 多个空行合并为两个
    .trim();
};

// 获取预览文本（截取前n个字符）
export const getPreviewText = (markdown, length = 100) => {
  const plainText = getPlainText(markdown);
  return plainText.length > length 
    ? plainText.substring(0, length) + '...' 
    : plainText;
};

export default {
  parse: parseMarkdown,
  getPlainText,
  getPreviewText
};
