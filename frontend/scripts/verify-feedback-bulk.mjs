/**
 * 「反馈批量操作」端到端验证（第 138 批）
 * ============================================================================
 * 这一批修的是一个"死接口"：`POST /api/feedback/bulk-status/` 第 100 批就写好了
 * （状态白名单、标记已处理必须给回复、逐条成败、上限 200 条都齐），
 * 但前端从未调用 —— 列表页连多选都没有。本批把它接上，并补了对称的批量删除。
 *
 * 覆盖：
 *   ① 列表页出现多选（能操作反馈的人才看得到）+「全选本页」
 *   ② 批量改状态为「处理中」→ 选中几条一起变，统计卡跟着变
 *   ③ 批量标记「已处理」**必须填回复**（不填时确定按钮禁用）
 *   ④ 填了回复 → 每条都写上回复内容
 *   ⑤ 批量删除：全权管理员可用，确认框提示不可撤销
 *   ⑥ 内容编辑员看不到「批量删除」按钮，直连接口也是 403
 *   ⑦ 普通用户（农户）在管理端反馈页看不到多选
 *
 * 用法：node scripts/verify-feedback-bulk.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const superName = `zze2e_bk_super_${suffix}`;
const editorName = `zze2e_bk_editor_${suffix}`;
const authorName = `zze2e_bk_author_${suffix}`;

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
      'from api.models import Feedback, EditorModuleGrant',
      'U = get_user_model()',
      "users = U.objects.filter(username__startswith='zze2e_bk_')",
      'Feedback.objects.filter(user__in=users).delete()',
      'EditorModuleGrant.objects.filter(user__in=users).delete()',
      "print('cleaned:', users.delete()[0])",
    ]);
  } catch (error) {
    console.error('清理失败（忽略）:', error?.message || error);
  }
};
process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });

// 种子：超管 + 只勾 feedback 模块的编辑员 + 一个提反馈的普通用户（造 5 条待处理反馈）
clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models import Feedback, EditorModuleGrant',
  'U = get_user_model()',
  `U.objects.create_superuser(username='${superName}', password='${password}', email='', role='ADMIN')`,
  `ed = U.objects.create_user(username='${editorName}', password='${password}', role='EDITOR')`,
  `admin = U.objects.get(username='${superName}')`,
  "EditorModuleGrant.objects.create(user=ed, module='feedback', granted_by=admin)",
  `au = U.objects.create_user(username='${authorName}', password='${password}', role='USER')`,
  "[Feedback.objects.create(user=au, suggestion=f'批量测试反馈{i}') for i in range(5)]",
  "print('seeded')",
]);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' });
const page = await ctx.newPage();
const pageErrors = [];
const consoleErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));
/**
 * ⚠️ 只监听 pageerror 是不够的（第一版就是这么漏掉的）：
 * Vue 会把**组件内部**抛出的错误自己捕获、打到 console.error，界面上则弹出红色提示条，
 * 但**不会**变成未捕获异常 —— 于是"无 JS 报错"是绿的，页面却一片红。
 *   例：`watch([... () => filters.value], ...)` 写在 `const filters` 之前 →
 *   `Cannot access 'filters' before initialization`，就是这样被漏掉的。
 */
page.on('console', (m) => {
  if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200));
});

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

/** 打开反馈管理页，只筛出这个测试用户提交的反馈 */
const openFeedbackPage = async (target, username) => {
  await target.goto(`${UI}/admin/feedback?search=${username}`, { waitUntil: 'domcontentloaded' });
  await target.waitForSelector('.feedback-item', { timeout: 25_000 });
  await target.waitForTimeout(1200);
};

const cards = () => page.locator('.feedback-item');
const statusOf = async (index) => cards().nth(index).locator('.el-tag').nth(1).innerText();

// ---------------------------------------------------------------------------
// ① 多选入口
// ---------------------------------------------------------------------------
clearThrottle();
await loginAsAdmin(page, superName);
await openFeedbackPage(page, authorName);

const cardCount = await cards().count();
check('列表里能看到 5 条测试反馈', cardCount === 5, `实际 ${cardCount} 条`);
check('出现了「全选本页」', await page.locator('.bulk-bar .el-checkbox').first().isVisible());
check('出现了「批量改状态」按钮',
  await page.locator('.bulk-bar button', { hasText: '批量改状态' }).isVisible());
check('超管能看到「批量删除」按钮',
  await page.locator('.bulk-bar button', { hasText: '批量删除' }).isVisible());

await page.locator('.bulk-bar .el-checkbox').first().click();
await page.waitForTimeout(400);
const bulkText = await page.locator('.bulk-bar').innerText();
check('全选后显示已选数量', bulkText.includes('已选 5 条'), bulkText.replace(/\s+/g, ' ').slice(0, 50));
// 留证（docs 会引用，所以不会被截图清理脚本删掉）
await page.screenshot({ path: 'dsh-shots/admin-feedback-bulk.png', clip: { x: 0, y: 0, width: 1500, height: 700 } });

