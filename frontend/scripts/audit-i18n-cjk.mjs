#!/usr/bin/env node
/**
 * audit-i18n-cjk.mjs —— 「英文界面残留中文」审计器
 * ============================================================================
 * 目标：把前端切到 English 后，逐页抓取**可见文本**（document.body.innerText），
 *       只保留含 CJK 汉字的行，按页分组输出 + 存 JSON + 存整页截图。
 *
 * 它只读不写应用代码：
 *   · 不改 frontend/src/**，不改 backend/api/**；
 *   · 唯一写入的"数据"来自临时夹具脚本 backend/_seed_i18n_audit_tmp.py（审计专用账号）；
 *   · 产物全部落在 frontend/dsh-shots/。
 *
 * 用法（在 frontend 目录下）：
 *     node scripts/audit-i18n-cjk.mjs
 *     node scripts/audit-i18n-cjk.mjs --headed          # 想看浏览器过程
 *     node scripts/audit-i18n-cjk.mjs --routes=/history  # 只跑部分路由
 *
 * 退出码：0 = 审计正常完成（**即使发现了中文**，发现问题才是目的）；
 *         1 = 脚本/浏览器/环境本身出错。
 */
import { chromium, request as playwrightRequest } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { existsSync, readdirSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';

// ── 可调参数 ────────────────────────────────────────────────────────────────
const FRONTEND_DIR = path.resolve(process.cwd());
const BACKEND_DIR = path.resolve(FRONTEND_DIR, '..', 'backend');
const SHOTS_DIR = path.join(FRONTEND_DIR, 'dsh-shots');

const BASE_URL = process.env.I18N_AUDIT_BASE_URL || 'http://127.0.0.1:5173';
const API_URL = process.env.I18N_AUDIT_API_URL || 'http://127.0.0.1:8000';
const PYTHON = process.env.I18N_AUDIT_PYTHON || 'C:\\Users\\zhx\\anaconda3\\envs\\crop_env\\python.exe';
const SEED_SCRIPT = '_seed_i18n_audit_tmp.py';

const VIEWPORT = { width: 1440, height: 1000 };
const CJK_RE = /[\u4e00-\u9fff]/;
/** 补充检测：CJK 标点/全角符号（不计入正文清单，只在日志里提一句） */
const CJK_PUNCT_RE = /[\u3000-\u303f\uff00-\uffef]/;

const NAV_TIMEOUT = 60_000;
const HEADING_TIMEOUT = 25_000;
const SETTLE_MS = 2_500;         // 等 Chart.js 动画 + 异步接口回来
const EXTRA_SETTLE_MS = 2_000;   // 切换开关后的额外沉降

const JSON_BEGIN = '===CJK-AUDIT-JSON===';
const JSON_END = '===END===';

/** 受限沙箱下 CDP 回退所需的常量（见 launchBrowser 注释） */
const CDP_HOST = '127.0.0.1';
const CDP_PORT = Number(process.env.I18N_AUDIT_CDP_PORT || 9333);
const CDP_BOOT_TIMEOUT = 40_000;

/** 待审计路由。heading 是"页面渲染成功"的判据（英文文案），用于区分"渲染了"和"没渲染"。 */
const ROUTES = [
  { page: 'home', path: '/', heading: 'Smart Crop Leaf Disease Recognition System' },
  {
    page: 'history',
    path: '/history',
    heading: 'Diagnosis history',
    // 管理员在 /history 上多一个「查看全部用户」开关；关着时统计卡/图表只有自己那点数据
    setup: enableViewAllUsers,
  },
  { page: 'detect', path: '/detect', heading: 'Upload a crop image to diagnose' },
  { page: 'calendar', path: '/calendar', heading: 'Farming Calendar' },
  { page: 'pests', path: '/pests', heading: 'Disease Wiki' },
  { page: 'admin-dashboard', path: '/admin/dashboard', heading: 'Dashboard' },
  // 第 78 批补：
  //   · consult —— 专家咨询页（作物标签、提问状态标签）
  //   · pest-detail —— 病害详情：防治措施**直接渲染**，是 measure_en 语料回填最直接的验证点
  //   · preventions —— 综合防治：类别名 + 措施正文都在这里，但默认折叠，要先展开
  { page: 'consult', path: '/consult', heading: 'Expert Q&A' },
  { page: 'pest-detail', path: '/pests/tomato_late_blight', heading: 'Late blight' },
  {
    page: 'preventions',
    path: '/preventions/32',
    heading: 'Integrated control strategies',
    setup: expandPreventionAccordion,
  },
  // 第 79 批：全站覆盖 —— 上面只看了 7 个页面，反馈"还有中文"说明漏了页面。
  // 这里把其余可达路由（含需要 id 的详情页）一次补齐，id 取开发库里的真实数据。
  { page: 'alerts', path: '/alerts', heading: 'Outbreak Alerts' },
  { page: 'news', path: '/news', heading: 'News' },
  // 第 80 批：改用**已发布**的新闻（22）。原来用 27（未发布草稿）—— 管理员能预览、
  // 普通用户会拿到 404，于是普通用户路径下这一页测不到真实渲染。
  { page: 'news-detail', path: '/news/22', heading: 'News' },
  { page: 'forum', path: '/forum', heading: 'Forum' },
  { page: 'forum-board', path: '/forum/board/1', heading: 'Forum' },
  { page: 'post-detail', path: '/forum/post/106', heading: 'Forum' },
  { page: 'forum-favorites', path: '/forum/favorites', heading: 'Forum' },
  { page: 'new-post', path: '/forum/post/new', heading: 'Forum' },
  { page: 'notifications', path: '/notifications', heading: 'Notifications' },
  { page: 'messages', path: '/messages', heading: 'Messages' },
  { page: 'feedback', path: '/feedback', heading: 'Feedback' },
  { page: 'user-profile', path: '/user/profile/1', heading: 'Profile' },
  { page: 'about', path: '/about', heading: 'About' },
  { page: 'help', path: '/help', heading: 'Help' },
  { page: 'terms', path: '/terms', heading: 'Terms' },
  { page: 'privacy', path: '/privacy', heading: 'Privacy' },
  { page: 'admin-users', path: '/admin/users', heading: 'User management' },
  { page: 'admin-review', path: '/admin/review', heading: 'Content review' },
  { page: 'admin-news', path: '/admin/news', heading: 'News management' },
  { page: 'admin-feedback', path: '/admin/feedback', heading: 'Feedback management' },
];

/**
 * 「综合防治」页的防治措施默认是**折叠**的（`expandedCategories` 为空），
 * 不展开的话抓不到措施正文 —— 那样审计会"通过"，但其实是没看到内容。
 * 折叠面板每个类别一个 `.accordion-header`，点一下展开。
 */
async function expandPreventionAccordion(page) {
  const label = '展开全部防治类别';
  const headers = page.locator('.accordion-header');
  const found = await headers.count();
  let opened = 0;
  for (let i = 0; i < found; i += 1) {
    try {
      await headers.nth(i).click({ timeout: 5_000 });
      opened += 1;
    } catch {
      /* 已展开或不可点：忽略，下面用 DOM 里是否有措施正文来兜底判断 */
    }
  }
  await page.waitForTimeout(800);
  const measuresRendered = await page.locator('.measure-item').count();
  return { found, nowOn: measuresRendered > 0, how: `.accordion-header ×${opened}`, label, measuresRendered };
}

// ── 小工具 ──────────────────────────────────────────────────────────────────
const log = (...args) => console.log(...args);
const warn = (...args) => console.warn(...args);

function parseArgs(argv) {
  const opts = { headed: false, routes: null, account: 'admin' };
  for (const arg of argv.slice(2)) {
    if (arg === '--headed') opts.headed = true;
    else if (arg.startsWith('--routes=')) {
      opts.routes = arg.slice('--routes='.length).split(',').map((s) => s.trim()).filter(Boolean);
    } else if (arg.startsWith('--as=')) {
      // 第 80 批：以**普通用户**身份审计。用户实测反馈"用普通账号登录时没翻译"，
      // 而此前所有审计都用管理员账号 —— 普通用户能看到的页面其实不一样
      // （没有管理入口、/history 只看得到自己的记录、部分面板按角色渲染）。
      opts.account = arg.slice('--as='.length).trim();
      if (!['admin', 'user'].includes(opts.account)) {
        throw new Error(`--as 只支持 admin / user，收到：${opts.account}`);
      }
    }
  }
  return opts;
}

/**
 * 跑 python 夹具脚本，拿它写出的 JSON。
 *
 * ⚠️ 为什么绕一圈走文件：本机 DSH 受限沙箱里，Node 的 child_process 无法打开
 * 命名管道，`spawn(..., { stdio: 'pipe' })` 会直接 `EPERM`（已实测 pipe/shell 均失败，
 * 只有 'inherit' / 'ignore' 可用）。所以这里让子进程把 JSON 写进临时文件，
 * 父进程再读文件 —— 输出用 inherit 直接透传到控制台，日志依然可见。
 */
function runJsonScript(scriptName, extraArgs = []) {
  const outFile = path.join(os.tmpdir(), `dsh-i18n-audit-seed-${process.pid}.json`);
  return new Promise((resolve, reject) => {
    if (existsSync(outFile)) {
      try { rmSync(outFile); } catch { /* 忽略 */ }
    }
    const child = spawn(PYTHON, [scriptName, `--out=${outFile}`, ...extraArgs], {
      cwd: BACKEND_DIR,
      windowsHide: true,
      stdio: ['ignore', 'inherit', 'inherit'],
    });
    child.on('error', (err) => {
      reject(new Error(
        `无法启动 python（${PYTHON}）：${err.code || err.message}\n`
        + '提示：可用 I18N_AUDIT_PYTHON 环境变量指定解释器。',
      ));
    });
    child.on('close', async (code) => {
      if (code !== 0) {
        reject(new Error(`${scriptName} 退出码 ${code}（详见上方 python 输出）`));
        return;
      }
      try {
        const raw = await readFile(outFile, 'utf8');
        resolve(JSON.parse(raw));
      } catch (err) {
        reject(new Error(`读取夹具 JSON 失败（${outFile}）：${err.message}`));
      } finally {
        await rm(outFile, { force: true }).catch(() => {});
      }
    });
  });
}

/** 去重 + trim，保持原出现顺序 */
function dedupe(lines) {
  const seen = new Set();
  const out = [];
  for (const line of lines) {
    const value = line.trim();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    out.push(value);
  }
  return out;
}

/** innerText → 含汉字的行 */
function extractCjkLines(rawText) {
  return dedupe(rawText.split(/\r?\n/).filter((line) => CJK_RE.test(line)));
}

// ── /history 专用：打开「查看全部用户」开关 ─────────────────────────────────
/**
 * 开关的三种可能实现都要兼容（ElSwitch 的 DOM 结构随版本变）：
 *   ① 语义化 role="switch" + aria-checked（Element Plus 2.x 会给）
 *   ② .el-switch 根节点的 is-checked class
 *   ③ 兜底：点它旁边那句英文 label
 * 返回 { found, wasOn, nowOn, how } 供报告说明，避免"静默没打开"。
 */
async function enableViewAllUsers(page) {
  const SWITCH_LABEL = 'View all users';

  // 先确认开关确实存在（正文里能找到那句英文说明）
  const labelVisible = await page
    .getByText(SWITCH_LABEL, { exact: false })
    .first()
    .isVisible()
    .catch(() => false);
  const switchCount = await page.locator('.el-switch').count();
  if (!labelVisible && switchCount === 0) {
    return { found: false, wasOn: null, nowOn: null, how: 'no el-switch / label on page' };
  }

  const root = page.locator('.el-switch').first();
  const hasRoot = switchCount > 0;

  const isOn = async () => {
    if (hasRoot) {
      const cls = (await root.getAttribute('class').catch(() => '')) || '';
      if (cls.includes('is-checked')) return true;
      const aria = await root.locator('[role="switch"], input').first().getAttribute('aria-checked').catch(() => null);
      if (aria != null) return aria === 'true';
      const inputChecked = await root.locator('input[type="checkbox"]').first().isChecked().catch(() => null);
      if (inputChecked != null) return inputChecked;
    }
    return false;
  };

  const wasOn = await isOn();
  if (wasOn) return { found: true, wasOn, nowOn: true, how: 'already checked' };

  let how = 'click .el-switch';
  try {
    if (hasRoot) {
      await root.click({ timeout: 5_000 });
    } else {
      how = 'click label text';
      await page.getByText(SWITCH_LABEL, { exact: false }).first().click({ timeout: 5_000 });
    }
  } catch (err) {
    // 兜底：直接派发 click 到 .el-switch__core
    how = `dispatchEvent on .el-switch__core after error: ${err.message.split('\n')[0]}`;
    await page.locator('.el-switch__core').first().dispatchEvent('click').catch(() => {});
  }

  await page.waitForTimeout(500);
  const nowOn = await isOn();
  if (nowOn) {
    // 开关会触发 all_users=true 的重新请求，多等一会儿让卡片与图表刷新
    await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});
    await page.waitForTimeout(EXTRA_SETTLE_MS);
  }
  return { found: true, wasOn, nowOn, how };
}

