/**
 * 信息编辑员「各自的功能」—— 前端侧栏与拦截（第 178 批，第 183 / 184 批改）
 * ============================================================================
 * 后端那一半已经由 `api.tests.RoleMatrixTests` 钉住了（拿矩阵表真请求每个接口）。
 * 这一支验**农户/编辑员看到的那一半**：控制台侧栏显示哪几项、直接输网址进不进得去、
 * **「内容管理」页里哪几个页签画给他看**、**「用户管理」合并页的两个页签**。
 *
 * 本脚本验证（四种身份各一遍）：
 *   ① **只勾「新闻管理」的编辑员**：侧栏只有 数据看板 + 新闻管理；
 *      直接输 /admin/pests 进不去（能看到"无权限"或跳走），而且**不显示**别的入口；
 *      ⚠️ 第 183 批起还要确认：侧栏**没有**「内容管理」这一项（他一个相关模块都没有）
 *   ② **只勾「病害百科」的编辑员**：侧栏只有 数据看板 + 病害百科维护
 *   ③ **只勾「论坛交流」的编辑员**（第 183 批新增）：侧栏**有**「内容管理」，
 *      页里只画「帖子」「评论」两个页签，**没有**「举报」（举报仅全权管理员，
 *      后端 `_can_handle_reports()` = `is_full_admin`，点了必然 403）
 *   ④ **全权管理员**：侧栏有全部入口（含系统健康/操作日志这些仅全权的），
 *      内容管理页三个页签齐全，且三条旧地址（/admin/review、/admin/forum、/admin/comments）
 *      都重定向到新页对应页签
 *   ⑤ **全权管理员 · 用户管理合并页**（第 184 批）：侧栏里「识别记录」不再单独占一项；
 *      `/admin/users` 是「用户」+「识别记录」两个页签、`?tab=` 双向同步、
 *      深链 `/admin/users?tab=detections` 直接落在识别记录上（且**不挂载**另一个页签，
 *      免得多打一遍接口），旧地址 `/admin/detection-history?...` 跳到新页并**保留参数**
 *
 * 为什么值得做：后端 403 只保证"拿不到数据"，而农户/编辑员感受的是**界面** ——
 * 侧栏或页签列出一个点进去 403 的入口，等于把人往墙上引（第 180/181 批两次踩过）。
 *
 * 用法：node scripts/verify-editor-modules.mjs
 */
import { chromium } from '@playwright/test';
import { clearThrottle, runDjango } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';   // 管理端在桌面端前端（Element Plus 那套）
const PASS = 'ZzEditor!2026';

const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

clearThrottle();

// 造四个账号：news-only / pests-only / forum-only 编辑员（admin 用现成的）
const seed = runDjango([
  'import json',
  'from django.contrib.auth import get_user_model',
  'from rest_framework.authtoken.models import Token',
  'from api.serializers import CustomUserSerializer',
  'from api.capabilities import capabilities_of, content_modules_of',
  'from api.models import EditorModuleGrant',
  'User = get_user_model()',
  "admin = User.objects.get(username='admin')",
  'def make(name, module):',
  "    u, _ = User.objects.get_or_create(username=name, defaults={'role': 'EDITOR'})",
  "    u.set_password('" + PASS + "')",
  "    u.role = 'EDITOR'",
  "    u.is_active = True",
  "    u.is_deleted = False",
  "    u.save()",
  '    EditorModuleGrant.objects.filter(user=u).delete()',
  '    EditorModuleGrant.objects.create(user=u, module=module, granted_by=admin)',
  '    return u',
  "make('zz_editor_news', 'news')",
  "make('zz_editor_pests', 'pests')",
  "make('zz_editor_forum', 'forum')",
  "print('ZZ_ADMIN_TOKEN=' + Token.objects.get_or_create(user=admin)[0].key)",
  # ⚠️ 第 184 批：`CustomUserSerializer` **不含** is_superuser / is_staff / capabilities /
  #    content_modules（它只服务注册接口）。只注入它的输出时，"仅超级管理员"的那些按钮
  #    与 hasCapability 判断都拿不到依据 —— 侧栏靠 role==='ADMIN' 的兜底还能显示，
  #    但只要哪天兜底口径变了，这一支就会假绿。这里按
  #    scripts/verify-editor-permission-preview.mjs 的同一套补法补齐四个字段。
  'payload = dict(CustomUserSerializer(admin).data)',
  "payload.update({'is_superuser': admin.is_superuser, 'is_staff': admin.is_staff,",
  "                'capabilities': list(capabilities_of(admin)),",
  "                'content_modules': list(content_modules_of(admin))})",
  "print('ZZ_ADMIN_USER=' + json.dumps(payload, ensure_ascii=False))",
]);
const adminToken = /ZZ_ADMIN_TOKEN=(\S+)/.exec(seed)?.[1];
const adminUser = /ZZ_ADMIN_USER=(.+)/.exec(seed)?.[1];

