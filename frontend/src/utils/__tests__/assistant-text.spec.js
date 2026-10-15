/**
 * 助手回答排版解析的单测（第 210 批）
 *
 * 为什么值得单独测：
 *   ① 它接的是**外部大模型的输出**，是不可信内容 —— 这层是"不引入 HTML 注入面"的边界，
 *      被改坏就等于把 `v-html` 那条路重新打开；
 *   ② 它是**正则改写**，最容易出的问题不是崩溃而是**误伤**
 *      （把 `*` 项目符号当加粗、把未闭合的 `**` 吃掉、把公式里的星号改坏）；
 *   ③ 用户是**看到星号**才反馈的，所以"未闭合时原样保留"必须钉死 ——
 *      流式输出中途每一帧都可能处于未闭合状态。
 */
import { describe, expect, it } from 'vitest';

import { parseAnswerLines, parseInlineBold } from '../assistantText';

describe('parseInlineBold', () => {
  it('把成对的 **加粗** 拆成加粗片段', () => {
    expect(parseInlineBold('**苹果黑星病** —— 叶面放射状霉点')).toEqual([
      { bold: true, text: '苹果黑星病' },
      { bold: false, text: ' —— 叶面放射状霉点' },
    ]);
  });

  it('一行里多个加粗都能拆出来', () => {
    expect(parseInlineBold('**病名** 用 **15%三唑酮** 防治')).toEqual([
      { bold: true, text: '病名' },
      { bold: false, text: ' 用 ' },
      { bold: true, text: '15%三唑酮' },
      { bold: false, text: ' 防治' },
    ]);
  });

  it('⚠️ 未闭合的 ** 原样保留（流式输出中途的每一帧都可能是这样）', () => {
    // 关键：不能把 "**苹果" 里的星号吃掉，否则星号会忽隐忽现
    expect(parseInlineBold('**苹果')).toEqual([{ bold: false, text: '**苹果' }]);
    expect(parseInlineBold('已闭合 **OK** 但后面 **又开了')).toEqual([
      { bold: false, text: '已闭合 ' },
      { bold: true, text: 'OK' },
      { bold: false, text: ' 但后面 **又开了' },
    ]);
  });

  it('空标记 **** 不产生加粗片段', () => {
    expect(parseInlineBold('****')).toEqual([{ bold: false, text: '****' }]);
  });

  it('单个星号不动它（模型有时拿它当项目符号）', () => {
    expect(parseInlineBold('* 第一条')).toEqual([{ bold: false, text: '* 第一条' }]);
    expect(parseInlineBold('1 * 2 * 3')).toEqual([{ bold: false, text: '1 * 2 * 3' }]);
  });

  it('引用序号保持普通文本（会和加粗连排，但不该被吞掉）', () => {
    expect(parseInlineBold('**病名** 【1】')).toEqual([
      { bold: true, text: '病名' },
      { bold: false, text: ' 【1】' },
    ]);
  });

  it('整段加粗', () => {
    expect(parseInlineBold('**全段都是重点**')).toEqual([{ bold: true, text: '全段都是重点' }]);
  });

  it('空串与空值返回空数组', () => {
    expect(parseInlineBold('')).toEqual([]);
    expect(parseInlineBold(null)).toEqual([]);
    expect(parseInlineBold(undefined)).toEqual([]);
  });

  it('⚠️ HTML 只是文字，不会被解析成标签（这是本层存在的意义）', () => {
    const out = parseInlineBold('<script>alert(1)</script> 和 **正常加粗**');
    expect(out).toEqual([
      { bold: false, text: '<script>alert(1)</script> 和 ' },
      { bold: true, text: '正常加粗' },
    ]);
    // 产出物只可能是"文本 + bold 标志"，没有别的字段可以承载 HTML
    for (const seg of out) {
      expect(Object.keys(seg).sort()).toEqual(['bold', 'text']);
    }
  });

  it('加粗标记里不会嵌星号（`[^*]+` 的边界）', () => {
    // `**a**b**c**` 应解析为 加粗 a、普通 b、加粗 c —— 而不是吞掉中间的 b
    expect(parseInlineBold('**a**b**c**')).toEqual([
      { bold: true, text: 'a' },
      { bold: false, text: 'b' },
      { bold: true, text: 'c' },
    ]);
  });
});

describe('parseAnswerLines', () => {
  it('按行拆分，去掉空行（与改动前的 linesOf 行为一致）', () => {
    const lines = parseAnswerLines('第一段\n\n第二段');
    expect(lines).toHaveLength(2);
    expect(lines[0]).toEqual([{ bold: false, text: '第一段' }]);
    expect(lines[1]).toEqual([{ bold: false, text: '第二段' }]);
  });

  it('每行各自解析加粗', () => {
    const lines = parseAnswerLines('**苹果**\n1. **黑腐病** —— 萼端腐烂');
    expect(lines[0]).toEqual([{ bold: true, text: '苹果' }]);
    expect(lines[1][0]).toEqual({ bold: false, text: '1. ' });
    expect(lines[1][1]).toEqual({ bold: true, text: '黑腐病' });
  });

  it('全是空白行时返回空数组（气泡不渲染空段落）', () => {
    expect(parseAnswerLines('\n\n   \n')).toEqual([]);
  });
});
