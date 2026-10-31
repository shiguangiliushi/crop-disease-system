/**
 * 管理端 · 意见反馈页的统计卡筛选（第 283 批）
 *
 * 第 271 批给四张统计卡加了「点一下按该状态筛选、再点清空」，但**没有回归测试** ——
 * 而这一批正好踩过两个坑（`filters` 是 ref 却当普通对象赋值；函数没进 `setup()` 的 return，
 * 控制台报 `_ctx.filterByStatus is not a function`）。这里把它钉住。
 */
import { test, expect } from '@playwright/test';
import { login, loginAs } from './helpers.mjs';

const ADMIN_FEEDBACK = '/admin/feedback';

test.describe('管理端 · 意见反馈统计卡筛选', () => {
  test('点「待处理」→ 高亮 + URL 带 status；再点一次清空', async ({ page }) => {
    const session = await login();
    await loginAs(page, session);

    await page.goto(ADMIN_FEEDBACK, { waitUntil: 'networkidle' });
    await expect(page.locator('.stat-tile.clickable')).toHaveCount(3);

    const tile = page.locator('.stat-tile--pending');
    await tile.click();

    await expect(tile).toHaveClass(/active/);
    await expect(page).toHaveURL(/status=pending/);

    await tile.click();
    await expect(tile).not.toHaveClass(/active/);
    await expect(page).not.toHaveURL(/status=pending/);
  });
});
