/**
 * 取消信息编辑员后，对方页面上的「管理后台」入口要消失（第 180 批）
 * ============================================================================
 * 用户报的问题：管理员把某人的信息编辑员取消掉，那人首页导航栏**还显示「管理后台」**。
 *
 * 查证结论：后端是**对的** —— `capabilities.py` 刻意不做缓存（注释写明"改了权限立刻生效"），
 * 降级时也删掉了 `EditorModuleGrant`。问题在前端：
 * `checkAuth()` 只从本地存储恢复（有 token 就直接 return），**从不向后端核对** ✗ ——
 * 于是浏览器里缓存的 `user.capabilities` / `content_modules` 一直驱动着导航，
 * **刷新页面也不消失**，只有重新登录才会变。那人点进去每个接口都是 403：
 * 「入口还在、里面全拒」，最难排查的一种状态。
 *
 * 修法：`authStore.refreshIdentity()` 在**启动**与**标签页重新可见**时核对一次身份
 * （断网时什么都不做，绝不清登录态）。
 *
 * 本脚本验证的正是这条链路：
 *   ① 有 forum 模块的编辑员 → 首页能看到「管理后台」
 *   ② 管理员把他降回普通用户（role=USER + 删授权）
 *   ③ **刷新页面** → 入口消失 ✓（修之前：仍在 ✗）
 *   ④ 他没有被登出（仍然显示用户名）
 *
 * 用法：node scripts/verify-editor-demote.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const EDITOR = 'zz_demote_editor';
const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

clearThrottle();

/** 造编辑员 + 取得登录形态的身份（含 capabilities / content_modules） */
const seed = runDjango([
  'import json',
  'from django.contrib.auth import get_user_model',
  'from rest_framework.authtoken.models import Token',
  'from api.serializers import CustomUserSerializer',
  'from api.capabilities import capabilities_of, content_modules_of',
  'from api.models import EditorModuleGrant',
  'User = get_user_model()',
  "admin = User.objects.get(username='admin')",
  `u, _ = User.objects.get_or_create(username='${EDITOR}')`,
  "u.role = 'EDITOR'; u.is_active = True; u.is_deleted = False; u.save()",
  "EditorModuleGrant.objects.filter(user=u).delete()",
  "EditorModuleGrant.objects.create(user=u, module='forum', granted_by=admin)",
  'token, _ = Token.objects.get_or_create(user=u)',
  'payload = dict(CustomUserSerializer(u).data)',
  "payload.update({'is_superuser': u.is_superuser, 'is_staff': u.is_staff, 'avatar': None,",
  "                'capabilities': list(capabilities_of(u)),",
  "                'content_modules': list(content_modules_of(u))})",
  "print('ZZ_TOKEN=' + token.key)",
  "print('ZZ_USER=' + json.dumps(payload, ensure_ascii=False))",
]);
const token = /ZZ_TOKEN=(\S+)/.exec(seed)?.[1];
const userJson = /ZZ_USER=(.+)/.exec(seed)?.[1];

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1500, height: 950 }, locale: 'zh-CN' })).newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error).slice(0, 160)));

const loginAsEditor = async () => {
  await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(([tk, us]) => {
    window.sessionStorage.setItem('auth_token', tk);
    window.sessionStorage.setItem('user', us);
  }, [token, userJson]);
  await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
};

// ---------------------------------------------------------------------------
// ① 有 forum 模块 → 能看到「管理后台」
// ---------------------------------------------------------------------------
await loginAsEditor();
const hasEntry = async () => (await page.locator('text=管理后台').count()) > 0;
check('有 forum 模块的编辑员能看到「管理后台」入口', await hasEntry(), '');
await page.screenshot({ path: 'dsh-shots/demote-before.png' });

// ---------------------------------------------------------------------------
// ② 管理员取消编辑员（role → USER，删掉模块授权）
// ---------------------------------------------------------------------------
runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models import EditorModuleGrant',
  'User = get_user_model()',
  `u = User.objects.get(username='${EDITOR}')`,
  "u.role = 'USER'; u.save()",
  'EditorModuleGrant.objects.filter(user=u).delete()',
  "print('已降回普通用户')",
]);

// ---------------------------------------------------------------------------
// ③ 刷新页面 → 入口消失（修之前这里仍然是 true）
// ---------------------------------------------------------------------------
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForTimeout(5000);
check('取消之后**刷新页面**，入口消失（修之前仍在 ✗）', !(await hasEntry()), '');
check('没有被登出（仍显示用户名）', (await page.locator(`text=${EDITOR}`).count()) > 0, '');
await page.screenshot({ path: 'dsh-shots/demote-after.png' });

// ---------------------------------------------------------------------------
// ④ 反向：恢复编辑员 + 刷新 → 入口回来（说明不是"一律不显示"）
// ---------------------------------------------------------------------------
runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models import EditorModuleGrant',
  'User = get_user_model()',
  "admin = User.objects.get(username='admin')",
  `u = User.objects.get(username='${EDITOR}')`,
  "u.role = 'EDITOR'; u.save()",
  "EditorModuleGrant.objects.create(user=u, module='forum', granted_by=admin)",
  "print('恢复编辑员')",
]);
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForTimeout(5000);
check('恢复授权后刷新，入口又回来（权限是双向实时生效的）', await hasEntry(), '');

check('全程无 JS 报错', errors.length === 0, errors.slice(0, 2).join(' | '));

await browser.close();

try {
  runDjango([
    'from django.contrib.auth import get_user_model',
    'from api.models import EditorModuleGrant',
    `u = get_user_model().objects.filter(username='${EDITOR}').first()`,
    'if u:',
    '    EditorModuleGrant.objects.filter(user=u).delete()',
    '    u.delete()',
    "print('cleaned')",
  ]);
} catch (error) {
  console.warn('  清理失败（忽略）:', String(error).slice(0, 90));
}

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
