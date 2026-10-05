/**
 * 离线同步（第 50 批）
 * ------------------------------------------------------------------
 * 把本地队列里的图片逐张补传到 `/detect/`，成功就出队。
 * 保守策略：
 *   · 一张失败不影响其它（逐张 try）；
 *   · 失败会记录次数，超过上限标记 `failed` 并保留，不静默丢数据；
 *   · 断网状态下直接返回"离线中"，不做无意义的请求。
 */
import http from '@/api/http';
import { getOfflineQueue } from './offlineStorage';
import { summarizeSync } from './offlineQueue';
import { t } from '@/i18n';  // 第 83 批：提示文案跟随语言

export function isBrowserOnline() {
  try {
    return navigator.onLine !== false;
  } catch {
    return true;
  }
}

/**
 * 同步一张图片到服务端识别
 * 返回 `{ ok, detection, error }`
 */
export async function syncOne(item) {
  const form = new FormData();
  form.append('image', item.blob, item.filename || 'offline.jpg');
  if (item.note) form.append('note', item.note);

  try {
    const response = await http.post('detect/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    const payload = response.data || {};
    const inner = payload.status === 'success' && payload.data ? payload.data : payload;
    const detection = inner.detection || inner;
    const diseaseName = detection?.disease_name
      || detection?.pest_info?.name
      || detection?.result
      || '';
    return { ok: true, detection: { ...detection, disease_name: diseaseName } };
  } catch (error) {
    return { ok: false, error: error?.message || t('msg.operationFailed') };
  }
}

/**
 * 同步整个队列
 * @returns {Promise<{offline?:boolean} & ReturnType<typeof summarizeSync>>}
 */
export async function syncPendingQueue({ onProgress } = {}) {
  if (!isBrowserOnline()) {
    return { ...summarizeSync([]), offline: true, message: t('offline.syncSkipped') };
  }

  const queue = getOfflineQueue();
  const items = await queue.pending();
  const results = [];

  for (const item of items) {
    if (onProgress) onProgress({ current: item, total: items.length });
    const result = await syncOne(item);
    if (result.ok) {
      await queue.remove(item.id);
      results.push({ id: item.id, ok: true, detection: result.detection });
    } else {
      await queue.markTried(item.id, result.error);
      results.push({ id: item.id, ok: false, error: result.error });
    }
  }

  return { ...summarizeSync(results), results };
}

/** 断网时把一张图片存入队列 */
export async function enqueueOfflineImage(file, note = '') {
  const queue = getOfflineQueue();
  const item = await queue.add({
    blob: file,
    filename: file?.name || 'offline.jpg',
    note,
    size: file?.size || 0,
  });
  return item;
}
