/**
 * 移动端「分享图片卡片」验收（第 177 批）
 * ============================================================================
 * 农户之间是"发图说话"：照片 + 病名 + 处理办法一张图说完，比复制一段文字更直观
 * （第 176 批做的是复制文字，这一批做图）。
 *
 * 本脚本验证：
 *   ① 结果页有「生成分享图」按钮
 *   ② 点它之后弹出预览，里面是一张 **data:image** 的图（不是空壳）
 *   ③ 图的真实尺寸是 750×1000（微信里发图这个尺寸很清楚）
 *   ④ 图**不是空白**：把它画进另一个 canvas 抽样，非白像素要占相当比例
 *   ⑤ 图上确实画了识别图（左侧/上部的颜色分布不是纯色块）
 *   ⑥ 关掉弹窗后可以再次生成（不残留状态）｜ 全程无 JS 报错
 *
 * 用法：node scripts/verify-share-card.mjs
 */
import { chromium } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';
import { clearThrottle, runDjango } from './helpers.mjs';

const UI = 'http://127.0.0.1:5174';
const SAMPLE = path.resolve(process.cwd(), '..', 'backend', 'pests', 'Apple___Apple_scab14.jpg');
const USER = 'zz_mobile_sharecard';
const PASS = 'ZzMobile!2026';

const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models import DetectionHistory',
  `u, _ = get_user_model().objects.get_or_create(username='${USER}', defaults={'role': 'USER'})`,
  `u.set_password('${PASS}')`,
  'u.is_active = True; u.is_deleted = False; u.save()',
  'DetectionHistory.objects.filter(user=u).delete()',
  "print('ok')",
]);

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true,
  locale: 'zh-CN',
});
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error).slice(0, 200)));

// 登录 → 识别一张真图 → 结果页
await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
await page.locator('input').nth(0).fill(USER);
await page.locator('input').nth(1).fill(PASS);
await page.getByRole('button', { name: /登录/ }).first().click();
await page.waitForTimeout(3000);
await page.goto(`${UI}/detect`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
await page.locator('input[type=file]').nth(1).setInputFiles(SAMPLE);
await page.waitForTimeout(1200);
await page.getByRole('button', { name: /开始识别|识别/ }).first().click();
await page.waitForURL((url) => url.pathname.startsWith('/result'), { timeout: 90_000 });
await page.waitForTimeout(3000);

// ---------------------------------------------------------------------------
// ① 按钮
// ---------------------------------------------------------------------------
const makeBtn = page.getByRole('button', { name: /生成分享图/ });
check('结果页有「生成分享图」按钮', (await makeBtn.count()) > 0, '');

// ---------------------------------------------------------------------------
// ② 生成 → 预览
// ---------------------------------------------------------------------------
await makeBtn.first().click();
await page.waitForSelector('.share-card-img', { timeout: 30_000 });
await page.waitForTimeout(1200);
const imgInfo = await page.evaluate(() => {
  const img = document.querySelector('.share-card-img');
  return {
    src: img?.getAttribute('src') || '',
    width: img?.naturalWidth || 0,
    height: img?.naturalHeight || 0,
  };
});
check('弹窗里出现一张图片', imgInfo.src.startsWith('data:image'), imgInfo.src.slice(0, 30));
check('图是生成出来的（data:image/jpeg，不是占位图）',
  imgInfo.src.startsWith('data:image/jpeg'), `长度 ${imgInfo.src.length}`);
check('尺寸是 750×1000', imgInfo.width === 750 && imgInfo.height === 1000,
  `${imgInfo.width}×${imgInfo.height}`);
check('图不是空壳（体积够大）', imgInfo.src.length > 20_000, `${Math.round(imgInfo.src.length / 1024)} KB（base64）`);

// ---------------------------------------------------------------------------
// ③ 图不是空白：抽样统计非白像素
// ---------------------------------------------------------------------------
const pixels = await page.evaluate(async (src) => {
  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = reject;
    img.src = src;
  });
  const canvas = document.createElement('canvas');
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0);
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
  let nonWhite = 0;
  let colored = 0;
  let total = 0;
  for (let i = 0; i < data.length; i += 4 * 37) {   // 跳着采样，够用且快
    const [r, g, b] = [data[i], data[i + 1], data[i + 2]];
    total += 1;
    if (r < 240 || g < 240 || b < 240) nonWhite += 1;
    // "彩色"：三通道差异明显（照片区域会是彩色的，纯文字/色块不会）
    if (Math.max(r, g, b) - Math.min(r, g, b) > 24) colored += 1;
  }
  return {
    total,
    nonWhiteRatio: +(nonWhite / total).toFixed(3),
    coloredRatio: +(colored / total).toFixed(3),
  };
}, imgInfo.src);
check('卡片上确实画了东西（非白像素占比 > 20%）', pixels.nonWhiteRatio > 0.2,
  `nonWhite=${pixels.nonWhiteRatio}`);