// ── Chart.js：读 canvas 背后的图表数据 ─────────────────────────────────────
/**
 * 在页面上下文里执行：从每个 <canvas> 出发，沿 Vue 组件树向上找
 * vue-chartjs 通过 `expose({ chart })` 暴露出来的 Chart.js 实例。
 *
 * 为什么不用 `Chart.getChart(canvas)`：那需要 `chart.js` 的模块命名空间，
 * 而它是 ESM 打包产物，页面里**没有** window.Chart（除非应用自己挂）。
 * 因此优先走 Vue 内部实例，其次才试 window.Chart，两条都不通就如实报告"读不到"。
 */
const PAGE_READ_CHARTS = () => {
  const INSTANCE_KEY = '__vueParentComponent';
  const MAX_DEPTH = 60;

  const looksLikeChart = (value) => Boolean(
    value && typeof value === 'object'
      && typeof value.update === 'function'
      && value.config
      && value.config.data,
  );

  const unwrap = (value) => {
    // ref / shallowRef / reactive → 原始对象（不 import Vue，靠特征判断）
    if (value && typeof value === 'object' && 'value' in value && looksLikeChart(value.value)) return value.value;
    return value;
  };

  const visited = new Set();

  /** 先看自己在 setup 里 expose 了什么，再递归子组件 */
  const findInInstance = (instance, depth = 0) => {
    if (!instance || depth > MAX_DEPTH || visited.has(instance)) return null;
    visited.add(instance);

    const exposed = instance.exposed;
    if (exposed) {
      const candidate = unwrap(exposed.chart);
      if (looksLikeChart(candidate)) return candidate;
      for (const key of Object.keys(exposed)) {
        const value = unwrap(exposed[key]);
        if (looksLikeChart(value)) return value;
      }
    }

    const visit = (vnode) => {
      if (!vnode || typeof vnode !== 'object') return null;
      if (vnode.component) {
        const inner = findInInstance(vnode.component, depth + 1);
        if (inner) return inner;
      }
      const children = vnode.children;
      if (Array.isArray(children)) {
        for (const child of children) {
          const found = visit(child);
          if (found) return found;
        }
      }
      return null;
    };

    return visit(instance.subTree);
  };

  const results = [];
  const canvases = Array.from(document.querySelectorAll('canvas'));
  canvases.forEach((canvas, index) => {
    const entry = {
      index,
      width: canvas.width,
      height: canvas.height,
      method: null,
      labels: [],
      datasetLabels: [],
      error: null,
    };
    try {
      // 路线 A：canvas 的父元素上挂着 vue-chartjs 组件实例
      let node = canvas.parentElement;
      let chart = null;
      while (node && !chart) {
        chart = findInInstance(node[INSTANCE_KEY]);
        node = node.parentElement;
      }
      if (chart) entry.method = 'vue-component-instance';

      // 路线 B：万一应用把 Chart 挂到了 window 上
      if (!chart && typeof window.Chart?.getChart === 'function') {
        const viaGlobal = window.Chart.getChart(canvas);
        if (looksLikeChart(viaGlobal)) { chart = viaGlobal; entry.method = 'window.Chart.getChart'; }
      }

      if (!chart) {
        entry.error = 'no Chart.js instance reachable from this canvas';
        results.push(entry);
        return;
      }

      const data = chart.config.data || {};
      entry.labels = (data.labels || []).map((l) => String(l));
      entry.datasetLabels = (data.datasets || []).map((d) => String(d?.label ?? ''));
    } catch (err) {
      entry.error = `${err.name}: ${err.message}`;
    }
    results.push(entry);
  });

  return results;
};

