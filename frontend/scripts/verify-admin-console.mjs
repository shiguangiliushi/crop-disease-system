/**
 * 管理后台外壳专项验证：`/admin/**` 必须是**独立的一套界面**（第 117 批）
 *
 * 为什么需要它
 * ---------------------------------------------------------------------------
 * 第 116 批把登录入口分开了，但管理员登录后看到的仍是农户端页面：
 * 主站顶栏（首页/识别/百科/历史…）+ 页脚（快速导航/农事工具/联系我们），
 * 管理功能只是顶栏里的一个下拉。这一批给 `/admin/**` 做了独立外壳
 * （左侧管理侧栏 + 顶部条，见 components/AdminLayout.vue）。
 *
 * 断言：
 *   ① 管理员登录后落在数据看板，且**页面上没有农户端顶栏与页脚**；
 *   ② 外壳在：侧栏 + 5 条导航 + 面包屑 + 身份 + 退出登录；
 *   ③ 5 条导航逐条点过去：URL 对、外壳还在、对应页面真的渲染出来了；
 *   ④ 退出登录回**管理员登录页**（不是农户登录页）；
 *   ⑤ 窄屏（390）：侧栏收起、汉堡键可展开抽屉，内容不被挤没；
 *   ⑥ 农户端不受影响：/pests 仍是主站顶栏 + 页脚，且没有管理侧栏；
 *   ⑦ 普通用户进不了管理区（守卫拦截），也就看不到外壳。
 *
 * 前置：后端 8000、前端 5173 均在运行。
 * 用法（在 frontend 目录下）：node scripts/verify-admin-console.mjs
 * 退出码：全部通过 0，任一失败 1。
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = process.env.AUDIT_UI || 'http://127.0.0.1:5173';

const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

// ---- 临时账号（Django 直建，避开注册限速；跑完即删） ----
const suffix = Math.random().toString(36).slice(2, 7);
const adminName = `zze2e_console_${suffix}`;
const userName = `zze2e_plain_${suffix}`;
const password = 'ZzE2e!2026pw';

try {
  clearThrottle();
  console.log(runDjango([
    'from django.contrib.auth import get_user_model',
    'U = get_user_model()',
    `U.objects.create_user(username='${userName}', password='${password}')`,
    `admin = U.objects.create_user(username='${adminName}', password='${password}')`,
    'admin.is_staff = True',
    'admin.save()',
    "print('temp accounts ready')",
  ]));
} catch (error) {
  console.error(`造临时账号失败：${String(error).slice(0, 300)}`);
  process.exit(2);
}
console.log(`临时账号：${adminName}（管理员）/ ${userName}（普通用户）`);

/** 清理临时账号。挂在 process exit 上：脚本中途抛异常也会清，不留残留行。 */
const cleanupAccounts = () => {
  try {
    const out = runDjango([
      'from django.contrib.auth import get_user_model',
      `print('deleted:', get_user_model().objects.filter(username__in=['${adminName}', '${userName}']).delete()[0])`,
    ]);
    console.log(`\n临时账号清理：${out}`);
  } catch (error) {
    console.log(`\n⚠️ 自动清理失败（${String(error).slice(0, 160)}），请手动删除 ${adminName} / ${userName}`);
  }
};
process.on('exit', cleanupAccounts);

/** 侧栏里应该有这 5 条（顺序即侧栏顺序） */
const NAV = [
  { to: '/admin/dashboard', label: '数据看板', root: '.dashboard-page' },
  { to: '/admin/users', label: '用户管理', root: '.admin-users' },
  { to: '/admin/review', label: '内容审核', root: '.review-page' },
  { to: '/admin/news', label: '新闻管理', root: '.news-management' },
  { to: '/admin/feedback', label: '意见反馈管理', root: '.admin-feedback' },
];

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 950 }, locale: 'zh-CN' });
const page = await context.newPage();
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));

