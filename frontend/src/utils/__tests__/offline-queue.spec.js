/**
 * 离线队列逻辑测试（第 50 批）
 * 队列本身不依赖 IndexedDB —— 换成内存适配器即可完整测试。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  MAX_TRIES, createMemoryAdapter, createOfflineQueue, makeTaskId, summarizeSync,
} from '@/utils/offlineQueue';

function makeQueue(options = {}) {
  let counter = 0;
  return createOfflineQueue(createMemoryAdapter(), {
    now: () => 1000 + counter,           // 时间递增，保证入队顺序可预期
    idFactory: () => `t${++counter}`,
    ...options,
  });
}

describe('离线队列', () => {
  let queue;
  beforeEach(() => {
    queue = makeQueue();
  });

  it('入队后可列出，且按入队时间升序（先来先传）', async () => {
    await new Promise((r) => setTimeout(r, 1));
    const a = await queue.add({ blob: new Blob(['a']), filename: 'a.jpg' });
    const b = await queue.add({ blob: new Blob(['b']), filename: 'b.jpg' });

    const items = await queue.list();
    expect(items.map((item) => item.filename)).toEqual([a.filename, b.filename]);
    expect(items[0].id).toBe(a.id);
    expect(items[1].id).toBe(b.id);
    expect(items[0].status).toBe('pending');
    expect(items[0].tries).toBe(0);
  });

  it('计数区分待传与失败', async () => {
    const a = await queue.add({ blob: new Blob(['a']) });
    await queue.add({ blob: new Blob(['b']) });
    expect(await queue.count()).toEqual({ total: 2, pending: 2, failed: 0 });

    // 连续失败到上限 → 标记为 failed，但仍留在队列里（不静默丢数据）
    for (let i = 0; i < MAX_TRIES; i += 1) {
      await queue.markTried(a.id, '网络错误');
    }
    const counts = await queue.count();
    expect(counts.total).toBe(2);
    expect(counts.pending).toBe(1);
    expect(counts.failed).toBe(1);

    const failed = (await queue.list()).find((item) => item.id === a.id);
    expect(failed.status).toBe('failed');
    expect(failed.lastError).toBe('网络错误');
  });

  it('pending 会跳过失败项，避免反复重试卡住队列', async () => {
    const a = await queue.add({ blob: new Blob(['a']) });
    await queue.add({ blob: new Blob(['b']) });
    for (let i = 0; i < MAX_TRIES; i += 1) await queue.markTried(a.id, 'x');

    const pending = await queue.pending();
    expect(pending.map((item) => item.id)).not.toContain(a.id);
    expect(pending).toHaveLength(1);
  });

  // -------------------------------------------------------------------------
  // 第 162 批：失败项**能被处理**（用户截图里那两条「同步失败」原本无处可去）
  // -------------------------------------------------------------------------
  it('failed() 能把失败项列出来（界面要摆给用户看）', async () => {
    const a = await queue.add({ blob: new Blob(['a']), filename: 'leaf-a.jpg' });
    const b = await queue.add({ blob: new Blob(['b']), filename: 'leaf-b.jpg' });
    for (let i = 0; i < MAX_TRIES; i += 1) await queue.markTried(a.id, '识别服务暂时不可用');

    const failed = await queue.failed();
    expect(failed).toHaveLength(1);
    expect(failed[0].id).toBe(a.id);
    expect(failed[0].filename).toBe('leaf-a.jpg');
    expect(failed[0].lastError).toBe('识别服务暂时不可用');
    expect(failed[0].tries).toBe(MAX_TRIES);
    expect(await queue.failed()).not.toContainEqual(expect.objectContaining({ id: b.id }));
  });

  it('retry() 把失败项重新排队，并把 tries 归零', async () => {
    const a = await queue.add({ blob: new Blob(['a']) });
    for (let i = 0; i < MAX_TRIES; i += 1) await queue.markTried(a.id, 'x');
    expect((await queue.count()).failed).toBe(1);

    await queue.retry(a.id);

    const counts = await queue.count();
    expect(counts.failed).toBe(0);
    expect(counts.pending).toBe(1);
    const item = (await queue.list()).find((row) => row.id === a.id);
    expect(item.status).toBe('pending');
    // ⚠️ tries 必须归零：否则下一次 markTried 立刻又 >= MAX_TRIES，重试等于没重试
    expect(item.tries).toBe(0);
    expect(item.lastError).toBe('');
    // 回到 pending 之后要能被同步流程取到
    expect((await queue.pending()).map((row) => row.id)).toContain(a.id);
  });

  it('retryAllFailed() 一次把失败项全部重新排队', async () => {
    const a = await queue.add({ blob: new Blob(['a']) });
    const b = await queue.add({ blob: new Blob(['b']) });
    const c = await queue.add({ blob: new Blob(['c']) });
    for (const id of [a.id, b.id]) {
      for (let i = 0; i < MAX_TRIES; i += 1) await queue.markTried(id, 'x');
    }
    expect((await queue.count()).failed).toBe(2);

    const count = await queue.retryAllFailed();

    expect(count).toBe(2);
    expect(await queue.count()).toEqual({ total: 3, pending: 3, failed: 0 });
    expect((await queue.list()).find((row) => row.id === c.id).status).toBe('pending');
  });

  it('出队与清空', async () => {
    const a = await queue.add({ blob: new Blob(['a']) });
    await queue.add({ blob: new Blob(['b']) });
    await queue.remove(a.id);
    expect((await queue.list()).map((item) => item.id)).toEqual(['t2']);
    await queue.clear();
    expect(await queue.list()).toEqual([]);
  });

  it('任务 id 唯一', () => {
    const ids = new Set(Array.from({ length: 50 }, () => makeTaskId()));
    expect(ids.size).toBe(50);
  });
});

describe('同步结果汇总', () => {
  it('统计成功/失败并给出可读消息', () => {
    const summary = summarizeSync([
      { id: '1', ok: true, detection: { disease_name: '番茄早疫病' } },
      { id: '2', ok: true, detection: { pest_info: { name: '草莓叶焦病' } } },
      { id: '3', ok: false, error: '网络错误' },
    ]);
    expect(summary.total).toBe(3);
    expect(summary.success).toBe(2);
    expect(summary.failed).toBe(1);
    expect(summary.names).toEqual(['番茄早疫病', '草莓叶焦病']);
    expect(summary.message).toContain('已同步 2 张');
    expect(summary.message).toContain('1 张失败');
  });

  it('空队列给友好提示', () => {
    expect(summarizeSync([]).message).toBe('没有待同步的识别任务');
  });

  it('结果里没有病害名时不报错', () => {
    const summary = summarizeSync([{ id: '1', ok: true, detection: {} }]);
    expect(summary.success).toBe(1);
    expect(summary.names).toEqual([]);
  });
});

describe('离线存储适配器选择', () => {
  it('IndexedDB 不可用时退回内存模式（不抛错）', async () => {
    vi.resetModules();
    const original = globalThis.indexedDB;
    // 模拟隐私模式：indexedDB 存在但打开就失败 → 这里直接删掉，走 hasIndexedDB 分支
    delete globalThis.indexedDB;
    try {
      const mod = await import('@/utils/offlineStorage');
      const queue = mod.getOfflineQueue();
      await queue.add({ blob: new Blob(['x']), filename: 'x.jpg' });
      expect((await queue.count()).pending).toBe(1);
    } finally {
      if (original !== undefined) globalThis.indexedDB = original;
    }
  });

  it('资料包可写入并读回（localStorage）', async () => {
    const mod = await import('@/utils/offlineStorage');
    mod.saveWikiPack({ version: 'v1', count: 2, items: [{ id: 1, name: '番茄早疫病' }], source_note: 'n' });
    const pack = mod.readWikiPack();
    expect(pack.version).toBe('v1');
    expect(pack.items[0].name).toBe('番茄早疫病');
    expect(mod.wikiPackVersion()).toBe('v1');
  });
});
