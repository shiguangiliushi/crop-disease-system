/**
 * 内容管理接口（第 38 批）
 * · 发帖审核：待审核列表、通过、驳回
 * · 敏感词：词库增删查
 * · 站点配置：发帖是否需要审核
 */
import http from './http';

/** 站点公开配置（发帖是否需要审核等） */
export function fetchSiteConfig() {
  return http.get('site-config/').then((res) => res.data);
}

/** 待审核（或指定状态）的帖子列表——仅管理员可用 */
export function fetchPostsByStatus(status = 'pending', params = {}) {
  return http
    .get('forums/posts/', { params: { status, page_size: 20, ordering: 'created_at', ...params } })
    .then((res) => res.data);
}

/** 审核通过 */
export function approvePost(postId) {
  return http.post(`forums/posts/${postId}/approve/`).then((res) => res.data);
}

/** 审核驳回（可带原因，会通知作者） */
export function rejectPost(postId, reason = '') {
  return http.post(`forums/posts/${postId}/reject/`, { reason }).then((res) => res.data);
}

/**
 * 批量审核（第 100 批）
 *
 * 逐条执行、不整体失败：响应里给每条的成败与原因。
 * 只处理 `pending` 状态的帖子，其它状态会被跳过并在 `detail` 里说明。
 *
 * @param {Array<number|string>} ids
 * @param {'approve'|'reject'} action
 * @param {string} [reason] 驳回原因（approve 时忽略）
 */
export function bulkReviewPosts(ids, action, reason = '') {
  return http
    .post('forums/posts/bulk-review/', { ids, action, reason })
    .then((res) => res.data);
}

/** 敏感词列表 */
export function fetchSensitiveWords(params = {}) {
  return http.get('sensitive-words/', { params }).then((res) => res.data);
}

/** 新增敏感词 */
export function createSensitiveWord(data) {
  return http.post('sensitive-words/', data).then((res) => res.data);
}

/** 删除敏感词 */
export function deleteSensitiveWord(id) {
  return http.delete(`sensitive-words/${id}/`).then((res) => res.data);
}

/**
 * 病害百科的**精简列表**（第 91 批）
 *
 * 用于「识别不正确 → 请选择正确病害」的下拉：识别纠错要变成训练样本，
 * 就必须知道"正确是哪一种"，否则负反馈只能计数、成不了标签。
 *
 * 只取 id / 名称 / 英文标识三个字段（38 条量级，一次拉完；不引第三个下拉组件）。
 */
export async function fetchPestOptions({ pageSize = 200 } = {}) {
  const data = await http
    .get('pests/', { params: { page: 1, page_size: pageSize } })
    .then((res) => res.data);

  // 兼容三种返回：DRF 分页 {results} / 自定义分页 {data:{items}} / 裸数组
  const list = Array.isArray(data)
    ? data
    : (data?.results || data?.data?.items || data?.items || []);

  return list.map((item) => ({
    id: item.id,
    // 英文界面下优先英文名，缺失回落中文（与 localizedField 同规则）
    name: item.name_en || item.name || item.english_identifier,
    nameZh: item.name,
    identifier: item.english_identifier || '',
  }));
}
