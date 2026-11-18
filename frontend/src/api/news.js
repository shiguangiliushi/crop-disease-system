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
  // 第 399 批：新增字段也要有显示名，否则后端返回字段级校验错误时
  // 英文界面会露出 `summary: ...` 这种原始字段名。
  summary: t('field.summary'),
  is_featured: t('field.featured'),
  published_at: t('field.publishedAt'),
  // 第 401 批：原文链接 / 关联病害（multipart 表单里相关键名同上）
  external_url: t('field.externalUrl'),
  related_pests: t('field.relatedPests'),
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
 * @param {object} params { page, page_size, search, search_type, category,
 *                          ordering, date_range, tags, featured }
 * @returns {Promise<{count:number,total_pages:number,results:Array,featured:Array}>}
 */
export async function fetchNewsList(params = {}) {
  const response = await http.get('/news/', { params });
  const data = response.data;

  // 第 399 批：读者列表页会传 featured=1，此时后端把 1~3 条头条从 results/count
  // 里剔除、单独放在 featured 段。老后端（或管理端不传 featured 的请求）没有该字段，
  // 这里统一归一化成 []，调用方不需要区分后端版本。
  const featured = Array.isArray(data?.featured) ? data.featured : [];

  // 兼容分页与不分页两种返回
  if (Array.isArray(data)) {
    return { count: data.length, total_pages: 1, results: data, featured };
  }
  return {
    count: data?.count ?? 0,
    total_pages: data?.total_pages ?? Math.ceil((data?.count ?? 0) / (params.page_size || 10)),
    results: data?.results ?? [],
    featured,
  };
}

/**
 * 查询热门标签聚合（第 399 批 · P0-2）
 * ------------------------------------------------------------------
 * 后端 `GET /news/tags/` 返回 `{ tags: [{ name, count }], count }`（匿名可访问）。
 * 老后端还没有这个接口（404），调用方 catch 后按空标签处理即可，页面不会崩。
 *
 * @param {object} params { category, limit } 均为可选
 * @returns {Promise<{tags: Array<{name:string,count:number}>, count:number}>}
 */
export async function fetchNewsTags(params = {}) {
  const response = await http.get('/news/tags/', { params });
  const data = response.data;
  const tags = Array.isArray(data?.tags) ? data.tags : [];
  return {
    tags,
    count: typeof data?.count === 'number' ? data.count : tags.length,
  };
}

/** 查询新闻详情 */
export async function fetchNewsDetail(id) {
  const response = await http.get(`/news/${id}/`);
  return response.data;
}

/**
 * 查询某条新闻的"相关推荐"（第 401 批 · P1）
 * ------------------------------------------------------------------
 * 后端 `GET /api/news/{id}/related/` 返回 `{ results: [NewsSerializer...], count: N }`，
 * 默认 4 条、可通过 `limit` 调整。
 *
 * 与列表接口不同，这里的返回体**不是分页结构**（没有 next/previous），
 * 老后端（接口还没上线时）会 404 —— 调用方 catch 后按"无推荐"处理即可，页面不崩。
 *
 * @param {number|string} id 当前新闻 id
 * @param {object} [params] { limit }
 * @returns {Promise<{results: Array, count: number}>}
 */
export async function fetchNewsRelated(id, params = {}) {
  const response = await http.get(`/news/${id}/related/`, { params });
  const data = response.data;

  // 兼容两种返回：约定的 {results,count}，以及万一后端直接给数组
  if (Array.isArray(data)) {
    return { results: data, count: data.length };
  }
  const results = Array.isArray(data?.results) ? data.results : [];
  return {
    results,
    count: typeof data?.count === 'number' ? data.count : results.length,
  };
}

/**
 * 新闻数据看板（第 403 批 · P2-12）
 * ------------------------------------------------------------------
 * 后端 `GET /api/admin/news-stats/?days=30`（7 / 30 / 90 天）一次返回：
 *   { totals, publish_trend, category_distribution, top_viewed, tag_cloud, generated_at }
 * 权限是 CONTENT 能力（管理员 / 信息编辑员可看，普通用户 403）。
 *
 * 这里做**向后兼容归一化**：数组字段缺失给 []、totals 缺失给 {}、
 * days 缺失回落到入参/30。看板是新增的辅助区块，后端某次响应少个字段时
 * 页面应按空态渲染，而不是在视图里对 undefined 调 .map() 崩掉。
 *
 * @param {object} [params] { days: 7|30|90 }
 * @returns {Promise<object>} 归一化后的看板数据
 */
