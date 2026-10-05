/**
 * E2E 公共工具（第 103 批）
 * ============================================================================
 * 为什么要有这个文件：第 91~102 批期间为了验证功能，陆陆续续写了十来个
 * "一次性脚本"（跑完就删）。它们的**收尾逻辑每次都重写一遍**，而且写法各异：
 *   · 有的用 py 文件、有的用 `manage.py shell -c`（引号转义地狱）；
 *   · 有的清理账号、有的没清（开发库里因此留下过 `zz_del_*` 这类残留）；
 *   · 有的把超时写成 30s，赶上识别慢就假红。
 *
 * 这里把这些共同部分固定下来，让用例只写"要验证什么"。
 *
 * 三条约定（这也是"常态化"与"一次性脚本"的区别）：
 *   1. **自己造数据、自己清**：`registerTempUser()` / `cleanupByPrefix()`
 *      保证跑完库是干净的，可以对着开发库反复跑；
 *   2. **后端必须已在跑**：不在跑就明确报错（由 global-setup 提前拦），
 *      绝不去悄悄启动一个"自己的后端"，否则测的可能是另一套数据；
 *   3. **失败要能看懂**：`expectThat()` 把"期望 / 实际"一起打出来，
 *      而不是只丢一个 `expect(false).toBe(true)`。
 *
 * ⚠️ 关于 localStorage / sessionStorage：本项目登录态在 `auth_token` +
 *    `user` 两个 key 上（见 utils/authStorage.js）。`loginAs()` 会把它们写进去，
 *    这样用例不必每次走一遍登录表单 —— 只有**专门测登录**的用例才该走表单。
 */
