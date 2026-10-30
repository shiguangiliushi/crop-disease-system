/**
 * 意见反馈提交（移动端，第 266 批）
 *
 * 后端 `POST /api/feedback/`（`FeedbackSerializer`）：`category` + `suggestion` 必填，
 * `contact` / `image` 选填。带图片时必须用 **multipart**，否则 DRF 收不到文件。
 */
import http from './http';

export async function submitFeedback({ category, suggestion, contact = '', imageFile = null }) {
  if (imageFile) {
    const form = new FormData();
    form.append('category', category);
    form.append('suggestion', suggestion);
    if (contact) form.append('contact', contact);
    form.append('image', imageFile, imageFile.name || 'feedback.jpg');
    const response = await http.post('/feedback/', form);
    return response.data || {};
  }

  const response = await http.post('/feedback/', {
    category,
    suggestion,
    ...(contact ? { contact } : {}),
  });
  return response.data || {};
}


/** 我的反馈列表（第 268 批）—— 普通用户只返回自己提交的 */
export async function fetchMyFeedback({ pageSize = 20 } = {}) {
  const response = await http.get('/feedback/', { params: { page_size: pageSize } });
  const body = response.data || {};
  const rows = Array.isArray(body) ? body : body.results || body.data?.items || body.data || [];
  return { items: rows, count: body?.count ?? rows.length };
}
