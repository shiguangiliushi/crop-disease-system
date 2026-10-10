/**
 * 「版块新建 / 编辑」端到端验证（第 143 批）
 * ============================================================================
 * 补的缺口：`POST /forums/boards/` 与 `PATCH /forums/boards/<id>/` 接口一直都有，
 * 但控制台没有入口 —— **在此之前建版块只能进 Django admin**。
 *
 * 覆盖：
 *   ① 页头「新建版块」打开弹窗，新建时排序默认是"现有最大 +1"（排在最后，不是 0）
 *   ② 填名称/英文名/描述/图标 → 保存 → 列表里出现，且农户端**也能看到**
 *   ③ 编辑：改名称与英文名 → 列表更新，**统计字段（帖数）不被冲掉**
 *   ④ 新建时**不勾选启用** → 农户端看不到，但管理页看得到（先建好后开放的场景）
 *   ⑤ 直连接口：普通用户/信息编辑员建版块 → 403
 *
 * 用法：node scripts/verify-board-crud.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const adminName = `zze2e_bc_admin_${suffix}`;
const editorName = `zze2e_bc_editor_${suffix}`;
const plainName = `zze2e_bc_plain_${suffix}`;
const boardName = `zze2e问答${suffix}`;
const boardNameEdited = `zze2e问答改${suffix}`;
const hiddenBoard = `zze2e预告${suffix}`;

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
      "print('cleaned boards:', ForumBoard.objects.filter(name__startswith='zze2e').delete()[0])",
      "EditorModuleGrant.objects.filter(user__username__startswith='zze2e_bc_').delete()",
      "print('cleaned users:', U.objects.filter(username__startswith='zze2e_bc_').delete()[0])",
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
  `admin = U.objects.create_user(username='${adminName}', password='${password}', is_staff=True, role='ADMIN')`,
  `ed = U.objects.create_user(username='${editorName}', password='${password}', role='EDITOR')`,
  "EditorModuleGrant.objects.create(user=ed, module='feedback', granted_by=admin)",
  `U.objects.create_user(username='${plainName}', password='${password}', role='USER')`,
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

/**
 * 读版块列表
 *
 * ⚠️ 两个坑（第一版就栽在第二个上）：
 *   1. 读自己的列表要用**当前会话的 token**，不要重新登录 ——
 *      第 94 批起"登录一律换一张新 Token"，而且会**删掉旧 token**；
 *      在同一个页面上下文里再登一次，等于把后台界面自己的会话弄失效，
 *      随后界面上所有请求都 401（第一版就是这样：创建版块静默失败）。
 *   2. 要用**别人**的视角看时（农户端能不能看到），务必另开一个上下文登录，
 *      别在管理员的上下文里登别人。
 */
const boardsWithToken = (target, token) => target.evaluate(async ({ api, token }) => {
  const res = await fetch(`${api}/forums/boards/`, { headers: { Authorization: `Token ${token}` } });
  const data = await res.json();
  return (Array.isArray(data) ? data : (data.results || []))
    .map((b) => ({ id: b.id, name: b.name, name_en: b.name_en, order: b.order,
                   is_active: b.is_active, post_count: b.post_count }));
}, { api: API, token });

const boardsAsCurrentUser = async () => {
  const token = await page.evaluate(() => sessionStorage.getItem('auth_token'));
  return boardsWithToken(page, token);
};

/** 另开上下文、以别人身份登录后读版块（不影响管理员会话） */
const boardsAsUser = async (username) => {
  const other = await browser.newContext({ viewport: { width: 1200, height: 800 } });
  const otherPage = await other.newPage();
  const list = await otherPage.evaluate(async ({ api, username, password }) => {
    const login = await (await fetch(`${api}/login/`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })).json();
    const res = await fetch(`${api}/forums/boards/`, {
      headers: { Authorization: `Token ${login?.data?.token}` },
    });
    const data = await res.json();
    return (Array.isArray(data) ? data : (data.results || []))
      .map((b) => ({ id: b.id, name: b.name, name_en: b.name_en, order: b.order,
                     is_active: b.is_active, post_count: b.post_count }));
  }, { api: API, username, password });
  await other.close();
  return list;
};

const rowOf = (name) => page.locator('.board-row').filter({ hasText: name }).first();

