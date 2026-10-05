/**
 * 账号安全相关接口（第 35 批）
 * ------------------------------------------------------------------
 * 用户反馈里的"安全性/账号体验"三项：
 *   · 注册用户名实时可用性校验
 *   · 忘记密码（邮箱重置）
 * 统一走 @/api/http 客户端（自动带 Token/CSRF、统一错误文案）。
 */
import http from './http';

/**
 * 注册时实时校验用户名是否可用
 * @param {string} username
 * @returns {Promise<{available: boolean, message: string, username: string}>}
 */
export function checkUsernameAvailability(username) {
  return http
    .get('users/check-username/', { params: { username } })
    .then((res) => res.data)
    .catch((error) => {
      // 校验接口失败不该阻塞注册流程：交给后端在提交时兜底校验
      console.warn('用户名可用性校验失败:', error);
      return { available: null, message: '', username };
    });
}

/**
 * 申请重置密码（后端会给注册邮箱发一封带链接的邮件）
 * 无论账号是否存在，后端都返回同样的话术（防用户名枚举）
 * @param {string} account 用户名或邮箱
 */
export function requestPasswordReset(account) {
  return http
    .post('password-reset/', { username_or_email: account })
    .then((res) => res.data);
}

/**
 * 用邮件里的 uid + token 设置新密码
 * @param {{uid: string, token: string, newPassword: string}} payload
 */
export function confirmPasswordReset({ uid, token, newPassword }) {
  return http
    .post('password-reset/confirm/', { uid, token, new_password: newPassword })
    .then((res) => res.data);
}

/** 注销账号时必须在请求体里回传这个字面量（与后端 AccountDeleteView.CONFIRM_WORD 一致） */
export const DELETE_ACCOUNT_CONFIRM_WORD = 'DELETE';

/**
 * 申请注销自己的账号（第 95 批新增，第 101 批改为**冷静期**）
 *
 * 后端**不立刻删除**：账号立即停用、无法登录，但进入 15 天冷静期（天数由后端返回），
 * 期间凭密码可随时取消。到期由后端定时任务执行真正的删除（清个人信息、让出用户名）。
 * 帖子与评论始终保留（内容属于社区，硬删会连带把别人的回复一起带走）。
 *
 * @param {{password: string}} payload 当前密码（必须校验，避免会话被盗后一键销号）
 */
export function deleteMyAccount({ password }) {
  return http
    .post('users/me/delete/', { password, confirm: DELETE_ACCOUNT_CONFIRM_WORD })
    .then((res) => res.data);
}

/**
 * 取消注销申请（第 101 批）
 *
 * ⚠️ 这个接口**不需要登录**：冷静期内账号已停用，用户根本拿不到 Token。
 * 身份靠"用户名 + 密码"自己认（后端会校验），所以登录页也能调用它。
 *
 * @param {{username: string, password: string}} payload
 * @returns {Promise<{status: string, message: string, token: string, username: string}>}
 */
export function cancelMyDeletion({ username, password }) {
  return http
    .post('users/me/cancel-deletion/', { username, password })
    .then((res) => res.data);
}