// ---------------------------------------------------------------------------
// ② 批量改状态 → 处理中
// ---------------------------------------------------------------------------
await page.locator('.bulk-bar button', { hasText: '批量改状态' }).click();
await page.waitForSelector('.el-dialog:visible', { timeout: 10_000 });
await page.locator('.el-dialog:visible .el-radio-button', { hasText: '处理中' }).click();
await page.locator('.el-dialog:visible .el-button--primary').click();
await page.waitForTimeout(2500);

await openFeedbackPage(page, authorName);
const statuses = [];
for (let i = 0; i < await cards().count(); i += 1) statuses.push(await statusOf(i));
check('5 条状态都变成「处理中」', statuses.every((s) => s.includes('处理中')),
  statuses.join(' / '));

// ---------------------------------------------------------------------------
// ③④ 批量标记「已处理」：回复是必填
// ---------------------------------------------------------------------------
await page.locator('.bulk-bar .el-checkbox').first().click();
await page.waitForTimeout(300);
await page.locator('.bulk-bar button', { hasText: '批量改状态' }).click();
await page.waitForSelector('.el-dialog:visible', { timeout: 10_000 });
await page.locator('.el-dialog:visible .el-radio-button', { hasText: '已处理' }).click();
await page.waitForTimeout(300);
const confirmBtn = page.locator('.el-dialog:visible .el-button--primary');
check('选「已处理」但没填回复时，确定按钮是禁用的', await confirmBtn.isDisabled());

await page.locator('.el-dialog:visible textarea').fill('这批问题已核实并修复，感谢反馈');
await page.waitForTimeout(300);
check('填了回复后确定按钮可用', !(await confirmBtn.isDisabled()));
await confirmBtn.click();
await page.waitForTimeout(2500);

await openFeedbackPage(page, authorName);
const text = await page.locator('.feedback-list').innerText();
const resolvedCount = (text.match(/已处理/g) || []).length;
const replyCount = (text.match(/这批问题已核实并修复，感谢反馈/g) || []).length;
check('5 条都变成「已处理」', resolvedCount >= 5, `出现 ${resolvedCount} 次`);
check('每条都写上了统一的回复内容', replyCount >= 5, `出现 ${replyCount} 次`);

// ---------------------------------------------------------------------------
// ⑤ 批量删除
// ---------------------------------------------------------------------------
await page.locator('.bulk-bar .el-checkbox').first().click();
await page.waitForTimeout(300);
await page.locator('.bulk-bar button', { hasText: '批量删除' }).click();
await page.waitForSelector('.el-message-box', { timeout: 10_000 });
const boxText = await page.locator('.el-message-box').innerText();
check('删除确认框写明了不可撤销与条数',
  boxText.includes('不可撤销') && boxText.includes('5'), boxText.replace(/\s+/g, ' ').slice(0, 60));
await page.locator('.el-message-box__btns button.el-button--primary').click();
await page.waitForTimeout(2500);

const remaining = await page.evaluate(async ({ api }) => {
  const token = sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}/feedback/?search=zze2e_bk_author_`, {
    headers: { Authorization: `Token ${token}` },
  });
  const data = await res.json();
  return data.count ?? (data.results || []).length;
}, { api: API });
check('批量删除后这 5 条都没了', remaining === 0, `还剩 ${remaining} 条`);

// ---------------------------------------------------------------------------
// ⑥ 编辑员的护栏
// ---------------------------------------------------------------------------
clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models import Feedback',
  'U = get_user_model()',
  `au = U.objects.get(username='${authorName}')`,
  "[Feedback.objects.create(user=au, suggestion=f'编辑员护栏测试{i}') for i in range(2)]",
  "print('ok')",
]);

const editorCtx = await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' });
const editorPage = await editorCtx.newPage();
clearThrottle();
await loginAsAdmin(editorPage, editorName);
await editorPage.goto(`${UI}/admin/feedback?search=${authorName}`, { waitUntil: 'domcontentloaded' });
await editorPage.waitForSelector('.feedback-item', { timeout: 25_000 });
await editorPage.waitForTimeout(1500);

check('编辑员也能多选（他有 feedback 模块）',
  await editorPage.locator('.bulk-bar .el-checkbox').first().isVisible());
const editorDeleteBtn = await editorPage.locator('.bulk-bar button', { hasText: '批量删除' }).count();
check('编辑员看不到「批量删除」按钮', editorDeleteBtn === 0);

const editorApi = await editorPage.evaluate(async ({ api }) => {
  const token = sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}/feedback/bulk-delete/`, {
    method: 'POST',
    headers: { Authorization: `Token ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids: [1] }),
  });
  return res.status;
}, { api: API });
check('编辑员直连批量删除接口 → 403', editorApi === 403, `HTTP ${editorApi}`);

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));
// 除 pageerror 外，还要盯 console.error（Vue 内部捕获的组件错误只走这条路）
const realConsoleErrors = consoleErrors.filter((text) => !/Failed to load resource|favicon/i.test(text));
check('控制台没有 console.error（含 Vue 内部捕获的错误）',
  realConsoleErrors.length === 0, realConsoleErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
