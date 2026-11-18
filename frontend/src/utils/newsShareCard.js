/**
 * 行业动态分享图（第 401 批 · P1）
 * ------------------------------------------------------------------
 * 读者看到一条值得转发的行业动态时，通常直接截屏 —— 截出来的是"半张页面"，
 * 系统名、来源、日期都不完整。这里用 Canvas 画一张固定尺寸的分享卡：
 *
 *    750 × 1000（3:4，微信/朋友圈与多数聊天工具的图片预览都不裁边）
 *
 * 几个刻意的取舍：
 *   · **纯 Canvas 2D**，不引第三方截图库：本页只需要"标题 + 摘要 + 封面 + 来源"，
 *     引 html2canvas（项目里已有）反而会把整页样式、滚动位置带进来，产出不稳定；
 *   · **只画同源图片**：跨域图片画到 canvas 上会"污染"画布，`toBlob()` 直接抛
 *     SecurityError —— 整张分享图就失败了。宁可留白也不能让生成失败；
 *   · 图片加载失败 / 超时（6 秒）同样留白：新闻正文才是主体，封面只是装饰；
 *   · 字体用系统中文字体栈（项目没有打包中文字体），避免分享图里出现方框。
 *
 * 导出：
 *   · `buildNewsShareCard(options) → Promise<Blob>` 画图并返回 PNG Blob；
 *   · `downloadNewsShareCard(blob, filename)` 用 `URL.createObjectURL` 触发下载。
 */

const CARD_WIDTH = 750;
const CARD_HEIGHT = 1000;
const PADDING_X = 48;
const CONTENT_WIDTH = CARD_WIDTH - PADDING_X * 2;

const COLORS = {
  brandStart: '#3d9a68',
  brandEnd: '#1f6343',
  ink900: '#14231c',
  ink700: '#3a4d43',
  ink500: '#78897f',
  ink300: '#c6d2cb',
  ink100: '#f1f6f3',
  border: '#e2ebe5',
  white: '#ffffff',
};

const FONT_STACK = '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif';

/** 圆角矩形路径（Canvas 的 roundRect 在旧浏览器上没有，这里手画一份） */
function roundRectPath(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + width - r, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + r);
  ctx.lineTo(x + width, y + height - r);
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  ctx.lineTo(x + r, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

/**
 * 是否是可以安全画进 canvas 的图片地址
 *
 * `data:` 不会污染画布；相对路径与同源绝对地址安全；跨站地址一律拒绝
 * （与后端 `image_url` 是绝对地址无关 —— 开发环境页面在 5173、媒体在 8000，
 *  调用方应传入同源的 `/media/...` 相对地址，见 NewsDetailView）。
 */
function isDrawableImageUrl(url) {
  if (!url || typeof url !== 'string') return false;
  if (url.startsWith('data:image/')) return true;
  if (url.startsWith('blob:')) return true;
  if (typeof window === 'undefined') return false;
  try {
    return new URL(url, window.location.href).origin === window.location.origin;
  } catch {
    return false;
  }
}

/** 加载一张图片；失败或超时都 resolve(null)（分享图不能因为封面挂掉） */
function loadImage(url) {
  return new Promise((resolve) => {
    const image = new Image();
    let settled = false;
    let timer = null;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      image.onload = null;
      image.onerror = null;
      resolve(value);
    };
    image.onload = () => finish(image);
    image.onerror = () => finish(null);
    timer = setTimeout(() => finish(null), 6000);
    image.src = url;
  });
}

/** 按 token（中文按字、英文按词）折行，避免把英文单词从中间切断 */
function splitTokens(text) {
  return String(text || '').match(
    /[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]|[^\s\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]+|\s+/g,
  ) || [];
}

/** 折成若干行；单个超长 token（URL 等）退化成逐字折行 */
function wrapAllLines(ctx, text, maxWidth) {
  const tokens = splitTokens(text);
  const lines = [];
  let current = '';

  const flush = () => {
    if (current.trim()) lines.push(current.trimEnd());
    current = '';
  };

  for (const token of tokens) {
    if (!current) {
      // 行首空白直接丢掉，否则每行开头会多一段缩进
      current = token.trimStart();
      if (!current) continue;
    } else {
      current += token;
    }
    if (ctx.measureText(current).width <= maxWidth) continue;

    // 超宽了：回退到上一个 token 再断行；若单个 token 本身就超宽则逐字拆
    const previous = token === current ? '' : current.slice(0, current.length - token.length);
    if (previous.trim()) {
      lines.push(previous.trimEnd());
      current = token.trimStart();
      if (ctx.measureText(current).width <= maxWidth) continue;
    }
    let piece = '';
    for (const char of Array.from(current)) {
      if (piece && ctx.measureText(piece + char).width > maxWidth) {
        lines.push(piece);
        piece = char;
      } else {
        piece += char;
      }
    }
    current = piece;
  }
  flush();
  return lines;
}

