/**
 * 应用内拍照（in-app camera）工具（第 75 批）
 * ----------------------------------------------------------------------------
 * 背景：第 74 批给识别页加的「拍照」只是一个 `<input type="file" capture="environment">`。
 * 它在手机上能唤起系统相机，但在**电脑上等于再开一次文件选择框** ——
 * 用户点了"拍照"却弹出"选择文件"，页面里也没有取景框、没有快门。
 *
 * 这里用 getUserMedia 做真正的页面内拍照：
 *   · 实时预览（后置优先，可切前置）
 *   · 快门把当前帧画进 canvas → 压缩成 JPEG File，直接进识别流程
 *
 * ⚠️ 两个必须记住的浏览器限制（决定了"降级"不是可选项）：
 *   1. **非安全上下文没有摄像头**：只有 https 或 localhost 才暴露
 *      `navigator.mediaDevices`。局域网调试（http://192.168.x.x:5173，
 *      也就是农户用手机访问时的真实地址）下它是 undefined。
 *   2. **iframe/权限策略**：页面被 http 页面嵌套或权限被拒时同样拿不到。
 * 因此调用方必须保留 `<input capture>` 这条老路（见 hasInAppCamera / describeCameraError）。
 */

/** 当前环境是否具备"页面内拍照"能力（不申请权限，只做能力探测） */
export function hasInAppCamera() {
  try {
    // 非 localhost 的 http 页面：mediaDevices 整个不存在
    if (!window.isSecureContext) return false;
    return Boolean(navigator.mediaDevices?.getUserMedia);
  } catch {
    return false;
  }
}

/**
 * 把 getUserMedia 的异常翻译成"人话"。
 * 返回值是 i18n key，由组件决定怎么展示（工具层不引入 i18n，便于单测）。
 */
export function describeCameraError(error) {
  const name = error?.name || '';
  switch (name) {
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
      // 例如设备没有前置摄像头时请求 facingMode: 'user'
      return 'camera.overconstrained';
    case 'SecurityError':
      return 'camera.insecure';
    default:
      return 'camera.failed';
  }
}

/**
 * 把视频当前帧抓成图片文件。
 * @param {HTMLVideoElement} video 正在播放的 video 元素
 * @param {object} options
 * @param {number} options.maxEdge 长边上限（默认 1600，与识别页上传前压缩口径一致）
 * @param {number} options.quality JPEG 质量（0~1）
 * @returns {Promise<File>}
 */
export async function captureFrameFromVideo(video, { maxEdge = 1600, quality = 0.92 } = {}) {
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
