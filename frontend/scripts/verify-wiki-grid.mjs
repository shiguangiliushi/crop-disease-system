/**
 * 病害百科列表布局专项验证：**每页 6 条必须是 3 列 × 2 行**（第 115 批）
 *
 * 为什么需要它
 * ---------------------------------------------------------------------------
 * 页面里 `pageSize = 6` 一直写着注释"2 行 × 3 列"，但网格用的是
 * `repeat(auto-fill, minmax(260px, 1fr))` —— 列数跟着容器宽度变。
 * 内容区宽 1132px 时能塞下 4 列（4×260 + 3×22 = 1106），于是**1920 / 1600
 * 这类最常见的宽屏上实际是"4 + 2"**，第二行右侧空一大块（第 115 批实测确认）。
 *
 * 这类回归"看代码看不出来"（`repeat(3, 1fr)` 与 auto-fill 在窄屏表现一致），
 * 只有把浏览器开到宽屏量一遍才看得见 —— 所以固化成脚本。
 *
 * 断言：
 *   ① 宽屏（≥1024）恰好 3 列，6 条 = 3 + 3（两行），且两行各自顶端对齐、行内卡片等高；
 *   ② 卡片宽度一致、网格不横向溢出容器；
 *   ③ 窄屏按断点降级：≤900 → 2 列，≤620 → 1 列；
 *   ④ 末页（不足 6 条）**网格轨道仍是 3 条**、卡片从左边往右排
 *      （少的只是卡片，不是列数）；
 *   ⑤ 卡片内容仍然完整（图片 / 病害名 / 描述 / 详情按钮），点"了解详情"能进详情页。
 *
 * 前置：后端 8000、前端 5173 均在运行。
 * 用法（在 frontend 目录下）：
 *   node scripts/verify-wiki-grid.mjs
 * 退出码：全部通过 0，任一失败 1。
 */
import { chromium } from '@playwright/test';
// 临时账号的清理复用 E2E 的 runDjango（注销接口只是软删除，会留下 deleted_* 行）
import { runDjango } from '../e2e/helpers.mjs';

const API = process.env.E2E_API_URL || 'http://127.0.0.1:8000';
const UI = process.env.AUDIT_UI || 'http://127.0.0.1:5173';

const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

// ---- 临时账号（百科页需要登录；用完即删） ----
// 前缀 zze2e_ 便于清理；总长必须 ≤ 20（后端限制），所以后缀取 5 位
const username = `zze2e_wg_${Math.random().toString(36).slice(2, 7)}`;
const password = 'ZzE2e!2026pw';
const reg = await fetch(`${API}/api/register/`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username, password, password2: password, email: `${username}@example.invalid` }),
});
const regJson = await reg.json();
const session = regJson?.data ?? regJson;
if (!session?.token) {
  console.error(`注册临时账号失败（HTTP ${reg.status}）：${JSON.stringify(regJson).slice(0, 300)}`);
  process.exit(2);
}

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1920, height: 1000 }, locale: 'zh-CN' });
await context.addInitScript((payload) => {
  sessionStorage.setItem('auth_token', payload.token);
  sessionStorage.setItem('user', JSON.stringify(payload.user));
  localStorage.setItem('app_locale', 'zh');
}, { token: session.token, user: session.user });

const page = await context.newPage();
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 160)));

/** 量一次当前网格的几何 */
const measure = () =>
  page.evaluate(() => {
    const grid = document.querySelector('.pest-grid');
    if (!grid) return null;
    const cards = [...grid.querySelectorAll('.pest-card')];
    const rects = cards.map((c) => c.getBoundingClientRect());
    const cols = [...new Set(rects.map((r) => Math.round(r.left)))].sort((a, b) => a - b);
    const rows = [...new Set(rects.map((r) => Math.round(r.top)))].sort((a, b) => a - b);
    const perRow = rows.map((top) => rects.filter((r) => Math.round(r.top) === top).length);
    return {
      cards: cards.length,
      perRow,
      columns: cols.length,
      rows: rows.length,
      // 网格**轨道数**（与"现有卡片占了几列"不同：末页只有 2 条时轨道仍是 3 条）
      trackCount: getComputedStyle(grid).gridTemplateColumns.split(' ').filter(Boolean).length,
      widths: [...new Set(rects.map((r) => Math.round(r.width)))],
      heights: rects.map((r) => Math.round(r.height)),
      rowHeights: rows.map((top) =>
        [...new Set(rects.filter((r) => Math.round(r.top) === top).map((r) => Math.round(r.height)))]
      ),
      gridWidth: Math.round(grid.getBoundingClientRect().width),
      overflows: grid.scrollWidth > grid.clientWidth + 1,
      parentWidth: Math.round(grid.parentElement.getBoundingClientRect().width),
    };
  });

const setViewport = async (width) => {
  await page.setViewportSize({ width, height: 1000 });
  await page.waitForTimeout(500);
};