const login = async (account) => {
  // 登录接口限流是 10/分钟（按 IP）。这个脚本一轮要登 3 次，反复跑很容易撞 429，
  // 而 429 的表现是"表单提交后没反应" —— 极容易被误读成"登录页坏了"，所以先清一次。
  clearThrottle();
  await page.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
  // 第 119 批：管理端登录是**独立页面**（`.admin-login`），不再是农户外壳 `.auth-shell`
  await page.waitForSelector('.admin-login', { timeout: 30_000 });
  await page.locator('#username').fill(account);
  await page.locator('#password').fill(password);
  await page.locator('button[type="submit"]').first().click();
  try {
    await page.waitForURL((url) => !url.pathname.startsWith('/admin/login'), { timeout: 25_000 });
  } catch {
    // 把页面上的错误提示带出来，别只丢一个 TimeoutError
    const alert = await page.locator('.auth-alert').innerText().catch(() => '(页面上没有错误提示)');
    throw new Error(`登录未跳转（停在 ${page.url()}）：${alert.replace(/\s+/g, ' ').trim()}`);
  }
  await page.waitForTimeout(1200);
};

// ============================================================================
// ① 登录后落在数据看板，且没有农户端顶栏/页脚
// ============================================================================
await login(adminName);
check('管理员登录后落在数据看板', /\/admin\/dashboard/.test(page.url()), page.url().replace(UI, ''));
const chrome = await page.evaluate(() => ({
  console: document.querySelectorAll('.admin-console').length,
  sidebar: document.querySelectorAll('.admin-sidebar').length,
  nav: document.querySelectorAll('.admin-nav-item').length,
  header: document.querySelectorAll('.app-header').length,
  footer: document.querySelectorAll('.app-footer').length,
  crumb: (document.querySelector('.admin-crumb')?.innerText || '').replace(/\s+/g, ' ').trim(),
  who: (document.querySelector('.admin-who')?.innerText || '').replace(/\s+/g, ' ').trim(),
}));
check('外壳在（.admin-console + 侧栏）', chrome.console === 1 && chrome.sidebar === 1, `侧栏 ${chrome.sidebar} 个`);
check('侧栏是 6 条管理导航', chrome.nav === 6, `${chrome.nav} 条`);
check('不显示农户端顶栏', chrome.header === 0, `.app-header ${chrome.header} 个`);
check('不显示农户端页脚', chrome.footer === 0, `.app-footer ${chrome.footer} 个`);
check('面包屑显示当前页', chrome.crumb.includes('管理后台') && chrome.crumb.includes('数据看板'), chrome.crumb);
check('顶部条显示身份', chrome.who.includes(adminName) && chrome.who.includes('管理员'), chrome.who);
check(
  '数据看板页面真的渲染了',
  await page.locator('.dashboard-page .admin-hero').first().isVisible(),
  '',
);

await page.screenshot({ path: 'dsh-shots/admin-console-dashboard.png' });

// ============================================================================
// ② 5 条导航逐条点过去
// ============================================================================
for (const item of NAV) {
  await page.locator(`.admin-nav-item[href="${item.to}"]`).click();
  await page.waitForURL(new RegExp(item.to.replace(/\//g, '\\/')), { timeout: 20_000 }).catch(() => {});
  await page.waitForTimeout(900);
  const state = await page.evaluate((rootSel) => ({
    path: location.pathname,
    hasConsole: document.querySelectorAll('.admin-console').length === 1,
    hasHeader: document.querySelectorAll('.app-header').length,
    hasRoot: document.querySelectorAll(rootSel).length > 0,
    crumb: (document.querySelector('.admin-crumb-current')?.innerText || '').trim(),
  }), item.root);
  check(
    `侧栏「${item.label}」→ 页面正常且仍在后台外壳内`,
    state.path === item.to && state.hasConsole && state.hasRoot && state.hasHeader === 0,
    `${state.path}｜面包屑「${state.crumb}」`,
  );
  if (item.to === '/admin/users') {
    // 留证截图：等表格真的出数据（否则截到的是"加载中"的骨架，看不出页面对不对）
    await page.waitForSelector('.el-table__row', { timeout: 20_000 }).catch(() => {});
    await page.waitForTimeout(600);
    await page.screenshot({ path: 'dsh-shots/admin-console-users.png' });
  }
  if (item.to === '/admin/review') {
    await page.screenshot({ path: 'dsh-shots/admin-console-review.png' });
  }
}

// ============================================================================
// ③ 退出登录 → 管理员登录页
// ============================================================================
await page.locator('.admin-logout').click();
await page.waitForURL(/\/admin\/login/, { timeout: 20_000 }).catch(() => {});
await page.waitForSelector('.admin-login', { timeout: 15_000 }).catch(() => {});
check(
  '退出登录回管理员登录页（且是那个独立页面）',
  page.url().includes('/admin/login') && (await page.locator('.admin-login').count()) === 1,
  page.url().replace(UI, ''),
);

// ============================================================================
// ④ 普通用户：进不了管理区
// ============================================================================
await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('auth_token'); });
await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.auth-shell', { timeout: 30_000 });
await page.locator('#username').fill(userName);
await page.locator('#password').fill(password);
await page.locator('button[type="submit"]').first().click();
await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 25_000 });
await page.waitForTimeout(800);
await page.goto(`${UI}/admin/dashboard`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1200);
const plainState = await page.evaluate(() => ({
  path: location.pathname,
  console: document.querySelectorAll('.admin-console').length,
}));
check(
  '普通用户直接开 /admin/dashboard：被挡回、看不到外壳',
  plainState.path !== '/admin/dashboard' && plainState.console === 0,
  `落在 ${plainState.path}`,
);

