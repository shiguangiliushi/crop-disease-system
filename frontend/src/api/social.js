/**
 * 关注 / 粉丝接口（第 40 批）
 */
import http from './http';

/** 关注 / 取消关注（toggle），返回最新状态与粉丝数 */
export function toggleFollow(userId) {
  return http.post(`users/${userId}/follow/`).then((res) => res.data);
}

/** 某人的粉丝列表 */
export function fetchFollowers(userId, params = {}) {
  return http.get(`users/${userId}/followers/`, { params }).then((res) => res.data);
}

/** 某人关注的人 */
export function fetchFollowing(userId, params = {}) {
  return http.get(`users/${userId}/following/`, { params }).then((res) => res.data);
}

/** 我关注的人（登录态） */
export function fetchMyFollowing(params = {}) {
  return http.get('users/me/following/', { params }).then((res) => res.data);
}

/** 我自己的关注数 / 粉丝数 */
export function fetchMyFollowStats() {
  return http.get('users/me/follow-stats/').then((res) => res.data);
}

/** 推荐关注（最近活跃且我还没关注的人） */
export function fetchFollowSuggestions() {
  return http.get('users/follow-suggestions/').then((res) => res.data);
}
