/**
 * 管理端「系统健康」（第 157 批）
 *
 * 后端把 `manage.py check_env` 的检查结果整理成 JSON 下发 ——
 * **命令行与界面用的是同一套检查**，不会出现两边说法不一致。
 * 仅全权管理员可访问（会暴露部署细节）。
 */
import http from './http';

/** 系统健康：`{ ok, level, problems, warnings, sections, counts, media, runtime }` */
export function fetchSystemHealth() {
  return http.get('/admin/health/').then((res) => res.data);
}

export default { fetchSystemHealth, fetchConsistency, fetchTaskStatus };
/**
 * 数据一致性对账（第 448 批）
 *
 * 同一指标在不同位置的口径不同（用户数：列表含游客 / 健康页排除游客），
 * 这个接口把它们**并排列出来**，不一致时给出解释（`note`）。
 * 返回 `{ ok, generated_at, checks: [{ key, label, consistent, note, values }] }`
 */
export function fetchConsistency() {
  return http.get('/admin/consistency/').then((res) => res.data);
}

/**
 * 定时任务状态（第 448 批）
 *
 * crontab 在宿主机上、容器读不到，所以这里只报**能从数据验证的**：
 * 健康快照最近日期与缺失天、备份目录最近一份，外加期望调度清单。
 */
export function fetchTaskStatus() {
  return http.get('/admin/task-status/').then((res) => res.data);
}
