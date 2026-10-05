/**
 * 病害预警接口（第 46 批）
 */
import http from './http';

/** 当前预警（登录后带个性化标注） */
export function fetchAlerts(params = {}) {
  return http.get('alerts/', { params }).then((res) => res.data);
}

/** 把预警推送给全部用户（仅管理员） */
export function pushAlerts() {
  return http.post('alerts/notify/').then((res) => res.data);
}
