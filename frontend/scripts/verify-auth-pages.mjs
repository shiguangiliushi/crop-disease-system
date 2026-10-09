/**
 * 认证页专项验证：**农户侧与管理端必须是两张脸**（第 116 批）
 *
 * 为什么需要它
 * ---------------------------------------------------------------------------
 * 改前 `/login` 一个页面同时写着「客服工作台 / 客服坐席专用入口 / 工单全流程 /
 * 服务数据看板 / 服务时间 周一至周五 09:00-18:00 / 内部支持 400-123-4567」——
 * 面向农户的 C 端产品，第一屏却是内部管理系统的样子。这类问题**不是功能坏了**，
 * 单元测试、接口测试全绿，只有把页面打开看才发现。
 *
 * 断言（农户侧）：
 *   ① /login /register /forgot-password /reset-password 四个页面都没有
 *      「客服 / 工作台 / 坐席 / 工单 / Agent Console」这类字样（中英各查一遍）；
 *   ② 页签标题也不再是"客服登录/客服注册"；
 *   ③ 左侧是农户那一栏（实拍图 hero + 四条能力胶囊），不是管理端那一栏；
 *   ④ 农户登录后落到首页（`/`）；
 *   ⑤ 匿名访问普通受保护页 → 送 /login。
 *
 * 断言（管理端）：
 *   ⑥ /admin/login 是**独立入口**：深色「管理后台」面板、没有能力胶囊、没有拍照识别那套话；
 *   ⑦ 管理员登录后落到**数据看板**（/admin/dashboard），不是首页；
 *   ⑧ 普通账号误入 /admin/login：给出"不是管理员账号"的提示并送回首页（不撞"无权限"）；
 *   ⑨ 匿名访问 /admin/** → 送 /admin/login（不是农户登录页），仍带 reason=loginRequired。
 *
 * 前置：后端 8000、前端 5173 均在运行。
 * 用法（在 frontend 目录下）：
 *   node scripts/verify-auth-pages.mjs
 * 退出码：全部通过 0，任一失败 1。
 */
import { chromium } from '@playwright/test';
// 造/清临时账号用（用例要验证"管理员登录后进数据看板"，必须有真管理员）；
// 顺带清限流计数 —— 注册/登录接口都有限速，反复跑这个脚本很容易撞 429。
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const API = process.env.E2E_API_URL || 'http://127.0.0.1:8000';
const UI = process.env.AUDIT_UI || 'http://127.0.0.1:5173';

const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

/** 不该再出现在认证页上的字样（农户侧与页签） */
const CONSOLE_WORDS = /客服|工作台|坐席|工单|Customer Service Console|Agent Console|console|ticket lifecycle/i;
/** 管理端**允许**出现「管理后台」这类词，但同样不该有"客服坐席"那套 */
const AGENT_WORDS = /客服|坐席|工单|Customer Service Console|Agent Console/i;

// ---- 临时账号（跑完即删） ----
// 两个账号都用 Django 直接建，而不是走 /api/register/：
// 注册接口有 5/小时的限速，反复跑本脚本必然撞 429（实测过），
// 而这个脚本要验的是**页面**，不是注册接口本身（那由 E2E 用例覆盖）。
const suffix = Math.random().toString(36).slice(2, 7);
const userName = `zze2e_auth_${suffix}`;
const adminName = `zze2e_adm_${suffix}`;
const password = 'ZzE2e!2026pw';

try {
  clearThrottle();   // 登录限速 10/分钟（按 IP），清掉免得上一轮把这一轮卡住
  const out = runDjango([
    'from django.contrib.auth import get_user_model',
    'U = get_user_model()',
    `U.objects.create_user(username='${userName}', password='${password}', email='${userName}@example.invalid')`,
    `admin = U.objects.create_user(username='${adminName}', password='${password}')`,
    'admin.is_staff = True',
    'admin.save()',
    "print('created:', U.objects.filter(username__startswith='zze2e_').count(), 'temp accounts')",
  ]);
  console.log(out);
} catch (error) {
  console.error(`造临时账号失败：${String(error).slice(0, 300)}`);
  process.exit(2);
}
console.log(`临时账号：${userName}（普通）/ ${adminName}（管理员），跑完自动清理`);

/**
 * 清理临时账号。挂在 process exit 上：脚本中途抛异常（比如断言超时）也会清干净。
 * 为什么补这一步：本脚本改 `useLoginForm` 那轮，中途崩过一次，
 * 库里就留下了 `zze2e_auth_*` / `zze2e_adm_*` 两个孤儿账号 —— 下次直接查"还有没有残留"才发现。
 */
