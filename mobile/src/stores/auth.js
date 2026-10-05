/**
 * 登录态（移动端）
 * ----------------------------------------------------------------------------
 * 单一数据源：这里持有 user/token，并同步到 localStorage（见 utils/authStorage）。
 * 手机端选择"持久登录"：浏览器进程随时会被系统回收，若像桌面端那样放
 * sessionStorage，农户每次打开都要重新输账号密码。
 */
import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import * as authApi from '@/api/auth';
import { clearIdentity, getIdentity, saveIdentity } from '@/utils/authStorage';

export const useAuthStore = defineStore('auth', () => {
  const stored = getIdentity();
  const user = ref(stored.user);
  const token = ref(stored.token);

  const isAuthenticated = computed(() => Boolean(token.value));
  const isAdmin = computed(() =>
    Boolean(user.value?.is_staff || user.value?.is_superuser || user.value?.role === 'ADMIN'),
  );
  const userId = computed(() => user.value?.id ?? null);
  const username = computed(() => user.value?.username || '');

  async function login(credentials) {
    const payload = await authApi.login(credentials);
    user.value = payload.user;
    token.value = payload.token;
    saveIdentity({ user: payload.user, token: payload.token });
    return payload.user;
  }

  async function register(payload) {
    const result = await authApi.register(payload);
    // 后端若直接签发 token 就顺手登录，否则由页面跳去登录页
    if (result?.token && result?.user) {
      user.value = result.user;
      token.value = result.token;
      saveIdentity({ user: result.user, token: result.token });
    }
    return result;
  }

  async function logout() {
    await authApi.logout();
    user.value = null;
    token.value = null;
    clearIdentity();
  }

  /**
   * 只清本地身份，**不调退出接口**（第 91 批）
   *
   * 使用场景：`api/http.js` 的 401 拦截器发现 token 已失效。
   * 为什么必须走这里而不是直接删 localStorage：
   * `isAuthenticated` 是 `computed(() => Boolean(token.value))` —— 读的是**内存里的 ref**，
   * 而 ref 只在 store 创建时从 localStorage 初始化一次。若拦截器只清 localStorage，
   * 内存里的 token 还在 → 路由守卫仍认为"已登录" → 把刚跳到的 `/login`
   * 又弹回 `/detect`（实测就是这个现象：身份清了，人却没回到登录页）。
   */
  function clearAuth() {
    user.value = null;
    token.value = null;
    clearIdentity();
  }

  /** 局部更新用户信息（改昵称/头像后同步） */
  function updateUser(partial = {}) {
    user.value = { ...(user.value || {}), ...partial };
    saveIdentity({ token: token.value, user: user.value });
    return user.value;
  }

  return {
    user,
    token,
    isAuthenticated,
    isAdmin,
    userId,
    username,
    login,
    register,
    logout,
    clearAuth,
    updateUser,
  };
});
