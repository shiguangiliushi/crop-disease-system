/**
 * 作物名「桃」→「桃子」的界面核对（第 190 批）
 * ============================================================================
 * 这个改名要同时落三处，只看数据库不够：库里的 `crop_type`、前端的百科作物映射
 * （PestEncyclopediaView 的 cropTypeMap）、以及 i18n（home.cropPeach）。
 * 任何一处漏改，界面就会出现"桃子 / 桃"两种叫法并存 —— 这个脚本就是查这个。
 *
 * 覆盖：
 *   ① 百科页出现「桃子」（筛选下拉/列表），且不出现"裸的桃"（病害名「桃细菌性斑点病」除外）；
 *   ② 点「桃子」这个作物筛选，能筛出该作物的词条；
 *   ③ 「关于」页的作物清单显示「桃子」（读的是 i18n 的 home.cropPeach）。
 *
 * 用法：node scripts/verify-peach-crop-rename.mjs
 * 自己造账号、自己清（zzpeach_ 前缀）；**只读业务数据**，不改任何病害词条。
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzPeach!2026pw';
const userName = `zzpeach_user_${suffix}`;
const adminName = `zzpeach_admin_${suffix}`;

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
      'U = get_user_model()',
      "print('users deleted:', U.objects.filter(username__startswith='zzpeach_').delete()[0])",
    ]);
  } catch (error) { console.error('清理失败（忽略）:', error?.message || error); }
};
process.on('exit', cleanup);

clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'U = get_user_model()',
  `U.objects.create_user(username='${userName}', password='${password}', role='USER')`,
  // 管理端那两条（筛选 + 编辑弹窗的作物下拉）要管理员账号才能进
  `U.objects.create_user(username='${adminName}', password='${password}', is_staff=True, role='ADMIN')`,
  "print('seeded')",
]);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 }, locale: 'zh-CN' });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)));

await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('input[type="password"]', { timeout: 30_000 });
await page.locator('input#username, input[type="text"]').first().fill(userName);
await page.locator('input[type="password"]').first().fill(password);
await page.locator('button[type="submit"]').first().click();
await page.waitForTimeout(3500);
check('临时账号登录成功', !page.url().includes('/login'), page.url().replace(UI, ''));

// ---------------------------------------------------------------------------
// ① 百科页：出现「桃子」，不出现裸的「桃」
// ---------------------------------------------------------------------------
console.log('\n--- ① 百科页 ---');
await page.goto(`${UI}/pests`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3500);
let pageText = await page.locator('body').innerText();
check('百科页出现「桃子」', pageText.includes('桃子'), pageText.replace(/\s+/g, ' ').slice(0, 70));

// "裸的桃" = 一个**独立的**「桃」，不是「桃子」的一部分、前面不是「樱」、也不属于病害名
//
// ⚠️ 四个陷阱（前三版全踩了，所以这里逐条写清楚）：
//   ① 「樱桃」里含一个「桃」字 —— 必须排除，否则永远误报；
//   ② 「桃细菌性斑点病」是**病害名**（PlantVillage 的写法，不带"子"），本批**不改**它；
//   ③ 百科的作物筛选是**竖排**的，`body.innerText` 里「桃子」被拆成 `\n桃` + `子` ——
//      所以不能用 `(^|[^樱子])桃` 这种"看前一个字符"的写法；
//   ④ **占位符本身不能含「桃」**：第一版把「桃子」换成 `【桃子】` 再去 match(/桃/)，
//      占位符里的那个「桃」又被自己命中 —— 永远失败。占位符必须是不含该字的记号。
//   ⑤ 报"命中位置"时要用**替换后**的文本去截上下文：直接拿原文 indexOf 会量到
//      另一个位置（命中 `\n桃` 时尤其明显），给出的上下文牛头不对马嘴、没法排查。
const scanNakedPeach = (text) => {
  const cleaned = text
    .replace(/桃子/g, '[PEACH]')
    .replace(/桃细菌性斑点病/g, '[PEACH-DISEASE]');
  const hits = [...cleaned.matchAll(/桃/g)];
  // ⚠️ 只把**不是**「樱桃」的那一处算作命中：樱桃是另一个作物，它的名字里天然带「桃」。
  //    逐个看命中的**前一个字**（不能像第一版那样先做整篇正则替换 —— 那会把换行也当成
  //    前一个字符，于是竖排的作物筛选 `\n桃子` 被误判成"裸桃"）。
  const naked = hits.filter((m) => cleaned[m.index - 1] !== '樱');
  return naked.length
    ? {
        count: naked.length,
        context: naked.slice(0, 4).map((m) => cleaned.slice(Math.max(0, m.index - 18), m.index + 12)),
      }
    : { count: 0, context: [] };
};
const nakedOnPests = scanNakedPeach(pageText);
// 排查用：把扫描结果原样打出来（含命中数与每处上下文），别只靠断言消息
console.log('   [debug] 裸桃扫描结果:', JSON.stringify(nakedOnPests));
check('百科页没有裸的「桃」（桃子/樱桃/病害名都不算）',
  nakedOnPests.count === 0,
  nakedOnPests ? `命中 ${nakedOnPests.count} 处：…${nakedOnPests.context.join(' ｜ ')}…` : '');

// ---------------------------------------------------------------------------
// ② 点「桃子」筛选
// ---------------------------------------------------------------------------
console.log('\n--- ② 按「桃子」筛选 ---');
const peachFilter = page.locator('button, .el-check-tag, .crop-item, .filter-chip, li, span')
  .filter({ hasText: /^桃子$/ }).first();
if (await peachFilter.count()) {
  await peachFilter.click();
  await page.waitForTimeout(3000);
  // ⚠️ 只断言**可见的**词条卡片：百科是 3×2 网格，整页文本里还留着被隐藏的卡片
  //    （第一版拿 body.innerText 断言，结果"筛选后仍看到苹果"是假失败）
  const visibleCards = await page.locator('.pest-card:visible, .pest-item:visible, .wiki-card:visible')
    .allInnerTexts().catch(() => []);
  const visibleText = visibleCards.join(' | ');
  check('筛选后能看到该作物的词条（桃细菌性斑点病 / 健康桃）',
    visibleText.includes('桃细菌性斑点病') || visibleText.includes('健康桃'),
    visibleText.replace(/\s+/g, ' ').slice(0, 90) || '（没抓到可见卡片，选择器可能变了）');
  check('筛选后可见卡片里没有别的作物（苹果）', !visibleText.includes('苹果'),
    visibleText.includes('苹果') ? visibleText.replace(/\s+/g, ' ').slice(0, 90) : '');
} else {
  // 筛选控件结构可能变了：退化为"页面上有桃子"的断言，并如实说明
  check('找到可点击的「桃子」筛选项', false, '控件选择器没命中（页面结构可能已变）');
}

// ---------------------------------------------------------------------------
// ③ 关于页的作物清单（i18n home.cropPeach）
// ---------------------------------------------------------------------------
console.log('\n--- ③ 关于页作物清单 ---');
await page.goto(`${UI}/about`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2500);
const aboutText = await page.locator('body').innerText();
check('关于页显示「桃子」', aboutText.includes('桃子'), aboutText.replace(/\s+/g, ' ').slice(0, 60));
const nakedOnAbout = scanNakedPeach(aboutText);
check('关于页没有裸的「桃」（桃子/樱桃/病害名都不算）', nakedOnAbout.count === 0,
  nakedOnAbout.count ? `命中 ${nakedOnAbout.count} 处：…${nakedOnAbout.context.join(' ｜ ')}…` : '');

// ---------------------------------------------------------------------------
// ④ 管理端「病害百科维护」：按作物筛选不该串味（用户报的那条）
// ---------------------------------------------------------------------------
console.log('\n--- ④ 管理端按作物筛选（桃子 vs 樱桃）---');
clearThrottle();
const adminCtx = await browser.newContext({ viewport: { width: 1500, height: 950 }, locale: 'zh-CN' });
const adminPage = await adminCtx.newPage();
const adminErrors = [];
adminPage.on('pageerror', (e) => adminErrors.push(String(e).slice(0, 200)));

await adminPage.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
await adminPage.waitForSelector('.admin-login', { timeout: 30_000 });
await adminPage.locator('#username').fill(adminName);
await adminPage.locator('#password').fill(password);
await adminPage.locator('button[type="submit"]').first().click();
await adminPage.waitForURL((u) => u.pathname.startsWith('/admin/') && u.pathname !== '/admin/login', { timeout: 30_000 });
await adminPage.waitForSelector('.admin-console', { timeout: 25_000 });

await adminPage.goto(`${UI}/admin/pests`, { waitUntil: 'domcontentloaded' });
await adminPage.waitForTimeout(3500);

/** 选一个作物并返回列表里可见的病害名 */
const filterByCrop = async (crop) => {
  await adminPage.goto(`${UI}/admin/pests`, { waitUntil: 'domcontentloaded' });
  await adminPage.waitForTimeout(2500);
  await adminPage.locator('.filter-bar .el-select, .el-select').first().click();
  await adminPage.waitForTimeout(600);
  await adminPage.locator('.el-select-dropdown__item:visible', { hasText: crop }).first().click();
  await adminPage.waitForTimeout(2500);
  const rows = await adminPage.locator('.el-table__row').allInnerTexts();
  return rows.map((t) => t.replace(/\s+/g, ' ').trim());
};

