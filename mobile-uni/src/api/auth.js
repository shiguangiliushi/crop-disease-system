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
