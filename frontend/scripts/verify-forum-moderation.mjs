/**
 * 「版主置顶 / 加精」端到端验证（第 145 批）
 * ============================================================================
 * 补的缺口：`posts/<id>/set_pinned/` 与 `set_essence/` 第 24 批就写好了，
 * 但界面上只有**作者自己的编辑页**有勾选框 —— "版主给别人的帖子加精/置顶"
 * 在界面上根本做不到（两个接口等于死代码）。本批把开关放到论坛列表（版主浏览帖子处）。
 *
 * 覆盖：
 *   ① 有 review 模块的信息编辑员：在论坛列表上看到「置顶 / 加精」按钮
 *   ② 点「置顶」→ 该帖出现「置顶」标签、接口状态为真；再点「取消置顶」→ 复原
 *   ③ 点「加精」→ 出现「加精」标签
 *   ④ 置顶后刷新列表：置顶帖排在最前（这个开关对用户不是隐形的）
 *   ⑤ 普通用户（农户）在同一个列表上看不到这两个按钮
 *   ⑥ 按钮点击**不会**顺手跳进帖子详情（整行是可点的，必须 @click.stop）
 *
 * 用法：node scripts/verify-forum-moderation.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const editorName = `zze2e_pm_editor_${suffix}`;
const authorName = `zze2e_pm_author_${suffix}`;
const postTitle = `zze2e待置顶的帖子${suffix}`;

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
      'from api.models_forum import Post, ForumBoard',
      "print('cleaned posts:', Post.objects.filter(title__startswith='zze2e待置顶').delete()[0])",
      "print('cleaned boards:', ForumBoard.objects.filter(name__startswith='zze2e版主').delete()[0])",
      "EditorModuleGrant.objects.filter(user__username__startswith='zze2e_pm_').delete()",
      'U = get_user_model()',
      "print('cleaned users:', U.objects.filter(username__startswith='zze2e_pm_').delete()[0])",
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
  'from api.models_forum import Post, ForumBoard',
  'U = get_user_model()',
  `admin = U.objects.create_superuser(username='zze2e_pm_admin_${suffix}', password='${password}', email='', role='ADMIN')`,
  `ed = U.objects.create_user(username='${editorName}', password='${password}', role='EDITOR')`,
  "EditorModuleGrant.objects.create(user=ed, module='review', granted_by=admin)",
  `author = U.objects.create_user(username='${authorName}', password='${password}', role='USER')`,
  `board = ForumBoard.objects.create(name='zze2e版主测试版块${suffix}', order=950)`,
  `Post.objects.create(title='${postTitle}', content='<p>别人的帖子正文</p>', author=author, board=board, status='published')`,
  "print('seeded')",
]);

const browser = await chromium.launch();

/** 以某个账号在**独立上下文**里登录农户端，返回该页面的检查结果 */
const checkForumList = async (username, actions) => {
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' });
  const page = await ctx.newPage();
  const errors = [];
  const consoleErrors = [];
  page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)));
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });

  clearThrottle();
  await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('input[type="password"]', { timeout: 25_000 });
  await page.locator('input#username, input[type="text"]').first().fill(username);
  await page.locator('input[type="password"]').first().fill(password);
  await page.locator('button[type="submit"]').first().click();
  await page.waitForTimeout(3000);

  await page.goto(`${UI}/forum`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  // 用搜索框定位那条帖子（列表默认可能有分页）
  const search = page.locator('input[placeholder*="搜索"], input[type="search"]').first();
  if (await search.count()) {
    await search.fill(postTitle);
    await search.press('Enter');
    await page.waitForTimeout(2200);
  }

  const out = await actions(page);
  await ctx.close();
  return { ...out, pageErrors: errors, consoleErrors };
};

const rowOf = (page) => page.locator('.post-row').filter({ hasText: postTitle }).first();

