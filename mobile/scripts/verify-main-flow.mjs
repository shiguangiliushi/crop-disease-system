/**
 * 移动端主链路 E2E（第 175 批）
 * ============================================================================
 * 到这一批为止，移动端验过的都是**外壳与单页**（顶栏口径、配色、空状态）——
 * 而"农户真正会走的那条路"从来没人自动跑过：**拍照 → 识别 → 结果 → 记录**。
 * 这一条要是断了，前面那些一致性做得再漂亮也没用。
 *
 * 本脚本验证：
 *   ① 用**专用测试账号**登录（不污染 admin 的记录，用完能干净清掉）
 *   ② 从相册选一张真实叶片图 → 识别成功 → 自动进结果页
 *   ③ 结果页显示病害中文名 + 置信度（英文类名不该露出来）
 *   ④ 记录页出现刚才那条记录（缩略图 + 名称）
 *   ⑤ **切 tab 不丢照片**（第 91 批的 keep-alive 承诺，回归它）
 *   ⑥ 记录页下拉刷新仍然可用
 *   ⑦ 全程无 JS 报错
 *
 * 用法：node scripts/verify-main-flow.mjs
 */
import { chromium } from '@playwright/test';
import path from 'node:path';
import { clearThrottle, runDjango } from './helpers.mjs';

const UI = 'http://127.0.0.1:5174';
const SAMPLE = path.resolve(
  process.cwd(), '..', 'backend', 'pests', 'Apple___Apple_scab14.jpg',
);
const USER = 'zz_mobile_flow';
const PASS = 'ZzMobile!2026';

const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

// ---------------------------------------------------------------------------
// 准备：专用账号（清空它的历史，保证"记录页出现第一条"这件事可判断）
// ---------------------------------------------------------------------------
clearThrottle();
const seed = runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models import DetectionHistory',
  `u, _ = get_user_model().objects.get_or_create(username='${USER}', defaults={'role': 'USER'})`,
  `u.set_password('${PASS}')`,
  'u.is_active = True',
  'u.is_deleted = False',
  'u.save()',
  'DetectionHistory.objects.filter(user=u).delete()',
  "print('flow user ready')",
]);

const AUTHED = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: 'zh-CN' };
const browser = await chromium.launch();
const context = await browser.newContext(AUTHED);
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error).slice(0, 200)));

const cleanup = () => {
  try {
    runDjango([
      'from django.contrib.auth import get_user_model',
      'from api.models import DetectionHistory',
      `u = get_user_model().objects.filter(username='${USER}').first()`,
      'if u:',
      '    DetectionHistory.objects.filter(user=u).delete()',
      '    u.delete()',
      "print('flow user cleaned')",
    ]);
  } catch (error) {
    console.warn('  清理失败（忽略）:', String(error).slice(0, 120));
  }
};

// ---------------------------------------------------------------------------
// ① 登录
// ---------------------------------------------------------------------------
await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
await page.locator('input').nth(0).fill(USER);
await page.locator('input').nth(1).fill(PASS);
await page.getByRole('button', { name: /登录/ }).first().click();
await page.waitForTimeout(3000);
check('专用账号能登录', !page.url().includes('/login'), page.url());

// ---------------------------------------------------------------------------
// ② 选图 → 识别 → 结果页
// ---------------------------------------------------------------------------
await page.goto(`${UI}/detect`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1800);
// 页面上有两个隐藏 input（拍照 / 相册），按"从相册选"这条路径走
await page.locator('input[type=file]').nth(1).setInputFiles(SAMPLE);
await page.waitForTimeout(1200);
const previewShown = await page.locator('img').count() > 0;
check('选图后出现预览', previewShown, '');

// 点"开始识别"（识别页的主按钮）
const startBtn = page.getByRole('button', { name: /开始识别|识别/ }).first();
await startBtn.click();
await page.waitForURL((url) => url.pathname.startsWith('/result'), { timeout: 90_000 });
await page.waitForTimeout(3000);
check('识别完成后自动进入结果页', page.url().includes('/result'), page.url());

const resultText = await page.locator('body').innerText();
check('结果页显示病害中文名（不是英文类名）',
  /苹果黑星病/.test(resultText), (resultText.match(/苹果黑星病|Apple___\w+/g) || []).join(' / '));
check('结果页不露英文类名',
  !/Apple___|healthy/i.test(resultText), '');
check('结果页显示置信度', /%/.test(resultText), (resultText.match(/\d+(\.\d+)?%/g) || []).slice(0, 3).join(' '));
check('结果页展示主要症状或防治建议',
  /症状|防治|建议/.test(resultText), '');
await page.screenshot({ path: 'dsh-shots/flow-result-after.png' });

// ---------------------------------------------------------------------------
// ③ 记录页出现这条记录
// ---------------------------------------------------------------------------
await page.goto(`${UI}/history`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3500);
const historyText = await page.locator('body').innerText();
check('记录页出现刚才那条记录',
  /苹果黑星病/.test(historyText), (historyText.match(/苹果黑星病/g) || []).length + ' 处');
check('记录页有缩略图', (await page.locator('.record-thumb').count()) > 0,
  `${await page.locator('.record-thumb').count()} 张`);
check('记录页不再显示空状态', (await page.locator('.van-empty').count()) === 0, '');
await page.screenshot({ path: 'dsh-shots/flow-history-after.png' });

// ---------------------------------------------------------------------------
// ④ 回归第 91 批的承诺：切 tab 不丢照片
//    ⚠️ 必须**点底部标签栏**切页。第一版用 page.goto() —— 那是整页刷新，
//    连浏览器内存都清了，keep-alive 再神也留不住 ✗（测的不是同一件事）。
// ---------------------------------------------------------------------------
await page.goto(`${UI}/detect`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
await page.locator('input[type=file]').nth(1).setInputFiles(SAMPLE);
await page.waitForTimeout(1500);
const beforeSwitch = await page.locator('.van-image img, img').count();
const canStartBefore = await page.getByRole('button', { name: /开始识别|识别/ }).count();

await page.locator('.van-tabbar-item').nth(1).click();   // 记录
await page.waitForTimeout(2000);
check('点底部导航能切到记录页', page.url().includes('/history'), page.url());
await page.locator('.van-tabbar-item').nth(0).click();   // 识别
await page.waitForTimeout(2500);
const afterSwitch = await page.locator('.van-image img, img').count();
const canStartAfter = await page.getByRole('button', { name: /开始识别|识别/ }).count();
check('切 tab 再回来：选好的照片还在（keep-alive 生效）',
  afterSwitch >= beforeSwitch && beforeSwitch > 0 && canStartAfter === canStartBefore,
  `切前 ${beforeSwitch} 张图（可识别=${canStartBefore > 0}）→ 切后 ${afterSwitch} 张图（可识别=${canStartAfter > 0}）`);

// ---------------------------------------------------------------------------
// ⑤ 下拉刷新仍然可用（记录页）
// ---------------------------------------------------------------------------
await page.goto(`${UI}/history`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2500);
const hasPullRefresh = await page.locator('.van-pull-refresh').count() > 0;
check('记录页仍带下拉刷新', hasPullRefresh, '');

check('全程无 JS 报错', errors.length === 0, errors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
