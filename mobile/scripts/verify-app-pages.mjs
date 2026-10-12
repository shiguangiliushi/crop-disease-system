/**
 * 移动端逐页精修验收（第 174 批）
 * ============================================================================
 * 这一批修的是"同一个 App 里两套东西"的细节，所以验的也是**一致性**：
 *
 *   ① 登录/注册/找回三页的 hero 里不再有与顶栏重复的标题（找回页是这一批补上的）
 *   ② 三页的主按钮**计算样式完全一致**（背景色/圆角/高度）—— 改前找回页写死了十六进制
 *   ③ 找回页的"返回登录"按钮也是主题色（不再是硬编码）
 *   ④ 记录页的空状态用 van-empty（改前是自定义小方块）
 *   ⑤ 识别页的进度不再是另一个浅绿（走主题色）
 *   ⑥ 全程无 JS 报错
 *
 * 用法：node scripts/verify-app-pages.mjs
 */
import { chromium } from '@playwright/test';
import { clearThrottle, runDjango } from './helpers.mjs';

const UI = 'http://127.0.0.1:5174';
const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

const BRAND = 'rgb(46, 125, 50)';
const AUTH_PAGES = [
  ['登录', '/login'],
  ['注册', '/register'],
  ['找回密码', '/forgot-password'],
];

clearThrottle();

// 造一个"没有任何识别记录"的账号，用来验记录页的空状态
const EMPTY_USER = 'zz_mobile_empty';
const EMPTY_PASS = 'ZzMobile!2026';
runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models import DetectionHistory',
  `u, created = get_user_model().objects.get_or_create(username='${EMPTY_USER}', defaults={'role': 'USER'})`,
  `u.set_password('${EMPTY_PASS}')`,
  'u.save()',
  'DetectionHistory.objects.filter(user=u).delete()',
  "print('empty user ready')",
]);

const AUTHED = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: 'zh-CN' };
const browser = await chromium.launch();
const errors = [];

const login = async (page, username, password) => {
  await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  await page.locator('input').nth(0).fill(username);
  await page.locator('input').nth(1).fill(password);
  await page.getByRole('button', { name: /登录/ }).first().click();
  await page.waitForTimeout(3000);
  return !page.url().includes('/login');
};

// ---------------------------------------------------------------------------
// ① 三个表单页：hero 无重复标题 + 主按钮样式一致
// ---------------------------------------------------------------------------
const guest = await browser.newContext(AUTHED);
const guestPage = await guest.newPage();
guestPage.on('pageerror', (error) => errors.push(String(error).slice(0, 160)));

const buttonStyleOf = async (route) => {
  await guestPage.goto(`${UI}${route}`, { waitUntil: 'domcontentloaded' });
  await guestPage.waitForTimeout(1800);
  return guestPage.evaluate(() => {
    const hero = document.querySelector('.auth-hero');
    const btn = document.querySelector('.van-button--primary');
    const style = btn ? getComputedStyle(btn) : null;
    return {
      heroHasHeading: Boolean(hero?.querySelector('h1, h2, h3')),
      bg: style?.backgroundColor || '',
      radius: style?.borderRadius || '',
      height: style?.height || '',
    };
  });
};

const styles = {};
for (const [label, route] of AUTH_PAGES) {
  const info = await buttonStyleOf(route);
  styles[label] = info;
  check(`${label}页 hero 里没有与顶栏重复的标题`, !info.heroHasHeading,
    info.heroHasHeading ? '还有 h1/h2/h3' : '');
  check(`${label}页主按钮是主题色`, info.bg.replace(/\s/g, '') === BRAND.replace(/\s/g, ''), info.bg);
}

const [a, b, c] = [styles['登录'], styles['注册'], styles['找回密码']];
const sameStyle = (x, y) => x.bg === y.bg && x.radius === y.radius && x.height === y.height;
check('三页主按钮样式完全一致（背景/圆角/高度）',
  sameStyle(a, b) && sameStyle(b, c),
  `登录 ${a.bg} ${a.radius} ${a.height} ｜ 注册 ${b.bg} ${b.radius} ${b.height} ｜ 找回 ${c.bg} ${c.radius} ${c.height}`);