import { execFileSync, spawn } from 'node:child_process';
import { writeFileSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { expect } from '@playwright/test';

const HERE = dirname(fileURLToPath(import.meta.url));
/** backend 目录（E2E 需要跑管理命令来造/清数据） */
export const BACKEND_DIR = resolve(HERE, '../../backend');
/** 跑管理命令用的解释器 */
export const PYTHON = process.env.E2E_PYTHON
  || process.env.DATASET_VERIFY_PYTHON
  || 'C:\\Users\\zhx\\anaconda3\\envs\\crop_env\\python.exe';
/** 后端地址 */
export const API_BASE = process.env.E2E_API_URL || 'http://127.0.0.1:8000';
/**
 * 移动端（H5）地址。
 *
 * 移动端是**独立的 Vue 应用**（`mobile/`，Vant），与桌面端零代码共享 ——
 * 所以它需要自己的用例，也必须**单独启动**（playwright 的 webServer 里
 * 只拉起了桌面端的 5173）。默认 5174，可用 E2E_MOBILE_URL 覆盖。
 */
export const MOBILE_BASE = process.env.E2E_MOBILE_URL || 'http://127.0.0.1:5174';

/** 所有临时数据的统一前缀 —— 清理时按它扫，避免误删真实数据 */
export const TEMP_PREFIX = 'zze2e';

// ---------------------------------------------------------------------------
// 断言
// ---------------------------------------------------------------------------
let checkCount = 0;
const problems = [];

/**
 * 带"期望/实际"的断言。
 *
 * 用它而不是 `expect(x).toBe(y)`：E2E 失败最常见的排查成本是"到底拿到了什么"，
 * 把实际值直接写在失败信息里，省掉一次加日志重跑。
 */
export function expectThat(label, actual, expected) {
  checkCount += 1;
  const ok = typeof expected === 'function' ? Boolean(expected(actual)) : actual === expected;
  if (!ok) {
    const shown = typeof expected === 'function' ? '(自定义判定)' : JSON.stringify(expected);
    problems.push(`${label}：期望 ${shown}，实际 ${JSON.stringify(actual)}`);
  }
  return ok;
}

/** 在 Playwright 的 test 里用：把收集到的问题一次性抛出来（带上全部失败项） */
export function assertNoProblems() {
  expect(problems, `共 ${problems.length} 项不符合预期：\n  ${problems.join('\n  ')}`).toEqual([]);
}

export function resetChecks() {
  checkCount = 0;
  problems.length = 0;
}

export function checksRun() {
  return checkCount;
}

// ---------------------------------------------------------------------------
// 跑 Python 片段（造数据 / 清数据）
// ---------------------------------------------------------------------------
/**
 * 跑一段 Django 代码。
 *
 * 用临时 `.py` 文件而不是 `manage.py shell -c "..."`：后者在 Windows 上
 * 引号/分号/中文混在一起时极易被 shell 吃掉（第 95 批踩过，代码里出现 `; from django…`）。
 */
export function runDjango(lines) {
  const file = resolve(BACKEND_DIR, `_e2e_tmp_${Date.now()}.py`);
  const body = [
    'import os, django',
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')",
    'django.setup()',
    ...lines,
  ].join('\n');
  writeFileSync(file, body, 'utf8');
  try {
    return execFileSync(PYTHON, [file], { cwd: BACKEND_DIR, encoding: 'utf8' }).trim();
  } finally {
    rmSync(file, { force: true });
  }
}

/**
 * 常驻的 Django 会话（第 109 批）—— 多次查询共用**一个** Python 进程。
 *
 * ⚠️ 为什么需要它：`runDjango()` 每次都要新起一个 Python 进程 + `django.setup()`，
 * 而这个项目装了 torch，导入链很长 —— 实测一台普通开发机上**单次要十几秒**。
 * 第 109 批给一条用例加计时打点后发现：
 *
 *     分步耗时：准备 42.6s｜页面打开 6.5s｜等待结果 1.0s
 *               （其中 maxDetectionId 36119ms）
 *
 * 也就是说**被测功能只用 1 秒**，剩下的 40 秒全是"启 Python 查一下数据库"。
 * 更糟的是这种纯开销会把"真的变慢"和"环境慢"混在一起 ——
 * 加打点之前根本看不出是哪一头。
 *
 * 用法（配合 `djangoSession.close()` 收尾）：
 *
 *     const session = djangoSession();
 *     const maxId = Number(session.run(['from api.models import X', 'print(X.objects.count())']));
 *     session.close();
 *
 * 实现：进程常驻，用 `stdin` 逐行发指令、按 `#OK<id>` / `#ERR<id>` 标记读回结果。
 * 只用一个 `data` 事件缓冲 stdout（不用 readline 逐行读，避免半行 JSON 被截断）。
 */
export function djangoSession() {
  const file = resolve(BACKEND_DIR, `_e2e_session_${Date.now()}.py`);
  writeFileSync(file, [
    'import os, sys, io, json, traceback, django',
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')",
    'django.setup()',
    'for raw in sys.stdin:',
    '    raw = raw.strip()',
    '    if not raw:',
    '        continue',
    '    request = json.loads(raw)',
    '    buffer = io.StringIO()',
    '    real_stdout, sys.stdout = sys.stdout, buffer',
    '    try:',
    '        exec(request["code"], {"__name__": "__main__"})',
    '        payload = {"ok": True, "out": buffer.getvalue()}',
    '    except Exception as exc:',
    '        payload = {"ok": False, "out": buffer.getvalue(),',
    '                   "err": f"{type(exc).__name__}: {exc}",',
    '                   "tb": traceback.format_exc()[-600:]}',
    '    finally:',
    '        sys.stdout = real_stdout',
    '    sys.stdout.write("#R#" + json.dumps(payload) + "\\n")',
    '    sys.stdout.flush()',
  ].join('\n'), 'utf8');

  const child = spawn(PYTHON, [file], {
    cwd: BACKEND_DIR,
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  let buffer = '';
  const pending = [];
  child.stdout.setEncoding('utf8');
  child.stdout.on('data', (chunk) => {
    buffer += chunk;
    let index = buffer.indexOf('\n');
    while (index >= 0) {
      const line = buffer.slice(0, index);
      buffer = buffer.slice(index + 1);
      if (line.startsWith('#R#')) {
        const waiter = pending.shift();
        if (waiter) {
          try {
            waiter.resolve(JSON.parse(line.slice(3)));
          } catch (error) {
            waiter.reject(new Error(`会话返回无法解析：${line.slice(0, 200)}`));
          }
        }
      }
      index = buffer.indexOf('\n');
    }
  });

  let stderr = '';
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => { stderr += chunk; });

  return {
    run(lines, { timeoutMs = 120_000 } = {}) {
      return new Promise((resolvePromise, rejectPromise) => {
        const timer = setTimeout(() => {
          rejectPromise(new Error(`djangoSession 超时（${timeoutMs}ms）；stderr: ${stderr.slice(-300)}`));
        }, timeoutMs);
        pending.push({
          resolve: (payload) => {
            clearTimeout(timer);
            if (!payload.ok) {
              rejectPromise(new Error(`会话里的代码出错：${payload.err}\n${payload.tb || ''}`));
              return;
            }
            resolvePromise(String(payload.out).trim());
          },
          reject: (error) => { clearTimeout(timer); rejectPromise(error); },
        });
        child.stdin.write(`${JSON.stringify({ code: lines.join('\n') })}\n`);
      });
    },
    close() {
      try { child.stdin.end(); } catch { /* 忽略 */ }
      try { child.kill(); } catch { /* 忽略 */ }
      rmSync(file, { force: true });
    },
    get stderr() { return stderr; },
  };
}

/** 按前缀清理临时数据（用例的 `afterAll` 里调它）。
 *
 * 为什么要带 `deleted_` 前缀：注销冷静期/软删除会把用户名改成 `deleted_<id>`，
 * 只扫 `zze2e` 会漏掉这些已注销的临时账号，留下孤儿行。
 */
export function cleanupByPrefix(prefix = TEMP_PREFIX) {
  return runDjango([
    'from django.contrib.auth import get_user_model',
    'from api.models_forum import Post, Comment',
    'from api.models import Feedback, DetectionHistory, News',
    'U = get_user_model()',
    `users = U.objects.filter(username__startswith='${prefix}') | U.objects.filter(username__startswith='deleted_')`,
    `print('users deleted:', users.delete()[0])`,
    `print('posts deleted:', Post.objects.filter(title__startswith='${prefix}').delete()[0])`,
    `print('feedback deleted:', Feedback.objects.filter(suggestion__startswith='${prefix}').delete()[0])`,
    `print('news deleted:', News.objects.filter(title__startswith='${prefix}').delete()[0])`,
  ]);
}

/**
 * 按 id 删识别记录（含它落盘的两张图）。
 *
 * ⚠️ 识别记录**没法按前缀清**：它的 `detection_result` 存的是模型预测出来的病害名
 * （"Apple Cedar Apple Rust"），不是我们造的数据 —— 没有任何标记可以按名字筛。
 * 所以识别类用例必须**记住自己产生的 history_id**，跑完显式删掉，
 * 否则每跑一次 E2E 就在开发库里多留一条记录 + 两张上传图（实测确实在累积）。
 */
/**
 * 按 id 删识别记录，并把这次识别**落盘的全部文件**清掉。
 *
 * ⚠️ 为什么要按 uuid 通配，而不是只删 FieldFile 指向的文件：
 *    识别接口落盘的文件比入库的多。实测一次识别会在 `media/detection_uploads/` 里留下
 *    `annotated_<uuid>.JPG` 等文件，而记录里只存了 `<uuid>.JPG` 一个字段 ——
 *    **其余文件没有任何数据库引用**，也就永远没人清理（这也是 media 目录里
 *    累计出十几 MB 孤儿文件的主因，第 104 批审计发现）。
 *    所以清理时按"入库文件名的 uuid 前缀"把所有同源文件一起删掉。
 */
export function cleanupDetections(ids = []) {
  const list = ids.filter((id) => Number.isInteger(id));
  if (!list.length) return 'no detections to clean';
  return runDjango([
    'import re',
    'from pathlib import Path',
    'from django.conf import settings',
    'from api.models import DetectionHistory',
    `rows = DetectionHistory.objects.filter(id__in=${JSON.stringify(list)})`,
    'names = []',
    'for row in rows:',
    '    for field in ("image", "annotated_image"):',
    '        handle = getattr(row, field, None)',
    '        name = getattr(handle, "name", "") if handle else ""',
    '        if name:',
    '            names.append(str(name))',
    'deleted = rows.delete()[0]',
    'print("rows deleted:", deleted)',
    'upload_dir = Path(settings.MEDIA_ROOT) / "detection_uploads"',
    'uuid_re = re.compile(r"[0-9a-f]{16,}")',
    'removed = 0',
    'for raw in names:',
    // ⚠️ 接口存下来的 name 用的是 **Windows 反斜杠**（`detection_uploads\\a66e…JPG`），
    //    而 `Path("a\\b")` 在 POSIX 语义下是**一个文件名** —— 必须先归一成 `/`，
    //    否则 is_file() 永远 False，表现就是"记录删了、文件全留着"。
    '    cleaned = str(raw).replace("\\\\", "/")',
    '    stem = Path(cleaned).name',
    '    if upload_dir.is_dir():',
    '        match = uuid_re.search(stem)',
    '        if match:',
    // 同源文件（annotated_ / txt 等）都以同一个 uuid 命名，一起清
    '            for sibling in upload_dir.glob(f"*{match.group(0)}*"):',
    '                try:',
    '                    sibling.unlink()',
    '                    removed += 1',
    '                except Exception as exc:',
    '                    print("  删除失败:", sibling, exc)',
    '        else:',
    '            direct = upload_dir / stem',
    '            if direct.is_file():',
    '                direct.unlink()',
    '                removed += 1',
    'print("files deleted:", removed, "of", len(names), "referenced")',
  ]);
}

/**
 * 清空限流计数。
 *
 * 为什么 E2E 需要它：登录接口限流是 **10/分钟（按 IP）**，而这套用例会反复登录
 * （夹具账号 + 临时账号 + 注销后重登 + 各种前置）。撞上 429 时表现是
 * "功能看起来坏了"，而其实只是被自己的请求数限住了 —— 实测踩过两次。
 *
 * 注意：这只清开发库的限流计数（生产用的是共享缓存，不该也清不掉）。
 */
export function clearThrottle() {
  return runDjango([
    'from django.core.cache import cache',
    'cache.clear()',
    "print('throttle cleared')",
  ]);
}

// ---------------------------------------------------------------------------
// 接口调用
// ---------------------------------------------------------------------------
/**
 * 打后端接口。
 *
 * 刻意用 `fetch` 而不是页面里的 axios：造数据/清理不该依赖前端是否已经加载，
 * 也不该被前端的拦截器（401 跳登录之类）带偏。
 */
export async function api(path, { method = 'GET', token, body, raw = false } = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Token ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (raw) return response;
  let json = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }
  return { status: response.status, json };
}

/** 登录并拿 Token（默认用审计夹具账号） */
export async function login(username = 'zz_i18n_audit', password = 'ZzI18nAudit!2026') {
  const { status, json } = await api('/api/login/', {
    method: 'POST',
    body: { username, password },
  });
  if (status !== 200 || !json?.data?.token) {
    throw new Error(
      `登录夹具账号失败（HTTP ${status}）：${JSON.stringify(json)}\n`
      + '→ 请确认后端在 8000 上跑着，且审计夹具账号存在（backend/_seed_i18n_audit_tmp.py）',
    );
  }
  return { token: json.data.token, user: json.data.user };
}

/** 注册一个临时账号（返回 {username, password, token, user}） */
export async function registerTempUser(suffix = Math.random().toString(36).slice(2, 8)) {
  const username = `${TEMP_PREFIX}_${suffix}`;
  const password = 'ZzE2e!2026pw';
  const { status, json } = await api('/api/register/', {
    method: 'POST',
    body: { username, password, password2: password, email: `${username}@example.invalid` },
  });
  if (status !== 201) {
    throw new Error(`注册临时账号失败（HTTP ${status}）：${JSON.stringify(json)}`);
  }
  const data = json?.data ?? json;
  return { username, password, token: data?.token, user: data?.user };
}

// ---------------------------------------------------------------------------
// 浏览器辅助
// ---------------------------------------------------------------------------
/**
 * 把登录态写进浏览器存储，省掉"每条用例都走一遍登录表单"。
 *
 * 只有**专门测登录流程**的用例才应该真的填表单 —— 其他用例每次都走表单，
 * 既慢又会把"登录坏了"这一个问题放大成"所有用例都红"。
 */
export async function loginAs(page, { token, user }) {
  await page.addInitScript((payload) => {
    sessionStorage.setItem('auth_token', payload.token);
    sessionStorage.setItem('user', JSON.stringify(payload.user));
  }, { token, user });
}

/**
 * 打开一个需要登录的页面，并在**被弹回登录页时自动重试一次**（第 109 批）。
 *
 * ⚠️ 为什么需要这个：桌面端的登录态放在 `sessionStorage`（关标签页就登出，这是有意的）。
 * 而 **Vite 在依赖重优化时会强制整页 reload** —— reload 会把我们注入的
 * sessionStorage 一起清掉，于是路由守卫把用例踢到 `/login`。
 *
 * 触发时机很典型：**刚改过前端文件就立刻跑 E2E**（改动使 Vite 的依赖图失效）。
 * 表现极具误导性：截图里是登录页，看起来像"登录态没注入"或"登录坏了"，
 * 而实际上注入是对的，只是被 reload 冲掉了。
 * （第 109 批为此查了很久 —— 同一个流程用独立脚本直连只要 2.4 秒，
 *   在用例里却卡 45~90 秒；最后靠失败截图才看出停在登录页。）
 *
 * 做法：导航后如果停在登录页，等 Vite 稳定再导航一次。
 * `addInitScript` 会重新注入，所以第二次必然带着登录态。
 * 真要是登录态本身有问题，第二次仍然会失败 —— 这条重试不会掩盖真 bug。
 */
export async function gotoAuthed(page, url, { attempts = 3 } = {}) {
  let lastUrl = '';
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    await page.goto(url);
    // 给路由守卫与首个接口调用一点时间落地
    await page.waitForTimeout(1000);
    lastUrl = page.url();
    if (!lastUrl.includes('/login')) return lastUrl;

    // 诊断：把"登录态到底还在不在"打出来。
    // 这一步很关键 —— 被弹回登录页有**两种完全不同的原因**：
    //   ① sessionStorage 被清掉了（reload / 拦截器清身份）→ 下面会显示 null
    //   ② 登录态还在，但守卫因为别的原因跳了 → 下面会显示 token 还在
    // 不区分这两种，就只能对着"停在登录页"这一个现象猜。
    const state = await page.evaluate(() => ({
      token: Boolean(sessionStorage.getItem('auth_token')),
      user: Boolean(sessionStorage.getItem('user')),
      url: location.href,
    })).catch(() => null);
    console.log(`  ↳ 第 ${attempt} 次被弹回登录页；存储状态 ${JSON.stringify(state)}`);

    // Vite 重优化期间会反复 reload；多等一会儿再试，这段时间不该算进用例超时
    await page.waitForTimeout(5000);
  }
  console.log(`  ↳ 重试 ${attempts} 次后仍停在登录页 —— 下面用例会失败，请检查登录态是否正确`);
  return lastUrl;
}

