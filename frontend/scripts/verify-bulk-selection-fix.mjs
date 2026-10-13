/**
 * 修复验证：「内容管理 → 帖子 → 论坛管理」批量操作后再勾选仍然有效
 *
 * 复现的原始故障（修复前实测）：
 *   ① 批量驳回 → 列表重载（父组件 forumSelectedIds 被清空）
 *   ② 再点表头复选框 → 视觉上勾上了，但批量条仍显示"勾选左侧复选框可批量处理"、
 *      「批量通过」始终 disabled → 点它浏览器不触发 click → Network 里没有任何请求
 *   根因：清空选中时只清了父组件数组，没清 el-table 的内部选中态（按 row-key 比对），
 *        同 id 的新行对象被当成"已选中"，toggleRowStatus 直接不加入、不派发事件。
 *
 * 本脚本逐步验证修复后的行为，并检查：
 *   · 每一次勾选都能同步到批量条与按钮；
 *   · 「批量通过」在勾选后真的可点、真的发 POST、真的把 hidden 恢复成 published；
 *   · 语言/权限之外不引入其它回归（无 JS 报错）。
 * 自己造数据自己清（zzfix_ 前缀）。
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzFix!2026pw';
const adminName = `zzfix_admin_${suffix}`;
const authorName = `zzfix_author_${suffix}`;
const boardName = `zzfix版块${suffix}`;

const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

let cleaned = false;
const cleanup = () => {
  if (cleaned) return;
  cleaned = true;
  try {
    runDjango([
      'from django.contrib.auth import get_user_model',
      'from api.models_forum import Post, ForumBoard',
      "print('posts deleted:', Post.objects.filter(title__startswith='zzfix').delete()[0])",
      "print('boards deleted:', ForumBoard.objects.filter(name__startswith='zzfix').delete()[0])",
      'U = get_user_model()',
      "print('users deleted:', U.objects.filter(username__startswith='zzfix_').delete()[0])",
    ]);
  } catch (error) { console.error('清理失败（忽略）:', error?.message || error); }
};
process.on('exit', cleanup);

clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models_forum import Post, ForumBoard',
  'U = get_user_model()',
  `U.objects.create_superuser(username='${adminName}', password='${password}', email='', role='ADMIN')`,
  `author = U.objects.create_user(username='${authorName}', password='${password}', role='USER')`,
  `board = ForumBoard.objects.create(name='${boardName}', order=944)`,
  "[Post.objects.create(title=f'zzfix待审{i}', content='<p>正文</p>', author=author, board=board, status='pending') for i in range(3)]",
  "print('seeded')",
]);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1700, height: 1000 }, locale: 'zh-CN' });
const page = await ctx.newPage();
let requests = [];
page.on('request', (r) => { if (r.url().includes('/api/')) requests.push(`${r.method()} ${r.url().replace(API, '').split('&_t=')[0]}`); });
const pageErrors = [];
const consoleErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });

await page.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.admin-login', { timeout: 30_000 });
await page.locator('#username').fill(adminName);
await page.locator('#password').fill(password);
await page.locator('button[type="submit"]').first().click();
await page.waitForURL((u) => u.pathname.startsWith('/admin/') && u.pathname !== '/admin/login', { timeout: 30_000 });
await page.waitForSelector('.admin-console', { timeout: 25_000 });

await page.goto(`${UI}/admin/content?tab=posts`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3200);
await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
const block = page.locator('.hub-block').filter({ has: page.locator('h2', { hasText: /^论坛管理$/ }) }).first();
await block.locator('.filter-bar .el-select').nth(0).click();
await page.waitForTimeout(700);
await page.locator('.el-select-dropdown__item:visible', { hasText: boardName }).first().click();
await page.waitForTimeout(2500);

const state = async () => ({
  bar: (await block.locator('.bulk-bar').innerText()).replace(/\s+/g, ' ').trim(),
  disabled: await block.locator('.bulk-bar button', { hasText: '批量通过' }).first().evaluate((el) => el.hasAttribute('disabled')),
});
const db = () => runDjango([
  'from api.models_forum import Post',
  "print(list(Post.objects.filter(title__startswith='zzfix').order_by('title').values_list('title','status')))",
]);
const messages = () => page.evaluate(() => [...document.querySelectorAll('.el-message')].map((el) => el.innerText.replace(/\s+/g, ' ').trim()));
const selectAll = async () => {
  await block.locator('.el-table__header .el-checkbox').first().click();
  await page.waitForTimeout(800);
  return state();
};

// ① 全选 → 批量通过（3 条 pending → published）
console.log('\n--- ① 全选 → 批量通过 ---');
let s = await selectAll();
check('全选后批量条显示已选 3 条', s.bar.includes('已选 3 条'), s.bar);
check('「批量通过」可点', s.disabled === false);
requests = [];
await block.locator('.bulk-bar button', { hasText: '批量通过' }).first().click();
await page.waitForTimeout(3200);
check('发出了 bulk-review 请求', requests.some((r) => r.includes('POST /forums/posts/bulk-review/')), requests.join(' | '));
check('库中 3 条都变成 published', (await db()).includes("'published'") && !(await db()).includes("'pending'"), await db());
console.log('提示:', JSON.stringify(await messages()));

// ② 全选 → 批量驳回（→ hidden）；这一步之后再勾选是原来坏掉的路径
console.log('\n--- ② 全选 → 批量驳回（→ 已隐藏） ---');
await page.waitForTimeout(1500);
s = await selectAll();
check('驳回前全选有效', s.bar.includes('已选 3 条'), s.bar);
requests = [];
await block.locator('.bulk-bar button', { hasText: '批量驳回' }).first().click();
await page.waitForSelector('.el-dialog:visible', { timeout: 10_000 });
await page.locator('.el-dialog:visible textarea').fill('验证：批量驳回');
await page.locator('.el-dialog:visible .el-button--danger').first().click();
await page.waitForTimeout(3200);
check('库中 3 条都变成 hidden', !(await db()).includes("'published'"), await db());

// ③ 【核心回归点】批量操作之后再全选 —— 修复前这里批量条不会变
console.log('\n--- ③ 批量操作后**再次**全选（修复前此处失灵） ---');
await page.waitForTimeout(1500);
s = await selectAll();
check('再次全选后批量条显示已选 3 条（修复前恒为"未选"）', s.bar.includes('已选 3 条'), s.bar);
check('「批量通过」再次可点（修复前恒 disabled）', s.disabled === false);

// ④ 用「批量通过」把已隐藏的帖子恢复（第 187 批的能力，走的是同一条链路）
console.log('\n--- ④ 批量通过（恢复已隐藏的帖子） ---');
requests = [];
let clicked = true;
try {
  await block.locator('.bulk-bar button', { hasText: '批量通过' }).first().click({ timeout: 5000 });
} catch (e) {
  clicked = false;
  console.log('点击失败:', String(e).split('\n')[0]);
}
await page.waitForTimeout(3500);
check('「批量通过」点击成功（不再被 disabled 吞掉）', clicked);
check('发出了 bulk-review 请求（用户报的"没有请求"已修复）', requests.some((r) => r.includes('POST /forums/posts/bulk-review/')), requests.join(' | '));
const finalDb = await db();
check('库中 3 条恢复成 published', !finalDb.includes("'hidden'") && !finalDb.includes("'pending'"), finalDb);
console.log('提示:', JSON.stringify(await messages()));

// ⑤ 单行勾选 / 取消勾选仍然正常
//
// ⚠️ 这里**等状态、不等固定毫秒数**：批量条的文案是 el-table 派发 selection-change
//    之后才更新的，写死 700ms 会在机器慢一点时读到旧文案（第 188 批自己踩过：
//    加了 ⑥ 之后这条偶发变红，查清是脚本时序问题，不是产品问题）。
console.log('\n--- ⑤ 单行勾选与取消 ---');
await page.waitForTimeout(1500);
const barText = () => block.locator('.bulk-bar').innerText();
const waitBar = (pattern) => page.waitForFunction(
  ([p]) => {
    // 只认「论坛管理」区块的批量条（页面里还有审核队列的同类元素）
    const el = document.querySelector('.hub-block:has([data-testid="forum-table"]) .bulk-bar');
    return el ? new RegExp(p).test(el.innerText) : false;
  },
  [pattern],
  { timeout: 8000 },
).catch(() => {});

await block.locator('.el-table__body .el-checkbox').first().click();
await waitBar('已选 1 条');
s = await state();
check('勾一条 → 已选 1 条', s.bar.includes('已选 1 条'), s.bar);

await block.locator('.el-table__body .el-checkbox').first().click();
await waitBar('勾选左侧复选框');
s = await state();
check('再点一次 → 回到未选', s.bar.includes('勾选左侧复选框'), s.bar);

// ⑥ 行内「恢复发布」：已隐藏的帖子单条也能恢复（第 187 批遗留的入口缺口）
console.log('\n--- ⑥ 已隐藏帖子的**行内**恢复发布 ---');
// 先把一条重新下架（批量驳回），再看行内按钮
await selectAll();
await block.locator('.bulk-bar button', { hasText: '批量驳回' }).first().click();
await page.waitForSelector('.el-dialog:visible', { timeout: 10_000 });
await page.locator('.el-dialog:visible textarea').fill('验证：行内恢复发布前先下架');
await page.locator('.el-dialog:visible .el-button--danger').first().click();
await page.waitForTimeout(3500);
const hiddenDb = await db();
check('已下架（库中至少一条 hidden）', hiddenDb.includes("'hidden'"), hiddenDb);

const firstRow = block.locator('.el-table__row').first();
const rowButtons = (await firstRow.innerText()).replace(/\s+/g, ' ').trim();
check('已隐藏的行里有「恢复发布」按钮', rowButtons.includes('恢复发布'), rowButtons.slice(0, 80));
// 按钮文字是独立的词（DOM 渲染后前后有空白），所以用带边界的判断，
// 不会被「恢复发布」这四个字里的"发布"误命中
check('对已隐藏的行不显示「通过」（文案不混用）',
  !/(^|\s)通过(\s|$)/.test(rowButtons), rowButtons.slice(0, 80));
requests = [];
await firstRow.locator('button', { hasText: '恢复发布' }).first().click();
await page.waitForTimeout(3000);
check('行内恢复发出了 approve 请求',
  requests.some((r) => /POST \/forums\/posts\/\d+\/approve\//.test(r)), requests.join(' | '));
const restoredDb = await db();
check('该帖回到 published',
  (restoredDb.match(/'published'/g) || []).length >= 1, restoredDb);
console.log('提示:', JSON.stringify(await messages()));

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));
check('全程无 console.error', consoleErrors.length === 0, consoleErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
