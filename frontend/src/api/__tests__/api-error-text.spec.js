/**
 * 统一错误文案出口的单测（第 213 批）
 *
 * 为什么值得单独测：`formatApiError` 是**全前端唯一的错误文案出口**（22 处调用）。
 * 评审意见指出"后端英文技术报错直接弹给农户"，而修法就是在这个出口上收口 ——
 * 出口一旦退化，22 个页面会同时开始弹英文，而且**开发时很难注意到**
 * （自己用的是中文后端提示，只有 DRF 的校验错误才是英文）。
 *
 * 判据由 `readableError.pickReadableMessage` 提供：**含中日韩字符才用原文**。
 * 所以下面既测"英文被拦住"，也测"中文要原样放行" ——
 * 只测前者会把工具改成"一律丢掉后端文案"，那会丢掉真正有用的提示。
 */
import { describe, expect, it, vi } from 'vitest';

//: `http.js` 会建 axios 实例并读会话，这里把副作用挡掉，只测纯函数
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ token: '', clearAuth: vi.fn() }) }));

import { formatApiError } from '../http';

const FALLBACK = '操作失败，请稍后重试';
const err = (data) => ({ response: { data } });

describe('formatApiError：英文技术文案不进用户界面', () => {
  it('DRF 的英文 detail 被拦住，换成友好文案', () => {
    expect(formatApiError(err({ detail: 'Authentication credentials were not provided.' }), FALLBACK))
      .toBe(FALLBACK);
    expect(formatApiError(err({ detail: 'Invalid token.' }), FALLBACK)).toBe(FALLBACK);
  });

  it('英文 error 字段同样被拦住', () => {
    expect(formatApiError(err({ error: 'Method "GET" not allowed.' }), FALLBACK)).toBe(FALLBACK);
  });

  it('字符串响应体也过滤', () => {
    expect(formatApiError(err('Internal Server Error'), FALLBACK)).toBe(FALLBACK);
  });

  it('字段级英文校验错误也过滤', () => {
    const out = formatApiError(err({ title: ['This field is required.'] }), FALLBACK);
    expect(out).not.toContain('This field is required');
    expect(out).toContain('title');
  });

  it('⚠️ 中文提示必须原样放行（这是我们自己写的、对用户有用的文案）', () => {
    expect(formatApiError(err({ detail: '未检测到图片文件' }), FALLBACK)).toBe('未检测到图片文件');
    expect(formatApiError(err({ error: '积分不足' }), FALLBACK)).toBe('积分不足');
    expect(formatApiError(err('图片格式不支持'), FALLBACK)).toBe('图片格式不支持');
  });

  it('超长中文会被截断（避免整屏弹一段后台堆栈式文案）', () => {
    const long = '这是一条非常长的中文错误说明'.repeat(20);
    const out = formatApiError(err({ detail: long }), FALLBACK);
    expect(out.length).toBeLessThanOrEqual(141);
    expect(out.endsWith('…')).toBe(true);
  });

  it('没有响应体时回落到 caller 给的文案', () => {
    expect(formatApiError({ message: '' }, FALLBACK)).toBe(FALLBACK);
    expect(formatApiError(err({}), FALLBACK)).toBe(FALLBACK);
  });
});