// ============================================================================
// ⑤ 农户端不受影响
// ============================================================================
await page.goto(`${UI}/pests`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.pest-grid', { timeout: 30_000 }).catch(() => {});
await page.waitForTimeout(600);
const siteState = await page.evaluate(() => ({
  header: document.querySelectorAll('.app-header').length,
  footer: document.querySelectorAll('.app-footer').length,
  console: document.querySelectorAll('.admin-console').length,
}));
check(
  '农户端 /pests 仍是主站顶栏 + 页脚、没有管理侧栏',
  siteState.header === 1 && siteState.footer === 1 && siteState.console === 0,
  `header=${siteState.header} footer=${siteState.footer} console=${siteState.console}`,
);

// ============================================================================
// ⑥ 窄屏：侧栏收成抽屉
// ============================================================================
await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('auth_token'); });
await login(adminName);
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(700);
const narrow = await page.evaluate(() => {
  const bar = document.querySelector('.admin-sidebar');
  const box = bar.getBoundingClientRect();
  return {
    offscreen: box.right <= 1 || box.left < 0,
    burgerVisible: getComputedStyle(document.querySelector('.admin-burger')).display !== 'none',
    contentWidth: Math.round(document.querySelector('.admin-content').getBoundingClientRect().width),
  };
});
check('窄屏：侧栏收起、汉堡键出现', narrow.offscreen && narrow.burgerVisible, `内容宽 ${narrow.contentWidth}px`);
await page.locator('.admin-burger').click();
await page.waitForTimeout(500);
const opened = await page.evaluate(() => {
  const box = document.querySelector('.admin-sidebar').getBoundingClientRect();
  return { visible: box.left >= -1 && box.width > 200, mask: document.querySelectorAll('.admin-drawer-mask').length };
});
check('窄屏：点汉堡键能展开抽屉（带遮罩）', opened.visible && opened.mask === 1, '');
await page.screenshot({ path: 'dsh-shots/admin-console-mobile.png' });
// 点遮罩关抽屉：不能用 locator.click()（它会点元素正中央，而 390px 宽时
// 侧栏占 236px，正中央落在侧栏上，Playwright 会判定"被遮挡"而拒绝点击）
await page.mouse.click(360, 420);
await page.waitForTimeout(400);
check('窄屏：点遮罩能收起抽屉', (await page.locator('.admin-drawer-mask').count()) === 0, '');

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