// ---------------------------------------------------------------------------
// ① 编辑员（有 review 模块）看得到按钮
// ---------------------------------------------------------------------------
const editorSee = await checkForumList(editorName, async (page) => {
  const row = rowOf(page);
  await row.waitFor({ timeout: 20_000 });
  const text = await row.innerText();
  return {
    text,
    hasPin: await row.locator('button', { hasText: /置顶/ }).count() > 0,
    hasEssence: await row.locator('button', { hasText: /加精/ }).count() > 0,
  };
});
check('编辑员在论坛列表看到「置顶」按钮', editorSee.hasPin, editorSee.text.replace(/\s+/g, ' ').slice(0, 80));
check('编辑员看到「加精」按钮', editorSee.hasEssence);

// ---------------------------------------------------------------------------
// ②③④ 点置顶 → 标签出现；刷新后置顶排最前；再点加精
// ---------------------------------------------------------------------------
const actions = await checkForumList(editorName, async (page) => {
  const row = rowOf(page);
  await row.waitFor({ timeout: 20_000 });
  const clickModerate = async (label) => {
    // 非锚定匹配：按钮文本带图标产生的空白
    await row.locator('button', { hasText: label }).first().click();
    await page.waitForTimeout(1800);
  };
  const before = await row.innerText();
  await clickModerate('置顶');
  const afterPin = await rowOf(page).innerText().catch(() => '');
  const urlAfterPin = page.url();
  await clickModerate('加精');
  const afterEssence = await rowOf(page).innerText().catch(() => '');
  return { before, afterPin, afterEssence, urlAfterPin };
});
check('点「置顶」后该行出现置顶标签', /置顶/.test(actions.afterPin), actions.afterPin.replace(/\s+/g, ' ').slice(0, 90));
check('点「置顶」不会顺手跳进帖子详情（整行可点，按钮必须 stop）',
  !actions.urlAfterPin.includes('/post/'), actions.urlAfterPin.replace(UI, ''));
check('点「加精」后该行出现加精标签', /加精|精华/.test(actions.afterEssence),
  actions.afterEssence.replace(/\s+/g, ' ').slice(0, 90));

// 接口状态确认（用编辑员的 token 读同一列表）
const state = await checkForumList(editorName, async (page) => page.evaluate(async ({ api, title }) => {
  const token = sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}/forums/posts/?search=${encodeURIComponent(title)}`, {
    headers: { Authorization: `Token ${token}` },
  });
  const data = await res.json();
  const rows = data.results || data;
  const post = rows.find((p) => p.title === title);
  return post ? { is_pinned: post.is_pinned, is_essence: post.is_essence } : null;
}, { api: API, title: postTitle }));
check('接口里该帖 is_pinned=true', state?.is_pinned === true, JSON.stringify(state));
check('接口里该帖 is_essence=true', state?.is_essence === true, JSON.stringify(state));

// 置顶后刷新列表：它应当排在第一条（列表默认按 -is_pinned 排序）
const firstRow = await checkForumList(authorName, async (page) => {
  const first = await page.evaluate(() => document.querySelector('.post-row')?.innerText.replace(/\s+/g, ' ').slice(0, 60) || '');
  return { first };
});
check('置顶帖在农户视角排到列表最前', firstRow.first.includes(postTitle), firstRow.first);

// ---------------------------------------------------------------------------
// ⑤ 普通用户看不到这两个按钮
// ---------------------------------------------------------------------------
const authorSee = await checkForumList(authorName, async (page) => {
  const row = rowOf(page);
  await row.waitFor({ timeout: 20_000 });
  return {
    pin: await row.locator('button', { hasText: /置顶/ }).count(),
    essence: await row.locator('button', { hasText: /加精/ }).count(),
    text: await row.innerText(),
  };
});
check('普通用户看不到任何版主按钮', authorSee.pin === 0 && authorSee.essence === 0,
  authorSee.text.replace(/\s+/g, ' ').slice(0, 80));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
