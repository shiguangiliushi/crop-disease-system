/**
 * 行业动态正文工具的单测（第 401 批）
 * ============================================================================
 * 详情页目录依赖两个字符串函数"对得上"：extractToc 给出的 id 必须能在
 * injectHeadingIds 的结果里找到，否则目录点了没反应。
 *
 * 这层又全是正则改写，最容易在边角上出错（大小写标签、属性顺序、重复标题、
 * 实体转义），所以这里把边界逐条钉住。
 */
import { describe, expect, it } from 'vitest';
import { extractToc, injectHeadingIds, stripHtmlText } from '../newsContent';

describe('extractToc：从正文 HTML 提取目录', () => {
  it('按出现顺序提取 h2/h3，并给出稳定 id', () => {
    const html = '<h2>政策要点</h2><p>正文</p><h3>补贴范围</h3>';
    expect(extractToc(html)).toEqual([
      { id: 'news-h-1', text: '政策要点', level: 2 },
      { id: 'news-h-2', text: '补贴范围', level: 3 },
    ]);
  });

  it('去除标题内部标签并解码 HTML 实体', () => {
    expect(extractToc('<h2><strong>重点</strong> &amp; 提要</h2>')).toEqual([
      { id: 'news-h-1', text: '重点 & 提要', level: 2 },
    ]);
  });

  it('重复标题不会冲突（id 按出现顺序编号）', () => {
    const toc = extractToc('<h2>预警</h2><h2>预警</h2>');
    expect(toc.map((item) => item.id)).toEqual(['news-h-1', 'news-h-2']);
    expect(toc.map((item) => item.text)).toEqual(['预警', '预警']);
  });

  it('只认 h2/h3：h1 与 h4 不进目录（但编号仍按所有 h2/h3 计算）', () => {
    const toc = extractToc('<h1>页面标题</h1><h2>章节</h2><h4>小节</h4><h3>子章节</h3>');
    expect(toc).toEqual([
      { id: 'news-h-1', text: '章节', level: 2 },
      { id: 'news-h-2', text: '子章节', level: 3 },
    ]);
  });

  it('大小写标签都能识别', () => {
    expect(extractToc('<H2>大写标题</H2>')).toEqual([
      { id: 'news-h-1', text: '大写标题', level: 2 },
    ]);
  });

  it('无标题 / 空值 / 非字符串 → []', () => {
    expect(extractToc('<p>只有正文</p>')).toEqual([]);
    expect(extractToc('')).toEqual([]);
    expect(extractToc(null)).toEqual([]);
    expect(extractToc(undefined)).toEqual([]);
    expect(extractToc(123)).toEqual([]);
  });

  it('空标题不放进目录，但不会让它后面的标题编号错位', () => {
    // 第 1 个 h2 内容为空（不显示），第 2 个 h2 的真实 id 仍然是 news-h-2
    const toc = extractToc('<h2> </h2><h2>有内容</h2>');
    expect(toc).toEqual([{ id: 'news-h-2', text: '有内容', level: 2 }]);
  });
});

describe('injectHeadingIds：给正文标题补稳定 id', () => {
  it('按顺序注入 news-h-N', () => {
    expect(injectHeadingIds('<h2>A</h2><h3>B</h3>'))
      .toBe('<h2 id="news-h-1">A</h2><h3 id="news-h-2">B</h3>');
  });

  it('保留原有属性、替换已有 id（避免正文自带 id 与目录不一致）', () => {
    expect(injectHeadingIds('<h2 class="x" id="old">A</h2>'))
      .toBe('<h2 id="news-h-1" class="x">A</h2>');
  });

  it('重复标题各自得到不同 id', () => {
    expect(injectHeadingIds('<h2>预警</h2><h2>预警</h2>'))
      .toBe('<h2 id="news-h-1">预警</h2><h2 id="news-h-2">预警</h2>');
  });

  it('没有 h2/h3 时原样返回（不改变正文）', () => {
    const html = '<p>普通正文，<strong>没有标题</strong>。</p>';
    expect(injectHeadingIds(html)).toBe(html);
  });

  it('非字符串 / 空值安全', () => {
    expect(injectHeadingIds(null)).toBe('');
    expect(injectHeadingIds(undefined)).toBe('');
    expect(injectHeadingIds('')).toBe('');
  });

  it('注入后的 id 与 extractToc 完全对应（目录能点中每一节）', () => {
    const html = '<p>导语</p><h2>一、政策</h2><p>a</p><h3>1.1 补贴</h3><p>b</p><h2>二、市场</h2>';
    const injected = injectHeadingIds(html);
    const toc = extractToc(injected);

    expect(toc.length).toBe(3);
    toc.forEach((item) => {
      // 每个目录项都能在注入后的 HTML 里找到同 id 的标题
      expect(injected).toContain(`id="${item.id}"`);
    });
  });
});

describe('stripHtmlText：正文纯文本化（分享图摘要用）', () => {
  it('去标签、解实体、压缩空白', () => {
    expect(stripHtmlText('<p>第一段 &amp; 内容</p>\n<p>第二段&nbsp;内容</p>'))
      .toBe('第一段 & 内容 第二段 内容');
  });

  it('数字实体与十六进制实体也能解码', () => {
    expect(stripHtmlText('&#65;&#x4e2d;')).toBe('A中');
  });

  it('空值与非字符串安全', () => {
    expect(stripHtmlText(null)).toBe('');
    expect(stripHtmlText(undefined)).toBe('');
    expect(stripHtmlText('')).toBe('');
  });
});
