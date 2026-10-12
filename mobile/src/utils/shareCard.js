/**
 * 生成"可分享的识别结果卡片"（第 177 批）
 * ============================================================================
 * ## 为什么是图片
 *
 * 第 176 批做的是**复制一段文字**。但农户之间真正好使的是**图** ——
 * 微信群里的对话方式就是发图：照片 + 病名 + 一句处理办法，一眼看完，
 * 对方（甚至农资店老板）不用点开链接、不用读长文。
 *
 * ## 怎么做的
 *
 * 用 Canvas 把这几样画进一张 750×1000 的图（微信里发图这个尺寸很清楚）：
 *   ① 顶部绿色标题条（App 名）
 *   ② 识别图（标注版优先，按 cover 裁切填满）
 *   ③ 病名（大字）+ 置信度
 *   ④ 防治/症状摘要（自动折行，最多几行，超出截断加省略号）
 *   ⑤ 底部一行提示（"由 XX 识别" + 用法提示）
 *
 * ## 两个关键点
 *
 * 1. **同源图片才能导出**：`/media/...` 走的是 Vite 代理（与页面同源），
 *    所以 `canvas.toDataURL()` 不会被"污染画布"的安全策略拦住。
 *    如果哪天图片换成跨域地址，必须让后端带上 CORS 头并把 `crossOrigin` 打开。
 * 2. **中文靠系统字体**：这里不像后端 PIL 画图那样需要指定字体文件 ——
 *    浏览器的 `ctx.font` 用系统字体，手机上一定有中文字体。
 */

/** 卡片尺寸（微信里发图这个比例很清楚） */
const CARD_WIDTH = 750;
const CARD_HEIGHT = 1000;
const IMAGE_HEIGHT = 560;
const BRAND = '#2e7d32';

/** 文字折行：按可用宽度切片（中文没有空格，只能逐字量） */
function wrapText(ctx, text, maxWidth, maxLines = 3) {
  const chars = String(text || '').replace(/\s+/g, ' ').trim();
  if (!chars) return [];
  const lines = [];
  let current = '';
  for (const char of chars) {
    const next = current + char;
    if (ctx.measureText(next).width > maxWidth && current) {
      lines.push(current);
      current = char;
      if (lines.length === maxLines) break;
    } else {
      current = next;
    }
  }
  if (lines.length < maxLines && current) lines.push(current);
  // 被截断了就补省略号
  if (lines.length === maxLines) {
    const joined = lines.join('').length;
    if (joined < chars.length) {
      let last = lines[maxLines - 1];
      while (last && ctx.measureText(`${last}…`).width > maxWidth) last = last.slice(0, -1);
      lines[maxLines - 1] = `${last}…`;
    }
  }
  return lines;
}

/** 加载图片（同源，不需要 crossOrigin） */
function loadImage(src) {
  return new Promise((resolve) => {
    if (!src) { resolve(null); return; }
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);   // 图挂了也要出卡片，只是那块留白
    img.src = src;
  });
}

/**
 * 画一张识别结果卡片
 *
 * @param {object} options
 *   `imageUrl`  识别图地址（同源，或已经被代理的相对路径）
 *   `diseaseName` 病害名（中文，已按当前语言取好）
 *   `confidenceText` 置信度文案（如 "99%"）
 *   `advice`    摘要正文（防治建议或主要症状）
 *   `appName`   底部署名
 *   `footer`    底部提示（如"拍照识别 · 科学防治"）
 * @returns {Promise<string>} data URL（image/jpeg）；失败时抛错由调用方兜底
 */
export async function renderResultCard({
  imageUrl = '',
  diseaseName = '',
  confidenceText = '',
  advice = '',
  appName = '',
  footer = '',
} = {}) {
  const canvas = document.createElement('canvas');
  canvas.width = CARD_WIDTH;
  canvas.height = CARD_HEIGHT;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('canvas_unavailable');

  // 底：白（微信里白底图更清楚）
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT);

  // ① 顶部标题条
  ctx.fillStyle = BRAND;
  ctx.fillRect(0, 0, CARD_WIDTH, 96);
  ctx.fillStyle = '#ffffff';
  ctx.font = 'bold 40px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif';
  ctx.textBaseline = 'middle';
  ctx.fillText(appName || '', 32, 48);

  // ② 识别图：cover 裁切填满
  const img = await loadImage(imageUrl);
  if (img) {
    const scale = Math.max(CARD_WIDTH / img.width, IMAGE_HEIGHT / img.height);
    const drawW = img.width * scale;
    const drawH = img.height * scale;
    const offsetX = (CARD_WIDTH - drawW) / 2;
    const offsetY = 96 + (IMAGE_HEIGHT - drawH) / 2;
    // 先铺一层浅灰，图片没盖满时不会露出白边
    ctx.fillStyle = '#f0f3f0';
    ctx.fillRect(0, 96, CARD_WIDTH, IMAGE_HEIGHT);
    // ⚠️ 必须裁剪：cover 缩放后 drawW/drawH 会超出这个区域，
    //    不裁的话照片会盖住下面的病名与建议（第一版就是这样）。
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 96, CARD_WIDTH, IMAGE_HEIGHT);
    ctx.clip();
    ctx.drawImage(img, offsetX, offsetY, drawW, drawH);
    ctx.restore();
  } else {
    ctx.fillStyle = '#f0f3f0';
    ctx.fillRect(0, 96, CARD_WIDTH, IMAGE_HEIGHT);
  }

  // ③ 病名 + 置信度
  let y = 96 + IMAGE_HEIGHT + 60;
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = '#1f2a1f';
  ctx.font = 'bold 54px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif';
  ctx.fillText(diseaseName || '', 40, y);

  if (confidenceText) {
    y += 52;
    ctx.fillStyle = BRAND;
    ctx.font = 'bold 34px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif';
    ctx.fillText(confidenceText, 40, y);
  }

  // ④ 摘要（最多 5 行）
  if (advice) {
    y += 52;
    ctx.fillStyle = '#3c4a3f';
    ctx.font = '30px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif';
    // 3 行封顶：再多会压到底部那行提示上（版面就这么高）
    const lines = wrapText(ctx, advice, CARD_WIDTH - 80, 3);
    for (const line of lines) {
      ctx.fillText(line, 40, y);
      y += 42;
    }
  }

  // ⑤ 底部一行提示
  ctx.fillStyle = '#9dada5';
  ctx.font = '26px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif';
  ctx.fillText(footer || '', 40, CARD_HEIGHT - 28);

  return canvas.toDataURL('image/jpeg', 0.92);
}

/**
 * 把 data URL 变成 File（用于 navigator.share 分享文件）
 *
 * Web Share API Level 2（分享文件）在安卓 Chrome 与 iOS 16.4+ 的 Safari 上可用；
 * 不支持时调用方退回"长按图片保存"的提示 —— 那条路在微信内置浏览器里也能走通。
 */
export function dataUrlToFile(dataUrl, filename = 'crop-result.jpg') {
  const [meta, base64] = String(dataUrl).split(',');
  const mime = /:(.*?);/.exec(meta)?.[1] || 'image/jpeg';
  const binary = atob(base64 || '');
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new File([bytes], filename, { type: mime });
}

export default renderResultCard;