const AUTHED = { viewport: { width: 1500, height: 950 }, locale: 'zh-CN' };
const browser = await chromium.launch();
const errors = [];

/** 用登录表单登进去（真实路径：编辑员也要能登录） */
const login = async (page, username) => {
  await page.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1800);
  const inputs = page.locator('input');
  await inputs.nth(0).fill(username);
  await inputs.nth(1).fill(PASS);
  await page.getByRole('button', { name: /登录/ }).first().click();
  await page.waitForTimeout(3500);
  return page.url();
};

const sidebarText = async (page) => {
  await page.waitForTimeout(1500);
  // 只看**侧栏**：整页文本里"内容管理/意见反馈"这些字在数据看板的统计卡片上也有，
  // 用 body 判断必然误报（第一版就误报了两条）
  const sidebar = page.locator('.admin-sidebar').first();
  if (await sidebar.count()) return (await sidebar.innerText()).replace(/\s+/g, ' ');
  return (await page.locator('body').innerText()).replace(/\s+/g, ' ');
};

/** 当前页面上的页签名（第 183 批：内容管理页的帖子/评论/举报） */
const tabLabels = async (page) => {
  await page.waitForTimeout(1500);
  const items = page.locator('.el-tabs__item');
  const count = await items.count();
  const out = [];
  for (let i = 0; i < count; i += 1) out.push((await items.nth(i).innerText()).replace(/\s+/g, ' ').trim());
  return out;
};

// ---------------------------------------------------------------------------
// ① 只勾新闻管理的编辑员
// ---------------------------------------------------------------------------
const ctx1 = await browser.newContext(AUTHED);
const p1 = await ctx1.newPage();
p1.on('pageerror', (e) => errors.push(String(e).slice(0, 160)));
const url1 = await login(p1, 'zz_editor_news');
check('新闻编辑员能登录并进后台', !url1.includes('/admin/login'), url1);

const text1 = await sidebarText(p1);
check('侧栏有「新闻管理」', text1.includes('新闻管理'), '');
// 第 183 批：合并后的入口叫「内容管理」——他没有 review/forum 模块，不能看到它
check('侧栏没有「内容管理」（他一个相关模块都没有）', !text1.includes('内容管理'), '');
check('侧栏没有「病害百科维护」', !text1.includes('病害百科维护'), '');
check('侧栏没有「意见反馈管理」', !text1.includes('意见反馈管理'), '');
check('侧栏没有「用户管理」', !text1.includes('用户管理'), '');
check('侧栏没有「版块管理」（BROADCAST 能力）', !text1.includes('版块管理'), '');
check('侧栏没有「系统健康」「操作日志」（仅全权）',
  !text1.includes('系统健康') && !text1.includes('操作日志'), '');
await p1.screenshot({ path: 'dsh-shots/editor-news-sidebar.png' });

// 直接输网址：拿不到百科页面
await p1.goto(`${UI}/admin/pests`, { waitUntil: 'domcontentloaded' });
await p1.waitForTimeout(3000);
const pestsText = await sidebarText(p1);
const blocked = !pestsText.includes('批量导入') || p1.url().includes('/admin/login');
check('新闻编辑员直接输 /admin/pests 进不去百科维护页', blocked,
  `${p1.url()} ｜ 含"批量导入"=${pestsText.includes('批量导入')}`);

// 直接输内容管理：应当被路由守卫拦（meta.modules = review|forum），落到看板并给出提示
await p1.goto(`${UI}/admin/content`, { waitUntil: 'domcontentloaded' });
await p1.waitForTimeout(3000);
check('新闻编辑员直接输 /admin/content 进不去内容管理页',
  !p1.url().includes('/admin/content'),
  p1.url().replace(UI, ''));

