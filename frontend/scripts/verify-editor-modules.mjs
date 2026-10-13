/**
 * 信息编辑员「各自的功能」—— 前端侧栏与拦截（第 178 批）
 * ============================================================================
 * 后端那一半已经由 `api.tests.RoleMatrixTests` 钉住了（拿矩阵表真请求每个接口）。
 * 这一支验**农户/编辑员看到的那一半**：控制台侧栏显示哪几项、直接输网址进不进得去。
 *
 * 本脚本验证（三种身份各一遍）：
 *   ① **只勾「新闻管理」的编辑员**：侧栏只有 数据看板 + 新闻管理；
 *      直接输 /admin/pests 进不去（能看到"无权限"或跳走），而且**不显示**别的入口
 *   ② **只勾「病害百科」的编辑员**：侧栏只有 数据看板 + 病害百科维护
 *   ③ **全权管理员**：侧栏有全部入口（含系统健康/操作日志这些仅全权的）
 *
 * 为什么值得做：后端 403 只保证"拿不到数据"，而农户/编辑员感受的是**界面** ——
 * 侧栏列出一个点进去 403 的入口，等于把人往墙上引。
 *
 * 用法：node scripts/verify-editor-modules.mjs
 */
import { chromium } from '@playwright/test';
import { clearThrottle, runDjango } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';   // 管理端在桌面端前端（Element Plus 那套）
const PASS = 'ZzEditor!2026';

const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

clearThrottle();

// 造三个账号：news-only 编辑员 / pests-only 编辑员 / （用现成的 admin）
const seed = runDjango([
  'import json',
  'from django.contrib.auth import get_user_model',
  'from rest_framework.authtoken.models import Token',
  'from api.serializers import CustomUserSerializer',
  'from api.models import EditorModuleGrant',
  'User = get_user_model()',
  "admin = User.objects.get(username='admin')",
  'def make(name, module):',
  "    u, _ = User.objects.get_or_create(username=name, defaults={'role': 'EDITOR'})",
  "    u.set_password('" + PASS + "')",
  "    u.role = 'EDITOR'",
  "    u.is_active = True",
  "    u.is_deleted = False",
  "    u.save()",
  '    EditorModuleGrant.objects.filter(user=u).delete()',
  '    EditorModuleGrant.objects.create(user=u, module=module, granted_by=admin)',
  '    return u',
  "make('zz_editor_news', 'news')",
  "make('zz_editor_pests', 'pests')",
  "print('ZZ_ADMIN_TOKEN=' + Token.objects.get_or_create(user=admin)[0].key)",
  "print('ZZ_ADMIN_USER=' + json.dumps(CustomUserSerializer(admin).data, ensure_ascii=False))",
]);
const adminToken = /ZZ_ADMIN_TOKEN=(\S+)/.exec(seed)?.[1];
const adminUser = /ZZ_ADMIN_USER=(.+)/.exec(seed)?.[1];

const AUTHED = { viewport: { width: 1500, height: 950 }, locale: 'zh-CN' };
const browser = await chromium.launch();
const errors = [];

