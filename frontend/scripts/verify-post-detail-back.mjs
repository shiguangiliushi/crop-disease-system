/**
 * 帖子详情页「返回列表」的落点（第 188 批回归）
 * ============================================================================
 * 用户反馈的路径：个人资料 → 草稿/帖子 → 编辑帖子 → 点「更新帖子」→ 详情页
 *                → 点「返回列表」→ **又回到了编辑帖子**。
 *
 * 原因：详情页的「返回列表」原来走 `goBackOr()` → `router.back()`，
 *      而历史里的上一页正是保存成功后跳过来的编辑页 —— 于是"返回列表"变成了
 *      "返回编辑器"，用户看着像页面卡住/按钮坏了。
 *
 * 现在的口径：按钮写「返回列表」就**确定性地去列表** —— 帖子属于哪个版块回哪个版块，
 * 没有版块信息时回落论坛首页。从分享链接直接打开时同样可用（不再依赖历史栈）。
 *
 * 用法：node scripts/verify-post-detail-back.mjs
 * 自己造数据自己清（zznav_ 前缀），不碰任何真实用户的帖子。
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzNav!2026pw';
const userName = `zznav_user_${suffix}`;
const boardName = `zznav版块${suffix}`;
const title = `zznav草稿-${suffix}`;

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
      "print('posts deleted:', Post.objects.filter(title__startswith='zznav').delete()[0])",
      "print('boards deleted:', ForumBoard.objects.filter(name__startswith='zznav').delete()[0])",
      'U = get_user_model()',
      "print('users deleted:', U.objects.filter(username__startswith='zznav_').delete()[0])",
    ]);
  } catch (error) { console.error('清理失败（忽略）:', error?.message || error); }
};
process.on('exit', cleanup);

clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models_forum import Post, ForumBoard',
  'U = get_user_model()',
  `user = U.objects.create_user(username='${userName}', password='${password}', role='USER')`,
  `board = ForumBoard.objects.create(name='${boardName}', order=946)`,
  `p = Post.objects.create(title='${title}', content='<p>草稿正文</p>', author=user, board=board, status='draft')`,
  "print('post id:', p.id)",
]);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' });
const page = await ctx.newPage();
const navLog = [];
page.on('framenavigated', (f) => { if (f === page.mainFrame()) navLog.push(new URL(f.url()).pathname + new URL(f.url()).search); });
const errors = [];
page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)));

await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('input[type="password"]', { timeout: 30_000 });
await page.locator('input#username, input[type="text"]').first().fill(userName);
await page.locator('input[type="password"]').first().fill(password);
await page.locator('button[type="submit"]').first().click();
await page.waitForTimeout(3000);

// 拿到草稿 id（断言用）
const raw = runDjango([
  'from api.models_forum import Post',
  `print(Post.objects.get(title='${title}').id)`,
]);
const postId = Number(raw.trim().split('\n').pop());
console.log('草稿 id =', postId);

// ① 从「我的草稿」进编辑页（与"从个人资料点编辑"同构：列表 → 编辑）
await page.goto(`${UI}/forum/drafts`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2500);
await page.locator('.draft-item', { hasText: title }).locator('button', { hasText: '继续编辑' }).first().click();
await page.waitForURL((u) => u.pathname.includes('/edit'), { timeout: 15_000 });
await page.waitForTimeout(2500);
check('① 进了编辑页', page.url().includes(`/forum/post/${postId}/edit`), page.url());

// ② 点「更新帖子」（= 发布）
await page.locator('button', { hasText: '更新帖子' }).first().click();
await page.waitForTimeout(4000);
const dbStatus = String(runDjango([
  'from api.models_forum import Post',
  `print(Post.objects.get(id=${postId}).status)`,
]).trim().split('\n').pop());
check('② 保存成功（帖子已发布）', dbStatus === 'published', `库中状态=${dbStatus}`);
check('② 保存后落在详情页', new URL(page.url()).pathname === `/forum/post/${postId}`, page.url());

// ③ 点「返回列表」—— 修复前会回到编辑页
await page.locator('.back-btn').first().click();
await page.waitForTimeout(3000);
const landed = new URL(page.url());
check('③「返回列表」不再回到编辑页', !landed.pathname.includes('/edit'), landed.pathname);
check('③ 落在列表页（帖子所属版块 / 论坛首页）',
  /^\/forum(\/board\/\d+)?$/.test(landed.pathname), landed.pathname);
check('③ 列表页有内容（不是白页）',
  await page.locator('.page-hero, .forum-page, .board-page, h1').first().isVisible().catch(() => false));
check('全程无 JS 报错', errors.length === 0, errors.slice(0, 2).join(' | '));

await page.screenshot({ path: 'dsh-shots/post-detail-back.png', clip: { x: 0, y: 0, width: 1440, height: 900 } });
await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
console.log('导航轨迹:', navLog.join(' → '));
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
