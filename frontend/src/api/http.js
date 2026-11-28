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
import { normalizeMediaUrlsIn, sameOriginMediaPath } from '@/utils/mediaUrl';  // 第 431 批：响应里的 http 媒体地址归一
import { t, locale } from '@/i18n';  // 第 83 批：错误兜底文案跟随语言；第 197 批：请求带语言头
import { pickReadableMessage } from '@/utils/readableError';  // 第 213 批：英文技术文案不进用户界面

// VITE_API_BASE_URL 形如 http://127.0.0.1:8000/api（开发）或 /api（生产，同源）
//
// ⚠️ 第 432 批：兜底值从 `http://127.0.0.1:8000/api` 改成 **`/api`**。
// 仓库里只有 `.env.development`（当时缺 `.env.production`），于是**生产构建**取不到变量、
// 用上兜底值 → 产物里写死 127.0.0.1:8000，线上所有请求与图片都指向访客自己的机器。
// 兜底必须是"最安全的那种"：同源相对路径（由 nginx 反代到后端）。
export const baseURL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/+$/, '');

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
  (response) => {
    // 第 431 批：把响应里 `http://<服务器IP>/media/…` 这类**绝对不安全地址**
    // 统一归一成相对路径（`/media/…`）。页面里大量 `<img :src="news.image">`
    // 是直接绑数据的，逐组件改既漏又不持久 —— 在数据进内存这一刻收口最省事。
    // 文件下载（`responseType: 'blob'`）跳过：那里必须是原始字节。
    const config = response?.config || {};
    const isBinary = config.responseType === 'blob' || config.responseType === 'arraybuffer';
    if (!isBinary) {
      response.data = normalizeMediaUrlsIn(response.data);
    }
    return response;
  },
  (error) => {
    const status = error?.response?.status;
    if (status === 401 && !error.config?.skipAuthRedirect) {
      // 第 439 批：游客试用身份失效时**不要**把人送到登录页 ——
      // 他从没登录过，看到"登录已过期"只会困惑。清掉身份即可，
      // 下一次进入识别/问答页时守卫会重新开一个试用身份。
      let wasGuest = false;
      try {
        const store = useAuthStore();
        wasGuest = Boolean(store?.isGuest);
        store.clearAuth();
      } catch (err) {
        console.error('清理登录态失败:', err);
      }

      const path = window.location.pathname;
      const onAuthPage = AUTH_PAGE_PREFIXES.some((prefix) => path.startsWith(prefix));
      if (!wasGuest && !authRedirecting && !onAuthPage) {
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

  // 第 434 批：历史数据里可能存着 `http://<主机>/media/x.jpg?sig=…`（早期本机调试时写进去的）。
  // 直接原样返回 → HTTPS 页面下会被浏览器拦/改成 https 后连不上（ERR_CONNECTION_REFUSED）。
  // 先归一成同源相对路径（`?sig=` 原样保留），这样"库里有脏数据"也不会裂图。
  const mediaPath = sameOriginMediaPath(path);
  if (mediaPath) return mediaPath;

  if (path.startsWith('http') || path.startsWith('data:')) {
    return path.replace('127.0.0.1', 'localhost');
  }
  return `${mediaBase}${path.startsWith('/') ? path : `/${path}`}`;
}

/**
 * 把接口错误整理成可读文案
 *
 * ⚠️ 第 213 批：**英文技术文案不再直出给用户**。
 * 后端的 `detail` / `error` 有两种来源：我们自己写的中文提示（"未检测到图片文件"），
 * 以及 DRF / Django 的英文技术文案（"Authentication credentials were not provided."、
 * "Invalid token."、"Expected a list of items but got type \"dict\"."）。
 * 后者弹给农户等于没说、还像报错 —— 而本函数被约 20 处调用，
 * 是**唯一**的统一出口，所以在这里收口最省事。
 *
 * 判据复用 `pickReadableMessage`（含中日韩字符才用原文，否则回落友好文案），
 * 它早就存在、此前只接了 `EditPostView` 一处（同一条意见的另一半）。
 * 技术原文仍由调用方 `console.error` 留在控制台，排查不受影响。
 *
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
  if (typeof data === 'string') return pickReadableMessage(data, fallbackText);
  if (data.detail) return pickReadableMessage(data.detail, fallbackText);
  if (data.error) return pickReadableMessage(data.error, fallbackText);

  const messages = [];
  Object.entries(data).forEach(([field, value]) => {
    const label = labels[field] || field;
    const text = Array.isArray(value) ? value.join(' / ') : String(value);
    //: 字段级错误也过一次同样的过滤器 —— Django 的字段报错同样是英文
    messages.push(`${label}: ${pickReadableMessage(text, t('msg.operationFailedRetry'))}`);
  });

  return messages.length ? messages.join('\n') : fallbackText;
}

export default http;