// ============================================================================
// ⑦ 侧栏可折叠（把宽度还给宽表格 —— 用户管理的列 min-width 合计 1406px）
// ============================================================================
await page.setViewportSize({ width: 1440, height: 950 });
await page.evaluate(() => localStorage.removeItem('admin_sidebar_collapsed'));
await page.goto(`${UI}/admin/users`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.admin-sidebar', { timeout: 20_000 });
await page.waitForTimeout(600);
const expanded = await page.evaluate(() => ({
  width: Math.round(document.querySelector('.admin-sidebar').getBoundingClientRect().width),
  labelsVisible: [...document.querySelectorAll('.admin-nav-item span')].filter((el) => el.offsetParent !== null).length,
}));
await page.locator('.admin-collapse').click();
await page.waitForTimeout(500);
const collapsedState = await page.evaluate(() => ({
  width: Math.round(document.querySelector('.admin-sidebar').getBoundingClientRect().width),
  labelsVisible: [...document.querySelectorAll('.admin-nav-item span')].filter((el) => el.offsetParent !== null).length,
  contentWidth: Math.round(document.querySelector('.admin-content').getBoundingClientRect().width),
  stored: localStorage.getItem('admin_sidebar_collapsed'),
}));
check(
  '侧栏可折叠成图标栏（宽度还给内容）',
  collapsedState.width < expanded.width && collapsedState.labelsVisible === 0 && expanded.labelsVisible === 6,
  `${expanded.width}px → ${collapsedState.width}px；内容区 ${collapsedState.contentWidth}px`,
);
check('折叠状态会记住（刷新后仍是折叠）', collapsedState.stored === '1', `localStorage=${collapsedState.stored}`);
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForSelector('.admin-sidebar', { timeout: 20_000 });
await page.waitForTimeout(600);
const afterReload = await page.evaluate(() =>
  Math.round(document.querySelector('.admin-sidebar').getBoundingClientRect().width));
check('刷新后侧栏仍是折叠态', afterReload === collapsedState.width, `${afterReload}px`);
await page.screenshot({ path: 'dsh-shots/admin-console-collapsed.png' });
await page.locator('.admin-collapse').click();
await page.waitForTimeout(400);

// ============================================================================
// ⑧ 密码重置：给**没绑邮箱**的账号签发一次性链接，并真的用它改密码（第 120 批）
// ----------------------------------------------------------------------------
// 这是"管理员忘了密码"那条断路的验收：自助找回密码只在账号绑了邮箱时才发信，
// 没绑邮箱时后端按防枚举策略静默什么都不做（页面却显示"已发送"）。
// 这里走完整链路：管理员点「重置密码」→ 拿到链接 → 打开链接设新密码 → 新密码能登录。
// ============================================================================
const resetTarget = `zze2e_reset_${suffix}`;
runDjango([
  'from django.contrib.auth import get_user_model',
  'U = get_user_model()',
  `U.objects.filter(username='${resetTarget}').delete()`,
  `U.objects.create_user(username='${resetTarget}', password='old-pw-123', email='')`,
  "print('reset target ready')",
]);

await page.goto(`${UI}/admin/users?search=${resetTarget}&page_size=10`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.el-table__row', { timeout: 25_000 });
await page.waitForTimeout(800);
await page.locator('.el-table__row button', { hasText: '重置密码' }).first().click();
await page.waitForSelector('.reset-link-input', { timeout: 20_000 }).catch(() => {});
const resetUrl = await page.locator('.reset-link-input').inputValue().catch(() => '');
check(
  '管理员能给「没绑邮箱」的账号签发重置链接',
  /\/reset-password\?uid=.+&token=.+/.test(resetUrl),
  resetUrl ? resetUrl.replace(UI, '').slice(0, 76) : '(没拿到链接)',
);
const noEmailHint = await page.locator('.reset-link-warning').innerText().catch(() => '');
check('弹窗如实说明"该账号没绑邮箱"', /没有绑定邮箱/.test(noEmailHint), noEmailHint.replace(/\s+/g, ' ').slice(0, 60));
await page.screenshot({ path: 'dsh-shots/admin-reset-link.png' });
await page.keyboard.press('Escape');
await page.waitForTimeout(400);

// 真的用这条链接设新密码（新开一个浏览器上下文，模拟"本人打开链接"）
{
  const freshContext = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'zh-CN' });
  const fresh = await freshContext.newPage();
  await fresh.goto(resetUrl, { waitUntil: 'domcontentloaded' });
  await fresh.waitForSelector('#newPassword', { timeout: 25_000 });
  await fresh.locator('#newPassword').fill('brand-new-pw-9');
  await fresh.locator('#confirmPassword').fill('brand-new-pw-9');
  await fresh.locator('button[type="submit"]').first().click();
  await fresh.waitForTimeout(2500);

  // 用新密码登录（普通账号在管理端登录会被送回首页，这是设计；
  // 关键是"密码真的换了、而且能登进去"）
  await fresh.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
  await fresh.waitForSelector('.admin-login', { timeout: 25_000 });
  await fresh.locator('#username').fill(resetTarget);
  await fresh.locator('#password').fill('brand-new-pw-9');
  await fresh.locator('button[type="submit"]').first().click();
  await fresh.waitForURL((url) => !url.pathname.startsWith('/admin/login'), { timeout: 25_000 }).catch(() => {});
  const landed = new URL(fresh.url()).pathname;
  check('用重置链接设的新密码确实能登录', landed === '/' || landed === '/admin/dashboard', `落在 ${landed}`);
  await freshContext.close();
}

