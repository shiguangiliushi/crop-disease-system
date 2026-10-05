/**
 * 管理员数据看板接口（第 39 批）
 */
import http from './http';

/** 看板聚合数据（仅管理员）；days 为趋势天数（7~90） */
export function fetchDashboard(days = 14) {
  return http.get('admin/dashboard/', { params: { days } }).then((res) => res.data);
}
