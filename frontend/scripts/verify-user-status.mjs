/**
 * 「停用 / 恢复账号」端到端验证（第 137 批）
 * ============================================================================
 * 这一批补的是个真空：用户管理页早有「已禁用」筛选与状态标签，却**没有入口能停用账号**，
 * 所以那个筛选在真实数据里永远筛不出东西（能产生禁用状态的两种途径都被默认列表排除了）。
 *
 * 覆盖：
 *   ① 超管在列表里点「停用」→ 确认框 → 行状态变「已禁用」，按钮变「恢复」
 *   ② **「已禁用」筛选真的能筛到这个账号了**（这正是本批要修的核心问题）
 *   ③ 停用是**真的**生效：对方旧 token 立刻 401、重新登录被拒
 *   ④ 点「恢复」→ 密码没动过，能直接登回来
 *   ⑤ 护栏（界面层）：自己的那一行「停用」按钮是禁用的，且 title 说明原因
 *   ⑥ 护栏（越权）：staff 管理员看超管那一行，「停用」也是禁用的
 *   ⑦ staff 管理员**可以**停用普通用户（口径与"删除"一致：能删就能停）
 *
 * 用法：node scripts/verify-user-status.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const superName = `zze2e_st_super_${suffix}`;
const staffName = `zze2e_st_staff_${suffix}`;
const targetName = `zze2e_st_target_${suffix}`;

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
      'U = get_user_model()',
      "print('cleaned:', U.objects.filter(username__startswith='zze2e_st_').delete()[0])",
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
  `U.objects.create_superuser(username='${superName}', password='${password}', email='', role='ADMIN')`,
  `U.objects.create_user(username='${staffName}', password='${password}', is_staff=True, role='ADMIN')`,
  `U.objects.create_user(username='${targetName}', password='${password}', role='USER')`,
  "print('seeded')",
]);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, locale: 'zh-CN' });
const page = await ctx.newPage();
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));

/** 走管理端登录页登录，落在后台外壳里 */
const loginAsAdmin = async (target, username) => {
  await target.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
  await target.waitForSelector('.admin-login', { timeout: 30_000 });
  await target.locator('#username').fill(username);
  await target.locator('#password').fill(password);
  await target.locator('button[type="submit"]').first().click();
  await target.waitForURL(
    (url) => url.pathname.startsWith('/admin/') && url.pathname !== '/admin/login',
    { timeout: 30_000 },
  );
  await target.waitForSelector('.admin-console', { timeout: 25_000 });
};

