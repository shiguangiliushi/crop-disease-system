/** 病害百科（uni-app，第 263 批） */
import { request } from '../utils/request'

export async function findPest(keyword) {
  const term = String(keyword || '').trim()
  if (!term) return null
  const body = await request({ url: '/pests/', data: { search: term, page_size: 5 } })
  const rows = Array.isArray(body) ? body : body?.results || body?.data?.items || body?.data || []
  return rows[0] || null
}

export async function fetchPestDetail(id) {
  const body = await request({ url: `/pests/${id}/` })
  return body?.data && !body?.name ? body.data : body
}
