/**
 * 助手回答的**受控**排版解析（第 210 批）。
 *
 * ## 为什么单独一个文件
 *
 * 用户反馈"回答为什么会出现 `**` 和【数字】"。原因是：助手气泡一直是**纯文本渲染**
 * （`split('\n')` 后 `{{ line }}`），而模型习惯写 `**加粗**` ——
 * 星号就原样显示出来了。抽屉与独立问答页两处都要改，所以抽到这里共用，
 * 而不是在两个 `.vue` 里各抄一份正则（抄两份迟早只改一处）。
 *
 * ## ⚠️ 为什么不用 `utils/richText.js` 或 `utils/markdown.js`
 *
 * 那两个是给**论坛帖子**用的：输入是**自己用户**写的内容，允许渲染 HTML /
 * 图片 / 链接，靠 `sanitizeRichText` 过滤危险标签。
 *
 * 助手回答的输入是**外部大模型**的输出 —— 属于完全不可信内容，
 * 而且是"每次都不一样、随时可能被诱导"的那一类。给它开 HTML 通道，
 * 就等于把整个 sanitize 链条的正确性押在一次过滤上。
 * 所以这里**只做一种替换**：`**加粗**` → 加粗片段；
 * 目标标签由模板写死（`<strong>`），片段内容走文本插值 ——
 * **模型无论输出什么，都只能是文字**，没有 HTML 注入面。
 *
 * ## 边界（都有单测钉住）
 *
 * - 未闭合的 `**`（流式输出中途很常见）**不当作标记**，否则星号会忽隐忽现；
 * - 空标记 `****` 不产生加粗片段；
 * - 单星号 `*` 原样保留（模型有时用 `*` 当项目符号）；
 * - 内容里的 `<script>` 等只是文字，不会被当标签解析（交给模板插值）。
 */

/**
 * 把一行/一段文本拆成片段数组，供模板渲染。
 *
 * @param {string} line 原始文本（模型输出的一行）
 * @returns {Array<{bold: boolean, text: string}>} 按原顺序排列的片段
 */
export function parseInlineBold(line) {
  const text = String(line ?? '');
  if (!text) return [];

  const out = [];
  //: `[^*]+` 而不是 `.+?`：加粗标记里不会再嵌星号，这样正则简单，
  //: 也不会出现"跨多个标记贪婪匹配"把中间内容吞掉的问题（`**a**b**c**` 必须解析成 a、b、c）。
  const pattern = /\*\*([^*]+)\*\*/g;
  let cursor = 0;
  let match = pattern.exec(text);
  while (match !== null) {
    if (match.index > cursor) {
      out.push({ bold: false, text: text.slice(cursor, match.index) });
    }
    out.push({ bold: true, text: match[1] });
    cursor = match.index + match[0].length;
    match = pattern.exec(text);
  }
  //: 收尾：剩下的普通文本（未闭合的 `**` 也包含在这里，会原样显示）
  if (cursor < text.length) {
    out.push({ bold: false, text: text.slice(cursor) });
  }
  return out;
}

/**
 * 按**空行**把回答切成段落，段内保留单换行（第 211 批）。
 *
 * ## 为什么需要它（用户反馈"我提问的时候都会多出一行下来"）
 *
 * 改动前是"**每一行都渲染成一个 `<p>`、每段带 8px 下边距**"。而模型的输出是这样：
 *
 * ```
 * 苹果常见病害主要有……          ← 行 0
 *                               ← 空行
 * **苹果雪松锈病** 【1】          ← 行 2
 * - 识别：……                    ← 行 3
 * - 关键时机：……                 ← 行 4
 * - 用药：……                    ← 行 5
 * ```
 *
 * 行 2~5 是**同一段里的子弹点**（模型没在它们之间放空行），却被逐行加了 8px ——
 * 一份 24 行的长回答凭空多出约 150px 空隙，看起来就是"每条之间都多了一行"。
 *
 * 正确语义：**空行 = 段落边界**（给间距），**单换行 = 段内换行**（不给间距）。
 * 段落用 `white-space: pre-wrap` 渲染即可让单换行显示成换行、且不额外留白。
 *
 * @param {string} content 完整回答
 * @param {{preserveLineBreaks?: boolean}} [options]
 *   `preserveLineBreaks: false` 时把段内换行折成空格（用于不支持 pre-wrap 的场景）。
 * @returns {Array<Array<{bold: boolean, text: string}>>} 每个段落一组的片段数组
 */
export function parseAnswerParagraphs(content, options = {}) {
  const { preserveLineBreaks = true } = options;
  const text = String(content ?? '');
  if (!text.trim()) return [];

  const paragraphs = [];

  for (const block of text.split(/\n\s*\n/)) {
    const trimmed = block.trim();
    if (trimmed === '') continue;

    //: ⚠️ 段内**逐行**解析，行与行之间显式插入 `\n` 片段。
    //:   直接把整段丢给 `parseInlineBold` 会**丢换行**：换行恰好落在两个片段之间时
    //:   （`**标题**\n- 要点` → 「加粗片段」「\n- 要点」），渲染成相邻文本节点后换行就没了，
    //:   子弹点会挤在同一行 —— 这个缺陷是被单测抓出来的。
    const lines = preserveLineBreaks ? trimmed.split('\n') : [trimmed.replace(/\n+/g, ' ')];
    const segments = [];
    lines.forEach((line, index) => {
      if (index > 0) segments.push({ bold: false, text: '\n' });
      segments.push(...parseInlineBold(line));
    });
    paragraphs.push(segments);
  }

  return paragraphs;
}

/**
 * 按行拆分回答，并逐行解析加粗片段。
 *
 * ⚠️ 第 211 批起界面改用 {@link parseAnswerParagraphs} ——
 * "每行一段"会把段内换行也加上段落间距，正是用户反馈的"多出一行"。
 * 本函数保留给"确实需要逐行"的场景（例如逐行做关键字高亮）。
 *
 * @param {string} content 完整回答
 * @returns {Array<Array<{bold: boolean, text: string}>>} 每行的片段数组
 */
export function parseAnswerLines(content) {
  return String(content ?? '')
    .split('\n')
    .filter((line) => line.trim() !== '')
    .map((line) => parseInlineBold(line));
}