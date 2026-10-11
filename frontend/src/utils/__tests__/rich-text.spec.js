/**
 * 富文本工具的单测（第 163 批：遗留 Markdown 图片/链接的兼容层）
 *
 * 为什么值得单独测：这层是给**存量数据**兜底的 —— 老帖子里用 markdown 插的图，
 * 现在渲染按 HTML 走，不转换就"图片凭空消失"。而它又是正则改写，
 * 很容易误伤（把散文里的方括号当链接、把代码示例改坏），所以边界要钉住。
 */
import { describe, expect, it } from 'vitest';
import { normalizeLegacyMarkdown, sanitizeRichText } from '../richText';

describe('normalizeLegacyMarkdown', () => {
  it('把 Markdown 图片改成 <img>', () => {
    const html = '看图：![苹果黑星病](/media/uploads/a.jpg) 就是这样。';
    expect(normalizeLegacyMarkdown(html))
      .toBe('看图：<img src="/media/uploads/a.jpg" alt="苹果黑星病" /> 就是这样。');
  });

  it('也认 http(s) 的图片地址', () => {
    expect(normalizeLegacyMarkdown('![](https://example.com/x.png)'))
      .toBe('<img src="https://example.com/x.png" alt="" />');
  });

  it('把 Markdown 链接改成 <a>', () => {
    expect(normalizeLegacyMarkdown('详见 [防治手册](https://example.com/doc)'))
      .toBe('详见 <a href="https://example.com/doc">防治手册</a>');
  });

  it('图片不会被链接规则二次改写', () => {
    const result = normalizeLegacyMarkdown('![图](/media/a.jpg)');
    expect(result).toBe('<img src="/media/a.jpg" alt="图" />');
    expect(result).not.toContain('<a ');
  });

  it('alt 里的引号会被转义（避免属性被截断）', () => {
    const result = normalizeLegacyMarkdown('![他说"很好"](/media/a.jpg)');
    expect(result).toContain('alt="他说&quot;很好&quot;"');
  });

  it('不认"不像 URL"的目标（散文里的方括号不该被改写）', () => {
    const text = '这药[见说明书](稍后补)，先按[常规](见附件)处理。';
    expect(normalizeLegacyMarkdown(text)).toBe(text);
  });

  it('<pre>/<code> 里的 markdown 保持原样（那是示例，不是内容）', () => {
    const html = '<p>写法：</p><pre><code>![图](/media/a.jpg)</code></pre>';
    const result = normalizeLegacyMarkdown(html);
    expect(result).toContain('<code>![图](/media/a.jpg)</code>');
    expect(result).not.toContain('<img');
  });

  it('没有 markdown 语法时原样返回（快速短路）', () => {
    const html = '<p>普通正文，没有任何语法。</p>';
    expect(normalizeLegacyMarkdown(html)).toBe(html);
  });

  it('非字符串与空值安全', () => {
    expect(normalizeLegacyMarkdown(null)).toBe('');
    expect(normalizeLegacyMarkdown(undefined)).toBe('');
    expect(normalizeLegacyMarkdown('')).toBe('');
  });
});

describe('sanitizeRichText 与兼容层的配合', () => {
  it('转换后的 <img> 仍然过白名单（不会因为转换绕过净化）', () => {
    const html = '![x](/media/a.jpg)';
    expect(sanitizeRichText(html)).toContain('<img');
  });

  it('转换不会把脚本带进来（净化仍然生效）', () => {
    const evil = '<img src=x onerror="alert(1)">![ok](/media/a.jpg)';
    const result = sanitizeRichText(evil);
    expect(result).not.toContain('onerror');
    expect(result).toContain('<img src="/media/a.jpg"');
  });

  it('markdown 图片里的 javascript: 目标不会被当成图片（正则只认 http(s) 与 /media/）', () => {
    const result = sanitizeRichText('![x](javascript:alert(1))');
    // ⚠️ 这里**不能**断言"输出里没有 javascript:" —— 它作为**纯文本**留在正文里是正常的
    //    （用户自己写的东西不该被吃掉）。要断言的是"它没变成可点的元素"。
    expect(result).not.toContain('<img');
    expect(result).not.toContain('<a ');
    expect(result).not.toContain('href="javascript:');
  });
});
