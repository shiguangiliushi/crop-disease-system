import { mediaOrigin, sameOriginMediaPath } from './mediaUrl';

/**
 * 获取图片的完整URL
 *
 * 第 430 批：历史数据里存过 `http://<服务器IP>/media/x.jpg` 这种**完整地址**，
 * HTTPS 页面下会被浏览器按 Mixed Content 拦掉（图片裂开）。所以第一件事是
 * 把"http 的 /media/ 地址"归一成同源相对路径。理由见 `utils/mediaUrl.js`。
 *
 * @param {string} path - 图片路径
 * @returns {string} 完整的图片URL
 */
export const getImageUrl = (path) => {
  if (!path) return '';

  // /media/ 走媒体 origin：生产为空（同源相对），开发是 http://127.0.0.1:8000
  const mediaPath = sameOriginMediaPath(path);
  if (mediaPath) return mediaPath;

  // 如果已经是完整的URL，直接返回
  if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('data:')) {
    return path;
  }
  
  // 处理相对路径
  if (path.startsWith('/')) {
    // 只拼**媒体 origin**（去掉 /api）：接口前缀和媒体前缀不是一回事，
    // 拼成 `…/api/media/…` 只会 404；生产下 origin 为空 → 直接同源相对路径。
    return `${mediaOrigin()}${path}`;
  }
  
  // 处理相对路径（不以/开头）
  return path;
};

/**
 * 获取缩略图URL
 * @param {string} path - 原始图片路径
 * @param {number} [width=300] - 缩略图宽度
 * @param {number} [height] - 缩略图高度（可选，不传则按比例缩放）
 * @returns {string} 缩略图URL
 */
export const getThumbnailUrl = (path, width = 300, height) => {
  if (!path) return '';
  
  // 如果是base64或完整URL，直接返回
  if (path.startsWith('data:') || path.startsWith('http')) {
    return path;
  }
  
  // 处理相对路径
  // ⚠️ 不能用 `new URL(path, baseUrl)`：生产下 origin 是空串（同源相对），
  //    空 base 会直接抛 `Invalid URL`。手工拼 query 更稳，也更好测。
  const base = mediaOrigin();
  const relative = path.startsWith('/') ? path : `/${path}`;
  const params = new URLSearchParams({ width: String(width) });
  if (height) params.set('height', String(height));
  const separator = relative.includes('?') ? '&' : '?';

  return `${base}${relative}${separator}${params.toString()}`;
};
