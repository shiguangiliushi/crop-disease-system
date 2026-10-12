/**
 * 控制台的「识别记录」（第 172 批）
 *
 * 对应后端 `api/views_detections_admin.py`：
 *   · 列表 / 统计：需要 **USER_ADMIN** 能力（识别记录里带用户身份与上传的图片，
 *     与「用户管理」同档）；
 *   · 删除（不可逆，连图片文件一起删）：**仅全权管理员** —— 前端不给非全权管理员
 *     画那个按钮，后端也会 403。
 *
 * 路径是 `/admin/detections/`，与农户端的 `/history/` 不是一回事：
 * 那边只回**当前用户自己的**记录。
 */
import http from './http';

/**
 * 识别记录列表 + 统计
 *
 * @param {object} params
 *   `page` / `page_size`        分页
 *   `search`                    用户名 / 识别结果 / 病害名
 *   `user` / `pest`             只看某个用户 / 某个病害词条
 *   `matched`                   `false` → 只看**没匹配到词条**的（最值得人工看的一批）
 *   `confidence_min/max`        置信度区间（0~1）
 *   `date_from` / `date_to`     `YYYY-MM-DD`（含当天）
 *   `ordering`                  `-timestamp`（默认）/ `confidence` / `-confidence` …
 */
export function fetchAdminDetections(params = {}) {
  return http.get('/admin/detections/', { params }).then((res) => res.data);
}

/** 删除一条识别记录（仅全权管理员；行与图片文件一起删，不可恢复） */
export function deleteAdminDetection(id) {
  return http.delete(`/admin/detections/${id}/`).then((res) => res.data);
}

export default { fetchAdminDetections, deleteAdminDetection };