/** 直接打接口拿 token / 验 token（绕开界面，避免把"登录页能不能用"混进来） */
const apiLogin = (target, username) => target.evaluate(async ({ api, username, password }) => {
  const res = await fetch(`${api}/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json().catch(() => ({}));
  return { status: res.status, token: data?.data?.token || data?.token || null };
}, { api: API, username, password });

const apiWhoami = (target, token) => target.evaluate(async ({ api, token }) => {
  const res = await fetch(`${api}/check-auth/`, { headers: { Authorization: `Token ${token}` } });
  return res.status;
}, { api: API, token });

/** 列表里按用户名定位一行（用搜索框，避免翻页） */
const openUserRow = async (username) => {
  await page.goto(`${UI}/admin/users?search=${username}`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.el-table__row', { timeout: 25_000 });
  await page.waitForTimeout(1200);
  const row = page.locator('.el-table__row').filter({ hasText: username }).first();
  await row.waitFor({ timeout: 15_000 });
  return row;
};

const rowButton = (row, label) => row.locator('button', { hasText: new RegExp(`^${label}$`) }).first();

// 先拿到目标账号在"停用前"的 token（第 ③ 步要用它验证旧凭证失效）
clearThrottle();
const before = await apiLogin(page, targetName);
check('目标账号停用前能登录并拿到 token', before.status === 200 && Boolean(before.token),
  `HTTP ${before.status}`);
check('停用前旧 token 可用', (await apiWhoami(page, before.token)) === 200);

// ---------------------------------------------------------------------------
// ① 停用
// ---------------------------------------------------------------------------
clearThrottle();
await loginAsAdmin(page, superName);

// 先看"自己那一行"（第 ⑤ 步的护栏）
const ownRow = await openUserRow(superName);
const ownButton = rowButton(ownRow, '停用');
check('自己那一行的「停用」按钮是禁用的', await ownButton.isDisabled(),
  await ownButton.getAttribute('title'));

const row = await openUserRow(targetName);
check('普通用户那一行的「停用」按钮可用', !(await rowButton(row, '停用').isDisabled()));
check('停用前该行状态是「正常」',
  (await row.innerText()).includes('正常'), '');

await rowButton(row, '停用').click();
await page.waitForSelector('.el-message-box', { timeout: 10_000 });
const boxText = (await page.locator('.el-message-box').innerText()).replace(/\s+/g, ' ');
check('确认框写明"会立刻掉线"', boxText.includes('掉线'), boxText.slice(0, 80));
// ⚠️ ElMessageBox 是纯文本：文案里写 markdown 星号会**原样显示**出去（第一版就是这样）
check('确认框里没有漏出的 markdown 星号', !boxText.includes('**'), boxText.slice(0, 60));
await page.locator('.el-message-box__btns button.el-button--primary').click();
await page.waitForTimeout(2500);

const afterRow = await openUserRow(targetName);
const afterText = await afterRow.innerText();
check('行状态变成「已禁用」', afterText.includes('已禁用'), afterText.replace(/\s+/g, ' ').slice(0, 60));
check('按钮变成「恢复」', await rowButton(afterRow, '恢复').isVisible());
// 留证（docs 里会引用这两张图，所以不会被截图清理脚本删掉）
await page.locator('.admin-table, .el-table').first().screenshot({ path: 'dsh-shots/admin-user-suspend.png' });

// ---------------------------------------------------------------------------
// ② 「已禁用」筛选能筛到（本批要修的核心问题）
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/users`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
// 打开「状态」筛选并选「已禁用」
// ⚠️ 两个坑（都是实测出来的）：
//    ① `.filter-bar` 里第一个 el-select 是「角色」，用 .first() 会去点角色下拉，
//       然后永远等不到「已禁用」；
//    ② Element Plus 的 placeholder **不是** input 的 placeholder 属性，
//       而是渲染成 `.el-select__placeholder` 文本 —— 所以要按文案筛。
const statusSelect = page.locator('.filter-bar .el-select').filter({ hasText: '状态' }).first();
await statusSelect.click();
await page.waitForTimeout(600);
await page.locator('.el-select-dropdown__item:visible', { hasText: '已禁用' }).first().click();
await page.waitForTimeout(2000);
const filtered = await page.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' '));
check('「已禁用」筛选能筛出刚停用的账号',
  filtered.includes(targetName), filtered.slice(0, 120));
await page.locator('.admin-table, .el-table').first().screenshot({ path: 'dsh-shots/admin-user-disabled-filter.png' });

// ---------------------------------------------------------------------------
// ③④ 旧 token 失效 + 登录被拒；恢复后能登回来
// ---------------------------------------------------------------------------
check('停用后旧 token 立刻 401',
  (await apiWhoami(page, before.token)) === 401, `HTTP ${await apiWhoami(page, before.token)}`);
const blocked = await apiLogin(page, targetName);
check('停用后重新登录被拒', blocked.status !== 200, `HTTP ${blocked.status}`);

await page.goto(`${UI}/admin/users?search=${targetName}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.el-table__row', { timeout: 25_000 });
await page.waitForTimeout(1200);
const restoredRow = page.locator('.el-table__row').filter({ hasText: targetName }).first();
await rowButton(restoredRow, '恢复').click();
await page.waitForSelector('.el-message-box', { timeout: 10_000 });
await page.locator('.el-message-box__btns button.el-button--primary').click();
await page.waitForTimeout(2500);

clearThrottle();
const again = await apiLogin(page, targetName);
check('恢复后不改密码就能登回来', again.status === 200, `HTTP ${again.status}`);

// ---------------------------------------------------------------------------
// ⑥⑦ 越权护栏 + staff 能停用普通用户
// ---------------------------------------------------------------------------
const staffCtx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, locale: 'zh-CN' });
const staffPage = await staffCtx.newPage();
clearThrottle();
await loginAsAdmin(staffPage, staffName);

await staffPage.goto(`${UI}/admin/users?search=${superName}`, { waitUntil: 'domcontentloaded' });
await staffPage.waitForSelector('.el-table__row', { timeout: 25_000 });
await staffPage.waitForTimeout(1500);
const superRowStaff = staffPage.locator('.el-table__row').filter({ hasText: superName }).first();
const staffSawButton = rowButton(superRowStaff, '停用');
check('staff 看超管那一行：「停用」被禁用',
  await staffSawButton.isDisabled(), await staffSawButton.getAttribute('title'));

await staffPage.goto(`${UI}/admin/users?search=${targetName}`, { waitUntil: 'domcontentloaded' });
await staffPage.waitForSelector('.el-table__row', { timeout: 25_000 });
await staffPage.waitForTimeout(1500);
const normalRowStaff = staffPage.locator('.el-table__row').filter({ hasText: targetName }).first();
check('staff 可以停用普通用户（能删就能停）',
  !(await rowButton(normalRowStaff, '停用').isDisabled()));

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
