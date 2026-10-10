/**
 * 控制台的评论管理（第 149 批）
 *
 * 对应后端 `api/views_comments_admin.py`（农户端的评论列表挂在帖子下，
 * 控制台要跨帖子看，所以有这一套全局接口）：
 *   · 列表 / 批量软删除：需要 review 内容模块；
 *   · 硬删除（不可逆）：仅全权管理员 —— 前端不画那个按钮，后端也会 403。
 */
import http from './http';

/**
 * 评论列表
 *
 * @param {object} params
 *   `page` / `page_size`  分页
 *   `post`                只看某条帖子下的评论
 *   `author`              只看某个作者的评论
 *   `search`              关键字（匹配评论内容，含英文内容）
 *   `only_deleted`        `true` → **只看**已删除的（审计"谁删了什么"）
 *   `ordering`            `-created_at`（默认）/ `created_at` / `like_count` …
 */
export function fetchAdminComments(params = {}) {
  return http.get('/admin/comments/', { params }).then((res) => res.data);
}

/** 软删除一条评论（review 模块；内容置为 [已删除]，可追溯） */
export function softDeleteComment(commentId) {
  return http.post(`/admin/comments/${commentId}/soft-delete/`).then((res) => res.data);
}

/** 彻底删除一条评论（**仅全权管理员**，不可逆） */
export function hardDeleteComment(commentId) {
  return http.delete(`/admin/comments/${commentId}/`).then((res) => res.data);
}

/**
 * 恢复一条被软删除的评论（第 152 批，**仅全权管理员**）
 *
 * 会把 `content` 放回删除前的原文（后端 `original_content`）。
 * ⚠️ 第 152 批之前删除的评论没有留存原文，后端会返回 400 并说明原因 ——
 *    前端用 `can_restore` 提前禁用按钮，别让用户白点。
 */
export function restoreComment(commentId) {
  return http.post(`/admin/comments/${commentId}/restore/`).then((res) => res.data);
}

/** 批量软删除（review 模块；最多 200 条，逐条成败） */
export function bulkSoftDeleteComments(ids) {
  return http.post('/admin/comments/bulk-delete/', { ids }).then((res) => res.data);
}

export default {
  fetchAdminComments, softDeleteComment, hardDeleteComment, bulkSoftDeleteComments,
  restoreComment,
};
