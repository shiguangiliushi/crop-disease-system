/**
 * 移动端 E2E 的小工具（第 174 批）
 * ============================================================================
 * 只做一件事：**清掉后端限流缓存**。
 *
 * 为什么要它：登录接口有频率限制（防爆破），而 E2E 每跑一次就要登录一次 ——
 * 连着跑几轮之后，登录会被限流挡住，脚本报"登录失败"，
 * 看起来像页面坏了，其实是限流在正常工作 ✗。
 * 前端那套 E2E 一直有 clearThrottle()（frontend/e2e/helpers.mjs），
 * 移动端这一批才补上，口径与它一致：清整个 cache（开发环境没有别的缓存数据）。
 */
import { execFileSync } from 'node:child_process';
import path from 'node:path';

/** 后端目录（移动端脚本在 mobile/scripts 下） */
const BACKEND_DIR = path.resolve(process.cwd(), '..', 'backend');

/** 用哪个解释器跑 Django 命令：优先项目环境 crop_env（与后端服务一致） */
const PYTHON = process.env.MOBILE_E2E_PYTHON
  || 'C:\\Users\\zhx\\anaconda3\\envs\\crop_env\\python.exe';

/** 把若干行 Python 拼成一条 `manage.py shell -c` 命令 */
export function runDjango(lines) {
  const code = lines.join('\n');
  return execFileSync(PYTHON, ['manage.py', 'shell', '-c', code], {
    cwd: BACKEND_DIR,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

/** 清掉限流计数（登录前调用） */
export function clearThrottle() {
  try {
    runDjango([
      'from django.core.cache import cache',
      'cache.clear()',
      "print('throttle cleared')",
    ]);
    return true;
  } catch (error) {
    console.warn('  ⚠️ 清限流失败（继续，可能撞上限流）:', String(error).slice(0, 120));
    return false;
  }
}
