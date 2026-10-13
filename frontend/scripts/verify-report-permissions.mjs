/**
 * 举报页签的两档分权（第 189 批回归）
 * ============================================================================
 * 用户反馈：信息编辑员在「内容管理」里管内容，却**看不到举报页签**。
 * 第 189 批把举报从"仅全权管理员"改成**只放开一半**：
 *
 *   | 能做什么 | 谁 |
 *   |---|---|
 *   | 看别人的举报、处置（处理/驳回） | `review`/`forum` 模块的编辑员 或 全权管理员 |
 *   | **看到举报人是谁**、**同时隐藏内容** | **仅全权管理员** |
 *
 * 覆盖（用真浏览器 + 真后端，两档身份各看一遍）：
 *   ① 编辑员：能打开举报页签、看得到别人提交的举报、**看不到举报人**；
 *   ② 编辑员：能处置（点「驳回」成功）；**没有**「同时隐藏内容」勾选框（只有一句说明）；
 *   ③ 编辑员：直接调接口传 hide_content=true → 帖子**不会**被隐藏，且回包 hide_denied=true；
 *   ④ 管理员：举报人可见、有勾选框、勾了真的把帖子下架（回归：别把编辑员的限制套给管理员）。
 *
 * 用法：node scripts/verify-report-permissions.mjs
 * 自己造数据自己清（zzrep_ 前缀）。
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzRep!2026pw';
const adminName = `zzrep_admin_${suffix}`;
const editorName = `zzrep_editor_${suffix}`;
const authorName = `zzrep_author_${suffix}`;
const reporterName = `zzrep_reporter_${suffix}`;
const boardName = `zzrep版块${suffix}`;

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
      'from api.models import EditorModuleGrant',
      'from api.models_forum import Post, ForumBoard',
      'from api.models_report import Report',
      "print('reports deleted:', Report.objects.filter(detail__startswith='zzrep').delete()[0])",
      "print('posts deleted:', Post.objects.filter(title__startswith='zzrep').delete()[0])",
      "print('boards deleted:', ForumBoard.objects.filter(name__startswith='zzrep').delete()[0])",
      "EditorModuleGrant.objects.filter(user__username__startswith='zzrep_').delete()",
      'U = get_user_model()',
      "print('users deleted:', U.objects.filter(username__startswith='zzrep_').delete()[0])",
    ]);
  } catch (error) { console.error('清理失败（忽略）:', error?.message || error); }
};
process.on('exit', cleanup);

clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models import EditorModuleGrant',
  'from api.models_forum import Post, ForumBoard',
  'from api.models_report import Report',
  'U = get_user_model()',
  `admin = U.objects.create_superuser(username='${adminName}', password='${password}', email='', role='ADMIN')`,
  `editor = U.objects.create_user(username='${editorName}', password='${password}', role='EDITOR')`,
  "EditorModuleGrant.objects.create(user=editor, module='review', granted_by=admin)",
  `author = U.objects.create_user(username='${authorName}', password='${password}', role='USER')`,
  `reporter = U.objects.create_user(username='${reporterName}', password='${password}', role='USER')`,
  `board = ForumBoard.objects.create(name='${boardName}', order=951)`,
  `post = Post.objects.create(title='zzrep被举报的帖子', content='<p>x</p>', author=author, board=board, status='published')`,
  `Report.objects.create(reporter=reporter, target_type='post', post=post, target_user=author, reason='ad', detail='zzrep举报内容')`,
  "print('seeded ok, post id =', post.id)",
]);

const postId = Number(String(runDjango([
  'from api.models_forum import Post',
  "print(Post.objects.get(title='zzrep被举报的帖子').id)",
])).trim().split('\n').pop());
const reportId = Number(String(runDjango([
  'from api.models_report import Report',
  "print(Report.objects.get(detail='zzrep举报内容').id)",
])).trim().split('\n').pop());
console.log('测试帖 id =', postId, '｜举报 id =', reportId);

const browser = await chromium.launch();

/** 以某个账号登录并打开举报页签，返回这个 context 的页面与收集到的错误 */
const openReports = async (username) => {
  clearThrottle();
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 }, locale: 'zh-CN' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text().slice(0, 160)}`); });

  await page.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.admin-login', { timeout: 30_000 });
  await page.locator('#username').fill(username);
  await page.locator('#password').fill(password);
  await page.locator('button[type="submit"]').first().click();
  await page.waitForURL((u) => u.pathname.startsWith('/admin/') && u.pathname !== '/admin/login', { timeout: 30_000 });
  await page.waitForSelector('.admin-console', { timeout: 25_000 });

  await page.goto(`${UI}/admin/content?tab=reports`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);
  return { ctx, page, errors };
};

// ---------------------------------------------------------------------------
// ① 编辑员：能看能处置，但看不到举报人
// ---------------------------------------------------------------------------
console.log('\n--- ① 信息编辑员（review 模块）打开举报页签 ---');
const ed = await openReports(editorName);
check('编辑员能进举报页签（不再被改回帖子页签）',
  ed.page.url().includes('tab=reports'), ed.page.url().replace(UI, ''));
const tabText = await ed.page.locator('.content-hub-tabs').innerText().catch(() => '');
check('页签栏里有「举报」', tabText.includes('举报'), tabText.replace(/\s+/g, ' ').slice(0, 60));

const panelText = await ed.page.locator('.content-report-panel').innerText().catch(() => '');
check('看得到别人提交的这条举报', panelText.includes('zzrep举报内容') || panelText.includes('广告'), panelText.replace(/\s+/g, ' ').slice(0, 80));
check('举报人用户名**不出现**在页面上', !panelText.includes(reporterName), panelText.replace(/\s+/g, ' ').slice(0, 100));
check('显示「举报人已隐去」的说明', panelText.includes('举报人已隐去'));
check('没有「同时隐藏内容」勾选框', (await ed.page.locator('.report-actions .el-checkbox').count()) === 0);
check('改为显示「下架内容仅全权管理员」说明', panelText.includes('下架内容仅全权管理员'));

// ② 编辑员处置这条举报（点「驳回」）
console.log('\n--- ② 编辑员处置举报（可逆动作，应当允许）---');
await ed.page.locator('.report-item').filter({ hasText: 'zzrep举报内容' })
  .locator('button', { hasText: '驳回' }).first().click();
await ed.page.waitForTimeout(2500);
const dbStatus = String(runDjango([
  'from api.models_report import Report',
  `print(Report.objects.get(id=${reportId}).status)`,
])).trim().split('\n').pop();
check('处置成功（库中状态 = rejected）', dbStatus === 'rejected', `status=${dbStatus}`);
check('全程无 JS 报错', ed.errors.length === 0, ed.errors.slice(0, 2).join(' | '));
await ed.ctx.close();

// ---------------------------------------------------------------------------
// ③ 编辑员直连接口传 hide_content=true：不该生效
// ---------------------------------------------------------------------------
console.log('\n--- ③ 编辑员绕过界面直接要求"同时隐藏内容" ---');
clearThrottle();
runDjango([
  'from api.models_report import Report',
  `r = Report.objects.get(id=${reportId})`,
  "r.status = 'pending'",
  "r.save(update_fields=['status'])",
  "print('report reset to pending')",
]);
const bypass = await (async () => {
  clearThrottle();
  const ctx = await browser.newContext({ locale: 'zh-CN' });
  const page = await ctx.newPage();
  await page.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.admin-login', { timeout: 30_000 });
  await page.locator('#username').fill(editorName);
  await page.locator('#password').fill(password);
  await page.locator('button[type="submit"]').first().click();
  await page.waitForURL((u) => u.pathname.startsWith('/admin/') && u.pathname !== '/admin/login', { timeout: 30_000 });
  const out = await page.evaluate(async ({ api, id }) => {
    const token = sessionStorage.getItem('auth_token');
    const res = await fetch(`${api}/reports/${id}/handle/`, {
      method: 'POST',
      headers: { Authorization: `Token ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'handled', note: 'zzrep 绕过测试', hide_content: true }),
    });
    return { status: res.status, body: await res.json() };
  }, { api: API, id: reportId });
  await ctx.close();
  return out;
})();
check('编辑员处置接口返回 200（不是 403）', bypass.status === 200, `HTTP ${bypass.status}`);
check('回包 hidden_content=false（没隐藏）', bypass.body?.hidden_content === false, JSON.stringify(bypass.body?.hidden_content));
check('回包 hide_denied=true（如实告知没隐藏）', bypass.body?.hide_denied === true, JSON.stringify(bypass.body?.hide_denied));
check('回包里没有举报人用户名', !bypass.body?.reporter?.username, JSON.stringify(bypass.body?.reporter));
const postAfterBypass = String(runDjango([
  'from api.models_forum import Post',
  `print(Post.objects.get(id=${postId}).status)`,
])).trim().split('\n').pop();
check('帖子**没有**被下架（仍是 published）', postAfterBypass === 'published', postAfterBypass);

