/**
 * 「编辑帖子」页完善后的验证（第 161 批）
 * ============================================================================
 * 用户截图里看出的三个问题，逐一钉住：
 *   ① 版块下拉显示成孤零零一个 `1` —— `getForumBoards` 只 import 从未调用，
 *      列表为空 → el-select 只能把原始值显示出来；
 *   ② 工具栏一排**空方块** —— `el-icon-*` 是 Element UI v2 的图标写法，
 *      Element Plus 2 没有图标字体（NewPostView 早就注释过这个坑，编辑页漏改）；
 *   ③ 预览把 **HTML 当 markdown** 渲染 —— 正文口径是 sanitizeRichText（详情页/审核页同款）。
 *
 * 另外钉住工具栏插入的是 **HTML 片段**（正文是 HTML，不是 markdown）。
 *
 * 用真实管理员账号 `admin`：通过 Django 签发 token + 注入 sessionStorage 登录，
 * 不需要 admin 的密码（做法同 scripts/capture-docs-shots.mjs）。
 *
 * 用法：node scripts/verify-edit-post.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const ADMIN = 'admin';

const results = [];
let cleaned = false;
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

// 造一篇带 HTML 正文的帖子（作者 admin）
clearThrottle();
const seedOutput = runDjango([
  'import json',
  'from django.contrib.auth import get_user_model',
  'from rest_framework.authtoken.models import Token',
  'from api.serializers import CustomUserSerializer',
  'from api.models_forum import ForumBoard, Post',
  `admin = get_user_model().objects.get(username='${ADMIN}')`,
  "board = ForumBoard.objects.order_by('order', 'id').first()",
  "Post.objects.filter(title__startswith='zz编辑页验证').delete()",
  "post = Post.objects.create(title='zz编辑页验证：高架基质栽培的几个问题', content='<p>第一段：品种与基质配比。</p><p>第二段：水肥与温湿度管理。</p>', author=admin, board=board, status='published')",
  'token, _ = Token.objects.get_or_create(user=admin)',
  "print('ZZ_ID=' + str(post.id))",
  "print('ZZ_BOARD=' + str(board.name))",
  "print('ZZ_TOKEN=' + token.key)",
  "print('ZZ_USER=' + json.dumps(CustomUserSerializer(admin).data, ensure_ascii=False))",
]);
const postId = /ZZ_ID=(\d+)/.exec(seedOutput)?.[1];
const boardName = /ZZ_BOARD=(.+)/.exec(seedOutput)?.[1]?.trim();
const token = /ZZ_TOKEN=(\S+)/.exec(seedOutput)?.[1];
const userJson = /ZZ_USER=(.+)/.exec(seedOutput)?.[1];
if (!postId || !token || !userJson) {
  console.error('❌ 造数据失败：', seedOutput);
  process.exit(1);
}

const cleanup = () => {
  if (cleaned) return;
  cleaned = true;
  clearThrottle();
  try {
    runDjango([
      'from api.models_forum import Post',
      "print('cleaned:', Post.objects.filter(title__startswith='zz编辑页验证').delete()[0])",
    ]);
  } catch (error) {
    console.error('清理失败（忽略）:', error?.message || error);
  }
};
process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 1100 }, locale: 'zh-CN' })).newPage();
const pageErrors = [];
page.on('pageerror', (error) => pageErrors.push(String(error).slice(0, 200)));

await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
await page.evaluate(([tokenValue, userValue]) => {
  window.sessionStorage.setItem('auth_token', tokenValue);
  window.sessionStorage.setItem('user', userValue);
}, [token, userJson]);

await page.goto(`${UI}/forum/post/${postId}/edit`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.edit-post', { timeout: 30_000 });
await page.waitForTimeout(2500);
await page.screenshot({ path: 'dsh-shots/edit-post.png', fullPage: false });

// ---------------------------------------------------------------------------
// ① 版块下拉：必须显示**版块名**，不能是裸数字
// ---------------------------------------------------------------------------
const selectText = (await page.locator('.edit-post .el-select').first().innerText().catch(() => '')).trim();
check('版块下拉显示了版块名（不是裸数字）',
  Boolean(selectText) && !/^\d+$/.test(selectText) && selectText.includes(boardName || selectText),
  `显示为「${selectText}」，期望「${boardName}」`);

const optionCount = await page.locator('.edit-post .el-select').first().locator('xpath=ancestor::div[1]').count();
check('版块下拉有选项可用', optionCount > 0, '');

// 展开确认选项里有版块名
await page.locator('.edit-post .el-select').first().click();
await page.waitForTimeout(800);
const optionTexts = await page.locator('.el-select-dropdown__item').allInnerTexts();
check('展开后能看到版块选项', optionTexts.length > 0, optionTexts.slice(0, 3).join(' / ').slice(0, 60));
check('选项里包含当前版块', optionTexts.some((text) => text.includes(boardName || '')), boardName || '');
await page.keyboard.press('Escape');
await page.waitForTimeout(400);

// ---------------------------------------------------------------------------
// ② 工具栏：6 个按钮，每个都有真实的 Font Awesome 图标（不再是空方块）
// ---------------------------------------------------------------------------
const toolbarIcons = await page.locator('.editor-toolbar .fas').count();
check('工具栏 6 个按钮都有图标', toolbarIcons >= 6, `${toolbarIcons} 个 .fas 图标`);
const legacyIcons = await page.locator('.editor-toolbar [class*="el-icon-"]').count();
check('工具栏里没有残留的 el-icon-*（那种会显示成空方块）', legacyIcons === 0, `${legacyIcons} 个`);

const boldHtml = await page.evaluate(() => {
  const style = getComputedStyle(document.querySelector('.editor-toolbar .fas.fa-bold'), '::before');
  return style.content;
});
check('图标字体真的渲染出了字形（不是空）',
  Boolean(boldHtml) && boldHtml !== 'none' && boldHtml !== '""', `content=${boldHtml}`);

// ---------------------------------------------------------------------------
// ③ 预览：必须按 HTML 渲染（与详情页同口径），而不是把标签当字面量
// ---------------------------------------------------------------------------
const previewHtml = await page.locator('.preview .markdown-body').first().innerHTML().catch(() => '');
check('预览把正文渲染成了 HTML 元素', /<p>/i.test(previewHtml), previewHtml.slice(0, 70));
check('预览里没有转义后的标签字面量', !/&lt;p&gt;/i.test(previewHtml), '');

// ---------------------------------------------------------------------------
// ④ 工具栏插入的是 HTML 片段
// ---------------------------------------------------------------------------
const contentBefore = await page.locator('#content').inputValue();
await page.locator('.editor-toolbar .fas.fa-bold').click();
await page.waitForTimeout(400);
const contentAfter = await page.locator('#content').inputValue();
check('点「加粗」插入的是 HTML 片段（不是 markdown 的 **粗体**）',
  contentAfter !== contentBefore && contentAfter.includes('<b>') && !contentAfter.includes('**粗体**'),
  contentAfter.slice(-30));

// ---------------------------------------------------------------------------
// ⑤ 保存后详情页正常渲染（且能看见刚才插入的加粗）
// ---------------------------------------------------------------------------
await page.getByRole('button', { name: /保存/ }).first().click();
await page.waitForTimeout(3000);
const savedOk = await page.evaluate(() => !document.querySelector('.el-message--error'));
check('保存没有报错', savedOk, '');

await page.goto(`${UI}/forum/post/${postId}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.post-content', { timeout: 30_000 });
await page.waitForTimeout(1500);
const detailHtml = await page.locator('.post-content').innerHTML();
check('详情页渲染了正文段落', /<p>/i.test(detailHtml), detailHtml.slice(0, 60));
check('详情页能看到刚插入的加粗内容', /<b>/i.test(detailHtml), '');

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
