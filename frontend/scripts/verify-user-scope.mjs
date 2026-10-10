/**
 * 「用户管理的账号范围」端到端验证（第 144 批）
 * ============================================================================
 * 补的缺口：已注销与注销冷静期的账号在控制台里**完全看不到** ——
 * 端点其实一直支持（`?include_deleted=true` / `?pending_deletion=true`，第 95/101 批），
 * 只是界面没有开关，要看只能直连接口。
 * 顺带把状态语义拆清：以前只有"正常/已禁用"两档，而"不可用"其实有三种，
 * 该做什么完全不同（已删除→只能看；冷静期→本人取消注销；被停用→可恢复）。
 *
 * 覆盖：
 *   ① 默认（正常账号）：只看到启用中的账号，已注销与冷静期都不出现
 *   ② 「包含已注销」：软删除的账号出现，状态标签是「已删除」，且它的操作按钮都禁用
 *   ③ 「只看注销冷静期」：冷静期账号出现，标签带"还剩 N 天"，停用按钮禁用且说明原因
 *   ④ 三种状态标签能同时正确区分（正常 / 已停用 / 注销冷静期 / 已删除）
 *
 * 用法：node scripts/verify-user-scope.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const adminName = `zze2e_sc_admin_${suffix}`;
const normalName = `zze2e_sc_normal_${suffix}`;
const suspendedName = `zze2e_sc_susp_${suffix}`;
const graceName = `zze2e_sc_grace_${suffix}`;
const deletedName = `zze2e_sc_deleted_${suffix}`;

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
      "print('cleaned:', U.objects.filter(username__startswith='zze2e_sc_').delete()[0])",
      // ⚠️ 软删除的账号已被改名成 deleted_<id>，按原名删不到 —— 用**本次记录下来的 id**
      //    精确删除；不要按"email 为空且 is_deleted"批量删，那会误伤别人的软删除账号
      `print('cleaned deleted:', U.objects.filter(id=${DELETED_ID}).delete()[0])`,
    ]);
  } catch (error) {
    console.error('清理失败（忽略）:', error?.message || error);
  }
};
process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });

clearThrottle();
// ⚠️ 软删除会把用户名改成 `deleted_<id>`（让出原名），所以**按原用户名是搜不到的** ——
//    这里把改名后的用户名接出来，后面的断言要用它（第一版就是按原名搜，白等一场）
const seedOutput = runDjango([
  'from django.contrib.auth import get_user_model',
  'U = get_user_model()',
  `admin = U.objects.create_user(username='${adminName}', password='${password}', is_staff=True, role='ADMIN')`,
  `U.objects.create_user(username='${normalName}', password='${password}', role='USER')`,
  `s = U.objects.create_user(username='${suspendedName}', password='${password}', role='USER')`,
  's.is_active = False',
  "s.save(update_fields=['is_active'])",
  `g = U.objects.create_user(username='${graceName}', password='${password}', role='USER')`,
  'g.request_deletion()',
  `d = U.objects.create_user(username='${deletedName}', password='${password}', role='USER')`,
  "d.soft_delete(by=admin, reason='admin')",
  "d.refresh_from_db()",
  "print('DELETED_AS', d.username, d.id)",
  "print('seeded:', U.objects.filter(username__startswith='zze2e_sc_').count(), 'accounts')",
]);

const deletedUsernameMatch = /DELETED_AS (\S+) (\d+)/.exec(String(seedOutput));
if (!deletedUsernameMatch) throw new Error('没拿到软删除后的用户名与 id');
const deletedUsername = deletedUsernameMatch[1];
const DELETED_ID = Number(deletedUsernameMatch[2]);
console.log('（软删除后用户名 = ' + deletedUsername + '）');

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1700, height: 1000 }, locale: 'zh-CN' });
const page = await ctx.newPage();
const pageErrors = [];
const consoleErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });

clearThrottle();
await page.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.admin-login', { timeout: 30_000 });
await page.locator('#username').fill(adminName);
await page.locator('#password').fill(password);
await page.locator('button[type="submit"]').first().click();
await page.waitForURL((u) => u.pathname.startsWith('/admin/') && u.pathname !== '/admin/login', { timeout: 30_000 });
await page.waitForSelector('.admin-console', { timeout: 25_000 });

/** 打开用户管理页（带搜索词），返回可见行的文本 */
const listRows = async (search, scope = '') => {
  // ⚠️ 账号范围现在也在 URL 里（第 144 批）：搜索时要把 scope 一起带上，
  //    否则一次 goto 就把它丢了（第一版就是这样，导致"包含已注销"白切）
  const query = scope ? `search=${search}&scope=${scope}` : `search=${search}`;
  await page.goto(`${UI}/admin/users?${query}`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2200);
  return page.evaluate(() => [...document.querySelectorAll('.el-table__row')]
    .map((row) => row.innerText.replace(/\s+/g, ' ').trim()));
};

