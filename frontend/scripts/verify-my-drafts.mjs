/**
 * 「我的草稿」端到端验证（第 166 批）
 * ============================================================================
 * 自动保存会把草稿存到**服务端**（`status='draft'`），但在此之前前端没有入口能看到它们 ——
 * 农户写到一半关掉页面，那条半成品就永远躺在库里。这个脚本验证新加的草稿箱：
 *
 *   ① 论坛页有「我的草稿」入口，且角标数量正确
 *   ② 草稿页列出草稿：标题、摘要、更新时间为空时不留空白、字数
 *   ③ 「继续编辑」跳到编辑页，且正文能读出来（不能是空框）
 *   ④ 「丢弃」走确认 → 删除 → 从列表消失
 *   ⑤ 已发布的帖子**不会**出现在草稿页
 *   ⑥ 别人的草稿看不到（用另一个账号登录，草稿页应为空）
 *
 * 用法：node scripts/verify-my-drafts.mjs
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

clearThrottle();
const seed = runDjango([
  'import json',
  'from django.contrib.auth import get_user_model',
  'from rest_framework.authtoken.models import Token',
  'from api.serializers import CustomUserSerializer',
  'from api.models_forum import ForumBoard, Post',
  "admin = get_user_model().objects.get(username='admin')",
  "other = get_user_model().objects.filter(username='zz_draft_e2e_other').first()",
  "if not other:",
  "    other = get_user_model().objects.create_user(username='zz_draft_e2e_other', password='ZzE2e!2026pw', role='USER')",
  "board = ForumBoard.objects.order_by('order', 'id').first()",
  "Post.objects.filter(title__startswith='zz草稿E2E').delete()",
  "d1 = Post.objects.create(title='zz草稿E2E：高架草莓叶片白点求助', content='<p>叶片背面有密集白色小点，还没写完…</p>', author=admin, board=board, status='draft')",
  "p1 = Post.objects.create(title='zz草稿E2E：已经发出来的帖子', content='<p>这篇是发布的，不该出现在草稿箱。</p>', author=admin, board=board, status='published')",
  "d2 = Post.objects.create(title='zz草稿E2E：别人的草稿', content='<p>这是另一个账号的草稿。</p>', author=other, board=board, status='draft')",
  'token, _ = Token.objects.get_or_create(user=admin)',
  'token2, _ = Token.objects.get_or_create(user=other)',
  "print('ZZ_DRAFT=' + str(d1.id))",
  "print('ZZ_PUB=' + str(p1.id))",
  "print('ZZ_OTHER_DRAFT=' + str(d2.id))",
  "print('ZZ_TOKEN=' + token.key)",
  "print('ZZ_TOKEN2=' + token2.key)",
  "print('ZZ_USER=' + json.dumps(CustomUserSerializer(admin).data, ensure_ascii=False))",
  "print('ZZ_USER2=' + json.dumps(CustomUserSerializer(other).data, ensure_ascii=False))",
]);
const draftId = /ZZ_DRAFT=(\d+)/.exec(seed)?.[1];
const pubId = /ZZ_PUB=(\d+)/.exec(seed)?.[1];
const token = /ZZ_TOKEN=(\S+)/.exec(seed)?.[1];
const token2 = /ZZ_TOKEN2=(\S+)/.exec(seed)?.[1];
const userJson = /ZZ_USER=(.+)/.exec(seed)?.[1];
const userJson2 = /ZZ_USER2=(.+)/.exec(seed)?.[1];
if (!draftId || !pubId || !token || !token2) {
  console.error('❌ 造数据失败：', seed);
  process.exit(1);
}

const cleanup = () => {
  if (cleaned) return;
  cleaned = true;
  clearThrottle();
  try {
    runDjango([
      'from api.models_forum import Post',
      'from django.contrib.auth import get_user_model',
      "print('cleaned posts:', Post.objects.filter(title__startswith='zz草稿E2E').delete()[0])",
      "print('cleaned user:', get_user_model().objects.filter(username='zz_draft_e2e_other').delete()[0])",
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

const loginWith = async (target, tokenValue, userValue) => {
  await target.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
  await target.evaluate(([tk, us]) => {
    window.sessionStorage.setItem('auth_token', tk);
    window.sessionStorage.setItem('user', us);
  }, [tokenValue, userValue]);
};

await loginWith(page, token, userJson);

// ---------------------------------------------------------------------------
// ① 论坛页入口与角标
// ---------------------------------------------------------------------------
await page.goto(`${UI}/forum`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.admin-hero-actions', { timeout: 30_000 });
await page.waitForTimeout(2500);
const forumText = await page.locator('.admin-hero-actions').innerText();
check('论坛页有「我的草稿」入口', forumText.includes('我的草稿'), forumText.replace(/\s+/g, ' '));
const badge = await page.locator('.drafts-badge').first().innerText().catch(() => '');
check('草稿角标显示数量 1', badge.trim() === '1', `角标=${badge.trim() || '（无）'}`);

// ---------------------------------------------------------------------------
// ② 草稿页列表
// ---------------------------------------------------------------------------
await page.locator('.admin-hero-actions').getByText('我的草稿').click();
await page.waitForURL((url) => url.pathname.includes('/forum/drafts'), { timeout: 20_000 });
await page.waitForSelector('.draft-list, .el-empty', { timeout: 20_000 });
await page.waitForTimeout(1200);
await page.screenshot({ path: 'dsh-shots/my-drafts.png' });

const draftText = await page.locator('.drafts-page').innerText();
check('草稿页列出了我的草稿', draftText.includes('zz草稿E2E：高架草莓叶片白点求助'), '');
check('草稿页显示内容摘要', draftText.includes('还没写完'), '');
check('草稿页显示更新时间与字数', /更新/.test(draftText) && /字/.test(draftText), '');
check('已发布的帖子不在草稿页', !draftText.includes('已经发出来的帖子'), '');
check('别人的草稿不在我的草稿页', !draftText.includes('别人的草稿'), '');
check('只有一条草稿', (await page.locator('.draft-item').count()) === 1,
  `${await page.locator('.draft-item').count()} 条`);

// ---------------------------------------------------------------------------
// ③ 继续编辑
// ---------------------------------------------------------------------------
await page.getByRole('button', { name: /继续编辑/ }).first().click();
await page.waitForURL((url) => url.pathname.includes(`/forum/post/${draftId}/edit`), { timeout: 20_000 });
await page.waitForSelector('.ql-editor', { timeout: 30_000 });
await page.waitForTimeout(1800);
const editorHtml = await page.locator('.ql-editor').innerHTML();
check('编辑器里读出了草稿正文（不是空框）', editorHtml.includes('白色小点'), editorHtml.slice(0, 70));
await page.screenshot({ path: 'dsh-shots/draft-continue.png' });

// ---------------------------------------------------------------------------
// ④ 丢弃草稿
// ---------------------------------------------------------------------------
await page.goto(`${UI}/forum/drafts`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.draft-item', { timeout: 20_000 });
await page.getByRole('button', { name: /丢弃/ }).first().click();
await page.waitForSelector('.el-message-box', { timeout: 10_000 });
await page.waitForTimeout(400);
const confirmText = await page.locator('.el-message-box').innerText();
check('丢弃前有确认（写明无法恢复）', /无法恢复/.test(confirmText), confirmText.replace(/\s+/g, ' ').slice(0, 70));
// ⚠️ 确认按钮的文案是「丢弃」（代码里自定义了 confirmButtonText），不是默认的"确定"
await page.locator('.el-message-box__btns button').filter({ hasText: /丢弃/ }).first().click();
await page.waitForTimeout(2500);
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2000);
const afterDiscard = await page.locator('.drafts-page').innerText();
check('丢弃后草稿从列表消失', !afterDiscard.includes('zz草稿E2E：高架草莓'), afterDiscard.replace(/\s+/g, ' ').slice(0, 60));
check('列表清空后显示空状态', (await page.locator('.el-empty').count()) > 0, '');

// ---------------------------------------------------------------------------
// ⑤ 别人的草稿：看不到
// ---------------------------------------------------------------------------
const otherPage = await (await browser.newContext({ viewport: { width: 1440, height: 950 }, locale: 'zh-CN' })).newPage();
await loginWith(otherPage, token2, userJson2);
await otherPage.goto(`${UI}/forum/drafts`, { waitUntil: 'domcontentloaded' });
await otherPage.waitForTimeout(3000);
const otherText = await otherPage.locator('.drafts-page').innerText();
check('另一个账号看不到 admin 的草稿', !otherText.includes('高架草莓'), otherText.replace(/\s+/g, ' ').slice(0, 70));
check('另一个账号只看到自己的草稿', otherText.includes('别人的草稿'), '');
await otherPage.close();

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