await page.goto(`${UI}/pests`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.pest-card', { timeout: 30_000 });
await page.waitForTimeout(800);

// ---- ① 宽屏 3 列 × 2 行 ----
for (const width of [2560, 1920, 1600, 1440, 1280, 1024]) {
  await setViewport(width);
  const m = await measure();
  const ok =
    m && m.cards === 6 && m.columns === 3 && m.rows === 2 &&
    m.perRow.every((n) => n === 3) && !m.overflows;
  check(`${width}px 视口：3 列 × 2 行`, ok, `实际 ${m?.perRow?.join('+')}（${m?.columns} 列 × ${m?.rows} 行），卡片宽 ${m?.widths?.join('/')}px`);
  if (width === 1920) {
    check('1920px 行内卡片等高', m.rowHeights.every((hs) => hs.length === 1), `行高 ${m.rowHeights.map((h) => h.join('/')).join(' | ')}`);
    check('1920px 卡片宽度一致', m.widths.length === 1, `${m.widths.join('/')}px`);
    check('1920px 网格不溢出容器', !m.overflows && m.gridWidth <= m.parentWidth, `网格 ${m.gridWidth}px / 容器 ${m.parentWidth}px`);
  }
}
// 留证：整块主区（3×2 卡片 + 右侧栏）与整页各一张。
// 用 `clip`（坐标取自 boundingBox()）而不是元素截图：整块主区比 1000px 高的视口还高，
// 元素截图会先把元素滚进视口，得到的图**与"整页截图里的同一块"是否一致并不直观**；
// clip 只管截哪一块，配合调高的视口（2200）让主区完整落在首屏内，结果最直观。
// 注：本次已用像素对齐核对过 —— 主区截图与整页截图同一区域**逐像素完全一致**（差值为 0）。
await page.setViewportSize({ width: 1920, height: 2200 });
await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(600);
const mainBox = await page.locator('.encyclopedia-main').boundingBox();
await page.screenshot({
  path: 'dsh-shots/wiki-grid-3x2.png',
  clip: { x: mainBox.x, y: mainBox.y, width: mainBox.width, height: mainBox.height },
});
await page.setViewportSize({ width: 1920, height: 1000 });
await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(300);
await page.screenshot({ path: 'dsh-shots/wiki-grid-fullpage.png', fullPage: true });

// ---- ② 窄屏降级 ----
for (const [width, expected] of [[900, 2], [768, 2], [620, 1], [390, 1]]) {
  await setViewport(width);
  const m = await measure();
  check(`${width}px 视口：${expected} 列`, m?.columns === expected && !m.overflows, `实际 ${m?.columns} 列，行分布 ${m?.perRow.join('+')}`);
}

// ---- ③ 末页仍然 3 列 ----
await setViewport(1920);
const totalText = await page.locator('.pagination-info').first().innerText().catch(() => '');
const totalPages = Number(/Page\s+\d+\/(\d+)/.exec(totalText)?.[1] || 1);
check('分页信息可读', totalPages >= 1, totalText.replace(/\s+/g, ' '));
if (totalPages > 1) {
  await page.locator('.pagination-btn', { hasText: '下一页' }).first().click();
  await page.waitForTimeout(700);
  const lastPageCards = await page.locator('.pest-card').count();
  for (let i = 2; i < totalPages; i += 1) {
    const next = page.locator('.pagination-btn', { hasText: '下一页' }).first();
    if (await next.isDisabled()) break;
    await next.click();
    await page.waitForTimeout(500);
  }
  const m = await measure();
  // 末页不足 6 条时，"有几张卡片占了几列"当然会变小 —— 要看的是**网格轨道**仍是 3 条，
  // 卡片从第 1 条轨道开始往右排（不是被拉伸成 1 列 / 居中）。
  const firstLeft = await page.locator('.pest-card').first().evaluate((c) => Math.round(c.getBoundingClientRect().left));
  const gridLeft = await page.locator('.pest-grid').evaluate((g) => Math.round(g.getBoundingClientRect().left));
  check(
    `末页（${lastPageCards} 条）仍是 3 列轨道、从左往右排`,
    m?.trackCount === 3 && firstLeft === gridLeft && !m.overflows,
    `第 ${totalPages} 页：${m?.perRow?.join('+')}，轨道 ${m?.trackCount} 条，卡片宽 ${m?.widths?.join('/')}px`,
  );
}

// ---- ④ 卡片内容与详情跳转 ----
await page.locator('.pagination-btn', { hasText: '上一页' }).first().click().catch(() => {});
await page.goto(`${UI}/pests`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.pest-card', { timeout: 30_000 });
await page.waitForTimeout(800);
const first = page.locator('.pest-card').first();
const content = await first.evaluate((card) => ({
  hasImage: !!card.querySelector('img')?.getAttribute('src'),
  name: card.querySelector('h3')?.innerText?.trim() || '',
  desc: card.querySelector('.description')?.innerText?.trim() || '',
  button: card.querySelector('.details-button')?.innerText?.trim() || '',
}));
check(
  '卡片内容完整（图 / 名称 / 描述 / 详情按钮）',
  content.hasImage && !!content.name && !!content.desc && !!content.button,
  `${content.name}｜按钮"${content.button}"`,
);
await first.locator('.details-button').click();
await page.waitForURL(/\/pests\/.+/, { timeout: 15_000 }).catch(() => {});
check('点"了解详情"进详情页', /\/pests\/.+/.test(page.url()), page.url().replace(UI, ''));

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();

// ---- 清理临时账号（硬删除，不留 deleted_* 残留行） ----
try {
  const out = runDjango([
    'from django.contrib.auth import get_user_model',
    `print('deleted:', get_user_model().objects.filter(username='${username}').delete()[0])`,
  ]);
  console.log(`\n临时账号 ${username} 清理：${out}`);
} catch (error) {
  console.log(`\n⚠️ 临时账号 ${username} 自动清理失败：${String(error).slice(0, 200)}`);
  console.log('   请手动删除该账号（前缀 zze2e_）。');
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} 项通过`);
process.exit(failed.length ? 1 : 0);
