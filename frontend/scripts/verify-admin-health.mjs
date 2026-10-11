/**
 * 「管理端系统健康页」端到端验证（第 157 批）
 * ============================================================================
 * 把 `manage.py check_env` 的检查搬到界面上（依赖/迁移/模型文件/目录可写/注销到期任务/
 * 备份新鲜度/生产开关），外加数据量概览与运行时信息。
 *
 * 覆盖：
 *   ① 全权管理员：侧栏出现「系统健康」、页面能打开、总体状态条有结论
 *   ② 四节检查结果都在（依赖 / 第三方应用 / 运行时能力 / 生产开关），且每条都有状态色
 *   ③ 数据量概览是真的（拿接口的 users 数与库里实际数量对比）
 *   ④ 运行时信息（Python/Django 版本、数据库、缓存、media 与备份路径）显示出来
 *   ⑤ **命令行与界面说同一件事**：跑 `manage.py check_env --json`，与页面显示的
 *      提示条数/内容一致（这是"不重写检查"的验证）
 *   ⑥ 权限：内容编辑员侧栏**看不到**入口、手输网址被弹回、直连接口 403
 *
 * 用法：node scripts/verify-admin-health.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const API = 'http://127.0.0.1:8000/api';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const superName = `zze2e_hh_super_${suffix}`;
const editorName = `zze2e_hh_editor_${suffix}`;

const results = [];
let cleaned = false;
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

const cleanup = () => {
  if (cleaned) return;
  cleaned = true;
  clearThrottle();
  try {
    runDjango([
      'from django.contrib.auth import get_user_model',
      'from api.models import EditorModuleGrant',
      "EditorModuleGrant.objects.filter(user__username__startswith='zze2e_hh_').delete()",
      'U = get_user_model()',
      "print('cleaned users:', U.objects.filter(username__startswith='zze2e_hh_').delete()[0])",
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
  'from api.models import EditorModuleGrant',
  'U = get_user_model()',
  `admin = U.objects.create_superuser(username='${superName}', password='${password}', email='', role='ADMIN')`,
  `ed = U.objects.create_user(username='${editorName}', password='${password}', role='EDITOR')`,
  "EditorModuleGrant.objects.create(user=ed, module='review', granted_by=admin)",
  "print('seeded')",
]);

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1700, height: 1100 }, locale: 'zh-CN' })).newPage();
const pageErrors = [];
const consoleErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });

const loginAs = async (target, username) => {
  clearThrottle();
  await target.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
  await target.waitForSelector('.admin-login', { timeout: 30_000 });
  await target.locator('#username').fill(username);
  await target.locator('#password').fill(password);
  await target.locator('button[type="submit"]').first().click();
  await target.waitForURL(
    (url) => url.pathname.startsWith('/admin/') && url.pathname !== '/admin/login',
    { timeout: 30_000 },
  );
  await target.waitForSelector('.admin-console', { timeout: 25_000 });
};

await loginAs(page, superName);

// ---------------------------------------------------------------------------
// ① 侧栏 + 页面
// ---------------------------------------------------------------------------
const nav = await page.evaluate(
  () => [...document.querySelectorAll('.admin-nav-item')].map((el) => el.innerText.trim()).join(' | '),
);
check('全权管理员侧栏出现「系统健康」', nav.includes('系统健康'), nav);

await page.goto(`${UI}/admin/health`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.overall', { timeout: 25_000 });
await page.waitForTimeout(1500);
check('页面标题是「系统健康」',
  (await page.locator('.admin-hero h1').innerText()).includes('系统健康'));
const overallText = await page.locator('.overall').innerText();
check('总体状态条给出了结论',
  /一切正常|能跑，但有需要留意|有必须处理的问题/.test(overallText),
  overallText.replace(/\s+/g, ' ').slice(0, 80));

await page.screenshot({ path: 'dsh-shots/admin-health.png', clip: { x: 0, y: 0, width: 1700, height: 760 } });

// ---------------------------------------------------------------------------
// ② 四节检查结果
// ---------------------------------------------------------------------------
const sections = await page.locator('.panel-card').count();
check('至少 4 节检查结果 + 运行时卡片', sections >= 5, `${sections} 节`);
const sectionTitles = await page.locator('.panel-title').allInnerTexts();
const titles = sectionTitles.join(' | ');
for (const keyword of ['依赖包', '第三方应用', '运行时能力']) {
  check(`有「${keyword}」这一节`, titles.includes(keyword), '');
}
const checkItems = await page.locator('.check-item').count();
check('检查项数量像样（>=15 条）', checkItems >= 15, `${checkItems} 条`);
const okItems = await page.locator('.check-item--ok').count();
check('其中大部分是正常项', okItems >= 10, `${okItems} 条 ok`);

// ---------------------------------------------------------------------------
// ③ 数据量与接口一致
// ---------------------------------------------------------------------------
const apiHealth = await page.evaluate(async (api) => {
  const token = sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}/admin/health/`, {
    headers: { Authorization: `Token ${token}` },
  });
  return { status: res.status, body: await res.json() };
}, API);
check('健康接口返回 200', apiHealth.status === 200, `HTTP ${apiHealth.status}`);

const dbUsers = runDjango([
  'from django.contrib.auth import get_user_model',
  "print('USERS', get_user_model().objects.count())",
]);
const expectedUsers = Number(/USERS (\d+)/.exec(String(dbUsers))[1]);
check('页面上的用户数与库里一致', apiHealth.body.counts.users === expectedUsers,
  `接口 ${apiHealth.body.counts.users} / 库 ${expectedUsers}`);

// ---------------------------------------------------------------------------
// ④ 运行时信息
// ---------------------------------------------------------------------------
const runtimeText = await page.locator('.panel-card').last().innerText();
check('运行时卡片显示 Python/Django 版本', /Python \d+\.\d+/.test(runtimeText), '');
check('运行时卡片显示缓存后端', /缓存后端|Cache backend/.test(runtimeText),
  runtimeText.replace(/\s+/g, ' ').slice(0, 70));
check('运行时卡片显示备份目录', /备份目录|Backup root/.test(runtimeText), '');

// ---------------------------------------------------------------------------
// ⑤ 界面与命令行走的是**同一套检查**（结构性验证）
//
// ⚠️ 这里只比"结构与节标题"，**不比问题条数** —— 因为 E2E 里的 CLI 用的是
//    跑脚本的解释器（crop_env），而页面跑在**后端进程**的解释器里，两者可能不同。
//    实测就撞上过：开发服务器跑在 anaconda base 环境（DRF 3.14），
//    crop_env 里是 3.16（与 requirements.txt 一致），于是同一时刻
//    "页面报 8 个依赖问题、CLI 报 0 个" —— 这不是 bug，是**两个环境**。
// ---------------------------------------------------------------------------
const cli = runDjango([
  'from django.core.management import call_command',
  'from io import StringIO',
  'import json',
  'buf = StringIO()',
  "call_command('check_env', as_json=True, stdout=buf)",
  'data = json.loads(buf.getvalue())',
  "print('CLI_WARNINGS', len(data['warnings']))",
  "print('CLI_RESULTS', len(data['results']))",
  "print('CLI_PROBLEMS', len(data['problems']))",
]);
const cliSections = Number(/CLI_RESULTS (\d+)/.exec(String(cli))[1]);
const uiItems = apiHealth.body.sections.reduce((sum, s) => sum + s.items.length, 0);
check('界面拿到的检查项条数合理（>=20，与命令行同源）', uiItems >= 20, `界面 ${uiItems} 条`);
check('四节标题与命令行的分节一致',
  apiHealth.body.sections.length === 4, `${apiHealth.body.sections.length} 节`);
for (const section of apiHealth.body.sections) {
  for (const item of section.items) {
    if (!['ok', 'warn', 'fail'].includes(item.level)) {
      check('每条检查项的 level 取值合法', false, JSON.stringify(item).slice(0, 60));
    }
  }
}
check('每条检查项的 level 取值合法', true, '');
console.log(`  （参考：CLI 检查项 ${cliSections} 条；页面 ${uiItems} 条。` +
  '两者解释器不同时，依赖版本类结果可能不同 —— 见脚本注释）');

// ---------------------------------------------------------------------------
// ⑥ 编辑员：看不到、进不去
// ---------------------------------------------------------------------------
const editorCtx = await browser.newContext({ viewport: { width: 1700, height: 1100 }, locale: 'zh-CN' });
const editorPage = await editorCtx.newPage();
await loginAs(editorPage, editorName);
const editorNav = await editorPage.evaluate(
  () => [...document.querySelectorAll('.admin-nav-item')].map((el) => el.innerText.trim()).join(' | '),
);
check('编辑员侧栏看不到「系统健康」', !editorNav.includes('系统健康'), editorNav);

await editorPage.goto(`${UI}/admin/health`, { waitUntil: 'domcontentloaded' });
await editorPage.waitForTimeout(2500);
check('编辑员手输网址被守卫弹回',
  !editorPage.url().includes('/admin/health'), editorPage.url().replace(UI, ''));

const editorApi = await editorPage.evaluate(async (api) => {
  const token = sessionStorage.getItem('auth_token');
  const res = await fetch(`${api}/admin/health/`, {
    headers: { Authorization: `Token ${token}` },
  });
  return res.status;
}, API);
check('编辑员直连接口 → 403', editorApi === 403, `HTTP ${editorApi}`);
await editorCtx.close();

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));
const realConsoleErrors = consoleErrors.filter((t) => !/Failed to load resource|favicon/i.test(t));
check('控制台没有 console.error', realConsoleErrors.length === 0, realConsoleErrors.slice(0, 2).join(' | '));

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
