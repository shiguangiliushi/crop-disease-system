/**
 * 图片处理（移动端）
 * ----------------------------------------------------------------------------
 * 农户在田里用手机拍照，一张 3~8MB。弱网下直传原图：上传慢、耗流量，
 * 还容易撞到后端 5MB 上限被拒（用户只看到"图片过大"却不知怎么办）。
 * 这里在上传前把长边压到 1600px / JPEG 0.85，体积通常降到 1/5 以下，
 * 对识别精度没有实际影响（模型输入远小于此）。
 * 压缩失败一律回落原文件 —— 绝不因为"优化"而让用户传不了图。
 *
 * ⚠️ 移动端有**三处**配置值，改之前先看清各自管什么（第 107 批补）
 * ----------------------------------------------------------------------------
 * | 位置 | 值 | 管什么 |
 * |---|---|---|
 * | 本文件 `COMPRESS_MAX_EDGE / COMPRESS_QUALITY` | 1600 / 0.85 | **上传前压缩**：决定性的一步，最终交给后端的就是它 |
 * | `components/CameraCapture.vue` 的 `maxEdge / quality` | 1280 / 0.9 | **抓帧**：把相机画面变成一张图，之后还会再走一次 compressImage |
 * | `utils/camera.js` 的默认值 | 1280 / 0.9 | 与上一行同一套（抓帧路径的默认参数），保持同步 |
 *
 * 为什么抓帧用 1280 而压缩用 1600 不是"重复配置"：
 * 抓帧值决定**取景分辨率**（越小越快、越省内存），压缩值决定**最终上传尺寸**。
 * 抓帧已经压到 1280 时，compressImage 的 1600 不会再放大（`scale = Math.min(1, …)`），
 * 所以实际生效的是 1280；只有"从相册选一张大图"这条路径才会用到 1600。
 * 真要统一成"移动端标准"，改这里的值即可（另外两处只影响抓帧快慢）。
 */

/** 后端允许的最大上传体积（超过会被拒）。**必须与后端上限保持一致** */
export const UPLOAD_LIMIT = 5 * 1024 * 1024;

/** 压缩后长边上限（px）。1600 的依据：YOLO 推理输入远小于此，再大只是白耗流量 */
const COMPRESS_MAX_EDGE = 1600;

/** JPEG 质量。0.85 是"肉眼几乎无损"与"体积明显下降"的常见折中点 */
const COMPRESS_QUALITY = 0.85;

/**
 * 跳过压缩的体积门槛（300KB）。
 *
 * 为什么是 300KB：农户手机拍的原图在 3~8MB，压缩收益巨大；
 * 而 300KB 以下的图压完往往反而更小不了多少，却要付出一次解码+编码的耗时
 * （中低端安卓机上 200ms 量级），还得承担重编码带来的画质损失。
 * 也就是说这是一条**"值不值得压"的成本线**，不是安全线。
 */
const COMPRESS_SKIP_BYTES = 300 * 1024;

/**
 * 上传前压缩。**失败一律返回原文件**，不抛异常。
 *
 * 各分支的取舍（第 107 批补，此前只有模块头有说明、函数体一句没有）：
 *   · **非图片**：直接返回（后端会拒，不该由这里判断类型合法性）；
 *   · **GIF**：跳过。真实原因是**用 canvas 重编码会毁掉动画** ——
 *     只留第一帧、且 PNG/GIF 的透明通道会被拍平。不是"GIF 不用压"；
 *   · **小于 300KB**：跳过（理由见 `COMPRESS_SKIP_BYTES`）；
 *   · **压完反而更大**：返回原文件（小图重编码偶尔会变大）；
 *   · **任何异常**：返回原文件。宁可传大图被后端拒，也不能因为"优化"让用户传不了图。
 *
 * ⚠️ 两个副作用要知情：
 *   1. 输出强制为 JPEG —— **透明通道会被拍平成黑底**（叶病照片一般是实的，影响小）；
 *   2. **EXIF 全部丢失**（方向、GPS、时间）。方向一般由浏览器自动纠正，问题不大；
 *      GPS 被去掉对隐私其实是好事，但这是"顺带"而非设计 —— 别指望它当隐私功能。
 *      文件名也会被改成 `.jpg`（否则后端按扩展名判断类型会出错）。
 *
 * ⚠️ 本函数**不检查 `UPLOAD_LIMIT`**：压缩策略与拒绝策略是两条独立的线。
 *    调用方（`views/DetectView.vue`）在压缩**之后**才检查上限 ——
 *    所以一个 >5MB 的 GIF、或压缩失败的图，会被拒且没有别的出路。
 *    见本文件末尾的"已知缺口"。
 */
export async function compressImage(file) {
  if (!file?.type?.startsWith('image/') || file.type === 'image/gif' || file.size < COMPRESS_SKIP_BYTES) {
    return file;
  }

  try {
    const bitmap = await createImageBitmap(file);
    // scale 上限为 1：只缩小、不放大（否则小图会被插值成 1600 反而更糊更占体积）
    const scale = Math.min(1, COMPRESS_MAX_EDGE / Math.max(bitmap.width, bitmap.height));
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    // 取不到 2d context（极老的浏览器/内存不足）就放弃压缩，别让整条上传失败
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, width, height);
    bitmap.close?.();   // 主动释放 ImageBitmap 占的内存（手机上很值钱）

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', COMPRESS_QUALITY));
    if (!blob || blob.size >= file.size) return file;

    const name = (file.name || 'photo').replace(/\.[^.]+$/, '') + '.jpg';
    return new File([blob], name, { type: 'image/jpeg', lastModified: Date.now() });
  } catch (error) {
    console.warn('[image] 压缩失败，改用原图:', error?.message || error);
    return file;
  }
}

/**
 * 已知缺口（第 107 批如实记录，未修）
 * ----------------------------------------------------------------------------
 * `views/DetectView.vue` 的顺序是"先 compressImage、再检查 UPLOAD_LIMIT"。
 * 于是这两类图会被拒且**没有出路**（用户只看到"图片过大"）：
 *   · 大于 5MB 的 **GIF**（压缩被跳过）；
 *   · 压缩失败（如 createImageBitmap 不支持该格式）的大图。
 * 这违反了本文件开头"绝不因为优化而让用户传不了图"的承诺 ——
 * 但那句话说的是"压缩环节不添麻烦"，而这里是**上限检查**的缺口，属于另一件事。
 * 要修的话有两条路：把 GIF 也走一次静态重编码，或在被拒时提示"请换一张图/用截图"。
 * 记录在此是为了让下一个人知道"这是已知的"，而不是重新发现一遍。
 */

/** File → dataURL（用于本地预览） */
export function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (event) => resolve(event.target?.result || '');
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
