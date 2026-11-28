/**
 * 登录态（第 232 批）
 *
 * 与现有 H5 的差别：存储从 `localStorage` 换成 `uni.getStorageSync` ——
 * 小程序没有 localStorage，`uni.*Storage*` 是唯一三端通用的写法。
 *
 * 为什么 token 存本地而不是内存：手机上应用随时被杀，每次打开都重新登录不可接受
 * （现有 H5 也是同一取舍，见 `mobile/src/utils/authStorage.js` 的说明）。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as authApi from '@/utils/api'
import { TOKEN_KEY, USER_KEY } from '@/utils/request'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(uni.getStorageSync(TOKEN_KEY) || '')
  const user = ref(uni.getStorageSync(USER_KEY) || null)

  const isAuthenticated = computed(() => Boolean(token.value))
  const username = computed(() => (user.value && user.value.username) || '')

  // ==========================================================================
  // 游客试用（第 439 批）
  // --------------------------------------------------------------------------
  // 游客**就是**一个带 token 的用户（`user.is_guest === true`），
  // 所以 isAuthenticated / 请求头 / 401 处理都不用分叉 —— 只多两件事：
  //   1. 进识别页发现没身份时自动开一个（而不是把人送到登录页）；
  //   2. 把"今天还能识别几次"显示出来，用完引导注册。
  // ==========================================================================
  const isGuest = computed(() => Boolean(user.value && user.value.is_guest))
  const quota = ref(null)

  /**
   * 开一个游客身份
   * @returns {Promise<boolean>} 成功与否；失败时调用方继续走"跳登录页"
   */
  async function startGuestTrial() {
    try {
      const data = await authApi.startGuestTrial()
      user.value = data.user
      token.value = data.token
      persist()
      quota.value = data.quota || null
      return true
    } catch (error) {
      // 403（试用关闭）/ 429（限流）/ 断网都走这里
      console.warn('[guest] 开启试用失败', error && error.message)
      return false
    }
  }

  /** 刷新剩余次数（识别成功 / 额度用尽后各调一次） */
  async function refreshQuota() {
    if (!token.value) return null
    try {
      const data = await authApi.fetchGuestQuota()
      if (data && typeof data === 'object') quota.value = data
      return quota.value
    } catch (error) {
      console.warn('[guest] 查额度失败', error && error.message)
      return quota.value
    }
  }

  /** 只清本地身份（401 拦截器用；不清额度会让下一个人看到上一个人的次数） */
  function clearAuth() {
    token.value = ''
    user.value = null
    quota.value = null
    try {
      uni.removeStorageSync(TOKEN_KEY)
      uni.removeStorageSync(USER_KEY)
    } catch (error) {
      /* 忽略 */
    }
  }

  function persist() {
    try {
      if (token.value) uni.setStorageSync(TOKEN_KEY, token.value)
      if (user.value) uni.setStorageSync(USER_KEY, user.value)
    } catch (error) {
      console.warn('[auth] 保存登录态失败', error)
    }
  }

  async function login(credentials) {
    const data = await authApi.login(credentials)
    token.value = data.token
    user.value = data.user
    // 第 439 批：真实账号登录后，试用额度不再有意义
    quota.value = null
    persist()
    return data.user
  }

  /**
   * 直接写入凭证（注册即登录用，第 237 批）
   *
   * 注册接口本身返回 `{user, token}`，没必要再让用户输一次密码；
   * 但必须走同一个 `persist()`，否则刷新后 token 丢了。
   */
  async function adopt({ user: account, token: key }) {
    if (!account || !key) return null
    user.value = account
    token.value = key
    quota.value = null
    persist()
    return account
  }

  async function logout() {
    await authApi.logout()
    token.value = ''
    user.value = null
    quota.value = null
    try {
      uni.removeStorageSync(TOKEN_KEY)
      uni.removeStorageSync(USER_KEY)
    } catch (error) {
      /* 忽略 */
    }
  }

  return {
    token,
    user,
    isAuthenticated,
    username,
    // 第 439 批：游客试用
    isGuest,
    quota,
    startGuestTrial,
    refreshQuota,
    clearAuth,
    login,
    adopt,
    logout,
  }
})
