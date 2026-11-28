/**
 * 游客试用接口（移动端，第 439 批）
 * ----------------------------------------------------------------------------
 * 与桌面端同一套后端接口，只是移动端的身份存在 localStorage（`mobile_token`）。
 * 手机上没有问答页，所以这里实际只用得到"开身份"和"查识别剩余次数"。
 */
import http from './http';
import { unwrapAuthPayload } from './auth';

/**
 * 开启（或复用）游客试用身份
 * @returns {Promise<{user: object, token: string, quota: object}>}
 */
export async function startGuestSession() {
  // `device` 与登录同口径（后端 `device_of()` 认这个字段），只影响日志与"同设备轮换"
  const response = await http.post('/guest/session/', { device: 'mobile' });
  return unwrapAuthPayload(response?.data || {});
}

/** 查剩余额度（登录用户返回 unlimited） */
export async function fetchGuestQuota() {
  const response = await http.get('/guest/quota/');
  const body = response?.data || {};
  // 后端是 `{status, data:{...}}`；容错成"直接给快照"也不算错
  return body.data || body;
}
