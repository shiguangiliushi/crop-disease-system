/**
 * 媒体地址归一化（第 430 批）—— 专治 **Mixed Content**
 *
 * ## 为什么需要它
 *
 * 生产站的 HTTPS 页面里，控制台会报：
 *
 *     Mixed Content: The page at 'https://…' was loaded over HTTPS,
 *     but requested an insecure image 'http://10.0.0.5/media/…'
 *     This request has been blocked; the content must be served over HTTPS.
 *
 * 也就是**图片被浏览器拦掉了**（看起来像"图片裂了/丢了"）。根因有两类：
 *
 *  1. 历史数据里存的是**完整地址**（`http://<服务器IP>/media/x.jpg`）——
 *     早期用局域网 IP 调试时写进去的，后来换了域名也一直跟着；
 *  2. 富文本正文里的 `<img src="http://…/media/…">` 是自己写的 HTML，
 *     它绕过所有 `:src` 绑定，浏览器直接按 HTML 里的地址去取。
 *
 * ## 为什么"改成相对路径"是正解，而不是改成 https://
 *
 * 那个 host 很可能是个**没有 TLS 的 IP**：把 `http` 换成 `https` 只会换成
 * "连接失败"。相对路径 `/media/…` 用的是**当前页面**的协议与域名，
 * 页面是 https 它自然就是 https，页面是 http 开发的也能用 —— 一份数据两种环境都成立。
 *
 * ## 只管 `/media/`
 *
 * 只重写**路径以 `/media/` 开头**的 http 地址（本项目的 MEDIA_URL）。
 * 外部图床（`https://cdn…/x.jpg`）一律不动：它们的域名不归我们管，
 * 也不该被"顺手本地化"。
 */

//: 本项目的媒体前缀。与后端 `settings.MEDIA_URL = '/media/'` 一致。
const MEDIA_PREFIX = '/media/';

/**
 * 媒体服务的 **origin**（把 `VITE_API_BASE_URL` 里的 `/api` 去掉）。
 *
 * ## 为什么要单独一个函数
 *
 * `VITE_API_BASE_URL` 是**接口**基地址，带 `/api` 前缀；而 `/media/`、`/static/`
 * 由 nginx 在**根路径**上发。直接用接口基地址拼图片会得到
 * `…/api/media/x.jpg`（404）或 `http://127.0.0.1:8000/api/media/x.jpg`（线上 Mixed Content）。
 *
 * 三种环境下的取值：
 *
 * | 环境 | `VITE_API_BASE_URL` | 本函数返回 | 拼出来的图片地址 |
 * |---|---|---|---|
 * | 开发 | `http://127.0.0.1:8000/api` | `http://127.0.0.1:8000` | 绝对地址（Vite 里也配了 `/media` 代理） |
 * | 生产 | `/api` | `''` | `/media/x.jpg`（同源，页面是 https 就是 https） |
 * | 没配 | `''` | `''` | 同上 |
 *
 * 第 432 批：生产构建缺 `.env.production` 时，兜底值是 `http://127.0.0.1:8000/api`，
 * 拼出来的图片就是 `http://127.0.0.1:8000/api/media/…` —— 既 404 又是 Mixed Content。
 * 现在基地址兜底是 `/api`，这里再保证"图片不吃 /api 前缀"。
 */
export function mediaOrigin() {
  const base = import.meta.env.VITE_API_BASE_URL || '';
  return base.replace(/\/+$/, '').replace(/\/api$/, '');
}

/**
 * 把一个"不安全的媒体地址"换成同源相对路径。
 *
 * @param {string} value 可能是 `http://host/media/x.jpg`、`/media/x.jpg`、完整外链
 * @returns {string} 需要改写时返回相对的 `/media/…`；**不需要改写时返回空串**
 *   （返回空串而不是原值，是为了让调用方一眼看出"这次改了吗"）
 */
