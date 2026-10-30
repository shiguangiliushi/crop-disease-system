/**
 * 识别结果的数据整形
 * ----------------------------------------------------------------------------
 * 后端有**两处**会给出"一次识别结果"，字段名还不一样：
 *   1. POST /api/detect/         → {detection:{disease, confidence, symptoms...}, history_id}
 *   2. GET  /api/detection-history/ → 列表项 {disease_name, confidence, pest_info:{...}}
 * 结果页要能同时服务"刚识别完"和"从记录里点进来"，所以在这里统一成同一个视图模型，
 * 页面只认一种形状（否则每个字段都要写两套兜底）。
 *
 * ⚠️ 图片地址必须改写：后端用 `request.build_absolute_uri()` 生成图片 URL，
 * 而请求是经 vite 代理转发到 127.0.0.1:8000 的，于是返回的是
 * `http://127.0.0.1:8000/media/...` —— 在手机上这个地址指向**手机自己**，必然加载失败。
 * 这里把本机地址剥成相对路径，让它跟着当前页面的 origin/代理走（见 toAbsoluteMediaUrl）。
 */
import { toAbsoluteMediaUrl } from '@/api/http';

/** 从病害百科对象里拼出防治建议文本 */
function joinPrevention(pestInfo, preferEnglish = false) {
  const methods = pestInfo?.prevention_methods || [];
  return methods
    .map((m) => (preferEnglish ? m.measure_en || m.measure : m.measure))
    .filter(Boolean)
    .join('\n');
}

export function isHealthyIdentifier(identifier) {
  return /healthy/i.test(identifier || '');
}

/** POST /detect/ 的响应 → 统一视图模型 */
export function normalizeDetectResponse(responseData) {
  let data = responseData || {};
  if (data.status === 'success' && data.data) data = data.data;

  const detection = data.detection;
  if (!detection) {
    throw new Error('missing_detection');
  }

  return {
    source: 'detect',
    // 第 253 批：保留模型类名 —— 识别后的「追问助手」把它当 pest_identifier 传，
    // 否则"这个病用什么药？"这种指代问题检索不到词条，会降级成"未收录"。
    identifier: detection.identifier || detection.pest_identifier || '',
    historyId: data.history_id ?? detection.history_id ?? null,
    timestamp: detection.timestamp || data.timestamp || new Date().toISOString(),
    healthy:
      detection.status === 'healthy' ||
      isHealthyIdentifier(detection.identifier) ||
      isHealthyIdentifier(detection.disease_en),
    originalImage: toAbsoluteMediaUrl(detection.original_image || detection.image_url || ''),
    annotatedImage: toAbsoluteMediaUrl(
      detection.annotated_image || detection.annotated_image_url || detection.original_image || '',
    ),
    disease: {
      name: detection.disease || '',
      nameEn: detection.disease_en || '',
      confidence: detection.confidence ?? 0,
      symptoms: detection.symptoms || detection.description || '',
      symptomsEn: detection.symptoms_en || detection.description_en || '',
      prevention: detection.prevention || detection.suggestions || '',
      preventionEn: detection.prevention_en || '',
    },
  };
}

/** 识别记录列表项 → 同一视图模型（source='history'） */
export function normalizeHistoryItem(raw = {}) {
  const info = raw.pest_info || {};
  return {
    source: 'history',
    // 第 253 批：同上（详情接口的 pest_info.english_identifier 是第 244 批加的）
    identifier: raw.english_identifier || info.english_identifier || raw.identifier || '',
    historyId: raw.id ?? null,
    timestamp: raw.timestamp || raw.timestamp_formatted || '',
    timeText: raw.timestamp_formatted || '',
    healthy: isHealthyIdentifier(raw.detection_result) || isHealthyIdentifier(info.name_en),
    originalImage: toAbsoluteMediaUrl(raw.image || ''),
    annotatedImage: toAbsoluteMediaUrl(raw.annotated_image_url || raw.image || ''),
    disease: {
      name: raw.disease_name || raw.detection_result || '',
      nameEn: info.name_en || '',
      confidence: raw.confidence ?? 0,
      symptoms: info.symptoms || raw.symptoms || '',
      symptomsEn: info.symptoms_en || '',
      prevention: joinPrevention(info),
      preventionEn: joinPrevention(info, true),
    },
  };
}

export default { normalizeDetectResponse, normalizeHistoryItem, isHealthyIdentifier };
