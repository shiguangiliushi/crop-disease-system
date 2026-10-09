/**
 * 「在后台开通编辑员账号」端到端验证（第 131 批）
 * ============================================================================
 * 这一批把"新建编辑员"从 Django admin 搬进了后台。闭环是：
 *   超管在用户管理里开通 → 拿到**一次性设置密码链接** →（线下发给本人）
 *   → 本人打开链接设密码 → 登录后只看到被授权的模块。
 *
 * 这条链路横跨三个界面（用户管理 / 重置密码 / 管理端登录），
 * 任何一段断了都只有真点一遍才发现，所以这里整条走完。
 *
 * 覆盖：
 *   ① 超管在「新增编辑员」弹窗里填用户名、只勾「新闻管理」→ 开通成功并给出链接
 *   ② 弹窗里明确提示"链接只显示这一次"
 *   ③ （新开浏览器上下文）用该链接设新密码
 *   ④ 用新密码在管理端登录 → 侧栏只有 数据看板 + 新闻管理
 *   ⑤ 直连接口：发新闻 201、改词条 403（模块隔离在开通链路里同样成立）
 *   ⑥ 同一条链接不能再用第二次
 *   ⑦ 非超管看不到「新增编辑员」按钮（staff 管理员登录后页头没有它）
 *   ⑧ 接口护栏：staff 管理员直连开通接口 → 403
 *
 * 用法：node scripts/verify-create-editor.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';
const newPassword = 'EditorSet!2026';

const superName = `zze2e_ce_super_${suffix}`;
const staffName = `zze2e_ce_staff_${suffix}`;
const editorName = `zze2e_ce_${suffix}`;

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
      'from api.models import EditorModuleGrant, News',
      'U = get_user_model()',
      `users = U.objects.filter(username__startswith='zze2e_ce_')`,
      'EditorModuleGrant.objects.filter(user__in=users).delete()',
      'print("cleaned users:", users.delete()[0])',
      'print("cleaned news:", News.objects.filter(title__startswith="zze2e开通").delete()[0])',
    ]);
  } catch (error) {
    // 退出钩子里必须吞异常，否则清理半途而废（第 128 批踩过）
    console.error('清理失败（忽略）:', error?.message || error);
  }
};

process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });

clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'U = get_user_model()',
  `U.objects.create_superuser(username='${superName}', password='${password}', email='', role='ADMIN')`,
  `s = U.objects.create_user(username='${staffName}', password='${password}', is_staff=True, role='ADMIN')`,
  "print('seeded')",
]);

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' });
const page = await context.newPage();
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));

const loginAs = async (target, username, pwd = password) => {
  await target.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
  await target.waitForSelector('.admin-login', { timeout: 30_000 });
  await target.locator('#username').fill(username);
  await target.locator('#password').fill(pwd);
  await target.locator('button[type="submit"]').first().click();
  await target.waitForURL(
    (url) => url.pathname.startsWith('/admin/') && url.pathname !== '/admin/login',
    { timeout: 30_000 },
  );
  await target.waitForSelector('.admin-console', { timeout: 25_000 });
  await target.waitForTimeout(900);
};

const logout = (target) => target.evaluate(() => {
  sessionStorage.clear();
  localStorage.removeItem('auth_token');
});

// ---------------------------------------------------------------------------
// ① 超管开通编辑员（只勾新闻管理）
// ---------------------------------------------------------------------------
clearThrottle();
await loginAs(page, superName);
await page.goto(`${UI}/admin/users`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1200);

const hasButton = await page.locator('.admin-hero-actions button', { hasText: '新增编辑员' }).count();
check('超管在用户管理页能看到「新增编辑员」按钮', hasButton === 1);

await page.locator('.admin-hero-actions button', { hasText: '新增编辑员' }).first().click();
await page.waitForSelector('.el-dialog .el-checkbox-group', { timeout: 15_000 });
await page.locator('.el-dialog input').first().fill(editorName);
// 默认全勾 → 只留「新闻管理」
for (const label of ['内容审核', '病害百科', '意见反馈']) {
  await page.locator('.el-dialog .el-checkbox', { hasText: label }).click();
}
await page.waitForTimeout(300);
await page.locator('.el-dialog__footer button').last().click();
await page.waitForSelector('.reset-link-input', { timeout: 20_000 });
await page.waitForTimeout(500);

const dialogText = await page.evaluate(
  () => (document.querySelector('.el-dialog')?.innerText || '').replace(/\s+/g, ' '),
);
const resetUrl = await page.locator('.reset-link-input').inputValue();
check('开通成功并给出一条设置密码链接', /reset-password\?uid=/.test(resetUrl), resetUrl.replace(UI, ''));
check('弹窗里写明"只显示这一次"', dialogText.includes('只显示这一次'), dialogText.slice(0, 60));
// ⚠️ 名字取错字段会渲染成 `已开通「undefined」` —— 这条断言就是为它加的
//    （接口把用户对象放在 `user` 下，第一版写成 createdEditor.username 就中了）
check('成功提示里带着用户名（不是 undefined）',
  dialogText.includes(editorName) && !dialogText.includes('undefined'), dialogText.slice(0, 50));
check('弹窗提示该账号没填邮箱（链接要线下发）', dialogText.includes('没填邮箱'), '');

// 列表里立刻能看到这个新账号
const listText = await page.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' '));
check('用户管理列表里能看到新账号（含模块标签）',
  listText.includes(editorName) && listText.includes('新闻管理'), '');

// ---------------------------------------------------------------------------
// ② 非超管（staff 管理员）看不到按钮 + 直连接口 403
// ---------------------------------------------------------------------------
const staffContext = await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' });
const staffPage = await staffContext.newPage();
clearThrottle();
await loginAs(staffPage, staffName);
await staffPage.goto(`${UI}/admin/users`, { waitUntil: 'domcontentloaded' });
await staffPage.waitForTimeout(1000);
const staffButton = await staffPage.locator('.admin-hero-actions button', { hasText: '新增编辑员' }).count();
check('staff 管理员看不到「新增编辑员」按钮（仅超管）', staffButton === 0);

const staffApi = await staffPage.evaluate(async () => {
  const token = sessionStorage.getItem('auth_token') || localStorage.getItem('auth_token');
  const res = await fetch('http://127.0.0.1:8000/api/admin/users/create-editor/', {
    method: 'POST',
    headers: { Authorization: `Token ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'zze2e_ce_by_staff', modules: ['news'] }),
  });
  return res.status;
});
check('staff 管理员直连开通接口 → 403', staffApi === 403, `HTTP ${staffApi}`);
await staffContext.close();

// ---------------------------------------------------------------------------
// ③ 用链接设密码（新开匿名上下文，模拟"链接发给本人"）
// ---------------------------------------------------------------------------
const guestContext = await browser.newContext({ viewport: { width: 1400, height: 950 }, locale: 'zh-CN' });
const guest = await guestContext.newPage();
await guest.goto(resetUrl, { waitUntil: 'domcontentloaded' });
await guest.waitForTimeout(1500);
const resetInputs = await guest.locator('input[type="password"]').count();
check('链接能打开重置密码页', resetInputs >= 2, `页面上有 ${resetInputs} 个密码输入框`);

await guest.locator('input[type="password"]').first().fill(newPassword);
await guest.locator('input[type="password"]').nth(1).fill(newPassword);
await guest.locator('button[type="submit"]').first().click();
await guest.waitForTimeout(2500);

// ---------------------------------------------------------------------------
// ④ 用新密码登录 → 侧栏只有 看板 + 新闻管理
// ---------------------------------------------------------------------------
clearThrottle();
await loginAs(guest, editorName, newPassword);
const navLabels = await guest.evaluate(
  () => [...document.querySelectorAll('.admin-nav-item')].map((el) => el.innerText.trim()),
);
check(
  '开通出来的编辑员登录后：侧栏只有「数据看板 + 新闻管理」',
  navLabels.length === 2 && navLabels.some((l) => l.includes('新闻管理')),
  navLabels.join(' / '),
);

const apiStatus = (target, path, method, body) => target.evaluate(async ({ path, method, body }) => {
  const token = sessionStorage.getItem('auth_token') || localStorage.getItem('auth_token');
  const res = await fetch(`http://127.0.0.1:8000/api${path}`, {
    method,
    headers: { Authorization: `Token ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  return res.status;
}, { path, method, body });

const newsStatus = await apiStatus(guest, '/news/', 'POST', {
  title: `zze2e开通新闻_${suffix}`, content: '<p>x</p>', category: 'notice',
});
check('他能发新闻（201）', newsStatus === 201, `HTTP ${newsStatus}`);

const pestStatus = await apiStatus(guest, '/pests/', 'POST', {
  name: 'zze2e开通越界', crop_type: '玉米', english_identifier: `zze2e_ce_${suffix}`,
  prevention_methods: [],
});
check('他改不了病害词条（403）', pestStatus === 403, `HTTP ${pestStatus}`);

// ---------------------------------------------------------------------------
// ⑤ 同一条链接不能再用第二次
// ---------------------------------------------------------------------------
const reuse = await guest.evaluate(async (url) => {
  const res = await fetch(url.replace('http://127.0.0.1:5173', 'http://127.0.0.1:8000/api').replace('/reset-password', '/password-reset/confirm/'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      uid: new URL(url).searchParams.get('uid'),
      token: new URL(url).searchParams.get('token'),
      new_password: 'Another!2026',
    }),
  });
  return res.status;
}, resetUrl);
check('同一条链接不能再用第二次', reuse !== 200, `HTTP ${reuse}`);

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