export function sameOriginMediaPath(value) {
  const text = typeof value === 'string' ? value.trim() : '';
  if (!text) return '';

  // 已经相对：/media/… 直接用（下面 getImageUrl 也不会再拼 API 前缀）
  if (text.startsWith(MEDIA_PREFIX)) return '';

  // 只有 http:// 才是不安全来源；https 与外链都不动
  if (!/^http:\/\//i.test(text)) return '';

  try {
    const parsed = new URL(text);
    if (!parsed.pathname.startsWith(MEDIA_PREFIX)) return '';
    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return '';   // 不是合法 URL（比如脏数据）就原样放着，由后端命令去清
  }
}

/**
 * `<img src>` / `:src` 绑定的统一入口：能归一就归一，否则原样返回。
 *
 * 用在富文本渲染钩子与 `getImageUrl` 里 —— **同一份实现**，
 * 免得"富文本改好了、图片组件又漏一个"。
 */
export function normalizeMediaUrl(value) {
  return sameOriginMediaPath(value) || value;
}

/** 递归深度上限：正常响应不会超过这个嵌套，超了就当数据有问题、不再下钻 */
const MAX_DEPTH = 12;

/**
 * 字符串里**内嵌**的 `http://…/media/…`（HTML 的 `<img src>`、Markdown 图片、纯文本链接）
 *
 * 与 `sameOriginMediaPath` 的分工：那个处理"整串就是一个 URL"，这个处理"URL 藏在一段
 * HTML/文本里"。两者都只认 `http://` + `/media/`，https 外链一律不动。
 */
const EMBEDDED_HTTP_MEDIA = /http:\/\/[^/\s"'<>()]+(\/media\/[^"\s'<>()]+)/gi;

/** 把一段文本里内嵌的 http 媒体地址换成相对路径（没有就原样返回） */
export function normalizeMediaUrlsInText(text) {
  if (typeof text !== 'string' || !text.includes('http') || !text.includes('/media/')) {
    return text;
  }
  const whole = sameOriginMediaPath(text);
  if (whole) return whole;
  return text.replace(EMBEDDED_HTTP_MEDIA, '$1');
}

/**
 * 把**整个响应体**里出现的 `http://…/media/…` 归一成相对路径（第 431 批）。
 *
 * ## 为什么要在响应层再做一次
 *
 * 第 430 批修了两处渲染出口（富文本的 DOMPurify 钩子、`getImageUrl`），
 * 但页面里大量图片是**直接绑数据**的：`<img :src="news.image">`、`<el-image :src="pest.image">`。
 * 它们拿到什么就发什么 —— 数据里是 `http://<服务器IP>/media/…`，浏览器就按 Mixed Content 拦。
 * 一个个组件去包 `normalizeMediaUrl()` 既漏又不持久（新增页面没人记得），
 * 所以在**数据进内存的那一刻**统一归一：一处收口，所有页面自动受益。
 *
 * ## 三条边界
 *
 * 1. **只动字符串**，且只动匹配 `http://…/media/…` 的（见 `sameOriginMediaPath`）；
 * 2. **不碰非 JSON**：`Blob` / `ArrayBuffer` / 文件下载必须是原始字节
 *    （调用方用 `responseType: 'blob'` 时要跳过，见 `api/http.js`）；
 * 3. 深度上限 `MAX_DEPTH`：异常嵌套的数据不再下钻，避免递归过深。
 *
 * @param {*} data 任意 JSON 值（字符串 / 数组 / 对象 / 数字 …）
 * @returns {*} 归一后的新值（不改原对象，避免影响 axios 之外的引用）
 */
export function normalizeMediaUrlsIn(data, depth = 0) {
  if (depth > MAX_DEPTH) return data;
  if (typeof data === 'string') {
    // 先做一次廉价判断：绝大多数字符串不含 'http'，不必进正则
    return data.includes('http') ? normalizeMediaUrlsInText(data) : data;
  }
  if (Array.isArray(data)) {
    let changed = false;
    const next = data.map((item) => {
      const value = normalizeMediaUrlsIn(item, depth + 1);
      if (value !== item) changed = true;
      return value;
    });
    return changed ? next : data;
  }
  if (data && typeof data === 'object') {
    // 只处理普通对象；Date / Blob / File 之类原样返回
    if (Object.getPrototypeOf(data) !== Object.prototype) return data;
    let changed = false;
    const next = {};
    for (const [key, value] of Object.entries(data)) {
      const normalized = normalizeMediaUrlsIn(value, depth + 1);
      next[key] = normalized;
      if (normalized !== value) changed = true;
    }
    return changed ? next : data;
  }
  return data;
}