// 管理端登录页要把"没绑邮箱时该怎么办"写清楚（否则会干等一封不会来的邮件）
await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('auth_token'); });
await page.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.admin-login', { timeout: 25_000 });
const forgotHint = await page.locator('.al-forgot-hint').innerText().catch(() => '');
check(
  '管理端登录页说明了忘记密码的两条路',
  /超级管理员/.test(forgotHint) && /邮箱/.test(forgotHint),
  forgotHint.replace(/\s+/g, ' ').slice(0, 70),
);

runDjango([
  'from django.contrib.auth import get_user_model',
  `print('reset target deleted:', get_user_model().objects.filter(username='${resetTarget}').delete()[0])`,
]);

// ============================================================================
// ⑨ 旧的新闻深链必须落在管理后台里（第 121 批）
// ----------------------------------------------------------------------------
// `/news/create`、`/news/:id/edit` 过去直接渲染**农户端外观**的行业动态页 + 弹窗，
// 而它们都要管理员权限。现在重定向到 /admin/news 并由它按 ?action= 打开自己的弹窗。
// ============================================================================
const newsTitle = `zze2e_news_${suffix}`;
const newsId = Number(runDjango([
  'from api.models import News',
  `News.objects.filter(title='${newsTitle}').delete()`,
  `n = News.objects.create(title='${newsTitle}', content='<p>e2e</p>', category='notice', is_published=True)`,
  'print(n.id)',
]).trim().split('\n').pop());

// 先看"匿名点旧链接"这条链：应当被守卫送到管理端登录页，并带上回到目标页的信息
await page.goto(`${UI}/news/create`, { waitUntil: 'domcontentloaded' });
await page.waitForURL(/\/admin\/login/, { timeout: 25_000 }).catch(() => {});
const anonDeep = new URL(page.url());
check(
  '匿名访问 /news/create → 管理端登录页（带着回跳目标）',
  anonDeep.pathname === '/admin/login'
    && (anonDeep.searchParams.get('redirect') || '').includes('/admin/news')
    && anonDeep.searchParams.get('reason') === 'loginRequired',
  page.url().replace(UI, ''),
);

// 登录后应当**直接落到管理后台并打开新增弹窗**（一次走完：守卫 → 重定向 → 弹窗）
await page.waitForSelector('.admin-login', { timeout: 25_000 });
clearThrottle();   // 登录接口 10/分钟（按 IP）：这一轮已经登了好几次，先清免得撞 429
await page.locator('#username').fill(adminName);
await page.locator('#password').fill(password);
await page.locator('button[type="submit"]').first().click();
// ⚠️ 谓词必须看 **pathname**，不能用 `/\/admin\/news/` 这种正则 —— 登录页的 URL 里
//    正好带着 `?redirect=/admin/news?action=create`，正则会当场匹配成功（假通过）。
await page.waitForURL((url) => url.pathname === '/admin/news', { timeout: 25_000 }).catch(async () => {
  const alert = await page.locator('.al-alert').innerText().catch(() => '(无提示)');
  console.log(`   ↳ 登录未跳转，页面提示：${alert.replace(/\s+/g, ' ').trim()}`);
});
await page.waitForSelector('.el-dialog', { timeout: 15_000 }).catch(() => {});
await page.waitForTimeout(900);
const createDeepLink = await page.evaluate(() => ({
  path: location.pathname,
  inConsole: document.querySelectorAll('.admin-console').length === 1,
  farmerHeader: document.querySelectorAll('.app-header').length,
  dialogOpen: document.querySelectorAll('.el-dialog').length > 0,
  dialogText: (document.querySelector('.el-dialog')?.innerText || '').slice(0, 40).replace(/\s+/g, ' '),
  query: location.search,
}));
check(
  '登录后落在管理后台并打开新增弹窗',
  createDeepLink.path === '/admin/news' && createDeepLink.inConsole
    && createDeepLink.farmerHeader === 0 && createDeepLink.dialogOpen,
  `${createDeepLink.path}${createDeepLink.query}｜弹窗「${createDeepLink.dialogText}」`,
);
check('处理完把 ?action= 从地址栏清掉', !/action=/.test(createDeepLink.query), `query="${createDeepLink.query}"`);
await page.keyboard.press('Escape');
await page.waitForTimeout(400);

