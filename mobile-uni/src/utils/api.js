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
export async function login({ username, password, captchaId, captchaCode }) {
  const requestBody = { username, password, device: 'app' }
  // 第 247 批：服务端开关打开时带上验证码（关着时多传两个字段无害）
  if (captchaId || captchaCode) {
    requestBody.captcha_id = captchaId || ''
    requestBody.captcha_code = captchaCode || ''
  }
  const body = await request({
    url: '/login/',
    method: 'POST',
    data: requestBody,
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
 * 注册（第 237 批）
 *
 * 后端注册接口**强制校验验证码**（第 233 批），所以必须带 `captcha_id` +
 * `captcha_code`；`device: 'app'` 与登录一致，注册即登录后这张凭证不会被别的端挤掉。
 */
export async function register({ username, password, email, captchaId, captchaCode }) {
  const body = await request({
    url: '/register/',
    method: 'POST',
    data: {
      username,
      password,
      email,
      captcha_id: captchaId,
      captcha_code: captchaCode,
      device: 'app',
    },
  })
  const data = unwrapAuth(body)
  return { user: data.user || null, token: data.token || '' }
}

/**
 * 忘记密码：`POST /api/password-reset/`，`{ username_or_email }`
 *
 * ⚠️ 安全设计：**无论账号是否存在，后端话术一致**（防账号枚举）——
 * 前端不要根据响应判断"这个账号在不在"，一律按"已发送"提示。
 */
export async function requestPasswordReset(account) {
  return request({
    url: '/password-reset/',
    method: 'POST',
    data: { username_or_email: account },
  })
}

/** 注销账号（冷静期）：需要密码确认，与 H5 的 `/users/me/delete/` 一致 */
export async function requestAccountDeletion(password) {
  return request({
    url: '/users/me/delete/',
    method: 'POST',
    data: { password },
  })
}

/** 候选病害列表（反馈"识别错了"时给用户选正确答案） */
export async function fetchPests() {
  const body = await request({ url: '/pests/', data: { page_size: 100 } })
  const inner = body.data || body || {}
  const items = Array.isArray(inner) ? inner : inner.results || inner.items || []
  return items.map((item) => ({ id: item.id, name: item.name || item.name_en || '' }))
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
