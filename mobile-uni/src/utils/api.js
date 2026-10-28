/**
 * 接口层（第 232 批）—— 与后端契约一一对应，页面不直接拼 URL
 *
 * 后端的登录响应是**带包装**的：`{status, message, data:{user, token}}`，
 * 这里统一"向下找一层"，页面只拿 `{user, token}`。
 */
import { request, uploadFile } from './request'

/** 把 `{status,message,data:{user,token}}` 或扁平结构统一成 `{user, token}` */
function unwrapAuth(payload) {
  let current = payload
  for (let depth = 0; depth < 3 && current && typeof current === 'object'; depth += 1) {
    if (current.user && current.token) return current
    if (current.data && typeof current.data === 'object') {
      current = current.data
      continue
    }
    break
  }
  return current || {}
}

/** 登录：`device: 'app'` 让后端单独记一张凭证（不会顶掉手机 H5 / 桌面） */
export async function login({ username, password }) {
  const body = await request({
    url: '/login/',
    method: 'POST',
    data: { username, password, device: 'app' },
  })
  const data = unwrapAuth(body)
  if (!data.user || !data.token) {
    throw new Error(body.message || '登录失败：服务器返回的数据格式不正确')
  }
  return { user: data.user, token: data.token }
}

/** 退出登录：接口失败不阻塞本地清理 */
export async function logout() {
  try {
    await request({ url: '/logout/', method: 'POST' })
  } catch (error) {
    console.warn('[auth] 退出接口失败，忽略', error.message)
  }
}

/**
 * 识别一张图
 *
 * @param {string} filePath `uni.chooseImage` 给的临时路径
 * @param {object} options  `crop_hint`（可选，用户先选作物可减少跨作物误判）
 * @returns {Promise<object>} `{ detection, history_id }`
 */
export async function detectImage(filePath, { cropHint = '' } = {}) {
  const formData = {}
  if (cropHint) formData.crop_hint = cropHint
  const body = await uploadFile({ url: '/detect/', filePath, name: 'image', formData })
  const data = body.data || {}
  if (!data.detection) {
    throw new Error(body.message || body.error || '识别失败，请重试')
  }
  return data
}