// ── 浏览器获取：先常规 launch，被沙箱挡住则回退到手动拉起 + connectOverCDP ──
/**
 * 本机 DSH 受限沙箱禁止进程打开命名管道，于是：
 *   · `chromium.launch()` 内部用 `--remote-debugging-pipe`（命名管道）→ spawn EPERM；
 *   · 而普通 `spawn(..., { stdio: 'ignore' })` 起浏览器 + `--remote-debugging-port`
 *     （走 localhost TCP，不是管道）完全可用。
 * 所以这里做两级策略：① 正常 launch；② 失败退化为"自己起浏览器 + connectOverCDP"。
 * 回退是**功能等价**的：仍然拿到真实 Chromium、真实渲染、真实截图。
 */
/**
 * 解析"回退方案"要用的 Chromium 可执行文件。
 *
 * 关键坑（本机实测）：`chromium.executablePath()` 返回的是**完整版** chrome.exe，
 * 而这台机器上完整版带 `--headless=new` 起不来（进程立刻退出，CDP 端口从不监听）。
 * Playwright 自己跑 headless 时用的是 `chromium_headless_shell-<rev>/chrome-win/headless_shell.exe`，
 * 它工作正常 —— 所以优先找 headless_shell。
 */
function resolveChromiumExecutable({ headed }) {
  const override = process.env.I18N_AUDIT_CHROMIUM;
  if (override) {
    if (!existsSync(override)) throw new Error(`I18N_AUDIT_CHROMIUM 指向的文件不存在：${override}`);
    return override;
  }

  // 想看界面时只能用完整版 chrome（headless_shell 没有窗口）
  if (headed) {
    const full = chromium.executablePath();
    if (!existsSync(full)) throw new Error(`找不到 Chromium：${full}`);
    return full;
  }

  const browsersRoot = process.env.PLAYWRIGHT_BROWSERS_PATH
    || path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'), 'ms-playwright');
  if (existsSync(browsersRoot)) {
    const candidates = [];
    for (const dir of readdirSync(browsersRoot)) {
      if (!dir.startsWith('chromium_headless_shell')) continue;
      candidates.push(path.join(browsersRoot, dir, 'chrome-win', 'headless_shell.exe'));
      candidates.push(path.join(browsersRoot, dir, 'chrome-linux', 'headless_shell'));
    }
    const found = candidates.find((p) => existsSync(p));
    if (found) return found;
  }

  // 兜底：Playwright 自己给的路径（可能仍能跑，先试）
  const fallback = chromium.executablePath();
  if (existsSync(fallback)) {
    warn(`   ! 没找到 headless_shell，回退用 ${fallback}`);
    return fallback;
  }
  throw new Error(`找不到任何 Chromium 可执行文件（已查 ${browsersRoot}）`);
}

