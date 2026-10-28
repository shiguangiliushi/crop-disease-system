/**
 * 智能回答助手接口（第 194 批）
 *
 * 只有一个接口：`POST /api/assistant/ask/`。会话与消息由后端落库，
 * 前端不另外拉取历史 —— 助手抽屉是"一次会话问到完"，刷新即结束。
 *
 * 三个后端约定，前端必须照做（否则会误报错）：
 *
 *  1. **降级也是 200**。`degraded=true` 表示"答得保守"（词条原文 / 未收录 / 命中敏感词），
 *     不是失败。所以这里**不按状态码判成败**，只把结果原样交给页面；
 *     真正失败只有 400（参数错）/ 401（未登录）/ 404（会话不存在）。
 *  2. `degrade_reason` 是给页面决定**怎么展示**用的，不是给用户看的错误码：
 *       empty / too_long / sensitive / rate_limited → 提示语气（引导用户改问题）
 *       no_source                                   → 中性（知识库没有这条）
 *       llm_disabled / llm_error / no_citation      → 说明"AI 暂不可用，下面是档案原文"
 *  3. `citations` 是**数组**（可能为空），元素形如
 *     `{ pest_id, prevention_id, label, snippet }`。
 */
import http, { formatApiError } from './http';
import { t } from '@/i18n';

/** 助手相关接口的统一错误文案 */
export function formatAssistantError(error) {
  // 兜底文案走 i18n（第 83 批起的约定，别写死中文）
  return formatApiError(error, t('assistant.askFailed'));
}

/**
 * 问一个问题
 *
 * @param {object} payload
 * @param {string} payload.question        用户问题（后端上限 500 字，闸门会给出可操作提示）
 * @param {number} [payload.session_id]    续问时带上；不传则新建会话
 * @param {string} [payload.pest_identifier] 识别结果直连的病害标识（如 tomato___late_blight）
 * @returns {Promise<{session_id, message_id, answer, degraded, degrade_reason, citations, usage}>}
 */
export async function askAssistant({ question, session_id, pest_identifier, image } = {}) {
  if (image) {
    // 第 229 批：图片走 multipart（同上：不要手动设 Content-Type）
    const form = new FormData();
    form.append('question', question || '');
    if (session_id) form.append('session_id', String(session_id));
    if (pest_identifier) form.append('pest_identifier', pest_identifier);
    form.append('image', image);
    const multipart = await http.post('/assistant/ask/', form);
    return multipart.data;
  }

  const body = { question };
  if (session_id) body.session_id = session_id;
  if (pest_identifier) body.pest_identifier = pest_identifier;

  const response = await http.post('/assistant/ask/', body);
  return response.data;
}

/** 与 `http.js` 保持一致的 baseURL（流式只能用 fetch，见下面注释） */
const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api').replace(/\/+$/, '');

/** 从 `utils/authStorage` 的约定里取 token（登录态在 sessionStorage） */
function authToken() {
  try {
    return sessionStorage.getItem('auth_token') || localStorage.getItem('auth_token') || '';
  } catch {
    return '';
  }
}

/**
 * 流式问答（SSE）。
 *
 * ## 为什么这一条不用 `http`（axios）而用原生 `fetch`
 *
 * axios 在浏览器端拿不到**增量**响应体：它的 `onDownloadProgress` 只在
 * XHR 的 readyState 变化时回调，拿到的仍是累积文本，而且不知道哪一段是新的。
 * 读 SSE 需要 `response.body.getReader()` —— 那是 Fetch API 才有的。
 *
 * ## 必须自己缓冲（这是 SSE 解析最容易错的地方）
 *
 * 网络分块与事件边界**不对齐**：一次 `read()` 可能只拿到半个事件
 * （`event: del`），也可能一次拿到两个半事件。所以做法是：
 *   1. 把每次读到的文本追加进缓冲；
 *   2. 只按**空行**（`\n\n`）切出**完整**事件，剩下的留在缓冲里等下一块；
 *   3. 流结束时若缓冲里还有内容，按最后一个事件处理。
 * 第一版若不做缓冲，表现是"偶发丢字/解析失败"，而且只在网络慢时复现。
 *
 * @param {object} payload 同 `askAssistant`
 * @param {(text: string) => void} onDelta 每收到一段正文就回调（用于逐字渲染）
 * @returns {Promise<{session_id, message_id, answer, degraded, degrade_reason, citations, usage}>}
 */
