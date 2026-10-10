/**
 * 「停用账号登录提示」端到端验证（第 142 批）
 * ============================================================================
 * 修的是什么：登录视图里本来就有 `account_disabled` 分支，但它**够不着** ——
 * Django 的 ModelBackend 对 is_active=False 的用户直接返回 None，
 * 于是被停用的账号拿到的提示是「密码错误，还可尝试 4 次」，
 * 而且**每试一次都在扣失败次数**（5 次后还会被临时锁定）：
 * 用户手里是正确密码，却被告知密码错，越试越像自己记错了。
 *
 * 覆盖：
 *   ① 管理端停用某账号后，该账号在**农户登录页**登录 → 看到「该账号已被停用」
 *   ② 反复登录（密码正确）**不消耗失败次数、不锁定**
 *   ③ 管理端「启用」回来后能正常登录
 *   ④ 只输入错误密码时，仍然只说「密码错误」（防枚举：探测不出账号被停用）
 *   ⑤ 英文界面下这句提示是英文（后端那句是中文，前端覆盖成双语）
 *
 * 用法：node scripts/verify-suspended-login.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';

const adminName = `zze2e_sl_admin_${suffix}`;
const victimName = `zze2e_sl_victim_${suffix}`;

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
      'U = get_user_model()',
      "print('cleaned:', U.objects.filter(username__startswith='zze2e_sl_').delete()[0])",
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
  `U.objects.create_user(username='${adminName}', password='${password}', is_staff=True, role='ADMIN')`,
  `U.objects.create_user(username='${victimName}', password='${password}', role='USER')`,
  "print('seeded')",
]);

/** 读目标账号的失败次数/锁定状态（用 Django 直查，避免被接口缓存影响） */
const readState = () => {
  const out = runDjango([
    'from django.contrib.auth import get_user_model',
    'U = get_user_model()',
    `u = U.objects.get(username='${victimName}')`,
    "print('STATE', u.is_active, u.failed_login_attempts, u.is_locked)",
  ]);
  const match = String(out).match(/STATE (\w+) (\d+) (\w+)/);
  return match ? { isActive: match[1] === 'True', attempts: Number(match[2]), locked: match[3] === 'True' } : null;
};

const browser = await chromium.launch();

/** 在农户登录页尝试登录，返回页面上显示的提示 */
const tryLogin = async (pwd, locale = 'zh-CN') => {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 950 }, locale });
  const page = await ctx.newPage();
  await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((l) => localStorage.setItem('app_locale', l), locale === 'en-US' ? 'en' : 'zh');
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForSelector('input[type="password"]', { timeout: 25_000 });
  await page.locator('input#username, input[name="username"], input[type="text"]').first().fill(victimName);
  await page.locator('input[type="password"]').first().fill(pwd);
  await page.locator('button[type="submit"]').first().click();
  await page.waitForTimeout(2500);
  const text = await page.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' '));
  await ctx.close();
  return text;
};

// ---------------------------------------------------------------------------
// ① 停用后登录 → 提示"已停用"
// ---------------------------------------------------------------------------
const adminCtx = await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' });
const adminPage = await adminCtx.newPage();
clearThrottle();
await adminPage.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
await adminPage.waitForSelector('.admin-login');
await adminPage.locator('#username').fill(adminName);
await adminPage.locator('#password').fill(password);
await adminPage.locator('button[type="submit"]').first().click();
await adminPage.waitForURL((u) => u.pathname.startsWith('/admin/') && u.pathname !== '/admin/login', { timeout: 30_000 });

const suspend = await adminPage.evaluate(async ({ api, name }) => {
  const token = sessionStorage.getItem('auth_token');
  const list = await (await fetch(`${api}/admin/users/?search=${name}`, {
    headers: { Authorization: `Token ${token}` },
  })).json();
  const target = (list.results || []).find((u) => u.username === name);
  const res = await fetch(`${api}/admin/users/${target.id}/status/`, {
    method: 'POST',
    headers: { Authorization: `Token ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_active: false }),
  });
  return { status: res.status };
}, { api: 'http://127.0.0.1:8000/api', name: victimName });
check('管理端成功停用该账号', suspend.status === 200, `HTTP ${suspend.status}`);

const suspendedText = await tryLogin(password);
check('登录页提示"已被停用，请联系管理员"', suspendedText.includes('已被停用'), suspendedText.slice(0, 120));
check('提示里不再出现"密码错误"', !suspendedText.includes('密码错误'), suspendedText.slice(0, 120));

// ---------------------------------------------------------------------------
// ② 反复尝试不消耗失败次数
// ---------------------------------------------------------------------------
const stateBefore = readState();
for (let i = 0; i < 6; i += 1) await tryLogin(password);
const stateAfter = readState();
check('反复登录（密码正确）不消耗失败次数',
  stateAfter && stateAfter.attempts === 0 && !stateAfter.locked,
  `尝试前 ${stateBefore?.attempts} → 尝试 6 次后 ${stateAfter?.attempts}，locked=${stateAfter?.locked}`);

// ---------------------------------------------------------------------------
// ④ 错误密码仍然只说"密码错误"（防枚举）
// ---------------------------------------------------------------------------
const wrongText = await tryLogin('definitely-wrong-pw');
check('密码错误时仍只说"密码错误"（不暴露账号被停用）',
  wrongText.includes('密码错误') && !wrongText.includes('停用'), wrongText.slice(0, 100));

// ---------------------------------------------------------------------------
// ⑤ 英文界面下的提示
// ---------------------------------------------------------------------------
const enText = await tryLogin(password, 'en-US');
check('英文界面下提示是英文',
  /suspended/i.test(enText) && !/停用/.test(enText), enText.slice(0, 140));

// ---------------------------------------------------------------------------
// ③ 启用回来后能登录
// ---------------------------------------------------------------------------
const enable = await adminPage.evaluate(async ({ api, name }) => {
  const token = sessionStorage.getItem('auth_token');
  const list = await (await fetch(`${api}/admin/users/?search=${name}`, {
    headers: { Authorization: `Token ${token}` },
  })).json();
  const target = (list.results || []).find((u) => u.username === name);
  const res = await fetch(`${api}/admin/users/${target.id}/status/`, {
    method: 'POST',
    headers: { Authorization: `Token ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_active: true }),
  });
  return res.status;
}, { api: 'http://127.0.0.1:8000/api', name: victimName });
check('管理端成功启用该账号', enable === 200, `HTTP ${enable}`);

clearThrottle();
const backText = await tryLogin(password);
check('启用后能正常登录（不再出现停用提示）',
  !backText.includes('已被停用'), backText.slice(0, 100));

const finalState = readState();
check('整个过程中失败次数始终为 0（停用账号不再被"试到锁定"）',
  finalState && finalState.attempts === 0,
  `最终 failed_login_attempts=${finalState?.attempts}，locked=${finalState?.locked}`);

await browser.close();
cleanup();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
