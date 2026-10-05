/**
 * 登录态存储（移动端）
 * ----------------------------------------------------------------------------
 * 与桌面端不同的一点：桌面端把身份放在 sessionStorage（"关掉标签页就登出"），
 * 移动端放在 localStorage —— 手机上每次打开都要重新登录是不可接受的
 * （浏览器进程随时被系统回收）。代价是长期驻留，退出登录时会显式清理。
 */
import { TOKEN_KEY, USER_KEY } from '@/api/http';

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function getStoredUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function getIdentity() {
  return { token: getToken(), user: getStoredUser() };
}

export function saveIdentity({ token, user }) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    /* 存不了就只在内存里有效 */
  }
}

export function patchStoredUser(partial = {}) {
  const current = getStoredUser() || {};
  saveIdentity({ token: getToken(), user: { ...current, ...partial } });
}

export function clearIdentity() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    /* 忽略 */
  }
}
