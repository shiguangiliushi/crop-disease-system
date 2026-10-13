/**
 * 控制台「识别记录」端到端验证（第 172 批）
 * ============================================================================
 * 农户每识别一次落一条 DetectionHistory，此前**只有农户自己**能在「历史记录」看到；
 * 管理员想抽查识别质量只能去 Django admin 翻表。这一页是跨用户的全局视图。
 *
 * 本脚本验证：
 *   ① 侧栏有「识别记录」入口，点进去是管理页（不再是重定向到农户端 /history）
 *   ② 列表显示：缩略图 / 用户 / 结果 / 置信度 / 时间
 *   ③ 筛选「只看未匹配词条」生效，**且顶部统计跟着筛选走**
 *   ④ 搜索能按用户名/结果过滤
 *   ⑤ 点行打开详情（原图 + 标注图 + 词条链接）
 *   ⑥ 删除：确认后行消失（不可逆，仅全权管理员）
 *   ⑦ 内容编辑员**看不到**这个入口（识别记录属于用户数据，不是内容）
 *
 * 用法：node scripts/verify-admin-detections.mjs
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
  'from api.models import PestInfo, DetectionHistory, EditorModuleGrant',
  'U = get_user_model()',
  "admin = U.objects.get(username='admin')",
  "plain = U.objects.filter(username='zz_detE2E_user').first()",
  "if not plain:",
  "    plain = U.objects.create_user(username='zz_detE2E_user', password='ZzE2e!2026pw', role='USER')",
  "editor = U.objects.filter(username='zz_detE2E_editor').first()",
  "if not editor:",
  "    editor = U.objects.create_user(username='zz_detE2E_editor', password='ZzE2e!2026pw', role='EDITOR')",
  "    EditorModuleGrant.objects.get_or_create(user=editor, module='review')",
  "pest = PestInfo.objects.filter(name='苹果黑星病').first() or PestInfo.objects.first()",
  "DetectionHistory.objects.filter(detection_result__startswith='zz识别记录E2E').delete()",
  "a = DetectionHistory.objects.create(user=plain, detection_result='zz识别记录E2E-已匹配', confidence=0.93, pest_info=pest)",
  "b = DetectionHistory.objects.create(user=plain, detection_result='zz识别记录E2E-未匹配', confidence=0.55, pest_info=None)",
  "ta, _ = Token.objects.get_or_create(user=admin)",
  "te, _ = Token.objects.get_or_create(user=editor)",
  "print('ZZ_TOKEN=' + ta.key)",
  "print('ZZ_TOKEN_EDITOR=' + te.key)",
  "print('ZZ_USER=' + json.dumps(CustomUserSerializer(admin).data, ensure_ascii=False))",
  "print('ZZ_USER_EDITOR=' + json.dumps(CustomUserSerializer(editor).data, ensure_ascii=False))",
  "print('ZZ_UNMATCHED_ID=' + str(b.id))",
]);
const token = /ZZ_TOKEN=(\S+)/.exec(seed)?.[1];
const tokenEditor = /ZZ_TOKEN_EDITOR=(\S+)/.exec(seed)?.[1];
const userJson = /ZZ_USER=(.+)/.exec(seed)?.[1];
const userJsonEditor = /ZZ_USER_EDITOR=(.+)/.exec(seed)?.[1];
const unmatchedId = /ZZ_UNMATCHED_ID=(\d+)/.exec(seed)?.[1];

const cleanup = () => {
  if (cleaned) return;
  cleaned = true;
  clearThrottle();
  try {
    runDjango([
      'from django.contrib.auth import get_user_model',
      'from api.models import DetectionHistory',
      "print('cleaned rows:', DetectionHistory.objects.filter(detection_result__startswith='zz识别记录E2E').delete()[0])",
      "print('cleaned users:', get_user_model().objects.filter(username__startswith='zz_detE2E_').delete()[0])",
    ]);
  } catch (error) {
    console.error('清理失败（忽略）:', error?.message || error);
  }
};
process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });


/** 读顶部「记录总数」磁贴的数字（页面自己算的，与列表同源） */
const readTotal = async () => Number(
  ((await page.locator('.stat-tile').first().innerText()).match(/\d+/) || ['0'])[0],
);

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1500, height: 950 }, locale: 'zh-CN' })).newPage();
const pageErrors = [];
page.on('pageerror', (error) => pageErrors.push(String(error).slice(0, 200)));

