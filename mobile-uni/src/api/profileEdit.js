/** 资料编辑（uni-app，第 265 批）：PATCH /api/users/<id>/ */
import { request } from '../utils/request'

export async function fetchProfile(userId) {
  const body = await request({ url: `/users/${userId}/` })
  return body?.data && !body?.username ? body.data : body
}

export async function updateProfile(userId, payload) {
  const body = await request({ url: `/users/${userId}/`, method: 'PATCH', data: payload })
  return body?.data && !body?.username ? body.data : body
}