let cleaned = false;
const cleanupAccounts = () => {
  if (cleaned) return;   // exit 钩子与正常收尾都会调一次，别重复跑
  cleaned = true;
  try {
    const out = runDjango([
      'from django.contrib.auth import get_user_model',
      `print('deleted:', get_user_model().objects.filter(username__in=['${userName}', '${adminName}']).delete()[0])`,
    ]);
    console.log(`\n临时账号清理：${out}`);
  } catch (error) {
    console.log(`\n⚠️ 自动清理失败（${String(error).slice(0, 160)}），请手动删除 ${userName} / ${adminName}`);
  }
};
process.on('exit', cleanupAccounts);

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN' });
const page = await context.newPage();
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));

const setLocale = async (locale) => {
  await page.addInitScript((value) => localStorage.setItem('app_locale', value), locale);
  await page.evaluate((value) => localStorage.setItem('app_locale', value), locale).catch(() => {});
};

const bodyText = () => page.locator('body').innerText();

const gotoAuth = async (path) => {
  await page.goto(`${UI}${path}`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.auth-shell', { timeout: 30_000 });
  await page.waitForTimeout(500);
};

/**
 * 管理端登录页是**一张独立页面**（第 119 批从农户外壳里拆出来的），
 * 所以等的是它自己的根节点 `.admin-login`，不是 `.auth-shell`。
 */
const gotoAdminLogin = async () => {
  await page.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.admin-login', { timeout: 30_000 });
  await page.waitForTimeout(500);
};

// ============================================================================
// 一、农户侧四个页面：中英各查一遍"没有后台味"
// ============================================================================
const USER_PAGES = ['/login', '/register', '/forgot-password', '/reset-password'];
for (const locale of ['zh', 'en']) {
  for (const path of USER_PAGES) {
    await page.addInitScript((value) => localStorage.setItem('app_locale', value), locale);
    await gotoAuth(path);
    const text = await bodyText();
    const title = await page.title();
    const hit = CONSOLE_WORDS.exec(text) || CONSOLE_WORDS.exec(title);
    check(
      `${path}（${locale}）无"后台/客服"字样`,
      !hit && !CONSOLE_WORDS.test(title),
      hit ? `命中「${hit[0]}」` : `title="${title}"`,
    );
    // 农户侧应该是 user 气质的外壳
    const isUserShell = await page.locator('.auth-shell--user').count();
    const chips = await page.locator('.auth-chip').count();
    check(`${path}（${locale}）是农户侧外壳（含能力胶囊）`, isUserShell === 1 && chips >= 3, `胶囊 ${chips} 个`);
    // 英文界面不该漏中文（第 78/116 批的老问题：外壳翻了、页面没翻）
    if (locale === 'en') {
      const cjk = text.split('\n').map((line) => line.trim()).filter((line) => /[\u4e00-\u9fff]/.test(line));
      check(`${path}（en）正文无中文`, cjk.length === 0, cjk.slice(0, 3).join(' | '));
    }
  }
}

// 页签标题
await page.addInitScript(() => localStorage.setItem('app_locale', 'zh'));
await gotoAuth('/login');
check('登录页签是「登录」不是「客服登录」', (await page.title()).startsWith('登录'), await page.title());
await gotoAuth('/register');
check('注册页签是「注册」不是「客服注册」', (await page.title()).startsWith('注册'), await page.title());

// 农户登录页的注册入口（表单下方，不是顶栏）
await gotoAuth('/login');
const cardActions = await page.locator('.auth-card-actions').innerText().catch(() => '');
check('注册入口在表单下方', /注册/.test(cardActions), cardActions.replace(/\s+/g, ' ').trim());

// 空表单时主按钮必须是"活"的
// （第 116 批实测抓到的回归：`passwordMismatch` 返回空字符串 → `:disabled=""` 生效 →
//   刚打开注册页时「创建账号」是灰的，用户以为按钮坏了）
await gotoAuth('/register');
const registerBtnDisabled = await page.locator('.auth-submit').first().isDisabled();
check('注册页空表单时「创建账号」不是灰的死按钮', registerBtnDisabled === false, `disabled=${registerBtnDisabled}`);
await gotoAuth('/reset-password');
const resetBtnDisabled = await page.locator('.auth-submit').first().isDisabled().catch(() => null);
check('重置密码页空表单时主按钮可用', resetBtnDisabled === false, `disabled=${resetBtnDisabled}`);

// ============================================================================
// 二、管理端入口：**另一张页面**（不是农户登录页的变体）
// ============================================================================
await gotoAdminLogin();
const adminText = await bodyText();
const agentHit = AGENT_WORDS.exec(adminText);
check('管理端登录页无"客服/坐席/工单"字样', !agentHit, agentHit ? `命中「${agentHit[0]}」` : '');

// 这是本批的核心要求：两页必须是**两套界面**，不是同一个外壳换文案
const isolation = await page.evaluate(() => ({
  adminRoot: document.querySelectorAll('.admin-login').length,
  userShell: document.querySelectorAll('.auth-shell').length,
  userHero: document.querySelectorAll('.auth-hero').length,
  userChips: document.querySelectorAll('.auth-chip').length,
  adminOwnInputs: document.querySelectorAll('.al-input').length,
}));
check(
  '管理端是独立页面（不套农户外壳）',
  isolation.adminRoot === 1 && isolation.userShell === 0 && isolation.userHero === 0 && isolation.userChips === 0,
  `admin-login=${isolation.adminRoot} auth-shell=${isolation.userShell} hero=${isolation.userHero} 胶囊=${isolation.userChips}`,
);
check('管理端用自己的表单控件（al- 前缀）', isolation.adminOwnInputs === 2, `${isolation.adminOwnInputs} 个输入框`);

check('管理端没有自助注册入口', !/立即注册|Sign up/i.test(adminText), '');
check('管理端点明是管理后台/管理员登录', /管理员登录/.test(adminText) && /管理后台/.test(adminText), '');
// 脚注也要是管理员口径（第 116 批实测踩过：外壳脚注还是农户那句"病害识别、百科查询"）
const adminCardFoot = await page.locator('.admin-login-note').innerText().catch(() => '');
check('管理端脚注是管理员口径', /超级管理员|授权/.test(adminCardFoot), adminCardFoot.replace(/\s+/g, ' ').trim());
const adminTitle = await page.title();
check('管理端页签是「管理员登录」', adminTitle.startsWith('管理员登录'), adminTitle);

// 管理端的英文界面同样不该漏中文
await page.addInitScript((value) => localStorage.setItem('app_locale', value), 'en');
await gotoAdminLogin();
const adminEnText = await bodyText();
const adminCjk = adminEnText.split('\n').map((line) => line.trim()).filter((line) => /[\u4e00-\u9fff]/.test(line));
check('管理端（en）正文无中文', adminCjk.length === 0, adminCjk.slice(0, 3).join(' | '));
await page.addInitScript((value) => localStorage.setItem('app_locale', value), 'zh');
await gotoAdminLogin();

// 管理端在手机宽度下也不能溢出（它是"整屏 + 居中卡片"，卡片比农户侧的窄，
// 但要确认 390px 下不横向滚动、输入框仍可交互）
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(500);
const adminMobile = await page.evaluate(() => ({
  overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
  cardWidth: Math.round(document.querySelector('.admin-login-card').getBoundingClientRect().width),
  viewport: window.innerWidth,
}));
check(
  '管理端 390px 不横向溢出、卡片放得下',
  !adminMobile.overflow && adminMobile.cardWidth <= adminMobile.viewport,
  `卡片 ${adminMobile.cardWidth}px / 视口 ${adminMobile.viewport}px`,
);
await page.screenshot({ path: 'dsh-shots/auth-login-admin-mobile.png', fullPage: true });
await page.setViewportSize({ width: 1440, height: 1000 });

// ============================================================================
// 三、登录后的去向：农户→首页，管理员→数据看板
// ============================================================================
const fillAndSubmit = async (account) => {
  await page.locator('#username').fill(account);
  await page.locator('#password').fill(password);
  await page.locator('button[type="submit"]').first().click();
};

// ③-a 农户登录 → 首页
await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('auth_token'); });
await gotoAuth('/login');
await fillAndSubmit(userName);
await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 25_000 }).catch(() => {});
check('农户登录后落在首页', new URL(page.url()).pathname === '/', page.url().replace(UI, ''));