await page.goto(`${UI}/news/${newsId}/edit`, { waitUntil: 'domcontentloaded' });
// 同样只看 pathname（见上面的说明）
await page.waitForURL((url) => url.pathname === '/admin/news', { timeout: 25_000 }).catch(() => {});
await page.waitForTimeout(1500);
const editDeepLink = await page.evaluate(() => ({
  path: location.pathname,
  inConsole: document.querySelectorAll('.admin-console').length === 1,
  dialogOpen: document.querySelectorAll('.el-dialog').length > 0,
  dialogText: (document.querySelector('.el-dialog')?.innerText || '').replace(/\s+/g, ' ').slice(0, 60),
  // ⚠️ 标题在 <input> 的 value 里，**不在 innerText 里** —— 只读文本会漏掉它
  inputValues: [...document.querySelectorAll('.el-dialog input')].map((el) => el.value).filter(Boolean),
}));
check(
  '/news/:id/edit 重定向进管理后台并带上那篇新闻',
  editDeepLink.path === '/admin/news' && editDeepLink.inConsole
    && editDeepLink.dialogOpen && editDeepLink.inputValues.includes(newsTitle),
  `${editDeepLink.path}｜弹窗「${editDeepLink.dialogText}」｜标题值=${JSON.stringify(editDeepLink.inputValues.slice(0, 3))}`,
);

runDjango([
  'from api.models import News',
  `print('temp news deleted:', News.objects.filter(title='${newsTitle}').delete()[0])`,
]);

