/**
 * 种植日历接口（第 47 批）
 */
import http from './http';

/** 某月的农事任务 + 该月站内真实病害统计 */
export function fetchCalendar(params = {}) {
  return http.get('calendar/', { params }).then((res) => res.data);
}

/** 可选作物（来自病害百科里真实存在的作物） */
export function fetchCalendarCrops() {
  return http.get('calendar/crops/').then((res) => res.data);
}

/** 新增任务（仅管理员） */
export function createCalendarTask(payload) {
  return http.post('calendar/tasks/', payload).then((res) => res.data);
}

/** 修改任务（仅管理员） */
export function updateCalendarTask(id, payload) {
  return http.patch(`calendar/tasks/${id}/`, payload).then((res) => res.data);
}

/** 删除任务（仅管理员） */
export function deleteCalendarTask(id) {
  return http.delete(`calendar/tasks/${id}/`).then((res) => res.data);
}
