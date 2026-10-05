/**
 * 私信接口（第 42 批建立，第 114 批补分页 / 删除 / 图片）
 */
import http from './http';

/** 我的会话列表（对方、最后一条、未读数） */
export function fetchConversations() {
  return http.get('messages/').then((res) => res.data);
}

/**
 * 与某人的聊天记录（打开即标记已读）。
 *
 * @param {number|string} userId
 * @param {{ page_size?: number, before_id?: number }} params
 *   `before_id`：**往上翻历史**的游标（传上一次响应里的 `oldest_id`）。
 *   不传就是最新一页 —— 这也是唯一会"标记已读"的情况，翻历史不会。
 */
export function fetchConversation(userId, params = {}) {
  return http.get(`messages/with/${userId}/`, { params }).then((res) => res.data);
}

/** 给某人发私信 */
export function sendMessage(userId, content) {
  return http.post(`messages/with/${userId}/`, { content }).then((res) => res.data);
}

/** 删除与某人的整个会话（只删我这一侧，对方不受影响） */
export function deleteConversation(userId) {
  return http.delete(`messages/with/${userId}/`).then((res) => res.data);
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

// ============================================================================
// 图片消息（第 114 批）
// ============================================================================
// 协议：图片消息的 `content` 是一段 JSON —— `{"type":"image","url":"…"}`。
//
// ⚠️ 为什么不新增一个消息类型字段：`DirectMessage` 表已经有了
// `content` 且是 TextField，加字段要迁移、要让老消息仍可读；
// 而 JSON-in-text 对"老客户端"是**优雅降级**的 —— 老前端会把那段 JSON
// 当普通文字显示（难看但不出错），而不是整条消息报错。
// 后端的 `_preview_of()` 已经会把这种消息在会话列表里显示成 `[图片]`。
//
// 图片上传复用**已有的** `/api/upload/image/`（有大小/格式/文件名校验），
// 不另开接口 —— 私信图片与帖子插图的安全要求完全一样。

/** 把一条图片消息的正文编码成后端能识别、老客户端也不至于崩的 JSON */
export function encodeImageMessage(url) {
  return JSON.stringify({ type: 'image', url });
}

/**
 * 解析一条私信正文。
 * @returns {{kind: 'text', text: string} | {kind: 'image', url: string}}
 *
 * 解析失败/不是 JSON/结构不对 → 一律当普通文字。
 * **绝不能因为一条消息解析不了就让整个聊天窗口报错** ——
 * 历史上脏数据、老客户端的自由文本都会走到这里。
 */
export function parseMessageContent(content) {
  const raw = typeof content === 'string' ? content : '';
  if (!raw.trimStart().startsWith('{')) {
    return { kind: 'text', text: raw };
  }
  try {
    const payload = JSON.parse(raw);
    if (payload && payload.type === 'image' && typeof payload.url === 'string') {
      return { kind: 'image', url: payload.url };
    }
  } catch {
    // 落到下面当普通文字
  }
  return { kind: 'text', text: raw };
}
