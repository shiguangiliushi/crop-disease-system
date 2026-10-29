/**
 * 运行时配置（第 232 批）
 * ============================================================================
 * 为什么需要它：H5 开发时走 vite 代理（`/api`），但 **APK / 小程序里没有代理** ——
 * 相对路径会解析到"应用自己的域名"上，请求直接失败。
 *
 * 没有域名的情况下，APK 只能连 `http://<电脑局域网IP>:8000`，而 IP 会因为
 * 换网络、重连 Wi-Fi 变来变去。**每换一次就要重新打包显然不现实**，所以：
 *
 *   1. 优先读本地存储里的 `api_base`（登录页的「服务器设置」写入，APP 专属）；
 *   2. 其次读构建期环境变量 `VITE_API_BASE`（有域名后写死在这里）；
 *   3. 最后回落到 `/api`（H5 开发，走 vite 代理）。
 *
 * 读取放在**调用时**而不是模块加载时：用户改完设置不用重启应用。
 */
const STORAGE_KEY = 'api_base'

/** 去掉末尾斜杠，避免拼出 `//api/login/` */
function normalize(base) {
  return String(base || '').trim().replace(/\/+$/, '')
}

/** 用户在 APP 里手填的服务器地址（形如 `http://192.168.1.20:8000/api`） */
export function storedApiBase() {
  try {
    return normalize(uni.getStorageSync(STORAGE_KEY))
  } catch (error) {
    return ''
  }
}

export function saveApiBase(base) {
  const value = normalize(base)
  try {
    if (value) uni.setStorageSync(STORAGE_KEY, value)
    else uni.removeStorageSync(STORAGE_KEY)
  } catch (error) {
    console.warn('[config] 保存服务器地址失败', error)
  }
  return value
}

/** 当前生效的 API 根地址（`.../api`） */
export function apiBase() {
  return storedApiBase() || normalize(import.meta.env.VITE_API_BASE) || '/api'
}
