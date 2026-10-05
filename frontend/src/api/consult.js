/**
 * 专家咨询接口（第 49 批）
 */
import http from './http';

/** 提问列表（status: open|answered|closed，mine: true，crop，search） */
export function fetchQuestions(params = {}) {
  return http.get('consult/questions/', { params }).then((res) => res.data);
}

/** 提问详情（含回答） */
export function fetchQuestion(id) {
  return http.get(`consult/questions/${id}/`).then((res) => res.data);
}

/** 发起提问 */
export function createQuestion(payload) {
  return http.post('consult/questions/', payload).then((res) => res.data);
}

/** 关闭问题（提问者或管理员） */
export function closeQuestion(id) {
  return http.post(`consult/questions/${id}/`).then((res) => res.data);
}

/** 作答（仅专家/管理员） */
export function createAnswer(questionId, content) {
  return http.post(`consult/questions/${questionId}/answers/`, { content }).then((res) => res.data);
}

/** 采纳回答（仅提问者） */
export function acceptAnswer(answerId) {
  return http.post(`consult/answers/${answerId}/accept/`).then((res) => res.data);
}

/** 专家列表 */
export function fetchExperts() {
  return http.get('consult/experts/').then((res) => res.data);
}

/** 授予专家（仅管理员） */
export function grantExpert(userId, payload = {}) {
  return http.post(`consult/experts/${userId}/`, payload).then((res) => res.data);
}

/** 取消专家（仅管理员） */
export function revokeExpert(userId) {
  return http.delete(`consult/experts/${userId}/`).then((res) => res.data);
}

/** 搜索用户（仅管理员，用于授予专家） */
export function searchUsers(keyword) {
  return http.get('users/', { params: { search: keyword, page_size: 20 } }).then((res) => res.data);
}
