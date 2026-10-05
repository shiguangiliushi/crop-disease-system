/**
 * 识别报告 PDF 生成工具
 *
 * 作用：把一条病害识别记录渲染成 A4 版式的 PDF 报告并直接下载，
 *       替代原先“拼一段 HTML 再下载 .html 文件”的做法。
 *
 * 实现：先把报告渲染成离屏 DOM（中文、图标、表格排版由浏览器负责），
 *       再用 html2canvas 截图、jsPDF 分页写入 A4 文档。
 *       这样中文字体、复杂样式都能正确显示，且无需后端接口。
 *
 * 依赖：jspdf、html2canvas（在使用时动态加载，不增加首屏体积）
 *
 * 第 72 批：报告文案全部走 i18n（`t('reportPdf.*')`），并按当前语言取
 * 病害名/作物/症状/防治措施的英文内容，英文界面下导出的 PDF 不再是中文。
 */
// 第 75 批：原来这里还导入了 `locale`，但全文没有任何使用点（oxlint 报
// no-unused-vars）。取英文内容靠的是 `localizedField`，它自己会读当前语言，
// 不需要本模块再持有一份 locale。
import { t } from '@/i18n';
import { localizedField } from '@/utils/localized';

// A4 尺寸：96dpi 下宽度 794px，210mm x 297mm
const A4_WIDTH_PX = 794;
const PAGE_WIDTH_MM = 210;
const PAGE_HEIGHT_MM = 297;
// 页面底部留白，用于放置页码
const PAGE_BOTTOM_MARGIN_MM = 12;

// 防治方法分类（与后端 category 字段对应）→ i18n key
const CATEGORY_KEYS = {
  AGRICULTURAL: 'prevent.agricultural',
  CHEMICAL: 'prevent.chemical',
  ECOLOGICAL: 'prevent.ecological',
  PHYSICAL: 'prevent.physical',
  MONITORING: 'prevent.monitoring',
};

const categoryLabel = (categoryKey) =>
  CATEGORY_KEYS[categoryKey] ? t(CATEGORY_KEYS[categoryKey]) : t('reportPdf.generalAdvice');

const RENDER_SCALE = 2; // 截图倍率，越高越清晰、体积越大

const escapeHtml = (value) => {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};

const pad = (num, len = 2) => String(num).padStart(len, '0');

const formatDateTime = (value) => {
  if (!value) return t('reportPdf.unknown');
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
};

