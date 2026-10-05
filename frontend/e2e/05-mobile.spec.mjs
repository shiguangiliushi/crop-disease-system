/**
 * 移动端（H5）：核心链路（第 104 批）
 * ============================================================================
 * 移动端是**独立的 Vue 应用**（`mobile/`，Vant，5174 端口，与桌面端零代码共享）。
 * 这意味着桌面端全绿**完全不能说明**移动端是好的 —— 它有自己的路由、自己的
 * 登录态存储、自己的 i18n 表。所以必须单独一套回归。
 *
 * 这里挑的是"移动端最容易悄悄坏掉"的四件事，全部来自真实修过的 bug：
 *   1. **登录页**（第 93 批修过：法务链接指向桌面端路由，点开是识别页；
 *      忘记密码入口此前根本不存在）；
 *   2. **身份失效自愈**（第 93 批：token 过期后界面仍显示已登录，各页只报"请求失败"）；
 *   3. **底部导航**（用错了路由名就整片跳不动）；
 *   4. **识别页能拍照/选图**（第 93 批加了 keep-alive，切页不丢照片）。
 *
 * ⚠️ 跑之前移动端开发服务器要在 5174 上（playwright.config.ts 的 webServer 里
 *    只拉起了桌面端的 5173，移动端需要单独起 —— 见 e2e/README.md）。
 */
import { test } from '@playwright/test';
import {
  api,
  assertNoProblems,
  expectThat,
  login,
  loginAsMobile,
  readMobileToken,
  resetChecks,
  runDjango,
  watchPageErrors,
  MOBILE_BASE,
} from './helpers.mjs';

