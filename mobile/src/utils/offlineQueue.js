/**
 * 离线队列（移动端，第 91 批）
 * ------------------------------------------------------------------
 * 与桌面端 `frontend/src/utils/offlineQueue.js` 是**同一套逻辑**（刻意复制而不是共享：
 * 两个工程零共享代码是第 75 批定下的规矩，跨工程 import 会让两端构建互相牵制）。
 *
 * 断网时拍的照片先存本地，联网后自动补传识别。
 *
 * 设计要点：
 *   · 队列逻辑（`createOfflineQueue`）**不直接依赖 IndexedDB**，而是接收一个"存储适配器"，
 *     这样纯逻辑可以用内存适配器测，浏览器里换成 IndexedDB 适配器；
 *   · 每条任务带 `id / createdAt / status / tries / lastError`，失败三次后标记为 `failed`，
 *     不静默丢弃（用户能在界面上看到"这张没传上去"）；
 *   · 图片以 Blob 存储，不上传前不落服务端。
 */
import { t } from '@/i18n';

/** 内存适配器（IndexedDB 不可用时兜底；隐私模式下功能降级为"本次会话内可排队"） */
export function createMemoryAdapter() {
  const store = new Map();
  return {
    async put(item) {
      store.set(item.id, item);
    },
    async all() {
      return Array.from(store.values());
    },
    async remove(id) {
      store.delete(id);
    },
    async clear() {
      store.clear();
    },
  };
}

/** 生成任务 id（时间戳 + 随机，够用且可读） */
export function makeTaskId(now = Date.now()) {
  return `off-${now}-${Math.random().toString(36).slice(2, 8)}`;
}

export const MAX_TRIES = 3;

/**
 * 创建一个离线队列
 * @param {{put:Function, all:Function, remove:Function, clear:Function}} adapter
 * @param {{now?:Function, idFactory?:Function}} options
 */
export function createOfflineQueue(adapter, options = {}) {
  const now = options.now || (() => Date.now());
  const idFactory = options.idFactory || (() => makeTaskId(now()));

  return {
    /** 入队一张待识别图片 */
    async add({ blob, filename = 'photo.jpg', note = '', size = 0 }) {
      const item = {
        id: idFactory(),
        blob,
        filename,
        note,
        size,
        createdAt: now(),
        status: 'pending',
        tries: 0,
        lastError: '',
      };
      await adapter.put(item);
      return item;
    },

    /** 全部任务（按入队时间升序，先来先传） */
    async list() {
      const items = await adapter.all();
      return items.sort((a, b) => a.createdAt - b.createdAt);
    },

    /** 待传任务 */
    async pending() {
      const items = await this.list();
      return items.filter((item) => item.status !== 'failed');
    },

    async count() {
      const items = await this.list();
      return {
        total: items.length,
        pending: items.filter((item) => item.status !== 'failed').length,
        failed: items.filter((item) => item.status === 'failed').length,
      };
    },

    async markTried(id, error = '') {
      const items = await adapter.all();
      const target = items.find((item) => item.id === id);
      if (!target) return null;
      target.tries = (target.tries || 0) + 1;
      target.lastError = String(error || '').slice(0, 200);
      if (target.tries >= MAX_TRIES) target.status = 'failed';
      await adapter.put(target);
      return target;
    },

    async remove(id) {
      await adapter.remove(id);
    },

    async clear() {
      await adapter.clear();
    },
  };
}

/**
 * 汇总一次同步的结果（纯函数，便于测试）
 * @param {Array<{id:string, ok:boolean, detection?:object, error?:string}>} results
 */
export function summarizeSync(results = []) {
  const succeeded = results.filter((item) => item.ok);
  const failed = results.filter((item) => !item.ok);
  // 只收真实病害名：拿不到名字就不往消息里塞"未知结果"（数量本身已经说明同步了几张）
  const names = succeeded
    .map((item) => item.detection?.disease_name || item.detection?.pest_info?.name || '')
    .filter(Boolean);

  return {
    total: results.length,
    success: succeeded.length,
    failed: failed.length,
    names,
    message: results.length === 0
      ? t('offline.nothingToSync')
      : failed.length
        ? t('offline.syncedWithFailed', { count: succeeded.length, failed: failed.length })
        : t('offline.synced', { count: succeeded.length }),
  };
}
