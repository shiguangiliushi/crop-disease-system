/**
 * 识别接口（移动端）
 *
 * POST /api/detect/
 *   form-data: image=<file>   ← 字段名必须是 image（后端 `if 'image' not in request.FILES`）
 *   返回: {status:'success', data:{detection:{...}, history_id}}
 */
import http from './http';
import { normalizeDetectResponse } from '@/utils/detectionResult';

/**
 * 上传图片并识别
 * @param {File} file
 * @param {(event: ProgressEvent) => void} [onUploadProgress]
 * @returns {Promise<object>} 统一视图模型（见 utils/detectionResult.js）
 */
export async function detectDisease(file, onUploadProgress) {
  const formData = new FormData();
  formData.append('image', file);

  const response = await http.post('/detect/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
  });

  return normalizeDetectResponse(response.data);
}

/**
 * 识别结果纠错反馈（POST /api/feedback/，multipart）
 * category=recognition 与桌面端一致，后台能区分"识别纠错"与"功能建议"。
 *
 * 第 91 批：补 `correctedPestId`。
 * 后端从这一版起会真正接收 `detection_id` 与 `corrected_pest_id`
 * （在这之前前端一直在传 `detection_id`，但后端没有这个字段 —— 参数被静默丢弃，
 * 于是反馈既关联不上识别记录，也没有"正确答案"，永远变不成训练样本）。
 */
export async function submitRecognitionFeedback({
  diseaseName, isCorrect, confidence, historyId, imageFile, correctedPestId,
}) {
  const formData = new FormData();
  formData.append('category', 'recognition');
  formData.append('disease_name', diseaseName || '');
  formData.append('is_correct', String(Boolean(isCorrect)));
  formData.append('suggestion', isCorrect ? '识别正确' : '识别错误');
  if (confidence !== undefined && confidence !== null) {
    formData.append('confidence', String(confidence));
  }
  if (historyId) {
    formData.append('detection_id', String(historyId));
  }
  if (correctedPestId) {
    formData.append('corrected_pest_id', String(correctedPestId));
  }
  if (imageFile) {
    formData.append('image', imageFile);
  }

  const response = await http.post('/feedback/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

export default { detectDisease, submitRecognitionFeedback };
