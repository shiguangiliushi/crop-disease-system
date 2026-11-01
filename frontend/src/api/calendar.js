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


// ============================================================================
// 我的农事提醒（第 316 批）
//
// ⚠️ 与 `CalendarTask` 不是一回事：全局农事表由管理员维护、所有人共享；
// 这里的都是**当前用户自己的**提醒（从助手回答加入）。
// ============================================================================

export async function listTaskReminders() {
  const response = await http.get('/calendar/reminders/');
  return Array.isArray(response.data?.items) ? response.data.items : [];
}

export async function setTaskReminderDone(id, isDone = true) {
  const response = await http.patch(`/calendar/reminders/${id}/`, { is_done: isDone });
  return response.data;
}

export async function deleteTaskReminder(id) {
  await http.delete(`/calendar/reminders/${id}/`);
}
