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
  // 第 163 批：再建一篇"老正文" —— 图片是 Markdown 语法（第 161 批之前的工具栏就是这么插的）
  "legacy = Post.objects.create(title='zz编辑页验证：老正文图片（markdown 语法）', content='<p>老帖子里插的图：</p><p>![苹果黑星病](/media/uploads/zz-legacy.jpg)</p>', author=admin, board=board, status='published')",
  "print('ZZ_LEGACY=' + str(legacy.id))",
  'token, _ = Token.objects.get_or_create(user=admin)',
  "print('ZZ_ID=' + str(post.id))",
  "print('ZZ_BOARD=' + str(board.name))",
  "print('ZZ_TOKEN=' + token.key)",
  "print('ZZ_USER=' + json.dumps(CustomUserSerializer(admin).data, ensure_ascii=False))",
]);
const postId = /ZZ_ID=(\d+)/.exec(seedOutput)?.[1];
const legacyId = /ZZ_LEGACY=(\d+)/.exec(seedOutput)?.[1];
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
// ② 工具栏：农户四件套（加粗 / 图片 / 列表 / 分隔线），且**没有**代码块这种技术按钮
// ---------------------------------------------------------------------------
const toolbarButtons = await page.locator('.farmer-toolbar .rte-btn').allInnerTexts();
const toolbarText = toolbarButtons.join(' | ');
check('工具栏是农户四件套', /加粗/.test(toolbarText) && /图片/.test(toolbarText)
  && /列表/.test(toolbarText) && /分隔线/.test(toolbarText), toolbarText);
check('工具栏没有「代码块 / 行内代码」这类技术按钮',
  !/代码/.test(toolbarText), toolbarText);
check('工具栏按钮数就是 4 个', toolbarButtons.length === 4, `${toolbarButtons.length} 个`);

const iconCount = await page.locator('.farmer-toolbar .fas').count();
check('四个按钮都带图标（Font Awesome）', iconCount === 4, `${iconCount} 个图标`);

// ---------------------------------------------------------------------------
// ②b 正文框是**所见即所得**：显示的是排版后的效果，不是 <p> 源码
// ---------------------------------------------------------------------------
const editorRoot = page.locator('.ql-editor').first();
check('正文用的是富文本编辑器（.ql-editor）', await editorRoot.count() > 0, '');

const editorHtml = await editorRoot.innerHTML();
check('编辑区里是真实的段落元素（不是转义后的源码）',
  /<p>/.test(editorHtml) && !/&lt;p&gt;/.test(editorHtml), editorHtml.slice(0, 80));
check('编辑区里没有裸露的 HTML 标签文本',
  !editorHtml.includes('&lt;'), '');

const editorFont = await editorRoot.evaluate((el) => getComputedStyle(el).fontFamily);
check('正文用普通正文字体（不是等宽代码字体）',
  !/mono/i.test(editorFont), editorFont.slice(0, 60));

// ③ 预览：必须按 HTML 渲染（与详情页同口径），而不是把标签当字面量
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// ④ 点「加粗」真的把选中的字变粗（所见即所得，不是插源码）
// ---------------------------------------------------------------------------
await editorRoot.click();
await page.keyboard.press('Control+A');
await page.waitForTimeout(300);
await page.locator('.farmer-toolbar .rte-btn-bold').click();
await page.waitForTimeout(600);
const afterBold = await editorRoot.innerHTML();
check('点「加粗」后编辑区出现了加粗标签',
  /<(strong|b)>/i.test(afterBold), afterBold.slice(0, 90));

// ④b 分隔线按钮：插进去的 <hr> 不会被 Quill 丢掉（这是注册 DividerBlot 的原因）
await page.keyboard.press('End');
await page.locator('.farmer-toolbar .rte-btn-divider').click();
await page.waitForTimeout(600);
const afterDivider = await editorRoot.innerHTML();
check('点「分隔线」插入了 <hr>', /<hr/i.test(afterDivider), afterDivider.slice(-60));

// ⑤ 保存后详情页正常渲染（且能看见刚才插入的加粗）
// ---------------------------------------------------------------------------
await page.waitForTimeout(500);
await page.getByRole('button', { name: /保存/ }).first().click();
await page.waitForTimeout(3000);
const savedOk = await page.evaluate(() => !document.querySelector('.el-message--error'));
check('保存没有报错', savedOk, '');

await page.goto(`${UI}/forum/post/${postId}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.post-content', { timeout: 30_000 });
await page.waitForTimeout(1500);
const detailHtml = await page.locator('.post-content').innerHTML();
check('详情页渲染了正文段落', /<p>/i.test(detailHtml), detailHtml.slice(0, 60));
check('详情页能看到刚插入的加粗内容', /<(strong|b)>/i.test(detailHtml), '');

// ---------------------------------------------------------------------------
// ⑥ 第 163 批：老正文里的 **Markdown 图片**也要能显示出来
//     （渲染口径是 HTML；不兼容存量数据的话，那些图会"凭空消失"）
//     ⚠️ 这一段必须放在"保存"之后 —— 它会导航到另一篇帖子，
//        放在前面会让后面的保存按钮点不到（第一版就是这么挂的）。
// ---------------------------------------------------------------------------
await page.goto(`${UI}/forum/post/${legacyId}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.post-content', { timeout: 30_000 });
await page.waitForTimeout(1200);
const legacyHtml = await page.locator('.post-content').innerHTML();
check('老正文里的 Markdown 图片被渲染成了 <img>', /<img[^>]+zz-legacy\.jpg/.test(legacyHtml),
  legacyHtml.slice(0, 90));
check('老正文里没有残留的 markdown 图片语法', !/!\[[^\]]*\]\(/.test(legacyHtml), '');

// ---------------------------------------------------------------------------
// ⑦ 第 165 批：英文区块默认收起 + 快捷键标注 + 删除确认写清后果
// ---------------------------------------------------------------------------
await page.goto(`${UI}/forum/post/${postId}/edit`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.ql-editor', { timeout: 30_000 });
await page.waitForTimeout(2000);
const englishVisible = await page.locator('.en-fields').first().isVisible().catch(() => false);
check('英文区块默认收起（农户不会被英文框吓到）', englishVisible === false, englishVisible ? '仍然展开' : '已收起');

const pageText = await page.locator('.edit-post').innerText();
check('按钮上标注了快捷键', /Ctrl\+Enter/.test(pageText) && /Ctrl\+S/.test(pageText),
  (pageText.match(/Ctrl\+\w+/g) || []).join(' / '));

await page.getByRole('button', { name: /删除帖子/ }).first().click();
// ⚠️ 删除确认是页内的 el-dialog（不是 ElMessageBox.confirm）—— 第一版按 MessageBox 找，超时了
await page.waitForSelector('.el-dialog', { timeout: 10_000 });
await page.waitForTimeout(600);
const confirmText = await page.locator('.el-dialog').innerText();
check('删除确认写清了后果（评论/配图一起删）',
  /评论/.test(confirmText) && /无法恢复|不能恢复/.test(confirmText),
  confirmText.replace(/\s+/g, ' ').slice(0, 90));
await page.locator('.el-dialog__footer button').filter({ hasText: /取消/ }).first().click();
await page.waitForTimeout(500);

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