clearThrottle();
await loginAsAdmin(page, adminName);
await page.goto(`${UI}/admin/boards`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.board-row', { timeout: 25_000 });
await page.waitForTimeout(1200);

// ---------------------------------------------------------------------------
// ① 打开新建弹窗：排序默认排最后
// ---------------------------------------------------------------------------
await page.locator('button', { hasText: '新建版块' }).first().click();
await page.waitForSelector('.el-dialog:visible', { timeout: 15_000 });
const existing = await boardsAsCurrentUser();
const maxOrder = existing.reduce((max, b) => Math.max(max, b.order || 0), 0);
const defaultOrder = await page.locator('.el-dialog:visible .el-input-number input').first().inputValue();
check('新建时排序默认 = 现有最大值 + 1（排在最后，不是 0）',
  Number(defaultOrder) === maxOrder + 1, `默认 ${defaultOrder}，现有最大 ${maxOrder}`);
check('名称为空时「保存」不可点',
  await page.locator('.el-dialog:visible .el-button--primary').isDisabled());

// ---------------------------------------------------------------------------
// ② 填写并保存 → 农户端可见
// ---------------------------------------------------------------------------
await page.locator('.el-dialog:visible input').first().fill(boardName);
await page.locator('.el-dialog:visible input').nth(1).fill('zz Q&A Board');
await page.locator('.el-dialog:visible textarea').first().fill('端到端测试用的问答版块');
await page.locator('.el-dialog:visible .el-button--primary').click();
await page.waitForTimeout(2500);

check('列表里出现新版块', await rowOf(boardName).count() > 0);
const publicBoards = await boardsAsUser(plainName);
check('农户端（普通用户）也能看到它',
  publicBoards.some((b) => b.name === boardName), publicBoards.map((b) => b.name).join(','));
const created = publicBoards.find((b) => b.name === boardName);
check('英文名写入成功', created?.name_en === 'zz Q&A Board', String(created?.name_en));

// ---------------------------------------------------------------------------
// ③ 编辑：改名 + 统计字段不被冲掉
// ---------------------------------------------------------------------------
const beforeEdit = (await boardsAsCurrentUser()).find((b) => b.name === boardName);
await rowOf(boardName).locator('button', { hasText: '编辑' }).click();
await page.waitForSelector('.el-dialog:visible', { timeout: 15_000 });
const nameInput = page.locator('.el-dialog:visible input').first();
check('编辑弹窗里带出了原有名称', (await nameInput.inputValue()) === boardName,
  await nameInput.inputValue());
await nameInput.fill(boardNameEdited);
await page.locator('.el-dialog:visible .el-button--primary').click();
await page.waitForTimeout(2500);

const afterEdit = (await boardsAsCurrentUser()).find((b) => b.name === boardNameEdited);
check('改名生效', Boolean(afterEdit), afterEdit ? afterEdit.name : '（没找到）');
check('编辑没有冲掉统计字段（帖数保持）',
  afterEdit?.post_count === beforeEdit?.post_count,
  `${beforeEdit?.post_count} → ${afterEdit?.post_count}`);

// ---------------------------------------------------------------------------
// ④ 新建但**不启用** → 农户端看不到
// ---------------------------------------------------------------------------
await page.locator('button', { hasText: '新建版块' }).first().click();
await page.waitForSelector('.el-dialog:visible', { timeout: 15_000 });
await page.locator('.el-dialog:visible input').first().fill(hiddenBoard);
await page.locator('.el-dialog:visible .el-checkbox').first().click();   // 取消"立即启用"
await page.locator('.el-dialog:visible .el-button--primary').click();
await page.waitForTimeout(2500);

const adminBoards = await boardsAsCurrentUser();
const growerBoards = await boardsAsUser(plainName);
check('管理页能看到未启用的新版块', adminBoards.some((b) => b.name === hiddenBoard));
check('农户端看不到它（先建好、内容备齐再开放）',
  !growerBoards.some((b) => b.name === hiddenBoard));

await page.screenshot({ path: 'dsh-shots/admin-boards-create.png', clip: { x: 0, y: 0, width: 1500, height: 720 } });

// ---------------------------------------------------------------------------
// ⑤ 权限：普通用户 / 信息编辑员不能建版块
// ---------------------------------------------------------------------------
const editorCtx = await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' });
const editorPage = await editorCtx.newPage();
clearThrottle();
await loginAsAdmin(editorPage, editorName);
const editorApi = await editorPage.evaluate(async ({ api }) => {
  const token = sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}/forums/boards/`, {
    method: 'POST',
    headers: { Authorization: `Token ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'zze2e越权版块' }),
  });
  return res.status;
}, { api: API });
check('信息编辑员建版块 → 403', editorApi === 403, `HTTP ${editorApi}`);

const plainCtx = await browser.newContext({ viewport: { width: 1400, height: 900 }, locale: 'zh-CN' });
const plainPage = await plainCtx.newPage();
const plainApi = await plainPage.evaluate(async ({ api, username, password }) => {
  const login = await (await fetch(`${api}/login/`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })).json();
  const res = await fetch(`${api}/forums/boards/`, {
    method: 'POST',
    headers: { Authorization: `Token ${login?.data?.token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'zze2e越权版块2' }),
  });
  return res.status;
}, { api: API, username: plainName, password });
check('普通用户建版块 → 403', plainApi === 403, `HTTP ${plainApi}`);

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
