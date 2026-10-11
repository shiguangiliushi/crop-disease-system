/**
 * 「识别结果显示中文名 + 症状 + 防治」端到端验证（第 159 批）
 * ============================================================================
 * 用户报的问题：识别结果**显示英文病害名**、**主要症状与防治建议都没有**，
 * 而 Django 后台里明明有内容。
 *
 * 根因：模型给的是 PlantVillage 风格类名（`Apple___Apple_scab`），
 * 库里存的是 `apple_scab`，而匹配规则只有"去掉空格后精确相等" → 永远匹配不上 →
 * 接口回落到英文类名 + `暂无详细描述` / `请咨询农业专家获取防治建议`。
 *
 * 这个脚本从**界面**验证修复：
 *   ① 登录 → 打开识别页 → 上传仓库里那张真实的苹果黑星病图
 *   ② 结果卡片上的病害名必须是**中文**（且不是英文类名的样子）
 *   ③ 主要症状与防治建议必须是有内容的（不是占位文字、也不是"暂无"）
 *   ④ 识别记录页里同样显示中文名（说明落库时也关联上了词条）
 *   ⑤ 顺带核对接口返回：`disease` 是中文、`description` / `prevention` 不是占位
 *
 * 用法：node scripts/verify-detect-result.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const IMAGE = 'D:/新建文件夹/crop-disease-system/backend/pests/Apple___Apple_scab14.jpg';

const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';
const username = `zze2e_detect_${suffix}`;

const results = [];
let cleaned = false;
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

const HAS_CJK = /[\u4e00-\u9fff]/;
const PLACEHOLDERS = ['暂无详细描述', '请咨询农业专家获取防治建议', '暂无', '没有找到'];

const cleanup = () => {
  if (cleaned) return;
  cleaned = true;
  clearThrottle();
  try {
    runDjango([
      'from django.contrib.auth import get_user_model',
      "U = get_user_model()",
      "print('cleaned', U.objects.filter(username__startswith='zze2e_detect_').delete()[0])",
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
  'U = get_user_model()',
  `U.objects.create_user(username='${username}', password='${password}', role='USER')`,
  "print('seeded')",
]);

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1500, height: 1100 }, locale: 'zh-CN' })).newPage();
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));

// 登录
await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('input#username, input[name="username"]', { timeout: 30_000 });
await page.locator('input#username, input[name="username"]').first().fill(username);
await page.locator('input[type="password"]').first().fill(password);
await page.locator('button[type="submit"]').first().click();
await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 30_000 });

// ① 识别页上传
await page.goto(`${UI}/detect`, { waitUntil: 'domcontentloaded' });
// ⚠️ 页面里有两个隐藏的 file input：`ref="fileInput"`（上传图片）与 `ref="cameraInput"`（拍照）。
// 它们都是 d-none，所以只能按"已挂载"等（setInputFiles 不要求可见）；
// 必须选**上传**那个 —— 选到拍照那个，页面会走另一条分支。
await page.waitForSelector('input[ref="fileInput"], input[type="file"]', { state: 'attached', timeout: 25_000 });
const fileInputs = page.locator('input[type="file"]');
const uploadInput = fileInputs.first();     // 模板里 fileInput 在前、cameraInput 在后
await uploadInput.setInputFiles(IMAGE);

// ⚠️ 选中文件只是"待命"，必须再点「开始识别」才会真的调接口 ——
// 第一版脚本没点，等了 120 秒结果卡片也没出现。
await page.waitForTimeout(800);
// ⚠️ 必须用**精确**名字：`{ name: /开始识别|识别/ }` 会先匹配到导航栏那个「识别」链接
// （它在 DOM 里更靠前），于是点了等于没点 —— 接口一直没被调用，等到超时。
await page.getByRole('button', { name: '开始识别' }).first().click();
// 识别要在 CPU 上跑模型，慢的时候十几秒；先等"正在生成检测结果"出现再等结果卡片
await page.waitForSelector('text=正在生成检测结果', { timeout: 30_000 }).catch(() => {});

// 等结果卡片出现（识别要跑模型，给足时间）
await page.waitForSelector('.results-container, .detect-disease-name', { timeout: 180_000 });
await page.waitForTimeout(2000);
await page.screenshot({ path: 'dsh-shots/detect-result.png', fullPage: false });

const nameText = (await page.locator('.detect-disease-name').first().innerText().catch(() => '')).trim();
check('结果卡片显示了病害名', Boolean(nameText), nameText);
check('病害名是中文（不是英文类名）', HAS_CJK.test(nameText), nameText);
check('病害名不是 PlantVillage 那种英文写法', !/^[A-Za-z_ ,()-]+$/.test(nameText), nameText);

const cardText = await page.locator('.results-container').innerText();
console.log('  ── 结果卡片原文 ──');
console.log(cardText.split('\n').filter(Boolean).map((l) => '    ' + l.trim()).join('\n'));
const symptomLine = await page.locator('.results-container p').allInnerTexts();
const symptomsShown = symptomLine.join(' ').slice(0, 400);
check('主要症状有内容（不是占位/暂无）',
  Boolean(symptomsShown.trim()) && !PLACEHOLDERS.some((p) => symptomsShown.includes(p)),
  symptomsShown.replace(/\s+/g, ' ').slice(0, 80));
const preventionShown = cardText.split(/防治|建议/).slice(1).join(' ').slice(0, 300);
check('防治建议有内容（不是占位/暂无）',
  Boolean(preventionShown.trim()) && !PLACEHOLDERS.some((p) => preventionShown.includes(p)),
  preventionShown.replace(/\s+/g, ' ').slice(0, 80));

// ② 接口层面核对（同一时刻）
const apiResult = await page.evaluate(async (api) => {
  const token = sessionStorage.getItem('auth_token') || localStorage.getItem('auth_token');
  const list = await fetch(`${api}/detection-history/?page_size=1`, {
    headers: { Authorization: `Token ${token}` },
  });
  return { status: list.status, body: await list.json() };
}, API);
check('识别记录接口可用', apiResult.status === 200, `HTTP ${apiResult.status}`);
const latest = (apiResult.body?.results || apiResult.body?.data?.results || [])[0];
if (latest) {
  check('最新一条记录的名称是中文', HAS_CJK.test(latest.detection_result || latest.pest_name || ''),
    JSON.stringify(latest.detection_result || latest.pest_name));
}

// ③ 识别记录页也显示中文
await page.goto(`${UI}/history`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3000);
const historyText = await page.locator('body').innerText();
check('识别记录页显示中文病害名',
  HAS_CJK.test(historyText) && !/Apple___|Apple {2,}/.test(historyText),
  historyText.replace(/\s+/g, ' ').slice(0, 90));

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