// ③-b 带着 ?redirect= 登录 → 回到被拦下的那一页（第 116 批新行为：
//     改前 store 里写死 `push('/')`，从 /pests 被弹回来的人登录后又得自己再点一次）
await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('auth_token'); });
await gotoAuth('/login?redirect=%2Fpests&reason=loginRequired');
await fillAndSubmit(userName);
await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 25_000 }).catch(() => {});
check('农户带 redirect 登录后回到原目标', new URL(page.url()).pathname === '/pests', page.url().replace(UI, ''));

// ③-b2 redirect 只认站内路径：`//evil.com` 这类不能把人带走（开放重定向）
await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('auth_token'); });
await gotoAuth('/login?redirect=%2F%2Fevil.example.com');
await fillAndSubmit(userName);
await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 25_000 }).catch(() => {});
const afterEvil = new URL(page.url());
check('站外 redirect 被忽略（落回首页）',
  afterEvil.pathname === '/' && afterEvil.host === new URL(UI).host,
  page.url().replace(UI, ''));

// ③-c 管理员登录 → 数据看板
await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('auth_token'); });
await gotoAdminLogin();
await fillAndSubmit(adminName);
await page.waitForURL(/\/admin\/dashboard/, { timeout: 25_000 }).catch(() => {});
check('管理员登录后落在数据看板', /\/admin\/dashboard/.test(page.url()), page.url().replace(UI, ''));

