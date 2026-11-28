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
// 第 439 批：游客试用（免登录 3 次识别）
import { fetchGuestQuota, startGuestSession } from '@/api/guest';
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

  // ==========================================================================
  // 游客试用（第 439 批）
  // --------------------------------------------------------------------------
  // 游客**就是**一个带 token 的用户（`user.is_guest === true`），所以
  // `isAuthenticated`、请求拦截器都不用分叉 —— 只多两件事：
  //   1. 进识别页发现没身份时自动开一个（而不是把人送到登录页）；
  //   2. 把"今天还能识别几次"显示出来，用完引导注册。
  // 手机上没有问答页，所以只用到识别额度。
  // ==========================================================================
  const isGuest = computed(() => Boolean(user.value?.is_guest));
  const quota = ref(null);

  /**
   * 开一个游客身份
   * @returns {Promise<boolean>} 成功与否；失败时调用方继续走"跳登录页"
   */
  async function startGuestTrial() {
    try {
      const payload = await startGuestSession();
      if (!payload?.token || !payload?.user) {
        console.warn('[guest] 开试用返回结构不认识:', payload);
        return false;
      }
      user.value = payload.user;
      token.value = payload.token;
      saveIdentity({ user: payload.user, token: payload.token });
      quota.value = payload.quota || null;
      return true;
    } catch (error) {
      // 403（试用关闭）/ 429（限流）都走这里
      console.warn('[guest] 开启试用失败:', error?.message || error);
      return false;
    }
  }

  /** 刷新剩余次数（识别成功 / 额度用尽后各调一次） */
  async function refreshQuota() {
    if (!token.value) return null;
    try {
      const data = await fetchGuestQuota();
      if (data && typeof data === 'object') quota.value = data;
      return quota.value;
    } catch (error) {
      console.warn('[guest] 查额度失败:', error?.message || error);
      return quota.value;
    }
  }

  async function login(credentials) {
    const payload = await authApi.login(credentials);
    user.value = payload.user;
    token.value = payload.token;
    // 第 439 批：真实账号登录后，游客额度不再有意义
    quota.value = null;
    saveIdentity({ user: payload.user, token: payload.token });
    return payload.user;
  }

  async function register(payload) {
    const result = await authApi.register(payload);
    // 后端若直接签发 token 就顺手登录，否则由页面跳去登录页
    if (result?.token && result?.user) {
      user.value = result.user;
      token.value = result.token;
      quota.value = null;
      saveIdentity({ user: result.user, token: result.token });
    }
    return result;
  }

  async function logout() {
    await authApi.logout();
    user.value = null;
    token.value = null;
    quota.value = null;
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
    quota.value = null;
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
    // 第 439 批：游客试用
    isGuest,
    quota,
    startGuestTrial,
    refreshQuota,
    login,
    register,
    logout,
    clearAuth,
    updateUser,
  };
});
