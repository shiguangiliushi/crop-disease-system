/**
 * 注册验证码（第 237 批）
 *
 * 后端 `GET /api/captcha/` 直接回 `data:image/png;base64,...`，
 * `<image>` 直接能用 —— 与 H5 同一套接口，不重复实现。
 */
import { request } from '../utils/request'

export async function fetchCaptcha() {
  const body = await request({ url: '/captcha/' })
  return {
    id: body.captcha_id || '',
    image: body.image || '',
    expiresIn: body.expires_in || 0,
  }
}

/** 第 247 批：登录页要不要验证码（`GET /api/login/`，开关在服务端） */
export async function loginCaptchaRequired() {
  const body = await request({ url: '/login/' })
  return Boolean(body.captcha_required)
}
