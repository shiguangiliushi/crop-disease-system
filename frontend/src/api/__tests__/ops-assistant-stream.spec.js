/**
 * 系统助手 SSE 客户端（`askOpsAssistantStream`）—— 解析与"定稿替换"的回归测试。
 *
 * ## 为什么值得单独测
 *
 * 流式解析有三个**只在真机上才会炸**的点，且都不报错、只是"看起来不对"：
 *
 *   1. 一个事件被拆在两个网络包里（`event: del` + `ta: ...`）——
 *      不缓冲就会当成两个残缺事件丢掉；
 *   2. `done.answer` 是**权威答案**（数值校验不过时它带的是换过的表格）——
 *      不覆盖就会把一段被判定为不可信的答案留在界面上；
 *   3. 用 axios 拿不到 `response.body`，必须走 fetch —— 这里把它换成假 fetch，
 *      顺便钉住"用的是 fetch 的流，不是 axios 的 data"。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { askOpsAssistantStream } from '@/api/opsAssistant';

/** 把若干段文本包成一个假的 fetch 流式响应 */
function sseResponse(chunks) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      chunks.forEach((text) => controller.enqueue(encoder.encode(text)));
      controller.close();
    },
  });
  return { ok: true, status: 200, body: stream };
}

function event(name, data) {
  return `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
}

describe('askOpsAssistantStream（系统助手 SSE 客户端）', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.unstubAllGlobals();
  });

  it('meta 给出意图与工具，delta 逐段累加，done 收尾', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse([
      event('meta', { intent: 'health', tools: [{ name: 'get_system_health', ok: true, ms: 120 }] }),
      event('delta', { text: '结论：' }),
      event('delta', { text: '9 项红。' }),
      event('done', { answer: '结论：9 项红。', verified: true, degraded: false }),
    ])));

    const deltas = [];
    const result = await askOpsAssistantStream(
      { question: '系统健康' }, { onDelta: (text) => deltas.push(text) },
    );

    expect(result.answer).toBe('结论：9 项红。');
    expect(result.intent).toBe('health');
    expect(result.tools[0].name).toBe('get_system_health');
    expect(result.verified).toBe(true);
    expect(deltas.join('')).toBe('结论：9 项红。');
  });

  it('一个事件被拆在两个包里也能拼回来', async () => {
    const raw = event('meta', { intent: 'health', tools: [] }) + event('delta', { text: '完整的一句话。' });
    const cut = raw.indexOf('data:');            // 就在 data 中间切开
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse([raw.slice(0, cut + 3), raw.slice(cut + 3)])));

    const result = await askOpsAssistantStream({ question: '系统健康' }, {});
    expect(result.answer).toBe('完整的一句话。');
  });

  it('done.answer 覆盖已渲染文本，并通过 onDelta(null, final) 通知页面', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse([
      event('meta', { intent: 'health', tools: [{ name: 'get_system_health' }], degraded: false }),
      event('delta', { text: '共有 999 项问题需要处理。' }),
      event('done', {
        answer: '（自动降级）问题 9 项',   // 后端校验不过，换成表格
        verified: false, degraded: true, degrade_reason: 'verify_failed',
      }),
    ])));

    const replacements = [];
    const result = await askOpsAssistantStream(
      { question: '系统健康有几项红' },
      { onDelta: (text, finalAnswer) => { if (typeof finalAnswer === 'string') replacements.push(finalAnswer); } },
    );

    expect(result.answer).toBe('（自动降级）问题 9 项');
    expect(result.verified).toBe(false);
    expect(result.degrade_reason).toBe('verify_failed');
    expect(replacements).toEqual(['（自动降级）问题 9 项']);
  });

  it('非 2xx 带出状态码，页面才能区分 403 / 429', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 429,
      json: async () => ({ detail: '请求过于频繁' }),
    })));

    await expect(askOpsAssistantStream({ question: '系统健康' }, {})).rejects.toMatchObject({
      response: { status: 429, data: { detail: '请求过于频繁' } },
    });
  });
});