const peachRows = (await filterByCrop('桃子')).join(' ｜ ');
check('管理端筛「桃子」只剩该作物的词条',
  peachRows.includes('桃细菌性斑点病') && peachRows.includes('健康桃'), peachRows.slice(0, 100));
check('管理端筛「桃子」**不再**出现樱桃白粉病（用户报的串味）',
  !peachRows.includes('樱桃'), peachRows.includes('樱桃') ? peachRows.slice(0, 120) : '');

const cherryRows = (await filterByCrop('樱桃')).join(' ｜ ');
check('管理端筛「樱桃」只剩该作物的词条',
  cherryRows.includes('樱桃白粉病') && !cherryRows.includes('桃细菌性斑点病'),
  cherryRows.slice(0, 100));

// 编辑弹窗的作物下拉：第 190 批把 cropOptions 从字符串数组改成了 {key,label}，
// 忘了同步改弹窗就会显示成 [object Object] —— 这条专门盯它
await adminPage.goto(`${UI}/admin/pests`, { waitUntil: 'domcontentloaded' });
await adminPage.waitForTimeout(2500);
await adminPage.locator('.el-table__row button', { hasText: '编辑' }).first().click();
await adminPage.waitForSelector('.el-dialog:visible', { timeout: 15_000 });
await adminPage.waitForTimeout(1200);
const dialogText = await adminPage.locator('.el-dialog:visible').innerText();
check('编辑弹窗的作物下拉没有显示成 [object Object]',
  !dialogText.includes('[object Object]'), dialogText.replace(/\s+/g, ' ').slice(0, 80));
check('管理端全程无 JS 报错', adminErrors.length === 0, adminErrors.slice(0, 2).join(' | '));
await adminCtx.close();

check('全程无 JS 报错', errors.length === 0, errors.slice(0, 2).join(' | '));

await page.screenshot({ path: 'dsh-shots/peach-rename-check.png', clip: { x: 0, y: 0, width: 1440, height: 950 } });
await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
