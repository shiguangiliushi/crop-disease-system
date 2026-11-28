/**
 * 游客试用接口（第 439 批）
 * ------------------------------------------------------------------
 * 免登录试用的两件事：开一个身份（拿 token）、查还剩几次。
 *
 * 为什么要开"身份"而不是匿名接口：识别历史与助手会话都挂在 `user` 外键上，
 * 匿名调用的第一行就会失败。游客是**真用户**，只是 `is_guest=True` ——
 * 这样识别、追问、历史全部复用现有链路，不必为试用单写一套。
 */
import http from './http';

/**
 * 开启（或复用）游客试用身份
 * @returns {Promise<{user: object, token: string, quota: object}>}
 */
export function startGuestSession() {
  return http.post('guest/session/').then((res) => res.data);
}

/** 查剩余额度（登录用户返回 unlimited） */
export function fetchGuestQuota() {
  return http.get('guest/quota/').then((res) => res.data);
}