// ③-c 普通账号误入管理入口 → 提示 + 首页
await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('auth_token'); });
await gotoAdminLogin();
await fillAndSubmit(userName);
await page.waitForURL((url) => !url.pathname.startsWith('/admin/login'), { timeout: 25_000 }).catch(() => {});
const warningText = await page.locator('.el-message').innerText().catch(() => '');
check('普通账号误入管理入口时被说明并送回首页',
  new URL(page.url()).pathname === '/' && /不是管理员/.test(warningText),
  `落在 ${new URL(page.url()).pathname}｜提示「${warningText.replace(/\s+/g, ' ').trim()}」`);

// ============================================================================
// 四、未登录访问受保护页：普通页→/login，管理页→/admin/login
// ============================================================================
const anonymousContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const anon = await anonymousContext.newPage();
await anon.goto(`${UI}/pests`, { waitUntil: 'domcontentloaded' });
await anon.waitForURL(/\/login/, { timeout: 20_000 }).catch(() => {});
const anonUrl = new URL(anon.url());
check('匿名访问 /pests → 农户登录页',
  anonUrl.pathname === '/login' && anonUrl.searchParams.get('reason') === 'loginRequired',
  anon.url().replace(UI, ''));

await anon.goto(`${UI}/admin/dashboard`, { waitUntil: 'domcontentloaded' });
await anon.waitForURL(/\/login/, { timeout: 20_000 }).catch(() => {});
const adminAnonUrl = new URL(anon.url());
check('匿名访问 /admin/dashboard → 管理端登录页',
  adminAnonUrl.pathname === '/admin/login'
    && adminAnonUrl.searchParams.get('reason') === 'loginRequired'
    && adminAnonUrl.searchParams.get('redirect') === '/admin/dashboard',
  anon.url().replace(UI, ''));
await anonymousContext.close();

// ============================================================================
// 五、留证截图 + 移动端
// ============================================================================
await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('auth_token'); });
await page.setViewportSize({ width: 1440, height: 900 });
await page.addInitScript(() => localStorage.setItem('app_locale', 'zh'));
await gotoAuth('/login');
await page.screenshot({ path: 'dsh-shots/auth-login-user.png' });
await gotoAuth('/register');
await page.screenshot({ path: 'dsh-shots/auth-register.png' });
await gotoAdminLogin();
await page.screenshot({ path: 'dsh-shots/auth-login-admin.png' });

// 英文界面留一张（第 78 批那类"中文浏览器 + 英文界面"的问题只靠断言容易漏画面）
await page.addInitScript((value) => localStorage.setItem('app_locale', value), 'en');
await gotoAuth('/login');
await page.screenshot({ path: 'dsh-shots/auth-login-en.png' });
await page.addInitScript((value) => localStorage.setItem('app_locale', value), 'zh');

await page.setViewportSize({ width: 390, height: 844 });
await gotoAuth('/login');
const mobileText = await bodyText();
check('手机宽度下农户登录页仍带品牌横幅',
  (await page.locator('.auth-hero-intro h2').count()) === 1 && !/客服|工作台/.test(mobileText),
  `h2="${(await page.locator('.auth-hero-intro h2').innerText().catch(() => '')).trim()}"`);
await page.screenshot({ path: 'dsh-shots/auth-login-mobile.png', fullPage: true });

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();

// ---- 收尾：清理临时账号（真正的清理逻辑在 cleanupAccounts，exit 钩子也会兜一次） ----
cleanupAccounts();

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} 项通过`);
process.exit(failed.length ? 1 : 0);
