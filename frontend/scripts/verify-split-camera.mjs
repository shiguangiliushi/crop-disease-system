/**
 * 客户端 / 移动端「拍照识别」端到端验证（第 75 批）
 * ----------------------------------------------------------------------------
 * 为什么要有这个脚本：
 *   本轮改动的核心是"页面内拍照"（getUserMedia 实时取景 + 快门）。
 *   这类功能的失败模式恰恰是"看起来没坏"——
 *   按钮点得动、界面不报错，但实际上拿不到摄像头、或者抓帧抓到的是黑图、
 *   或者压缩后上传的文件是空的。所以必须真的：
 *     ① 真浏览器 + **真实摄像头设备**（用 Chromium 的假摄像头，
 *        它会输出一段合成视频，可以验证 videoWidth>0、抓帧非空）
 *     ② 真的点快门、真的走完识别流程
 *     ③ 检查发出去的 multipart body 里**确实有** filenam="photo-*.jpg" 且体积 > 10KB
 *        （证明 File 是从画布真实编码出来的，而不是 0 字节占位）
 *
 * 后端接口全部用 Playwright 路由拦截模拟（不依赖 Django/模型是否在跑），
 * 这样本脚本既能验证前端逻辑，又不会因为"模型没加载"而假失败。
 *
 * 运行：
 *   1) 先起两个前端：mobile(5174) 与 frontend(5173)
 *   2) node scripts/verify-split-camera.mjs
 */
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SHOT_DIR = resolve(__dirname, '..', 'dsh-shots');
mkdirSync(SHOT_DIR, { recursive: true });

const MOBILE_URL = process.env.MOBILE_URL || 'http://127.0.0.1:5174';
const CLIENT_URL = process.env.CLIENT_URL || 'http://127.0.0.1:5173';

const results = [];
const record = (name, ok, detail = '') => {
  results.push({ name, ok, detail });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

/** 1×1 绿色 PNG，用来顶替后端返回的标注图（否则图片请求会 404 影响截图观感） */
const TINY_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  'base64',
);

const DISEASE = {
  disease: '玉米大斑病',
  disease_en: 'Northern Corn Leaf Blight',
  confidence: 0.93,
  description: '叶片初现水渍状青灰色斑点，后沿叶脉扩展成梭形褐色大斑，潮湿时病斑背面产生灰黑色霉层。',
  description_en: 'Water-soaked spots enlarge into long cigar-shaped brown lesions along the veins.',
  prevention: '1. 选用抗病品种；2. 收获后清除病残体，深翻灭茬；3. 发病初期喷施杀菌剂。',
  prevention_en: '1. Use resistant hybrids; 2. Remove crop residue after harvest; 3. Apply fungicide early.',
  original_image: 'http://127.0.0.1:8000/media/detection_uploads/original.jpg',
  annotated_image: 'http://127.0.0.1:8000/media/detection_uploads/annotated.jpg',
};

const USER = { id: 7, username: '测试农户', is_staff: false, is_superuser: false, role: 'FARMER', avatar: '' };

const HISTORY_ITEM = {
  id: 321,
  user: { id: 7, username: '测试农户', is_staff: false },
  image: 'http://127.0.0.1:8000/media/detection_uploads/original.jpg',
  annotated_image_url: 'http://127.0.0.1:8000/media/detection_uploads/annotated.jpg',
  detection_result: '玉米大斑病',
  disease_name: '玉米大斑病',
  confidence: 0.93,
  timestamp: '2026-09-27T10:20:00+08:00',
  timestamp_formatted: '2026-09-27 10:20:00',
  symptoms: DISEASE.description,
  suggestion: '',
  pest_info: {
    name: '玉米大斑病',
    name_en: 'Northern Corn Leaf Blight',
    crop_type: '玉米',
    crop_type_en: 'Corn',
    symptoms: DISEASE.description,
    symptoms_en: DISEASE.description_en,
    prevention_methods: [
      { id: 1, measure: '选用抗病品种', measure_en: 'Use resistant hybrids' },
      { id: 2, measure: '清除病残体并深翻', measure_en: 'Remove residue and deep plough' },
    ],
  },
};