const login = async (target, tk, us) => {
  await target.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
  await target.evaluate(([t1, u1]) => {
    window.sessionStorage.setItem('auth_token', t1);
    window.sessionStorage.setItem('user', u1);
  }, [tk, us]);
};

await login(page, token, userJson);

// ---------------------------------------------------------------------------
// ① 侧栏入口 → 管理页（不再是跳到农户端历史记录）
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/dashboard`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.admin-sidebar, .admin-console, aside', { timeout: 30_000 });
await page.waitForTimeout(2000);
// ⚠️ 第 184 批：侧栏不再单列「识别记录」——它成了「用户管理」页的**第二个页签**
//    （`/admin/users?tab=detections`）。原来这里查的是整页 `body.innerText`，
//    连"页内页签/其它区块"里的字都会算进去（查文案必然假绿）；改成**按 href 精确核**。
const navItems = await page.evaluate(() => [...document.querySelectorAll('.admin-nav-item')]
  .map((el) => ({ href: el.getAttribute('href'), text: el.innerText.replace(/\s+/g, ' ').trim() })));
check('侧栏有「用户管理」一项且指向 /admin/users（识别记录是它的页签）',
  navItems.some((item) => item.href === '/admin/users' && item.text === '用户管理'),
  JSON.stringify(navItems));
check('侧栏不再有独立的「识别记录」项（/admin/detection-history 已并入用户管理页签）',
  !navItems.some((item) => item.href === '/admin/detection-history'), JSON.stringify(navItems));
// 第 183/185/186 批并掉的旧入口：侧栏里一个都不该再有（它们都成了页内页签）
const mergedHrefs = ['/admin/review', '/admin/forum', '/admin/comments',
  '/admin/boards', '/admin/audit-logs'];
check('侧栏不再有已并入页签的旧入口（/review、/forum、/comments、/boards、/audit-logs）',
  !navItems.some((item) => mergedHrefs.includes(item.href)),
  navItems.map((item) => item.href).join(' '));

await page.goto(`${UI}/admin/detection-history`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.admin-table', { timeout: 30_000 });
await page.waitForTimeout(2500);
// ⚠️ 第 184 批起这条旧地址**就是重定向**：`/admin/detection-history` → `/admin/users?tab=detections`。
//    所以判据是"落在管理页的识别记录页签上、**没有**被丢到农户端 `/history`"，
//    而不是"URL 还留在旧地址上"（第一版是后者，184 批之后必然红）。
const landed = new URL(page.url());
check('旧地址落在管理页的识别记录页签（没有被重定向到农户端 /history）',
  landed.pathname === '/admin/users' && landed.search.includes('tab=detections'),
  `${landed.pathname}${landed.search}`);

// ---------------------------------------------------------------------------
// ② 列表内容
// ---------------------------------------------------------------------------
let tableText = await page.locator('.admin-table').innerText();
check('列表显示识别结果', tableText.includes('zz识别记录E2E-已匹配'), '');
check('列表显示用户名', tableText.includes('zz_detE2E_user'), '');
check('列表显示置信度', /9[0-9]\.\d%|93\.0%/.test(tableText), (tableText.match(/\d+\.\d%/g) || []).slice(0, 3).join(' '));
check('未匹配词条的记录被标出来', tableText.includes('未匹配词条'), '');
check('列表有缩略图', (await page.locator('.detect-thumb').count()) > 0,
  `${await page.locator('.detect-thumb').count()} 张`);
await page.screenshot({ path: 'dsh-shots/admin-detections.png' });

// ---------------------------------------------------------------------------
// ③ 筛选：只看未匹配（统计要跟着走）
// ---------------------------------------------------------------------------
const totalBefore = await page.locator('.stat-tile').first().innerText();
await page.locator('.filter-select').first().click();
await page.waitForTimeout(600);
await page.getByText('只看未匹配词条', { exact: true }).click();
await page.waitForTimeout(2500);
tableText = await page.locator('.admin-table').innerText();
check('筛选后只剩未匹配的记录',
  tableText.includes('zz识别记录E2E-未匹配') && !tableText.includes('zz识别记录E2E-已匹配'), '');
const unmatchedTile = await page.locator('.stat-tile').nth(2).innerText();
check('「未匹配词条」统计与筛选一致',
  /^1/.test(unmatchedTile.replace(/\s+/g, ' ').trim()), unmatchedTile.replace(/\s+/g, ' '));
const totalAfter = await page.locator('.stat-tile').first().innerText();
check('总数统计跟着筛选变化', totalBefore !== totalAfter,
  `${totalBefore.replace(/\s+/g, ' ')} → ${totalAfter.replace(/\s+/g, ' ')}`);

// ---------------------------------------------------------------------------
// ④ 搜索
// ---------------------------------------------------------------------------
await page.getByRole('button', { name: /重置筛选/ }).click();
await page.waitForTimeout(2200);
await page.locator('.filter-search input').fill('zz_detE2E_user');
await page.keyboard.press('Enter');
await page.waitForTimeout(2500);
tableText = await page.locator('.admin-table').innerText();
check('按用户名搜索能过滤到这两条', tableText.includes('zz_detE2E_user') && tableText.includes('zz识别记录E2E'), '');
await page.getByRole('button', { name: /重置筛选/ }).click();
await page.waitForTimeout(2200);

// ---------------------------------------------------------------------------
// ⑤ 详情
// ---------------------------------------------------------------------------
await page.locator('.admin-table tbody tr').first().click();
await page.waitForSelector('.el-dialog', { timeout: 15_000 });
await page.waitForTimeout(1200);
const dialogText = await page.locator('.el-dialog').innerText();
check('详情里有原图/标注图与词条信息',
  /原图|标注/.test(dialogText) && /病害词条|没有匹配/.test(dialogText),
  dialogText.replace(/\s+/g, ' ').slice(0, 90));
await page.keyboard.press('Escape');
await page.waitForTimeout(800);

// ---------------------------------------------------------------------------
// ⑥ 删除（不可逆）
// ---------------------------------------------------------------------------
await page.goto(`${UI}/admin/detection-history`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.admin-table', { timeout: 30_000 });
await page.waitForTimeout(2500);
// ⚠️ 不能用"行数 -1"判断：每页 20 条、库里 25 条时，删掉一行列表**还是 20 行**（第一版就栽在这）。
// 正确的判据是"那条记录本身不见了" + "总数少了 1"。
const targetText = 'zz识别记录E2E-未匹配';
const totalBeforeDelete = await readTotal();
const targetRow = page.locator('.admin-table tbody tr').filter({ hasText: targetText }).first();
await targetRow.getByRole('button').last().click();
await page.waitForSelector('.el-message-box', { timeout: 15_000 });
await page.waitForTimeout(600);
const confirmText = await page.locator('.el-message-box').innerText();
check('删除确认写清了不可恢复', /无法恢复/.test(confirmText), confirmText.replace(/\s+/g, ' ').slice(0, 80));
await page.locator('.el-message-box__btns button').filter({ hasText: /删除/ }).first().click();
await page.waitForTimeout(3500);
const tableAfter = await page.locator('.admin-table').innerText();
check('被删的那条记录从列表消失', !tableAfter.includes(targetText),
  tableAfter.includes(targetText) ? '还在' : '已消失');
const totalAfterDelete = await readTotal();
check('记录总数少了 1', totalAfterDelete === totalBeforeDelete - 1,
  `${totalBeforeDelete} → ${totalAfterDelete}`);

// ---------------------------------------------------------------------------
// ⑦ 内容编辑员看不到（识别记录是用户数据，不是内容）
// ---------------------------------------------------------------------------
const editorPage = await (await browser.newContext({ viewport: { width: 1500, height: 950 }, locale: 'zh-CN' })).newPage();
await login(editorPage, tokenEditor, userJsonEditor);
await editorPage.goto(`${UI}/admin/dashboard`, { waitUntil: 'domcontentloaded' });
await editorPage.waitForTimeout(3000);
// 第 184 批：按 href 核（编辑员侧栏不该有 /admin/users —— 识别记录是它的页签）
const editorNav = await editorPage.evaluate(() => [...document.querySelectorAll('.admin-nav-item')]
  .map((el) => el.getAttribute('href')));
check('内容编辑员侧栏里没有 /admin/users（识别记录是它的页签，他要 USER_ADMIN 才有）',
  !editorNav.includes('/admin/users'), JSON.stringify(editorNav));
await editorPage.goto(`${UI}/admin/detection-history`, { waitUntil: 'domcontentloaded' });
await editorPage.waitForTimeout(3000);
const editorUrl = new URL(editorPage.url()).pathname;
const blocked = !editorUrl.includes('/admin/detection-history')
  || (await editorPage.locator('.admin-table').count()) === 0;
check('内容编辑员直接输网址也进不去', blocked, editorUrl);
await editorPage.close();

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
