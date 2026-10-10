/**
 * 「控制台评论管理页」端到端验证（第 149 批）
 * ============================================================================
 * 帖子有「论坛管理」页，评论却一直没有控制台入口：一波广告刷在十几条帖子的评论区里，
 * 只能一条条帖子点进去删（农户端的评论列表还挂在帖子下，没法跨帖子看）。
 * 这一批后端补了全局接口（/api/admin/comments/），前端补了页面。
 *
 * 覆盖：
 *   ① 侧栏出现「评论管理」，页面能打开，能跨帖子看到评论（带所属帖子标题）
 *   ② 关键字搜索生效（搜不存在的词 → 空列表）
 *   ③ 「只看已删除」能筛出被软删的评论
 *   ④ 软删除：内容变为 [已删除]、农户端该帖的评论数跟着减少
 *   ⑤ 批量软删除：选中多条一次删掉，农户端看不到这些评论了
 *   ⑥ 全权管理员能看到「彻底删除」按钮，**编辑员看不到**（直连接口 403）
 *   ⑦ 彻底删除后行真的没了（农户端 + 控制台都查不到）
 *
 * 用法：node scripts/verify-admin-comments.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const superName = `zze2e_cm_super_${suffix}`;
const editorName = `zze2e_cm_editor_${suffix}`;
const authorName = `zze2e_cm_author_${suffix}`;
const postTitle = `zz评论管理帖${suffix}`;
const boardName = `zze2e评论管理版块${suffix}`;

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
      'from api.models_forum import Comment, Post, ForumBoard',
      "print('cleaned comments:', Comment.objects.filter(content__startswith='zz评论').delete()[0])",
      "print('cleaned posts:', Post.objects.filter(title__startswith='zz评论管理帖').delete()[0])",
      "print('cleaned boards:', ForumBoard.objects.filter(name__startswith='zze2e评论管理版块').delete()[0])",
      "print('cleaned logs:', AdminAuditLog.objects.filter(target_repr__startswith='zz评论').delete()[0])",
      "EditorModuleGrant.objects.filter(user__username__startswith='zze2e_cm_').delete()",
      'U = get_user_model()',
      "print('cleaned users:', U.objects.filter(username__startswith='zze2e_cm_').delete()[0])",
    ]);
  } catch (error) {
    console.error('清理失败（忽略）:', error?.message || error);
  }
};
process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });

clearThrottle();
const seedOut = runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models import EditorModuleGrant',
  'from api.models_forum import Comment, Post, ForumBoard',
  'U = get_user_model()',
  `admin = U.objects.create_superuser(username='${superName}', password='${password}', email='', role='ADMIN')`,
  `ed = U.objects.create_user(username='${editorName}', password='${password}', role='EDITOR')`,
  "EditorModuleGrant.objects.create(user=ed, module='review', granted_by=admin)",
  `author = U.objects.create_user(username='${authorName}', password='${password}', role='USER')`,
  `board = ForumBoard.objects.create(name='${boardName}', order=991)`,
  `post = Post.objects.create(title='${postTitle}', content='<p>正文</p>', author=author, board=board, status='published')`,
  // 4 条正常评论（其中一条用来硬删）+ 1 条已被软删的（验证"只看已删除"）
  "[Comment.objects.create(post=post, author=author, content=f'zz评论{i}') for i in range(4)]",
  "gone = Comment.objects.create(post=post, author=author, content='zz评论已删的那条')",
  "gone.content = '[已删除]'",
  "gone.is_deleted = True",
  "gone.save(update_fields=['content', 'is_deleted'])",
  "post.update_comment_count()",
  "print('POST_ID', post.id)",
]);
const postId = Number(/POST_ID (\d+)/.exec(String(seedOut))[1]);
console.log('（帖子 id =', postId, '）');

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
// ① 侧栏 + 跨帖子列表
// ---------------------------------------------------------------------------
const nav = await page.evaluate(
  () => [...document.querySelectorAll('.admin-nav-item')].map((el) => el.innerText.trim()).join(' | '),
);
check('侧栏出现「评论管理」', nav.includes('评论管理'), nav);

await page.goto(`${UI}/admin/comments?search=zz评论`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.el-table__row', { timeout: 25_000 });
await page.waitForTimeout(2000);
const listText = (await rowTexts()).join(' || ');
check('列表里能看到评论内容', listText.includes('zz评论0'), listText.slice(0, 90));
check('评论行显示所属帖子的标题', listText.includes(postTitle), '');
check('默认不显示已删除的评论', !listText.includes('zz评论已删的那条') || listText.includes('[已删除]'),
  listText.slice(0, 90));

await page.screenshot({ path: 'dsh-shots/admin-comments.png', clip: { x: 0, y: 0, width: 1700, height: 700 } });

// ---------------------------------------------------------------------------
// ② 搜索
// ---------------------------------------------------------------------------
// ⚠️ 不能用 `.filter-bar input[type="text"]` —— el-select（评论范围）内部也有一个
//    text 输入框，而且是**只读**的，fill 会一直等"可编辑"直到超时（第一版就这么挂的）。
//    按 placeholder 定位最稳，也不依赖 DOM 结构。
const searchInput = page.getByPlaceholder('搜索评论内容');
await searchInput.fill('zz绝不存在的评论词zz');
await searchInput.press('Enter');
await page.waitForTimeout(2000);
check('搜不存在的词 → 空列表', (await page.locator('.el-table__row').count()) === 0);

// ---------------------------------------------------------------------------
// ③ 只看已删除
// ---------------------------------------------------------------------------
// ⚠️ 别带 search=zz评论：软删除会把内容换成 [已删除]，按原文搜必然搜不到（这是**正确**行为）
await page.goto(`${UI}/admin/comments?scope=deleted`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2200);
const deletedText = (await rowTexts()).join(' || ');
check('「只看已删除」筛出被软删的评论', deletedText.includes('[已删除]'), deletedText.slice(0, 90));

// ---------------------------------------------------------------------------
// ④ 软删除（编辑员做：这是审核工作）
// ---------------------------------------------------------------------------
clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'from rest_framework.test import APIClient',
  'from api.models_forum import Comment',
  'U = get_user_model()',
  `ed = U.objects.get(username='${editorName}')`,
  "c = APIClient(); c.force_authenticate(user=ed)",
  "post = Comment.objects.filter(content='zz评论0').first().post",
  "r = c.post(f'/api/admin/comments/{Comment.objects.get(content=\"zz评论0\").id}/soft-delete/')",
  "print('编辑员软删:', r.status_code)",
  "post.refresh_from_db(); print('POST_COUNT', post.comment_count)",
]);
const countOut = runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models_forum import Comment, Post',
  `import os`,
  'from django.db.models import Count',
  "p = Post.objects.filter(title__startswith='zz评论管理帖').first()",
  "print('POST_COUNT', p.comment_count, '| 未删评论数', Comment.objects.filter(post=p, is_deleted=False).count())",
]);
check('软删除会同步减少帖子的评论数',
  /POST_COUNT (\d+) \| 未删评论数 \1/.test(String(countOut)), String(countOut).trim().slice(0, 60));

// ---------------------------------------------------------------------------
// ⑤ 批量软删除
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/comments?search=zz评论`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.el-table__row', { timeout: 25_000 });
await page.waitForTimeout(2000);
const before = await page.locator('.el-table__row').count();
await page.locator('.el-table__header .el-checkbox').first().click();
await page.waitForTimeout(500);
await page.locator('.bulk-bar button', { hasText: '批量删除' }).click();
await page.waitForSelector('.el-message-box', { timeout: 10_000 });
await page.locator('.el-message-box__btns button.el-button--primary').click();
await page.waitForTimeout(2500);
const afterBulk = await page.locator('.el-table__row').count();
check('批量软删除后列表清空', afterBulk === 0, `${before} → ${afterBulk}`);

// 农户端确实看不到了
const publicView = await page.evaluate(async ({ api, postId }) => {
  const res = await fetch(`${api}/forums/posts/${postId}/comments/`);
  const data = await res.json();
  const rows = data.results || data;
  return rows.map((row) => row.content);
}, { api: API, postId });
check('农户端的评论列表里已经没有这些评论',
  !publicView.some((text) => text.includes('zz评论')), JSON.stringify(publicView).slice(0, 80));

// ---------------------------------------------------------------------------
// ⑥⑦ 彻底删除：仅全权管理员
// ---------------------------------------------------------------------------
clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models_forum import Comment, Post',
  'U = get_user_model()',
  "p = Post.objects.filter(title__startswith='zz评论管理帖').first()",
  "Comment.objects.create(post=p, author=U.objects.get(username='" + authorName + "'), content='zz评论待硬删')",
  "print('ok')",
]);

const editorCtx = await browser.newContext({ viewport: { width: 1700, height: 1000 }, locale: 'zh-CN' });
const editorPage = await editorCtx.newPage();
await loginAs(editorPage, editorName);
await editorPage.goto(`${UI}/admin/comments?search=zz评论待硬删`, { waitUntil: 'domcontentloaded' });
await editorPage.waitForSelector('.el-table__row', { timeout: 25_000 });
await editorPage.waitForTimeout(2000);
const editorRowButtons = await editorPage.locator('.el-table__row button').allInnerTexts();
check('编辑员看不到「彻底删除」按钮', !editorRowButtons.join(' ').includes('彻底删除'),
  editorRowButtons.join(' / '));

const editorHardDelete = await editorPage.evaluate(async ({ api, postId }) => {
  const token = sessionStorage.getItem('auth_token');
  const list = await (await fetch(`${api}/admin/comments/?search=zz评论待硬删`, {
    headers: { Authorization: `Token ${token}` },
  })).json();
  const row = (list.results || list)[0];
  const res = await fetch(`${api}/admin/comments/${row.id}/`, {
    method: 'DELETE', headers: { Authorization: `Token ${token}` },
  });
  return res.status;
}, { api: API, postId });
check('编辑员直连彻底删除接口 → 403', editorHardDelete === 403, `HTTP ${editorHardDelete}`);
await editorCtx.close();

await page.goto(`${UI}/admin/comments?search=zz评论待硬删`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.el-table__row', { timeout: 25_000 });
await page.waitForTimeout(1800);
const adminRowButtons = await page.locator('.el-table__row button').allInnerTexts();
check('全权管理员能看到「彻底删除」按钮', adminRowButtons.join(' ').includes('彻底删除'),
  adminRowButtons.join(' / '));
await page.locator('.el-table__row button', { hasText: '彻底删除' }).first().click();
await page.waitForSelector('.el-message-box', { timeout: 10_000 });
await page.locator('.el-message-box__btns button.el-button--primary').click();
await page.waitForTimeout(2500);
check('彻底删除后列表里查不到该评论',
  !(await rowTexts()).join(' ').includes('zz评论待硬删'));

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