export async function askAssistantStream(
  { question, session_id, pest_identifier, image } = {}, { onDelta } = {},
) {
  // 第 229 批：带图片时走 multipart（后端用 `request.FILES['image']` 取），
  // 不带图片仍然是 JSON —— 两条路径的参数名完全一致，只是编码不同。
  let body;
  if (image) {
    body = new FormData();
    body.append('question', question || '');
    if (session_id) body.append('session_id', String(session_id));
    if (pest_identifier) body.append('pest_identifier', pest_identifier);
    body.append('image', image);
  } else {
    body = JSON.stringify({ question, session_id, pest_identifier });
  }

  const response = await fetch(`${BASE_URL}/assistant/ask/stream/`, {
    method: 'POST',
    headers: {
      // ⚠️ multipart 时**不能**手动设 Content-Type：boundary 由浏览器生成，
      //    自己写死就成了 `multipart/form-data`（没有 boundary）→ 后端解析失败。
      ...(image ? {} : { 'Content-Type': 'application/json' }),
      Accept: 'text/event-stream',
      ...(authToken() ? { Authorization: `Token ${authToken()}` } : {}),
    },
    body,
  });

  if (!response.ok) {
    // 只有真正的失败会走到这里：业务降级是 200 + degraded=true（见模块顶部说明）。
    let detail = '';
    try {
      detail = JSON.stringify(await response.json());
    } catch {
      try { detail = await response.text(); } catch { /* 读不出就算了 */ }
    }
    const error = new Error(detail || `HTTP ${response.status}`);
    error.response = { status: response.status };
    throw error;
  }
  if (!response.body) {
    throw new Error('当前环境不支持流式响应（response.body 为空）');
  }

  const result = {
    session_id: null, message_id: null, answer: '',
    degraded: false, degrade_reason: '', citations: [], usage: {},
  };

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const handleEvent = (rawEvent) => {
    let eventName = 'message';
    let dataLine = '';
    for (const line of rawEvent.split('\n')) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLine += line.slice(5).trim();
    }
    if (!dataLine) return;
    let data = null;
    try {
      data = JSON.parse(dataLine);
    } catch {
      return;   // 解析不了就跳过这一段，不让整个回答炸掉
    }

    if (eventName === 'meta') {
      result.session_id = data.session_id ?? result.session_id;
      result.message_id = data.message_id ?? result.message_id;
      result.degraded = Boolean(data.degraded);
      result.degrade_reason = data.degrade_reason || '';
      if (Array.isArray(data.citations)) result.citations = data.citations;
    } else if (eventName === 'delta') {
      const text = data.text || '';
      result.answer += text;
      if (text && onDelta) onDelta(text);
    } else if (eventName === 'citations') {
      if (Array.isArray(data.citations)) result.citations = data.citations;
    } else if (eventName === 'done') {
      result.usage = data.usage || {};
      result.degraded = Boolean(data.degraded);
      result.degrade_reason = data.degrade_reason || '';
      //: 第 212 批：后端会把**最终正文**带回来（单来源时 `【1】` 被折叠成一处）。
      //: 逐字增量只是"过程"，done 里的才是定稿 —— 以它为准，
      //: 这样"流式看到的"与"落库/历史里的"一致，不会刷新前后两副样子。
      if (typeof data.answer === 'string' && data.answer) {
        result.answer = data.answer;
        if (onDelta) onDelta(null, data.answer);
      }
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index = buffer.indexOf('\n\n');
    while (index >= 0) {
      handleEvent(buffer.slice(0, index));
      buffer = buffer.slice(index + 2);
      index = buffer.indexOf('\n\n');
    }
  }
  // 收尾：最后一块可能没有以空行结束
  buffer += decoder.decode();
  if (buffer.trim()) handleEvent(buffer);

  return result;
}

/**
 * 给某条助手回答打分（第 196 批）
 *
 * 语义是"最后一次评价为准"：用户可以改主意（点错了会再点一次），
 * 后端会覆盖 verdict 并更新 `feedback_at`。
 *
 * @param {number} messageId 助手消息 id（`meta` / 同步响应的 `message_id`）
 * @param {'helpful'|'useless'} verdict
 * @param {string} [note] `useless` 时补充"哪里不对" —— 这是最有价值的信号
 */
export async function sendAssistantFeedback(messageId, verdict, note = '') {
  const response = await http.post(`/assistant/messages/${messageId}/feedback/`, {
    verdict,
    note: note || undefined,
  });
  return response.data;
}

/**
 * 把这次会话转人工（第 196 批）—— 写进既有的专家咨询链路
 *
 * **幂等**：同一会话重复调用返回同一张工单（后端返回 `created=false` 时说明已经转过），
 * 所以前端不必自己做"已转过就别再发"的判断，但也不该故意重复发。
 *
 * @param {number} sessionId
 * @param {string} [note] 想让专家知道的补充信息
 */
export async function escalateSession(sessionId, note = '') {
  const response = await http.post(`/assistant/sessions/${sessionId}/escalate/`, {
    note: note || undefined,
  });
  return response.data;
}

/**
 * 我的问答历史（第 198 批，独立问答页用）
 *
 * @param {{page?: number, page_size?: number}} params
 * @returns {Promise<{count, page, page_size, has_more, results: Array}>}
 */
export async function listAssistantSessions(params = {}) {
  const response = await http.get('/assistant/sessions/', { params });
  return response.data;
}

/**
 * 取一次会话的完整问答（含引用与评价）
 *
 * 流式回答在生成前会先落一条**空消息行**再回填，后端已在详情里过滤掉，
 * 所以这里拿到的每一条 `content` 都非空。
 */
export async function getAssistantSession(sessionId) {
  const response = await http.get(`/assistant/sessions/${sessionId}/`);
  return response.data;
}

/** 删除一次会话（消息随会话级联删除，不留孤儿） */
export async function deleteAssistantSession(sessionId) {
  await http.delete(`/assistant/sessions/${sessionId}/`);
}

export default {
  askAssistant,
  askAssistantStream,
  sendAssistantFeedback,
  escalateSession,
  listAssistantSessions,
  getAssistantSession,
  deleteAssistantSession,
  formatAssistantError,
};
