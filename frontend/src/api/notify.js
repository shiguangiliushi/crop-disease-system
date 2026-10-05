/**
 * 通知与公告接口（第 37 批）
 */
import http from './http';

/** 我的通知列表（分页） */
export function fetchNotifications(params = {}) {
  return http.get('notifications/', { params }).then((res) => res.data);
}

/** 未读数（铃铛红点用） */
export function fetchUnreadCount() {
  return http.get('notifications/unread-count/').then((res) => res.data);
}

/** 标记单条已读 */
export function markNotificationRead(id) {
  return http.post(`notifications/${id}/read/`).then((res) => res.data);
}

/** 全部标记已读 */
export function markAllNotificationsRead() {
  return http.post('notifications/read-all/').then((res) => res.data);
}

/** 删除某条通知 */
export function deleteNotification(id) {
  return http.delete(`notifications/${id}/`).then((res) => res.data);
}

/** 生效中的公告列表 */
export function fetchAnnouncements(params = {}) {
  return http.get('announcements/', { params }).then((res) => res.data);
}

/** 首页横幅用的置顶公告（没有则 announcement 为 null） */
export function fetchLatestAnnouncement() {
  return http.get('announcements/latest/').then((res) => res.data);
}

/** 发布公告（仅管理员） */
export function createAnnouncement(data) {
  return http.post('announcements/', data).then((res) => res.data);
}

/** 修改公告（仅管理员） */
export function updateAnnouncement(id, data) {
  return http.patch(`announcements/${id}/`, data).then((res) => res.data);
}

/** 删除公告（仅管理员） */
export function deleteAnnouncement(id) {
  return http.delete(`announcements/${id}/`).then((res) => res.data);
}
