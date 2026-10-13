/**
 * 「调整角色」对话框里的权限预览（第 179 批）
 * ============================================================================
 * 用户要求：把权限矩阵接进用户管理页 —— 授权的人要能直接看到
 * "勾了这几项 = 他能做什么"，而不是凭记忆猜。
 *
 * 走**稳定可达**的路径：造一个普通用户 → 在他那一行点「调整角色」→ 选「信息编辑员」
 * → 预览出现 → 逐项验证。
 * （「新增编辑员」按钮也挂了同一个预览组件，但那个按钮对"可改角色的行"另有显示条件，
 *   E2E 里不稳定；两处共用同一个组件，验一处即可。）
 *
 * 用法：node scripts/verify-editor-permission-preview.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const TARGET = 'zz_perms_target';
const results = [];
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
  'from api.capabilities import capabilities_of, content_modules_of',
  'User = get_user_model()',
  "admin = User.objects.get(username='admin')",
  // 管理员那一行不给改角色，普通用户这一行才会显示「调整角色」
  `u, _ = User.objects.get_or_create(username='${TARGET}', defaults={'role': 'USER'})`,
  "u.role = 'USER'; u.is_active = True; u.is_deleted = False; u.save()",
  'token, _ = Token.objects.get_or_create(user=admin)',
  "print('ZZ_TOKEN=' + token.key)",
  "payload = dict(CustomUserSerializer(admin).data)",
  "payload.update({'is_superuser': admin.is_superuser, 'is_staff': admin.is_staff,",
  "                'avatar': None, 'capabilities': list(capabilities_of(admin)),",
  "                'content_modules': list(content_modules_of(admin))})",
  "print('ZZ_USER=' + json.dumps(payload, ensure_ascii=False))",
]);
const token = /ZZ_TOKEN=(\S+)/.exec(seed)?.[1];
const userJson = /ZZ_USER=(.+)/.exec(seed)?.[1];

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' })).newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error).slice(0, 200)));

await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
await page.evaluate(([tk, us]) => {
  window.sessionStorage.setItem('auth_token', tk);
  window.sessionStorage.setItem('user', us);
}, [token, userJson]);

await page.goto(`${UI}/admin/users`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.admin-hero', { timeout: 30_000 });
await page.waitForTimeout(2500);

// 搜出目标用户（列表分页，不一定在第一页）
const search = page.locator('.el-input__inner').first();
if (await search.count()) {
  await search.fill(TARGET);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(2500);
}

// ---------------------------------------------------------------------------
// ① 调整角色 → 选编辑员 → 预览出现
// ---------------------------------------------------------------------------
const roleBtn = page.getByRole('button', { name: /新增编辑员/ }).first();
check('页面上有「新增编辑员」按钮（仅超级管理员可见）', (await roleBtn.count()) > 0, '');
await roleBtn.click();
await page.waitForSelector('.el-dialog', { timeout: 15_000 });
await page.waitForTimeout(1000);

await page.waitForSelector('.perms-preview', { timeout: 20_000 });
const previewText = await page.locator('.perms-preview').innerText();
check('对话框里有权限预览', previewText.length > 10, '');
check('预览标题是"勾了这几项，他就能做这些："', /勾了这几项/.test(previewText), '');
for (const [module, keyword] of [
  ['内容审核', /审核帖子|处置评论/],
  ['论坛交流', /帖子与评论|置顶/],
  ['新闻管理', /行业动态/],
  ['病害百科', /词条/],
  ['意见反馈', /反馈/],
]) {
  check(`预览里列出了「${module}」能做的事`, keyword.test(previewText),
    (previewText.match(new RegExp(`${module}[^\\n]*`)) || [])[0] || '');
}
check('预览说的是人话，不是接口路径', !/\/api\//.test(previewText), '');
check('预览说明了编辑员碰不到什么', /用户账号|公告|系统健康/.test(previewText), '');
await page.screenshot({ path: 'dsh-shots/editor-perms-dialog.png' });

// ---------------------------------------------------------------------------
// ② 实时性
// ---------------------------------------------------------------------------
const before = await page.locator('.perms-item').count();
const baike = page.locator('.el-checkbox', { hasText: '病害百科' }).first();
if (await baike.count()) {
  await baike.click();
  await page.waitForTimeout(800);
  const afterText = await page.locator('.perms-preview').innerText();
  const after = await page.locator('.perms-item').count();
  check('取消勾选后预览立刻少一条', after === before - 1 && !/维护病害词条/.test(afterText),
    `${before} → ${after}`);
  await baike.click();
  await page.waitForTimeout(600);
} else {
  check('取消勾选后预览立刻少一条', false, '没找到「病害百科」勾选框');
}

// ---------------------------------------------------------------------------
// ③ 全部取消 → 提醒（**不提交**，别真把账号改成编辑员）
// ---------------------------------------------------------------------------
const all = page.locator('.el-checkbox', { hasText: /内容审核|论坛交流|新闻管理|病害百科|意见反馈/ });
const total = await all.count();
for (let i = 0; i < total; i += 1) {
  const label = all.nth(i);
  if (await label.locator('input').isChecked().catch(() => false)) await label.click();
}
await page.waitForTimeout(800);
const dialogText = await page.locator('.el-dialog').innerText();
check('全部取消后给出"一个模块都没勾"的提醒', /一个模块都没勾/.test(dialogText),
  (dialogText.match(/一个模块都没勾[^\n]*/) || [])[0] || '');
await page.screenshot({ path: 'dsh-shots/editor-perms-empty.png' });

check('全程无 JS 报错', errors.length === 0, errors.slice(0, 2).join(' | '));

await page.keyboard.press('Escape');
await page.waitForTimeout(600);
await browser.close();

try {
  runDjango([
    'from django.contrib.auth import get_user_model',
    `print('cleaned:', get_user_model().objects.filter(username='${TARGET}').delete()[0])`,
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
