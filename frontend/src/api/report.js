/**
 * 举报接口（第 41 批）
 */
import http from './http';

/** 提交举报：{target_type: 'post'|'comment'|'user', target_id, reason, detail} */
export function submitReport(payload) {
  return http.post('reports/', payload).then((res) => res.data);
}

/**
 * 我的举报记录（管理员默认看全部）
 * @param {{status?: string, page?: number, page_size?: number}} params
 */
export function fetchReports(params = {}) {
  return http.get('reports/', { params }).then((res) => res.data);
}

/** 处理举报（仅管理员）：{status: 'handled'|'rejected', note, hide_content} */
export function handleReport(id, payload) {
  return http.post(`reports/${id}/handle/`, payload).then((res) => res.data);
}