export async function fetchNewsStats(params = {}) {
  const response = await http.get('/admin/news-stats/', { params });
  const data = response.data;
  const toArray = (value) => (Array.isArray(value) ? value : []);
  const payload = data && typeof data === 'object' && !Array.isArray(data) ? data : {};

  return {
    // 保留后端原字段（如 generated_at），只补/修归一化字段
    ...payload,
    days: typeof payload.days === 'number' ? payload.days : (params.days ?? 30),
    totals: payload.totals && typeof payload.totals === 'object' ? payload.totals : {},
    publish_trend: toArray(payload.publish_trend),
    category_distribution: toArray(payload.category_distribution),
    top_viewed: toArray(payload.top_viewed),
    tag_cloud: toArray(payload.tag_cloud),
  };
}

/**
 * 组装 multipart 表单数据（第 399 批：由私有 buildFormData 改为导出 buildNewsFormData，
 * 便于单测直接断言"哪些键被 append"；创建/修改两个接口共用）
 *
 * 可选字段（summary / is_featured / published_at）**只在 payload 里存在该键时才追加**：
 * 两个页面（行业动态弹窗、新闻管理页）各有自己关心的字段，若一律追加空值，
 * 就会在 A 页面保存时把 B 页面维护的字段清空。
 *
 * @param {object} payload 表单字段
 * @param {File|null} imageFile 新封面图（null 表示不改封面）
 */
export function buildNewsFormData(payload = {}, imageFile = null) {
  const formData = new FormData();

  formData.append('title', payload.title ?? '');
  formData.append('content', payload.content ?? '');
  formData.append('category', payload.category ?? 'notice');
  formData.append('source', payload.source ?? '');
  formData.append('is_published', payload.is_published ? 'true' : 'false');

  const tags = payload.tags;
  formData.append('tags', Array.isArray(tags) ? tags.join(',') : tags ?? '');

  // 第 399 批：摘要（可空字符串 = 清空摘要）
  if (Object.prototype.hasOwnProperty.call(payload, 'summary')) {
    formData.append('summary', payload.summary ?? '');
  }
  // 第 399 批：精选标记，后端按 'true'/'false' 解析
  if (Object.prototype.hasOwnProperty.call(payload, 'is_featured')) {
    formData.append('is_featured', payload.is_featured ? 'true' : 'false');
  }
  // 第 399 批：定时发布时间。传 null/空串表示清空定时发布（后端转 None，立即发布）
  if (Object.prototype.hasOwnProperty.call(payload, 'published_at')) {
    formData.append('published_at', payload.published_at || '');
  }

  // 第 401 批：原文链接。空串 = 清空原文链接（后端 validate_external_url 归一成 ''），
  // 因此只在 payload 显式带这个键时才 append —— 与上面几个可选字段同一口径，
  // 避免「行业动态」弹窗保存时把「新闻管理」页维护的数据顺手清掉。
  if (Object.prototype.hasOwnProperty.call(payload, 'external_url')) {
    formData.append('external_url', payload.external_url ?? '');
  }

  // 第 401 批：关联病害。multipart 没有"数组"类型，后端按**重复同名 key**解析；
  // 空数组时**不能** append 空串（后端会尝试把它转成 int 而报错），
  // 清空改用下面独立的 clear_related_pests 开关。
  if (Object.prototype.hasOwnProperty.call(payload, 'related_pests')) {
    const relatedPests = Array.isArray(payload.related_pests) ? payload.related_pests : [];
    relatedPests
      .filter((id) => id !== null && id !== undefined && id !== '')
      .forEach((id) => formData.append('related_pests', String(id)));
  }

  // 第 401 批：清空关联病害的开关（只有显式传键时才 append，布尔打字符串）
  if (Object.prototype.hasOwnProperty.call(payload, 'clear_related_pests')) {
    formData.append('clear_related_pests', payload.clear_related_pests ? 'true' : 'false');
  }

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
  const response = await http.post('/news/', buildNewsFormData(payload, imageFile), {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

/** 修改新闻 */
export async function updateNews(id, payload, imageFile = null) {
  const response = await http.patch(`/news/${id}/`, buildNewsFormData(payload, imageFile), {
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

/**
 * 上传新闻正文里的插图（第 141 批接上前端）
 *
 * 接口 `POST /api/news/upload_image/` **早就有**（第 91 批还专门加固过：大小上限、
 * 按**文件头**判真实格式而不是信 `content_type`、随机文件名），但前端从没调用过 ——
 * 于是 Quill 的图片按钮一直走默认行为，把图片转成 **base64 内联进正文**：
 * 一张手机照片就让正文膨胀好几 MB，图片也无法复用。
 *
 * 返回体：`{url, image_url, message}`（两个字段同值，历史原因都留着）。
 *
 * @param {FormData} formData 需含 `image` 字段
 */
export async function uploadNewsImage(formData) {
  const response = await http.post('/news/upload_image/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

export default {
  fetchNewsList,
  fetchNewsTags,
  fetchNewsDetail,
  fetchNewsRelated,
  fetchNewsStats,
  createNews,
  updateNews,
  toggleNewsPublished,
  deleteNews,
  uploadNewsImage,
  formatNewsError,
  getNewsCategoryLabel,
  NEWS_CATEGORIES,
};
