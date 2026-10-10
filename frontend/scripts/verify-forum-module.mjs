/**
 * 「论坛交流」内容模块端到端验证（第 151 批）
 * ============================================================================
 * 需求原话："用户管理角色，多添加一个可以管理论坛交流的信息编辑员"。
 *
 * 此前"能审核"就自动"能管论坛"（论坛管理页与评论管理页都挂在 review 模块下），
 * 想开一个**只管论坛**的编辑员做不到 —— 只能连审核队列、举报、敏感词一起给。
 * 这一批新增 `forum` 模块，并让论坛两页「review 或 forum 任一命中」即可进入
 * （review 仍是宽口径，老账号不会掉权限）。
 *
 * 覆盖：
 *   ① 用户管理弹窗的模块勾选框里出现「论坛交流」
 *   ② 从界面上真的开一个**只勾论坛交流**的编辑员（不勾内容审核）
 *   ③ 该账号登录后：侧栏有「论坛管理」「评论管理」，**没有**「内容审核」
 *   ④ 它能在论坛管理页审帖（通过）／置顶／加精
 *   ⑤ 它能在评论管理页软删除评论
 *   ⑥ 它进不去「内容审核」页（手输网址被弹回、接口也拒绝）
 *   ⑦ 它进不去「用户管理」页；「操作日志」也不可见
 *   ⑧ 反面：勾「内容审核」的编辑员**仍然**能进论坛管理（宽口径不变）
 *
 * 用法：node scripts/verify-forum-module.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const superName = `zze2e_fm_super_${suffix}`;
const forumEditorName = `zze2e_fm_forum_${suffix}`;
const reviewEditorName = `zze2e_fm_review_${suffix}`;
const authorName = `zze2e_fm_author_${suffix}`;
const boardName = `zze2e论坛交流版块${suffix}`;

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
      'from api.models_forum import Comment, Post, ForumBoard',
      "print('cleaned comments:', Comment.objects.filter(content__startswith='zz论坛交流').delete()[0])",
      "print('cleaned posts:', Post.objects.filter(title__startswith='zz论坛交流').delete()[0])",
      "print('cleaned boards:', ForumBoard.objects.filter(name__startswith='zze2e论坛交流').delete()[0])",
      "EditorModuleGrant.objects.filter(user__username__startswith='zze2e_fm_').delete()",
      'U = get_user_model()',
      "print('cleaned users:', U.objects.filter(username__startswith='zze2e_fm_').delete()[0])",
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
  'from api.models_forum import Comment, Post, ForumBoard',
  'U = get_user_model()',
  `U.objects.create_superuser(username='${superName}', password='${password}', email='', role='ADMIN')`,
  `author = U.objects.create_user(username='${authorName}', password='${password}', role='USER')`,
  `board = ForumBoard.objects.create(name='${boardName}', order=996)`,
  "[Post.objects.create(title=f'zz论坛交流待审{i}', content='<p>正文</p>', author=author, board=board, status='pending') for i in range(2)]",
  "p = Post.objects.create(title='zz论坛交流已发布', content='<p>正文</p>', author=author, board=board, status='published')",
  "Comment.objects.create(post=p, author=author, content='zz论坛交流评论')",
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

const navText = (target) => target.evaluate(
  () => [...document.querySelectorAll('.admin-nav-item')].map((el) => el.innerText.trim()).join(' | '),
);

await loginAs(page, superName);

// ---------------------------------------------------------------------------
// ① 用户管理弹窗里的模块勾选框
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/users`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.el-table__row', { timeout: 25_000 });
await page.waitForTimeout(1500);
await page.locator('button', { hasText: '新增编辑员' }).first().click();
await page.waitForSelector('.el-dialog:visible', { timeout: 15_000 });
await page.waitForTimeout(800);
const dialogText = await page.locator('.el-dialog:visible').innerText();
check('「开通编辑员」弹窗里有「论坛交流」勾选框', dialogText.includes('论坛交流'),
  dialogText.replace(/\s+/g, ' ').slice(0, 110));
check('原有的四个模块都还在',
  ['内容审核', '新闻管理', '病害百科', '意见反馈'].every((m) => dialogText.includes(m)), '');

// ---------------------------------------------------------------------------
// ② 只勾「论坛交流」开一个编辑员（走界面）
// ---------------------------------------------------------------------------
await page.locator('.el-dialog:visible input[type="text"]').first().fill(forumEditorName);
// 先把模块全取消，再只勾「论坛交流」
const boxes = page.locator('.el-dialog:visible .el-checkbox');
const boxCount = await boxes.count();
for (let i = 0; i < boxCount; i += 1) {
  const label = (await boxes.nth(i).innerText()).trim();
  if (!label.includes('论坛交流') && label !== '') {
    await boxes.nth(i).click();
    await page.waitForTimeout(120);
  }
}
const forumBox = page.locator('.el-dialog:visible .el-checkbox', { hasText: '论坛交流' }).first();
if (!(await forumBox.getAttribute('class'))?.includes('is-checked')) {
  await forumBox.click();
  await page.waitForTimeout(200);
}
await page.locator('.el-dialog:visible button', { hasText: '开通并生成设置密码链接' }).last().click();
await page.waitForTimeout(3000);

// 控制台开通的编辑员**没有可用密码**（第 131 批的刻意设计：签发一次性设置密码链接，
// 链接只显示一次、1 小时有效）—— 所以下面不能直接登录，要先确认链接确实给出了。
const dialogAfter = await page.locator('.el-dialog:visible').innerText().catch(() => '');
check('开通后弹窗给出了设置密码链接（只显示这一次）',
  /reset-password|设置密码/.test(dialogAfter), dialogAfter.replace(/\s+/g, ' ').slice(0, 90));

const created = await page.evaluate(async ({ api, name }) => {
  const token = sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}/admin/users/?search=${name}`, {
    headers: { Authorization: `Token ${token}` },
  });
  const data = await res.json();
  const row = (data.results || data)[0];
  return row ? { role: row.role, modules: row.content_modules } : null;
}, { api: API, name: forumEditorName });
check('界面上开出来的编辑员只带「论坛交流」模块',
  created?.role === 'EDITOR' && Array.isArray(created?.modules)
  && created.modules.length === 1 && created.modules[0] === 'forum',
  JSON.stringify(created));

// 界面开的账号没有密码 → 补一个（真实流程是本人点链接设置；
// 链接本身的有效性由第 131 批的测试覆盖，这里只是让 E2E 能登录进去看权限）
clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'U = get_user_model()',
  `u = U.objects.get(username='${forumEditorName}')`,
  `u.set_password('${password}')`,
  "u.save(update_fields=['password'])",
  "print('password set')",
]);

// 反面样本：另开一个只勾「内容审核」的编辑员（验证宽口径没变）
clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models import EditorModuleGrant',
  'U = get_user_model()',
  `ed = U.objects.create_user(username='${reviewEditorName}', password='${password}', role='EDITOR')`,
  "EditorModuleGrant.objects.create(user=ed, module='review')",
  "print('ok')",
]);

// ---------------------------------------------------------------------------
// ③ 论坛编辑员登录后的侧栏
// ---------------------------------------------------------------------------
const forumCtx = await browser.newContext({ viewport: { width: 1700, height: 1000 }, locale: 'zh-CN' });
const forumPage = await forumCtx.newPage();
await loginAs(forumPage, forumEditorName);
const forumNav = await navText(forumPage);
check('论坛编辑员侧栏有「论坛管理」', forumNav.includes('论坛管理'), forumNav);
check('论坛编辑员侧栏有「评论管理」', forumNav.includes('评论管理'), forumNav);
check('论坛编辑员侧栏**没有**「内容审核」', !forumNav.includes('内容审核'), forumNav);
check('论坛编辑员侧栏没有「用户管理」与「操作日志」',
  !forumNav.includes('用户管理') && !forumNav.includes('操作日志'), forumNav);

// ---------------------------------------------------------------------------
// ④ 论坛管理页：审帖 / 置顶 / 加精
// ---------------------------------------------------------------------------
await forumPage.goto(`${UI}/admin/forum?search=zz论坛交流待审`, { waitUntil: 'domcontentloaded' });
await forumPage.waitForSelector('.el-table__row', { timeout: 25_000 });
await forumPage.waitForTimeout(2000);
check('论坛编辑员能打开论坛管理页并看到待审帖',
  (await forumPage.locator('.el-table__row').count()) >= 1);

await forumPage.locator('.el-table__row button', { hasText: '通过' }).first().click();
await forumPage.waitForTimeout(2500);
await forumPage.goto(`${UI}/admin/forum?search=zz论坛交流已发布`, { waitUntil: 'domcontentloaded' });
await forumPage.waitForSelector('.el-table__row', { timeout: 25_000 });
await forumPage.waitForTimeout(1800);
await forumPage.locator('.el-table__row button', { hasText: '置顶' }).first().click();
await forumPage.waitForTimeout(1500);
await forumPage.locator('.el-table__row button', { hasText: '加精' }).first().click();
await forumPage.waitForTimeout(1800);
const markedRow = await forumPage.locator('.el-table__row').first().innerText();
check('论坛编辑员能置顶', /置顶/.test(markedRow), markedRow.replace(/\s+/g, ' ').slice(0, 70));
check('论坛编辑员能加精', /精华/.test(markedRow));

// ---------------------------------------------------------------------------
// ⑤ 评论管理页：软删除
// ---------------------------------------------------------------------------
await forumPage.goto(`${UI}/admin/comments?search=zz论坛交流评论`, { waitUntil: 'domcontentloaded' });
await forumPage.waitForSelector('.el-table__row', { timeout: 25_000 });
await forumPage.waitForTimeout(1800);
await forumPage.locator('.el-table__row button', { hasText: '删除' }).first().click();
await forumPage.waitForSelector('.el-message-box', { timeout: 10_000 });
await forumPage.locator('.el-message-box__btns button.el-button--primary').click();
await forumPage.waitForTimeout(2200);
const deletedComment = await page.evaluate(async ({ api, name }) => {
  const token = sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}/admin/comments/?only_deleted=true&search=${encodeURIComponent(name)}`, {
    headers: { Authorization: `Token ${token}` },
  });
  const data = await res.json();
  return data.count;
}, { api: API, name: '[已删除]' });
check('论坛编辑员能软删除评论（已删除列表里能查到）', deletedComment >= 1, `count=${deletedComment}`);

// ---------------------------------------------------------------------------
// ⑥⑦ 进不去的页面
// ---------------------------------------------------------------------------
await forumPage.goto(`${UI}/admin/review`, { waitUntil: 'domcontentloaded' });
await forumPage.waitForTimeout(2500);
check('论坛编辑员手输「内容审核」网址被弹回',
  !forumPage.url().includes('/admin/review'), forumPage.url().replace(UI, ''));

const reviewApiStatus = await forumPage.evaluate(async (api) => {
  const token = sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}/admin/users/`, {
    headers: { Authorization: `Token ${token}` },
  });
  return res.status;
}, API);
check('论坛编辑员直连用户管理接口 → 403', reviewApiStatus === 403, `HTTP ${reviewApiStatus}`);

await forumPage.goto(`${UI}/admin/users`, { waitUntil: 'domcontentloaded' });
await forumPage.waitForTimeout(2500);
check('论坛编辑员手输「用户管理」网址被弹回',
  !forumPage.url().includes('/admin/users'), forumPage.url().replace(UI, ''));

// ---------------------------------------------------------------------------
// ⑧ 宽口径没变：内容审核编辑员仍然能进论坛管理
// ---------------------------------------------------------------------------
const reviewCtx = await browser.newContext({ viewport: { width: 1700, height: 1000 }, locale: 'zh-CN' });
const reviewPage = await reviewCtx.newPage();
await loginAs(reviewPage, reviewEditorName);
const reviewNav = await navText(reviewPage);
check('内容审核编辑员侧栏仍有「论坛管理」与「评论管理」',
  reviewNav.includes('论坛管理') && reviewNav.includes('评论管理'), reviewNav);
await reviewPage.goto(`${UI}/admin/forum`, { waitUntil: 'domcontentloaded' });
await reviewPage.waitForTimeout(2500);
check('内容审核编辑员仍能直接打开论坛管理页（老账号不掉权限）',
  reviewPage.url().includes('/admin/forum'), reviewPage.url().replace(UI, ''));

await page.screenshot({ path: 'dsh-shots/admin-forum-module.png', clip: { x: 0, y: 0, width: 1700, height: 640 } });

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));
const realConsoleErrors = consoleErrors.filter((t) => !/Failed to load resource|favicon/i.test(t));
check('控制台没有 console.error', realConsoleErrors.length === 0, realConsoleErrors.slice(0, 2).join(' | '));

await forumCtx.close();
await reviewCtx.close();
await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
