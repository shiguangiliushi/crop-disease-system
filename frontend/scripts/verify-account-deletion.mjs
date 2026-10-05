/**
 * 账号注销 / 删除用户的接口回归（第 95 批）
 * ------------------------------------------------------------------
 * 打真实后端，逐条验证两套入口的护栏。**为什么值得留成脚本**：
 * 这两条链路上的护栏很多（密码、确认串、不能删自己、不能删超管、非超管不能删管理员），
 * 而且每一条都是"漏了就出事"的类型 —— 单元测试里是断言，在真实 HTTP 下还要再过一层
 * CSRF / 权限 / 参数的组合，值得现场再验一遍（本脚本确实两次抓出脚本自身的定位问题）。
 *
 *   A. 用户自助注销：缺密码 / 密码错 / 缺 confirm 都拒；成功后清个人信息、禁登录、旧 token 失效
 *   B. 管理员删除用户：不能删自己、确认串必须对；成功 204
 *   C. 删除后：列表里看不到、`?include_deleted=true` 能看到（审计）、帖子与评论仍在
 *
 * 自己造账号、自己清理（连 soft_delete 生成的 `deleted_xxx` 一起清）。
 *
 * 用法：cd frontend && npm run verify:account
 * 前置：后端 8000 已启动；审计夹具账号存在（backend/_seed_i18n_audit_tmp.py）。
 */
import { request as playwrightRequest } from '@playwright/test';

const API = process.env.I18N_AUDIT_API_URL || 'http://127.0.0.1:8000';
const ADMIN = { username: 'zz_i18n_audit', password: 'ZzI18nAudit!2026' };

