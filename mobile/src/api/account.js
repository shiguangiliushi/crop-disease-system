/**
 * 账号相关接口（移动端，第 95 批）
 *
 * 目前只有一件：**注销自己的账号**。
 * 在此之前移动端没有任何注销入口，用户只能找管理员 —— 而隐私政策写的是
 * "可申请注销"，属于"说了没做"。现在前后端都补齐了。
 */
import http from './http';

/** 注销时必须在请求体里回传这个字面量（与后端 AccountDeleteView.CONFIRM_WORD 一致） */
export const DELETE_ACCOUNT_CONFIRM_WORD = 'DELETE';

/**
 * 注销自己的账号
 *
 * 后端是**软删除**：清个人信息 + 禁登录 + 失效 Token/会话，但保留帖子与评论
 * （硬删会连带把别人的回复一起带走）。注销后无法再用该账号登录，也无法恢复。
 *
 * @param {{password: string}} payload 当前密码（必须校验，避免会话被盗后一键销号）
 */
export async function deleteMyAccount({ password }) {
  const response = await http.post('/users/me/delete/', {
    password,
    confirm: DELETE_ACCOUNT_CONFIRM_WORD,
  });
  return response.data;
}

export default { deleteMyAccount, DELETE_ACCOUNT_CONFIRM_WORD };
