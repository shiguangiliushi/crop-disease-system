/**
 * 管理操作日志（第 148 批，控制台「操作日志」页用）
 *
 * 对应后端 `api/views_audit.py`：两个接口都**仅全权管理员**可访问
 * （它显示"谁在什么时候对谁做了什么"，内容编辑员不该看到别的管理员的操作记录）。
 */
import http from './http';

/**
 * 日志列表
 *
 * @param {object} params
 *   `page` / `page_size`  分页
 *   `action`              动作，如 `user.suspend`（取值见 fetchAuditActions）
 *   `actor`               操作人 id
 *   `target_type`         目标类型（user / feedback / board / post / word …）
 *   `search`              关键字（匹配操作人、目标、说明）
 *   `start` / `end`       `YYYY-MM-DD`，**两端都含当天**（后端按 date 比较）
 */
export function fetchAuditLogs(params = {}) {
  return http.get('/admin/audit-logs/', { params }).then((res) => res.data);
}

/** 动作清单（与后端模型 choices 单一来源，前端不写死） */
export function fetchAuditActions() {
  return http.get('/admin/audit-logs/actions/').then((res) => res.data);
}

export default { fetchAuditLogs, fetchAuditActions };
