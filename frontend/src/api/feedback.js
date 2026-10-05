/**
 * 意见反馈接口（第 26 批新增）
 *
 * 后端的 FeedbackView（router 注册在 /feedback/）此前只服务"识别结果对不对"这种反馈，
 * 现在扩展为通用意见反馈：类型 / 内容 / 图片 / 处理状态 / 管理员回复。
 */
import http from './http';

/**
 * 提交反馈
 * @param {{category?: string, suggestion: string, disease_name?: string,
 *          confidence?: number, is_correct?: boolean}} payload
 * @param {File|null} imageFile 可选图片
 */
export async function submitFeedback(payload = {}, imageFile = null) {
  const formData = new FormData();
  formData.append('category', payload.category || 'suggestion');
  formData.append('suggestion', payload.suggestion || '');

  // 识别结果反馈才会带的字段
  if (payload.disease_name !== undefined && payload.disease_name !== null) {
    formData.append('disease_name', payload.disease_name);
  }
  if (payload.confidence !== undefined && payload.confidence !== null) {
    formData.append('confidence', payload.confidence);
  }
  if (payload.is_correct !== undefined && payload.is_correct !== null) {
    formData.append('is_correct', String(payload.is_correct));
  }

  if (imageFile) {
    formData.append('image', imageFile);
  }

  const response = await http.post('/feedback/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

/** 我的反馈列表（管理员调用时后端返回全部；支持 category/status/search/user 等参数） */
export async function fetchMyFeedback(params = {}) {
  const response = await http.get('/feedback/', {
    params: { page: 1, page_size: 10, ...params },
  });
  return response.data;
}

/** 撤回（删除）自己的一条反馈；管理员可删除任意一条 */
export async function deleteFeedback(id) {
  await http.delete(`/feedback/${id}/`);
  return true;
}

/**
 * 管理员回复 / 流转处理状态（第 27 批新增）
 *
 * `status` 与 `admin_reply` 在序列化器里是只读的（防止普通用户自评"已处理"），
 * 所以管理端走这个专用动作：POST /feedback/{id}/reply/
 * @param {number|string} id
 * @param {{status?: 'pending'|'processing'|'resolved', admin_reply?: string}} payload
 */
export async function replyFeedback(id, payload = {}) {
  const response = await http.post(`/feedback/${id}/reply/`, payload);
  return response.data;
}

export default { submitFeedback, fetchMyFeedback, deleteFeedback, replyFeedback };
