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
export async function askAssistant({ question, session_id, pest_identifier } = {}) {
  const body = { question };
  if (session_id) body.session_id = session_id;
  if (pest_identifier) body.pest_identifier = pest_identifier;

  const response = await http.post('/assistant/ask/', body);
  return response.data;
}

export default { askAssistant, formatAssistantError };