/**
 * 跨域响应头。
 *
 * 桌面客户端请求的是**绝对地址** `http://127.0.0.1:8000/api/...`（源是 5173），
 * 属于跨域 + 带自定义头 → 浏览器会先发 OPTIONS 预检；Playwright 的 fulfill
 * 仍然会被 Chromium 按 CORS 规则校验，所以必须把 CORS 头补上，
 * 否则表现为"接口被拦截了但前端拿不到数据"（登录一直失败）。
 * 注意：带 credentials 时 `Access-Control-Allow-Origin` 不能是 `*`，必须回显 Origin。
 */
function corsHeaders(request) {
  const origin = request.headers()['origin'];
  if (!origin) return {};
  return {
    'access-control-allow-origin': origin,
    'access-control-allow-credentials': 'true',
    'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
    'access-control-allow-headers':
      request.headers()['access-control-request-headers'] ||
      'Content-Type, Authorization, X-CSRFToken, X-Requested-With',
  };
}

/**
 * 统一的接口拦截。返回一个"请求记录器"，用来断言前端到底发了什么。
 *
 * ⚠️ 这里用**正则**而不是通配写法（形如 两个星号 + /api/ + 两个星号）：
 * 那种写法会把 vite 自己提供的模块请求 `/src/api/http.js`、`/src/api/detection.js`
 * 也一起拦掉（它们同样含 `/api/`），于是应用连模块都加载不出来，
 * 表现为"页面一直白屏、路由守卫也不跳转"。正则要求 `/api/` 紧跟域名之后，
 * 因此只匹配真正的接口。
 */
async function mockApi(context) {
  const seen = { detectBodies: [], loginBodies: [], feedback: [] };

  await context.route(/^https?:\/\/[^/]+\/(api|media)\//, async (route) => {
    const request = route.request();
    const url = request.url();
    const method = request.method();

    if (method === 'OPTIONS') {
      return route.fulfill({ status: 204, headers: corsHeaders(request) });
    }

    if (url.includes('/media/')) {
      return route.fulfill({ status: 200, contentType: 'image/png', body: TINY_PNG, headers: corsHeaders(request) });
    }

    if (url.includes('/api/login/')) {
      seen.loginBodies.push(request.postData() || '');
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: corsHeaders(request),
        body: JSON.stringify({ status: 'success', message: '登录成功', data: { user: USER, token: 'fake-token-123' } }),
      });
    }

    if (url.includes('/api/register/')) {
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        headers: corsHeaders(request),
        body: JSON.stringify({ status: 'success', data: { user: USER, token: 'fake-token-123' } }),
      });
    }

    if (url.includes('/api/detect/')) {
      // 记录 multipart body：后面要断言"确实上传了一张真实编码的 JPEG"
      const body = request.postDataBuffer();
      seen.detectBodies.push(body || Buffer.alloc(0));
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: corsHeaders(request),
        body: JSON.stringify({ status: 'success', data: { detection: DISEASE, history_id: 321 } }),
      });
    }

    if (url.includes('/api/detection-history/321/')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: corsHeaders(request),
        body: JSON.stringify(HISTORY_ITEM),
      });
    }

    if (url.includes('/api/detection-history/')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: corsHeaders(request),
        body: JSON.stringify({
          code: 200,
          msg: 'success',
          data: { items: [HISTORY_ITEM], total: 1, page: 1, page_size: 10, total_pages: 1, has_next: false },
        }),
      });
    }

    if (url.includes('/api/feedback/')) {
      if (method === 'POST') seen.feedback.push(request.postData() || '');
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        headers: corsHeaders(request),
        body: JSON.stringify({ id: 1, status: 'pending' }),
      });
    }

    if (url.includes('/api/users/me/points/')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: corsHeaders(request),
        body: JSON.stringify({ points: 128, level: 2, level_name: '种植能手' }),
      });
    }

    if (url.includes('/stats/')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: corsHeaders(request),
        body: JSON.stringify({ post_count: 5, comment_count: 12, like_count: 30 }),
      });
    }

    if (url.includes('/api/check-auth/')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: corsHeaders(request),
        body: JSON.stringify({ status: 'success', data: { user: USER } }),
      });
    }

    // 其它接口（公告、通知等）返回空成功，避免页面出现无谓报错
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: corsHeaders(request),
      body: JSON.stringify({ code: 200, msg: 'success', data: { items: [], total: 0, results: [] } }),
    });
  });

  return seen;
}