/** 用登录表单登进去（真实路径：编辑员也要能登录） */
const login = async (page, username) => {
  await page.goto(`${UI}/admin/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1800);
  const inputs = page.locator('input');
  await inputs.nth(0).fill(username);
  await inputs.nth(1).fill(PASS);
  await page.getByRole('button', { name: /登录/ }).first().click();
  await page.waitForTimeout(3500);
  return page.url();
};

const sidebarText = async (page) => {
  await page.waitForTimeout(1500);
  // 只看**侧栏**：整页文本里"内容审核/意见反馈"这些字在数据看板的统计卡片上也有，
  // 用 body 判断必然误报（第一版就误报了两条）
  const sidebar = page.locator('.admin-sidebar').first();
  if (await sidebar.count()) return (await sidebar.innerText()).replace(/\s+/g, ' ');
  return (await page.locator('body').innerText()).replace(/\s+/g, ' ');
};

// ---------------------------------------------------------------------------
// ① 只勾新闻管理的编辑员
// ---------------------------------------------------------------------------
const ctx1 = await browser.newContext(AUTHED);
const p1 = await ctx1.newPage();
p1.on('pageerror', (e) => errors.push(String(e).slice(0, 160)));
const url1 = await login(p1, 'zz_editor_news');
check('新闻编辑员能登录并进后台', !url1.includes('/admin/login'), url1);

const text1 = await sidebarText(p1);
check('侧栏有「新闻管理」', text1.includes('新闻管理'), '');
check('侧栏没有「内容审核」', !text1.includes('内容审核'), '');
check('侧栏没有「病害百科维护」', !text1.includes('病害百科维护'), '');
check('侧栏没有「意见反馈管理」', !text1.includes('意见反馈管理'), '');
check('侧栏没有「用户管理」', !text1.includes('用户管理'), '');
check('侧栏没有「版块管理」（BROADCAST 能力）', !text1.includes('版块管理'), '');
check('侧栏没有「系统健康」「操作日志」（仅全权）',
  !text1.includes('系统健康') && !text1.includes('操作日志'), '');
await p1.screenshot({ path: 'dsh-shots/editor-news-sidebar.png' });

// 直接输网址：拿不到百科页面
await p1.goto(`${UI}/admin/pests`, { waitUntil: 'domcontentloaded' });
await p1.waitForTimeout(3000);
const pestsText = await sidebarText(p1);
const blocked = !pestsText.includes('批量导入') || p1.url().includes('/admin/login');
check('新闻编辑员直接输 /admin/pests 进不去百科维护页', blocked,
  `${p1.url()} ｜ 含"批量导入"=${pestsText.includes('批量导入')}`);

// ---------------------------------------------------------------------------
// ② 只勾病害百科的编辑员
// ---------------------------------------------------------------------------
const ctx2 = await browser.newContext(AUTHED);
const p2 = await ctx2.newPage();
p2.on('pageerror', (e) => errors.push(String(e).slice(0, 160)));
await login(p2, 'zz_editor_pests');
const text2 = await sidebarText(p2);
check('百科编辑员侧栏有「病害百科维护」', text2.includes('病害百科维护'), '');
check('百科编辑员侧栏没有「新闻管理」', !text2.includes('新闻管理'), '');
check('百科编辑员侧栏没有「用户管理」', !text2.includes('用户管理'), '');
await p2.screenshot({ path: 'dsh-shots/editor-pests-sidebar.png' });

// ---------------------------------------------------------------------------
// ③ 全权管理员：入口齐全
// ---------------------------------------------------------------------------
const ctx3 = await browser.newContext(AUTHED);
const p3 = await ctx3.newPage();
p3.on('pageerror', (e) => errors.push(String(e).slice(0, 160)));
await p3.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
await p3.evaluate(([tk, us]) => {
  window.sessionStorage.setItem('auth_token', tk);
  window.sessionStorage.setItem('user', us);
}, [adminToken, adminUser]);
await p3.goto(`${UI}/admin/dashboard`, { waitUntil: 'domcontentloaded' });
const text3 = await sidebarText(p3);
for (const [label, need] of [
  ['用户管理', '用户管理'], ['内容审核', '内容审核'], ['论坛管理', '论坛管理'],
  ['评论管理', '评论管理'], ['新闻管理', '新闻管理'], ['病害百科维护', '病害百科维护'],
  ['意见反馈管理', '意见反馈管理'], ['版块管理', '版块管理'],
  ['系统健康', '系统健康'], ['操作日志', '操作日志'],
]) {
  check(`管理员侧栏有「${label}」`, text3.includes(need), '');
}
await p3.screenshot({ path: 'dsh-shots/editor-admin-sidebar.png' });

check('全程无 JS 报错', errors.length === 0, errors.slice(0, 2).join(' | '));

await browser.close();

try {
  runDjango([
    'from django.contrib.auth import get_user_model',
    "print('cleaned:', get_user_model().objects.filter(username__startswith='zz_editor_').delete()[0])",
  ]);
} catch (error) {
  console.warn('  清理失败（忽略）:', String(error).slice(0, 100));
}

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