async function launchViaCdp(opts) {
  const executablePath = resolveChromiumExecutable(opts);
  const isHeadlessShell = /headless_shell/i.test(executablePath);

  const userDataDir = path.join(os.tmpdir(), `dsh-i18n-audit-profile-${process.pid}`);
  await rm(userDataDir, { recursive: true, force: true }).catch(() => {});

  const args = [
    `--remote-debugging-port=${CDP_PORT}`,
    `--user-data-dir=${userDataDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-dev-shm-usage',
    '--no-sandbox',
    '--disable-extensions',
    '--hide-scrollbars',
    `--window-size=${VIEWPORT.width},${VIEWPORT.height}`,
    'about:blank',
  ];
  // headless_shell 本身就是无头的，只要一个 --headless 开关
  if (!opts.headed) {
    args.unshift(isHeadlessShell ? '--headless' : '--headless=new');
  } else {
    args.unshift('--start-maximized');
  }

  log(`   · 回退方案：直接启动 ${path.basename(executablePath)}（--remote-debugging-port=${CDP_PORT}）`);
  const child = spawn(executablePath, args, { stdio: 'ignore', windowsHide: true });
  child.on('error', (err) => warn(`   ! 浏览器进程启动错误：${err.code || err.message}`));

  const endpoint = `http://${CDP_HOST}:${CDP_PORT}`;
  const deadline = Date.now() + CDP_BOOT_TIMEOUT;
  let version = null;
  while (Date.now() < deadline) {
    try {
      const resp = await fetch(`${endpoint}/json/version`);
      if (resp.ok) { version = await resp.json(); break; }
    } catch { /* 还没起来，继续等 */ }
    if (child.exitCode !== null) {
      throw new Error(`浏览器进程已退出（exitCode=${child.exitCode}）：${executablePath}`);
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  if (!version) {
    try { child.kill(); } catch { /* 忽略 */ }
    throw new Error(`等待 CDP 端点 ${endpoint} 超时（${CDP_BOOT_TIMEOUT}ms）`);
  }
  log(`   · CDP 就绪：${version.Browser}`);

  const browser = await chromium.connectOverCDP(endpoint);
  return {
    browser,
    spawned: child,
    userDataDir,
    note: `chromium.launch() 被沙箱拒绝（spawn EPERM），已回退为「自起 ${path.basename(executablePath)} + connectOverCDP(${endpoint})」；真实 Chromium 渲染，能力等价`,
  };
}

async function launchBrowser(opts) {
  try {
    const browser = await chromium.launch({ headless: !opts.headed, args: ['--disable-dev-shm-usage'] });
    return { browser, spawned: null, userDataDir: null, note: null };
  } catch (err) {
    const code = err?.message?.includes('EPERM') || err?.code === 'EPERM';
    if (!code) throw err;
    warn('   ! chromium.launch() 失败（spawn EPERM）——启用 CDP 回退方案');
    return launchViaCdp(opts);
  }
}

/** 关闭浏览器与自起进程，并清理临时 profile */
async function closeBrowser(handle) {
  if (!handle) return;
  try { await handle.browser?.close(); } catch { /* 忽略 */ }
  if (handle.spawned) {
    try { handle.spawned.kill(); } catch { /* 忽略 */ }
    // 给 Chromium 一点时间自己退出，再兜底强杀
    await new Promise((r) => setTimeout(r, 1_200));
    try { handle.spawned.kill('SIGKILL'); } catch { /* 忽略 */ }
  }
  if (handle.userDataDir) {
    await rm(handle.userDataDir, { recursive: true, force: true, maxRetries: 3 }).catch(() => {});
  }
}

// ── 单页审计 ────────────────────────────────────────────────────────────────
async function auditRoute(page, route, options) {
  const url = `${BASE_URL}${route.path}`;
  const result = {
    page: route.page,
    requestedPath: route.path,
    requestedUrl: url,
    finalUrl: null,
    httpStatus: null,
    status: 'ok',
    notes: [],
    headingText: null,
    switchState: null,
    cjkLines: [],
    cjkFromCharts: [],
    chartReadout: { supported: false, method: null, canvases: 0, chartsRead: 0, errors: [] },
    screenshot: null,
  };

  log(`\n── ${route.page}  (${route.path}) ${'─'.repeat(Math.max(0, 46 - route.page.length))}`);

  let response;
  try {
    response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
  } catch (err) {
    result.status = 'navigation-failed';
    result.notes.push(`page.goto 失败：${err.message.split('\n')[0]}`);
    warn(`   ✗ 导航失败：${err.message.split('\n')[0]}`);
    return result;
  }

  result.httpStatus = response?.status() ?? null;
  await page.waitForLoadState('networkidle', { timeout: NAV_TIMEOUT }).catch(() => {
    result.notes.push('networkidle 超时（可能有轮询/长连接），改用固定沉降时间继续');
  });

  const landedUrl = page.url();
  result.finalUrl = landedUrl;

  // 被守卫踢到登录页 = 认证失败，必须明说，不能报"空列表即成功"
  if (new URL(landedUrl).pathname.startsWith('/login')) {
    result.status = 'redirected-to-login';
    result.notes.push(`被重定向到登录页（认证态无效）：${landedUrl}`);
    warn(`   ✗ 被重定向到 /login：${landedUrl}`);
  }

  // 等页面标题出现，确认"渲染完成了"而不是白屏
  let headingText = null;
  try {
    const h1 = page.locator('h1').first();
    await h1.waitFor({ state: 'visible', timeout: HEADING_TIMEOUT });
    headingText = (await h1.innerText()).trim();
  } catch {
    result.notes.push(`等 <h1> 超时（${HEADING_TIMEOUT}ms），可能渲染失败或结构不同`);
  }
  result.headingText = headingText;

  if (headingText && route.heading && !headingText.includes(route.heading)) {
    if (/404|not found/i.test(headingText)) {
      result.status = 'not-found';
      result.notes.push(`渲染出 404 页面（h1="${headingText}"）`);
      warn(`   ✗ 页面是 404：h1="${headingText}"`);
    } else {
      result.notes.push(`h1="${headingText}" 与预期 "${route.heading}" 不一致（页面结构可能变了，仍继续抓取）`);
      warn(`   ! h1="${headingText}"，预期包含 "${route.heading}"`);
    }
  }
  if (headingText && result.status === 'ok') log(`   h1: "${headingText}"`);

  // 页面级特殊处理
  if (typeof route.setup === 'function' && result.status === 'ok') {
    const state = await route.setup(page);
    result.switchState = state;
    const setupLabel = state?.label || 'View all users';
    if (state?.found === false) {
      result.notes.push(`页面上的「${setupLabel}」没有找到，抓取的内容可能不完整`);
      warn(`   ! 没找到「${setupLabel}」`);
    } else {
      if (!state.nowOn) {
        result.notes.push(`「${setupLabel}」存在但**没能生效**（wasOn=${state.wasOn}, nowOn=${state.nowOn}, how=${state.how}）`);
        warn(`   ! 「${setupLabel}」没能生效：${state.how}`);
      } else {
        log(`   ✓ 「${setupLabel}」已生效（${state.how}）`);
      }
    }
  }

  // 等 Chart.js 画完：canvas 有尺寸 + 至少一个 dataset 有数据点
  await page.waitForFunction(() => {
    const canvases = Array.from(document.querySelectorAll('canvas'));
    if (canvases.length === 0) return true; // 本页没有图表
    return canvases.every((c) => c.width > 0 && c.height > 0);
  }, null, { timeout: 15_000 }).catch(() => {});
  await page.waitForTimeout(SETTLE_MS);

  // 截图（整页）
  await mkdir(SHOTS_DIR, { recursive: true });
  const shotPath = path.join(SHOTS_DIR, `i18n-${route.page}.png`);
  try {
    await page.screenshot({ path: shotPath, fullPage: true });
    result.screenshot = shotPath;
    log(`   📷 ${shotPath}`);
  } catch (err) {
    result.notes.push(`截图失败：${err.message.split('\n')[0]}`);
    warn(`   ! 截图失败：${err.message.split('\n')[0]}`);
  }

  // 正文可见文本
  const rawText = await page.evaluate(() => document.body?.innerText ?? '');
  result.cjkLines = extractCjkLines(rawText);

  const punctOnly = rawText
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !CJK_RE.test(l) && CJK_PUNCT_RE.test(l));
  if (punctOnly.length) {
    result.notes.push(`另有 ${dedupe(punctOnly).length} 行只含全角标点、不含汉字（未计入清单）：${dedupe(punctOnly).slice(0, 3).join(' | ')}`);
  }

  // canvas / Chart.js 数据
  let charts = [];
  try {
    charts = await page.evaluate(PAGE_READ_CHARTS);
  } catch (err) {
    result.chartReadout.errors.push(`页面内读取图表异常：${err.message.split('\n')[0]}`);
    charts = [];
  }
  result.chartReadout.canvases = charts.length;
  const readable = charts.filter((c) => !c.error);
  result.chartReadout.chartsRead = readable.length;
  result.chartReadout.supported = charts.length > 0 && readable.length > 0;
  const methods = [...new Set(readable.map((c) => c.method).filter(Boolean))];
  result.chartReadout.method = methods.length ? methods.join(', ') : null;
  const chartErrors = charts.filter((c) => c.error).map((c) => `canvas#${c.index}: ${c.error}`);
  if (chartErrors.length) result.chartReadout.errors.push(...chartErrors);

  if (charts.length === 0) {
    result.chartReadout.note = '本页没有 <canvas>（无 Chart.js 图表）';
  } else if (!result.chartReadout.supported) {
    result.chartReadout.note =
      '页面有 <canvas> 但 Chart.js 实例**不可达**（chart.js 的 ESM 命名空间没有挂到 window，'
      + 'Vue 组件树里也没找到 expose 的 chart）——按要求不做猜测，图表内文字**未纳入**本次清单。';
    warn(`   ! 图表数据读不到：${chartErrors.join('; ') || 'unknown'}`);
  } else {
    log(`   ✓ 读到 ${readable.length}/${charts.length} 个 Chart.js 实例（via ${result.chartReadout.method}）`);
  }

  const chartLines = [];
  for (const chart of readable) {
    for (const label of [...chart.labels, ...chart.datasetLabels]) {
      if (CJK_RE.test(label)) chartLines.push(`canvas#${chart.index}: ${label.trim()}`);
    }
  }
  result.cjkFromCharts = dedupe(chartLines);

  // 汇总
  if (result.status === 'ok') {
    log(`   正文含汉字行：${result.cjkLines.length}；图表含汉字项：${result.cjkFromCharts.length}`);
    for (const line of result.cjkLines.slice(0, 5)) log(`     · ${line.slice(0, 100)}`);
    if (result.cjkLines.length > 5) log(`     … 其余见 JSON`);
  }
  for (const note of result.notes) warn(`   note: ${note}`);

  return result;
}

// ── 主流程 ──────────────────────────────────────────────────────────────────
async function main() {
  const opts = parseArgs(process.argv);

  log('════════════════════════════════════════════════════════════════');
  log(' i18n CJK 残留审计（英文界面）');
  log('════════════════════════════════════════════════════════════════');
  log(` 前端: ${BASE_URL}`);
  log(` 后端: ${API_URL}`);

  // ① 造/复用临时审计账号（临时夹具，见 backend/_seed_i18n_audit_tmp.py）
  log(`\n[1/4] 准备临时审计账号…（身份：${opts.account === 'user' ? '普通用户' : '管理员'}）`);
  const seed = await runJsonScript(SEED_SCRIPT, [`--role=${opts.account}`]);
  log(`   ✓ ${seed.username}（id=${seed.user_id}, role=${seed.role}, 检测记录 ${seed.detection_history_count} 条）`);

  // ② 走**正常登录接口**拿真实 token（这也是对"该账号能正常登录"的验证）
  log('\n[2/4] 通过 /api/login/ 正常登录…');
  const api = await playwrightRequest.newContext({ baseURL: API_URL, timeout: 30_000 });
  const loginResp = await api.post('/api/login/', {
    data: { username: seed.username, password: seed.password },
  });
  if (!loginResp.ok()) {
    throw new Error(`登录接口返回 ${loginResp.status()}：${(await loginResp.text()).slice(0, 300)}`);
  }
  const loginBody = await loginResp.json();
  const token = loginBody?.data?.token;
  const user = loginBody?.data?.user;
  if (!token || !user) throw new Error(`登录响应缺少 token/user：${JSON.stringify(loginBody).slice(0, 300)}`);
  log(`   ✓ 登录成功：${user.username} is_staff=${user.is_staff} is_superuser=${user.is_superuser} role=${user.role}`);

  // 普通用户进不了 /admin/*（路由守卫会挡回去并弹提示），
  // 把这些页面排除掉，避免把"被挡回上一页"误报成"页面没渲染"。
  const adminOnly = new Set(['admin-dashboard', 'admin-users', 'admin-review', 'admin-news', 'admin-feedback']);
  const availableRoutes = opts.account === 'user'
    ? ROUTES.filter((r) => !adminOnly.has(r.page))
    : ROUTES;

  const routes = opts.routes
    ? availableRoutes.filter((r) => opts.routes.includes(r.page) || opts.routes.includes(r.path))
    : availableRoutes;
  if (!routes.length) throw new Error(`--routes 没匹配到任何页面；可选：${ROUTES.map((r) => r.page).join(', ')}`);

  // ③ 浏览器
  log('\n[3/4] 启动 Chromium 并逐页审计…');
  const browserHandle = await launchBrowser(opts);
  if (browserHandle.note) warn(`   ! ${browserHandle.note}`);
  const context = await browserHandle.browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 1,
    locale: 'en-US',
  });

  // 必须在应用启动**之前**把语言与登录态写进 storage，
  // 否则 i18n 模块顶层的 `ref(readStoredLocale())` 已经读过中文默认值了。
  await context.addInitScript(({ seededToken, seededUser }) => {
    try {
      window.localStorage.setItem('app_locale', 'en');
      window.localStorage.setItem('auth_token', seededToken);
      window.localStorage.setItem('user', JSON.stringify(seededUser));
      window.sessionStorage.setItem('auth_token', seededToken);
      window.sessionStorage.setItem('user', JSON.stringify(seededUser));
    } catch { /* 存储不可用时忽略 */ }
  }, { seededToken: token, seededUser: user });

  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text().slice(0, 300));
  });
  page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message.split('\n')[0]}`));

  const results = [];
  try {
    for (const route of routes) {
      results.push(await auditRoute(page, route, opts));
    }
  } finally {
    await context.close().catch(() => {});
    await closeBrowser(browserHandle);
    await api.dispose();
  }

  // ④ 报告
  log('\n[4/4] 结果汇总');
  log('════════════════════════════════════════════════════════════════');

  const findings = {};
  let totalLines = 0;
  for (const r of results) {
    const lines = r.cjkLines;
    findings[r.page] = lines;
    totalLines += lines.length;

    const badge = r.status === 'ok' ? '✓' : '✗';
    log(`\n${badge} ${r.requestedPath}  —  ${r.status}`);
    log(`   URL: ${r.finalUrl}`);
    if (r.headingText) log(`   标题: ${r.headingText}`);
    if (r.switchState) log(`   开关: found=${r.switchState.found} wasOn=${r.switchState.wasOn} nowOn=${r.switchState.nowOn} (${r.switchState.how})`);
    log(`   图表: canvas=${r.chartReadout.canvases} 可读=${r.chartReadout.chartsRead}` +
      `${r.chartReadout.method ? ` via ${r.chartReadout.method}` : ''}`);
    if (r.chartReadout.note) log(`         ${r.chartReadout.note}`);

    if (r.status !== 'ok') {
      log(`   ⚠ 本页**没有**得到可信结果，不把空清单当作通过。原因：`);
      for (const note of r.notes) log(`     - ${note}`);
    } else if (lines.length === 0) {
      log('   ✅ 未发现残留中文');
    } else {
      log(`   ⚠ 残留中文 ${lines.length} 行：`);
      lines.forEach((line, i) => log(`     ${String(i + 1).padStart(2)}. ${line}`));
    }
    if (r.cjkFromCharts.length) {
      log(`   ⚠ 图表（canvas/Chart.js）内含中文 ${r.cjkFromCharts.length} 项：`);
      r.cjkFromCharts.forEach((line, i) => log(`     ${String(i + 1).padStart(2)}. ${line}`));
    }
    if (r.screenshot) log(`   截图: ${r.screenshot}`);
    if (r.notes.length && r.status === 'ok') {
      for (const note of r.notes) log(`   note: ${note}`);
    }
  }

  log('\n────────────────────────────────────────────────────────────────');
  log(` 合计：${results.length} 个页面，正文残留中文 ${totalLines} 行`);
  const bad = results.filter((r) => r.status !== 'ok').map((r) => `${r.page}(${r.status})`);
  if (bad.length) log(` 未取得可信结果的页面：${bad.join(', ')}`);
  if (consoleErrors.length) {
    const uniq = [...new Set(consoleErrors)];
    log(` 浏览器控制台错误 ${uniq.length} 类（前 5 条）：`);
    uniq.slice(0, 5).forEach((e) => log(`   ! ${e}`));
  }

  // 机器可读 JSON（既打印也落盘，方便以后 diff）
  const payload = {
    generatedAt: new Date().toISOString(),
    baseUrl: BASE_URL,
    locale: 'en',
    viewport: VIEWPORT,
    account: seed.username,
    page: findings,
    details: results.map((r) => ({
      page: r.page,
      requestedPath: r.requestedPath,
      finalUrl: r.finalUrl,
      httpStatus: r.httpStatus,
      status: r.status,
      headingText: r.headingText,
      switchState: r.switchState,
      chartReadout: r.chartReadout,
      cjkFromCharts: r.cjkFromCharts,
      notes: r.notes,
      screenshot: r.screenshot,
      count: r.cjkLines.length,
    })),
    totals: { pages: results.length, cjkLines: totalLines },
  };

  await mkdir(SHOTS_DIR, { recursive: true });
  const jsonPath = path.join(SHOTS_DIR, 'i18n-audit.json');
  await writeFile(jsonPath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');

  log('\n机器可读结果：');
  log(JSON_BEGIN);
  log(JSON.stringify({ page: findings }, null, 2));
  log(JSON_END);
  log(`\n已写入：${jsonPath}`);
  return 0;
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error('\n[FATAL] 审计脚本自身出错（这不是"发现中文"，而是环境/脚本问题）：');
    console.error(err?.stack || String(err));
    process.exit(1);
  });
