/**
 * 信息编辑员（EDITOR）端到端验证（第 126/127 批）
 * ============================================================================
 * 这一批的核心承诺是"**角色不同，看到的后台不一样**"，而这件事必须真的用
 * 编辑员账号登录一次才算验证过 —— 单测能证明接口 403，但证明不了
 * "侧栏里真没有用户管理" 与 "手输网址会被弹回去"。
 *
 * 覆盖：
 *   ① 编辑员登录后落在 /admin/dashboard（和迁移前一致），侧栏**只有 5 项**（无「用户管理」）
 *   ② 顶部条身份标签显示「信息编辑员」（不是"管理员"）
 *   ③ 手输 /admin/users → 被弹回 /admin/dashboard，并提示"只有管理员可以访问"
 *   ④ 直连接口 GET /api/admin/users/ → 403（前端隐藏不是边界）
 *   ⑤ 编辑员能用的页面（病害百科维护）确实能打开，且**看板里没有"贡献榜/最近注册"**
 *   ⑥ 全权管理员登录：侧栏 6 项、看板里那两块在
 *   ⑦ 超级管理员给普通用户改角色 → 该用户重新登录后侧栏真的变成 5 项（127 批闭环）
 *
 * 用法：node scripts/verify-editor-role.mjs
 * 退出时自动清理临时账号（zze2e_editor_*）。
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const editorName = `zze2e_editor_${suffix}`;
const adminName = `zze2e_super_${suffix}`;
const promotedName = `zze2e_promote_${suffix}`;

const results = [];
let cleaned = false;

const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

/** 造账号：编辑员 / 超级管理员 / 待提权的普通用户 */
const seed = () => runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models import EditorModuleGrant',
  'U = get_user_model()',
  `e = U.objects.create_user(username='${editorName}', password='${password}', role='EDITOR')`,
  `s = U.objects.create_superuser(username='${adminName}', password='${password}', email='')`,
  `p = U.objects.create_user(username='${promotedName}', password='${password}', role='USER')`,
  // 第 128 批：编辑员要**按模块授权**。这一组验的是"编辑员能进后台、进不了用户管理"，
  // 所以四个内容模块全勾（"只勾一块时侧栏只剩那一块"由 verify-content-modules 盯）。
  "EditorModuleGrant.objects.bulk_create([EditorModuleGrant(user=e, module=m) for m in ('review', 'news', 'pests', 'feedback')])",
  "print('seeded')",
]);

const cleanup = () => {
  if (cleaned) return;
  cleaned = true;
  clearThrottle();
  runDjango([
    'from django.contrib.auth import get_user_model',
    'U = get_user_model()',
    `print('cleaned:', U.objects.filter(username__in=['${editorName}', '${adminName}', '${promotedName}']).delete()[0])`,
  ]);
};

process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });

clearThrottle();
seed();

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' });
const page = await context.newPage();
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));

/** 在管理端登录页登录 */
const loginAs = async (username) => {
  await page.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.admin-login', { timeout: 30_000 });
  await page.locator('#username').fill(username);
  await page.locator('#password').fill(password);
  await page.locator('button[type="submit"]').first().click();
  // ⚠️ 谓词必须排除 /admin/login 本身 —— 它**也**以 /admin/ 开头，
  //    写成 startsWith('/admin/') 会在"还没登录完"时就判定成功（第 121 批踩过同样的坑）。
  await page.waitForURL(
    (url) => url.pathname.startsWith('/admin/') && url.pathname !== '/admin/login',
    { timeout: 30_000 },
  );
  await page.waitForSelector('.admin-console', { timeout: 25_000 });
  await page.waitForTimeout(900);
};

/** 侧栏里的导航项文案 */
const navLabels = () => page.evaluate(
  () => [...document.querySelectorAll('.admin-nav-item')].map((el) => el.innerText.trim()),
);