/** 最多 maxLines 行，超出时最后一行补省略号（删到放得下为止） */
function wrapLines(ctx, text, maxWidth, maxLines) {
  const lines = wrapAllLines(ctx, text, maxWidth);
  if (lines.length <= maxLines) return lines;

  const clipped = lines.slice(0, maxLines);
  let last = clipped[maxLines - 1];
  while (last && ctx.measureText(`${last}…`).width > maxWidth) {
    last = last.slice(0, -1);
  }
  clipped[maxLines - 1] = `${last}…`;
  return clipped;
}

/** 单行超宽时截断加省略号 */
function truncateLine(ctx, text, maxWidth) {
  let value = String(text || '');
  if (ctx.measureText(value).width <= maxWidth) return value;
  while (value && ctx.measureText(`${value}…`).width > maxWidth) {
    value = value.slice(0, -1);
  }
  return `${value}…`;
}

/** 等比缩放 + 居中裁切（cover），并裁成圆角 */
function drawCover(ctx, image, x, y, width, height, radius) {
  const naturalWidth = image.naturalWidth || image.width || 1;
  const naturalHeight = image.naturalHeight || image.height || 1;
  const scale = Math.max(width / naturalWidth, height / naturalHeight);
  const sourceWidth = width / scale;
  const sourceHeight = height / scale;
  const sourceX = (naturalWidth - sourceWidth) / 2;
  const sourceY = (naturalHeight - sourceHeight) / 2;

  ctx.save();
  roundRectPath(ctx, x, y, width, height, radius);
  ctx.clip();
  ctx.drawImage(image, sourceX, sourceY, sourceWidth, sourceHeight, x, y, width, height);
  ctx.restore();
}

