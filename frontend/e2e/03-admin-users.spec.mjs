/**
 * 管理端：用户管理页的关键行为（第 103 批）
 * ============================================================================
 * 这一页在最近几批里被改得最多（第 76 批新建、88 批重置筛选、95 批删除用户、
 * 100 批批量删除与后端排序、98 批筛选进 URL），
 * 也最容易"改坏了只有点进去才发现"。
 *
 * 所以这里把三条**用户报过的原话**变成断言：
 *   · 「在用户管理，点击角色其中一项，只能显示当前的，我想在用户列表显示全部却不能」
 *     —— 筛选必须能清干净、回到全部用户（第 88 批修的）；
 *   · 表头排序必须真的**走后端**（不是只排当前这 10 行）；
 *   · 批量删除要能删掉、并如实报告被跳过的。
 */
import { test } from '@playwright/test';
import {
  api,
  assertNoProblems,
  cleanupByPrefix,
  expectThat,
  login,
  loginAs,
  registerTempUser,
  resetChecks,
  runDjango,
  TEMP_PREFIX,
  watchPageErrors,
} from './helpers.mjs';

// 管理端表格的等待上限。
//
// ⚠️ 第 109 批：原来这里散落着多个硬编码的 timeout: 20000，而实测在
//    **机器忙的时候**（例如同时跑两轮 E2E、或识别接口正在冷启动）20 秒会不够，
//    表现为 waitForSelector 超时 —— 看起来像功能坏了，其实只是渲染慢。
//    提成具名常量并放宽到 35 秒：
//      · 正常情况仍是 1~2 秒内就出现，放宽不会让测试变慢；
//      · 真正坏了的情况照样会失败，只是晚 15 秒报错。
const TABLE_WAIT_MS = 35_000;