check('卡片里包含识别照片（彩色像素占比 > 15%）', pixels.coloredRatio > 0.15,
  `colored=${pixels.coloredRatio}`);

// ---- 定点检查：整张图的"平均非白"看不出"照片溢出盖住文字"这类版面错误 ----
const zones = await page.evaluate(async (src) => {
  const img = new Image();
  await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = reject; img.src = src; });
  const canvas = document.createElement('canvas');
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0);
  const at = (x, y) => {
    const d = ctx.getImageData(x, y, 1, 1).data;
    return [d[0], d[1], d[2]];
  };
  // 照片区域下方那一条（病名所在行）应当**基本是白的**（照片不该溢到这里）
  // 左侧 0~35px 是纯留白（正文从 x=40 开始）：照片若溢出，这一列会变彩色。
  // 第一版我采样的是 y=700 整行 —— 那一行**正好压在病名大字上**，自然非白 ✗。
  let bleed = 0;
  for (let y = 670; y < 990; y += 8) {
    const [r, g, b] = at(10, y);
    if (r < 240 || g < 240 || b < 240) bleed += 1;
  }
  return {
    topLeft: at(10, 10),                    // 顶部标题条应为品牌绿
    belowPhotoNonWhite: bleed,
    footerZone: at(375, 985),               // 底部提示那一带
  };
}, imgInfo.src);
// JPEG 是有损的：颜色会有 ±2 的偏差，卡精确值会误报（第一版就误报了）
const isBrandGreen = (rgb) => Math.abs(rgb[0] - 46) <= 3 && Math.abs(rgb[1] - 125) <= 3 && Math.abs(rgb[2] - 50) <= 3;
check('顶部标题条是品牌绿（容差 ±3，JPEG 有损）', isBrandGreen(zones.topLeft),
  `rgb(${zones.topLeft.join(',')})`);
check('照片没有溢出到文字区（病名那一行基本是白的）',
  zones.belowPhotoNonWhite <= 2, `${zones.belowPhotoNonWhite} 个非白采样点`);

await page.screenshot({ path: 'dsh-shots/share-card-preview.png' });

// ---------------------------------------------------------------------------
// ④ 关掉再生成一次（不残留状态）
// ---------------------------------------------------------------------------
// ⚠️ Vant 的 Dialog 不响应 Escape（我按 Element Plus 的习惯写的，白等一轮）——
// 它是 close-on-click-overlay，点遮罩关闭。
await page.locator('.van-overlay').first().click({ position: { x: 5, y: 5 } });
await page.waitForTimeout(1200);
check('点遮罩能关掉预览', !(await page.locator('.share-card-img').first().isVisible().catch(() => false)), '');
await makeBtn.first().click();
await page.waitForTimeout(2500);
check('关掉后可以再次生成',
  await page.locator('.share-card-img').first().isVisible().catch(() => false), '');

check('全程无 JS 报错', errors.length === 0, errors.slice(0, 2).join(' | '));

await browser.close();

try {
  runDjango([
    'from django.contrib.auth import get_user_model',
    'from api.models import DetectionHistory',
    `u = get_user_model().objects.filter(username='${USER}').first()`,
    'if u:',
    '    DetectionHistory.objects.filter(user=u).delete()',
    '    u.delete()',
    "print('cleaned')",
  ]);
} catch (error) {
  console.warn('  清理失败（忽略）:', String(error).slice(0, 100));
}

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