// ---------------------------------------------------------------------------
// ② 只勾病害百科的编辑员
// ---------------------------------------------------------------------------
const ctx2 = await browser.newContext(AUTHED);
const p2 = await ctx2.newPage();
p2.on('pageerror', (e) => errors.push(String(e).slice(0, 160)));
await login(p2, 'zz_editor_pests');
const text2 = await sidebarText(p2);
check('百科编辑员侧栏有「病害百科维护」', text2.includes('病害百科维护'), '');
check('百科编辑员侧栏没有「新闻管理」', !text2.includes('新闻管理'), '');
check('百科编辑员侧栏没有「用户管理」', !text2.includes('用户管理'), '');
check('百科编辑员侧栏没有「内容管理」', !text2.includes('内容管理'), '');
await p2.screenshot({ path: 'dsh-shots/editor-pests-sidebar.png' });

// ---------------------------------------------------------------------------
// ③ 只勾论坛交流的编辑员（第 183 批新增）：有内容管理、但只有两个页签
// ---------------------------------------------------------------------------
const ctx3 = await browser.newContext(AUTHED);
const p3 = await ctx3.newPage();
p3.on('pageerror', (e) => errors.push(String(e).slice(0, 160)));
await login(p3, 'zz_editor_forum');
const text3 = await sidebarText(p3);
check('论坛编辑员侧栏有「内容管理」', text3.includes('内容管理'), '');
check('论坛编辑员侧栏没有「用户管理」', !text3.includes('用户管理'), '');
check('论坛编辑员侧栏没有「版块管理」', !text3.includes('版块管理'), '');

await p3.goto(`${UI}/admin/content`, { waitUntil: 'domcontentloaded' });
await p3.waitForTimeout(3500);
const forumTabs = await tabLabels(p3);
check('论坛编辑员在内容管理页看到「帖子」「评论」两个页签',
  forumTabs.includes('帖子') && forumTabs.includes('评论'),
  `页签=${JSON.stringify(forumTabs)}`);
check('论坛编辑员**看不到**「举报」页签（仅全权管理员，点了必然 403）',
  !forumTabs.includes('举报'),
  `页签=${JSON.stringify(forumTabs)}`);

// 帖子页签里两块都在：审核队列（原内容审核）+ 帖子管理（原论坛管理）
const forumPostsText = (await p3.locator('.content-post-panel').first().innerText().catch(() => ''))
  .replace(/\s+/g, ' ');
check('帖子页签里有「待审核帖子」（原内容审核的审核队列）',
  forumPostsText.includes('待审核帖子'), forumPostsText.slice(0, 80));
check('帖子页签里有「论坛管理」（原论坛管理页：筛选 + 表格）',
  forumPostsText.includes('论坛管理') && forumPostsText.includes('全部帖子'),
  '');

// 切到评论页签：地址要带上 tab=comments，且评论面板真的渲染出来
await p3.locator('.el-tabs__item', { hasText: '评论' }).first().click();
await p3.waitForTimeout(2500);
const commentsState = await p3.evaluate(() => ({
  query: location.search,
  panel: document.querySelectorAll('.content-comment-panel').length,
  postsPanel: document.querySelectorAll('.content-post-panel').length,
  text: (document.querySelector('.content-comment-panel')?.innerText || '').replace(/\s+/g, ' '),
}));
check('切到「评论」页签：地址带 tab=comments 且评论面板渲染出来',
  commentsState.query.includes('tab=comments') && commentsState.panel === 1,
  `query="${commentsState.query}" 面板=${commentsState.panel}`);
check('评论页签是原评论管理页（筛选/表头都在），且帖子面板已卸载',
  commentsState.text.includes('评论内容') && commentsState.postsPanel === 0,
  commentsState.text.slice(0, 60));
await p3.screenshot({ path: 'dsh-shots/editor-forum-content-hub.png' });

// ---------------------------------------------------------------------------
// ④ 全权管理员：入口齐全 + 三个页签 + 旧地址重定向
// ---------------------------------------------------------------------------
const ctx4 = await browser.newContext(AUTHED);
const p4 = await ctx4.newPage();
p4.on('pageerror', (e) => errors.push(String(e).slice(0, 160)));
await p4.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
await p4.evaluate(([tk, us]) => {
  window.sessionStorage.setItem('auth_token', tk);
  window.sessionStorage.setItem('user', us);
}, [adminToken, adminUser]);
await p4.goto(`${UI}/admin/dashboard`, { waitUntil: 'domcontentloaded' });
const text4 = await sidebarText(p4);
for (const [label, need] of [
  ['用户管理', '用户管理'], ['内容管理', '内容管理'], ['新闻管理', '新闻管理'],
  ['病害百科维护', '病害百科维护'],
  ['意见反馈管理', '意见反馈管理'], ['版块管理', '版块管理'],
  ['系统健康', '系统健康'], ['操作日志', '操作日志'],
]) {
  check(`管理员侧栏有「${label}」`, text4.includes(need), '');
}
// 合并后旧的三项不该再作为**侧栏项**出现（文案本身仍用于页内区块标题，所以只查侧栏 href）
const navHrefs = await p4.evaluate(() =>
  [...document.querySelectorAll('.admin-nav-item')].map((el) => el.getAttribute('href')));
