/**
 * 「更新帖子」后不该再弹「有未保存的修改」（第 170 批）
 * ============================================================================
 * 用户反馈的原始场景（附了截图）：
 *   编辑帖子 → 点「更新帖子」→ 弹出「当前页面还有未保存的内容，离开后这些修改会丢失」
 *   ✗ 可修改**其实已经存好了**。
 *
 * 根因：本页的 isDirty 是"表单 vs 打开时的基准"比对，而离开守卫在**跳转时重新求值** ——
 * 保存成功后没有挪基准，于是详情页的 router.push 被自己的守卫拦下。
 *
 * 本脚本把三条路径都钉住：
 *   ① 改标题 → 更新帖子 → 跳到详情页，且**没有**弹「未保存」对话框，改动确实生效
 *   ② 改正文 → 保存草稿 → 之后再点导航离开，不该弹（草稿也"存好了"）
 *   ③ 删除帖子 → 跳回论坛，不该弹
 *   ④ 反过来：**真的**有未保存修改时，守卫仍然要拦（别把守卫改废了）
 *
 * 用法：node scripts/verify-edit-save-guard.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const results = [];
let cleaned = false;
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

clearThrottle();
const seed = runDjango([
  'import json',
  'from django.contrib.auth import get_user_model',
  'from rest_framework.authtoken.models import Token',
  'from api.serializers import CustomUserSerializer',
  'from api.models_forum import ForumBoard, Post',
  "admin = get_user_model().objects.get(username='admin')",
  "b = ForumBoard.objects.order_by('order','id').first()",
  "Post.objects.filter(title__startswith='zz存盘守卫').delete()",
  "p = Post.objects.create(title='zz存盘守卫：原始标题', content='<p>原始正文，够十个字了吧。</p>', author=admin, board=b, status='published')",
  'token, _ = Token.objects.get_or_create(user=admin)',
  "print('ZZ_ID=' + str(p.id))",
  "print('ZZ_TOKEN=' + token.key)",
  "print('ZZ_USER=' + json.dumps(CustomUserSerializer(admin).data, ensure_ascii=False))",
]);
const postId = /ZZ_ID=(\d+)/.exec(seed)?.[1];
const token = /ZZ_TOKEN=(\S+)/.exec(seed)?.[1];
const userJson = /ZZ_USER=(.+)/.exec(seed)?.[1];

const cleanup = () => {
  if (cleaned) return;
  cleaned = true;
  clearThrottle();
  try {
    runDjango([
      'from api.models_forum import Post',
      "print('cleaned:', Post.objects.filter(title__startswith='zz存盘守卫').delete()[0])",
    ]);
  } catch (error) {
    console.error('清理失败（忽略）:', error?.message || error);
  }
};
process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 950 }, locale: 'zh-CN' })).newPage();
const pageErrors = [];
page.on('pageerror', (error) => pageErrors.push(String(error).slice(0, 200)));

const login = async () => {
  await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(([tk, us]) => {
    window.sessionStorage.setItem('auth_token', tk);
    window.sessionStorage.setItem('user', us);
  }, [token, userJson]);
};

/** 页面上有没有那个「未保存」对话框 */
const hasLeaveDialog = async () => {
  const text = await page.locator('.el-message-box').allInnerTexts().catch(() => []);
  return text.some((t) => t.includes('未保存'));
};

await login();