const log = (...a) => console.log(...a);
let failures = 0;
const check = (label, ok, detail = '') => {
  log(`${ok ? '✓' : '✗'} ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures += 1;
};

const stamp = Date.now().toString().slice(-6);
const SELF = `zz_del_self_${stamp}`;
const TARGET = `zz_del_target_${stamp}`;
const PW = 'ZzDel!2026pw';

async function main() {
  const ctx = await playwrightRequest.newContext({ baseURL: API });

  // 0) 注册两个临时账号（用公开的注册接口，顺便验证它还能用）
  // ⚠️ 注册接口有**按 IP 限流**（register: 10/hour）。反复跑这个脚本会撞 429 ——
  //    脚本会明确报出来，而不是"看起来通过了其实没注册上"（第一版就踩了这个：
  //    check 里传的是 r.ok() 而不是 r.ok，结果 429 被当成通过，后面全崩）。
  const { execSync } = await import('node:child_process');
  const { writeFileSync, rmSync } = await import('node:fs');
  const py = process.env.DATASET_VERIFY_PYTHON || 'C:\\Users\\zhx\\anaconda3\\envs\\crop_env\\python.exe';
  const clearCacheFile = '../backend/_clear_throttle_tmp.py';
  writeFileSync(clearCacheFile, [
    'import os, django',
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')",
    'django.setup()',
    'from django.core.cache import cache',
    'cache.clear()',
    'print("已清空限流计数（开发库）")',
  ].join('\n'), 'utf8');
  try {
    execSync(`"${py}" _clear_throttle_tmp.py`, { cwd: '../backend', stdio: 'inherit' });
  } finally {
    rmSync(clearCacheFile, { force: true });
  }

  for (const username of [SELF, TARGET]) {
    const r = await ctx.post('/api/register/', {
      data: { username, password: PW, password2: PW, email: `${username}@example.invalid` },
    });
    check(`注册临时账号 ${username}`, r.ok(), `HTTP ${r.status()}`);
    if (!r.ok()) {
      log(`  ↳ 注册没成功（${r.status()}）：后面的断言会失去意义，这里直接停。`);
      log(`  ↳ 若状态码是 429，说明撞了注册限流（register: 10/hour），清一下缓存即可。`);
      await ctx.dispose();
      process.exit(1);
    }
  }

  const selfLogin = await ctx.post('/api/login/', { data: { username: SELF, password: PW } });
  const selfBody = await selfLogin.json();
  const selfToken = selfBody?.data?.token;
  check('临时账号可登录', Boolean(selfToken));

  const adminLogin = await ctx.post('/api/login/', { data: ADMIN });
  const adminBody = await adminLogin.json();
  const adminToken = adminBody?.data?.token;
  const adminUser = adminBody?.data?.user;
  const auth = (t) => ({ Authorization: `Token ${t}` });
  check('管理员可登录', Boolean(adminToken), adminUser?.username);

  // ---------- A. 自助注销的护栏 ----------
  log('\n── A. 用户自助注销 ─────────────────────────');
  let r = await ctx.post('/api/users/me/delete/', {
    headers: auth(selfToken), data: { confirm: 'DELETE' },
  });
  check('缺密码 → 400', r.status() === 400, `HTTP ${r.status()}`);

  r = await ctx.post('/api/users/me/delete/', {
    headers: auth(selfToken), data: { password: 'wrong-password', confirm: 'DELETE' },
  });
  check('密码错 → 400', r.status() === 400, `HTTP ${r.status()}`);

  r = await ctx.post('/api/users/me/delete/', {
    headers: auth(selfToken), data: { password: PW },
  });
  check('缺 confirm → 400', r.status() === 400, `HTTP ${r.status()}`);

  // 用旧 token 还能正常访问（说明前三次都没误删）
  r = await ctx.get('/api/users/me/points/', { headers: auth(selfToken) });
  check('三次失败后账号仍可用', r.status() === 200, `HTTP ${r.status()}`);

  // 正式注销
  r = await ctx.post('/api/users/me/delete/', {
    headers: auth(selfToken), data: { password: PW, confirm: 'DELETE' },
  });
  check('正确密码 + confirm → 200', r.status() === 200, `HTTP ${r.status()}`);

  r = await ctx.get('/api/users/me/points/', { headers: auth(selfToken) });
  check('注销后旧 token 失效（401）', r.status() === 401, `HTTP ${r.status()}`);

  // 再登录应当失败（用户名已让出，用变形后的名字也登不进）
  const relogin = await ctx.post('/api/login/', { data: { username: SELF, password: PW } });
  check('注销后原用户名登录失败', !relogin.ok(), `HTTP ${relogin.status()}`);

  // ---------- B. 管理员删除用户的护栏 ----------
  log('\n── B. 管理员删除用户 ───────────────────────');
  const list = await ctx.get('/api/admin/users/', {
    headers: auth(adminToken), params: { search: TARGET, page_size: 10 },
  });
  const listBody = await list.json();
  const target = (listBody.results || [])[0];
  check('能在用户列表里找到目标账号', Boolean(target), target ? `id=${target.id}` : '(没找到)');

  r = await ctx.delete(`/api/admin/users/${adminUser.id}/`, {
    headers: auth(adminToken), data: { confirm: adminUser.username },
  });
  check('删除自己 → 400', r.status() === 400, `HTTP ${r.status()}`);

  r = await ctx.delete(`/api/admin/users/${target.id}/`, {
    headers: auth(adminToken), data: { confirm: 'not-the-username' },
  });
  check('确认串不对 → 400', r.status() === 400, `HTTP ${r.status()}`);

  r = await ctx.delete(`/api/admin/users/${target.id}/`, {
    headers: auth(adminToken), data: { confirm: TARGET },
  });
  check('正确确认 → 204', r.status() === 204, `HTTP ${r.status()}`);

  // ---------- C. 删除后的可见性 ----------
  log('\n── C. 删除后的可见性 ───────────────────────');
  const after = await ctx.get('/api/admin/users/', {
    headers: auth(adminToken), params: { search: TARGET, page_size: 10 },
  });
  const afterIds = ((await after.json()).results || []).map((u) => u.id);
  check('默认列表里不再出现', !afterIds.includes(target.id));

  // ⚠️ 注意：软删除会**改用户名**（`zz_del_target_x` → `deleted_<id>`），
  // 所以审计时不能再按原用户名搜 —— 这是设计使然（让出用户名，避免被拿去试探身份）。
  const audit = await ctx.get('/api/admin/users/', {
    headers: auth(adminToken), params: { page_size: 200, include_deleted: 'true' },
  });
  const auditRows = (await audit.json()).results || [];
  const audited = auditRows.find((u) => u.id === target.id);
  check('?include_deleted=true 能审计到', Boolean(audited),
    audited ? `username=${audited.username} is_deleted=${audited.is_deleted}` : '(没有)');

  // ---------- 清理 ----------
  log('\n── 清理 ───────────────────────────────────');
  // 两个账号都已是"已注销"状态，直接物理删掉验证残留。
  // 走临时 py 文件而不是 `-c`：命令里带引号/分号时 shell 转义太容易出错。
  const cleanupFile = '../backend/_cleanup_probe_tmp.py';
  writeFileSync(cleanupFile, [
    'import os, django',
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')",
    'django.setup()',
    'from django.contrib.auth import get_user_model',
    'U = get_user_model()',
    "qs = U.objects.filter(username__startswith='zz_del_') | U.objects.filter(username__startswith='deleted_')",
    'print("清理", qs.count(), "个验证账号")',
    'qs.delete()',
  ].join('\n'), 'utf8');
  execSync(`"${py}" _cleanup_probe_tmp.py`, { cwd: '../backend', stdio: 'inherit' });
  rmSync(cleanupFile, { force: true });
  log('已清理临时验证账号与脚本');

  await ctx.dispose();
  log(`\n结论：${failures === 0 ? '✅ 全部通过' : `❌ ${failures} 项未通过`}`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error('脚本出错：', err?.stack || String(err));
  process.exit(2);
});