check('侧栏不再有 /admin/review、/admin/forum、/admin/comments 三条旧入口',
  !navHrefs.some((href) => ['/admin/review', '/admin/forum', '/admin/comments'].includes(href)),
  navHrefs.join(' '));
// 第 184 批：识别记录并入「用户管理」—— 侧栏不再单列一项，href 也不该再出现
check('侧栏不再有 /admin/detection-history（识别记录已并入「用户管理」页签）',
  !navHrefs.includes('/admin/detection-history'), navHrefs.join(' '));
check('管理员侧栏里有「用户管理」，且「识别记录」不再单独占一项',
  text4.includes('用户管理') && !text4.includes('识别记录'), '');
await p4.screenshot({ path: 'dsh-shots/editor-admin-sidebar.png' });

await p4.goto(`${UI}/admin/content`, { waitUntil: 'domcontentloaded' });
await p4.waitForTimeout(3500);
const adminTabs = await tabLabels(p4);
check('管理员在内容管理页看到三个页签（帖子/评论/举报）',
  ['帖子', '评论', '举报'].every((label) => adminTabs.includes(label)),
  `页签=${JSON.stringify(adminTabs)}`);
await p4.screenshot({ path: 'dsh-shots/admin-content-hub.png' });

// 举报页签：真的是原来那块举报处理（面板 + 待处理计数）
await p4.locator('.el-tabs__item', { hasText: '举报' }).first().click();
await p4.waitForTimeout(2500);
const reportState = await p4.evaluate(() => ({
  query: location.search,
  panel: document.querySelectorAll('.content-report-panel').length,
  text: (document.querySelector('.content-report-panel')?.innerText || '').replace(/\s+/g, ' '),
}));
check('举报页签是原举报处理（面板在、地址带 tab=reports）',
  reportState.panel === 1 && reportState.query.includes('tab=reports')
    && reportState.text.includes('待处理'),
  `query="${reportState.query}"｜${reportState.text.slice(0, 60)}`);

// 三条旧地址：必须落到新页的对应页签
for (const [legacy, tab] of [
  ['/admin/review', 'posts'],
  ['/admin/forum', 'posts'],
  ['/admin/comments', 'comments'],
]) {
  await p4.goto(`${UI}${legacy}`, { waitUntil: 'domcontentloaded' });
  await p4.waitForTimeout(2500);
  check(`旧地址 ${legacy} 重定向到 /admin/content?tab=${tab}`,
    p4.url().includes('/admin/content') && p4.url().includes(`tab=${tab}`),
    p4.url().replace(UI, ''));
}

// 旧地址上的筛选参数要保留（第 98 批的约定：筛选/分页写在 URL 上，老链接照样能用）
await p4.goto(`${UI}/admin/forum?search=zz老链接`, { waitUntil: 'domcontentloaded' });
await p4.waitForTimeout(2500);
const legacyQuery = await p4.evaluate(() => ({
  search: (document.querySelector('.filter-bar input')?.value || ''),
  url: location.pathname + location.search,
}));
check('旧地址 /admin/forum?search=xx 的筛选参数被保留',
  legacyQuery.search === 'zz老链接' && legacyQuery.url.includes('tab=posts'),
  `${legacyQuery.url}｜输入框="${legacyQuery.search}"`);

// ---------------------------------------------------------------------------
// ⑤ 用户管理合并页（第 184 批）：两个页签 + `?tab=` 同步 + 旧地址重定向
// ---------------------------------------------------------------------------
// ⚠️ 页签用的是 Element Plus 的 `lazy` 页签：**打开过的**页签会一直留在 DOM 里
//    （只是 `display:none`），所以"另一个页签没挂载"这条只能在**首次进入**时验 ——
//    下面两处（默认进入、深链进入）都是刚 `goto` 过的全新页面，判据成立。
await p4.goto(`${UI}/admin/users`, { waitUntil: 'domcontentloaded' });
await p4.waitForTimeout(3500);
const hubDefault = await p4.evaluate(() => ({
  tabs: [...document.querySelectorAll('.el-tabs__item')]
    .map((el) => el.innerText.replace(/\s+/g, ' ').trim()),
  usersPanel: document.querySelectorAll('.admin-users').length,
  detectionsPanel: document.querySelectorAll('.admin-page').length,
  text: (document.querySelector('.admin-users')?.innerText || '').replace(/\s+/g, ' '),
}));
check('管理员 /admin/users 是带页签的合并页（用户 + 识别记录）',
  hubDefault.tabs.includes('用户') && hubDefault.tabs.includes('识别记录'),
  `页签=${JSON.stringify(hubDefault.tabs)}`);
