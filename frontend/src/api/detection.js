/**
 * 识别记录接口（第 22 批起由合并后的「识别记录」页 = views/HistoryView.vue 使用；
 * 原「识别记录管理」页已停用）
 *
 * 修复说明（原实现存在多处错误）：
 *   1. 请求路径写成 `/api/history/`，后端并没有该路由（正确为 `/api/detection-history/`）；
 *      而且 apiClient 的 baseURL 已含 `/api`，实际请求会变成 `/api/api/history/` → 404，
 *      管理端页面因此一直拿不到数据；
 *   2. 列表响应结构不匹配：后端返回 `{ code, msg, data: { items, total, ... } }`，
 *      原代码取的是 `response.data.results`（不存在）；
 *   3. 页面用到的 `getDetectionHistory` / `batchDeleteDetectionHistory` 当时根本没有实现。
 */
import http from './http';

/**
 * 识别记录列表
 * @param {object} params { page, page_size, search, pest, user, date, all_users }
 * @returns {Promise<{items: Array, total: number, totalPages: number}>}
 */
export const getAllDetectionHistory = async (params = {}) => {
  const { page = 1, page_size = 6, search, ...rest } = params;

  const query = { page, page_size, ...rest };
  // 后端支持 search=用户名/病害名（第 21 批补齐）。
  // 原来这里把 search 映射成 pest，于是管理端"搜索用户名"永远搜不到东西
  // —— 页面 placeholder 写的是"搜索用户或病害名称"，但实际只能按病害搜。
  if (search) {
    query.search = search;
  }

  const response = await http.get('/detection-history/', { params: query });
  const payload = response.data || {};
  const inner = payload.data || payload;
  const items = Array.isArray(inner) ? inner : inner.items || inner.results || [];

  return {
    items,
    total: inner.total ?? items.length,
    totalPages: inner.total_pages ?? 1,
  };
};

/** 单条识别记录详情 */
export const getDetectionHistory = async ({ id }) => {
  const response = await http.get(`/detection-history/${id}/`);
  return response.data;
};

/** 兼容旧命名 */
export const getDetectionDetail = async (id) => getDetectionHistory({ id });

/** 删除单条识别记录 */
export const deleteDetection = async (id) => {
  await http.delete(`/detection-history/${id}/`);
  return true;
};

/**
 * 批量删除识别记录
 * 后端未提供批量接口，这里逐条删除（管理端一次最多删除一页数据，量可控）
 */
export const batchDeleteDetectionHistory = async ({ ids = [] } = {}) => {
  const results = [];
  for (const id of ids) {
    results.push(await deleteDetection(id));
  }
  return results;
};

export default {
  getAllDetectionHistory,
  getDetectionHistory,
  getDetectionDetail,
  deleteDetection,
  batchDeleteDetectionHistory,
};
