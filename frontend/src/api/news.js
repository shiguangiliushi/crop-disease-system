/**
 * 行业新闻接口
 *
 * - 读取（列表 / 详情）任何人可访问
 * - 新增：仅管理员；修改 / 删除：管理员或该新闻作者
 * - 统一由 @/api/http 处理 Token、CSRF 与错误文案
 */
import http, { formatApiError } from './http';
import { t } from '@/i18n';

/**
 * 后端字段名 → 显示名（第 83 批）
 * ------------------------------------------------------------------
 * 原先是一个写死中文的常量：英文界面下表单校验报错会拼成
 * 「标题：This field is required.」这种半中半英。改成**每次调用时按当前语言**生成
 * （不能用常量：常量在模块加载时就求值，切语言不会变）。
 */
const fieldLabels = () => ({
  title: t('field.title'),
  content: t('field.content'),
  image: t('field.image'),
  category: t('field.category'),
  source: t('field.source'),
  tags: t('field.tags'),
  is_published: t('field.publishState'),
  detail: t('field.permission'),
  non_field_errors: t('field.validationFailed'),
});

/** 新闻相关接口的错误提示 */
export function formatNewsError(error, fallback = '') {
  return formatApiError(error, fallback || t('msg.operationFailedRetry'), fieldLabels());
}

/**
 * 新闻分类（与后端 News.CATEGORY_CHOICES 保持一致）
 * 第 79 批：补 `labelKey` —— 原来只有中文 `label`，后台新闻列表的"分类"标签
 * 在英文界面下一直是中文（政策解读/农业技术/…）。显示时用 `t(labelKey)`，
 * `label` 仅作为 i18n 缺 key 时的兜底。
 */
export const NEWS_CATEGORIES = [
  { value: 'policy', label: '政策解读', labelKey: 'news.catPolicy' },
  { value: 'tech', label: '农业技术', labelKey: 'news.catTech' },
  { value: 'market', label: '市场动态', labelKey: 'news.catMarket' },
  { value: 'report', label: '行业报告', labelKey: 'news.catReport' },
  { value: 'notice', label: '通知公告', labelKey: 'news.catNotice' },
];

/**
 * 分类值 → 当前语言下的分类名
 * @param {string} value 分类值（policy / tech / …）
 * @param {(key: string) => string} [t] i18n 取值函数；不传则回落中文
 */
export function getNewsCategoryLabel(value, t) {
  const found = NEWS_CATEGORIES.find((item) => item.value === value);
  if (!found) return value || '';
  if (typeof t === 'function' && found.labelKey) return t(found.labelKey);
  return found.label;
}

/**
 * 查询新闻列表
 * @param {object} params { page, page_size, search, search_type, category }
 * @returns {Promise<{count:number,total_pages:number,results:Array}>}
 */
export async function fetchNewsList(params = {}) {
  const response = await http.get('/news/', { params });
  const data = response.data;

  // 兼容分页与不分页两种返回
  if (Array.isArray(data)) {
    return { count: data.length, total_pages: 1, results: data };
  }
  return {
    count: data?.count ?? 0,
    total_pages: data?.total_pages ?? Math.ceil((data?.count ?? 0) / (params.page_size || 10)),
    results: data?.results ?? [],
  };
}

/** 查询新闻详情 */
export async function fetchNewsDetail(id) {
  const response = await http.get(`/news/${id}/`);
  return response.data;
}

/** 组装 multipart 表单数据 */
function buildFormData(payload = {}, imageFile = null) {
  const formData = new FormData();

  formData.append('title', payload.title ?? '');
  formData.append('content', payload.content ?? '');
  formData.append('category', payload.category ?? 'notice');
  formData.append('source', payload.source ?? '');
  formData.append('is_published', payload.is_published ? 'true' : 'false');

  const tags = payload.tags;
  formData.append('tags', Array.isArray(tags) ? tags.join(',') : tags ?? '');

  if (payload.clear_image) {
    formData.append('clear_image', 'true');
  }
  if (imageFile) {
    formData.append('image', imageFile);
  }

  return formData;
}

/** 新增新闻（仅管理员） */
export async function createNews(payload, imageFile = null) {
  const response = await http.post('/news/', buildFormData(payload, imageFile), {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

/** 修改新闻 */
export async function updateNews(id, payload, imageFile = null) {
  const response = await http.patch(`/news/${id}/`, buildFormData(payload, imageFile), {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

/** 切换发布状态（只提交该字段，避免覆盖其他内容） */
export async function toggleNewsPublished(id, isPublished) {
  const formData = new FormData();
  formData.append('is_published', isPublished ? 'true' : 'false');

  const response = await http.patch(`/news/${id}/`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

/** 删除新闻 */
export async function deleteNews(id) {
  await http.delete(`/news/${id}/`);
  return true;
}

export default {
  fetchNewsList,
  fetchNewsDetail,
  createNews,
  updateNews,
  toggleNewsPublished,
  deleteNews,
  formatNewsError,
  getNewsCategoryLabel,
  NEWS_CATEGORIES,
};