/** 画一个"图片占位"（封面加载失败/缺失时的留白，纯几何图形，无文字，天然语言无关） */
function drawCoverPlaceholder(ctx, x, y, width, height, radius) {
  ctx.save();
  roundRectPath(ctx, x, y, width, height, radius);
  ctx.fillStyle = COLORS.ink100;
  ctx.fill();
  ctx.strokeStyle = COLORS.border;
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.clip();

  // 简化的"山与太阳"图标
  const centerX = x + width / 2;
  const centerY = y + height / 2;
  ctx.strokeStyle = COLORS.ink300;
  ctx.lineWidth = 6;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.arc(centerX + 46, centerY - 46, 18, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(centerX - 92, centerY + 58);
  ctx.lineTo(centerX - 18, centerY - 28);
  ctx.lineTo(centerX + 26, centerY + 16);
  ctx.lineTo(centerX + 62, centerY - 22);
  ctx.lineTo(centerX + 118, centerY + 58);
  ctx.stroke();
  ctx.restore();
}

/** 把 canvas 转成 Blob；没有 toBlob 的旧浏览器用 toDataURL 兜底 */
function canvasToBlob(canvas) {
  return new Promise((resolve, reject) => {
    try {
      if (typeof canvas.toBlob === 'function') {
        canvas.toBlob((blob) => {
          if (blob) resolve(blob);
          else reject(new Error('分享图生成失败：空 Blob'));
        }, 'image/png');
        return;
      }
      const dataUrl = canvas.toDataURL('image/png');
      resolve(dataUrlToBlob(dataUrl));
    } catch (error) {
      // 画布被污染（跨域图片）时 toBlob/toDataURL 会抛 SecurityError
      reject(error);
    }
  });
}

/** dataURL → Blob（旧浏览器兜底路径） */
function dataUrlToBlob(dataUrl) {
  const [header, base64 = ''] = String(dataUrl).split(',');
  const mime = /data:([^;]+)/.exec(header || '')?.[1] || 'image/png';
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new Blob([bytes], { type: mime });
}

/**
 * 生成行业动态分享图
 *
 * @param {object} options
 * @param {string} [options.title]     新闻标题（自动折行，最多 3 行）
 * @param {string} [options.summary]   摘要纯文本（最多 3 行）
 * @param {string} [options.source]    来源
 * @param {string} [options.dateText]  日期（调用方已按当前语言格式化）
 * @param {string} [options.coverUrl]  封面地址（只接受同源；失败留白）
 * @param {string} [options.brandName] 品牌条上的系统名
 * @param {string} [options.footer]    底部提示语
 * @returns {Promise<Blob>} PNG Blob
 */
export async function buildNewsShareCard(options = {}) {
  if (typeof document === 'undefined') {
    throw new Error('分享图只能在浏览器中生成');
  }

  const {
    title = '',
    summary = '',
    source = '',
    dateText = '',
    coverUrl = '',
    brandName = '',
    footer = '',
  } = options || {};

  const canvas = document.createElement('canvas');
  canvas.width = CARD_WIDTH;
  canvas.height = CARD_HEIGHT;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('当前浏览器不支持 Canvas 2D，无法生成分享图');

  // ---- 背景 ----
  ctx.fillStyle = COLORS.white;
  ctx.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT);

  // ---- 品牌条 ----
  const brandGradient = ctx.createLinearGradient(0, 0, CARD_WIDTH, 160);
  brandGradient.addColorStop(0, COLORS.brandStart);
  brandGradient.addColorStop(1, COLORS.brandEnd);
  ctx.fillStyle = brandGradient;
  ctx.fillRect(0, 0, CARD_WIDTH, 160);

  // 两个半透明圆做装饰，避免顶部是一整条纯色
  ctx.save();
  ctx.globalAlpha = 0.12;
  ctx.fillStyle = COLORS.white;
  ctx.beginPath();
  ctx.arc(640, 20, 120, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(730, 150, 86, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();

  // 系统名：超宽时自动缩小字号（英文系统名比中文长得多）
  const brandText = String(brandName || '').trim();
  if (brandText) {
    let fontSize = 36;
    do {
      ctx.font = `700 ${fontSize}px ${FONT_STACK}`;
      if (ctx.measureText(brandText).width <= CONTENT_WIDTH) break;
      fontSize -= 2;
    } while (fontSize > 18);
    ctx.fillStyle = COLORS.white;
    ctx.textBaseline = 'middle';
    ctx.fillText(brandText, PADDING_X, 82);
  }

  // ---- 封面 ----
  const coverX = PADDING_X;
  const coverY = 190;
  const coverWidth = CONTENT_WIDTH;
  const coverHeight = 340;
  let coverDrawn = false;
  if (isDrawableImageUrl(coverUrl)) {
    const image = await loadImage(coverUrl);
    if (image) {
      try {
        drawCover(ctx, image, coverX, coverY, coverWidth, coverHeight, 24);
        coverDrawn = true;
      } catch (error) {
        console.warn('分享图：封面绘制失败，改为留白', error);
      }
    }
  }
  if (!coverDrawn) {
    drawCoverPlaceholder(ctx, coverX, coverY, coverWidth, coverHeight, 24);
  }

  // ---- 标题 ----
  ctx.textBaseline = 'top';
  ctx.fillStyle = COLORS.ink900;
  ctx.font = `700 40px ${FONT_STACK}`;
  const titleLines = wrapLines(ctx, title, CONTENT_WIDTH, 3);
  let cursorY = 566;
  titleLines.forEach((line) => {
    ctx.fillText(line, PADDING_X, cursorY);
    cursorY += 54;
  });

  // ---- 摘要 ----
  // 先设好字号再折行：wrapLines 依赖 ctx.font 的 measureText，用标题的 40px
  // 去量 24px 的摘要会把每行都量得太短（行数虚高、留白变大）。
  ctx.font = `400 24px ${FONT_STACK}`;
  const summaryLines = wrapLines(
    ctx,
    summary,
    CONTENT_WIDTH,
    3,
  );
  if (summaryLines.length) {
    cursorY += 22;
    ctx.fillStyle = COLORS.ink500;
    summaryLines.forEach((line) => {
      ctx.fillText(line, PADDING_X, cursorY);
      cursorY += 36;
    });
  }

  // ---- 分隔线 + 来源 / 日期 ----
  const metaY = 892;
  ctx.strokeStyle = COLORS.border;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(PADDING_X, metaY);
  ctx.lineTo(CARD_WIDTH - PADDING_X, metaY);
  ctx.stroke();

  ctx.textBaseline = 'middle';
  const metaTextY = metaY + 28;
  if (source) {
    ctx.fillStyle = COLORS.ink700;
    ctx.font = `600 22px ${FONT_STACK}`;
    ctx.fillText(truncateLine(ctx, source, 360), PADDING_X, metaTextY);
  }
  if (dateText) {
    ctx.fillStyle = COLORS.ink500;
    ctx.font = `400 20px ${FONT_STACK}`;
    ctx.textAlign = 'right';
    ctx.fillText(dateText, CARD_WIDTH - PADDING_X, metaTextY);
    ctx.textAlign = 'left';
  }

  // ---- 底部提示 ----
  if (footer) {
    ctx.fillStyle = COLORS.ink300;
    ctx.font = `500 20px ${FONT_STACK}`;
    ctx.textAlign = 'center';
    ctx.fillText(truncateLine(ctx, footer, CONTENT_WIDTH), CARD_WIDTH / 2, 960);
    ctx.textAlign = 'left';
  }

  return canvasToBlob(canvas);
}

/**
 * 触发浏览器下载（文件名形如 `news-12.png`）
 *
 * @param {Blob} blob `buildNewsShareCard` 的返回值
 * @param {string} filename
 * @returns {boolean} 是否成功发起下载
 */
export function downloadNewsShareCard(blob, filename = 'news.png') {
  if (!blob || typeof document === 'undefined' || typeof URL === 'undefined') return false;
  let objectUrl = '';
  try {
    objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    link.remove();
    return true;
  } catch (error) {
    console.warn('分享图下载失败:', error);
    return false;
  } finally {
    // 立刻 revoke 会让部分浏览器下载到空文件，延迟释放
    if (objectUrl) {
      setTimeout(() => {
        try {
          URL.revokeObjectURL(objectUrl);
        } catch {
          /* 忽略：页面卸载后 revoke 失败无影响 */
        }
      }, 10000);
    }
  }
}

export default {
  buildNewsShareCard,
  downloadNewsShareCard,
};
