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
 *   POST   /api/admin/users/{id}/reset-link/   签发一次性密码重置链接（第 120 批）
 *   POST   /api/admin/users/{id}/role/         调整角色（第 127 批，仅超级管理员）
 *
 * 第 124 批起，这里的权限口径不再是"is_staff"，而是后端 `capabilities.py` 里的
 * `USER_ADMIN` 能力（全权管理员都有；信息编辑员 EDITOR 没有）。
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

/**
 * 给某个用户签发**一次性密码重置链接**（第 120 批）
 *
 * 为什么需要它：自助找回密码（`/api/password-reset/`）只在账号**绑了邮箱**时才发信，
 * 没绑邮箱时后端按防枚举策略静默什么都不做（而页面照样显示"已发送"）——
 * 管理端账号大多是超管开通的、常常没绑邮箱，于是"管理员忘了密码"无路可走。
 *
 * 这个接口生成一条 1 小时有效、只能用一次的链接，由管理员**线下**发给本人，
 * 本人在 `/reset-password` 自己设新密码。接口**不返回明文密码**。
 *
 * 若该账号绑了邮箱，后端会顺手也发一封邮件（`mailed=true`）。
 *
 * 护栏（后端）：仅管理员；不能给权限不低于自己的账号签发（防提权）。
 *
 * @param {number|string} userId
 * @returns {Promise<{status:string, username:string, url:string, expires_in_minutes:number,
 *                    has_email:boolean, mailed:boolean, message:string}>}
 */
export function createAdminResetLink(userId) {
  return http
    .post(`admin/users/${userId}/reset-link/`)
    .then((res) => res.data);
}

/**
 * 调整某个用户的角色与**内容模块**（第 127/128 批）
 *
 * 后端护栏：只有**超级管理员**能调；只能在 `EDITOR`（信息编辑员）与 `USER`
 * （普通用户）之间切换；不能改自己；不能动管理员账号（升管理员请走 Django admin）。
 *
 * 第 128 批起内容能力拆成四个模块，改成 EDITOR 时必须带 `modules`
 * （至少一个），否则后端 400 —— 一个模块都没有的编辑员进后台什么也做不了。
 *
 * @param {number|string} userId
 * @param {'EDITOR'|'USER'} role
 * @param {string[]} [modules] 内容模块：review / news / pests / feedback
 *        （改成 USER 时忽略，后端会顺手清空他的模块授权）
 * @returns {Promise<{id:number, username:string, role:string, content_modules:string[],
 *                    changed:boolean, detail:string}>}
 */
export function updateUserRole(userId, role, modules) {
  const payload = { role };
  if (Array.isArray(modules)) payload.modules = modules;
  return http
    .post(`admin/users/${userId}/role/`, payload)
    .then((res) => res.data);
}

/**
 * 停用 / 恢复一个账号（第 137 批）
 *
 * 背景：用户管理页早就有「已禁用」筛选与状态标签，却**没有入口能停用账号** ——
 * 状态只能来自"用户自助注销（冷静期）"或"管理员删除（软删除）"，而这两类都被默认列表
 * 排除，于是那个筛选在控制台里永远筛不出东西；「重置密码」的拒绝语还写着
 * "请先恢复账号再重置密码"，可界面上根本没有"恢复"入口。这个接口把链路补齐。
 *
 * 后端行为（护栏在服务端，前端只是"别让人白点一次"）：
 *   · 停用：立刻作废对方的 token（他马上掉线且登不回来），**恢复后需要重新登录**；
 *   · 恢复：密码全程没动过，所以不需要重置密码就能登回来；
 *   · 不能停用自己；非超管不能停用权限不低于自己的账号（与删除同一套口径）。
 *
 * @param {number} userId
 * @param {boolean} isActive  false = 停用，true = 恢复
 * @returns {Promise<{status:string, changed:boolean, user:object, message:string}>}
 */
export function updateUserStatus(userId, isActive) {
  return http
    .post(`admin/users/${userId}/status/`, { is_active: isActive })
    .then((res) => res.data);
}

/**
 * 开通一个信息编辑员账号（第 131 批）
 *
 * 在这之前"新建编辑员"只能去 Django admin 建号、再回用户管理勾模块，
 * 而且新建的账号还得自己想办法设密码。这个接口一次做完：
 *
 *   1. 建号（角色直接是 EDITOR，模块写进 EditorModuleGrant）；
 *   2. **不设密码** —— 后端用 `set_unusable_password()`，没有任何明文密码经手；
 *   3. 返回一条**一次性设置密码链接**（1 小时有效、改密即失效），
 *      超管线下发给本人，本人在 `/reset-password` 自己设密码。
 *
 * 护栏（与改角色同一套）：**只有超级管理员**；用户名符合规则且未被占用；
 * 邮箱可选但填了要合法且未占用；至少给一个内容模块。
 *
 * @param {{username: string, email?: string, modules: string[]}} payload
 * @returns {Promise<{status:string, user:object, url:string, expires_in_minutes:number,
 *                    has_email:boolean, mailed:boolean, message:string}>}
 */
export function createEditorAccount(payload) {
  return http.post('admin/users/create-editor/', payload).then((res) => res.data);
}
