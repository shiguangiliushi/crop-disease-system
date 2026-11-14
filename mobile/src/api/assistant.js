/**
 * 智能问答（移动端 Vant，第 253 批）
 *
 * 与桌面端 / uni-app 共用同一个非流式接口：`POST /api/assistant/ask/`
 *   { question, pest_identifier, allow_llm } → { answer, citations, degraded, degrade_reason }
 *
 * 第 376 批：`allow_llm` 是隐私开关（默认 true）。传 false 时后端走 `user_opt_out`
 * 降级，只返回词条原文，不产生任何外部模型请求。
 *
 * 为什么不用 SSE：识别后追问通常就一两句，非流式足够；逐字效果属于体验加分项，
 * 需要时桌面端那条流式链路已经验证过（移动端浏览器也支持 fetch stream）。
 */
import http from './http';

export async function askAssistant({ question, pestIdentifier = '', allowLlm = true }) {
  const response = await http.post('/assistant/ask/', {
    question,
    pest_identifier: pestIdentifier || '',
    // 第 376 批：隐私开关（false 时后端只返回词条原文，不调外部模型）
    allow_llm: allowLlm !== false,
  });
  const body = response.data || {};
  return {
    answer: body.answer || '',
    citations: Array.isArray(body.citations) ? body.citations : [],
    degraded: Boolean(body.degraded),
    degradeReason: body.degrade_reason || '',
    related: body.related || [],  // 第 377 批：同作物其他病害（原写成未定义的 data，必崩）
  };
}

export default { askAssistant };