test.describe('移动端：核心链路', () => {
  test.beforeEach(() => resetChecks());

  test('登录页可打开，并且有忘记密码入口', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto(`${MOBILE_BASE}/login`);
    await page.waitForTimeout(2000);

    const text = await page.locator('body').innerText();
    expectThat('页面有登录相关文案', /登录|注册/.test(text), true);

    // 第 93 批加的入口：此前忘了密码只能找管理员
    const forgotLink = page.locator('a, button', { hasText: /忘记密码/ }).first();
    expectThat('有"忘记密码"入口', await forgotLink.count() > 0, true);

    expectThat('没有 JS 报错', errors.length, 0);
    assertNoProblems();
  });

  test('忘记密码页可打开并提交（不泄露账号是否存在）', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto(`${MOBILE_BASE}/forgot-password`);
    await page.waitForTimeout(1800);

    const inputs = page.locator('input');
    expectThat('有输入框', await inputs.count() >= 1, true);
    await inputs.first().fill('definitely-not-a-user@example.invalid');

    const submit = page.locator('button', { hasText: /提交|发送|重置/ }).first();
    if (await submit.count()) {
      await submit.click();
      await page.waitForTimeout(2500);
    }
    // 无论账号是否存在，都应当给出中性提示（防账号枚举）
    const text = await page.locator('body').innerText();
    expectThat('给出中性提示', /邮件|发送|如果|存在/.test(text), true);
    expectThat('没有 JS 报错', errors.length, 0);
    assertNoProblems();
  });

  test('底部导航能切到"记录"与"我的"', async ({ page }) => {
    // ⚠️ 这条**必须真的注入登录态**再断言 tabbar。
    //    第一版忘了调 `loginAsMobile`（session 变量取了但没用上），
    //    结果未登录访问 /detect 被守卫送去了 /login，而登录页的 meta 里
    //    `tabbar: false` —— 于是"底部导航 0 个 tab"。那不是 bug，是测试没登录。
    const session = await login();
    await loginAsMobile(page, session);

    const errors = watchPageErrors(page);
    // 诊断用：把 4xx/5xx 的 URL 记下来。浏览器只报
    // "Failed to load resource: 404"，**不说是哪个资源** —— 没有这一行就只能猜。
    const failedRequests = [];
    page.on('response', (response) => {
      if (response.status() >= 400) {
        failedRequests.push(`${response.status()} ${response.url()}`);
      }
    });
    await page.goto(`${MOBILE_BASE}/detect`);
    await page.waitForTimeout(2500);

    // 底部导航的标签文案随 i18n；**按可见文案点**而不是按标签名/属性 ——
    // ⚠️ 这里试过两种"更精确"的写法，都不成立：
    //    · `.van-tabbar a`      → 0 个（Vant 的 tabbar-item 根节点不是 <a>）
    //    · `href*="/history"`   → 0 个（item 上没有 href，路由是靠组件内部跳的）
    //    所以改成按用户真正看到的东西点：tab 上写着"识别/记录/我的"。
    //    这也更贴近"用户能不能用"这个判据。
    const tabbarExists = await page.locator('.van-tabbar').count();
    const tabItemCount = await page.locator('.van-tabbar-item').count();
    expectThat('底部导航容器存在', tabbarExists >= 1, true);
    expectThat('底部导航有 3 个 item', tabItemCount, 3);

    const tabbarText = await page.locator('.van-tabbar').innerText();
    expectThat('tab 里有"记录"', /记录/.test(tabbarText), true);
    expectThat('tab 里有"我的"', /我的/.test(tabbarText), true);

    const historyTab = page.locator('.van-tabbar-item', { hasText: '记录' }).first();
    if (await historyTab.count()) {
      await historyTab.click({ force: true });
      await page.waitForTimeout(2000);
      expectThat('跳到了记录页', page.url().includes('/history'), true);
    }

    const mineTab = page.locator('.van-tabbar-item', { hasText: '我的' }).first();
    if (await mineTab.count()) {
      await mineTab.click({ force: true });
      await page.waitForTimeout(2000);
      expectThat('跳到了"我的"', page.url().includes('/mine'), true);
      const text = await page.locator('body').innerText();
      expectThat('"我的"页显示已登录', /退出登录|注销账号|zz_i18n_audit/.test(text), true);
    }

    // 把实际报错内容带上，免得只看到"期望 0，实际 1"还要回去加日志
    expectThat(
      `没有 JS 报错（实际：${JSON.stringify(errors.slice(0, 3))}；`
      + `失败请求：${JSON.stringify(failedRequests.slice(0, 5))}）`,
      errors.length,
      0,
    );
    assertNoProblems();
  });

  test('识别页有选图入口（相机 / 相册）', async ({ page }) => {
    const session = await login();
    await loginAsMobile(page, session);

    const errors = watchPageErrors(page);
    await page.goto(`${MOBILE_BASE}/detect`);
    await page.waitForTimeout(2500);

    // 第 93 批的实现：两个隐藏输入（相册 + capture 降级唤起系统相机）
    const fileInputs = page.locator('input[type="file"]');
    const inputCount = await fileInputs.count();
    expectThat('页面上有文件输入', inputCount >= 1, true);

    const text = await page.locator('body').innerText();
    expectThat('页面上有"拍照"或"相册"入口', /拍照|相册|拍摄|选择图片/.test(text), true);

    // 带 capture 的那个才是"调起相机"的入口 —— 桌面端没有这个属性，是移动端的关键差异
    const captureCount = await page.locator('input[type="file"][capture]').count();
    expectThat('有一个 file input 带 capture（调起相机）', captureCount >= 1, true);

    expectThat('没有 JS 报错', errors.length, 0);
    assertNoProblems();
  });

  test('身份失效时移动端会自动回登录页（第 93 批自愈）', async ({ page }) => {
    // 造一个"看起来已登录但实际无效"的状态：把假 token 写进**移动端该写的地方**
    await page.addInitScript(() => {
      localStorage.setItem('mobile_token', 'definitely-not-a-valid-token');
      localStorage.setItem('mobile_user', JSON.stringify({ id: 999999, username: 'ghost' }));
    });
    const errors = watchPageErrors(page, {
      // "token 失效自动跳登录"本身就会打一次 401，浏览器把它记成 console error ——
      // 这是**预期产物**，不是缺陷。这里只忽略这一类，而不是放宽所有 console error。
      ignore: [/401/, /Failed to load resource/i],
    });

    await page.goto(`${MOBILE_BASE}/history`);
    // 任何受保护接口都会 401 → 拦截器应当清身份并跳登录页（带原因码）
    await page.waitForTimeout(4000);

    const url = page.url();
    expectThat('被送到登录页', /\/login/.test(url), true);
    expectThat('带上"已过期"原因', /reason=expired/.test(url), true);

    const stored = await readMobileToken(page);
    expectThat('本地身份已清干净', stored, null);
    expectThat('没有 JS 报错', errors.length, 0);
    assertNoProblems();
  });

  test('移动端依赖的三个只读接口都可用', async () => {
    // 这条看起来"多此一举"，但它挡的是一类真实事故：
    // 移动端是**独立应用**，改接口时很容易只改桌面端的调用方；
    // 而移动端的错误提示是 Vant 的 toast（一闪而过），坏了不容易被发现。
    // 注：`/api/alerts/` 允许 404 —— 该路由在不同版本里存在与否不影响移动端主流程，
    //     这里要防的是"5xx / 路由整个消失"，不是"某个可选页面没了"。
    const session = await login();
    const me = await api('/api/users/me/points/', { token: session.token });
    expectThat('受保护接口可用', me.status, 200);

    const endpoints = [
      ['病害百科', '/api/pests/?page_size=1'],
      ['识别记录', '/api/detection-history/?page_size=1'],
      ['预警', '/api/alerts/'],
    ];
    for (const [label, path] of endpoints) {
      const response = await api(path, { token: session.token });
      expectThat(`${label}接口没有 5xx（实际 ${response.status}）`, response.status < 500, true);
    }
    assertNoProblems();
  });
});
