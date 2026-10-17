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

  //: ⚠️ 第 225 批（P2-7）：联系方式。
  //: 这个函数是**逐字段拼 FormData** 的，不走"整个对象塞进去" —— 漏一行就等于该字段
  //: 永远发不出去，而且后端不会报错（`contact` 有默认值 ''），前端也看不出来。
  //: 第一版就是这样：表单填了联系方式、提交成功，库里存的是空字符串。
  if (payload.contact) {
    formData.append('contact', payload.contact);
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

/**
 * 批量流转处理状态（第 138 批接上前端）
 *
 * 这个接口**第 100 批就在后端写好了**（状态白名单、"标记已处理必须给回复"、
 * 逐条成败、上限 200 条都齐），但前端一直没调用 —— 等于一个死接口。
 * 列表页加上多选后，它才真正被用起来。
 *
 * 服务端规则（前端只是别让人白点一次）：
 *   · 只接受 pending / processing / resolved；
 *   · 传 `status: 'resolved'` 时**必须**带 admin_reply，否则 400；
 *   · 逐条处理不整体失败，返回里给每条的成败。
 *
 * @param {number[]} ids
 * @param {'pending'|'processing'|'resolved'} status
 * @param {string} [adminReply] 统一写进去的回复内容
 * @returns {Promise<{requested:number, succeeded:number, failed:number,
 *                    results:{id:number, ok:boolean, detail:string}[]}>}
 */
export async function bulkUpdateFeedbackStatus(ids, status, adminReply = '') {
  const payload = { ids, status };
  if (adminReply) payload.admin_reply = adminReply;
  const response = await http.post('/feedback/bulk-status/', payload);
  return response.data;
}

/**
 * 批量删除反馈（第 138 批）
 *
 * **仅全权管理员**：批量删除不可逆，而列表页里内容编辑员看到的本来就是全部反馈 ——
 * 开放给他等于把"不能删别人的反馈"这条守卫从后门绕过去。后端同样是 403。
 *
 * @param {number[]} ids
 * @returns {Promise<{requested:number, succeeded:number, failed:number,
 *                    results:{id:number, ok:boolean, detail:string}[]}>}
 */
export async function bulkDeleteFeedback(ids) {
  const response = await http.post('/feedback/bulk-delete/', { ids });
  return response.data;
}

/** 统计卡数据（第 224 批）：一次请求、**跟随当前筛选** */
export async function fetchFeedbackStats(params = {}) {
  const response = await http.get('/feedback/stats/', { params });
  return response.data;
}

/** 确认 / 排除一条识别纠错样本（第 224 批；改前只能在 Django 原生 admin 里勾选） */
export async function verifyFeedbackSample(id, verifyStatus) {
  const response = await http.post(`/feedback/${id}/verify-sample/`, {
    verify_status: verifyStatus,
  });
  return response.data;
}

/** 批量确认 / 排除样本 */
export async function bulkVerifyFeedbackSamples(ids = [], verifyStatus = 'confirmed') {
  const response = await http.post('/feedback/bulk-verify-samples/', {
    ids,
    verify_status: verifyStatus,
  });
  return response.data;
}

/** 按当前筛选导出 CSV（第 225 批 · P2-8）。返回完整响应，好拿 Content-Disposition */
export async function exportFeedbackCsv(params = {}) {
  return http.get('/feedback/export-csv/', { params, responseType: 'blob' });
}

export default {
  submitFeedback,
  fetchMyFeedback,
  deleteFeedback,
  replyFeedback,
  bulkUpdateFeedbackStatus,
  bulkDeleteFeedback,
  fetchFeedbackStats,
  verifyFeedbackSample,
  bulkVerifyFeedbackSamples,
};