const formatDateStamp = (value = new Date()) => {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return formatDateStamp(new Date());
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}`;
};

/** 去掉文件名中的非法字符 */
const sanitizeFileName = (name) =>
  String(name || t('reportPdf.unknownDisease'))
    .replace(/[\\/:*?"<>|\r\n\t]/g, '_')
    .trim()
    .slice(0, 40) || t('reportPdf.unknownDisease');

/** 把图片地址转成 dataURL（避免跨域图片无法写入 canvas） */
const toDataUrl = async (url) => {
  if (!url) return null;
  if (url.startsWith('data:')) return url;
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  } catch (error) {
    console.warn(`[PDF] ${t('reportPdf.imageFailed')}`, url, error);
    return null;
  }
};

/** 归一化记录数据，兼容不同字段来源 */
export const normalizeRecord = (item = {}) => {
  const pest = item.pest_info || {};
  const confidenceValue = typeof item.confidence === 'number' ? item.confidence : null;

  const methods = Array.isArray(pest.prevention_methods)
    ? pest.prevention_methods
        .map((method) => ({
          category: categoryLabel(method?.category),
          // 第 72 批：英文界面下取 measure_en
          measure: localizedField(method, 'measure') || '',
        }))
        .filter((method) => method.measure && method.measure.trim())
    : [];

  const fallbackPrevention =
    pest.prevention || item.prevention || pest.prevention_measures || item.prevention_measures || '';

  return {
    id: item.id ?? '—',
    diseaseName:
      localizedField(pest, 'name') || item.disease_name || item.detection_result || t('reportPdf.unknownDisease'),
    cropType: localizedField(pest, 'crop_type') || t('reportPdf.noCrop'),
    englishIdentifier: pest.english_identifier || '—',
    confidenceText: confidenceValue === null ? 'N/A' : `${(confidenceValue * 100).toFixed(2)}%`,
    confidencePercent: confidenceValue === null ? 0 : Math.max(0, Math.min(100, confidenceValue * 100)),
    detectionTime: formatDateTime(item.timestamp || item.timestamp_formatted),
    symptoms:
      localizedField(pest, 'symptoms') ||
      localizedField(pest, 'description') ||
      item.symptoms ||
      item.description ||
      item.suggestion ||
      t('reportPdf.noSymptoms'),
    methods,
    fallbackPrevention,
  };
};

/** 生成报告 DOM 结构与样式 */
export const buildReportHtml = (record, images, logoUrl) => {
  const reportNo = `RPT-${pad(record.id, 4)}-${formatDateStamp()}`;
  const now = formatDateTime(new Date());

  const imageFigures = [];
  if (images.original) {
    imageFigures.push(`
      <figure class="rpt-figure">
        <img class="rpt-img" src="${images.original}" alt="${escapeHtml(t('reportPdf.altOriginal'))}" />
        <figcaption>${escapeHtml(t('reportPdf.figOriginal'))}</figcaption>
      </figure>`);
  }
  if (images.annotated) {
    imageFigures.push(`
      <figure class="rpt-figure">
        <img class="rpt-img" src="${images.annotated}" alt="${escapeHtml(t('reportPdf.altAnnotated'))}" />
        <figcaption>${escapeHtml(t('reportPdf.figAnnotated'))}</figcaption>
      </figure>`);
  }

  const preventionHtml = record.methods.length
    ? record.methods
        .map(
          (method, index) => `
        <div class="rpt-method">
          <div class="rpt-method-head">
            <span class="rpt-method-index">${index + 1}</span>
            <span class="rpt-method-category">${escapeHtml(method.category)}</span>
          </div>
          <p class="rpt-method-text">${escapeHtml(method.measure)}</p>
        </div>`,
        )
        .join('')
    : `<p class="rpt-paragraph">${escapeHtml(record.fallbackPrevention || t('reportPdf.fallbackPrevention'))}</p>`;

  return `
  <div class="rpt-root" style="width:${A4_WIDTH_PX}px;background:#ffffff;font-family:'Microsoft YaHei','PingFang SC','Hiragino Sans GB',SimSun,sans-serif;color:#22312b;">
    <style>
      .rpt-root { padding: 40px 40px 28px; box-sizing: border-box; font-size: 13px; line-height: 1.75; }
      .rpt-root * { box-sizing: border-box; }
      .rpt-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
      .rpt-logo { width: 54px; height: 54px; object-fit: contain; margin-right: 14px; }
      .rpt-head-main { display: flex; align-items: center; }
      .rpt-title { margin: 0; font-size: 25px; font-weight: 700; letter-spacing: 1px; color: #1a5f3e; }
      .rpt-title-en { margin: 4px 0 0; font-size: 11px; letter-spacing: 2px; color: #8b9c95; text-transform: uppercase; }
      .rpt-meta { text-align: right; font-size: 11.5px; color: #66756e; line-height: 1.9; }
      .rpt-meta b { color: #22312b; font-weight: 600; }
      .rpt-rule { height: 3px; margin: 16px 0 26px; background: linear-gradient(90deg,#1a5f3e 0%,#4caf50 42%,#e6efe9 42%,#e6efe9 100%); border-radius: 2px; }
      .rpt-section { margin-bottom: 24px; }
      .rpt-h2 { display: flex; align-items: center; margin: 0 0 14px; font-size: 15px; font-weight: 700; color: #1a5f3e; }
      .rpt-h2::before { content: ''; display: inline-block; width: 4px; height: 15px; margin-right: 9px; border-radius: 2px; background: #4caf50; }
      .rpt-h2::after { content: ''; flex: 1; height: 1px; margin-left: 12px; background: #e6efe9; }
      .rpt-table { width: 100%; border-collapse: collapse; border: 1px solid #dbe6e0; }
      .rpt-table th, .rpt-table td { border: 1px solid #dbe6e0; padding: 9px 12px; font-size: 12.5px; vertical-align: middle; }
      .rpt-table th { width: 108px; background: #f2f8f4; color: #40564c; font-weight: 600; text-align: left; }
      .rpt-table td { color: #22312b; }
      .rpt-highlight { font-weight: 700; color: #1a5f3e; }
      .rpt-bar { position: relative; height: 12px; margin-top: 6px; border-radius: 6px; background: #eef2f0; overflow: hidden; }
      .rpt-bar-inner { height: 100%; border-radius: 6px; background: linear-gradient(90deg,#4caf50,#2a7f53); }
      .rpt-images { display: flex; align-items: flex-start; gap: 18px; }
      .rpt-figure { margin: 0; flex: 1 1 0; border: 1px solid #dbe6e0; border-radius: 6px; overflow: hidden; background: #fbfdfc; }
      .rpt-img { display: block; width: 100%; height: auto; }
      .rpt-figure figcaption { padding: 8px 10px; border-top: 1px solid #e6efe9; background: #f2f8f4; font-size: 11.5px; color: #4a5c54; text-align: center; }
      .rpt-paragraph { margin: 0; font-size: 12.5px; line-height: 1.95; color: #33443c; text-align: justify; }
      .rpt-method { margin-bottom: 12px; padding: 11px 14px; border-left: 3px solid #4caf50; background: #f7fbf8; border-radius: 0 6px 6px 0; }
      .rpt-method:last-child { margin-bottom: 0; }
      .rpt-method-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
      .rpt-method-index { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: #2a7f53; color: #ffffff; font-size: 11px; font-weight: 700; }
      .rpt-method-category { font-size: 12.5px; font-weight: 700; color: #1a5f3e; }
      .rpt-method-text { margin: 0; font-size: 12.5px; line-height: 1.9; color: #33443c; text-align: justify; }
      .rpt-foot { margin-top: 26px; padding-top: 14px; border-top: 1px solid #e6efe9; font-size: 11px; color: #8b9c95; line-height: 1.8; }
      .rpt-foot-sign { display: flex; justify-content: space-between; margin-top: 6px; color: #66756e; }
    </style>

    <div class="rpt-head">
      <div class="rpt-head-main">
        ${logoUrl ? `<img class="rpt-logo" src="${logoUrl}" alt="${escapeHtml(t('reportPdf.altLogo'))}" />` : ''}
        <div>
          <h1 class="rpt-title">${escapeHtml(t('reportPdf.title'))}</h1>
          <p class="rpt-title-en">Crop Leaf Disease Recognition Report</p>
        </div>
      </div>
      <div class="rpt-meta">
        <div>${escapeHtml(t('reportPdf.reportNo'))}<b>${reportNo}</b></div>
        <div>${escapeHtml(t('reportPdf.generatedAt'))}<b>${now}</b></div>
      </div>
    </div>

    <div class="rpt-rule"></div>

    <div class="rpt-section">
      <h2 class="rpt-h2">${escapeHtml(t('reportPdf.secOverview'))}</h2>
      <table class="rpt-table">
        <tr>
          <th>${escapeHtml(t('reportPdf.colDisease'))}</th>
          <td class="rpt-highlight">${escapeHtml(record.diseaseName)}</td>
          <th>${escapeHtml(t('reportPdf.colCrop'))}</th>
          <td>${escapeHtml(record.cropType)}</td>
        </tr>
        <tr>
          <th>${escapeHtml(t('reportPdf.colConfidence'))}</th>
          <td colspan="3">
            <span class="rpt-highlight">${record.confidenceText}</span>
            <div class="rpt-bar"><div class="rpt-bar-inner" style="width:${record.confidencePercent}%"></div></div>
          </td>
        </tr>
        <tr>
          <th>${escapeHtml(t('reportPdf.colDetectedAt'))}</th>
          <td>${escapeHtml(record.detectionTime)}</td>
          <th>${escapeHtml(t('reportPdf.colRecordId'))}</th>
          <td>#${escapeHtml(record.id)}</td>
        </tr>
        <tr>
          <th>${escapeHtml(t('reportPdf.colIdentifier'))}</th>
          <td colspan="3">${escapeHtml(record.englishIdentifier)}</td>
        </tr>
      </table>
    </div>

    ${
      imageFigures.length
        ? `<div class="rpt-section">
      <h2 class="rpt-h2">${escapeHtml(t('reportPdf.secImages'))}</h2>
      <div class="rpt-images">${imageFigures.join('')}</div>
    </div>`
        : ''
    }

    <div class="rpt-section">
      <h2 class="rpt-h2">${escapeHtml(t('reportPdf.secSymptoms'))}</h2>
      <p class="rpt-paragraph">${escapeHtml(record.symptoms)}</p>
    </div>

    <div class="rpt-section">
      <h2 class="rpt-h2">${escapeHtml(t('reportPdf.secPrevention'))}</h2>
      ${preventionHtml}
    </div>

    <div class="rpt-foot">
      <div>${escapeHtml(t('reportPdf.disclaimer'))}</div>
      <div class="rpt-foot-sign">
        <span>${escapeHtml(t('reportPdf.generatedBy'))}</span>
        <span>${escapeHtml(t('reportPdf.generatedAt'))}${now}</span>
      </div>
    </div>
  </div>`;
};

/** 等待容器内图片与字体就绪 */
const waitForAssets = async (host) => {
  const images = Array.from(host.querySelectorAll('img'));
  await Promise.all(
    images.map((img) =>
      img.complete && img.naturalWidth > 0
        ? Promise.resolve()
        : new Promise((resolve) => {
            img.onload = () => resolve();
            img.onerror = () => resolve();
            setTimeout(resolve, 8000);
          }),
    ),
  );
  if (document.fonts && document.fonts.ready) {
    try {
      await document.fonts.ready;
    } catch {
      /* 忽略字体等待失败 */
    }
  }
};

/** 判断某一行是否为空白行（用于智能分页，避免把文字截断） */
const createBlankRowDetector = (canvas) => {
  const ctx = canvas.getContext('2d');
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const step = Math.max(1, Math.floor(canvas.width / 160));

  return (y) => {
    const rowStart = y * canvas.width * 4;
    for (let x = 0; x < canvas.width; x += step) {
      const index = rowStart + x * 4;
      if (data[index] < 247 || data[index + 1] < 247 || data[index + 2] < 247) {
        return false;
      }
    }
    return true;
  };
};

/** 把长图按 A4 高度切分为多页，并在空白行处断开 */
export const sliceCanvasIntoPages = (canvas) => {
  const pageHeightPx = Math.floor(canvas.width * ((PAGE_HEIGHT_MM - PAGE_BOTTOM_MARGIN_MM) / PAGE_WIDTH_MM));
  const minSlicePx = Math.floor(pageHeightPx * 0.55);
  const isBlankRow = createBlankRowDetector(canvas);

  const slices = [];
  let start = 0;

  while (start < canvas.height) {
    let end = Math.min(start + pageHeightPx, canvas.height);

    if (end < canvas.height) {
      // 向上寻找最近的空白行作为分页位置
      for (let y = end; y > start + minSlicePx; y -= 1) {
        if (isBlankRow(y)) {
          end = y;
          break;
        }
      }
    }

    slices.push([start, end]);
    start = end;
  }

  return slices;
};

/**
 * 生成并下载识别报告 PDF
 * @param {object} item 历史记录对象
 * @param {object} [options]
 * @param {string} [options.imageUrl] 原始图片完整地址
 * @param {string} [options.annotatedImageUrl] 标注图片完整地址
 * @param {string} [options.logoUrl] 报告页眉 Logo 地址
 * @returns {Promise<string>} 生成的文件名
 */
export async function downloadDetectionReportPdf(item, options = {}) {
  if (!item) throw new Error(t('reportPdf.missingRecord'));

  const record = normalizeRecord(item);

  // 图片与依赖并行加载
  const [originalImage, annotatedImage, jsPdfModule, html2canvasModule] = await Promise.all([
    toDataUrl(options.imageUrl),
    toDataUrl(options.annotatedImageUrl),
    import('jspdf'),
    import('html2canvas'),
  ]);

  const { jsPDF } = jsPdfModule;
  const html2canvas = html2canvasModule.default || html2canvasModule;

  const host = document.createElement('div');
  host.setAttribute('data-pdf-report-host', 'true');
  host.style.cssText = `position:absolute;left:-10000px;top:0;width:${A4_WIDTH_PX}px;background:#ffffff;`;
  host.innerHTML = buildReportHtml(
    record,
    { original: originalImage, annotated: annotatedImage },
    options.logoUrl || '',
  );
  document.body.appendChild(host);

  try {
    await waitForAssets(host);

    const canvas = await html2canvas(host.firstElementChild, {
      scale: RENDER_SCALE,
      backgroundColor: '#ffffff',
      useCORS: true,
      logging: false,
      width: A4_WIDTH_PX,
      windowWidth: A4_WIDTH_PX,
    });

    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4', compress: true });
    const slices = sliceCanvasIntoPages(canvas);
    const sliceCanvas = document.createElement('canvas');
    const sliceCtx = sliceCanvas.getContext('2d');

    slices.forEach(([start, end], index) => {
      const sliceHeight = end - start;
      sliceCanvas.width = canvas.width;
      sliceCanvas.height = sliceHeight;
      sliceCtx.fillStyle = '#ffffff';
      sliceCtx.fillRect(0, 0, sliceCanvas.width, sliceHeight);
      sliceCtx.drawImage(canvas, 0, start, canvas.width, sliceHeight, 0, 0, canvas.width, sliceHeight);

      const imageData = sliceCanvas.toDataURL('image/jpeg', 0.96);
      const renderHeightMm = (sliceHeight * PAGE_WIDTH_MM) / canvas.width;

      if (index > 0) pdf.addPage();
      pdf.addImage(imageData, 'JPEG', 0, 0, PAGE_WIDTH_MM, renderHeightMm, undefined, 'FAST');
      pdf.setFontSize(9);
      pdf.setTextColor(150, 160, 155);
      pdf.text(`${index + 1} / ${slices.length}`, PAGE_WIDTH_MM - 8, PAGE_HEIGHT_MM - 5, { align: 'right' });
    });

    const fileName = `${t('reportPdf.fileName')}_${sanitizeFileName(record.diseaseName)}_${formatDateStamp()}.pdf`;
    pdf.save(fileName);
    return fileName;
  } finally {
    host.remove();
  }
}

export default downloadDetectionReportPdf;
