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

/**
 * 按用户名搜人（第 112 批）—— "发起新私信"用
 *
 * ⚠️ 关键词**至少 2 个字**，否则后端回空列表 + 一句 `detail` 提示
 * （不是报错）。前端把 `detail` 显示在输入框下方即可。
 *
 * 为什么不用 `/api/users/`：那个是**仅管理员**；
 * `/api/users/follow-suggestions/` 只回固定 Top 5、不接受关键词。
 */
export function searchUsers(keyword) {
  return http.get('users/search/', { params: { q: keyword } }).then((res) => res.data);
}
