/**
 * 多语言专项验证：**浏览器语言是中文**时，英文界面是否真的没有中文（第 78 批）
 *
 * 为什么需要这个脚本（主审计脚本查不出来）
 * ---------------------------------------------------------------------------
 * `scripts/audit-i18n-cjk.mjs` 跑在无头 Chromium 里，默认 locale 是 en-US；
 * 而**原生控件**（`<input type="date">` 的「年/月/日」、系统日期面板）的语言
 * 由**浏览器/系统语言**决定，与页面语言无关。于是主审计在 en-US 下看起来一切正常，
 * 用户在自己的中文浏览器里却看到「年/月/日」—— 这正是真实反馈里的那个 bug。
 *
 * 本脚本把浏览器 locale 固定成 zh-CN 复现用户环境，再验证英文界面：
 *   ① 日期筛选占位符是英文（修复前是「年/月/日」）；
 *   ② 弹出的日期面板是英文（修复前是「日一二三四五六」）；
 *   ③ Element Plus 自带文案（分页器等）是英文；
 *   ④ 整页正文除页脚备案号外无中文。
 *
 * 前置：后端 8000、前端 5173 均在运行。
 * 用法（在 frontend 目录下）：
 *   1) 在 backend 目录下造临时审计账号并导出登录态：
 *      python _seed_i18n_audit_tmp.py --out=D:\...\frontend\_seed.json
 *      （用完请删掉该 JSON —— 里面是真实 token）
 *   2) node scripts/verify-i18n-zh-browser.mjs ./_seed.json
 *
 * 退出码：全部通过 0，任一失败 1。
 */
import { chromium } from '@playwright/test';
import { readFileSync } from 'node:fs';

const UI = process.env.AUDIT_UI || 'http://127.0.0.1:5173';
const seedPath = process.argv[2];
if (!seedPath) {
  console.error('用法: node scripts/verify-i18n-zh-browser.mjs <seed.json>');
  process.exit(2);
}
const seed = JSON.parse(readFileSync(seedPath, 'utf8'));

const CJK = /[\u4e00-\u9fff]/;
const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok, detail });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

const browser = await chromium.launch();
// 关键：浏览器/系统语言设成中文，复现用户环境
const context = await browser.newContext({ locale: 'zh-CN' });
await context.addInitScript(
  ([token, user, locale]) => {
    window.localStorage.setItem('auth_token', token);
    window.localStorage.setItem('user', user);
    window.localStorage.setItem('app_locale', locale);
  },
  [seed.token, JSON.stringify(seed.user || { id: seed.user_id, username: seed.username, is_staff: true, is_superuser: true, role: 'ADMIN' }), 'en'],
);

const page = await context.newPage();
await page.goto(`${UI}/history`, { waitUntil: 'networkidle' });
await page.waitForSelector('#filter-date', { timeout: 25_000 });
await page.waitForTimeout(1500);

const dateRoot = page.locator('#filter-date').first();
// el-date-picker 会把 id 透传到真正的 <input> 上（也可能落在包裹层），两种都兼容
const rootTag = await dateRoot.evaluate((el) => el.tagName.toLowerCase());
const dateInput = rootTag === 'input' ? dateRoot : dateRoot.locator('input').first();
const placeholder = await dateInput.getAttribute('placeholder');
check('日期筛选占位符是英文', !!placeholder && !CJK.test(placeholder), `placeholder="${placeholder}"`);

// 选中一个日期，确认筛选**真的发出去**（换了控件不能只剩外观）
const historyRequests = [];
page.on('request', (req) => {
  if (req.url().includes('detection-history')) historyRequests.push(req.url());
});
await dateInput.click();
await page.waitForSelector('.el-picker-panel', { timeout: 10_000 }).catch(() => {});
await page.waitForTimeout(600);
const panelText = await page
  .locator('.el-picker-panel')
  .first()
  .innerText()
  .catch(() => '');
const panelHasCjk = CJK.test(panelText);
check('日期面板无中文', !!panelText && !panelHasCjk, `panel="${panelText.replace(/\s+/g, ' ').slice(0, 80)}"`);

await page.locator('.el-picker-panel td.available').first().click();
await page.waitForTimeout(1800);
const pickedValue = await dateInput.inputValue().catch(() => '');
const sentDateParam = historyRequests.some((url) => /[?&]date=/.test(url));
check(
  '选中日期后筛选仍然生效（请求带 date 参数）',
  Boolean(pickedValue) && sentDateParam,
  `值="${pickedValue}"，带 date 的请求=${sentDateParam}，共 ${historyRequests.length} 次记录请求`,
);
await page.keyboard.press('Escape');
await page.waitForTimeout(300);

// Element Plus 自带文案：分页器
const pager = await page.locator('.el-pagination').first().innerText().catch(() => '');
check('分页器文案无中文', !CJK.test(pager), `pager="${pager.replace(/\s+/g, ' ').slice(0, 60)}"`);

// 整页兜底：除了页脚备案号，不应有中文
const body = await page.locator('body').innerText();
const cjkLines = body
  .split('\n')
  .map((line) => line.trim())
  .filter((line) => CJK.test(line));
const nonFooter = cjkLines.filter((line) => !/ICP|公网安备/.test(line));
check('页面正文无中文（备案号除外）', nonFooter.length === 0, nonFooter.slice(0, 6).join(' | '));

await page.screenshot({ path: 'dsh-shots/i18n-history-zh-browser.png', fullPage: true });
await browser.close();

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} 项通过`);
process.exit(failed.length ? 1 : 0);
