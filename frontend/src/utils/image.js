/**
 * 获取图片的完整URL
 * @param {string} path - 图片路径
 * @returns {string} 完整的图片URL
 */
export const getImageUrl = (path) => {
  if (!path) return '';
  
  // 如果已经是完整的URL，直接返回
  if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('data:')) {
    return path;
  }
  
  // 处理相对路径
  if (path.startsWith('/')) {
    // 如果路径以/开头，说明是绝对路径，直接拼接API基础URL
    const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
    return `${baseUrl}${path}`;
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
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
  const url = new URL(path, baseUrl);
  
  // 添加缩略图参数（这里假设你的后端支持这些参数）
  url.searchParams.set('width', width);
  if (height) {
    url.searchParams.set('height', height);
  }
  
  return url.toString();
};
