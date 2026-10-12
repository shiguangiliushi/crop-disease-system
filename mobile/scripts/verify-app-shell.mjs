/**
 * 移动端外壳验收（第 173 批）
 * ============================================================================
 * 这一批做的是"统一口径 + 收顶栏进外壳"，所以要验的就是**一致性**：
 *
 *   ① 每个页面**有且仅有一个**顶栏，标题正确（改前识别页/登录页是 0 个）
 *   ② 返回箭头按 meta 出现：注册/找回/结果页有；识别/记录/我的/登录没有
 *   ③ 底部导航按 meta 出现：识别/记录/我的有；登录/注册/找回/结果没有
 *   ④ 顶栏统一 `fixed`（改前三页是随内容滚动的）
 *   ⑤ 页面切换有过渡动画（改前是瞬间替换）
 *   ⑥ 没有底部导航的页面垫了安全区
 *   ⑦ 主题色生效（主色 #2e7d32 与网页端一致）
 *   ⑧ 全程无 JS 报错
 *
 * 用法：node scripts/verify-app-shell.mjs
 */
import { chromium } from '@playwright/test';
import { clearThrottle } from './helpers.mjs';

const UI = 'http://127.0.0.1:5174';
const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

/** 期望：标题 / 返回箭头 / 底部导航 */
const EXPECT = {
  '/detect': { title: '病害识别', back: false, tabbar: true },
  '/history': { title: '识别记录', back: false, tabbar: true },
  '/mine': { title: '我的', back: false, tabbar: true },
  '/result': { title: '识别结果', back: true, tabbar: false },
  '/login': { title: '欢迎回来', back: false, tabbar: false },   // auth.loginTitle 的实际文案
  '/register': { title: '注册账号', back: true, tabbar: false },
  '/forgot-password': { title: '找回密码', back: true, tabbar: false },
};

const AUTHED = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: 'zh-CN' };
// ⚠️ 先清限流：登录接口有频率限制，E2E 连跑几轮就会被挡住
clearThrottle();

const browser = await chromium.launch();
const errors = [];

// 登录态上下文（受保护页面用）
const authed = await browser.newContext(AUTHED);
const page = await authed.newPage();
page.on('pageerror', (error) => errors.push(String(error).slice(0, 160)));
await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
await page.locator('input').nth(0).fill(process.env.MOBILE_E2E_USER || 'admin');
await page.locator('input').nth(1).fill(process.env.MOBILE_E2E_PASS || 'admin123456');
await page.getByRole('button', { name: /登录/ }).first().click();
await page.waitForTimeout(3000);
check('能正常登录（后续受保护页面才拍得到真页面）', !page.url().includes('/login'), page.url());

// 未登录上下文（登录/注册/找回三页）
const guest = await browser.newContext(AUTHED);
const guestPage = await guest.newPage();
guestPage.on('pageerror', (error) => errors.push(String(error).slice(0, 160)));

const probe = async (target) => target.evaluate(() => {
  const bars = Array.from(document.querySelectorAll('.van-nav-bar'));
  const bar = bars[0];
  const tabbar = document.querySelector('.van-tabbar');
  return {
    navCount: bars.length,
    title: bar?.querySelector('.van-nav-bar__title')?.textContent?.trim() || '',
    back: Boolean(bar?.querySelector('.van-nav-bar__left .van-icon-arrow-left')),
    fixed: bar ? getComputedStyle(bar).position === 'fixed' : false,
    placeholder: Boolean(document.querySelector('.van-nav-bar__placeholder')),
    tabbar: tabbar ? getComputedStyle(tabbar).display !== 'none' : false,
    safeBottom: Boolean(document.querySelector('.safe-bottom')),
    hasTransitionRule: Array.from(document.styleSheets).some((sheet) => {
      try {
        return Array.from(sheet.cssRules || []).some((rule) => rule.selectorText?.includes('fade-slide-enter-active'));
      } catch { return false; }
    }),
  };
});

const AUTHED_PAGES = ['/detect', '/history', '/mine', '/result'];
const GUEST_PAGES = ['/login', '/register', '/forgot-password'];

for (const route of [...AUTHED_PAGES, ...GUEST_PAGES]) {
  const target = AUTHED_PAGES.includes(route) ? page : guestPage;
  await target.goto(`${UI}${route}`, { waitUntil: 'domcontentloaded' });
  await target.waitForTimeout(2200);
  const info = await probe(target);
  const want = EXPECT[route];
  const label = route.padEnd(18);

  check(`${label} 有且仅有一个顶栏`, info.navCount === 1, `${info.navCount} 个`);
  check(`${label} 标题 = ${want.title}`, info.title === want.title, `实际 "${info.title}"`);
  check(`${label} 返回箭头 ${want.back ? '有' : '无'}`,
    info.back === want.back, info.back ? '有' : '无');
  check(`${label} 底部导航 ${want.tabbar ? '有' : '无'}`,
    info.tabbar === want.tabbar, info.tabbar ? '有' : '无');
  check(`${label} 顶栏固定 + 占位（内容不被压住）`,
    info.fixed && info.placeholder, `fixed=${info.fixed} placeholder=${info.placeholder}`);
  if (!want.tabbar) {
    check(`${label} 垫了底部安全区`, info.safeBottom, info.safeBottom ? '' : '没有 .safe-bottom');
  }
  if (route === '/detect') {
    check('页面切换动画的样式已生效', info.hasTransitionRule, '');
  }
}

// 主题色：登录页的主按钮应为品牌绿 #2e7d32（与网页端 --brand 一致）
await guestPage.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
await guestPage.waitForTimeout(1800);
const buttonColor = await guestPage.evaluate(() => {
  const btn = document.querySelector('.van-button--primary');
  return btn ? getComputedStyle(btn).backgroundColor : '';
});
check('主题主色 = 品牌绿 rgb(46, 125, 50)',
  buttonColor.replace(/\s/g, '') === 'rgb(46,125,50)', buttonColor);

check('全程无 JS 报错', errors.length === 0, errors.slice(0, 2).join(' | '));

await browser.close();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
