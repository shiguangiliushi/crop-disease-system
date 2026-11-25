/**
 * 不可逆写的确认接口（`confirmOpsAction`，第 426 批）
 *
 * 这条链路的三个风险都不在 JSON 解析上，而在"确认"这件事本身：
 *
 *   1. **只发 `confirm` / `cancel` 两个词**。让模型去解析"他说的是确认吗"，
 *      等于让模型可以确认自己刚提的议 —— 这是二次确认要防的第一件事；
 *   2. **失败也是 200**（`ok=false` + `reason`）。把 200 当成"已执行"，
 *      就会出现"界面说删了、其实早就过期了"这种最难发现的错；
 *   3. `token` 一次性 —— 页面要能区分 `expired` / `consumed` / `not_found`，
 *      否则用户只会看到一句"失败"，然后反复重试一个永远不可能成功的凭据。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import { confirmOpsAction, fetchOpsPending } from '@/api/opsAssistant';

/** 200 的假响应（确认接口的失败也是 200，见模块说明第 2 条） */
function jsonResponse(data) {
  return { ok: true, status: 200, json: async () => data };
}

describe('confirmOpsAction（不可逆写的确认 / 取消）', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.unstubAllGlobals();
  });

  it('把 token 与 decision 原样发给确认接口', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({
      ok: true, status: 'confirmed', answer: '已执行：删除反馈', token: 'tok-1',
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await confirmOpsAction({ token: 'tok-1', decision: 'cancel' });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain('/admin/assistant/ops/confirm/');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ token: 'tok-1', decision: 'cancel' });
    expect(result.status).toBe('confirmed');
  });

  it('默认 decision 是 confirm', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true, status: 'confirmed' }));
    vi.stubGlobal('fetch', fetchMock);

    await confirmOpsAction({ token: 'tok-2' });

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      token: 'tok-2', decision: 'confirm',
    });
  });

  it('后端拒绝也是 200：ok=false 带 reason，不抛异常', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      ok: false, status: 'rejected', reason: 'consumed', answer: '已经处理过了', token: 'tok-3',
    })));

    const result = await confirmOpsAction({ token: 'tok-3' });

    expect(result.ok).toBe(false);
    expect(result.reason).toBe('consumed');
  });

  it('请求本身失败才抛（页面据此区分"没执行"与"请求没到"）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 403,
      json: async () => ({ detail: '只有管理员可以确认写操作' }),
    })));

    await expect(confirmOpsAction({ token: 'tok-4' })).rejects.toMatchObject({
      response: { status: 403, data: { detail: '只有管理员可以确认写操作' } },
    });
  });
});

describe('fetchOpsPending（待确认队列，第 428 批）', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.unstubAllGlobals();
  });

  it('GET 自己的待确认队列，原样带回 rows', async () => {
    const rows = [
      { token: 'tok-a', action: 'delete_feedback', label: '删除反馈', target: '反馈 #12', seconds_left: 420 },
    ];
    const fetchMock = vi.fn(async () => jsonResponse({ rows, count: 1 }));
    vi.stubGlobal('fetch', fetchMock);

    const data = await fetchOpsPending();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain('/admin/assistant/ops/pending/');
    expect(init.method ?? 'GET').toBe('GET');
    expect(data).toEqual({ rows, count: 1 });
  });

  it('非 2xx 抛错（403 时不该被当成"没有待确认"）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 403,
      json: async () => ({ detail: '只有管理员可以查看待确认操作' }),
    })));

    await expect(fetchOpsPending()).rejects.toMatchObject({ response: { status: 403 } });
  });
});
