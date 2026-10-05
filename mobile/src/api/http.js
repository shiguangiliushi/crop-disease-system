/**
 * 移动端统一 API 客户端
 * ----------------------------------------------------------------------------
 * 与桌面端（frontend/src/api/http.js）保持同一套契约：
 *   · 自动带 `Authorization: Token xxx`
 *   · 写操作自动带 `X-CSRFToken`（Django 的 CSRF 只对 cookie 会话生效，
 *     带 Token 的接口其实不需要，但带上不会错，也兼容仍走 session 的接口）
 *   · 统一把后端字段错误整理成可读提示
 *
 * 与桌面端唯一的区别：**默认用相对地址 `/api`**，让请求走 vite dev server 的代理。
 * 因为农户是用手机访问 `http://<电脑IP>:5174`，若像桌面端那样写死
 * `http://127.0.0.1:8000/api`，手机会去请求"手机自己"的 8000 端口 → 必然失败。
 */
import axios from 'axios';

export const TOKEN_KEY = 'mobile_token';
export const USER_KEY = 'mobile_user';

export const baseURL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/+$/, '');
const isAbsoluteBase = /^https?:\/\//i.test(baseURL);
/** 图片地址前缀：相对地址时留空（交给代理/同源），绝对地址时去掉 /api */
export const mediaBase = isAbsoluteBase ? baseURL.replace(/\/api\/?$/, '') : '';

const http = axios.create({
  baseURL,
  timeout: 60000,
  withCredentials: true,
});

http.interceptors.request.use((config) => {
  let token = '';
  try {
    token = localStorage.getItem(TOKEN_KEY) || '';
  } catch {
    /* 隐私模式下读不到，按未登录处理 */
  }
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

/**
 * 第 91 批：**401 自愈** —— Token 失效时自动清理身份并回到登录页
 * ----------------------------------------------------------------------------
 * 改前的实际后果（农户会直接卡住）：
 *   · `stores/auth.js` 的 `isAuthenticated` 只看"本地有没有 token"，token 过期了
 *     界面**仍然显示已登录**；
 *   · 各页面请求全部 401，但没有人处理 → 页面上只显示"请求失败"，
 *     「我的」里的统计静默回落成 0；
 *   · 用户唯一的出路是**自己想到**去"我的"点退出登录再重新登录 —— 而多数人不会。
 *
 * 现在：任何请求返回 401 → 清掉本地身份 → 带 `reason=expired` 跳登录页
 *（登录页据此提示"登录已过期，请重新登录"，而不是让人对着"请求失败"发呆）。
 *
 * 两个必须注意的细节：
 *   1. **不能 import router**：`router` 会 import `stores/auth`，本文件又被 store 使用，
 *      顶层互相 import 会形成循环依赖；所以在函数内部动态 import（Vite 会正常分包）。
 *   2. **登录接口自己的 401 不触发跳转**：那是"密码错"，由登录页自己提示；
 *      否则用户会看到"登录已过期"这种驴唇不对马嘴的说明。
 */
const AUTH_EXPIRED_FLAG = 'mobile_auth_expired';

/**
 * 正在跳登录页的标记（第 91 批修正）
 *
 * 为什么需要它：一个页面上往往**同时**有好几个请求（记录列表 + 统计 + 画像…），
 * token 失效时它们会**几乎同时**返回 401。若每个 401 都 `router.replace({name:'login'})`，
 * 第二个就会撞上"与当前导航重复"，Vue Router 抛 NavigationDuplicated 并把这次导航**中止** ——
 * 实测结果：页面停在 `/detect`（当时的页面），用户根本没被送到登录页，只看到一片空白。
 * 所以：进程内只允许跳一次，落地后由 `afterEach` 复位。
 */
let redirectingToLogin = false;

http.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error?.response?.status;
    const url = String(error?.config?.url || '');
    const isAuthEndpoint = url.includes('login') || url.includes('register')
      || url.includes('password-reset');

    if (status === 401 && !isAuthEndpoint && !redirectingToLogin) {
      // ⚠️ 必须走 store 的 clearAuth()，不能只删 localStorage：
      // `isAuthenticated` 读的是**内存里的 ref**，只清存储的话路由守卫仍认为已登录，
      // 会把刚跳到的 /login 又弹回 /detect（实测踩过）。
      try {
        const [{ useAuthStore }, { default: router }] = await Promise.all([
          import('@/stores/auth'),
          import('@/router'),
        ]);
        useAuthStore().clearAuth();

        try {
          // 标记"这次是被踢出来的"，登录页读完即删
          sessionStorage.setItem(AUTH_EXPIRED_FLAG, '1');
        } catch {
          /* 隐私模式忽略 */
        }

        redirectingToLogin = true;
        router.afterEach(() => { redirectingToLogin = false; });
        if (router.currentRoute.value.name !== 'login') {
          await router.replace({ name: 'login', query: { reason: 'expired' } });
        }
      } catch (navError) {
        // 导航失败（例如被别的导航打断）不该吞掉原始 401 —— 让调用方照常拿到错误
        console.warn('[auth] 401 后的跳转未完成:', navError?.message || navError);
      } finally {
        // 兜底复位：万一 afterEach 没跑到（例如本来就在登录页，没发生导航）
        setTimeout(() => { redirectingToLogin = false; }, 800);
      }
    }

    return Promise.reject(error);
  },
);

/** 读取并消费"登录已过期"标记（登录页用） */
export function consumeAuthExpiredFlag() {
  try {
    const flag = sessionStorage.getItem(AUTH_EXPIRED_FLAG);
    if (flag) sessionStorage.removeItem(AUTH_EXPIRED_FLAG);
    return flag === '1';
  } catch {
    return false;
  }
}

/**
 * 把后端返回的图片地址转成当前页面能访问的地址。
 *
 * ⚠️ 这里必须处理"绝对地址指向本机"的情况，否则**手机上图片全是坏的**：
 * 后端用 `request.build_absolute_uri()` 生成地址，而我们是通过 vite 代理
 * （changeOrigin: true）访问的，于是返回的是 `http://127.0.0.1:8000/media/...`。
 * 这个地址在电脑上恰好能打开，但在手机上它指向**手机自己** —— 必须剥成
 * 相对路径 `/media/...`，让请求跟着当前页面的 origin（也就是 vite 代理）走。
 */
export function toAbsoluteMediaUrl(path) {
  if (!path) return '';
  if (path.startsWith('data:')) return path;

  if (/^https?:\/\//i.test(path)) {
    const local = path.match(/^https?:\/\/(?:127\.0\.0\.1|localhost|0\.0\.0\.0)(?::\d+)?(\/.*)$/i);
    if (local) {
      return `${mediaBase}${local[1]}`;
    }
    return path;
  }

  const normalized = path.replace(/\\/g, '/');
  const suffix = normalized.startsWith('/') ? normalized : `/${normalized}`;
  return `${mediaBase}${suffix}`;
}

/** 把接口错误整理成可读文案（字段级错误也拼出来） */
export function formatApiError(error, fallback = '操作失败，请稍后重试') {
  const data = error?.response?.data;
  if (!data) return error?.message || fallback;
  if (typeof data === 'string') return data;
  if (data.detail) return data.detail;
  if (data.error) return data.error;
  if (data.message) return data.message;

  const messages = [];
  Object.entries(data).forEach(([field, value]) => {
    const text = Array.isArray(value) ? value.join('；') : String(value);
    messages.push(`${field}：${text}`);
  });
  return messages.length ? messages.join('\n') : fallback;
}

export default http;
