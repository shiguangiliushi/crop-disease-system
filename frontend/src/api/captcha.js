/**
 * 注册验证码（第 233 批）
 *
 * 后端 `GET /api/captcha/` 直接回一张 `data:image/png;base64,...`，
 * 前端不用再发第二个请求拿图 —— 少一次往返，也少一处"图拿了、id 过期了"的错位。
 */
import api from '@/api';

export async function fetchCaptcha() {
  const response = await api.get('captcha/');
  const body = response?.data ?? response ?? {};
  return {
    id: body.captcha_id || '',
    image: body.image || '',
    expiresIn: body.expires_in || 0,
  };
}
