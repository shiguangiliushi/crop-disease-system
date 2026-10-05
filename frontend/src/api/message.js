/**
 * 私信接口（第 42 批）
 */
import http from './http';

/** 我的会话列表 */
export function fetchConversations() {
  return http.get('messages/').then((res) => res.data);
}

/** 与某人的聊天记录（打开即标记已读） */
export function fetchConversation(userId, params = {}) {
  return http.get(`messages/with/${userId}/`, { params }).then((res) => res.data);
}

/** 给某人发私信 */
export function sendMessage(userId, content) {
  return http.post(`messages/with/${userId}/`, { content }).then((res) => res.data);
}

/** 未读私信总数（顶栏红点用） */
export function fetchMessageUnreadCount() {
  return http.get('messages/unread-count/').then((res) => res.data);
}
