/** 资料编辑（第 264 批）：后端没有 /users/me/，用 PATCH /users/<id>/ */
import http from './http';

export async function fetchProfile(userId) {
  const response = await http.get(`/users/${userId}/`);
  return response.data || {};
}

export async function updateProfile(userId, payload) {
  const response = await http.patch(`/users/${userId}/`, payload);
  return response.data || {};
}
