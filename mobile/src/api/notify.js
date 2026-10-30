/**
 * 站内通知（移动端，第 261 批）
 *
 * 后端接口：`GET /api/notifications/`（分页）、`/unread-count/`、`/read-all/`、`/<id>/read/`。
 * 列表的响应形状有两种可能（DRF 分页 vs 自定义包装），这里统一抹平。
 */
import http from './http';

function rowsOf(body) {
  if (Array.isArray(body)) return body;
  if (Array.isArray(body?.results)) return body.results;
  if (Array.isArray(body?.data?.items)) return body.data.items;
  if (Array.isArray(body?.data)) return body.data;
  return [];
}

export async function fetchNotifications(params = {}) {
  const response = await http.get('/notifications/', { params: { page_size: 20, ...params } });
  const body = response.data || {};
  return { items: rowsOf(body), count: body.count ?? rowsOf(body).length };
}

export async function fetchUnreadCount() {
  try {
    const response = await http.get('/notifications/unread-count/');
    const body = response.data || {};
    return Number(body.unread ?? body.count ?? body.data?.unread ?? 0) || 0;
  } catch (error) {
    return 0;
  }
}

export async function markAllRead() {
  await http.post('/notifications/read-all/');
}
