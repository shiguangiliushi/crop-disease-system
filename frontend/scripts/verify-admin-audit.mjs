/**
 * 「控制台操作日志页」端到端验证（第 148 批）
 * ============================================================================
 * 第 146 批把管理动作落进了 AdminAuditLog 表并给了只读接口，但只能在 Django admin 里看。
 * 这一页把它接进控制台：按动作/时间/关键字筛选。**仅全权管理员**。
 *
 * 覆盖：
 *   ① 全权管理员：侧栏出现「操作日志」，页面能打开
 *   ② 做完一个可审计动作（停用账号）后，日志里能查到那条记录
 *      （含操作人、目标、说明、目标类型）
 *   ③ 按动作筛选生效且进 URL；关键字搜索生效
 *   ④ 时间范围：今天能查到、未来日期查不到（end 含当天的边界）
 *   ⑤ 页面是**只读**的：没有编辑/删除按钮，接口也只有 GET
 *   ⑥ 信息编辑员：侧栏**看不到**「操作日志」，手输网址被守卫弹回
 *      （直连接口也是 403 —— 前端拦一道、后端拦一道）
 *
 * 用法：node scripts/verify-admin-audit.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const superName = `zze2e_al_super_${suffix}`;
const editorName = `zze2e_al_editor_${suffix}`;
const victimName = `zze2e_al_victim_${suffix}`;

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
      'from api.models import EditorModuleGrant',
      'from api.models_audit import AdminAuditLog',
      'from api.models_forum import ForumBoard',
      "print('cleaned boards:', ForumBoard.objects.filter(name__startswith='zze2e审计版块').delete()[0])",
      "print('cleaned logs:', AdminAuditLog.objects.filter(actor_repr__startswith='zze2e_al_').delete()[0])",
      "EditorModuleGrant.objects.filter(user__username__startswith='zze2e_al_').delete()",
      'U = get_user_model()',
      "print('cleaned users:', U.objects.filter(username__startswith='zze2e_al_').delete()[0])",
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
  'from api.models import EditorModuleGrant',
  'U = get_user_model()',
  `admin = U.objects.create_superuser(username='${superName}', password='${password}', email='', role='ADMIN')`,
  `ed = U.objects.create_user(username='${editorName}', password='${password}', role='EDITOR')`,
  "EditorModuleGrant.objects.create(user=ed, module='review', granted_by=admin)",
  `U.objects.create_user(username='${victimName}', password='${password}', role='USER')`,
  "print('seeded')",
]);

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1700, height: 1000 }, locale: 'zh-CN' })).newPage();
const pageErrors = [];
const consoleErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });

const loginAs = async (target, username) => {
  clearThrottle();
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

const rowTexts = () => page.evaluate(() => [...document.querySelectorAll('.el-table__row')]
  .map((row) => row.innerText.replace(/\s+/g, ' ').trim()));

await loginAs(page, superName);

// ---------------------------------------------------------------------------
// ② 先做一个可审计的动作：去用户管理页停用那个账号
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/users?search=${victimName}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.el-table__row', { timeout: 25_000 });
await page.waitForTimeout(1500);
await page.locator('.el-table__row').filter({ hasText: victimName }).first()
  .locator('button', { hasText: '停用' }).first().click();
await page.waitForTimeout(600);
const confirmBtn = page.locator('.el-message-box__btns button.el-button--primary');
if (await confirmBtn.count()) {
  await confirmBtn.click();
  await page.waitForTimeout(2000);
}

// ---------------------------------------------------------------------------
// ① 侧栏 + 页面
// ---------------------------------------------------------------------------
const nav = await page.evaluate(
  () => [...document.querySelectorAll('.admin-nav-item')].map((el) => el.innerText.trim()).join(' | '),
);
check('全权管理员侧栏出现「操作日志」', nav.includes('操作日志'), nav);

await page.goto(`${UI}/admin/audit-logs`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.el-table__row', { timeout: 25_000 });
await page.waitForTimeout(1800);
check('页面标题是「操作日志」',
  (await page.locator('.admin-hero h1').innerText()).includes('操作日志'));
check('页面上写明"日志只读"', (await page.locator('.readonly-note').innerText()).includes('只读'));

const allRows = (await rowTexts()).join(' || ');
check('能查到刚才那次「停用账号」', allRows.includes('停用账号'), allRows.slice(0, 120));
check('日志里带操作人', allRows.includes(superName), '');
check('日志里带目标账号', allRows.includes(victimName), '');
check('日志里带目标类型（账号）', allRows.includes('账号'));

await page.screenshot({ path: 'dsh-shots/admin-audit-log.png', clip: { x: 0, y: 0, width: 1700, height: 700 } });

// ---------------------------------------------------------------------------
// ③ 动作筛选 + 关键字
// ---------------------------------------------------------------------------
await page.locator('.filter-bar .el-select').first().click();
await page.waitForTimeout(600);
await page.locator('.el-select-dropdown__item:visible', { hasText: '停用账号' }).first().click();
await page.waitForTimeout(2000);
const filtered = (await rowTexts()).join(' || ');
check('按动作筛选后只剩该动作', filtered.includes('停用账号') && !filtered.includes('恢复账号'),
  filtered.slice(0, 90));
check('动作筛选进了 URL', page.url().includes('action=user.suspend'), page.url().split('?')[1] || '');

await page.locator('.filter-bar input[type="text"]').last().fill(victimName);
await page.locator('.filter-bar input[type="text"]').last().press('Enter');
await page.waitForTimeout(2000);
check('关键字搜索命中目标账号', (await rowTexts()).join(' ').includes(victimName));

// 搜一个不存在的词 → 空列表（确认搜索真的生效，而不是忽略参数）
await page.locator('.filter-bar input[type="text"]').last().fill('zz绝不存在的关键字zz');
await page.locator('.filter-bar input[type="text"]').last().press('Enter');
await page.waitForTimeout(2000);
check('搜不存在的关键字得到空列表', (await page.locator('.el-table__row').count()) === 0);

// ---------------------------------------------------------------------------
// ④ 时间范围
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/audit-logs`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1800);
const today = new Date().toISOString().slice(0, 10);
await page.goto(`${UI}/admin/audit-logs?start=${today}&end=${today}`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2200);
check('时间范围含当天（能查到今天的记录）',
  (await rowTexts()).join(' ').includes('停用账号'), '');

await page.goto(`${UI}/admin/audit-logs?start=2030-01-01&end=2030-01-02`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2200);
check('未来日期区间查不到任何记录', (await page.locator('.el-table__row').count()) === 0);

// ---------------------------------------------------------------------------
// ⑤ 只读
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/audit-logs`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.el-table__row', { timeout: 25_000 });
await page.waitForTimeout(1500);
const rowButtons = await page.locator('.el-table__row button').count();
check('列表里没有任何操作按钮（只读）', rowButtons === 0, `${rowButtons} 个按钮`);
const postStatus = await page.evaluate(async ({ api, today }) => {
  const token = sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}/admin/audit-logs/`, {
    method: 'POST',
    headers: { Authorization: `Token ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'user.suspend', created_at: today }),
  });
  return res.status;
}, { api: API, today });
check('日志接口不接受 POST（无新增入口）', postStatus === 405, `HTTP ${postStatus}`);

// ---------------------------------------------------------------------------
// ⑤b 第 150 批新接入的动作：新建版块也要能查到
//     （顺带验证"动作下拉来自后端 choices"——新动作不用改前端）
// ---------------------------------------------------------------------------
clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'from rest_framework.test import APIClient',
  'U = get_user_model()',
  `admin = U.objects.get(username='${superName}')`,
  'c = APIClient(); c.force_authenticate(user=admin)',
  `r = c.post('/api/forums/boards/', {'name': 'zze2e审计版块${suffix}', 'order': 999}, format='json')`,
  "print('BOARD', r.status_code)",
]);

await page.goto(`${UI}/admin/audit-logs?search=zze2e审计版块`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2500);
const boardLog = (await rowTexts()).join(' || ');
check('第 150 批新接入的「新建版块」也能在日志页查到',
  boardLog.includes('新建版块'), boardLog.slice(0, 100));
check('日志里带版块名（快照）', boardLog.includes('zze2e审计版块'), '');

await page.locator('.filter-bar .el-select').first().click();
await page.waitForTimeout(800);
const actionOptions = await page.locator('.el-select-dropdown__item:visible').allInnerTexts();
check('动作下拉里出现「新建版块」', actionOptions.join(' | ').includes('新建版块'),
  actionOptions.slice(0, 6).join(' / '));
await page.keyboard.press('Escape');
await page.waitForTimeout(500);

// ---------------------------------------------------------------------------
// ⑥ 编辑员：看不到、进不去
// ---------------------------------------------------------------------------
const editorCtx = await browser.newContext({ viewport: { width: 1700, height: 1000 }, locale: 'zh-CN' });
const editorPage = await editorCtx.newPage();
await loginAs(editorPage, editorName);
const editorNav = await editorPage.evaluate(
  () => [...document.querySelectorAll('.admin-nav-item')].map((el) => el.innerText.trim()).join(' | '),
);
check('编辑员侧栏看不到「操作日志」', !editorNav.includes('操作日志'), editorNav);

await editorPage.goto(`${UI}/admin/audit-logs`, { waitUntil: 'domcontentloaded' });
await editorPage.waitForTimeout(2500);
check('编辑员手输网址被守卫弹回（不停在日志页）',
  !editorPage.url().includes('/admin/audit-logs'), editorPage.url().replace(UI, ''));

const editorApi = await editorPage.evaluate(async (api) => {
  const token = sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}/admin/audit-logs/`, {
    headers: { Authorization: `Token ${token}` },
  });
  return res.status;
}, API);
check('编辑员直连接口 → 403', editorApi === 403, `HTTP ${editorApi}`);
await editorCtx.close();

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
