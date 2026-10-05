import { defineStore } from 'pinia';
import { computed } from 'vue';

import { useAuthStore } from './auth';

/**
 * 用户信息的**适配器 store**（第 70 批修复）
 * ------------------------------------------------------------------
 * 背景（真实 bug）：这个 store 原来自己持有一份 `user = ref(null)`，只提供 `setUser()`，
 * 但**全项目没有任何地方调用过 setUser** —— 于是 `userStore.user` 永远是 null。
 * 后果：`EditPostView` 的 `checkEditPermission()` 第一步就 `if (!userStore.user)` 返回
 * "没有权限"，页面被无条件跳回 /forum —— **编辑帖子页对所有人（含作者和管理员）都打不开**。
 *
 * 修法：把它改成 auth store 的**只读视图**（登录态本来就在 auth store 里，且应用启动时
 * 已由 initAuth/checkAuth 填好），这样既修好调用方，又不会出现"两份用户状态不一致"。
 * `setUser/clearUser` 保留为兼容旧调用（转发给 auth store）。
 */
export const useUserStore = defineStore('user', () => {
  const authStore = useAuthStore();

  const user = computed(() => authStore.user || null);
  const isAuthenticated = computed(() => Boolean(authStore.user));
  const isAdmin = computed(
    () => Boolean(authStore.user?.is_staff || authStore.user?.is_superuser || authStore.user?.role === 'ADMIN'),
  );

  /** 兼容旧调用：写回 auth store，保持单一数据源 */
  function setUser(userData) {
    authStore.user = userData;
  }

  function clearUser() {
    authStore.user = null;
  }

  return {
    user,
    isAuthenticated,
    isAdmin,
    setUser,
    clearUser,
  };
});