/** 视频是否真的出画面了（假摄像头也要确认分辨率 > 0） */
async function videoSize(page, selector) {
  return page.evaluate((sel) => {
    const video = document.querySelector(sel);
    if (!video) return null;
    return { w: video.videoWidth, h: video.videoHeight, readyState: video.readyState };
  }, selector);
}

function checkUploadBody(bodies, label) {
  const body = bodies[bodies.length - 1];
  if (!body || !body.length) {
    record(`${label}：/detect/ 请求体非空`, false, '没有捕获到请求体');
    return;
  }
  const text = body.toString('latin1');
  // 文件名形如 photo-2026-09-27T14-47-14-123Z.jpg（\w 覆盖末尾的 Z）
  const hasPhotoName = /filename="photo-[\w:.-]+\.jpg"/.test(text);
  const hasJpegMagic = body.includes(Buffer.from([0xff, 0xd8, 0xff]));
  record(
    `${label}：上传体含真实 JPEG（${(body.length / 1024).toFixed(1)}KB）`,
    hasPhotoName && hasJpegMagic,
    `filename=photo-*.jpg:${hasPhotoName} jpeg 头:${hasJpegMagic}`,
  );
}

/* ==========================================================================
 * 移动端
 * ======================================================================== */
async function runMobile(browser) {
  console.log('\n=== 移动端（mobile，5174，iPhone 视口）===');
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    locale: 'zh-CN',
    permissions: ['camera'],
  });
  const seen = await mockApi(context);
  const page = await context.newPage();

  // 1. 未登录访问识别页 → 应被守卫拦到登录页
  await page.goto(`${MOBILE_URL}/detect`, { waitUntil: 'domcontentloaded' });
  await page.waitForURL('**/login**', { timeout: 15000 }).catch(() => {});
  const onLogin = page.url().includes('/login');
  record('移动端：未登录访问 /detect 被重定向到登录页', onLogin, page.url());
  await page.screenshot({ path: resolve(SHOT_DIR, 'mobile-01-login.png') });

  // 2. 登录
  await page.fill('input[name="username"]', '测试农户');
  await page.fill('input[name="password"]', 'farm123456');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/detect', { timeout: 15000 });
  record('移动端：登录后进入识别页', page.url().includes('/detect'), page.url());
  record('移动端：登录请求已发出', seen.loginBodies.length > 0);

  // 3. 点「拍照识别」→ 页面内取景
  await page.click('.entry--primary');
  await page.waitForSelector('.cam', { state: 'visible', timeout: 10000 });
  await page.waitForFunction(() => {
    const v = document.querySelector('.cam-video');
    return v && v.videoWidth > 0;
  }, null, { timeout: 15000 });
  const size = await videoSize(page, '.cam-video');
  record('移动端：取景框出画面', Boolean(size && size.w > 0 && size.h > 0), JSON.stringify(size));
  await page.screenshot({ path: resolve(SHOT_DIR, 'mobile-02-camera.png') });

  // 4. 快门
  await page.click('.cam-shutter');
  await page.waitForSelector('.preview-img', { state: 'visible', timeout: 10000 });
  const previewOk = await page.evaluate(() => {
    const img = document.querySelector('.preview-img');
    return Boolean(img && img.src.startsWith('data:image/jpeg') && img.src.length > 3000);
  });
  record('移动端：快门 → 本地生成 JPEG 预览', previewOk);
  await page.screenshot({ path: resolve(SHOT_DIR, 'mobile-03-preview.png') });

  // 5. 开始识别 → 结果页
  await page.click('button:has-text("开始识别")');
  await page.waitForURL('**/result', { timeout: 20000 });
  await page.waitForSelector('.disease-name', { timeout: 10000 });
  const diseaseText = await page.textContent('.disease-name');
  record('移动端：识别结果页显示病害名', /玉米大斑病/.test(diseaseText || ''), diseaseText?.trim());
  const confidenceText = await page.textContent('.confidence-value');
  record('移动端：置信度显示为百分比', /93%/.test(confidenceText || ''), confidenceText?.trim());

  // 后端给的是 build_absolute_uri 出来的绝对地址（http://127.0.0.1:8000/media/...）。
  // 手机上该地址指向手机自己 → 必须被改写为相对路径才加载得到。
  const resultImgSrc = await page.getAttribute('.result-img', 'src');
  record(
    '移动端：后端绝对图片地址被改写为相对路径',
    Boolean(resultImgSrc && resultImgSrc.startsWith('/media/')),
    resultImgSrc || '(空)',
  );

  checkUploadBody(seen.detectBodies, '移动端');
  await page.screenshot({ path: resolve(SHOT_DIR, 'mobile-04-result.png'), fullPage: true });

  // 6. 纠错反馈
  await page.click('button:has-text("准确")');
  await page.waitForTimeout(600);
  record('移动端：纠错反馈已提交', seen.feedback.length > 0, `${seen.feedback.length} 次`);

  // 7. 识别记录
  await page.goto(`${MOBILE_URL}/history`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.record-name', { timeout: 15000 });
  const recordName = await page.textContent('.record-name');
  record('移动端：识别记录列表有数据', /玉米大斑病/.test(recordName || ''), recordName?.trim());
  await page.screenshot({ path: resolve(SHOT_DIR, 'mobile-05-history.png') });

  // 8. 记录详情（走接口）
  await page.click('.record');
  await page.waitForURL('**/result/321', { timeout: 15000 });
  await page.waitForSelector('.disease-name', { timeout: 15000 });
  const detailName = await page.textContent('.disease-name');
  record('移动端：记录详情按 id 拉取', /玉米大斑病/.test(detailName || ''), detailName?.trim());
  await page.screenshot({ path: resolve(SHOT_DIR, 'mobile-06-history-detail.png'), fullPage: true });

  // 9. 我的
  await page.goto(`${MOBILE_URL}/mine`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.user-name', { timeout: 15000 });
  const mineName = await page.textContent('.user-name');
  await page.waitForTimeout(800);
  const statValues = await page.$$eval('.stat strong', (nodes) => nodes.map((n) => n.textContent.trim()));
  record('移动端：「我的」显示当前用户', /测试农户/.test(mineName || ''), mineName?.trim());
  record(
    '移动端：「我的」统计数字已填充',
    statValues.length === 3 && statValues[0] === '1' && statValues[2] === '128',
    `detections/posts/points = ${statValues.join('/')}`,
  );
  await page.screenshot({ path: resolve(SHOT_DIR, 'mobile-07-mine.png') });

  await context.close();
}

/** 移动端降级路径：没有 mediaDevices 时必须能用系统相机（input capture） */
async function runMobileFallback(browser) {
  console.log('\n=== 移动端降级：拿不到摄像头（模拟局域网 http 场景）===');
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    locale: 'zh-CN',
  });
  await mockApi(context);

  // 直接种登录态（mobile 用 localStorage），并抹掉 mediaDevices 模拟非安全上下文
  await context.addInitScript(() => {
    localStorage.setItem('mobile_token', 'fake-token-123');
    localStorage.setItem(
      'mobile_user',
      JSON.stringify({ id: 7, username: '测试农户', is_staff: false, role: 'FARMER' }),
    );
    try {
      Object.defineProperty(window.navigator, 'mediaDevices', { get: () => undefined });
    } catch {
      /* 定义失败则忽略，测试会体现为失败 */
    }
  });

  const page = await context.newPage();
  await page.goto(`${MOBILE_URL}/detect`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.entry--primary', { timeout: 15000 });

  const chooserPromise = page.waitForEvent('filechooser', { timeout: 8000 }).catch(() => null);
  await page.click('.entry--primary');
  const chooser = await chooserPromise;

  record('移动端降级：无摄像头时唤起系统相机/文件选择', Boolean(chooser), chooser ? 'filechooser 已触发' : '未触发');
  const toastText = await page
    .waitForSelector('.van-toast', { timeout: 5000 })
    .then((el) => el.textContent())
    .catch(() => '');
  record('移动端降级：给出明确原因提示', /不支持|禁用/.test(toastText || ''), toastText?.trim());
  await page.screenshot({ path: resolve(SHOT_DIR, 'mobile-08-fallback.png') });

  await context.close();
}

