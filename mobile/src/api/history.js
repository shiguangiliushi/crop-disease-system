/**
 * 识别记录接口（移动端）
 *
 * 后端返回结构：{code, msg, data:{items, total, page, page_size, total_pages}}
 * （不是 DRF 默认的 {count, results}，别照抄其它项目的写法）
 */
import http from './http';
import { normalizeHistoryItem } from '@/utils/detectionResult';

/**
 * 识别记录分页列表
 * @param {{page?: number, page_size?: number}} params
 * @returns {Promise<{items: Array, total: number, page: number, totalPages: number, hasNext: boolean}>}
 */
export async function fetchHistory({ page = 1, page_size = 10 } = {}) {
  const response = await http.get('/detection-history/', { params: { page, page_size } });
  const payload = response.data || {};
  const inner = payload.data || payload;
  const rawItems = Array.isArray(inner) ? inner : inner.items || inner.results || [];

  const total = inner.total ?? rawItems.length;
  const totalPages = inner.total_pages ?? Math.max(1, Math.ceil(total / page_size));

  return {
    items: rawItems.map(normalizeHistoryItem),
    total,
    page: inner.page ?? page,
    totalPages,
    hasNext: inner.has_next ?? page < totalPages,
  };
}

/** 单条识别记录详情 → 统一视图模型 */
export async function fetchHistoryDetail(id) {
  const response = await http.get(`/detection-history/${id}/`);
  const payload = response.data || {};
  return normalizeHistoryItem(payload.data || payload);
}

/** 删除一条识别记录 */
export async function deleteHistory(id) {
  await http.delete(`/detection-history/${id}/`);
  return true;
}

export default { fetchHistory, fetchHistoryDetail, deleteHistory };
