/**
 * 行业动态正文的阅读辅助工具（第 401 批 · P1）
 * ------------------------------------------------------------------
 * 详情页要"给正文标题生成目录"，而正文是**后端存的富文本 HTML**：
 * 标题原本没有 id，目录点不过去；不同新闻的标题层级也不一样。
 *
 * 这里只做两件纯字符串的事，方便单测钉住边界：
 *   · `extractToc(html)`       从正文里提取 h2/h3，生成 `[{id,text,level}]`；
 *   · `injectHeadingIds(html)` 给每个 h2/h3 补一个稳定可预测的 id（news-h-1、news-h-2…）。
 *
 * 两个函数**共用同一套"按出现顺序编号"的规则** —— 这是它们能对上的前提：
 * 只要编号规则一致，extractToc 给出的 id 就一定能在 injectHeadingIds 的结果里找到。
 * 不按标题文本生成 id（如把标题转 slug），是因为：
 *   1. 中文标题转 slug 会得到一长串空/百分号编码，可读性差；
 *   2. 同一篇新闻里出现两个同名标题时，按文本生成会撞 id。
 *
 * 注意：本文件不负责 XSS 净化（由 utils/richText.js 的 sanitizeRichText 负责），
 * 调用顺序固定为「先净化、再注入 id」，否则正文里手写的 `id` 可能与目录不一致。
 */

/** 富文本里 h2/h3 的开标签（只认 h2/h3：h1 留给页面标题，h4+ 通常不是章节） */
const HEADING_OPEN_RE = /<(h[23])(\s[^>]*)?>/gi;

/** 常见 HTML 实体（其余用数字实体规则兜底） */
const NAMED_ENTITIES = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: ' ',
};

/** 解码一个 HTML 实体（传入的是 `&` 与 `;` 之间的部分） */
function decodeEntity(raw) {
  const code = String(raw || '').toLowerCase();
  if (Object.prototype.hasOwnProperty.call(NAMED_ENTITIES, code)) {
    return NAMED_ENTITIES[code];
  }
  if (code.startsWith('#x') || code.startsWith('#')) {
    const isHex = code.startsWith('#x');
    const value = Number.parseInt(isHex ? code.slice(2) : code.slice(1), isHex ? 16 : 10);
    // fromCodePoint 对越界值会抛 RangeError —— 实体来自正文，不能让它把整页渲染搞崩
    if (Number.isFinite(value) && value >= 0 && value <= 0x10ffff) {
      return String.fromCodePoint(value);
    }
  }
  return `&${raw};`;
}

/**
 * 把一段 HTML 变成"可读纯文本"（去标签、解实体、合并空白）
 *
 * 第 401 批：分享图/摘要截断都需要纯文本 —— 但新闻正文是富文本，
 * 直接截 HTML 字符串会把 `<p>`、`&nbsp;` 截进分享图（分享图里会画出标签字符）。
 *
 * @param {unknown} html
 * @returns {string}
 */
export function stripHtmlText(html) {
  if (typeof html !== 'string' || !html) return '';
  return html
    .replace(/<[^>]*>/g, ' ')
    .replace(/&(#x?[0-9a-f]+|[a-z][a-z0-9]*);/gi, (_match, code) => decodeEntity(code))
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * 从正文 HTML 里提取目录（只取 h2/h3，按出现顺序编号）
 *
 * 每个标题的 id 与 `injectHeadingIds` 注入的值一致（news-h-序号），
 * 序号按**所有 h2/h3 开标签**计数 —— 即使某个标题内容是空的（会被跳过、不放进目录），
 * 它后面的标题编号也不会因此前移，两边的对应关系仍然成立。
 *
 * @param {unknown} html 正文 HTML
 * @returns {Array<{id: string, text: string, level: number}>}
 */
export function extractToc(html) {
  if (typeof html !== 'string' || !html) return [];

  // 复用模块级全局正则：每次进入先把 lastIndex 归零，避免上一次 exec 中途退出时残留游标
  HEADING_OPEN_RE.lastIndex = 0;
  const toc = [];
  let index = 0;
  let match = HEADING_OPEN_RE.exec(html);
  while (match) {
    index += 1;
    const tag = match[1].toLowerCase();
    const start = match.index + match[0].length;
    // 用 indexOf 找闭合标签，而不是第二条正则：这样能保证"开标签计数"与
    // injectHeadingIds 完全一致（两条正则各写一遍，迟早会有一边漏掉某种写法）
    const end = html.toLowerCase().indexOf(`</${tag}>`, start);
    const inner = end === -1 ? '' : html.slice(start, end);
    const text = stripHtmlText(inner);
    if (text) {
      toc.push({ id: `news-h-${index}`, text, level: tag === 'h2' ? 2 : 3 });
    }
    match = HEADING_OPEN_RE.exec(html);
  }
  return toc;
}

/**
 * 给正文里的 h2/h3 补稳定 id（news-h-1、news-h-2…）
 *
 * 为什么"覆盖已有 id"：正文可能自带 id（富文本编辑器里手写锚点），
 * 若保留它，extractToc 按序号算出的 id 就对不上了。目录是本页生成的，
 * 以本页的编号为准最不容易错。
 *
 * 没有 h2/h3 时**原样返回**（不复制、不归一化），这样调用方可以放心地
 * 把它当成"注入了 id 的正文"传给 v-html，性能与内容都不受影响。
 *
 * @param {unknown} html 已净化的正文 HTML
 * @returns {string}
 */
export function injectHeadingIds(html) {
  if (typeof html !== 'string' || !html) return '';

  HEADING_OPEN_RE.lastIndex = 0;
  let index = 0;
  return html.replace(HEADING_OPEN_RE, (_match, tag, attrs = '') => {
    index += 1;
    // 先去掉原有 id（含引号/无引号两种写法），再补新 id，避免出现两个 id 属性
    const rest = attrs
      .replace(/\sid\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')
      .trimEnd();
    return `<${tag} id="news-h-${index}"${rest}>`;
  });
}

export default {
  extractToc,
  injectHeadingIds,
  stripHtmlText,
};
