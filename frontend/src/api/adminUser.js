/**
 * 管理端用户管理接口（第 76 批）
 * ------------------------------------------------------------------
 * 背景：管理后台此前**没有用户管理**页（只有新闻/反馈/审核/看板），
 * 管理员想查"平台上有哪些用户、谁是专家"只能进 Django 自带的 /admin/。
 *
 * 后端接口（均要求 is_staff，见 api/views_user.py 的 AdminUserListView）：
 *   GET    /api/admin/users/           列表（search / role / status / page / page_size）
 *   GET    /api/admin/users/{id}/      单个用户详情
 *   DELETE /api/admin/users/{id}/      删除用户（第 95 批，软删除）
 *
 * 授予 / 取消专家不在本文件：那是专家咨询域的接口，统一走 @/api/consult.js
 * （`grantExpert` / `revokeExpert`），避免同一个后端接口有两处封装。
 */
import http from './http';

/**
 * 用户列表
 * @param {{search?: string, role?: string, status?: string, page?: number, page_size?: number,
 *          include_deleted?: boolean}} params
 * @returns {Promise<{count: number, next: string|null, previous: string|null, results: object[]}>}
 */
export function fetchAdminUsers(params = {}) {
  return http.get('admin/users/', { params }).then((res) => res.data);
}

/**
 * 单个用户详情
 * @param {number|string} userId
 */
export function fetchAdminUser(userId) {
  return http.get(`admin/users/${userId}/`).then((res) => res.data);
}

/**
 * 删除用户（第 95 批，软删除）
 *
 * `confirm` 必须是**对方的用户名**：后端以此作为"确认删除哪一行"的凭据，
 * 防止误点（表格里每行都有按钮，旁边就是"取消专家"）。
 *
 * @param {number|string} userId
 * @param {string} confirmUsername
 */
export function deleteAdminUser(userId, confirmUsername) {
  return http
    .delete(`admin/users/${userId}/`, { data: { confirm: confirmUsername } })
    .then((res) => res.data);
}

/**
 * 批量删除用户（第 100 批，软删除）
 *
 * 与单条删除**共用同一套后端护栏**（不能删自己 / 不能删超管 / 非超管不能删管理员），
 * 而且是**逐条执行**的：部分失败会如实返回，不会"以为都删了"。
 *
 * @param {Array<number|string>} ids
 * @returns {Promise<{requested:number, succeeded:number, failed:number,
 *                    results: Array<{id:number, ok:boolean, detail:string}>}>}
 */
export function bulkDeleteAdminUsers(ids) {
  return http
    .post('admin/users/bulk-delete/', { ids })
    .then((res) => res.data);
}
