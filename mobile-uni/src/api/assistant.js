/**
 * 智能问答接口（uni-app 版，第 244 批）
 *
 * 复用后端的非流式接口 `POST /api/assistant/ask/`：
 * `{ question, pest_identifier }` → `{ answer, citations, degraded, degrade_reason, session_id }`。
 *
 * 为什么不用 SSE 流式：小程序/App 的 `uni.request` 不支持增量读取（要 `enableChunked` + 手动
 * 拼 ArrayBuffer，三端差异大）。识别后追问通常是一两句话，非流式够用；
 * 真需要逐字效果时再按平台做。
 */
import { request } from '../utils/request'

export async function askAssistant({ question, pestIdentifier = '' }) {
  const body = await request({
    url: '/assistant/ask/',
    method: 'POST',
    data: { question, pest_identifier: pestIdentifier || '' },
  })
  return {
    answer: body.answer || '',
    citations: Array.isArray(body.citations) ? body.citations : [],
    degraded: Boolean(body.degraded),
    degradeReason: body.degrade_reason || '',
    sessionId: body.session_id || '',
  }
}
