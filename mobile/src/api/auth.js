/**
 * 认证接口（移动端）
 * ----------------------------------------------------------------------------
 * 后端登录成功返回的是**带包装**的结构：`{status, message, data:{user, token}}`。
 * 这里统一"向下找真正含 user/token 的那一层"，兼容后端将来改成扁平结构，
 * 避免把某一层的形状写死（桌面端踩过这个坑）。
 */
import http from './http';

function unwrapAuthPayload(responseData) {
  let cur = responseData;
  for (let depth = 0; depth < 3 && cur && typeof cur === 'object'; depth += 1) {
    if (cur.user && cur.token) return cur;
    if (cur.data && typeof cur.data === 'object') {
      cur = cur.data;
      continue;
    }
    break;
  }
  return cur && typeof cur === 'object' ? cur : {};
}

/** 登录：成功返回 {user, token}，失败抛出带可读文案的 Error */
export async function login({ username, password }) {
  // 第 231 批：`device: 'mobile'` —— 后端"每设备一张 token"，手机登录不再把桌面挤下线
  const response = await http.post('/login/', { username, password, device: 'mobile' });
  const body = response.data || {};
  const payload = unwrapAuthPayload(body);

  if (body.status === 'error' || payload.status === 'error') {
    throw new Error(payload.message || body.message || '登录失败');
  }
  if (!payload.user || !payload.token) {
    throw new Error('登录失败：服务器返回的数据格式不正确');
  }
  return { user: payload.user, token: payload.token };
}

/** 注册：后端可能直接签发 token（自动登录），也可能只返回成功 */
export async function register(payload) {
  const response = await http.post('/register/', payload);
  return unwrapAuthPayload(response.data || {});
}

/** 退出登录：接口失败不阻塞本地清理（调用方负责清状态） */
export async function logout() {
  try {
    await http.post('/logout/');
  } catch (error) {
    console.warn('[auth] 退出接口失败，忽略:', error?.message || error);
  }
}

/** 拉取当前登录用户资料（登录响应里的 user 字段可能不含最新统计） */
export async function fetchProfile(userId) {
  const response = await http.get(`/users/${userId}/`);
  return response.data?.data || response.data;
}

/**
 * 请求重置密码（第 91 批）
 *
 * 后端：`POST /api/password-reset/`，`{ username_or_email }` → 给注册邮箱发重置链接。
 * 安全说明：**无论账号是否存在，返回话术一致**（防账号枚举），所以调用方
 * 不需要（也不应该）根据响应判断"这个账号在不在"。
 */
export async function requestPasswordReset(account) {
  const response = await http.post('/password-reset/', { username_or_email: account });
  return response.data?.data || response.data || {};
}

export default { login, register, logout, fetchProfile, requestPasswordReset };
