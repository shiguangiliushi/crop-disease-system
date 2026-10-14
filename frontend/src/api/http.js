/**
 * 统一的 API 客户端
 *
 * 项目里原本存在三套 axios 实例（@/api、@/utils/axios、@/utils/request），
 * 拦截器的注册情况各不相同，容易出现“有的接口带 Token、有的不带、写操作缺 CSRF 头”的问题。
 * 这里提供一个统一实例：
 *   - 自动附带 Authorization: Token xxx
 *   - 自动附带 X-CSRFToken（写操作需要）
 *   - 统一把后端字段错误整理成可读提示（文案跟随界面语言，见 formatApiError）
 *   - 第 123 批：**401 统一收口** —— 清登录态 + 送到对应端的登录页（见下面的响应拦截器）
 */
import axios from 'axios';
import { useAuthStore } from '@/stores/auth';
import { t, locale } from '@/i18n';  // 第 83 批：错误兜底文案跟随语言；第 197 批：请求带语言头

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
  // 第 197 批：带上界面语言（后端已挂 LocaleMiddleware，会协商成 request.LANGUAGE_CODE）。
  // 首个消费者是智能回答助手 —— 它据此选提示词与词条的中/英文字段，
  // 否则用户在英文界面下会收到中文回答。
  if (locale.value) {
    config.headers['Accept-Language'] = locale.value;
  }
  return config;
});

// ============================================================================
// 401 统一处理（第 123 批补）
// ----------------------------------------------------------------------------
// 这个客户端原来**只有请求拦截器**，没有响应拦截器 —— 于是 token 一旦失效
// （本项目 Token 有 7 天有效期，见后端 api/middleware.py 的 TOKEN_TTL；
//   也可能因为改过密码 / 在别的标签页登出而被删掉），会发生什么：
//
//   · 后端对每个接口都回 401（它甚至带了 `X-Token-Expired: 1` 这个明确信号，
//     但**前端从来没人读**）；
//   · 前端在本地还"有 token"，于是 boot 时打印 "assuming user is authenticated"，
//     接着通知铃铛、私信未读、当前页面的数据请求**全部 401**；
//   · 页面**不跳登录、也不提示**，用户看到的就是"一堆空面板 + 控制台红字"。
//
// 现在统一在这里收口：清掉本地登录态 → 送到**对应端的**登录页（管理区去
// /admin/login，其余去 /login），并带上 `reason=sessionExpired` ——
// 两个登录页都已经会把这个原因码翻成"登录已过期，请重新登录。"（第 84 批的约定）。
//
// 几个刻意的细节：
//   · **去重**：一串并发请求会同时 401，只允许触发一次跳转（`redirecting`）；
//   · **不在认证页上跳**：已经在 /login、/admin/login 等页面时不做跳转，避免打转；
//   · **`skipAuthRedirect`**：少数请求（如登出）明知可能 401 且不想被拽走，传这个标记即可；
//   · 用 `window.location.href`（整页跳转）而不是路由跳转：与 utils/axios.js 的既有
//     行为一致，且能一次性清干净内存里的残留状态。
// ============================================================================
let authRedirecting = false;

/** 认证相关页面：在这些页面上不再跳转（否则会来回打转） */
const AUTH_PAGE_PREFIXES = ['/login', '/admin/login', '/register', '/forgot-password', '/reset-password'];

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    if (status === 401 && !error.config?.skipAuthRedirect) {
      try {
        useAuthStore().clearAuth();
      } catch (err) {
        console.error('清理登录态失败:', err);
      }

      const path = window.location.pathname;
      const onAuthPage = AUTH_PAGE_PREFIXES.some((prefix) => path.startsWith(prefix));
      if (!authRedirecting && !onAuthPage) {
        authRedirecting = true;
        // 管理区回管理端登录页（第 116 批分开的两套入口，别把人丢错站）
        const loginPath = path.startsWith('/admin') ? '/admin/login' : '/login';
        const params = new URLSearchParams({
          reason: 'sessionExpired',
          redirect: path + window.location.search,
        });
        console.warn(`[auth] ${status}：登录已失效，跳转 ${loginPath}`);
        window.location.href = `${loginPath}?${params.toString()}`;
      }
    }
    return Promise.reject(error);
  },
);

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
