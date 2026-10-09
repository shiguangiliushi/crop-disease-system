/**
 * 内容模块隔离的端到端验证（第 128 批）
 * ============================================================================
 * 用户要求："信息编辑员分为内容审核、新闻管理、病害百科、意见反馈，
 * 功能互不干扰，只能管理自己的。"
 *
 * 这件事**必须**用真账号登录验证：后端测试能证明接口 403，但证明不了
 * "侧栏里真的只显示他被授权的那几项" —— 那才是用户看到的东西。
 *
 * 覆盖：
 *   ① 只勾「新闻管理」的编辑员：侧栏只有 数据看板 + 新闻管理
 *   ② 他能发新闻（自己那块真的能用）
 *   ③ 他打不开病害百科维护 / 内容审核 / 意见反馈（手输网址被弹回 + 明确提示）
 *   ④ 他直连别的模块的接口 → 403（前端隐藏不是边界）
 *   ⑤ 超管在用户管理里看到他的模块标签，并能把模块改成「病害百科 + 意见反馈」
 *   ⑥ 他重新登录后侧栏变成 数据看板 + 病害百科维护 + 意见反馈管理
 *   ⑦ 越界反向再验一次：现在他打不开新闻管理、也发不了新闻
 *
 * 用法：node scripts/verify-content-modules.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const editorName = `zze2e_mod_${suffix}`;
const superName = `zze2e_modsuper_${suffix}`;

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
      'from api.models import EditorModuleGrant, News, PestInfo',
      'U = get_user_model()',
      `users = U.objects.filter(username__in=['${editorName}', '${superName}'])`,
      'EditorModuleGrant.objects.filter(user__in=users).delete()',
      'print("cleaned users:", users.delete()[0])',
      'print("cleaned news:", News.objects.filter(title__startswith="zze2e").delete()[0])',
      'print("cleaned pests:", PestInfo.objects.filter(english_identifier__startswith="zze2e").delete()[0])',
    ]);
  } catch (error) {
    // ⚠️ 退出钩子里**必须吞掉异常**：这里一抛，清理就半途而废（本批就踩过：
    //    库还没建表时清理失败，临时账号全留在库里）。宁可少删也不要中断。
    console.error('清理临时数据失败（忽略）:', error?.message || error);
  }
};

process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });

clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'U = get_user_model()',
  `e = U.objects.create_user(username='${editorName}', password='${password}', role='EDITOR')`,
  `s = U.objects.create_superuser(username='${superName}', password='${password}', email='', role='ADMIN')`,
  "print('seeded')",
]);

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' });
const page = await context.newPage();
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));

const loginAs = async (username) => {
  await page.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.admin-login', { timeout: 30_000 });
  await page.locator('#username').fill(username);
  await page.locator('#password').fill(password);
  await page.locator('button[type="submit"]').first().click();
  // ⚠️ 排除 /admin/login 本身（它也以 /admin/ 开头 —— 第 121/126 批都踩过）
  await page.waitForURL(
    (url) => url.pathname.startsWith('/admin/') && url.pathname !== '/admin/login',
    { timeout: 30_000 },
  );
  await page.waitForSelector('.admin-console', { timeout: 25_000 });
  await page.waitForTimeout(900);
};

const logout = async () => {
  await page.evaluate(() => { sessionStorage.clear(); localStorage.removeItem('auth_token'); });
};

const navLabels = () => page.evaluate(
  () => [...document.querySelectorAll('.admin-nav-item')].map((el) => el.innerText.trim()),
);

/** 以当前登录身份直连一个接口，返回状态码 */
const apiStatus = (path, method = 'GET', body = null) => page.evaluate(async ({ path, method, body }) => {
  const token = sessionStorage.getItem('auth_token') || localStorage.getItem('auth_token');
  const res = await fetch(`http://127.0.0.1:8000/api${path}`, {
    method,
    headers: {
      Authorization: `Token ${token}`,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  return res.status;
}, { path, method, body });

// ---------------------------------------------------------------------------
// ① 超管先把这个人仅授权「新闻管理」
// ---------------------------------------------------------------------------
clearThrottle();
await loginAs(superName);
await page.goto(`${UI}/admin/users?search=${editorName}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.el-table__row', { timeout: 25_000 });
await page.waitForTimeout(500);
await page.locator('.el-table__row button', { hasText: '改角色' }).first().click();
await page.waitForSelector('.role-modules', { timeout: 15_000 });
// 先取消全勾（默认全勾），只留「新闻管理」
for (const label of ['内容审核', '病害百科', '意见反馈']) {
  await page.locator('.role-modules .el-checkbox', { hasText: label }).click();
}
await page.locator('.role-options .el-radio', { hasText: '信息编辑员' }).click();
await page.locator('.el-dialog__footer button').last().click();
await page.waitForTimeout(2500);
const rowText = await page.evaluate(
  () => (document.querySelector('.el-table__row')?.innerText || '').replace(/\s+/g, ' '),
);
check('超管能只勾「新闻管理」并把该账号设为编辑员', rowText.includes('新闻管理') && rowText.includes('信息编辑员'),
  rowText.slice(0, 80));

// ---------------------------------------------------------------------------
// ② 该编辑员登录：侧栏只有 看板 + 新闻管理
// ---------------------------------------------------------------------------
await logout();
clearThrottle();
await loginAs(editorName);
const nav1 = await navLabels();
check(
  '只勾新闻管理的编辑员：侧栏只有「数据看板 + 新闻管理」',
  nav1.length === 2 && nav1.some((l) => l.includes('数据看板')) && nav1.some((l) => l.includes('新闻管理')),
  nav1.join(' / '),
);

const newsStatus = await apiStatus('/news/', 'POST', { title: `zze2e模块新闻_${suffix}`, content: '<p>x</p>', category: 'notice' });
check('他自己那一块真能用：发新闻 201', newsStatus === 201, `HTTP ${newsStatus}`);

const pestStatus = await apiStatus('/pests/', 'POST', {
  name: 'zze2e模块越界', crop_type: '玉米', english_identifier: `zze2e_mod_${suffix}`, prevention_methods: [],
});
check('越界：直连病害百科新增 → 403', pestStatus === 403, `HTTP ${pestStatus}`);

const approveStatus = await apiStatus('/forums/posts/999999/approve/', 'POST');
check('越界：直连帖子审核 → 403/404（不该 200）', approveStatus !== 200, `HTTP ${approveStatus}`);

// ---------------------------------------------------------------------------
// ③ 手输别的模块网址：被弹回并说明缺哪一块
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/pests`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
const bouncedTo = new URL(page.url()).pathname;
const bounceMsg = await page.evaluate(
  () => (document.querySelector('.el-message')?.innerText || '').replace(/\s+/g, ' '),
);
check('手输 /admin/pests 被弹回看板', bouncedTo === '/admin/dashboard', page.url().replace(UI, ''));
check('并且明确说缺「病害百科」权限', bounceMsg.includes('病害百科'), bounceMsg || '(没有提示)');

await page.goto(`${UI}/admin/feedback`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1200);
check('手输 /admin/feedback 也被弹回', new URL(page.url()).pathname === '/admin/dashboard',
  page.url().replace(UI, ''));

// ---------------------------------------------------------------------------
// ④ 超管把模块改成「病害百科 + 意见反馈」
// ---------------------------------------------------------------------------
await logout();
clearThrottle();
await loginAs(superName);
await page.goto(`${UI}/admin/users?search=${editorName}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.el-table__row', { timeout: 25_000 });
await page.waitForTimeout(500);
await page.locator('.el-table__row button', { hasText: '改角色' }).first().click();
await page.waitForSelector('.role-modules', { timeout: 15_000 });
// 回填的是他现有的模块（新闻管理）→ 换成 病害百科 + 意见反馈
await page.locator('.role-modules .el-checkbox', { hasText: '病害百科' }).click();
await page.locator('.role-modules .el-checkbox', { hasText: '意见反馈' }).click();
await page.locator('.role-modules .el-checkbox', { hasText: '新闻管理' }).click();
await page.locator('.el-dialog__footer button').last().click();
await page.waitForTimeout(2500);
const rowText2 = await page.evaluate(
  () => (document.querySelector('.el-table__row')?.innerText || '').replace(/\s+/g, ' '),
);
check(
  '改模块后列表标签变成「病害百科、意见反馈」（新闻管理已移除）',
  rowText2.includes('病害百科') && rowText2.includes('意见反馈') && !rowText2.includes('新闻管理'),
  rowText2.slice(0, 90),
);

// ---------------------------------------------------------------------------
// ⑤ 编辑员重新登录：侧栏跟着变；新闻管理反过来打不开了
// ---------------------------------------------------------------------------
await logout();
clearThrottle();
await loginAs(editorName);
const nav2 = await navLabels();
check(
  '重新登录后侧栏变成 看板 + 病害百科维护 + 意见反馈管理',
  nav2.length === 3 && nav2.some((l) => l.includes('病害百科')) && nav2.some((l) => l.includes('意见反馈'))
    && !nav2.some((l) => l.includes('新闻管理')),
  nav2.join(' / '),
);

const newsStatus2 = await apiStatus('/news/', 'POST', { title: 'zze2e越界新闻', content: '<p>x</p>' });
check('反向：他现在发不了新闻（403）', newsStatus2 === 403, `HTTP ${newsStatus2}`);

const pestStatus2 = await apiStatus('/pests/', 'POST', {
  name: 'zze2e模块新增', crop_type: '玉米', english_identifier: `zze2e_mod2_${suffix}`,
  symptoms: 'x', prevention_methods: [],
});
check('反向：他现在能新增病害词条（201）', pestStatus2 === 201, `HTTP ${pestStatus2}`);

// 清理测试数据（词条 + 新闻）
runDjango([
  'from api.models import PestInfo, News',
  `print('cleanup pest:', PestInfo.objects.filter(english_identifier__startswith='zze2e_mod').delete()[0])`,
  `print('cleanup news:', News.objects.filter(title__startswith='zze2e模块新闻').delete()[0])`,
]);

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
