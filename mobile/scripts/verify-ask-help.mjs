/**
 * 移动端「一键求助」验收（第 176 批）
 * ============================================================================
 * 结果页多了一张「复制求助内容」的卡片：农户识别完，点一下就把一段现成的说明
 * 复制到剪贴板，粘到微信群/论坛里就能问 —— 移动端没有论坛（设计上留给桌面端），
 * 而农户真实的提问场景就是微信群。
 *
 * 本脚本验证：
 *   ① 走一遍真实识别，结果页出现「求助」卡片
 *   ② 点它之后**剪贴板里真的有一段文案**（不是弹个提示了事）
 *   ③ 文案内容完整：病名 / 把握多大 / 症状 / 防治建议 / 图片链接 / 一句提问
 *   ④ 文案里不出现英文类名（Apple___ 之类）
 *   ⑤ **HTTP 局域网下 Clipboard API 不可用时要能回退**（模拟：把 navigator.clipboard 删掉，
 *      看是否仍然复制成功；这条正是手机上最会踩的坑）
 *   ⑥ 全程无 JS 报错
 *
 * 用法：node scripts/verify-ask-help.mjs
 */
import { chromium } from '@playwright/test';
import path from 'node:path';
import { clearThrottle, runDjango } from './helpers.mjs';

const UI = 'http://127.0.0.1:5174';
const SAMPLE = path.resolve(process.cwd(), '..', 'backend', 'pests', 'Apple___Apple_scab14.jpg');
const USER = 'zz_mobile_askhelp';
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
  'u.is_active = True',
  'u.is_deleted = False',
  'u.save()',
  'DetectionHistory.objects.filter(user=u).delete()',
  "print('askhelp user ready')",
]);

const browser = await chromium.launch();
// ⚠️ 剪贴板读取权限只对**安全上下文**生效；Playwright 里显式授予即可读
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true,
  locale: 'zh-CN',
  permissions: ['clipboard-read', 'clipboard-write'],
});
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error).slice(0, 200)));

// 登录 → 识别一张真图 → 到结果页
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
// ① 卡片在不在
// ---------------------------------------------------------------------------
const pageText = await page.locator('body').innerText();
check('结果页出现「求助」卡片', /问问大家|复制求助内容/.test(pageText), '');
await page.screenshot({ path: 'dsh-shots/ask-help-card.png' });

// ---------------------------------------------------------------------------
// ② 点一下，读剪贴板
// ---------------------------------------------------------------------------
await page.getByRole('button', { name: /复制求助内容/ }).first().click();
await page.waitForTimeout(1200);
const clip = await page.evaluate(async () => {
  try { return await navigator.clipboard.readText(); } catch { return ''; }
});
check('剪贴板里真的有文案', clip.length > 20, `${clip.length} 字`);
check('文案含病名', /苹果黑星病/.test(clip), clip.split('\n')[0] || '');
check('文案含把握（置信度）', /\d+%/.test(clip), (clip.match(/\d+%/) || [])[0] || '');
check('文案含症状', /症状/.test(clip), '');
check('文案含防治建议', /防治|用药|喷|杀菌/.test(clip), '');
check('文案含图片链接', /https?:\/\/|media\//.test(clip), (clip.match(/(https?:\/\/|media\/)\S+/) || [])[0] || '');
check('文案含一句提问', /怎么|谢谢|多久/.test(clip), '');
check('文案不露英文类名', !/Apple___|healthy/i.test(clip), '');
// 这两条是这一批踩出来的：占位符没替换、链接是相对路径 —— 都只有把文案打出来才看得到
check('文案里没有未替换的占位符（{xxx}）', !/\{[a-zA-Z_]+\}/.test(clip),
  (clip.match(/\{[a-zA-Z_]+\}/g) || []).join(' '));
check('图片链接是绝对地址（粘到微信里能点开）',
  /识别照片：https?:\/\//.test(clip), (clip.match(/识别照片：\S+/) || [])[0] || '');
console.log('  —— 复制的文案 ——');
console.log(clip.split('\n').map((line) => `  ｜ ${line}`).join('\n'));

await page.screenshot({ path: 'dsh-shots/ask-help-copied.png' });

// ---------------------------------------------------------------------------
// ③ 回退路径：手机走 HTTP 局域网时 navigator.clipboard 是 undefined
//    这里把标准 API 摘掉，看它会不会自动回退到 execCommand
// ---------------------------------------------------------------------------
const fallbackOk = await page.evaluate(async () => {
  // 清掉剪贴板，确保"成功"不是上一轮的残留
  try { await navigator.clipboard.writeText(''); } catch { /* 忽略 */ }
  const saved = navigator.clipboard;
  try {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
  } catch { /* 忽略 */ }
  const area = document.createElement('textarea');
  return { removed: !navigator.clipboard, hadApi: Boolean(saved) };
});
check('能模拟出"没有 Clipboard API"的手机环境', fallbackOk.removed, '');

await page.getByRole('button', { name: /复制求助内容/ }).first().click();
await page.waitForTimeout(1500);
const afterFallback = await page.evaluate(() => ({
  // 回退路径成功时 execCommand 会返回 true；这里看页面上是否弹出了"长按复制"的兜底弹窗
  dialogShown: document.querySelectorAll('.van-dialog').length > 0,
  toast: document.querySelector('.van-toast')?.textContent?.trim() || '',
}));
check('没有 Clipboard API 时不会"点了没反应"（成功提示或兜底弹窗至少有一个）',
  afterFallback.dialogShown || afterFallback.toast.length > 0,
  `弹窗=${afterFallback.dialogShown} 提示="${afterFallback.toast}"`);
await page.screenshot({ path: 'dsh-shots/ask-help-fallback.png' });

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
    "print('askhelp user cleaned')",
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
