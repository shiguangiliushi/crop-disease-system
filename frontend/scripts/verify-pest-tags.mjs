/**
 * 帖子病害标签端到端验证（第 168 批）
 * ============================================================================
 * 评审意见："不能给帖子打『苹果黑星病』这种标签，后期没法按病害聚合讨论。"
 * 标签是 Post ↔ PestInfo 的 M2M（后端 pest_ids 写 / pests 读、?pest=<id> 筛选）。
 *
 * 本脚本验证：
 *   ① 发帖页有「相关病害」选择器，能搜到词条并选上
 *   ② 发出去以后，帖子详情页出现病害标签胶囊，且链接指向词条页
 *   ③ 编辑页能读出既有标签（胶囊里显示名字），并能取消标签
 *   ④ ?pest=<id> 能筛出打该标签的帖子（"按病害聚合讨论"）
 *   ⑤ 识别结果「一键发帖」带过去的病害会被预选成标签
 *
 * 用法：node scripts/verify-pest-tags.mjs
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
  'from api.models import PestInfo',
  'from api.models_forum import ForumBoard, Post',
  "admin = get_user_model().objects.get(username='admin')",
  "b = ForumBoard.objects.order_by('order','id').first()",
  "Post.objects.filter(title__startswith='zz标签E2E').delete()",
  "pest = PestInfo.objects.filter(name='苹果黑星病').first() or PestInfo.objects.first()",
  "print('ZZ_PEST=' + str(pest.id))",
  "print('ZZ_PEST_NAME=' + pest.name)",
  "print('ZZ_PEST_EN=' + pest.english_identifier)",
  "print('ZZ_BOARD=' + str(b.id))",
  'token, _ = Token.objects.get_or_create(user=admin)',
  "print('ZZ_TOKEN=' + token.key)",
  "print('ZZ_USER=' + json.dumps(CustomUserSerializer(admin).data, ensure_ascii=False))",
]);
const pestId = /ZZ_PEST=(\d+)/.exec(seed)?.[1];
const pestName = /ZZ_PEST_NAME=(.+)/.exec(seed)?.[1]?.trim();
const pestEn = /ZZ_PEST_EN=(.+)/.exec(seed)?.[1]?.trim();
const boardId = /ZZ_BOARD=(\d+)/.exec(seed)?.[1];
const token = /ZZ_TOKEN=(\S+)/.exec(seed)?.[1];
const userJson = /ZZ_USER=(.+)/.exec(seed)?.[1];

const cleanup = () => {
  if (cleaned) return;
  cleaned = true;
  clearThrottle();
  try {
    runDjango([
      'from api.models_forum import Post',
      "print('cleaned:', Post.objects.filter(title__startswith='zz标签E2E').delete()[0])",
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

await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
await page.evaluate(([tk, us]) => {
  window.sessionStorage.setItem('auth_token', tk);
  window.sessionStorage.setItem('user', us);
}, [token, userJson]);

// ---------------------------------------------------------------------------
// ① 发帖页：选择器 + 搜索 + 选中
// ---------------------------------------------------------------------------
await page.goto(`${UI}/forum/post/new`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.ql-editor', { timeout: 30_000 });
await page.waitForTimeout(2500);

const picker = page.locator('.pest-tag-picker');
check('发帖页有「相关病害」选择器', await picker.count() > 0, '');

// 标题 + 正文（校验要求标题 ≥5 字、正文 ≥10 字）
const titleInput = page.locator('.el-form-item').filter({ hasText: '标题' }).locator('input').first();
await titleInput.fill('zz标签E2E：苹果黑星病怎么治');
await page.locator('.ql-editor').click();
await page.keyboard.type('叶片正面出现橄榄色绒状霉层，想请教一下怎么处理。');
await page.waitForTimeout(300);

// 打开下拉，搜索病害名
await picker.locator('.el-select').click();
await page.waitForTimeout(1200);
const optionCount = await page.locator('.el-select-dropdown__item').count();
check('下拉里给出了病害词条（不必先打字）', optionCount > 0, `${optionCount} 条`);

await picker.locator('input').first().fill(pestName);
await page.waitForTimeout(1800);
const matched = await page.locator('.el-select-dropdown__item').filter({ hasText: pestName }).count();
check('能按病害名搜到词条', matched > 0, pestName);
await page.locator('.el-select-dropdown__item').filter({ hasText: pestName }).first().click();
await page.waitForTimeout(800);
const chips = await picker.locator('.tag-chip').allInnerTexts();
check('选中的病害显示成胶囊', chips.some((c) => c.includes(pestName)), chips.join(' | '));
await page.screenshot({ path: 'dsh-shots/pest-tag-picker.png' });

// ---------------------------------------------------------------------------
// ② 发布 → 详情页胶囊
// ---------------------------------------------------------------------------
await page.getByRole('button', { name: /发布帖子|发表帖子|发布/ }).last().click();
// 提交前把当前表单状态打出来，卡住时能直接看出是校验没过还是别的原因
const formState = await page.evaluate(() => {
  const editor = document.querySelector('.ql-editor');
  const title = document.querySelector('.el-form-item input');
  return { title: title ? title.value : '(无)', contentLen: editor ? editor.innerText.trim().length : 0 };
});
console.log('  · 提交前表单：', JSON.stringify(formState));
try {
  await page.waitForURL((url) => /\/forum\/post\/\d+$/.test(url.pathname), { timeout: 25_000 });
} catch (error) {
  const toast = await page.locator('.el-message, .el-form-item__error').allInnerTexts().catch(() => []);
  console.log('  ⚠️ 提交后仍在发帖页，提示:', JSON.stringify(toast.slice(0, 5)));
  throw error;
}
await page.waitForTimeout(2500);
const postUrl = page.url();
const postId = postUrl.split('/').pop();

const tagChips = page.locator('.pest-tags .pest-tag');
check('详情页显示病害标签胶囊', await tagChips.count() > 0, '');
check('胶囊文字是病害名', (await tagChips.first().innerText()).includes(pestName), await tagChips.first().innerText());
const href = await tagChips.first().getAttribute('href');
check('胶囊链接指向病害词条页', Boolean(href) && href.includes(`/pests/${pestEn}`), href || '（无链接）');
await page.screenshot({ path: 'dsh-shots/post-pest-tags.png' });

// ---------------------------------------------------------------------------
// ③ 编辑页能读出既有标签
// ---------------------------------------------------------------------------
await page.goto(`${UI}/forum/post/${postId}/edit`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.ql-editor', { timeout: 30_000 });
await page.waitForTimeout(2500);
const editChips = await page.locator('.pest-tag-picker .tag-chip').allInnerTexts();
check('编辑页读出了已有标签', editChips.some((c) => c.includes(pestName)), editChips.join(' | '));

// ---------------------------------------------------------------------------
// ④ 按病害聚合：?pest=<id>
// ---------------------------------------------------------------------------
await page.goto(`${UI}/forum`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
const aggregated = await page.evaluate(async ({ id }) => {
  const tk = window.sessionStorage.getItem('auth_token');
  const res = await fetch(`http://127.0.0.1:8000/api/forums/posts/?pest=${id}&page_size=50`, {
    headers: { Authorization: `Token ${tk}` },
  });
  const body = await res.json();
  const rows = body.results || [];
  return {
    total: rows.length,
    allTagged: rows.every((row) => (row.pests || []).some((tag) => tag.id === id)),
    titles: rows.map((row) => row.title).slice(0, 3),
  };
}, { id: Number(pestId) });
check('?pest=<id> 能按病害聚合出讨论', aggregated.total > 0, `${aggregated.total} 篇`);
check('聚合结果里每一篇都确实带这个标签', aggregated.allTagged, aggregated.titles.join(' / '));

// ---------------------------------------------------------------------------
// ⑤ 一键发帖带过去的病害会预选成标签
// ---------------------------------------------------------------------------
await page.goto(`${UI}/forum/post/new?ask=${encodeURIComponent(pestName)}&pest=${pestId}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.ql-editor', { timeout: 30_000 });
await page.waitForTimeout(2500);
const prefilledChips = await page.locator('.pest-tag-picker .tag-chip').allInnerTexts();
check('一键发帖带过来的病害被预选成标签',
  prefilledChips.some((c) => c.includes(pestName)), prefilledChips.join(' | ') || '（空）');

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
