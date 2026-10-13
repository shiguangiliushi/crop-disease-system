/**
 * 编辑页「开发信息」面板：默认不显示 + 手动开关可用（第 188 批回归）
 * ============================================================================
 * 用户反馈：编辑帖子页顶部老挂着一条「▶ 开发信息（仅开发模式显示，点开查看）」。
 * 原因是判定用了 `import.meta.env.DEV`，而本项目日常就用 `npm run dev` 跑 —— 于是它一直在。
 * 现在改成显式开关（`@/utils/debugFlags`），默认关闭。
 *
 * 覆盖：
 *   ① 默认进编辑页：**没有**开发信息面板；
 *   ② localStorage 打开开关（dsh_debug_panel=1）后：面板出现且能点开；
 *   ③ 去掉开关再刷新：面板消失（开关真的可控，不是单向的）。
 *
 * 用法：node scripts/verify-debug-panel-off.mjs
 * 自己造数据自己清（zzdbg_ 前缀）。
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzDbg!2026pw';
const userName = `zzdbg_user_${suffix}`;
const boardName = `zzdbg版块${suffix}`;
const title = `zzdbg草稿-${suffix}`;

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
      "print('posts deleted:', Post.objects.filter(title__startswith='zzdbg').delete()[0])",
      "print('boards deleted:', ForumBoard.objects.filter(name__startswith='zzdbg').delete()[0])",
      'U = get_user_model()',
      "print('users deleted:', U.objects.filter(username__startswith='zzdbg_').delete()[0])",
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
  `board = ForumBoard.objects.create(name='${boardName}', order=947)`,
  `p = Post.objects.create(title='${title}', content='<p>草稿正文</p>', author=user, board=board, status='draft')`,
  "print('post id:', p.id)",
]);
const postId = Number(String(runDjango([
  'from api.models_forum import Post',
  `print(Post.objects.get(title='${title}').id)`,
])).trim().split('\n').pop());
console.log('草稿 id =', postId);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)));
const consoleErrors = [];
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });

await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('input[type="password"]', { timeout: 30_000 });
await page.locator('input#username, input[type="text"]').first().fill(userName);
await page.locator('input[type="password"]').first().fill(password);
await page.locator('button[type="submit"]').first().click();
await page.waitForTimeout(3000);

const gotoEdit = async () => {
  await page.goto(`${UI}/forum/post/${postId}/edit`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('textarea, .ql-editor', { timeout: 25_000 });
  await page.waitForTimeout(1800);
};
const panelCount = () => page.locator('.debug-info').count();
const hasSummaryText = async () => (await page.locator('summary', { hasText: '开发信息' }).count()) > 0;

// ① 默认：不显示
await gotoEdit();
check('① 默认进编辑页，页面上没有开发信息面板', (await panelCount()) === 0);
check('① 也没有"开发信息"这行字', !(await hasSummaryText()));
// 注意：页面第一个 el-select（版块）内部也有 input，必须按表单项定位「标题」
const titleValue = await page.locator('.el-form-item', { hasText: '标题' })
  .locator('input[type="text"]').first().inputValue();
check('① 编辑表单本身正常（标题框有内容）', titleValue.includes('zzdbg'), titleValue);

// ② 打开开关后：显示
await page.evaluate(() => localStorage.setItem('dsh_debug_panel', '1'));
await gotoEdit();
check('② localStorage 打开开关后，面板出现', (await panelCount()) === 1);
check('② 面板里有"开发信息"这行字', await hasSummaryText());
// <details> 默认是折叠的 —— 要点开 summary 才看得到里面的内容（这正是它的设计）
await page.locator('.debug-info summary').first().click();
await page.waitForTimeout(500);
const detailText = (await page.locator('.debug-info').innerText().catch(() => '')).replace(/\s+/g, ' ').trim();
check('② 点开后能看到帖子 ID 等信息', detailText.includes(String(postId)), detailText.slice(0, 70));

// ③ 关掉开关后：恢复隐藏（开关是双向的）
await page.evaluate(() => localStorage.removeItem('dsh_debug_panel'));
await gotoEdit();
check('③ 去掉开关后，面板又消失', (await panelCount()) === 0);

check('全程无 JS 报错', errors.length === 0, errors.slice(0, 2).join(' | '));
check('全程无 console.error', consoleErrors.length === 0, consoleErrors.slice(0, 2).join(' | '));

await page.screenshot({ path: 'dsh-shots/edit-post-no-debug.png', clip: { x: 0, y: 0, width: 1440, height: 900 } });
await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
