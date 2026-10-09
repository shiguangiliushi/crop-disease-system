/**
 * 「编辑器插图上传」端到端验证（第 141 批）
 * ============================================================================
 * 修的是什么：Quill 的图片按钮走默认行为 → 图片被转成 **base64 内联进正文**
 * （一张手机照片就让正文涨几 MB、图片无法复用）；而后端
 * `POST /api/news/upload_image/`（第 91 批加固过：大小上限、按文件头判格式、随机文件名）
 * 因为前端从没调用而成为**死接口**。
 *
 * 覆盖：
 *   ① 点工具栏图片按钮 → 选中一张 PNG → 正文里出现 `/media/news_images/` 的 URL
 *   ② 正文里**没有** data:image（核心：不再 base64 内联）
 *   ③ 服务端真的落盘了（media/news_images 下能查到这张图）
 *   ④ 粘贴图片同样走上传（不再是 base64）
 *   ⑤ 论坛发帖页走的是**通用**通道 `/api/upload/image/`（upload-target=generic）
 *
 * 用法：node scripts/verify-editor-image-upload.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';
const adminName = `zze2e_img_${suffix}`;

const results = [];
let cleaned = false;
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

const cleanup = () => {
  if (cleaned) return;
  cleaned = true;
  clearThrottle();
  try {
    runDjango([
      'from django.contrib.auth import get_user_model',
      "U = get_user_model()",
      "print('cleaned:', U.objects.filter(username__startswith='zze2e_img_').delete()[0])",
      // 顺手删掉最近 15 分钟内上传的测试图片，别在 media/ 里攒垃圾
      'import glob, os, time',
      'from django.conf import settings',
      "files = glob.glob(os.path.join(settings.MEDIA_ROOT, 'news_images', 'news_*.png'))",
      "fresh = [f for f in files if os.path.getmtime(f) > time.time() - 900]",
      "[os.remove(f) for f in fresh]",
      "print('removed temp images:', len(fresh))",
    ]);
  } catch (error) {
    console.error('清理失败（忽略）:', error?.message || error);
  }
};
process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });

clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'U = get_user_model()',
  `U.objects.create_user(username='${adminName}', password='${password}', is_staff=True, role='ADMIN')`,
  "print('seeded')",
]);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' });
const page = await ctx.newPage();
const pageErrors = [];
const consoleErrors = [];
const uploadCalls = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });
page.on('request', (r) => {
  if (r.method() === 'POST' && /upload_image|\/upload\/image\//.test(r.url())) uploadCalls.push(r.url());
});

await page.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.admin-login', { timeout: 30_000 });
await page.locator('#username').fill(adminName);
await page.locator('#password').fill(password);
await page.locator('button[type="submit"]').first().click();
await page.waitForURL((u) => u.pathname.startsWith('/admin/') && u.pathname !== '/admin/login', { timeout: 30_000 });
await page.waitForSelector('.admin-console', { timeout: 25_000 });

// ---------------------------------------------------------------------------
// ① 新闻编辑器的图片按钮
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/news`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.admin-console', { timeout: 25_000 });
await page.waitForTimeout(1200);
// ⚠️ 新闻的正文编辑器在**弹窗**里，必须先点「新增新闻」把弹窗打开（第一版直接找 .ql-editor 会超时）
await page.locator('button', { hasText: '新增新闻' }).first().click();
await page.waitForSelector('.el-dialog .ql-editor', { timeout: 25_000 });
await page.waitForTimeout(1000);

// 造一张 1×1 的真实 PNG 当上传文件
const pngBuffer = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==',
  'base64',
);

const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 15_000 });
await page.locator('.el-dialog .ql-toolbar button.ql-image').click();
const fileChooser = await fileChooserPromise;
await fileChooser.setFiles({ name: 'e2e-upload.png', mimeType: 'image/png', buffer: pngBuffer });
await page.waitForTimeout(3000);

const html = await page.locator('.el-dialog .ql-editor').innerHTML();
check('工具栏图片按钮上传后插入了图片', /<img[^>]+src=/.test(html), html.slice(0, 120));
check('图片地址是媒体目录的 URL（不是 base64）',
  /\/media\/news_images\//.test(html), (html.match(/src="([^"]+)"/) || [])[1] || '（没找到 src）');
check('正文里没有 data:image（核心：不再 base64 内联）', !/data:image/.test(html),
  /data:image/.test(html) ? '仍有 base64！' : '');
check('确实调用了新闻图片上传接口',
  uploadCalls.some((u) => u.includes('/news/upload_image/')), uploadCalls.join(' | ') || '（没调用）');

// ③ 服务端落盘
const saved = await page.evaluate(async ({ api }) => {
  const token = sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}/news/`, { headers: { Authorization: `Token ${token}` } });
  return res.status;
}, { api: API });
check('新闻列表接口仍正常（编辑页没被这次改动弄坏）', saved === 200, `HTTP ${saved}`);

const onDisk = await page.evaluate(() => {
  // 页面拿不到文件系统，这里只确认引用的 URL 可访问（HTTP 200）
  const img = document.querySelector('.el-dialog .ql-editor img');
  if (!img) return null;
  return fetch(img.src, { method: 'HEAD' }).then((r) => r.status).catch(() => 'ERR');
});
check('插入的图片 URL 真的能访问（服务端已落盘）', onDisk === 200, `HEAD ${onDisk}`);

// ---------------------------------------------------------------------------
// ④ 粘贴图片也走上传
// ---------------------------------------------------------------------------
const beforeCount = uploadCalls.length;
await page.evaluate(async () => {
  const editor = document.querySelector('.el-dialog .ql-editor');
  editor.focus();
  // 造一个带图片文件的 paste 事件（DataTransfer 在 Chromium 里可用）
  const base64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==';
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  const file = new File([bytes], 'pasted.png', { type: 'image/png' });
  const dt = new DataTransfer();
  dt.items.add(file);
  editor.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
});
await page.waitForTimeout(3000);
const htmlAfterPaste = await page.locator('.el-dialog .ql-editor').innerHTML();
check('粘贴图片也触发了上传', uploadCalls.length > beforeCount,
  `${beforeCount} → ${uploadCalls.length}`);
check('粘贴后正文里依然没有 base64', !/data:image/.test(htmlAfterPaste),
  /data:image/.test(htmlAfterPaste) ? '仍有 base64！' : '');

await page.screenshot({ path: 'dsh-shots/editor-image-upload.png', clip: { x: 0, y: 0, width: 1500, height: 700 } });

// ---------------------------------------------------------------------------
// ⑤ 论坛发帖走通用通道
// ---------------------------------------------------------------------------
const postCallsBefore = uploadCalls.length;
// ⚠️ 路由是 `/forum/post/new`（name: new-post），不是 `/forum/new`（第一版写错，页面 404 后
//    等不到编辑器就超时了）
await page.goto(`${UI}/forum/post/new`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.ql-editor', { timeout: 25_000 });
await page.waitForTimeout(1500);
const chooser2 = page.waitForEvent('filechooser', { timeout: 15_000 });
// 论坛发帖是**整页**（不是弹窗），所以这里不能用 .el-dialog 限定
await page.locator('.ql-toolbar button.ql-image').click();
const fileChooser2 = await chooser2;
await fileChooser2.setFiles({ name: 'e2e-post.png', mimeType: 'image/png', buffer: pngBuffer });
await page.waitForTimeout(3000);
const postCalls = uploadCalls.slice(postCallsBefore);
check('论坛发帖页走通用上传通道 /api/upload/image/',
  postCalls.some((u) => u.includes('/upload/image/')), postCalls.join(' | ') || '（没调用）');
const postHtml = await page.locator('.ql-editor').innerHTML();
check('帖子正文里也没有 base64', !/data:image/.test(postHtml), '');

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));
const realConsoleErrors = consoleErrors.filter((t) => !/Failed to load resource|favicon/i.test(t));
check('控制台没有 console.error', realConsoleErrors.length === 0, realConsoleErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