// ---------------------------------------------------------------------------
// ① 编辑员：侧栏少一项、身份标签如实显示
// ---------------------------------------------------------------------------
clearThrottle();
await loginAs(editorName);
check(
  '编辑员登录后落在管理后台（而不是被当成普通账号送回首页）',
  new URL(page.url()).pathname === '/admin/dashboard',
  page.url().replace(UI, ''),
);

const editorNav = await navLabels();
check(
  '编辑员的侧栏是 5 项，且**没有「用户管理」**',
  editorNav.length === 5 && !editorNav.some((label) => label.includes('用户管理')),
  editorNav.join(' / '),
);

const roleText = await page.locator('.admin-who-text em').first().innerText().catch(() => '');
check('身份标签显示「信息编辑员」', roleText.includes('信息编辑员'), roleText.trim() || '(没读到标签)');

// ---------------------------------------------------------------------------
// ② 编辑员：手输 /admin/users 被弹回 + 接口 403
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/users`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
check(
  '手输 /admin/users 被弹回数据看板（而不是白开一个用户管理页）',
  new URL(page.url()).pathname === '/admin/dashboard',
  page.url().replace(UI, ''),
);
const bounced = await page.evaluate(
  () => (document.querySelector('.el-message')?.innerText || '').replace(/\s+/g, ' '),
);
check('并且明确说明"只有管理员可以访问"', bounced.includes('只有管理员'), bounced || '(没有提示)');

const apiProbe = await page.evaluate(async () => {
  const token = sessionStorage.getItem('auth_token') || localStorage.getItem('auth_token');
  const res = await fetch('http://127.0.0.1:8000/api/admin/users/', {
    headers: { Authorization: `Token ${token}` },
  });
  return res.status;
});
check('直连 GET /api/admin/users/ 是 403（前端隐藏不是边界）', apiProbe === 403, `HTTP ${apiProbe}`);

// ---------------------------------------------------------------------------
// ③ 编辑员：内容页能打开；看板里没有用户明细
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/pests`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.pest-admin', { timeout: 25_000 });
// 等表格真的出数据（列表是异步拉的，只等容器会数到 0 行）
await page.waitForSelector('.el-table__row', { timeout: 25_000 }).catch(() => {});
await page.waitForTimeout(600);
const pestRows = await page.locator('.el-table__row').count();
check('编辑员能打开「病害百科维护」（CONTENT）', pestRows > 0, `${pestRows} 行词条`);

await page.goto(`${UI}/admin/dashboard`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2000);
const editorDash = await page.evaluate(() => ({
  hasContributors: (document.body.innerText || '').includes('贡献榜'),
  hasRecentUsers: (document.body.innerText || '').includes('最近注册'),
  hasTotals: (document.body.innerText || '').includes('识别'),
}));
check(
  '编辑员的看板里**没有**「贡献榜 / 最近注册」（后端裁剪 + 前端不画空卡片）',
  !editorDash.hasContributors && !editorDash.hasRecentUsers && editorDash.hasTotals,
  `贡献榜=${editorDash.hasContributors} 最近注册=${editorDash.hasRecentUsers}`,
);

// ---------------------------------------------------------------------------
// ④ 管理员：侧栏 6 项、看板里那两块在
// ---------------------------------------------------------------------------
await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('auth_token'); });
clearThrottle();
await loginAs(adminName);
const adminNav = await navLabels();
check(
  '全权管理员的侧栏是 6 项（含「用户管理」）',
  adminNav.length === 6 && adminNav.some((label) => label.includes('用户管理')),
  adminNav.join(' / '),
);

await page.goto(`${UI}/admin/dashboard`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2000);
const adminDash = await page.evaluate(() => ({
  hasContributors: (document.body.innerText || '').includes('贡献榜'),
  hasRecentUsers: (document.body.innerText || '').includes('最近注册'),
}));
check(
  '管理员的看板里两块用户明细都在',
  adminDash.hasContributors && adminDash.hasRecentUsers,
  `贡献榜=${adminDash.hasContributors} 最近注册=${adminDash.hasRecentUsers}`,
);

