/**
 * 请求封装（第 232 批）
 * ============================================================================
 * 为什么不用 axios：小程序端**没有 XMLHttpRequest**，axios 跑不了；uni-app 里
 * 统一用 `uni.request` / `uni.uploadFile` —— 一套代码三端都能发请求。
 *
 * 三个约定（与现有 H5 / 桌面端保持一致，减少"这里和那里不一样"）：
 *   1. 登录态存 `uni_token`（`uni.setStorageSync`），请求自动带 `Authorization: Token xxx`；
 *   2. **401 统一在这里处理**：清 token + 回登录页。页面里不要各写一份 ——
 *      一个页面同时发三四个请求时，每份 401 都跳一次会互相打架；
 *   3. 失败统一抛 `{ message, status, data }`，页面只管展示 `message`。
 */
// 第 232 批：不再在模块加载时定死 —— APK 里要能**运行时**改服务器地址
// （没有域名时只能连局域网 IP，换了 Wi-Fi 就得改，不能每改一次都重新打包）
import { apiBase } from './config'

export const TOKEN_KEY = 'uni_token'
export const USER_KEY = 'uni_user'

function tokenHeader() {
  try {
    const token = uni.getStorageSync(TOKEN_KEY)
    return token ? { Authorization: `Token ${token}` } : {}
  } catch (error) {
    return {}
  }
}

/** 清掉登录态并回登录页（多个请求同时 401 时只跳一次） */
let redirecting = false
export function clearSession() {
  try {
    uni.removeStorageSync(TOKEN_KEY)
    uni.removeStorageSync(USER_KEY)
  } catch (error) {
    /* 忽略 */
  }
  if (redirecting) return
  redirecting = true
  uni.reLaunch({
    url: '/pages/login/login',
    complete: () => {
      setTimeout(() => { redirecting = false }, 600)
    },
  })
}

function normalizeError(statusCode, body) {
  const data = body || {}
  const message = data.message || data.detail || data.error || `请求失败（${statusCode}）`
  const error = new Error(message)
  error.status = statusCode
  error.data = data
  return error
}

/** 普通 JSON 请求 */
export function request({ url, method = 'GET', data, header = {} } = {}) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: `${apiBase()}${url}`,
      method,
      data,
      timeout: 30000,
      header: { 'Content-Type': 'application/json', ...tokenHeader(), ...header },
      success: (res) => {
        if (res.statusCode === 401) {
          clearSession()
          reject(normalizeError(401, res.data))
          return
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
          return
        }
        reject(normalizeError(res.statusCode, res.data))
      },
      fail: (err) => {
        const error = new Error('网络连接失败，请检查网络后重试')
        error.raw = err
        reject(error)
      },
    })
  })
}

/**
 * 上传文件（识别用）
 *
 * ⚠️ 字段名必须是 `image`：后端 `DetectView` 读的就是 `request.FILES['image']`，
 *    与现有 H5 一致。`uni.uploadFile` 的 `name` 就是表单字段名。
 */
export function uploadFile({ url, filePath, name = 'image', formData = {} } = {}) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: `${apiBase()}${url}`,
      filePath,
      name,
      formData,
      timeout: 120000, // 识别要跑模型，30 秒不够（现有 H5 也是 60~120 秒）
      header: tokenHeader(),
      success: (res) => {
        let body = {}
        try {
          body = typeof res.data === 'string' ? JSON.parse(res.data) : res.data
        } catch (error) {
          reject(new Error('服务器返回的数据格式不正确'))
          return
        }
        if (res.statusCode === 401) {
          clearSession()
          reject(normalizeError(401, body))
          return
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(body)
          return
        }
        reject(normalizeError(res.statusCode, body))
      },
      fail: (err) => {
        const error = new Error('上传失败，请检查网络后重试')
        error.raw = err
        reject(error)
      },
    })
  })
}

/** 把后端返回的相对/本机地址转成当前页面能访问的地址（H5 走代理，小程序/APP 用绝对地址） */
export function mediaUrl(path) {
  if (!path) return ''
  if (/^https?:\/\//i.test(path)) {
    // dev 下后端回的是 http://127.0.0.1:8000/media/...，真机上这个地址指向手机自己
    const local = path.match(/^https?:\/\/(?:127\.0\.0\.1|localhost|0\.0\.0\.0)(?::\d+)?(\/.*)$/i)
    if (local) return local[1]
    return path
  }
  return path.startsWith('/') ? path : `/${path}`
}
