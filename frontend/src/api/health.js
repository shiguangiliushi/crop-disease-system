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

export default { fetchSystemHealth };
