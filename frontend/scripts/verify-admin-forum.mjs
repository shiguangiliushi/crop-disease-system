/**
 * 「控制台论坛管理」端到端验证（第 147 批）
 * ============================================================================
 * 这一批把论坛帖子搬进控制台：此前控制台只能管**待审核**的帖子（内容审核页），
 * 已发布的帖子里有广告、有吵架、也有该置顶加精的好帖 —— 但控制台看不到它们，
 * 只能回农户端论坛翻。
 *
 * ⚠️ 第 183 批把这几个入口合并了，本脚本**在 188 批按新结构改过**，否则它是红的：
 *   · 侧栏的「内容审核 / 论坛管理 / 评论管理」三项已并成一项**「内容管理」**
 *     （`/admin/content?tab=posts|comments|reports`）；
 *   · 页面里不再有 `.admin-hero h1`，论坛管理的标题是页面内第二个区块的 `h2`；
 *   · 帖子表格与**审核队列的表格不是同一张**，选择器必须限定在论坛管理区块内
 *     （区块里给了 `data-testid="forum-table"`，比按文案过滤稳）。
 *   旧地址 `/admin/forum` 仍会重定向到这一页，所以老书签/老链接照样能用。
 *
 * 覆盖：
 *   ① 侧栏出现「内容管理」，页面能打开，论坛管理区块在
 *   ② 列表默认把各状态的帖子都列出来（版主视角，这是管理页的前提）
 *   ③ 按状态/版块/关键字筛选生效，且**进 URL**（刷新/分享不丢）
 *   ④ 行内：待审帖「通过」→ 变成已发布；「驳回」要填原因
 *   ⑤ 行内：置顶 / 加精生效（复用第 145 批的接口）
 *   ⑥ 行内删除 → 该帖从列表消失（软删除）
 *   ⑦ 批量：选中多条 → 批量通过（只处理待审的）/ 批量删除（**仅全权管理员**）
 *   ⑧ 有 review 模块的编辑员：能进页面、能审核、**看不到批量删除按钮**（后端 403）
 *
 * 用法：node scripts/verify-admin-forum.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const superName = `zze2e_fa_super_${suffix}`;
const editorName = `zze2e_fa_editor_${suffix}`;
const authorName = `zze2e_fa_author_${suffix}`;
const boardName = `zze2e论坛管理版块${suffix}`;

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
      "print('cleaned posts:', Post.objects.filter(title__startswith='zz论坛管理').delete()[0])",
      "print('cleaned boards:', ForumBoard.objects.filter(name__startswith='zze2e论坛管理').delete()[0])",
      "EditorModuleGrant.objects.filter(user__username__startswith='zze2e_fa_').delete()",
      'U = get_user_model()',
      "print('cleaned users:', U.objects.filter(username__startswith='zze2e_fa_').delete()[0])",
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
  `admin = U.objects.create_superuser(username='${superName}', password='${password}', email='', role='ADMIN')`,
  `ed = U.objects.create_user(username='${editorName}', password='${password}', role='EDITOR')`,
  "EditorModuleGrant.objects.create(user=ed, module='review', granted_by=admin)",
  `author = U.objects.create_user(username='${authorName}', password='${password}', role='USER')`,
  `board = ForumBoard.objects.create(name='${boardName}', order=970)`,
  // 各状态各造一条，验证"管理页看得到全部状态"
  "[Post.objects.create(title=f'zz论坛管理已发布{i}', content='<p>正文</p>', author=author, board=board, status='published') for i in range(2)]",
  "[Post.objects.create(title=f'zz论坛管理待审{i}', content='<p>正文</p>', author=author, board=board, status='pending') for i in range(3)]",
  "Post.objects.create(title='zz论坛管理草稿', content='<p>正文</p>', author=author, board=board, status='draft')",
  "Post.objects.create(title='zz论坛管理已隐藏', content='<p>正文</p>', author=author, board=board, status='hidden')",
  "print('seeded')",
]);

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1700, height: 1050 }, locale: 'zh-CN' })).newPage();
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

/**
 * 论坛管理所在的区块（`data-testid` 由 PostPanel 提供）
 *
 * 为什么不按文案过滤：这一页里「内容审核」区块的文案也含"论坛"二字，而
 * 「审核队列」区块里还有一排独立的复选框与按钮 —— 不限定范围就会选错元素
 * （第 188 批改脚本时正是因为这一点才加了 testid）。
 */
const forumBlock = () => page.locator('.hub-block:has([data-testid="forum-table"])');
/** 论坛管理这张表里的行（页面里还有审核队列的列表，必须限定） */
const forumRows = () => forumBlock().locator('.el-table__row');
const rowTitles = () => forumRows().allInnerTexts()
  .then((list) => list.map((t) => t.replace(/\s+/g, ' ').trim()));
const rowOf = (title) => forumRows().filter({ hasText: title }).first();

await loginAs(page, superName);

