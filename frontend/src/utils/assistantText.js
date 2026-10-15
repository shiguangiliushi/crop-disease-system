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
 * 按行拆分回答，并逐行解析加粗片段。
 *
 * 空行被丢掉：气泡里不需要空段落（行距已经用 CSS 控制），
 * 这与改动前 `linesOf()` 的行为一致，避免"修一个排版问题引入另一个"。
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
