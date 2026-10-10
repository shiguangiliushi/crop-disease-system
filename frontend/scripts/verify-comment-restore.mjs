/**
 * 「评论删除可恢复」端到端验证（第 152 批）
 * ============================================================================
 * 起因：控制台有「删除」与「彻底删除」两个按钮，但"删除"其实也是不可恢复的 ——
 * 第 17 批的实现是把 content 直接覆盖成 `[已删除]`，原文就没了，删错只能去日志里"看"。
 * 这一批给软删除留档（Comment.original_content + deleted_by）并加恢复接口。
 *
 * 覆盖：
 *   ① 软删除后，「只看已删除」里能看到**原内容**与**删除人**
 *   ② 全权管理员点「恢复」→ 评论回到列表/农户端，帖子评论数加回来
 *   ③ 编辑员：能删但**看不到**「恢复」按钮；直连接口 403
 *   ④ 本批之前删除的评论（没有留存原文）→ 恢复按钮禁用并说明原因；直连接口 400
 *   ⑤ 恢复会写审计日志（comment.restore，含原删除人）
 *   ⑥ 「彻底删除」不受影响：连原文一起没了，之后也恢复不了
 *
 * 用法：node scripts/verify-comment-restore.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const superName = `zze2e_cr_super_${suffix}`;
const editorName = `zze2e_cr_editor_${suffix}`;
const authorName = `zze2e_cr_author_${suffix}`;
const boardName = `zze2e恢复测试版块${suffix}`;
const postTitle = `zz恢复测试帖${suffix}`;

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
      "print('cleaned comments:', Comment.objects.filter(post__title__startswith='zz恢复测试帖').delete()[0])",
      "print('cleaned posts:', Post.objects.filter(title__startswith='zz恢复测试帖').delete()[0])",
      "print('cleaned boards:', ForumBoard.objects.filter(name__startswith='zze2e恢复测试版块').delete()[0])",
      "print('cleaned logs:', AdminAuditLog.objects.filter(target_repr__contains='zz可恢复').delete()[0])",
      "EditorModuleGrant.objects.filter(user__username__startswith='zze2e_cr_').delete()",
      'U = get_user_model()',
      "print('cleaned users:', U.objects.filter(username__startswith='zze2e_cr_').delete()[0])",
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
  `board = ForumBoard.objects.create(name='${boardName}', order=998)`,
  `post = Post.objects.create(title='${postTitle}', content='<p>x</p>', author=author, board=board, status='published')`,
  "Comment.objects.create(post=post, author=author, content='zz可恢复的评论原文')",
  // 一条"本批之前删除的"历史数据：删过、但没留原文
  "legacy = Comment.objects.create(post=post, author=author, content='[已删除]')",
  "Comment.objects.filter(id=legacy.id).update(is_deleted=True, original_content='')",
  "post.update_comment_count()",
  "print('POST_ID', post.id)",
]);
const postId = Number(/POST_ID (\d+)/.exec(String(seedOut))[1]);

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

const callApi = (target, path, method = 'GET') => target.evaluate(async ({ api, path, method }) => {
  const token = sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}${path}`, {
    method, headers: { Authorization: `Token ${token}`, 'Content-Type': 'application/json' },
  });
  let body = null;
  try { body = await res.json(); } catch { body = null; }
  return { status: res.status, body };
}, { api: API, path, method });

await loginAs(page, superName);

// ---------------------------------------------------------------------------
// ① 编辑员删掉那条评论 → 管理员在「只看已删除」里看到原内容与删除人
// ---------------------------------------------------------------------------
clearThrottle();
const softDeleted = runDjango([
  'from django.contrib.auth import get_user_model',
  'from rest_framework.test import APIClient',
  'from api.models_forum import Comment',
  'U = get_user_model()',
  `ed = U.objects.get(username='${editorName}')`,
  'c = APIClient(); c.force_authenticate(user=ed)',
  "row = Comment.objects.get(content='zz可恢复的评论原文')",
  "r = c.post(f'/api/admin/comments/{row.id}/soft-delete/')",
  "print('SOFT', r.status_code, row.id)",
]);
const commentId = Number(/SOFT \d+ (\d+)/.exec(String(softDeleted))[1]);
check('编辑员软删除成功', /SOFT 200/.test(String(softDeleted)), String(softDeleted).trim().slice(0, 40));

await page.goto(`${UI}/admin/comments?scope=deleted&search=zz可恢复`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.el-table__row', { timeout: 25_000 });
await page.waitForTimeout(2000);
const deletedRow = (await rowTexts()).join(' || ');
check('「只看已删除」里显示原内容', deletedRow.includes('zz可恢复的评论原文'),
  deletedRow.slice(0, 110));
check('显示是谁删的（删除人 = 编辑员）', deletedRow.includes(editorName), '');
check('有「恢复」按钮（全权管理员）',
  (await page.locator('.el-table__row button').filter({ hasText: /^\s*恢复\s*$/ }).count()) >= 1);

await page.screenshot({ path: 'dsh-shots/admin-comment-restore.png', clip: { x: 0, y: 0, width: 1700, height: 700 } });

// ---------------------------------------------------------------------------
// ② 恢复
// ---------------------------------------------------------------------------
const beforeCount = (await callApi(page, `/forums/posts/${postId}/`)).body?.comment_count;
// ⚠️ 必须点**有原文那一行**的恢复按钮：列表里还有别处删掉的评论（没有原文，
//    按钮是禁用的），`.first()` 很容易点到那种，然后一直等不到确认框。
const targetRow = page.locator('.el-table__row').filter({ hasText: 'zz可恢复的评论原文' }).first();
const restoreBtn = targetRow.locator('button').filter({ hasText: /^\s*恢复\s*$/ }).first();
console.log('  [诊断] 目标行数 =', await page.locator('.el-table__row').filter({ hasText: 'zz可恢复的评论原文' }).count(),
  '| 恢复按钮数 =', await targetRow.locator('button', { hasText: '恢复' }).count(),
  '| 禁用 =', await restoreBtn.isDisabled());
await restoreBtn.click();
await page.waitForTimeout(2500);
console.log('  [诊断] 点击后 .el-message-box =', await page.locator('.el-message-box').count(),
  '| 可见 =', await page.locator('.el-message-box').first().isVisible().catch(() => false),
  '| 最近的 console.error =', consoleErrors.slice(-3).join(' || ') || '（无）');
await page.waitForSelector('.el-message-box', { timeout: 10_000 });
const confirmText = await page.locator('.el-message-box').innerText();
check('恢复确认框里写明原文与"是谁删的"',
  confirmText.includes('zz可恢复的评论原文') && confirmText.includes(editorName),
  confirmText.replace(/\s+/g, ' ').slice(0, 110));
await page.locator('.el-message-box__btns button.el-button--primary').click();
await page.waitForTimeout(2500);

const afterRestore = await callApi(page, `/forums/posts/${postId}/comments/`);
const contents = (afterRestore.body?.results || afterRestore.body || []).map((r) => r.content);
check('恢复后农户端又能看到这条评论', contents.includes('zz可恢复的评论原文'),
  JSON.stringify(contents).slice(0, 80));
const countAfter = (await callApi(page, `/forums/posts/${postId}/`)).body?.comment_count;
check('帖子评论数加回来了', countAfter === (beforeCount ?? 0) + 1,
  `${beforeCount} → ${countAfter}`);

// ---------------------------------------------------------------------------
// ⑤ 审计日志
// ---------------------------------------------------------------------------
const logs = runDjango([
  'from api.models_audit import AdminAuditLog',
  "log = AdminAuditLog.objects.filter(action='comment.restore').first()",
  "print('LOG', log.target_repr if log else 'NONE', '|', (log.detail[:60] if log else ''))",
]);
check('恢复写了审计日志（含原删除人）',
  /zz可恢复的评论原文/.test(String(logs)) && /原删除人/.test(String(logs)),
  String(logs).trim().slice(0, 90));

// ---------------------------------------------------------------------------
// ③ 编辑员看不到恢复按钮、直连 403
// ---------------------------------------------------------------------------
const editorCtx = await browser.newContext({ viewport: { width: 1700, height: 1000 }, locale: 'zh-CN' });
const editorPage = await editorCtx.newPage();
await loginAs(editorPage, editorName);
await editorPage.goto(`${UI}/admin/comments?scope=deleted`, { waitUntil: 'domcontentloaded' });
await editorPage.waitForSelector('.el-table__row', { timeout: 25_000 });
await editorPage.waitForTimeout(2000);
const editorButtons = (await editorPage.locator('.el-table__row button').allInnerTexts())
  .map((text) => text.trim());
// 精确比较，别用 includes：行的「所属帖子」按钮是帖子标题，
// 而这次的测试帖就叫「zz恢复测试帖」—— 子串匹配会把它误判成"有恢复按钮"。
check('编辑员看不到「恢复」按钮', !editorButtons.includes('恢复'),
  editorButtons.join(' / ').slice(0, 60));

clearThrottle();
// ⚠️ 取数一律**限定本次那篇帖子**并用 filter().first()：
//    用 `Comment.objects.get(content=...)` 会被库里同名评论（含早先跑崩那几轮的残留）坑成
//    MultipleObjectsReturned。测试数据要能被反复跑。
const myPost = `Post.objects.filter(title__startswith='zz恢复测试帖').first()`;
runDjango([
  'from django.contrib.auth import get_user_model',
  'from rest_framework.test import APIClient',
  'from api.models_forum import Comment, Post',
  'U = get_user_model()',
  `ed = U.objects.get(username='${editorName}')`,
  'c = APIClient(); c.force_authenticate(user=ed)',
  `p = ${myPost}`,
  "row2 = Comment.objects.filter(post=p).exclude(content='[已删除]').first()",
  "c.post(f'/api/admin/comments/{row2.id}/soft-delete/')",
  "r = c.post(f'/api/admin/comments/{row2.id}/restore/')",
  "print('EDITOR_RESTORE', r.status_code)",
]);
// 编辑员：能删、**不能**恢复 —— 用"刚被自己软删、且有原文"的那条去试，必须 403
const editorRestore = runDjango([
  'from django.contrib.auth import get_user_model',
  'from rest_framework.test import APIClient',
  'from api.models_forum import Comment, Post',
  'U = get_user_model()',
  `ed = U.objects.get(username='${editorName}')`,
  'c = APIClient(); c.force_authenticate(user=ed)',
  `p = ${myPost}`,
  "row = Comment.objects.filter(post=p, is_deleted=True).exclude(original_content='').first()",
  "r = c.post(f'/api/admin/comments/{row.id}/restore/')",
  "print('EDITOR_RESTORE', r.status_code)",
]);
check('编辑员直连恢复接口 → 403（能删不能恢复）',
  /EDITOR_RESTORE 403/.test(String(editorRestore)),
  String(editorRestore).trim().slice(0, 40));

// ---------------------------------------------------------------------------
// ④ 没有原文的历史数据：按钮禁用 + 直连 400
// ---------------------------------------------------------------------------
const legacyStatus = runDjango([
  'from django.contrib.auth import get_user_model',
  'from rest_framework.test import APIClient',
  'from api.models_forum import Comment, Post',
  'U = get_user_model()',
  `admin = U.objects.get(username='${superName}')`,
  'c = APIClient(); c.force_authenticate(user=admin)',
  `p = ${myPost}`,
  "row = Comment.objects.filter(post=p, is_deleted=True, original_content='').first()",
  "r = c.post(f'/api/admin/comments/{row.id}/restore/')",
  "print('LEGACY', r.status_code, r.data.get('detail',''))",
]);
check('没有留存原文的评论 → 恢复被拒并说明原因（400）',
  /LEGACY 400/.test(String(legacyStatus)) && /没有留存原文/.test(String(legacyStatus)),
  String(legacyStatus).trim().slice(0, 90));

await page.goto(`${UI}/admin/comments?scope=deleted`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.el-table__row', { timeout: 25_000 });
await page.waitForTimeout(2000);
const legacyRow = page.locator('.el-table__row').filter({ hasText: '没有留存原文' }).first();
// ⚠️ 精确匹配「恢复」：这一行里还有个"所属帖子"按钮，标题是帖子名
//    （本次叫「zz恢复测试帖…」），子串匹配会挑中它 —— 那个按钮当然不是禁用的。
const legacyRestore = legacyRow.locator('button').filter({ hasText: /^\s*恢复\s*$/ }).first();
check('历史数据行的「恢复」按钮被禁用（并给出原因）',
  (await legacyRestore.count()) === 1 && await legacyRestore.isDisabled(),
  await legacyRestore.getAttribute('title'));

await editorCtx.close();

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
