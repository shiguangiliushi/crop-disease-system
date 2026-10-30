/**
 * 病害百科（移动端，第 260 批）
 *
 * 结果页只拿到识别结果的病害名，没有词条 id（`/api/detect/` 返回的是模型类名）。
 * 所以这里用 `search` 先定位词条，再取详情 —— 两次请求都很轻（列表接口本身支持 search）。
 */
import http from './http';

/** 按关键字（病害名 / 模型类名）定位词条，返回第一条或 null */
export async function findPest(keyword) {
  const term = String(keyword || '').trim();
  if (!term) return null;
  const response = await http.get('/pests/', { params: { search: term, page_size: 5 } });
  const body = response.data || {};
  const rows = Array.isArray(body.results) ? body.results : Array.isArray(body) ? body : [];
  return rows[0] || null;
}

/** 词条详情（含症状、防治方法、来源） */
export async function fetchPestDetail(id) {
  const response = await http.get(`/pests/${id}/`);
  return response.data || {};
}
