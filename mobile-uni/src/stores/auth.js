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
    persist()
    return account
  }

  async function logout() {
    await authApi.logout()
    token.value = ''
    user.value = null
    try {
      uni.removeStorageSync(TOKEN_KEY)
      uni.removeStorageSync(USER_KEY)
    } catch (error) {
      /* 忽略 */
    }
  }

  return { token, user, isAuthenticated, username, login, adopt, logout }
})
