/**
 * 首页作物图标 + 百科页分页文案验证（第 169 批）
 * ============================================================================
 * 用户反馈两件事：
 *   ① 首页「热门作物」四个图标要换成「关于」页那套作物图标（原来苹果画的是一只虫子 ✗）；
 *   ② 病害百科页的分页文案在**中文界面下显示英文** "Page 1/5 · 26 entries" ✗。
 *
 * 本脚本验证：
 *   ① 首页四个作物卡片的图标是 🍎🥔🌽🍇，且与「关于」页同一套
 *   ② 中文界面下百科页显示「第 x/y 页 · 共 n 条」
 *   ③ 切到英文后显示 "Page x/y · n entries"
 *
 * 用法：node scripts/verify-home-and-wiki-i18n.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

// ⚠️ /pests 的路由 meta 是 requiresAuth：不注入登录态会被守卫弹回首页，
// 页面上根本找不到 .pagination-info（第一版就是这么超时的）。
clearThrottle();
const seed = runDjango([
  'import json',
  'from django.contrib.auth import get_user_model',
  'from rest_framework.authtoken.models import Token',
  'from api.serializers import CustomUserSerializer',
  "u = get_user_model().objects.get(username='admin')",
  'token, _ = Token.objects.get_or_create(user=u)',
  "print('ZZ_TOKEN=' + token.key)",
  "print('ZZ_USER=' + json.dumps(CustomUserSerializer(u).data, ensure_ascii=False))",
]);
const token = /ZZ_TOKEN=(\S+)/.exec(seed)?.[1];
const userJson = /ZZ_USER=(.+)/.exec(seed)?.[1];

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 950 }, locale: 'zh-CN' });
const page = await context.newPage();
const pageErrors = [];
page.on('pageerror', (error) => pageErrors.push(String(error).slice(0, 200)));

// 注入登录态（其余用例沿用同样的方式）
await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
await page.evaluate(([tk, us]) => {
  window.sessionStorage.setItem('auth_token', tk);
  window.sessionStorage.setItem('user', us);
}, [token, userJson]);

// ---------------------------------------------------------------------------
// ① 中文首页：四个作物图标
// ---------------------------------------------------------------------------
await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.crops-grid .crop-card', { timeout: 30_000 });
await page.waitForTimeout(2500);

const homeIcons = await page.locator('.crops-grid .crop-icon').allInnerTexts();
const homeNames = await page.locator('.crops-grid .crop-info h3').allInnerTexts();
console.log('  · 首页作物:', homeNames.map((n, i) => `${n}=${homeIcons[i]}`).join('  '));
check('首页四个作物图标是 🍎🥔🌽🍇',
  homeIcons.join('') === '🍎🥔🌽🍇', homeIcons.join(' '));
check('首页不再有图标字体的 class（已改为 emoji 文本）',
  (await page.locator('.crops-grid .crop-icon i').count()) === 0, '');
await page.locator('.crops-grid').scrollIntoViewIfNeeded();
await page.waitForTimeout(600);
await page.screenshot({ path: 'dsh-shots/home-crops.png' });

// ---------------------------------------------------------------------------
// ② 关于页：同一套图标（用户要求"换成关于页面对应的作物图标"）
// ---------------------------------------------------------------------------
await page.goto(`${UI}/about`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.crop-item', { timeout: 30_000 });
await page.waitForTimeout(1500);
const aboutPairs = await page.evaluate(() => Array.from(document.querySelectorAll('.crop-item')).map((el) => ({
  icon: (el.querySelector('.crop-icon')?.textContent || '').trim(),
  name: (el.querySelector('h4')?.textContent || '').trim(),
})));
const aboutByName = Object.fromEntries(aboutPairs.map((pair) => [pair.name, pair.icon]));
console.log('  · 关于页作物:', aboutPairs.slice(0, 6).map((p) => `${p.name}=${p.icon}`).join('  '));

let sameAsAbout = true;
homeNames.forEach((name, index) => {
  const aboutIcon = aboutByName[name];
  if (aboutIcon && aboutIcon !== homeIcons[index]) sameAsAbout = false;
});
check('首页图标与「关于」页同一作物完全一致', sameAsAbout, '');
check('关于页确实有这四个作物的图标',
  ['苹果', '马铃薯', '玉米', '葡萄'].every((n) => aboutByName[n]), Object.keys(aboutByName).join('/'));

// ---------------------------------------------------------------------------
// ③ 百科页：中文文案
// ---------------------------------------------------------------------------
await page.goto(`${UI}/pests`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.pagination-info', { timeout: 40_000 });
await page.waitForTimeout(3000);
const zhInfo = (await page.locator('.pagination-info').innerText()).trim();
console.log('  · 中文分页文案:', zhInfo);
check('中文界面下分页文案是中文', /第 \d+\/\d+ 页 · 共 \d+ 条/.test(zhInfo), zhInfo);
check('中文界面下不再出现英文 entries', !/entries/i.test(zhInfo), zhInfo);
await page.screenshot({ path: 'dsh-shots/wiki-pagination-zh.png' });

// ---------------------------------------------------------------------------
// ④ 切英文：文案应变回英文
// ---------------------------------------------------------------------------
await page.evaluate(() => window.localStorage.setItem('app_locale', 'en'));
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForSelector('.pagination-info', { timeout: 40_000 });
await page.waitForTimeout(3000);
const enInfo = (await page.locator('.pagination-info').innerText()).trim();
console.log('  · 英文分页文案:', enInfo);
check('英文界面下分页文案是英文', /Page \d+\/\d+ · \d+ entries/.test(enInfo), enInfo);
await page.screenshot({ path: 'dsh-shots/wiki-pagination-en.png' });

// 英文下首页也确认一下没被改坏
await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.crops-grid .crop-icon', { timeout: 30_000 });
await page.waitForTimeout(2000);
const enIcons = await page.locator('.crops-grid .crop-icon').allInnerTexts();
check('英文界面下图标同样是 emoji', enIcons.join('') === '🍎🥔🌽🍇', enIcons.join(' '));

// 收尾：把语言恢复成中文
await page.evaluate(() => window.localStorage.setItem('app_locale', 'zh-CN'));

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
