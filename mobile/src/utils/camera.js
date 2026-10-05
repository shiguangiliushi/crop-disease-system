/**
 * 应用内拍照工具（移动端，第 75 批）
 * ----------------------------------------------------------------------------
 * 与桌面客户端 frontend/src/utils/camera.js 是同一套逻辑（两个独立工程，
 * 各自保留一份，避免跨工程引用）；差别只在默认取景参数：手机端把长边压到
 * 1280，兼顾清晰度与弱网下的上传速度。
 *
 * ⚠️ 关键限制（决定"降级"必须有）：
 *   浏览器只在**安全上下文**（https 或 localhost）暴露 `navigator.mediaDevices`。
 *   农户用手机访问 `http://<电脑IP>:5174` 属于非安全上下文 → 拿不到摄像头，
 *   必须回退到 `<input capture="environment">`（唤起系统相机）。
 *   想要真正的"页面内取景拍照"，要么部署到 https，要么用 adb reverse 之类的
 *   方式把页面映射到 localhost。
 */

export function hasInAppCamera() {
  try {
    if (!window.isSecureContext) return false;
    return Boolean(navigator.mediaDevices?.getUserMedia);
  } catch {
    return false;
  }
}

/** getUserMedia 异常 → i18n key */
export function describeCameraError(error) {
  switch (error?.name || '') {
    case 'NotAllowedError':
    case 'PermissionDeniedError':
      return 'camera.denied';
    case 'NotFoundError':
    case 'DevicesNotFoundError':
      return 'camera.notFound';
    case 'NotReadableError':
    case 'TrackStartError':
      return 'camera.busy';
    case 'OverconstrainedError':
      return 'camera.overconstrained';
    case 'SecurityError':
      return 'camera.insecure';
    default:
      return 'camera.failed';
  }
}

/**
 * 把视频当前帧抓成 JPEG 文件
 *
 * ⚠️ 默认值 `1280 / 0.9` 与 `components/CameraCapture.vue` 里的 `maxEdge / quality` 是**同一套**，
 *    而 `utils/image.js` 的上传前压缩用的是 `1600 / 0.85` —— 三处值不同不是笔误：
 *    · 这里的 **1280 是"取景/抓帧"分辨率**，决定中低端机的流畅度与内存占用；
 *    · `image.js` 的 1600 是**最终上传尺寸**，只对"从相册选大图"那条路径才起作用
 *      （抓帧已压到 1280 时，compressImage 不会放大）。
 *    完整对照表见 `utils/image.js` 顶部。要调"移动端标准"改那里。
 *
 * @param {HTMLVideoElement} video
 * @param {{maxEdge?: number, quality?: number}} options
 * @returns {Promise<File>}
 */
export async function captureFrameFromVideo(video, { maxEdge = 1280, quality = 0.9 } = {}) {
  if (!video || !video.videoWidth || !video.videoHeight) {
    throw new Error('video_not_ready');
  }

  const scale = Math.min(1, maxEdge / Math.max(video.videoWidth, video.videoHeight));
  const width = Math.round(video.videoWidth * scale);
  const height = Math.round(video.videoHeight * scale);

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;

  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('canvas_unavailable');
  ctx.drawImage(video, 0, 0, width, height);

  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality));
  if (!blob) throw new Error('encode_failed');

  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  return new File([blob], `photo-${stamp}.jpg`, { type: 'image/jpeg', lastModified: Date.now() });
}
