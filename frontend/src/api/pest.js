/**
 * 病害百科数据接口（含管理员的新增 / 修改 / 删除）
 *
 * 说明：
 * - 读取接口对所有人开放；写入接口仅管理员可用（后端会校验 is_staff / is_superuser / role=ADMIN）
 * - Token、CSRF 头与错误格式化统一由 @/api/http 处理
 */
import http, { formatApiError, toAbsoluteMediaUrl } from './http';
import { t } from '@/i18n';

/** 后端字段名 → 显示名（第 83 批：按当前语言生成，见 api/news.js 的说明） */
const fieldLabels = () => ({
  name: t('field.pestName'),
  crop_type: t('field.cropType'),
  symptoms: t('field.symptoms'),
  english_identifier: t('field.englishIdentifier'),
  description: t('field.description'),
  image: t('field.pestImage'),
  prevention_methods: t('field.preventionMethods'),
  detail: t('field.permission'),
  non_field_errors: t('field.validationFailed'),
});

/** 病害相关接口的错误提示 */
export function formatPestError(error, fallback = '') {
  return formatApiError(error, fallback || t('msg.operationFailedRetry'), fieldLabels());
}

/** 组装 multipart 表单数据 */
function buildFormData(payload = {}, imageFile = null) {
  const formData = new FormData();

  ['name', 'crop_type', 'symptoms', 'english_identifier', 'description'].forEach((key) => {
    if (payload[key] !== undefined && payload[key] !== null) {
      formData.append(key, payload[key]);
    }
  });

  formData.append('prevention_methods', JSON.stringify(payload.prevention_methods || []));

  if (payload.clear_image) {
    formData.append('clear_image', 'true');
  }
  if (imageFile) {
    formData.append('image', imageFile);
  }

  return formData;
}

/** 获取病害详情（编辑用，含防治方法） */
export async function fetchPestDetail(id) {
  const response = await http.get(`/pests/${id}/`);
  return response.data;
}

/**
 * 病害列表（第 122 批：管理端页面用 —— 支持搜索 / 作物筛选 / 分页，都是**服务端**的）
 *
 * 与农户端百科页的区别：那一页是把整库拉下来在内存里筛（因为要按页签切作物、
 * 还要离线缓存）；管理端要的是"精确找到某一条"，所以走后端已有的
 * `?search=`（名称/症状/描述）与 `?crop_type=`（icontains）加标准分页。
 *
 * @param {{search?: string, crop_type?: string, page?: number, page_size?: number}} params
 * @returns {Promise<{count:number, next:string|null, previous:string|null, results:object[]}>}
 */
export async function fetchPestList(params = {}) {
  const response = await http.get('/pests/', { params });
  return response.data;
}

/**
 * ⚠️ 第 122 批记一笔：**要"作物"清单时不要用 `/pest-types/`**。
 *
 * 那个接口的名字很误导 —— 它返回的是**病害名称**（`PestInfo.name`，38 条，
 * 还包含"健康大豆"这类占位条目），返回体形如：
 *     {"status":"success","count":38,"results":["南瓜白粉病", ...]}
 * 而"可选作物"的正确来源是 `/api/calendar/crops/`（取自百科里真实存在的作物，
 * 见 `@/api/calendar` 的 `fetchCalendarCrops()`）。
 *
 * 这个坑真实存在过：农户端百科页把 `pest-types/` 的结果当作物用来生成筛选按钮，
 * 于是**登录用户**会看到"健康大豆/南瓜白粉病"之类的按钮（匿名访问该接口是 401，
 * 走的是预设列表兜底，反而看不出问题）。第 122 批一并修掉。
 */

/** 新增病害 */
export async function createPest(payload, imageFile = null) {
  const response = await http.post('/pests/', buildFormData(payload, imageFile), {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

/** 修改病害（整体覆盖防治方法） */
export async function updatePest(id, payload, imageFile = null) {
  const response = await http.patch(`/pests/${id}/`, buildFormData(payload, imageFile), {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

/** 删除病害 */
export async function deletePest(id) {
  await http.delete(`/pests/${id}/`);
  return true;
}

export { toAbsoluteMediaUrl };

export default {
  fetchPestDetail,
  fetchPestList,
  createPest,
  updatePest,
  deletePest,
  formatPestError,
  toAbsoluteMediaUrl,
};
