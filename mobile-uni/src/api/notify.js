/** 站内通知（uni-app，第 262 批）—— 与 Vant 端同一套接口 */
import { request } from '../utils/request'

function rowsOf(body) {
  if (Array.isArray(body)) return body
  if (Array.isArray(body?.results)) return body.results
  if (Array.isArray(body?.data?.items)) return body.data.items
  if (Array.isArray(body?.data)) return body.data
  return []
}

export async function fetchNotifications() {
  const body = await request({ url: '/notifications/', data: { page_size: 20 } })
  return { items: rowsOf(body), count: body?.count ?? rowsOf(body).length }
}

export async function fetchUnreadCount() {
  try {
    const body = await request({ url: '/notifications/unread-count/' })
    return Number(body?.unread ?? body?.count ?? body?.data?.unread ?? 0) || 0
  } catch (error) {
    return 0
  }
}

export async function markAllRead() {
  await request({ url: '/notifications/read-all/', method: 'POST' })
}
