/**
 * 识别记录接口（uni-app 版，第 236 批）
 *
 * 与现有 H5（`mobile/src/api/history.js`）**同一套后端契约**：
 *   GET    /api/detection-history/?page=&page_size=   → {data:{items,total,page,total_pages,has_next}}
 *   GET    /api/detection-history/{id}/               → 单条详情
 *   DELETE /api/detection-history/{id}/               → 删除
 *
 * 注意：这里不是 DRF 默认的 `{count, results}`，别照抄别的项目。
 */
import { request, mediaUrl } from '../utils/request'

/** 后端字段 → 页面用的视图模型（只保留列表需要的字段） */
function normalize(raw = {}) {
  const info = raw.pest_info || {}
  return {
    id: raw.id ?? null,
    disease: raw.disease_name || raw.detection_result || '未识别',
    diseaseEn: info.name_en || '',
    confidence: Number(raw.confidence ?? 0),
    image: mediaUrl(raw.annotated_image_url || raw.image || ''),
    time: raw.timestamp_formatted || raw.timestamp || '',
    healthy: /healthy/i.test(String(raw.detection_result || info.name_en || '')),
  }
}

/** 分页拉取识别记录 */
export async function fetchHistory({ page = 1, pageSize = 10 } = {}) {
  const body = await request({
    url: '/detection-history/',
    data: { page, page_size: pageSize },
  })
  const inner = body.data || body || {}
  const rawItems = Array.isArray(inner) ? inner : inner.items || inner.results || []
  const total = inner.total ?? rawItems.length
  const totalPages = inner.total_pages ?? Math.max(1, Math.ceil(total / pageSize))
  return {
    items: rawItems.map(normalize),
    total,
    page: inner.page ?? page,
    totalPages,
    hasNext: inner.has_next ?? page < totalPages,
  }
}

/** 单条详情（从历史点进结果页时用） */
export async function fetchHistoryDetail(id) {
  const body = await request({ url: `/detection-history/${id}/` })
  return body.data || body
}

/** 删除一条记录 */
export async function deleteHistory(id) {
  await request({ url: `/detection-history/${id}/`, method: 'DELETE' })
  return true
}
