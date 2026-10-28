/**
 * 管理端「助手质量看板」（第 228 批）
 *
 * 后端把一个时间窗内的落库记录聚合成一页 JSON（见 `api/views_assistant_admin.py`）。
 * 这里只做展示 —— 不在前端算任何比率，口径只留一份在后端。
 */
import http from './http';

/**
 * 取助手质量统计
 *
 * @param {number} days 时间窗（1~90；后端会夹紧）
 * @returns {Promise<object>} `{range, totals, languages, trend, gaps, top_sources}`
 */
export function fetchAssistantStats(days = 14) {
  return http.get('/admin/assistant/stats/', { params: { days } }).then((res) => res.data);
}

export default { fetchAssistantStats };
