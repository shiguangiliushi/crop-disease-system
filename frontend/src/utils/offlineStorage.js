/**
 * 离线存储（第 50 批）
 * ------------------------------------------------------------------
 * 两块数据：
 *   ① 待识别的图片（Blob）→ IndexedDB（localStorage 存不下二进制且会卡）
 *   ② 病害百科资料包（JSON）→ localStorage（体积小、读取同步、够用）
 *
 * 浏览器不支持 IndexedDB（或隐私模式禁用）时，自动退回内存适配器：
 * 功能降级为"本次会话内可排队"，而不是直接报错。
 */
import { createMemoryAdapter, createOfflineQueue } from './offlineQueue';

const DB_NAME = 'crop_offline';
const DB_VERSION = 1;
const STORE = 'pending_detections';
export const WIKI_CACHE_KEY = 'offline_wiki_pack';

function hasIndexedDB() {
  try {
    return typeof indexedDB !== 'undefined' && indexedDB !== null;
  } catch {
    return false;
  }
}

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'id' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function createIndexedDbAdapter() {
  const withStore = async (mode, handler) => {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const store = tx.objectStore(STORE);
      let result;
      try {
        result = handler(store);
      } catch (error) {
        reject(error);
        return;
      }
      tx.oncomplete = () => resolve(result);
      tx.onerror = () => reject(tx.error);
    });
  };

  return {
    async put(item) {
      await withStore('readwrite', (store) => store.put(item));
    },
    async all() {
      const db = await openDb();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, 'readonly');
        const request = tx.objectStore(STORE).getAll();
        request.onsuccess = () => resolve(request.result || []);
        request.onerror = () => reject(request.error);
      });
    },
    async remove(id) {
      await withStore('readwrite', (store) => store.delete(id));
    },
    async clear() {
      await withStore('readwrite', (store) => store.clear());
    },
  };
}

let queueInstance = null;

/** 取全局离线队列（懒加载，避免每个组件各建一份） */
export function getOfflineQueue() {
  if (!queueInstance) {
    const adapter = hasIndexedDB() ? createIndexedDbAdapter() : createMemoryAdapter();
    queueInstance = createOfflineQueue(adapter);
    if (!hasIndexedDB()) {
      console.warn('[offline] IndexedDB 不可用，离线队列退回内存模式（刷新后丢失）');
    }
  }
  return queueInstance;
}

/** 仅供测试重置 */
export function __resetOfflineQueue(adapter) {
  queueInstance = createOfflineQueue(adapter || createMemoryAdapter());
  return queueInstance;
}

// ---------------- 病害百科资料包缓存（localStorage） ----------------

export function saveWikiPack(pack) {
  try {
    localStorage.setItem(WIKI_CACHE_KEY, JSON.stringify({
      version: pack.version,
      savedAt: Date.now(),
      count: pack.count,
      items: pack.items || [],
      sourceNote: pack.source_note || '',
    }));
    return true;
  } catch (error) {
    console.warn('[offline] 保存资料包失败（可能超出容量）:', error);
    return false;
  }
}

export function readWikiPack() {
  try {
    const raw = localStorage.getItem(WIKI_CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function wikiPackVersion() {
  return readWikiPack()?.version || '';
}