// ---------------------------------------------------------------------------
// ① 侧栏与页面
// ---------------------------------------------------------------------------
const nav = await page.evaluate(
  () => [...document.querySelectorAll('.admin-nav-item')].map((el) => el.innerText.trim()).join(' | '),
);
check('侧栏出现「内容管理」（第 183 批合并后的入口）', nav.includes('内容管理'), nav);

await page.goto(`${UI}/admin/forum`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('[data-testid="forum-table"] .el-table__row', { timeout: 25_000 });
await page.waitForTimeout(1800);
check('老地址 /admin/forum 会落到「内容管理 · 帖子」页',
  page.url().includes('/admin/content') && page.url().includes('tab=posts'), page.url().replace(UI, ''));
check('页面里有「论坛管理」区块',
  await page.locator('.hub-block h2', { hasText: '论坛管理' }).first().isVisible());

// 用版块筛选，只看这个测试版块的帖子
await page.goto(`${UI}/admin/forum`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
// ⚠️ 按**下标**定位筛选下拉：选中之后 placeholder 文案（"版块"/"状态"）就没了，
//    再按 hasText 找必然失配（第一版就是这么超时的）。顺序：版块 / 状态 / 标记。
const filterSelects = page.locator('.filter-bar .el-select');
const boardSelect = filterSelects.nth(0);
await boardSelect.click();
await page.waitForTimeout(500);
await page.locator('.el-select-dropdown__item:visible', { hasText: boardName }).first().click();
await page.waitForTimeout(2000);

// ---------------------------------------------------------------------------
// ② 各状态都看得到
// ---------------------------------------------------------------------------
const titles = (await rowTitles()).join(' | ');
check('看得到已发布的帖子', titles.includes('zz论坛管理已发布'));
check('看得到待审核的帖子', titles.includes('zz论坛管理待审'));
check('看得到草稿', titles.includes('zz论坛管理草稿'));
check('看得到已隐藏的帖子', titles.includes('zz论坛管理已隐藏'));

// ---------------------------------------------------------------------------
// ③ 状态筛选 + 进 URL
// ---------------------------------------------------------------------------
const statusSelect = filterSelects.nth(1);
await statusSelect.click();
await page.waitForTimeout(500);
await page.locator('.el-select-dropdown__item:visible', { hasText: '待审核' }).first().click();
await page.waitForTimeout(2000);
const pendingTitles = (await rowTitles()).join(' | ');
check('按「待审核」筛选后只剩待审帖',
  pendingTitles.includes('zz论坛管理待审') && !pendingTitles.includes('zz论坛管理已发布'),
  pendingTitles.slice(0, 90));
check('筛选进了 URL（刷新/分享不丢）', page.url().includes('status=pending'), page.url().split('?')[1] || '');

// ---------------------------------------------------------------------------
// ④ 行内审核：通过 + 驳回要填原因
// ---------------------------------------------------------------------------
await rowOf('zz论坛管理待审0').locator('button', { hasText: '通过' }).first().click();
await page.waitForTimeout(2200);
const afterApprove = (await rowTitles()).join(' | ');
check('「通过」后该帖离开待审列表', !afterApprove.includes('zz论坛管理待审0'), afterApprove.slice(0, 80));

await rowOf('zz论坛管理待审1').locator('button', { hasText: '驳回' }).first().click();
await page.waitForSelector('.el-dialog:visible', { timeout: 15_000 });
check('驳回弹窗里「确认驳回」在没填原因时禁用',
  await page.locator('.el-dialog:visible .el-button--danger').first().isDisabled());
await page.locator('.el-dialog:visible textarea').fill('端到端测试：内容与农业无关');
await page.waitForTimeout(300);
await page.locator('.el-dialog:visible .el-button--danger').first().click();
await page.waitForTimeout(2200);
const afterReject = (await rowTitles()).join(' | ');
check('「驳回」后该帖也离开待审列表', !afterReject.includes('zz论坛管理待审1'), afterReject.slice(0, 80));

// ---------------------------------------------------------------------------
// ⑤ 置顶 / 加精
// ---------------------------------------------------------------------------
await statusSelect.click();
await page.waitForTimeout(500);
await page.locator('.el-select-dropdown__item:visible', { hasText: '已发布' }).first().click();
await page.waitForTimeout(2000);
const targetRow = rowOf('zz论坛管理已发布0');
await targetRow.locator('button', { hasText: '置顶' }).first().click();
await page.waitForTimeout(1500);
await rowOf('zz论坛管理已发布0').locator('button', { hasText: '加精' }).first().click();
await page.waitForTimeout(1500);
const marked = await rowOf('zz论坛管理已发布0').innerText();
check('置顶后出现「置顶」标签', /置顶/.test(marked), marked.replace(/\s+/g, ' ').slice(0, 90));
check('加精后出现「精华」标签', /精华/.test(marked));

// 留证（放在列表里还有内容的时刻，别等批量删完再拍 —— 那样只有一张空列表）
await page.screenshot({ path: 'dsh-shots/admin-forum.png', clip: { x: 0, y: 0, width: 1700, height: 720 } });

// ---------------------------------------------------------------------------
// ⑥ 行内删除（软删除）
// ---------------------------------------------------------------------------
await rowOf('zz论坛管理已发布1').locator('button', { hasText: '删除' }).first().click();
await page.waitForSelector('.el-message-box', { timeout: 10_000 });
const boxText = await page.locator('.el-message-box').innerText();
check('删除确认框说明是"从论坛移除"（软删除）', boxText.includes('评论') || boxText.includes('移除'),
  boxText.replace(/\s+/g, ' ').slice(0, 70));
await page.locator('.el-message-box__btns button.el-button--primary').click();
await page.waitForTimeout(2200);
await page.goto(page.url(), { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2200);
check('删除后该帖不再出现在列表里',
  !(await rowTitles()).join(' | ').includes('zz论坛管理已发布1'));

// ---------------------------------------------------------------------------
// ⑦ 批量：通过 + 删除
// ---------------------------------------------------------------------------
await statusSelect.click();
await page.waitForTimeout(500);
await page.locator('.el-select-dropdown__item:visible', { hasText: '待审核' }).first().click();
await page.waitForTimeout(2000);
const bulkRows = await forumRows().count();
check('还有待审帖可供批量处理', bulkRows >= 1, `${bulkRows} 条`);

await forumBlock().locator('.el-table__header .el-checkbox').first().click();
await page.waitForTimeout(500);
check('全选后批量条显示已选数量',
  (await forumBlock().locator('.bulk-bar').innerText()).includes('已选'), '');
await forumBlock().locator('.bulk-bar button', { hasText: '批量通过' }).click();
await page.waitForTimeout(2500);
check('批量通过后待审列表清空',
  (await forumRows().count()) === 0,
  `${await forumRows().count()} 条`);

await boardSelect.click();
await page.waitForTimeout(500);
await page.locator('.el-select-dropdown__item:visible', { hasText: boardName }).first().click();
await page.waitForTimeout(500);
await statusSelect.click();
await page.waitForTimeout(500);
await page.locator('.el-select-dropdown__item:visible', { hasText: '全部状态' }).first().click();
await page.waitForTimeout(2000);
await forumBlock().locator('.el-table__header .el-checkbox').first().click();
await page.waitForTimeout(500);
await forumBlock().locator('.bulk-bar button', { hasText: '批量删除' }).click();
await page.waitForSelector('.el-message-box', { timeout: 10_000 });
await page.locator('.el-message-box__btns button.el-button--primary').click();
await page.waitForTimeout(2500);
check('批量删除后列表清空',
  (await forumRows().count()) === 0,
  `${await forumRows().count()} 条`);

// ---------------------------------------------------------------------------
// ⑧ 编辑员：能进能审，但看不到批量删除
// ---------------------------------------------------------------------------
clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models_forum import Post, ForumBoard',
  'U = get_user_model()',
  `au = U.objects.get(username='${authorName}')`,
  `b = ForumBoard.objects.get(name='${boardName}')`,
  "Post.objects.create(title='zz论坛管理编辑员待审', content='<p>x</p>', author=au, board=b, status='pending')",
  "print('ok')",
]);

const editorCtx = await browser.newContext({ viewport: { width: 1700, height: 1050 }, locale: 'zh-CN' });
const editorPage = await editorCtx.newPage();
await loginAs(editorPage, editorName);
const editorNav = await editorPage.evaluate(
  () => [...document.querySelectorAll('.admin-nav-item')].map((el) => el.innerText.trim()).join(' | '),
);
check('编辑员侧栏也能看到「内容管理」（同为 review 模块）', editorNav.includes('内容管理'), editorNav);
await editorPage.goto(`${UI}/admin/forum`, { waitUntil: 'domcontentloaded' });
await editorPage.waitForSelector('[data-testid="forum-table"] .el-table__row', { timeout: 25_000 });
await editorPage.waitForTimeout(1800);
const editorBulkText = await editorPage
  .locator('.hub-block:has([data-testid="forum-table"]) .bulk-bar').innerText();
check('编辑员看不到「批量删除」（仅全权管理员）', !editorBulkText.includes('批量删除'),
  editorBulkText.replace(/\s+/g, ' ').slice(0, 60));
check('编辑员仍能看到「批量通过」（review 模块可审核）', editorBulkText.includes('批量通过'),
  editorBulkText.replace(/\s+/g, ' ').slice(0, 60));

const editorApi = await editorPage.evaluate(async ({ api, title }) => {
  const token = sessionStorage.getItem('auth_token');
  const list = await (await fetch(`${api}/forums/posts/?search=${encodeURIComponent(title)}`, {
    headers: { Authorization: `Token ${token}` },
  })).json();
  const rows = list.results || list;
  const post = rows.find((p) => p.title === title);
  const res = await fetch(`${api}/forums/posts/bulk-delete/`, {
    method: 'POST',
    headers: { Authorization: `Token ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids: [post?.id] }),
  });
  return res.status;
}, { api: API, title: 'zz论坛管理编辑员待审' });
check('编辑员直连批量删除接口 → 403', editorApi === 403, `HTTP ${editorApi}`);

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
