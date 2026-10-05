/**
 * 等级与积分接口（第 42 批）
 */
import http from './http';

/** 我的积分与等级（含下一级进度） */
export function fetchMyPoints() {
  return http.get('users/me/points/').then((res) => res.data);
}

/** 我的积分流水 */
export function fetchMyPointLogs(params = {}) {
  return http.get('users/me/point-logs/', { params }).then((res) => res.data);
}

/** 等级体系与加分规则（公开） */
export function fetchPointLevels() {
  return http.get('points/levels/').then((res) => res.data);
}