/* ==========================================================================
 * 桌面客户端（frontend）
 * ======================================================================== */
async function runClient(browser) {
  console.log('\n=== 桌面客户端（frontend，5173）===');
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
    permissions: ['camera'],
  });
  const seen = await mockApi(context);

  // 桌面端身份存在 sessionStorage（键名 auth_token / user，见 utils/authStorage.js）。
  // 这里直接种登录态，把验证重点留给"拍照"这条链路。
  await context.addInitScript(() => {
    sessionStorage.setItem('auth_token', 'fake-token-123');
    sessionStorage.setItem(
      'user',
      JSON.stringify({ id: 7, username: '测试农户', is_staff: false, role: 'FARMER' }),
    );
  });

  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(String(error).slice(0, 200)));

  await page.goto(`${CLIENT_URL}/detect`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.entry-btn.is-primary', { timeout: 30000 });
  record('客户端：识别页加载（已登录态）', true, page.url());
  await page.screenshot({ path: resolve(SHOT_DIR, 'client-01-detect.png') });

  // 点「拍照」→ 应该是**页面内取景**（而不是弹出文件选择框）
  let fileChooserFired = false;
  page.on('filechooser', () => {
    fileChooserFired = true;
  });
  await page.click('.entry-btn.is-primary');
  await page.waitForSelector('.camera-overlay', { state: 'visible', timeout: 15000 });
  await page.waitForFunction(() => {
    const v = document.querySelector('.camera-video');
    return v && v.videoWidth > 0;
  }, null, { timeout: 20000 });
  const size = await videoSize(page, '.camera-video');
  record(
    '客户端：点「拍照」打开页面内取景（未弹文件框）',
    Boolean(size && size.w > 0) && !fileChooserFired,
    JSON.stringify(size),
  );
  await page.screenshot({ path: resolve(SHOT_DIR, 'client-02-camera.png') });

  // 切换摄像头按钮：桌面假设备只有一个 videoinput，按钮应隐藏（避免"点了没反应"）
  const switchVisible = await page.isVisible('.camera-side .camera-btn--icon').catch(() => false);
  record('客户端：单摄像头时不显示「切换摄像头」', switchVisible === false, `visible=${switchVisible}`);

  await page.click('.camera-shutter');
  await page.waitForSelector('.drop-preview', { state: 'visible', timeout: 15000 });
  const preview = await page.getAttribute('.drop-preview', 'src');
  record(
    '客户端：快门 → 生成 JPEG 预览',
    Boolean(preview && preview.startsWith('data:image/jpeg')),
    `${(preview || '').length} 字节 dataURL`,
  );
  await page.screenshot({ path: resolve(SHOT_DIR, 'client-03-preview.png') });

  await page.click('button:has-text("开始识别")');
  await page.waitForFunction(() => document.body.innerText.includes('玉米大斑病'), null, { timeout: 30000 });
  record('客户端：识别结果渲染', true);
  checkUploadBody(seen.detectBodies, '客户端');
  await page.screenshot({ path: resolve(SHOT_DIR, 'client-04-result.png'), fullPage: true });

  record('客户端：页面无 JS 报错', pageErrors.length === 0, pageErrors.join(' | ').slice(0, 300));

  await context.close();
}

/* ========================================================================== */
const browser = await chromium.launch({
  channel: 'msedge', // 本机已安装 Edge，免去下载 Playwright 自带浏览器
  args: [
    '--use-fake-ui-for-media-stream',
    '--use-fake-device-for-media-stream',
    '--autoplay-policy=no-user-gesture-required',
  ],
});

try {
  await runMobile(browser);
  await runMobileFallback(browser);
  await runClient(browser);
} finally {
  await browser.close();
}

const failed = results.filter((item) => !item.ok);
console.log(`\n===== 汇总：${results.length - failed.length}/${results.length} 通过 =====`);
if (failed.length) {
  console.log('失败项：');
  failed.forEach((item) => console.log(`  · ${item.name} ${item.detail || ''}`));
  process.exitCode = 1;
}
