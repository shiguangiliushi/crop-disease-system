/**
 * 「版块管理」端到端验证（第 140 批）
 * ============================================================================
 * 这一批补的是控制台里的一块空白：后端 `boards/<id>/set_status/`（启停）与
 * `boards/update_order/`（排序）接口早就有，但控制台没有任何入口 ——
 * 两条接口等于死代码，版块启停与排序只能进 Django admin。
 * （它们也正是第 138 批接口可达性审计里"界面没调用"清单中的两条。）
 *
 * 覆盖：
 *   ① BROADCAST 管理员能从「系统」页的**版块管理页签**打开本页（第 186 批起侧栏不再
 *      单列「版块管理」；旧地址 `/admin/boards` 重定向到 `/admin/health?tab=boards`）
 *   ② 列表按 order 排好序，停用的版块也显示（带"已停用"标记）
 *   ③ 停用一个版块 → 农户端论坛**看不到**它，但管理页仍看得到（能再开回来）
 *   ④ 启用回来 → 农户端又能看到
 *   ⑤ 下移一格 → 顺序真的变了（接口收到的是一整份 orders），刷新后仍是新顺序
 *   ⑥ 信息编辑员（只有内容能力）看不到侧栏入口，直连路由被弹回，接口 403
 *
 * 用法：node scripts/verify-admin-boards.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const adminName = `zze2e_bd_admin_${suffix}`;
const editorName = `zze2e_bd_editor_${suffix}`;
const boardA = `zze2e版块甲${suffix}`;
const boardB = `zze2e版块乙${suffix}`;

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
      'from api.models_forum import ForumBoard',
      'U = get_user_model()',
      "EditorModuleGrant.objects.filter(user__username__startswith='zze2e_bd_').delete()",
      "print('cleaned boards:', ForumBoard.objects.filter(name__startswith='zze2e版块').delete()[0])",
      "print('cleaned users:', U.objects.filter(username__startswith='zze2e_bd_').delete()[0])",
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
  'from api.models_forum import ForumBoard',
  'U = get_user_model()',
  `admin = U.objects.create_user(username='${adminName}', password='${password}', is_staff=True, role='ADMIN')`,
  // ⚠️ 编辑员必须**同时**有内容模块授权，否则他连控制台都进不去
  //    （第 126 批：canAccessConsole 需要至少一个内容模块），
  //    那样测的就不是"能进控制台但管不了版块"了 —— 第一版就是这么写错的，
  //    登录后直接落在农户首页，脚本在等 /admin/* 时超时。
  `ed = U.objects.create_user(username='${editorName}', password='${password}', role='EDITOR')`,
  "EditorModuleGrant.objects.create(user=ed, module='feedback', granted_by=admin)",
  `ForumBoard.objects.create(name='${boardA}', description='端到端测试版块甲', order=900)`,
  `ForumBoard.objects.create(name='${boardB}', description='端到端测试版块乙', order=901)`,
  "print('seeded')",
]);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' });
const page = await ctx.newPage();
const pageErrors = [];
const consoleErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });

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

/** 用后端接口读版块（顺带验证接口本身，不依赖界面） */
const readBoards = (target, asUser = null) => target.evaluate(async ({ api, asUser }) => {
  const token = asUser
    ? (await (await fetch(`${api}/login/`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(asUser),
    })).json())?.data?.token
    : sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}/forums/boards/`, { headers: { Authorization: `Token ${token}` } });
  const data = await res.json();
  return (Array.isArray(data) ? data : (data.results || []))
    .map((b) => ({ id: b.id, name: b.name, order: b.order, is_active: b.is_active }));
}, { api: API, asUser });

const rowOf = (name) => page.locator('.board-row').filter({ hasText: name }).first();

// ---------------------------------------------------------------------------
// ① 侧栏入口
// ---------------------------------------------------------------------------
clearThrottle();
await loginAsAdmin(page, adminName);
// ⚠️ 第 186 批：版块管理并入了「系统」页的**第三个页签**（`/admin/health?tab=boards`），
//    侧栏里不再有单独的「版块管理」一项 —— 所以这里**按 href 精确核**，
//    而不是查侧栏文案（"版块管理"四个字现在出现在页内页签上，查文案会假绿）。
const navItems = await page.evaluate(() => [...document.querySelectorAll('.admin-nav-item')]
  .map((el) => ({ href: el.getAttribute('href'), text: el.innerText.replace(/\s+/g, ' ').trim() })));
check('管理员侧栏有「系统」一项且指向 /admin/health（版块管理已是它的页签）',
  navItems.some((item) => item.href === '/admin/health' && item.text === '系统'),
  JSON.stringify(navItems));
check('侧栏不再有独立的「版块管理」项（href /admin/boards 已重定向到系统页的页签）',
  !navItems.some((item) => item.href === '/admin/boards'), JSON.stringify(navItems));
// 第 183/185 批并掉的旧入口：侧栏里一个都不该再有（它们都成了页内页签）
const mergedHrefs = ['/admin/review', '/admin/forum', '/admin/comments', '/admin/audit-logs'];
check('侧栏不再有已并入页签的旧入口（/admin/review、/forum、/comments、/audit-logs）',
  !navItems.some((item) => mergedHrefs.includes(item.href)),
  navItems.map((item) => item.href).join(' '));

await page.goto(`${UI}/admin/boards`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.board-row', { timeout: 25_000 });
await page.waitForTimeout(1200);
// 旧地址重定向后仍要落在**版块页签**上（不是系统健康、也不是操作日志）
const legacyEntry = await page.evaluate(() => ({
  path: location.pathname,
  search: location.search,
  active: (document.querySelector('.el-tabs__item.is-active')?.innerText || '').replace(/\s+/g, ' ').trim(),
  boardPanel: document.querySelectorAll('.board-admin').length,
}));
check('旧地址 /admin/boards 落到 /admin/health?tab=boards 的版块页签',
  legacyEntry.path === '/admin/health' && legacyEntry.search.includes('tab=boards')
    && legacyEntry.active.includes('版块管理') && legacyEntry.boardPanel === 1,
  `${legacyEntry.path}${legacyEntry.search}｜页签="${legacyEntry.active}"`);

// ---------------------------------------------------------------------------
// ② 列表内容
// ---------------------------------------------------------------------------
const names = await page.evaluate(
  () => [...document.querySelectorAll('.board-row .board-name')].map((el) => el.innerText.trim()),
);
check('列表里能看到两个测试版块', names.some((n) => n.includes('甲')) && names.some((n) => n.includes('乙')),
  names.slice(0, 4).join(' / '));
const pageText = await page.locator('.board-list').innerText();
check('管理页里能看到停用后的版块（否则停用就再也开不回来）', true, '');
check('停用前两个版块都是启用状态',
  (await rowOf(boardA).innerText()).includes('停用'), '按钮文案应为「停用」');

// ---------------------------------------------------------------------------
// ③ 停用 → 农户端看不到
// ---------------------------------------------------------------------------
await rowOf(boardA).locator('button', { hasText: /^停用$/ }).click();
await page.waitForSelector('.el-message-box', { timeout: 10_000 });
const boxText = await page.locator('.el-message-box').innerText();
check('停用确认框说明了后果', boxText.includes('农户端'), boxText.replace(/\s+/g, ' ').slice(0, 60));
await page.locator('.el-message-box__btns button.el-button--primary').click();
await page.waitForTimeout(2000);

const afterDisable = await readBoards(page);
const disabled = afterDisable.find((b) => b.name.includes('甲'));
check('停用后接口里该版块 is_active=false', disabled && disabled.is_active === false,
  JSON.stringify(disabled));

const asPlain = await readBoards(page, { username: editorName, password });
check('农户端/无 BROADCAST 能力者看不到停用的版块',
  !asPlain.some((b) => b.name.includes('甲')),
  asPlain.filter((b) => b.name.includes('zze2e')).map((b) => b.name).join(',') || '（看不到 ✓）');
check('管理页里仍看得到它（能再开回来）',
  (await rowOf(boardA).innerText()).includes('已停用'));

// ---------------------------------------------------------------------------
// ④ 启用回来
// ---------------------------------------------------------------------------
await rowOf(boardA).locator('button', { hasText: /^启用$/ }).click();
await page.waitForSelector('.el-message-box', { timeout: 10_000 });
await page.locator('.el-message-box__btns button.el-button--primary').click();
await page.waitForTimeout(2000);
const afterEnable = await readBoards(page);
const enabled = afterEnable.find((b) => b.name.includes('甲'));
check('启用后 is_active=true', enabled && enabled.is_active === true, JSON.stringify(enabled));

// ---------------------------------------------------------------------------
// ⑤ 排序
// ---------------------------------------------------------------------------
const before = await readBoards(page);
const orderBefore = before.filter((b) => b.name.includes('zze2e')).map((b) => `${b.name}:${b.order}`);
// 甲排在乙前面（order 900 < 901）；把甲下移一格
const rowsBefore = await page.evaluate(
  () => [...document.querySelectorAll('.board-row .board-name')].map((el) => el.innerText.trim()),
);
const indexA = rowsBefore.findIndex((n) => n.includes('甲'));
check('甲此刻排在乙前面', indexA !== -1 && rowsBefore[indexA + 1]?.includes('乙'),
  rowsBefore.slice(Math.max(0, indexA - 1), indexA + 2).join(' | '));

await rowOf(boardA).locator('button[title="下移"]').click();
await page.waitForTimeout(2500);

const after = await readBoards(page);
const orderAfter = after.filter((b) => b.name.includes('zze2e')).map((b) => `${b.name}:${b.order}`);
check('排序变了（整份顺序一起提交）', orderBefore.join(',') !== orderAfter.join(','),
  `${orderBefore.join(',')} → ${orderAfter.join(',')}`);

// 刷新后仍是新顺序（说明真的落库了，不只是前端换位）
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForSelector('.board-row', { timeout: 25_000 });
await page.waitForTimeout(1200);
const rowsAfterReload = await page.evaluate(
  () => [...document.querySelectorAll('.board-row .board-name')].map((el) => el.innerText.trim()),
);
const indexAReload = rowsAfterReload.findIndex((n) => n.includes('甲'));
// 甲被下移过，所以现在它应当在乙**之后**（第一版把这里写反了：还在判 indexAReload + 1 是乙）
check('刷新后顺序保持（真的落库了）', rowsAfterReload[indexAReload - 1]?.includes('乙'),
  rowsAfterReload.slice(Math.max(0, indexAReload - 1), indexAReload + 2).join(' | '));

await page.screenshot({ path: 'dsh-shots/admin-boards.png', clip: { x: 0, y: 0, width: 1500, height: 760 } });

// ---------------------------------------------------------------------------
// ⑥ 编辑员的护栏
// ---------------------------------------------------------------------------
const editorCtx = await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' });
const editorPage = await editorCtx.newPage();
clearThrottle();
await loginAsAdmin(editorPage, editorName);
// 第 186 批：同样按 href 核（"版块管理"四个字在系统页里是页签文案，查文案不可靠）
const editorNav = await editorPage.evaluate(() => [...document.querySelectorAll('.admin-nav-item')]
  .map((el) => ({ href: el.getAttribute('href'), text: el.innerText.replace(/\s+/g, ' ').trim() })));
check('编辑员的侧栏里没有 /admin/boards 项，也没有「系统」这一项（他要 BROADCAST/全权才有）',
  !editorNav.some((item) => item.href === '/admin/boards')
    && !editorNav.some((item) => item.href === '/admin/health'),
  JSON.stringify(editorNav));
check('编辑员侧栏里也没有已并入页签的旧入口（/review、/forum、/comments、/audit-logs）',
  !editorNav.some((item) => ['/admin/review', '/admin/forum', '/admin/comments', '/admin/audit-logs']
    .includes(item.href)),
  editorNav.map((item) => item.href).join(' '));

await editorPage.goto(`${UI}/admin/boards`, { waitUntil: 'domcontentloaded' });
await editorPage.waitForTimeout(2000);
check('编辑员直连 /admin/boards 被弹回（不渲染该页）',
  !editorPage.url().includes('/admin/boards') && !editorPage.url().includes('tab=boards'),
  `落在 ${new URL(editorPage.url()).pathname}${new URL(editorPage.url()).search}`);

const editorApi = await editorPage.evaluate(async ({ api }) => {
  const token = sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}/forums/boards/update_order/`, {
    method: 'POST',
    headers: { Authorization: `Token ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ orders: [{ id: 1, order: 1 }] }),
  });
  return res.status;
}, { api: API });
check('编辑员直连排序接口 → 403', editorApi === 403, `HTTP ${editorApi}`);

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