check('默认落在「用户」页签：用户管理在（用户总数），识别记录**未挂载**',
  hubDefault.usersPanel === 1 && hubDefault.detectionsPanel === 0
    && hubDefault.text.includes('用户总数'),
  `users面板=${hubDefault.usersPanel}｜identify面板=${hubDefault.detectionsPanel}`);

// 点「识别记录」页签：地址要带上 tab=detections，且识别记录页真的渲染出来
await p4.locator('.el-tabs__item', { hasText: '识别记录' }).first().click();
await p4.waitForTimeout(2500);
const hubDetections = await p4.evaluate(() => ({
  query: location.search,
  detectionsPanel: document.querySelectorAll('.admin-page').length,
  usersStillVisible: (document.body.innerText || '').includes('用户总数'),
  text: (document.querySelector('.admin-page')?.innerText || '').replace(/\s+/g, ' '),
}));
check('点「识别记录」页签：地址带 tab=detections 且识别记录页渲染出来',
  hubDetections.query.includes('tab=detections') && hubDetections.detectionsPanel === 1
    && hubDetections.text.includes('记录总数'),
  `query="${hubDetections.query}"｜${hubDetections.text.slice(0, 50)}`);
check('切到识别记录后「用户」页签的内容不再显示（不是两页摞在一起）',
  hubDetections.usersStillVisible === false, `页面上还有"用户总数"=${hubDetections.usersStillVisible}`);

// 深链：直接打开 /admin/users?tab=detections —— 落在识别记录上，
// 且**不挂载**用户页签（第 183 批的教训：两边都挂载 = 一次进页面打两倍的接口）
await p4.goto(`${UI}/admin/users?tab=detections`, { waitUntil: 'domcontentloaded' });
await p4.waitForTimeout(3500);
const hubDeepLink = await p4.evaluate(() => ({
  active: (document.querySelector('.el-tabs__item.is-active')?.innerText || '').replace(/\s+/g, ' ').trim(),
  usersPanel: document.querySelectorAll('.admin-users').length,
  detectionsPanel: document.querySelectorAll('.admin-page').length,
}));
check('深链 /admin/users?tab=detections 直接落在「识别记录」页签',
  hubDeepLink.active.includes('识别记录') && hubDeepLink.detectionsPanel === 1,
  `当前页签="${hubDeepLink.active}"｜identify面板=${hubDeepLink.detectionsPanel}`);
check('深链进入时「用户」页签**没有**被挂载（只挂当前页签）',
  hubDeepLink.usersPanel === 0, `users面板=${hubDeepLink.usersPanel}`);
await p4.screenshot({ path: 'dsh-shots/admin-user-hub-detections.png' });

// 旧地址：/admin/detection-history 重定向到新页的识别记录页签，且**参数不丢**
// （第 98 批的约定：筛选/分页写在 URL 上，所以"打开一条带筛选的老链接"必须照旧能用）
await p4.goto(`${UI}/admin/detection-history?x=1&page=2`, { waitUntil: 'domcontentloaded' });
await p4.waitForTimeout(3000);
const legacyHub = await p4.evaluate(() => ({
  path: location.pathname,
  search: location.search,
  detectionsPanel: document.querySelectorAll('.admin-page').length,
}));
check('旧地址 /admin/detection-history 重定向到 /admin/users?tab=detections',
  legacyHub.path === '/admin/users' && legacyHub.search.includes('tab=detections')
    && legacyHub.detectionsPanel === 1,
  `${legacyHub.path}${legacyHub.search}`);
check('旧地址上的查询参数被保留（x=1 与 page=2 都还在）',
  legacyHub.search.includes('x=1') && legacyHub.search.includes('page=2'),
  `query="${legacyHub.search}"`);

check('全程无 JS 报错', errors.length === 0, errors.slice(0, 2).join(' | '));

await browser.close();

try {
  runDjango([
    'from django.contrib.auth import get_user_model',
    "print('cleaned:', get_user_model().objects.filter(username__startswith='zz_editor_').delete()[0])",
  ]);
} catch (error) {
  console.warn('  清理失败（忽略）:', String(error).slice(0, 100));
}

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
