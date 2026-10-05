/**
 * 统一的 API 客户端
 *
 * 项目里原本存在三套 axios 实例（@/api、@/utils/axios、@/utils/request），
 * 拦截器的注册情况各不相同，容易出现“有的接口带 Token、有的不带、写操作缺 CSRF 头”的问题。
 * 这里提供一个统一实例：
 *   - 自动附带 Authorization: Token xxx
 *   - 自动附带 X-CSRFToken（写操作需要）
 *   - 统一把后端字段错误整理成可读提示（文案跟随界面语言，见 formatApiError）
 */
import axios from 'axios';
import { useAuthStore } from '@/stores/auth';
import { t } from '@/i18n';  // 第 83 批：错误兜底文案跟随语言

// VITE_API_BASE_URL 形如 http://127.0.0.1:8000/api，已包含 /api 前缀
export const baseURL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api').replace(/\/+$/, '');

// 媒体文件地址（去掉 /api 前缀）
export const mediaBase = baseURL.replace(/\/api\/?$/, '');

const http = axios.create({
  baseURL,
  timeout: 60000,
  withCredentials: true,
});

http.interceptors.request.use((config) => {
  const authStore = useAuthStore();
  const token = authStore.authToken;
  if (token) {
    config.headers.Authorization = `Token ${token}`;
  }

  const csrfMatch = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  if (csrfMatch) {
    config.headers['X-CSRFToken'] = decodeURIComponent(csrfMatch[1]);
  }

  config.headers['X-Requested-With'] = 'XMLHttpRequest';
  return config;
});

/** 把后端返回的相对图片地址转成可直接访问的绝对地址 */
export function toAbsoluteMediaUrl(path) {
  if (!path) return '';
  if (path.startsWith('http') || path.startsWith('data:')) {
    return path.replace('127.0.0.1', 'localhost');
  }
  return `${mediaBase}${path.startsWith('/') ? path : `/${path}`}`;
}

/**
 * 把接口错误整理成可读文案
 * @param {object} error axios 错误对象
 * @param {string} fallback 兜底文案（调用方一般传 t('msg.xxx')）
 * @param {object} labels 字段名 → 显示名映射（由调用方用 t() 构造，见 api/news.js）
 */
export function formatApiError(error, fallback = '', labels = {}) {
  // 第 83 批：兜底文案也走 i18n（原来是写死的中文默认参数）
  const fallbackText = fallback || t('msg.operationFailedRetry');
  const data = error?.response?.data;
  if (!data) {
    return error?.message || fallbackText;
  }
  if (typeof data === 'string') return data;
  if (data.detail) return data.detail;
  if (data.error) return data.error;

  const messages = [];
  Object.entries(data).forEach(([field, value]) => {
    const label = labels[field] || field;
    const text = Array.isArray(value) ? value.join(' / ') : String(value);
    messages.push(`${label}: ${text}`);
  });

  return messages.length ? messages.join('\n') : fallbackText;
}

export default http;
