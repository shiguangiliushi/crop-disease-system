/**
 * 「识别结果 → 一键发帖求助」端到端验证（第 167 批）
 * ============================================================================
 * 农户识别出病害后最常见的下一步是"问问别人怎么治"。以前要：
 *   记住病名 → 切到发帖页 → 手打一遍 → 再自己把照片传一次。
 * 现在识别结果页有一个「发帖求助」按钮，点一下把病名 / 识别图片 / 症状带进发帖页预填。
 *
 * 本脚本验证：
 *   ① 识别结果页有「发帖求助」按钮（健康叶片时不出现 —— 那时没什么可求助的）
 *   ② 点它跳到发帖页，标题与正文被预填（含病名、识别图片 <img>、症状、提问）
 *   ③ 预填**不会**覆盖用户已经写好的内容
 *   ④ 真的能发出去，详情页能看到病名与图片
 *
 * 用法：node scripts/verify-ask-forum.mjs
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
  "Post.objects.filter(title__startswith='【求助】').delete()",
  'token, _ = Token.objects.get_or_create(user=admin)',
  "print('ZZ_TOKEN=' + token.key)",
  "print('ZZ_USER=' + json.dumps(CustomUserSerializer(admin).data, ensure_ascii=False))",
]);
const token = /ZZ_TOKEN=(\S+)/.exec(seed)?.[1];
const userJson = /ZZ_USER=(.+)/.exec(seed)?.[1];

const cleanup = () => {
  if (cleaned) return;
  cleaned = true;
  clearThrottle();
  try {
    runDjango([
      'from api.models_forum import Post',
      "print('cleaned:', Post.objects.filter(title__startswith='【求助】').delete()[0])",
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
// ① 直接带着识别结果访问识别页（结果存在 sessionStorage 里，第 74 批的跨刷新保留）
// ---------------------------------------------------------------------------
await page.goto(`${UI}/detect`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
await page.evaluate(() => {
  // 造一份"识别结果"（结构与 DetectView 读取的一致）
  const result = {
    diseases: [{
      id: 991,
      name: '苹果黑星病',
      name_en: 'Apple scab',
      confidence: 0.93,
      symptoms: '叶片正面出现橄榄色至黑色的绒状霉层，后期叶片扭曲。',
      prevention: '<p>清除病叶；花期前后喷施保护性杀菌剂。</p>',
    }],
    healthy: false,
    originalImage: 'http://127.0.0.1:8000/media/detections/zz_ask_original.jpg',
    annotatedImage: 'http://127.0.0.1:8000/media/detections/zz_ask_annotated.jpg',
    historyId: 999999,
    // ⚠️ restoreResult 有新鲜度校验（超过 2 小时就丢弃，第 74 批）：
    // 不写 savedAt 会被当成过期结果直接删掉，结果区根本不渲染 —— 第一版就是漏了它。
    timestamp: new Date().toISOString(),
    savedAt: Date.now(),
  };
  window.sessionStorage.setItem('detect_last_result', JSON.stringify(result));
});
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2500);

const askButton = page.getByRole('button', { name: /发帖求助/ });
check('识别结果页有「发帖求助」按钮', await askButton.count() > 0, '');
await page.screenshot({ path: 'dsh-shots/detect-ask-forum.png' });

// ---------------------------------------------------------------------------
// ② 点击 → 发帖页预填
// ---------------------------------------------------------------------------
await askButton.first().click();
await page.waitForURL((url) => url.pathname.includes('/forum/post/new'), { timeout: 20_000 });
await page.waitForSelector('.ql-editor', { timeout: 30_000 });
await page.waitForTimeout(2500);

// ⚠️ 不能用 input.first() —— 页面第一个 input 是版块下拉，取到的是空串
const titleValue = await page
  .locator('.el-form-item')
  .filter({ hasText: '标题' })
  .locator('input')
  .first()
  .inputValue()
  .catch(() => '');
const editorHtml = await page.locator('.ql-editor').innerHTML();
check('标题预填了病名', /苹果黑星病/.test(titleValue), titleValue);
check('正文预填了识别图片（<img> 指向 /media）',
  /<img[^>]+src="[^"]*zz_ask_(annotated|original)\.jpg/.test(editorHtml), editorHtml.slice(0, 120));
check('正文预填了症状', /绒状霉层|症状/.test(editorHtml), '');
check('正文预填了提问', /怎么处理|谢谢/.test(editorHtml), '');
check('正文里用的是识别图的服务器地址（不是 base64）',
  !editorHtml.includes('base64'), '');
await page.screenshot({ path: 'dsh-shots/ask-forum-prefill.png' });

// ---------------------------------------------------------------------------
// ③ 预填不覆盖已写内容
// ---------------------------------------------------------------------------
await page.goto(`${UI}/forum/post/new?ask=测试病`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.ql-editor', { timeout: 30_000 });
await page.waitForTimeout(2000);
const prefilledWithParam = await page.locator('.ql-editor').innerText();
check('带 ask 参数打开时会预填', /测试病/.test(prefilledWithParam), prefilledWithParam.slice(0, 50));

// 用户已经写过的内容（localStorage 草稿）优先，不被覆盖
await page.evaluate(() => {
  window.localStorage.setItem('post_draft_new', JSON.stringify({
    title: '我自己已经写好的标题', content: '<p>我自己写的正文</p>', board: '',
  }));
});
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForSelector('.ql-editor', { timeout: 30_000 });
await page.waitForTimeout(2000);
// ⚠️ maybeRestoreDraft 会先弹一个"是否恢复草稿"的确认框 —— 不点它，内容就一直没恢复
const restoreBtn = page.locator('.el-message-box__btns button').filter({ hasText: /恢复/ });
if (await restoreBtn.count()) {
  await restoreBtn.first().click();
  await page.waitForTimeout(1500);
}
const restored = await page.locator('.ql-editor').innerText();
check('已有本地草稿时不会被预填覆盖', /我自己写的正文/.test(restored), restored.slice(0, 50));
await page.evaluate(() => window.localStorage.removeItem('post_draft_new'));

// ---------------------------------------------------------------------------
// ④ 真发出去
// ---------------------------------------------------------------------------
await page.goto(`${UI}/forum/post/new?ask=苹果黑星病&image=http://127.0.0.1:8000/media/detections/zz_ask_annotated.jpg`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.ql-editor', { timeout: 30_000 });
await page.waitForTimeout(2500);
await page.getByRole('button', { name: /发布帖子|发表帖子|发布/ }).last().click();
await page.waitForTimeout(4500);
if (page.url().includes('/forum/post/new')) {
  // 提交没走成：把页面上的提示/报错打出来，方便定位原因
  const toast = await page.locator('.el-message, .el-form-item__error').allInnerTexts().catch(() => []);
  console.log('  ⚠️ 提交后仍在发帖页，页面提示:', JSON.stringify(toast.slice(0, 4)));
}
const afterSubmit = page.url();
check('提交后离开了发帖页', !afterSubmit.includes('/forum/post/new'), afterSubmit);
// 第 167 批修掉的坑：发布成功后守卫仍会弹"有未保存的修改"（因为它在离开时重新判定），
// 用户点「留下」就停在可重复提交的表单上 → 重复发帖。这里确认那个框不再出现。
const leaveDialog = await page.locator('.el-message-box').count();
check('发布成功后不再弹「有未保存的修改」', leaveDialog === 0, leaveDialog ? '仍然弹了' : '');
const detailText = await page.locator('body').innerText();
check('详情页能看到病名', /苹果黑星病/.test(detailText), '');
check('详情页渲染了识别图片', (await page.locator('.post-content img, article img, img').count()) > 0, '');

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