/** 切换"账号范围"下拉（按当前文案找选项） */
const pickScope = async (optionText) => {
  const select = page.locator('.filter-bar .el-select').filter({ hasText: '账号范围' }).first();
  await select.click();
  await page.waitForTimeout(500);
  await page.locator('.el-select-dropdown__item:visible', { hasText: optionText }).first().click();
  await page.waitForTimeout(2200);
};

// ---------------------------------------------------------------------------
// ① 默认：只有正常账号与"被停用"的账号（已注销/冷静期不出现）
// ---------------------------------------------------------------------------
const defaultRows = await listRows('zze2e_sc_');
const defaultText = defaultRows.join(' | ');
check('默认能看到正常账号', defaultText.includes(normalName));
check('默认也能看到被停用的账号（第 137 批起它就在列表里）', defaultText.includes(suspendedName));
check('默认**看不到**注销冷静期账号', !defaultText.includes(graceName), defaultText.slice(0, 120));
check('默认**看不到**已注销账号', !defaultText.includes(deletedUsername));

// 状态标签：正常 / 已停用
const normalRow = (await listRows(normalName)).find((t) => t.includes(normalName)) || '';
const suspRow = (await listRows(suspendedName)).find((t) => t.includes(suspendedName)) || '';
check('正常账号标签是「正常」', normalRow.includes('正常'), normalRow.slice(0, 80));
check('被停用账号标签是「已停用」（与动作同词）', suspRow.includes('已停用'), suspRow.slice(0, 80));

// ---------------------------------------------------------------------------
// ② 包含已注销 → 软删除账号出现，标签「已删除」，操作按钮禁用
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/users`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
await pickScope('包含已注销');
check('切到「包含已注销」后 URL 里带上了 scope（筛选进 URL，刷新/分享不丢）',
  page.url().includes('scope=include_deleted'), page.url().split('?')[1] || '');
const withDeleted = (await listRows(deletedUsername, 'include_deleted'))
  .find((t) => t.includes(deletedUsername)) || '';
check('「包含已注销」后能看到已注销账号', Boolean(withDeleted), withDeleted.slice(0, 100));
check('它的状态标签是「已删除」', withDeleted.includes('已删除'), withDeleted.slice(0, 100));

const deletedRowEl = page.locator('.el-table__row').filter({ hasText: deletedUsername }).first();
const deletedStatusBtn = deletedRowEl.locator('button', { hasText: /^(停用|恢复)$/ }).first();
check('已注销账号的「停用/恢复」按钮被禁用',
  await deletedStatusBtn.isDisabled(), await deletedStatusBtn.getAttribute('title'));

// ---------------------------------------------------------------------------
// ③ 只看注销冷静期 → 冷静期账号出现，标签带剩余天数，停用被禁用
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/users`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
await pickScope('只看注销冷静期');
const graceRows = await listRows(graceName, 'pending_deletion');
const graceRow = graceRows.find((t) => t.includes(graceName)) || '';
check('「只看注销冷静期」能筛出冷静期账号', Boolean(graceRow), graceRow.slice(0, 120));
check('标签写明是注销冷静期并带剩余天数',
  /注销冷静期/.test(graceRow) && /还剩\s*\d+\s*天/.test(graceRow), graceRow.slice(0, 120));

const graceRowEl = page.locator('.el-table__row').filter({ hasText: graceName }).first();
const graceStatusBtn = graceRowEl.locator('button', { hasText: /^(停用|恢复)$/ }).first();
check('冷静期账号的「停用/恢复」被禁用且说明原因',
  await graceStatusBtn.isDisabled() && /本人|冷静期/.test(await graceStatusBtn.getAttribute('title') || ''),
  await graceStatusBtn.getAttribute('title'));
check('冷静期列表里**不会**混进普通账号',
  !graceRows.some((t) => t.includes(normalName)), graceRows.length + ' 行');

await page.screenshot({ path: 'dsh-shots/admin-users-scope.png', clip: { x: 0, y: 0, width: 1700, height: 640 } });

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