/** 收集页面 JS 报错（很多问题的唯一线索就是它，别丢） */
export function watchPageErrors(page, { ignore = [] } = {}) {
  const errors = [];
  // 有些"报错"是**被测场景本身**的预期产物：例如"token 失效自动跳登录"这条用例
  // 一定会产生一次 401 网络错误，浏览器会把它记成 console error。
  // 用 `ignore` 明确列出允许出现的模式，而不是放宽所有 console error。
  const skip = (text) => ignore.some((re) => re.test(text));
  page.on('pageerror', (error) => {
    const message = String(error.message || error).split('\n')[0];
    if (!skip(message)) errors.push(message);
  });
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const text = `console: ${message.text().slice(0, 200)}`;
    if (!skip(text)) errors.push(text);
  });
  return errors;
}

// ---------------------------------------------------------------------------
// 移动端专用（第 104 批）
// ---------------------------------------------------------------------------
/**
 * 给**移动端**注入登录态。
 *
 * ⚠️ 移动端与桌面端的存储**故意不一样**，写错地方就会得到
 * "看起来已登录、其实没登录"（页面正常渲染、接口全 401）：
 *   · 桌面端：`sessionStorage` 的 `auth_token` / `user`（关标签就登出）
 *   · 移动端：`localStorage` 的 `mobile_token` / `mobile_user`
 *     （手机上每次打开都要重登是不可接受的 —— 见 mobile/src/utils/authStorage.js）
 * 第一版照着桌面端的写法注入，结果"底部导航不存在""文件输入不存在"
 * 全是假的 —— 实际是识别页因为未登录直接跳走了。
 */
export async function loginAsMobile(page, { token, user }) {
  await page.addInitScript((payload) => {
    localStorage.setItem('mobile_token', payload.token);
    localStorage.setItem('mobile_user', JSON.stringify(payload.user));
  }, { token, user });
}

/** 读移动端存储里的 token（用来验证"身份被清干净了"） */
export function readMobileToken(page) {
  return page.evaluate(() => localStorage.getItem('mobile_token'));
}

/** 等元素出现，返回是否出现（不抛异常，交给 expectThat 统一报） */
export async function appears(page, selector, timeout = 8000) {
  try {
    await page.waitForSelector(selector, { timeout, state: 'visible' });
    return true;
  } catch {
    return false;
  }
}