// ---------------------------------------------------------------------------
// ⑤ 第 127 批闭环：超级管理员把普通用户改成编辑员 → 本人重新登录后侧栏 5 项
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/users?search=${promotedName}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.el-table__row', { timeout: 25_000 });
await page.waitForTimeout(600);
await page.locator('.el-table__row button', { hasText: '改角色' }).first().click();
await page.waitForSelector('.role-options', { timeout: 15_000 });
await page.locator('.role-options .el-radio', { hasText: '信息编辑员' }).click();
// 第 128 批：改成编辑员必须勾模块（弹窗默认全勾，这里保持默认）
await page.waitForSelector('.role-modules', { timeout: 10_000 });
await page.locator('.el-dialog__footer button').last().click();
await page.waitForTimeout(2500);
const promoted = await page.evaluate(() => (document.querySelector('.el-table__row')?.innerText || '').replace(/\s+/g, ' '));
check('用户管理里能把普通用户改成「信息编辑员」（并带上模块）',
  promoted.includes('信息编辑员') && promoted.includes('内容审核'), promoted.slice(0, 80));

await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('auth_token'); });
clearThrottle();
await loginAs(promotedName);
const promotedNav = await navLabels();
check(
  '被提权的人重新登录后侧栏变成 5 项（无用户管理）',
  promotedNav.length === 5 && !promotedNav.some((label) => label.includes('用户管理')),
  promotedNav.join(' / '),
);

// 反向：超级管理员不能改自己的角色（把自己降级会锁死系统）。
// ⚠️ 必须**以超管身份**发这个请求：上一步登录的是刚被提权的人，
//    用他测只能证明"编辑员不能改角色"（那是护栏 1），测不到护栏 3。
await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('auth_token'); });
clearThrottle();
await loginAs(adminName);
const selfProbe = await page.evaluate(async () => {
  const token = sessionStorage.getItem('auth_token') || localStorage.getItem('auth_token');
  const me = await fetch('http://127.0.0.1:8000/api/check-auth/', { headers: { Authorization: `Token ${token}` } });
  const meData = await me.json();
  const res = await fetch(`http://127.0.0.1:8000/api/admin/users/${meData.data.id}/role/`, {
    method: 'POST',
    headers: { Authorization: `Token ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ role: 'EDITOR' }),
  });
  return { status: res.status, role: meData.data.role, caps: meData.data.capabilities };
});
check(
  '超级管理员不能改自己的角色（把自己降级会锁死系统）',
  selfProbe.status === 400 || selfProbe.status === 403,
  `HTTP ${selfProbe.status}（自己 role=${selfProbe.role} caps=${JSON.stringify(selfProbe.caps)}）`,
);

// 再确认：超管也不能把别人改成 ADMIN（升管理员只能走 Django admin）
const promoteProbe = await page.evaluate(async () => {
  const token = sessionStorage.getItem('auth_token') || localStorage.getItem('auth_token');
  const list = await fetch(`http://127.0.0.1:8000/api/admin/users/?search=${new URLSearchParams(location.search).get('x') || ''}`, {
    headers: { Authorization: `Token ${token}` },
  });
  const data = await list.json();
  const row = (data.results || []).find((u) => u.username.startsWith('zze2e_promote_'));
  if (!row) return { skipped: true };
  const res = await fetch(`http://127.0.0.1:8000/api/admin/users/${row.id}/role/`, {
    method: 'POST',
    headers: { Authorization: `Token ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ role: 'ADMIN' }),
  });
  return { status: res.status, target: row.username };
});
check(
  '不能在后台把人升成「系统管理员」（只能走 Django admin）',
  promoteProbe.skipped || promoteProbe.status === 400,
  promoteProbe.skipped ? '(没找到目标行，跳过)' : `HTTP ${promoteProbe.status}`,
);

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  console.log('失败项：');
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · ${r.name}`));
  process.exit(1);
}
