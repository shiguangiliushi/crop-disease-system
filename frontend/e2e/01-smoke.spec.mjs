/**
 * 冒烟：服务活着、登录能走通（第 103 批）
 * ============================================================================
 * 这套 E2E 的"第 0 层"。它在几十秒内回答一个问题：
 * **前端能打开、后端能应答、用真账号能登进去。**
 *
 * 之所以单独成一个 spec（而不是混在功能用例里）：一旦这一层红了，
 * 后面所有用例的红都**不值得看** —— 直接修服务，别看功能断言。
 */
import { test, expect } from '@playwright/test';
import { api, login, expectThat, assertNoProblems, resetChecks, watchPageErrors } from './helpers.mjs';

test.describe('冒烟：服务与登录', () => {
  test.beforeEach(() => resetChecks());

  test('后端健康检查返回 ok，且自带数据库与缓存结论', async () => {
    const { status, json } = await api('/api/health/?deep=true');
    expectThat('HTTP 状态', status, 200);
    expectThat('status', json?.status, 'ok');
    expectThat('数据库检查通过', Boolean(json?.checks?.database?.ok), true);
    expectThat('迁移已应用', Boolean(json?.checks?.migrations?.ok), true);
    assertNoProblems();
  });

  test('匿名访问受保护页面会被送到登录页', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/admin/users');

    // 路由守卫应当带 reason=loginRequired（第 84 批起只传原因码，由登录页翻译）
    await page.waitForURL(/\/login/, { timeout: 15000 });
    expectThat('落在登录页', /\/login/.test(page.url()), true);
    expectThat('带上跳转原因', new URL(page.url()).searchParams.get('reason'), 'loginRequired');
    expectThat('没有 JS 报错', errors.length, 0);
  });

  test('用真实账号登录后能进到首页，并且顶栏显示用户名', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/login');
    await page.waitForSelector('form');

    await page.locator('#username, input[type="text"]').first().fill('zz_i18n_audit');
    await page.locator('input[type="password"]').first().fill('ZzI18nAudit!2026');
    await page.locator('button[type="submit"]').first().click();

    // 登录成功会离开 /login
    await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 20000 });
    expectThat('已离开登录页', page.url().includes('/login'), false);

    const body = await page.locator('body').innerText();
    expectThat('顶栏出现用户名', body.includes('zz_i18n_audit'), true);
    expectThat('页面没有 JS 报错', errors.filter((e) => !e.includes('favicon')).length, 0);
  });

  test('密码错误时给出可读提示，且不会误判为登录成功', async ({ page }) => {
    await page.goto('/login');
    await page.waitForSelector('form');

    await page.locator('#username, input[type="text"]').first().fill('zz_i18n_audit');
    await page.locator('input[type="password"]').first().fill('definitely-wrong-password');
    await page.locator('button[type="submit"]').first().click();
    await page.waitForTimeout(2500);

    expectThat('仍停在登录页', page.url().includes('/login'), true);
    const text = await page.locator('body').innerText();
    expectThat('提示里说明是密码问题', /密码|password/i.test(text), true);

    // 接口层面也必须是否认的（界面文案可能被改，状态码是硬约束）
    const { status } = await api('/api/login/', {
      method: 'POST',
      body: { username: 'zz_i18n_audit', password: 'definitely-wrong-password' },
    });
    expectThat('登录接口拒绝', status === 401 || status === 423, true);
  });

  test('登录夹具账号可用（后续用例的前提）', async () => {
    const session = await login();
    expectThat('拿到 Token', typeof session.token === 'string' && session.token.length > 10, true);
    expectThat('返回的是管理员', Boolean(session.user?.is_staff || session.user?.is_superuser), true);

    const me = await api('/api/users/me/points/', { token: session.token });
    expectThat('Token 能访问受保护接口', me.status, 200);
  });
});
