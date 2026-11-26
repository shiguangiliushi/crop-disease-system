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