// ---------------------------------------------------------------------------
// ① 更新帖子：跳到详情页、无对话框、改动生效
// ---------------------------------------------------------------------------
await page.goto(`${UI}/forum/post/${postId}/edit`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.ql-editor', { timeout: 30_000 });
await page.waitForTimeout(2500);

const titleInput = page.locator('.el-form-item').filter({ hasText: '标题' }).locator('input').first();
await titleInput.fill('zz存盘守卫：改过的标题');
await page.waitForTimeout(400);
await page.getByRole('button', { name: /更新帖子/ }).first().click();

// 提示会自己消失（约 3 秒），所以在等待跳转的同时**轮询抓一次**它的文字
let updateToast = '';
for (let i = 0; i < 25; i += 1) {
  const texts = await page.locator('.el-message').allInnerTexts().catch(() => []);
  if (texts.length) { updateToast = texts.join(' / '); break; }
  await page.waitForTimeout(200);
}

// ⚠️ 要**等跳转**，不能只 sleep：校验 + 保存 + 跳转实测 2~4 秒，
//    第一版固定等 2.5 秒，断言时人还在编辑页（其实已经修好，是脚本太急）。
let navigatedAfterUpdate = true;
try {
  await page.waitForURL((url) => /\/forum\/post\/\d+$/.test(url.pathname), { timeout: 25_000 });
} catch {
  navigatedAfterUpdate = false;
}
await page.waitForTimeout(600);

const dialogAfterUpdate = await hasLeaveDialog();
await page.screenshot({ path: 'dsh-shots/edit-save-guard.png' });
check('点「更新帖子」后**没有**弹「未保存」对话框', !dialogAfterUpdate,
  dialogAfterUpdate ? await page.locator('.el-message-box').innerText() : '');
check('更新后跳到了帖子详情页', navigatedAfterUpdate && /\/forum\/post\/\d+$/.test(new URL(page.url()).pathname), page.url());
check('更新成功的提示写的是「更新成功！」而不是「发帖成功！」',
  updateToast.includes('更新成功'), updateToast || '（没抓到提示）');

const detailText = await page.locator('body').innerText();
check('详情页显示的是改过的标题', detailText.includes('zz存盘守卫：改过的标题'),
  (detailText.match(/zz存盘守卫：[^\s]*/g) || []).join(' / '));

// ---------------------------------------------------------------------------
// ② 保存草稿后离开：不该弹
// ---------------------------------------------------------------------------
await page.goto(`${UI}/forum/post/${postId}/edit`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.ql-editor', { timeout: 30_000 });
await page.waitForTimeout(2500);
await page.locator('.ql-editor').click();
await page.keyboard.type('又补了一句说明。');
await page.waitForTimeout(400);
await page.getByRole('button', { name: /保存草稿/ }).first().click();
await page.waitForTimeout(3000);
const dialogAfterDraft = await hasLeaveDialog();
check('点「保存草稿」后没有弹对话框', !dialogAfterDraft, '');
await page.getByRole('link', { name: '论坛' }).first().click().catch(async () => {
  await page.goto(`${UI}/forum`, { waitUntil: 'domcontentloaded' });
});
await page.waitForTimeout(2000);
const dialogAfterNav = await hasLeaveDialog();
check('保存草稿后再离开页面，也不该弹', !dialogAfterNav,
  dialogAfterNav ? await page.locator('.el-message-box').innerText() : '');

// ---------------------------------------------------------------------------
// ③ 删除帖子后跳回论坛：不该弹
// ---------------------------------------------------------------------------
await login();
const seed2 = runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models_forum import ForumBoard, Post',
  "admin = get_user_model().objects.get(username='admin')",
  "b = ForumBoard.objects.order_by('order','id').first()",
  "Post.objects.filter(title__startswith='zz存盘守卫删除').delete()",
  "p = Post.objects.create(title='zz存盘守卫删除：待删', content='<p>这篇待会儿删掉，够十个字。</p>', author=admin, board=b, status='published')",
  "print('ZZ_DEL=' + str(p.id))",
]);
const delId = /ZZ_DEL=(\d+)/.exec(seed2)?.[1];
await page.goto(`${UI}/forum/post/${delId}/edit`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.ql-editor', { timeout: 30_000 });
await page.waitForTimeout(2000);
await page.locator('.ql-editor').click();
await page.keyboard.type('先改一下再删（制造未保存状态）。');
await page.waitForTimeout(400);
await page.getByRole('button', { name: /删除帖子/ }).first().click();
await page.waitForSelector('.el-dialog', { timeout: 10_000 });
await page.locator('.el-dialog__footer button').filter({ hasText: /确认删除|删除/ }).first().click();
await page.waitForTimeout(3000);
const dialogAfterDelete = await hasLeaveDialog();
check('删除帖子后跳回论坛没有弹对话框', !dialogAfterDelete,
  dialogAfterDelete ? await page.locator('.el-message-box').innerText() : '');
check('删除后确实回到了论坛', page.url().includes('/forum'), page.url());

// ---------------------------------------------------------------------------
// ④ 反例：真有未保存修改时，守卫必须仍然工作
// ---------------------------------------------------------------------------
await page.goto(`${UI}/forum/post/${postId}/edit`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.ql-editor', { timeout: 30_000 });
await page.waitForTimeout(2500);
await titleInput.fill('zz存盘守卫：改了但不保存');
await page.waitForTimeout(400);
await page.getByRole('link', { name: '论坛' }).first().click();
await page.waitForTimeout(2000);
const dialogWhenReallyDirty = await hasLeaveDialog();
check('真有未保存修改时，仍然会拦（守卫没被改废）', dialogWhenReallyDirty,
  dialogWhenReallyDirty ? '' : '没拦，守卫失效了 ✗');
if (dialogWhenReallyDirty) {
  await page.locator('.el-message-box__btns button').filter({ hasText: /留在此页/ }).first().click();
  await page.waitForTimeout(800);
}

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
