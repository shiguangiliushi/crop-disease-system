/**
 * uni-app H5 端关键路径（第 280 批）
 *
 * 已有 `05-mobile.spec.mjs`（Vant H5）与 `08-mobile-features.spec.mjs`（Vant 新增能力）。
 * uni-app 是**另一个独立工程**（mobile-uni，:5175），桌面端/Vant 全绿完全不能说明它是对的 ——
 * 今天它已经连续踩过 5 个只有真机/真浏览器才暴露的坑（i18n 命名空间、`useI18n` 不存在、
 * `onLoad` 必须在 setup、`reactive.value`、选择器被 `›` 挡住）。
 *
 * 这条 spec 用**最少的断言**守住三条最容易坏的路径：
 *   1. 登录 → 我的 → 系统通知（列表 + 「N 条未读」）
 *   2. 我的 → 我的反馈（列表或空状态）
 *   3. 我的 → 意见反馈（类型 chips + 文本域 + 联系方式）
 *
 * ⚠️ uni H5 用 hash 路由（`#/pages/...`），登录页是首页 `#/`。
 */
import { test, expect } from '@playwright/test';

const UNI = process.env.E2E_UNI_URL || 'http://127.0.0.1:5175';
const ACCOUNT = { username: 'zz_i18n_audit', password: 'ZzI18nAudit!2026' };

async function loginUni(page) {
  await page.goto(`${UNI}/`, { waitUntil: 'networkidle' });
  await page.locator('input').nth(0).fill(ACCOUNT.username);
  await page.locator('input').nth(1).fill(ACCOUNT.password);
  await page.locator('.btn-primary').first().click();
  await expect(page).toHaveURL(/#\/pages\/detect\/detect/, { timeout: 15000 });
}

test.describe('uni-app · 关键路径', () => {
  test('登录 → 我的 → 系统通知', async ({ page }) => {
    await loginUni(page);

    await page.goto(`${UNI}/#/pages/mine/mine`, { waitUntil: 'networkidle' });
    const entry = page.getByText('系统通知', { exact: true });
    await expect(entry).toBeVisible();

    await entry.click();
    await expect(page).toHaveURL(/#\/pages\/notify\/notify/);
    await expect(page.locator('.hint')).toContainText('条未读');
  });

  test('我的 → 我的反馈 / 意见反馈 页面可达', async ({ page }) => {
    await loginUni(page);

    await page.goto(`${UNI}/#/pages/myfeedback/myfeedback`, { waitUntil: 'networkidle' });
    await expect(page.locator('.page')).toBeVisible();
    // 等 loading 消失再断言（uni 的 onMounted 请求比 Vant 晚一拍，实测会抢跑）
    await expect(page.locator('.loading')).toHaveCount(0, { timeout: 15000 });
    // 有数据时是卡片，没数据时是空状态提示 —— 两者都算页面正常
    const hasCards = await page.locator('.card').count();
    const emptyText = await page.getByText('还没有提交过反馈').count();
    expect(hasCards + emptyText).toBeGreaterThan(0);

    await page.goto(`${UNI}/#/pages/feedback/feedback`, { waitUntil: 'networkidle' });
    await expect(page.locator('.chip')).toHaveCount(3);
    await expect(page.locator('textarea')).toHaveCount(1);
  });
});