// ============================================================================
// ⑩ 农户端的行业动态页（NewsView）自己那套没被打坏
// ----------------------------------------------------------------------------
// 第 121 批顺手删掉了 NewsView 里"按路由进入创建/编辑模式"的死代码
// （那两条深链已经重定向走了）。这里确认它还认得**页内按钮**这条路：
// 点「添加新闻」→ 就地弹窗（不跳路由），这是农户端管理员维护新闻的正常入口。
// ============================================================================
await page.goto(`${UI}/news`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.news-container', { timeout: 25_000 });
await page.waitForTimeout(1200);
await page.locator('.add-news-btn').first().click();
await page.waitForTimeout(800);
const siteNewsDialog = await page.evaluate(() => ({
  path: location.pathname,
  dialogOpen: document.querySelectorAll('.el-dialog').length > 0,
  farmerHeader: document.querySelectorAll('.app-header').length,
  dialogText: (document.querySelector('.el-dialog')?.innerText || '').replace(/\s+/g, ' ').slice(0, 24),
}));
check(
  '农户端 /news 的「添加新闻」仍是就地弹窗（没跳路由、仍在主站外壳里）',
  siteNewsDialog.path === '/news' && siteNewsDialog.dialogOpen && siteNewsDialog.farmerHeader === 1,
  `${siteNewsDialog.path}｜弹窗「${siteNewsDialog.dialogText}」`,
);

// ============================================================================
// ⑪ 病害百科维护（第 122 批）：从农户端页面搬进后台，并在后台完成一套增删
// ----------------------------------------------------------------------------
// 改前：维护入口长在**农户端**的 /pests 上（顶部「管理员模式」工具条 + 卡片按钮）。
// 现在它是侧栏里的一页；这里验证"农户页干净了 + 后台这一页真的能增能删"。
// ============================================================================
const pestName = `zze2e病害_${suffix}`;
const pestIdent = `zze2e_pest_${suffix}`;

// ⑪-a 农户端 /pests 不该再出现管理员工具条与卡片按钮（对管理员也一样）
await page.goto(`${UI}/pests`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.pest-grid', { timeout: 25_000 });
await page.waitForTimeout(600);
const siteWiki = await page.evaluate(() => ({
  toolbar: document.querySelectorAll('.admin-toolbar').length,
  cardAdmin: document.querySelectorAll('.card-admin-actions').length,
  cards: document.querySelectorAll('.pest-card').length,
  text: (document.body.innerText || '').includes('管理员模式'),
}));
check(
  '农户端 /pests 已是纯阅读页（没有管理员工具条/卡片按钮/"管理员模式"字样）',
  siteWiki.toolbar === 0 && siteWiki.cardAdmin === 0 && !siteWiki.text && siteWiki.cards > 0,
  `工具条=${siteWiki.toolbar} 卡片按钮=${siteWiki.cardAdmin} 卡片=${siteWiki.cards}`,
);

// ⑪-b 后台侧栏里应当有「病害百科维护」，且页面能列出词条
await page.goto(`${UI}/admin/pests`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.pest-admin', { timeout: 25_000 });
await page.waitForSelector('.el-table__row', { timeout: 25_000 }).catch(() => {});
await page.waitForTimeout(800);
const pestAdmin = await page.evaluate(() => ({
  navItems: document.querySelectorAll('.admin-nav-item').length,
  hasNav: [...document.querySelectorAll('.admin-nav-item')].some((el) => el.innerText.includes('病害百科维护')),
  rows: document.querySelectorAll('.el-table__row').length,
  inConsole: document.querySelectorAll('.admin-console').length === 1,
  farmerHeader: document.querySelectorAll('.app-header').length,
}));
check(
  '侧栏新增「病害百科维护」且页面在后台外壳里',
  pestAdmin.hasNav && pestAdmin.navItems === 6 && pestAdmin.inConsole && pestAdmin.farmerHeader === 0,
  `导航 ${pestAdmin.navItems} 条｜表行 ${pestAdmin.rows}`,
);
check('页面列出了真实词条（表格有行）', pestAdmin.rows > 0, `${pestAdmin.rows} 行`);
await page.screenshot({ path: 'dsh-shots/admin-pests.png' });

// ⑪-c 走一遍完整增删：新增 → 搜到 → 删除
await page.locator('.admin-hero-actions button', { hasText: '新增病害' }).first().click();
await page.waitForSelector('.el-dialog', { timeout: 15_000 });
await page.waitForTimeout(600);

// ⚠️ 不要按 `.el-dialog input` 的**下标**取字段：弹窗里还有下拉框内部 input、
//    图片上传的 file input、防治方法行等，下标一改就填错（第一版就是这么错的）。
//    按 el-form-item 的 label 定位，稳定得多。
const fieldByLabel = (label) => page.locator('.el-dialog .el-form-item', { hasText: label }).first();

await fieldByLabel('病害名称').locator('input').first().fill(pestName);
// 作物类型是「可筛选」的下拉：点开后输入作物名，回车选中第一项（default-first-option）
const cropInput = fieldByLabel('作物类型').locator('.el-select__wrapper').first();
await cropInput.click();
await page.waitForTimeout(500);
await page.locator('.el-select-dropdown__item:visible').first().click();
await page.waitForTimeout(400);
await fieldByLabel('英文标识符').locator('input').first().fill(pestIdent);
await fieldByLabel('症状描述').locator('textarea').first().fill('叶片出现黄斑（自动化体检用，稍后删除）');
await page.waitForTimeout(300);

await page.locator('.el-dialog__footer button').last().click();
await page.waitForTimeout(3000);
const createAlert = await page.locator('.el-dialog .el-form-item__error').allInnerTexts().catch(() => []);
if (createAlert.length) console.log(`   ↳ 新增表单校验提示：${createAlert.join(' / ')}`);

await page.goto(`${UI}/admin/pests?search=${encodeURIComponent(pestName)}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.pest-admin', { timeout: 25_000 });
await page.waitForTimeout(1200);
const created = await page.evaluate(() => ({
  rows: document.querySelectorAll('.el-table__row').length,
  text: (document.querySelector('.el-table__body')?.innerText || '').replace(/\s+/g, ' '),
}));
check(
  '在后台新增的词条能搜到（服务端搜索生效）',
  created.rows === 1 && created.text.includes(pestName),
  `${created.rows} 行｜${created.text.slice(0, 50)}`,
);

// 删除它（确认框 + 校验行数归零）
await page.locator('.el-table__row button', { hasText: '删除' }).first().click();
await page.waitForSelector('.el-message-box', { timeout: 15_000 });
await page.locator('.el-message-box__btns button').last().click();
await page.waitForTimeout(2000);
const afterDelete = await page.evaluate(() => ({
  rows: document.querySelectorAll('.el-table__row').length,
  empty: (document.querySelector('.el-table__empty-text')?.innerText || '').trim(),
}));
check('后台能删除词条（删除后列表为空）', afterDelete.rows === 0, `剩 ${afterDelete.rows} 行｜${afterDelete.empty}`);

// 兜底清理：万一界面删除失败，别把测试词条留在库里
runDjango([
  'from api.models import PestInfo',
  `print('temp pest deleted:', PestInfo.objects.filter(english_identifier='${pestIdent}').delete()[0])`,
]);

// ============================================================================
// ⑫ 失效 token 必须被"请去重新登录"，而不是留在一堆空面板上（第 123 批）
// ----------------------------------------------------------------------------
// 复现用户报的现象：浏览器里存着一个**服务端已不认**的 token（本项目的 Token 有
// 7 天有效期，也可能因为改密码/别处登出被删），于是：
//   通知铃铛、私信未读、当前页面数据 —— 所有请求 401，
//   而 `api/http.js` 原来**没有 401 处理**，页面既不一跳也不提示。
// 现在应当：清登录态 + 送到**对应端**的登录页，并带上 reason=sessionExpired
// （两个登录页都会把它翻成"登录已过期，请重新登录。"）。
// ============================================================================
{
  const deadContext = await browser.newContext({ viewport: { width: 1440, height: 950 }, locale: 'zh-CN' });
  await deadContext.addInitScript(() => {
    // 一个格式合法、但服务端不存在的 token
    sessionStorage.setItem('auth_token', 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef');
    sessionStorage.setItem('user', JSON.stringify({ id: 1, username: 'ghost', is_staff: true }));
  });
  const dead = await deadContext.newPage();

  // ① 管理区：应被送到 /admin/login（不是农户登录页）
  await dead.goto(`${UI}/admin/pests`, { waitUntil: 'domcontentloaded' });
  await dead.waitForURL(/\/admin\/login/, { timeout: 25_000 }).catch(() => {});
  const adminDead = new URL(dead.url());
  check(
    '失效 token 打开管理页 → 送到管理端登录页（带 sessionExpired）',
    adminDead.pathname === '/admin/login'
      && adminDead.searchParams.get('reason') === 'sessionExpired'
      && (adminDead.searchParams.get('redirect') || '').includes('/admin/pests'),
    dead.url().replace(UI, ''),
  );
  const deadHint = await dead.locator('.al-alert, .auth-alert').innerText().catch(() => '');
  check(
    '登录页明确告诉用户"登录已过期"',
    /过期/.test(deadHint),
    deadHint.replace(/\s+/g, ' ').slice(0, 50) || '(没有提示)',
  );

  // ② 农户区：应被送到 /login（不是管理端登录页）
  const dead2 = await deadContext.newPage();
  await dead2.goto(`${UI}/history`, { waitUntil: 'domcontentloaded' });
  await dead2.waitForURL(/\/login/, { timeout: 25_000 }).catch(() => {});
  const farmerDead = new URL(dead2.url());
  check(
    '失效 token 打开普通受保护页 → 送到农户登录页',
    farmerDead.pathname === '/login' && farmerDead.searchParams.get('reason') === 'sessionExpired',
    dead2.url().replace(UI, ''),
  );
  check('跳转后本地 token 已被清掉', !(await dead2.evaluate(() => sessionStorage.getItem('auth_token'))), '');

  await deadContext.close();
}

check('全程无 JS 报错（含重置流程）', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} 项通过`);
process.exit(failed.length ? 1 : 0);
