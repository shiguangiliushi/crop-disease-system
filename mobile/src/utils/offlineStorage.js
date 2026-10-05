/**
 * 离线存储（移动端，第 91 批）
 * ------------------------------------------------------------------
 * 待识别的图片（Blob）→ IndexedDB。
 *
 * 为什么不用 localStorage：localStorage 只能存字符串，图片要转 base64（体积涨 1/3），
 * 而且同步读写会卡住主线程 —— 手机上拍照动辄 1~3MB，用 localStorage 是自找麻烦。
 *
 * 浏览器不支持 IndexedDB（或隐私模式禁用）时自动退回内存适配器：
 * 功能降级为"本次会话内可排队"，而不是直接报错。
 */
import { createMemoryAdapter, createOfflineQueue } from './offlineQueue';

const DB_NAME = 'crop_mobile_offline';
const DB_VERSION = 1;
const STORE = 'pending_detections';

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

/** 通知界面刷新角标（组件监听这个事件即可，不必自己轮询） */
export function notifyQueueChanged() {
  try {
    window.dispatchEvent(new Event('offline-queue-changed'));
  } catch {
    /* 非浏览器环境忽略 */
  }
}
