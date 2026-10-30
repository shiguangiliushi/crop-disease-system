/**
 * 智能问答（移动端 Vant，第 253 批）
 *
 * 与桌面端 / uni-app 共用同一个非流式接口：`POST /api/assistant/ask/`
 *   { question, pest_identifier } → { answer, citations, degraded, degrade_reason }
 *
 * 为什么不用 SSE：识别后追问通常就一两句，非流式足够；逐字效果属于体验加分项，
 * 需要时桌面端那条流式链路已经验证过（移动端浏览器也支持 fetch stream）。
 */
import http from './http';

export async function askAssistant({ question, pestIdentifier = '' }) {
  const response = await http.post('/assistant/ask/', {
    question,
    pest_identifier: pestIdentifier || '',
  });
  const body = response.data || {};
  return {
    answer: body.answer || '',
    citations: Array.isArray(body.citations) ? body.citations : [],
    degraded: Boolean(body.degraded),
    degradeReason: body.degrade_reason || '',
  };
}

export default { askAssistant };