// 找回页那个"返回登录"按钮（改前是硬编码色）
await guestPage.goto(`${UI}/forgot-password`, { waitUntil: 'domcontentloaded' });
await guestPage.waitForTimeout(1800);
const backBtnColor = await guestPage.evaluate(() => {
  const btn = document.querySelector('.van-button--primary');
  return btn ? getComputedStyle(btn).backgroundColor : '';
});
check('找回页按钮不再是硬编码色（走主题）',
  backBtnColor.replace(/\s/g, '') === BRAND.replace(/\s/g, ''), backBtnColor);

// ---------------------------------------------------------------------------
// ② 记录页空状态 = van-empty（用没有记录的账号）
// ---------------------------------------------------------------------------
const emptyContext = await browser.newContext(AUTHED);
const emptyPage = await emptyContext.newPage();
emptyPage.on('pageerror', (error) => errors.push(String(error).slice(0, 160)));
const ok = await login(emptyPage, EMPTY_USER, EMPTY_PASS);
check('空记录账号能登录', ok, emptyPage.url());

await emptyPage.goto(`${UI}/history`, { waitUntil: 'domcontentloaded' });
await emptyPage.waitForTimeout(2500);
const emptyInfo = await emptyPage.evaluate(() => ({
  empty: document.querySelectorAll('.van-empty').length,
  oldBox: document.querySelectorAll('.empty-box').length,
  text: document.querySelector('.van-empty__description')?.textContent?.trim() || '',
}));
check('记录页空状态用 van-empty', emptyInfo.empty === 1, `${emptyInfo.empty} 个`);
check('旧的自定义空状态已移除', emptyInfo.oldBox === 0, `${emptyInfo.oldBox} 个`);
check('空状态有文案', Boolean(emptyInfo.text), emptyInfo.text);
await emptyPage.screenshot({ path: 'dsh-shots/history-empty-after.png' });

// ---------------------------------------------------------------------------
// ③ 识别页：进度/按钮不再用另一个浅绿
// ---------------------------------------------------------------------------
const detectContext = await browser.newContext(AUTHED);
const detectPage = await detectContext.newPage();
detectPage.on('pageerror', (error) => errors.push(String(error).slice(0, 160)));
await login(detectPage, process.env.MOBILE_E2E_USER || 'admin', process.env.MOBILE_E2E_PASS || 'admin123456');
await detectPage.goto(`${UI}/detect`, { waitUntil: 'domcontentloaded' });
await detectPage.waitForTimeout(2200);
const detectColors = await detectPage.evaluate(() => {
  // 页面元素上不该再出现那个浅绿（#7ec87e → rgb(126, 200, 126)）
  const lightGreen = 'rgb(126, 200, 126)';
  const offenders = Array.from(document.querySelectorAll('*')).filter((el) => {
    const style = getComputedStyle(el);
    return style.color === lightGreen || style.backgroundColor === lightGreen
      || style.borderTopColor === lightGreen;
  });
  // 未选图时识别页上是自定义的大入口（不是 van-button），所以这里看 .entry--primary
  const entry = document.querySelector('.entry--primary');
  return {
    offenders: offenders.length,
    entryBg: entry ? getComputedStyle(entry).backgroundColor : '',
  };
});
check('识别页不再出现另一个浅绿（#7ec87e）', detectColors.offenders === 0, `${detectColors.offenders} 处`);
const BRAND_SOFT = 'rgb(232, 245, 233)';   // --brand-soft
check('识别页主入口用的是品牌浅色底（--brand-soft）',
  detectColors.entryBg.replace(/\s/g, '') === BRAND_SOFT.replace(/\s/g, ''), detectColors.entryBg);
await detectPage.screenshot({ path: 'dsh-shots/detect-pages-after.png' });

check('全程无 JS 报错', errors.length === 0, errors.slice(0, 2).join(' | '));

await browser.close();

// 清理造出来的空账号
try {
  runDjango([
    'from django.contrib.auth import get_user_model',
    `print('cleaned:', get_user_model().objects.filter(username='${EMPTY_USER}').delete()[0])`,
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