// ---------------------------------------------------------------------------
// ④ 管理员：举报人可见 + 勾了真的隐藏
// ---------------------------------------------------------------------------
console.log('\n--- ④ 全权管理员对照 ---');
clearThrottle();
runDjango([
  'from api.models_report import Report',
  `r = Report.objects.get(id=${reportId})`,
  "r.status = 'pending'",
  "r.save(update_fields=['status'])",
  "print('report reset to pending')",
]);
const ad = await openReports(adminName);
const adminText = await ad.page.locator('.content-report-panel').innerText().catch(() => '');
check('管理员看得到举报人用户名', adminText.includes(reporterName), adminText.replace(/\s+/g, ' ').slice(0, 90));
check('副标题不再写"仅全权管理员"（第 189 批后编辑员也能进）',
  !adminText.includes('仅全权管理员：'), adminText.replace(/\s+/g, ' ').slice(0, 60));

// ⚠️ 只在这条举报的卡片里数勾选框：用全局 `.report-actions .el-checkbox` 会把
//    别处渲染出来的同类元素一起数进来（第 188 批就在这类"范围没限定"的断言上踩过）
const adminCard = ad.page.locator('.report-item').filter({ hasText: 'zzrep举报内容' }).first();
check('管理员有「同时隐藏内容」勾选框', (await adminCard.locator('.el-checkbox').count()) === 1);
// 用 check() 而不是 click()：click 一次只保证"点了一下"，不保证"变成了选中"
//
// ⚠️ 要点 `.el-checkbox`（可见的壳），不要点里面真正的 `input`：
//    Element Plus 的原始 checkbox 是视觉隐藏的，Playwright 会报
//    "Element is outside of the viewport"（踩过一次）
const adminCheckbox = adminCard.locator('.el-checkbox').first();
await adminCheckbox.scrollIntoViewIfNeeded();
if (!(await adminCheckbox.evaluate((el) => el.className.includes('is-checked')))) {
  await adminCheckbox.click();
}
await ad.page.waitForTimeout(400);
check('勾选框确实处于选中状态',
  await adminCard.locator('.el-checkbox').first().evaluate((el) => el.className.includes('is-checked')));
await adminCard.locator('button', { hasText: '处理' }).first().click();
await ad.page.waitForTimeout(3000);
const postAfterAdmin = String(runDjango([
  'from api.models_forum import Post',
  `print(Post.objects.get(id=${postId}).status)`,
])).trim().split('\n').pop();
check('管理员勾选后帖子真的被下架（hidden）', postAfterAdmin === 'hidden', postAfterAdmin);
check('管理员操作全程无 JS 报错', ad.errors.length === 0, ad.errors.slice(0, 2).join(' | '));
await ad.ctx.close();

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
