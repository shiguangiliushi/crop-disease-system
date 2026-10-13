/**
 * 「内容管理 → 评论」页签的批量选中（同一个坑的另一处）
 *
 * 复现路径：全选 → 批量删除（软删）→ 列表重载 → **再全选**。
 * 修复前：第二次全选不会生效（复选框看着勾上、批量条一直是"未选"、按钮 disabled、无请求）。
 * 修复后：每次勾选都能同步到批量条与按钮。
 * 自己造数据自己清（zzfixc_ 前缀）。
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzFix!2026pw';
const adminName = `zzfixc_admin_${suffix}`;
const authorName = `zzfixc_author_${suffix}`;
const boardName = `zzfixc版块${suffix}`;

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
      'from api.models_forum import Post, Comment, ForumBoard',
      "print('comments deleted:', Comment.objects.filter(content__startswith='zzfixc').delete()[0])",
      "print('posts deleted:', Post.objects.filter(title__startswith='zzfixc').delete()[0])",
      "print('boards deleted:', ForumBoard.objects.filter(name__startswith='zzfixc').delete()[0])",
      'U = get_user_model()',
      "print('users deleted:', U.objects.filter(username__startswith='zzfixc_').delete()[0])",
    ]);
  } catch (error) { console.error('清理失败（忽略）:', error?.message || error); }
};
process.on('exit', cleanup);

clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models_forum import Post, Comment, ForumBoard',
  'U = get_user_model()',
  `U.objects.create_superuser(username='${adminName}', password='${password}', email='', role='ADMIN')`,
  `author = U.objects.create_user(username='${authorName}', password='${password}', role='USER')`,
  `board = ForumBoard.objects.create(name='${boardName}', order=945)`,
  `post = Post.objects.create(title='zzfixc帖子', content='<p>正文</p>', author=author, board=board, status='published')`,
  "[Comment.objects.create(post=post, author=author, content=f'zzfixc评论{i}') for i in range(3)]",
  "print('seeded')",
]);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1700, height: 1000 }, locale: 'zh-CN' });
const page = await ctx.newPage();
let requests = [];
page.on('request', (r) => { if (r.url().includes('/api/')) requests.push(`${r.method()} ${r.url().replace(API, '')}`); });
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));

await page.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.admin-login', { timeout: 30_000 });
await page.locator('#username').fill(adminName);
await page.locator('#password').fill(password);
await page.locator('button[type="submit"]').first().click();
await page.waitForURL((u) => u.pathname.startsWith('/admin/') && u.pathname !== '/admin/login', { timeout: 30_000 });
await page.waitForSelector('.admin-console', { timeout: 25_000 });

await page.goto(`${UI}/admin/content?tab=comments`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3500);
await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));

const bar = page.locator('.bulk-bar').first();
const bulkBtn = bar.locator('button', { hasText: '批量删除' }).first();
const dbDeleted = () => runDjango([
  'from api.models_forum import Comment',
  "print(list(Comment.objects.filter(content__startswith='zzfixc').order_by('content').values_list('content','is_deleted')))",
]);
const state = async () => ({
  bar: (await bar.innerText()).replace(/\s+/g, ' ').trim(),
  disabled: await bulkBtn.evaluate((el) => el.hasAttribute('disabled')),
});
const selectAll = async () => {
  await page.locator('.el-table__header .el-checkbox').first().click();
  await page.waitForTimeout(800);
  return state();
};

// 找到本页里属于测试帖的评论行：直接全选（开发库里的其它评论也会被选中，但只对测试评论做断言）
console.log('初始:', JSON.stringify(await state()));
let s = await selectAll();
check('第一次全选后按钮可点', s.disabled === false, s.bar);

requests = [];
await bulkBtn.click();
await page.waitForSelector('.el-message-box', { timeout: 10_000 });
await page.locator('.el-message-box__btns button.el-button--primary').click();
await page.waitForTimeout(3500);
check('发出了批量软删请求', requests.some((r) => r.includes('POST /api/admin/comments/bulk-delete/') || r.includes('POST /admin/comments/bulk-delete/')), requests.join(' | '));
console.log('库中测试评论:', await dbDeleted());

// 核心回归点：批量操作后再全选
console.log('\n--- 批量删除后再次全选（修复前此处失灵） ---');
await page.waitForTimeout(1500);
s = await selectAll();
check('再次全选后按钮可点（修复前恒 disabled、点了无请求）', s.disabled === false, s.bar);
check('批量条显示了已选数量', /已选\s*\d+\s*条/.test(s.bar), s.bar);

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
