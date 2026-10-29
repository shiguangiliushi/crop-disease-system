/**
 * 反馈（识别纠错）接口（第 237 批）
 *
 * 与 H5 一致：`POST /api/feedback/`，category=recognition，带上 detection_id 与
 * corrected_pest_id 才有训练价值（第 91 批之后后端真的会接收这两个字段）。
 *
 * 为什么用 form-urlencoded 而不是 multipart：小程序端没有 `FormData`，
 * 而这条反馈的图不是必须的（识别图已经在 detection_history 里了）。
 */
import { request } from '../utils/request'

export async function submitRecognitionFeedback({
  diseaseName,
  isCorrect,
  confidence,
  historyId,
  correctedPestId,
} = {}) {
  const fields = {
    category: 'recognition',
    disease_name: diseaseName || '',
    is_correct: String(Boolean(isCorrect)),
    suggestion: isCorrect ? '识别正确' : '识别错误',
  }
  if (confidence !== undefined && confidence !== null) fields.confidence = String(confidence)
  if (historyId) fields.detection_id = String(historyId)
  if (correctedPestId) fields.corrected_pest_id = String(correctedPestId)

  return request({
    url: '/feedback/',
    method: 'POST',
    data: fields,
    header: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
}
