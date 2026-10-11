/**
 * 上传前压缩图片（第 74 批写在识别页里；第 165 批提取成共用工具）
 * ============================================================================
 * ## 为什么需要
 *
 * 农户在田里用手机拍照，一张 3~8 MB。直传原图有三个后果：
 *   · 弱网下上传很慢、耗流量；
 *   · 经常撞到后端 **5 MB 上限**被拒 —— 用户只看到"图片大小不能超过5MB"，
 *     既不知道怎么办，也不知道该怎么改（这条是评审意见点名的）；
 *   · 论坛配图/新闻配图同理。
 *
 * 本地把长边压到 1600px、JPEG 质量 0.85 再提交：对识别精度没有实际影响
 * （模型输入远小于此），体积通常降到 1/5 以下。
 *
 * ## 两条安全约定（沿用第 74 批的做法，测试与注释都保留）
 *   · **压缩失败就用原图** —— 绝不让用户因为"压缩"这件事传不了图；
 *   · **压完反而更大就用原图** —— 原图可能已经是高度压缩的 JPEG。
 */
const MAX_EDGE = 1600;
const QUALITY = 0.85;
/** 小于这个体积的文件没必要处理 */
const SKIP_BELOW_BYTES = 300 * 1024;

/**
 * 压缩一张图片（返回 File；不需要压缩或失败时返回原文件）
 *
 * @param {File|Blob} file
 * @param {{maxEdge?: number, quality?: number}} [options]
 * @returns {Promise<File|Blob>}
 */
export async function compressImage(file, options = {}) {
  const maxEdge = options.maxEdge || MAX_EDGE;
  const quality = options.quality || QUALITY;

  if (!file || !String(file.type || '').startsWith('image/')) return file;
  // GIF 可能是动图，canvas 重编码会毁掉动画；体积本来就不大的也不必折腾
  if (file.type === 'image/gif' || file.size < SKIP_BELOW_BYTES) return file;

  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, width, height);
    bitmap.close?.();

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality));

    // 压完反而更大（原图已是高度压缩的 JPEG）→ 用原图
    if (!blob || blob.size >= file.size) return file;

    const name = String(file.name || 'photo').replace(/\.[^.]+$/, '') + '.jpg';
    return new File([blob], name, { type: 'image/jpeg', lastModified: Date.now() });
  } catch (error) {
    console.warn('[image] 压缩失败，改用原图:', error?.message || error);
    return file;
  }
}

export default compressImage;
