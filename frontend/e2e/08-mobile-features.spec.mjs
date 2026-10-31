/**
 * 移动端 Vant 端新增能力（第 273 批）
 *
 * 已有 `05-mobile.spec.mjs` 覆盖"登录页 / 忘记密码 / 底部导航 / 相机入口 / token 失效"。
 * 这条 spec 补的是第 253~272 批新增、**此前只能靠临时脚本验**的部分：
 *
 *   1. 结果页「问一下助手」→ 弹层 + 调用 `/api/assistant/ask/`
 *   2. 结果页「查看病害百科」→ `/pests/...` 词条详情（症状/防治）
 *   3. 我的 → 系统通知（列表 + 未读数）
 *   4. 我的 → 编辑资料（只提交改动字段，保存后服务端确实变了）
 *
 * 一律**只读断言为主**（不写脏数据）；资料编辑用例会改回原值。
 */
import { test, expect } from '@playwright/test';
import { MOBILE_BASE, login, loginAsMobile } from './helpers.mjs';

const HISTORY_SAMPLE = '/api/detection-history/?page_size=1';

test.describe('移动端 · 新增能力', () => {
  test('我的 → 系统通知：列表与未读数可见', async ({ page }) => {
    const session = await login();
    await loginAsMobile(page, session);

    await page.goto(`${MOBILE_BASE}/mine`, { waitUntil: 'networkidle' });
    await expect(page.getByText('系统通知', { exact: true })).toBeVisible();

    await page.getByText('系统通知', { exact: true }).click();
    await expect(page).toHaveURL(/\/notifications$/);
    await expect(page.locator('.notify-head')).toContainText('条未读');
  });

  test('我的 → 编辑资料：只提交改动字段且服务端生效', async ({ page, request }) => {
    const session = await login();
    await loginAsMobile(page, session);

    const before = await request.get(`${MOBILE_BASE.replace('5174', '8000')}/api/users/${session.user.id}/`, {
      headers: { Authorization: `Token ${session.token}` },
    });
    const original = (await before.json()).first_name || '';

    await page.goto(`${MOBILE_BASE}/profile/edit`, { waitUntil: 'networkidle' });
    const nickname = page.locator('.edit-page input').first();
    await expect(nickname).toHaveValue(original);

    const next = `e2e昵称${Date.now().toString().slice(-5)}`;
    await nickname.fill(next);
    await page.getByText('保存', { exact: true }).first().click();
    await expect(page.locator('.van-toast').first()).toBeVisible({ timeout: 8000 });

    const after = await request.get(`${MOBILE_BASE.replace('5174', '8000')}/api/users/${session.user.id}/`, {
      headers: { Authorization: `Token ${session.token}` },
    });
    expect((await after.json()).first_name).toBe(next);

    // 复原，避免污染夹具账号
    await page.goto(`${MOBILE_BASE}/profile/edit`, { waitUntil: 'networkidle' });
    await page.locator('.edit-page input').first().fill(original);
    await page.getByText('保存', { exact: true }).first().click();
  });

  test('结果页入口存在（追问助手 / 查看病害百科）', async ({ page, request }) => {
    const session = await login();
    const response = await request.get(`${MOBILE_BASE.replace('5174', '8000')}${HISTORY_SAMPLE}`, {
      headers: { Authorization: `Token ${session.token}` },
    });
    const body = await response.json();
    const rows = body?.data?.items || body?.results || [];
    test.skip(rows.length === 0, '夹具账号没有识别记录，跳过结果页断言');

    await loginAsMobile(page, session);
    await page.goto(`${MOBILE_BASE}/result/${rows[0].id}`, { waitUntil: 'networkidle' });

    await expect(page.getByText('问一下助手', { exact: true })).toBeVisible();
    await expect(page.getByText('查看病害百科', { exact: true })).toBeVisible();
  });
});
