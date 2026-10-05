/**
 * E2E 前置检查（第 103 批）
 * ============================================================================
 * 在跑任何用例之前，先确认"被测的东西真的在跑"。这一层看起来多余，
 * 但它把**最常见的一种假红**变成了**一句人话**：
 *
 *   后端没起 → 每条用例各自超时 → 一屏 timeout，看不出根因。
 *
 * 现在会在开头直接说：
 *   "后端没在 8000 上响应 —— 先 cd backend && python manage.py runserver"
 *
 * 另外顺手检查前端能不能打开（webServer 会拉起 vite，但如果 5173 上
 * 挂着的是**别的项目**，reuseExistingServer 会默默复用它，然后所有选择器都找不到 ——
 * 这种情况也在这里拦掉）。
 */
import { API_BASE, MOBILE_BASE } from './helpers.mjs';

async function probe(url, timeoutMs = 5000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal });
    return response.status;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export default async function globalSetup() {
  const backendStatus = await probe(`${API_BASE}/api/health/`);
  if (backendStatus === null) {
    throw new Error(
      `\nE2E 前置检查失败：后端没在 ${API_BASE} 上响应。\n`
      + '→ 先启动后端：cd backend && python manage.py runserver 127.0.0.1:8000\n'
      + '（E2E 打的是真实后端与真实数据库，不会自动启动它 —— 否则可能测到另一套数据）\n',
    );
  }
  if (backendStatus !== 200) {
    throw new Error(`后端 /api/health/ 返回 HTTP ${backendStatus}，服务不正常，先修它再跑 E2E`);
  }

  const frontStatus = await probe(process.env.E2E_BASE_URL || 'http://127.0.0.1:5173');
  if (frontStatus === null) {
    throw new Error('前端（5173）打不开：请确认 `npm run dev` 能起来（playwright 的 webServer 会尝试拉起）');
  }

  // 移动端是**独立的第二个应用**，playwright 的 webServer 里没有它 ——
  // 这里只提示、不抛错（不跑移动端用例的人也应当能用这套 E2E）。
  const mobileStatus = await probe(MOBILE_BASE, 3000);
  if (mobileStatus === null) {
    console.warn(
      `\n⚠ 移动端（${MOBILE_BASE}）打不开 —— e2e/05-mobile.spec.mjs 会失败。\n`
      + '  启动它：cd mobile && npm run dev\n',
    );
  }

  // 审计夹具账号是管理员用例的前提：不在就明说，别让用例在登录处抛一句看不懂的错
  const loginStatus = await probe(`${API_BASE}/api/login/`);   // GET 会 405，只用来确认路由存在
  if (loginStatus === null) {
    throw new Error('后端 /api/login/ 不可达');
  }
}
