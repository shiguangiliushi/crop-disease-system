/**
 * 移动端外观基线截图（第 173 批 Step 0）
 * ============================================================================
 * 改壳之前先把 7 个页面在**手机尺寸**下拍一遍，作为"改前"的对照。
 * 这些图只作本地留证（mobile/dsh-shots 是 gitignore 的），改动后的对照图同目录命名 + `-after`。
 *
 * 用法：node scripts/capture-baseline.mjs [suffix]
 *   suffix 省略 → 拍基线（-before）；传 after → 拍改后
 */
import { chromium } from '@playwright/test';
import { clearThrottle } from './helpers.mjs';
import fs from 'node:fs';
import path from 'node:path';

const UI = 'http://127.0.0.1:5174';
const suffix = process.argv[2] || 'before';
const outDir = path.resolve('dsh-shots');
fs.mkdirSync(outDir, { recursive: true });

/** 7 个页面（分成两类：需要登录的 / 只能在未登录时看的） */
const PAGES_AUTHED = [
  ['detect', '/detect'],
  ['history', '/history'],
  ['mine', '/mine'],
  ['result', '/result'],
];
const PAGES_GUEST = [
  ['login', '/login'],
  ['register', '/register'],
  ['forgot', '/forgot-password'],
];
const PAGES = [...PAGES_AUTHED, ...PAGES_GUEST];

/**
 * ⚠️ 必须分**两个上下文**拍：
 *   · 受保护页面（detect / history / result）未登录会被守卫弹到登录页；
 *   · 而登录页/注册页在**已登录**时又会跳走（拍到的是识别页）✗。
 * 第一版只用一个上下文，两头都拍错了。
 */
const AUTHED = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: 'zh-CN' };
const USERNAME = process.env.MOBILE_E2E_USER || 'admin';
// ⚠️ 口令只从环境变量读，不写默认值（2026-10 安全核查）：仓库是公开的
const PASSWORD = process.env.MOBILE_E2E_PASS;
if (!PASSWORD) {
  console.error('缺少环境变量 MOBILE_E2E_PASS。设置后再跑，例如：\n  $env:MOBILE_E2E_PASS="<测试账号口令>"');
  process.exit(1);
}

// ⚠️ 先清限流：登录接口有频率限制，E2E 连跑几轮就会被挡住
clearThrottle();

const browser = await chromium.launch();

/** 登录态上下文：走真实登录流程（顺带把登录本身过一遍） */
const authedContext = await browser.newContext(AUTHED);
const page = await authedContext.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error).slice(0, 160)));
try {
  await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  const inputs = page.locator('input');
  await inputs.nth(0).fill(USERNAME);
  await inputs.nth(1).fill(PASSWORD);
  await page.getByRole('button', { name: /登录/ }).first().click();
  await page.waitForTimeout(3000);
  console.log(`  登录(${USERNAME}): ${page.url().includes('/login') ? '未成功 ✗' : '成功 ✓'}`);
} catch (error) {
  console.log('  登录失败（忽略）:', String(error).slice(0, 120));
}

/** 未登录上下文：登录/注册/找回密码这三页本来就是给未登录用户看的 */
const guestContext = await browser.newContext(AUTHED);
const guestPage = await guestContext.newPage();
guestPage.on('pageerror', (error) => errors.push(String(error).slice(0, 160)));

const capture = async (target, name, route) => {
  await target.goto(`${UI}${route}`, { waitUntil: 'domcontentloaded' });
  await target.waitForTimeout(2200);
  await target.screenshot({ path: path.join(outDir, `${name}-${suffix}.png`) });
  const probe = await target.evaluate(() => {
    const bars = document.querySelectorAll('.van-nav-bar');
    const tabbar = document.querySelector('.van-tabbar');
    const first = bars[0]?.querySelector('.van-nav-bar__title')?.textContent?.trim() || '';
    return {
      navBars: bars.length,
      navTitle: first,
      tabbar: tabbar ? getComputedStyle(tabbar).display !== 'none' : false,
      hasBackArrow: Boolean(bars[0]?.querySelector('.van-nav-bar__left .van-icon-arrow-left')),
    };
  });
  console.log(`  ${name.padEnd(9)} ${route.padEnd(18)} 顶栏${probe.navBars}个 标题="${probe.navTitle}" 返回箭头=${probe.hasBackArrow ? '有' : '无'} 底部导航=${probe.tabbar ? '有' : '无'}  实际路径=${new URL(target.url()).pathname}`);
};

for (const [name, route] of PAGES_AUTHED) await capture(page, name, route);
for (const [name, route] of PAGES_GUEST) await capture(guestPage, name, route);

console.log(`\n  截图 ${PAGES.length} 张 → mobile/dsh-shots/*-${suffix}.png`);
console.log('  JS 报错:', errors.length ? errors.join(' | ') : '无');
await browser.close();
