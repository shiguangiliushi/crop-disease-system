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
  createPest,
  updatePest,
  deletePest,
  formatPestError,
  toAbsoluteMediaUrl,
};