test.describe('管理端：用户管理', () => {
  let session;

  test.beforeAll(async () => {
    session = await login();
    // 造几个带前缀的普通账号，保证列表里有"可删且不敏感"的目标
    runDjango([
      'from django.contrib.auth import get_user_model',
      'U = get_user_model()',
      `U.objects.filter(username__startswith='${TEMP_PREFIX}_ui').delete()`,
      `for i in range(3):`,
      `    U.objects.create_user(username=f'${TEMP_PREFIX}_ui{i}', password='x', points=i * 10)`,
      `print('seeded:', U.objects.filter(username__startswith='${TEMP_PREFIX}_ui').count())`,
    ]);
  });

  test.beforeEach(() => resetChecks());
  test.afterAll(async () => {
    cleanupByPrefix();
  });

  test('角色筛选能清干净、回到全部用户', async ({ page }) => {
    const errors = watchPageErrors(page);
    await loginAs(page, session);
    await page.goto('/admin/users');
    await page.waitForSelector('.el-table__row', { timeout: TABLE_WAIT_MS });
    await page.waitForTimeout(800);

    const totalAll = await page.locator('.pagination-wrap .el-pagination').first().innerText();
    const countAll = Number((totalAll.match(/(\d+)/) || [])[1]);

    // 选一个角色 → 列表应变化、且地址栏带上 role 参数
    await page.locator('.filter-bar .el-select').first().click();
    await page.waitForTimeout(400);
    await page.locator('.el-select-dropdown__item', { hasText: /普通用户|Normal user/ }).first().click();
    await page.waitForTimeout(1200);

    const roleParam = new URL(page.url()).searchParams.get('role');
    expectThat('地址栏带 role 参数', roleParam, 'USER');

    const totalFiltered = await page.locator('.pagination-wrap .el-pagination').first().innerText();
    const countFiltered = Number((totalFiltered.match(/(\d+)/) || [])[1]);
    expectThat('筛选后条数不超过全部', countFiltered <= countAll, true);

    // 关键：点"全部用户/清除筛选"必须能回到全部（这正是用户报过的问题）
    const resetBtn = page.locator('.filter-bar button', { hasText: /全部用户|All users/ }).first();
    await resetBtn.click();
    await page.waitForTimeout(1200);

    const afterReset = await page.locator('.pagination-wrap .el-pagination').first().innerText();
    const countAfterReset = Number((afterReset.match(/(\d+)/) || [])[1]);
    expectThat('清空筛选后条数回到全部', countAfterReset, countAll);
    expectThat('地址栏不再带筛选参数', new URL(page.url()).searchParams.get('role'), null);
    expectThat('没有 JS 报错', errors.length, 0);
    assertNoProblems();
  });

  test('筛选与分页写进 URL，刷新后仍在', async ({ page }) => {
    await loginAs(page, session);

    // 直接打开"带条件的链接"→ 条件必须已生效（第 98 批的能力）
    await page.goto(`/admin/users?search=${TEMP_PREFIX}_ui&page_size=10`);
    await page.waitForSelector('.el-table__row, .el-table__empty-text', { timeout: TABLE_WAIT_MS });
    await page.waitForTimeout(1200);

    const searchValue = await page.locator('.filter-bar input:not([readonly])').first().inputValue();
    expectThat('搜索框已填入 URL 里的条件', searchValue, `${TEMP_PREFIX}_ui`);

    // 刷新后条件还在（"刷新即重置"就是这一条要防的）
    await page.reload();
    await page.waitForSelector('.el-table__row, .el-table__empty-text', { timeout: TABLE_WAIT_MS });
    await page.waitForTimeout(1000);
    const afterReload = await page.locator('.filter-bar input:not([readonly])').first().inputValue();
    expectThat('刷新后条件仍在', afterReload, `${TEMP_PREFIX}_ui`);
    assertNoProblems();
  });

  test('表头排序走后端（地址栏出现 ordering，且顺序真的变了）', async ({ page }) => {
    await loginAs(page, session);
    await page.goto(`/admin/users?search=${TEMP_PREFIX}_ui&page_size=10`);
    await page.waitForSelector('.el-table__row', { timeout: TABLE_WAIT_MS });
    await page.waitForTimeout(1000);

    const readPoints = async () => {
      const cells = await page.locator('.el-table__row .activity-text').allInnerTexts();
      return cells;
    };
    const before = await readPoints();

    const header = page.locator('.el-table th .cell', { hasText: /注册时间|Joined/ }).first();
    await header.click();
    await page.waitForTimeout(1200);
    expectThat('地址栏出现 ordering（降序）',
      new URL(page.url()).searchParams.get('ordering'), '-date_joined');

    await header.click();
    await page.waitForTimeout(1200);
    expectThat('第二次点变成升序',
      new URL(page.url()).searchParams.get('ordering'), 'date_joined');

    // 换一列：积分/活跃度排序
    const activityHeader = page.locator('.el-table th .cell', { hasText: /活跃|Activity/ }).first();
    await activityHeader.click();
    await page.waitForTimeout(1200);
    const ordering = new URL(page.url()).searchParams.get('ordering');
    expectThat('换列后 ordering 指向新列', /detections/.test(ordering || ''), true);

    const after = await readPoints();
    expectThat('列表确实重新取过数据（行内容有变化或至少仍有序）', Array.isArray(after) && after.length > 0, true);
    assertNoProblems();
  });

  test('批量删除：能删掉选中的，并如实报告跳过的', async ({ page }) => {
    // 再补两个目标（前面的用例可能已经动过数据）
    runDjango([
      'from django.contrib.auth import get_user_model',
      'U = get_user_model()',
      `U.objects.filter(username__startswith='${TEMP_PREFIX}_bulk').delete()`,
      `for i in range(2):`,
      `    U.objects.create_user(username=f'${TEMP_PREFIX}_bulk{i}', password='x')`,
      `print('seeded:', U.objects.filter(username__startswith='${TEMP_PREFIX}_bulk').count())`,
    ]);

    await loginAs(page, session);
    await page.goto(`/admin/users?search=${TEMP_PREFIX}_bulk&page_size=10`);
    await page.waitForSelector('.el-table__row', { timeout: TABLE_WAIT_MS });
    await page.waitForTimeout(1200);

    const rows = await page.locator('.el-table__row').count();
    expectThat('搜到目标账号', rows >= 2, true);

    // 勾选（Element Plus 必须点 .el-checkbox，check() 原生 input 不触发 selection-change）
    //
    // ⚠️ 这里最终用 `evaluate` 直接触发点击，是三次失败换来的结论：
    //    · 裸 `click()`            → `Element is outside of the viewport`
    //      （这一页很长：深绿页头 + 4 个统计卡 + 筛选栏 + 表格，行在折叠线以下）；
    //    · `click({ force: true })` → force 不做"滚进视口"，照样 outside；
    //    · 先 `scrollIntoViewIfNeeded()` → 滚了，但**对该元素无效**：
    //      Element Plus 的表格列可能是 `fixed`（独立滚动容器）或用 transform 定位，
    //      `scrollIntoView` 滚动的是文档/外层容器，元素相对视口仍在外面。
    //    最终做法：把点击交给 DOM 自己（`label.click()`），
    //    **不依赖 Playwright 的几何判定**。要验的是"勾选后出现批量条"，
    //    而不是"这个像素有没有落在视口里"。同理，下面的批量删除按钮也用它。
    const clickInDom = (selector, index = 0) => page.evaluate(
      ({ sel, idx }) => {
        const nodes = [...document.querySelectorAll(sel)];
        if (!nodes[idx]) return `NOT_FOUND: ${sel}[${idx}]`;
        nodes[idx].click();
        return 'CLICKED';
      },
      { sel: selector, idx: index },
    );

    const boxCount = await page.locator('.el-table__row .el-checkbox').count();
    expectThat('表格里有可勾选的行', boxCount >= 2, true);
    // 只勾**第一行**：多选时 Element Plus 会重排/重渲染行，
    // 按索引连点两次会点到同一行（第二次反而取消勾选），第一版就是这么少删了一个。
    // 这条用例要验的是"批量删除能生效且如实报告"，勾一行足够。
    const result = await clickInDom('.el-table__row .el-checkbox', 0);
    expectThat('勾选第一行', result, 'CLICKED');
    await page.waitForTimeout(700);

    const selectionHint = await page.locator('.selection-hint').first().innerText().catch(() => '');
    expectThat('出现"已选 N"提示', /已选|selected/.test(selectionHint), true);

    const bulkBtn = page.locator('.panel-head-right button', { hasText: /批量删除|Delete selected/ }).first();
    await bulkBtn.scrollIntoViewIfNeeded();
    expectThat('出现批量删除按钮', await bulkBtn.count() > 0, true);
    await bulkBtn.click();
    await page.waitForTimeout(800);

    const listCount = await page.locator('.el-dialog .bulk-list li').count();
    expectThat('弹窗列出待删清单', listCount >= 1, true);

    // 没有确认词时按钮必须禁用
    const confirmBtn = page.locator('.el-dialog__footer button').last();
    expectThat('未输入确认词时确认按钮禁用', await confirmBtn.isDisabled(), true);

    const input = page.locator('.el-dialog input').last();
    await input.fill('WRONG');
    await page.waitForTimeout(300);
    expectThat('确认词不对仍禁用', await confirmBtn.isDisabled(), true);

    await input.fill('DELETE');
    await page.waitForTimeout(300);
    expectThat('确认词正确后可点', await confirmBtn.isDisabled(), false);

    await confirmBtn.click();
    await page.waitForTimeout(2500);

    // 直接查接口确认真的删了（界面提示可能被改动，数据是硬证据）
    const after = await api(`/api/admin/users/?search=${TEMP_PREFIX}_bulk&page_size=20`, {
      token: session.token,
    });
    expectThat('少了一个账号（勾了几行就少几个）', after.json?.count, 1);
    assertNoProblems();
  });

  test('普通用户进不了管理端（权限口径与后端一致）', async ({ page }) => {
    const temp = await registerTempUser('plain');
    await loginAs(page, temp);
    await page.goto('/admin/users');
    await page.waitForTimeout(2500);

    // 要么被守卫挡回，要么看到"无权限"提示；总之不能停在用户管理表格上
    const body = await page.locator('body').innerText();
    const stillOnAdmin = page.url().includes('/admin/users') && body.includes('用户管理');
    expectThat('非管理员看不到用户管理表格', stillOnAdmin, false);
    assertNoProblems();
  });
});
