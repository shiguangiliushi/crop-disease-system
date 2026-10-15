/**
 * 独立问答页的端到端用例（第 198 批）
 * ============================================================================
 * 验的是"手上没有识别结果时也能提问，并且问过的能找回来"这条链路：
 *   打开 /assistant → 点快捷问题 → 拿到真实回答 → 左侧出现这次问答
 *   → 刷新后仍在 → 点回去能看到历史 → 删除后消失
 *
 * 为什么必须走浏览器：
 *   · 后端单测（`api.tests.AssistantSessionViewTests`）只验接口，
 *     **不验"页面有没有把它渲染出来"**；
 *   · 这一批前几个改动里已经踩过两次"只改数据源、忘了改消费端"
 *     （识别响应没带 identifier → 助手永远答"未收录"），
 *     所以"从页面能不能真的走通"必须有一条自动化用例守着。
 *
 * ⚠️ 与 06 一样会**真的调用大模型**（`LLM_ENABLED=True` 时计费、需外网）。
 *    为省费用，本用例只问 **1 个**问题。无外网时后端走降级，
 *    断言会自动退到"有回答即可"（降级也是一条回答）。
 */
import { test, expect } from '@playwright/test';
import {
  cleanupByPrefix,
  gotoAuthed,
  loginAs,
  registerTempUser,
  resetChecks,
  watchPageErrors,
} from './helpers.mjs';

test.describe('智能问答页', () => {
  // 与 06 同一约定：自己造账号、跑完自己清（夹具账号只在 i18n 审计时才存在）
  test.afterAll(() => {
    try {
      cleanupByPrefix();
    } catch (error) {
      console.log(`  ↳ 清理临时账号时出错（不影响用例结论）：${error.message}`);
    }
  });

  test('能开新提问、拿到回答，并在历史里看到它', async ({ page }) => {
    // 一次真实问答 3~9s，加上页面加载与接口往返，给足余量
    test.setTimeout(180_000);
    resetChecks();
    const pageErrors = watchPageErrors(page);

    const fixture = await registerTempUser('asstpage');
    await loginAs(page, fixture);

    await gotoAuthed(page, '/assistant');

    // ── 一、页面骨架 ────────────────────────────────────────────────────
    await expect(page.locator('.assistant-page')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole('heading', { name: /智能问答|Smart Q&A/ })).toBeVisible();
    console.log('  ↳ 页面已打开，标题可见');

    // 空态（新账号没有任何历史）
    await expect(page.locator('.assistant-side-empty')).toBeVisible({ timeout: 15_000 });
    console.log('  ↳ 历史为空态：已显示');

    // ── 二、开新提问 → 点快捷问题 ──────────────────────────────────────
    const preset = page.locator('.assistant-presets button').first();
    await expect(preset).toBeVisible({ timeout: 10_000 });
    const presetText = (await preset.textContent())?.trim() || '';
    console.log(`  ↳ 快捷问题：${presetText.slice(0, 40)}`);
    await preset.click();

    // 用户那条消息应当立刻出现在对话里
    await expect(page.locator('.assistant-msg.is-user')).toHaveCount(1, { timeout: 10_000 });

    // ── 三、等回答（并确认**真的在流**）────────────────────────────────
    const bubbles = page.locator('.assistant-msg.is-assistant .assistant-bubble');
    await expect(bubbles.first()).toBeVisible({ timeout: 60_000 });

    // 采样长度：流式下应当逐步增长，而不是停在一个值上不动。
    // ⚠️ "生成结束"的信号试错了两次，都记下来：
    //    ① 用 `.assistant-typing` 消失 —— **不对**：第 195 批改成流式后，骨架只在
    //       "还没收到第一个字"时显示，一出字就消失，而**骨架内部也是 `.assistant-bubble`**，
    //       所以那一刻可能只匹配到骨架（第一版就采样到 2 字，快照里却明明有完整回答）。
    //    ② 用「发送按钮解禁」—— **也不对**：本页 `:disabled="!draft.trim()"`，
    //       提交后 draft 被清空，按钮**一直禁着**，等它解禁必然超时。
    //    可靠的信号是 Element Plus 在 loading 期间加在按钮上的 `is-loading` class。
    const sendBtn = page.locator('.assistant-send button, button.assistant-send').first();
    const samples = [];
    for (let i = 0; i < 40; i += 1) {
      const text = (await bubbles.last().textContent().catch(() => '')) || '';
      samples.push(text.trim().length);
      const busy = await sendBtn.evaluate((el) => el.classList.contains('is-loading'))
        .catch(() => true);
      if (!busy && samples.length >= 2 && samples.at(-1) === samples.at(-2)) break;
      await page.waitForTimeout(300);
    }
    console.log(`  ↳ 长度采样（每 4 次抽一个）：${samples.filter((_, i) => i % 4 === 0).join(' → ')} … 末值 ${samples.at(-1)}`);
    const grew = new Set(samples.filter((n) => n > 0)).size;
    expect(grew, `回答长度没有变化（${samples.join('/')}）—— 疑似没走流式`).toBeGreaterThan(1);

    // 再等一会确保最后一个 delta 已落地，然后读最终长度
    await sendBtn.evaluate((el) => el.classList.contains('is-loading')).catch(() => {});
    await page.waitForTimeout(500);
    const answer = (await bubbles.last().textContent()) || '';
    console.log(`  ↳ 回答长度：${answer.trim().length} 字（气泡数 ${await bubbles.count()}）`);
    expect(
      answer.trim().length,
      `回答太短（${answer.trim().length} 字）—— 检查后端 LLM_ENABLED / 外网；无外网时应走降级但仍有档案原文`,
    ).toBeGreaterThan(30);

    // ── 四、历史里应当出现这次问答 ─────────────────────────────────────
    const sideItems = page.locator('.assistant-side-item');
    await expect(sideItems).toHaveCount(1, { timeout: 20_000 });
    const title = (await sideItems.first().locator('.assistant-side-title span').first().textContent())?.trim();
    console.log(`  ↳ 历史条目标题：${title}`);
    expect(title, '历史条目标题为空').toBeTruthy();
    // 预览取的是回答的开头，不该是空白
    const preview = (await sideItems.first().locator('.assistant-side-preview').textContent())?.trim();
    expect(preview, '历史条目预览为空 —— 后端可能取到了流式留下的空消息行').toBeTruthy();

    // ── 五、刷新后仍在，且点回去能看到完整问答 ─────────────────────────
    const sessionUrl = page.url();
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.locator('.assistant-page').waitFor({ state: 'visible', timeout: 20_000 });
    await expect(page.locator('.assistant-side-item')).toHaveCount(1, { timeout: 20_000 });
    console.log('  ↳ 刷新后历史仍在');

    await page.locator('.assistant-side-item').first().click();
    // 历史会话应当渲染出 2 条消息（用户 + 助手）
    await expect(page.locator('.assistant-msg')).toHaveCount(2, { timeout: 20_000 });
    const restored = (await page.locator('.assistant-msg.is-assistant .assistant-bubble').last()
      .textContent()) || '';
    expect(restored.trim().length, '点回历史后回答内容为空').toBeGreaterThan(30);
    console.log(`  ↳ 点回历史：恢复 ${restored.trim().length} 字，URL=${sessionUrl.replace(/.*\/\//, '')}`);

    // ── 六、删除 ────────────────────────────────────────────────────────
    // ⚠️ 删除按钮是 **hover 才显形** 的（`.assistant-side-item:hover .assistant-side-del
    //    { opacity: 1 }`）。第一版直接 `click({ force: true })` 报 15s 超时，
    //    且快照里根本没出现确认弹窗 —— 说明点击没落到按钮上（force 只跳过可见性等待，
    //    并不改变元素的实际可点区域）。先 hover 让它显形再点，才是真实用户的操作。
    const item = page.locator('.assistant-side-item').first();
    await item.hover();
    await page.waitForTimeout(200);   // 等 CSS 过渡（0.15s）走完
    await item.locator('.assistant-side-del').click();

    const confirmBox = page.locator('.el-message-box');
    await expect(confirmBox).toBeVisible({ timeout: 10_000 });
    // 按文案点"删除"，而不是"最后一个按钮"（按钮顺序会随语言/主题变化）
    await confirmBox.locator('button', { hasText: /删除这次问答|Delete this conversation/ }).click();
    await expect(page.locator('.assistant-side-item')).toHaveCount(0, { timeout: 20_000 });
    await expect(page.locator('.assistant-side-empty')).toBeVisible({ timeout: 10_000 });
    console.log('  ↳ 删除后历史回到空态');

    // ── 七、控制台不能有 JS 报错 ────────────────────────────────────────
    const realErrors = pageErrors.filter((e) => !/favicon|ResizeObserver|404/i.test(e));
    expect(realErrors, `页面出现 JS 报错：\n  ${realErrors.join('\n  ')}`).toEqual([]);
  });

  test('导航里有「智能问答」入口，点进去能打开', async ({ page }) => {
    test.setTimeout(90_000);
    const fixture = await registerTempUser('asstnav');
    await loginAs(page, fixture);
    await gotoAuthed(page, '/');

    // ⚠️ 顶栏在单行模式下用的是 `navShort.*`（短文案「问答」），
    //    而悬停 title 才是 `nav.*`（「智能问答」）。第一版按长文案找，找不到。
    //    所以按**链接地址**定位 —— 这才是稳定的选择器。
    const link = page.locator('.navigation a[href="/assistant"]').first();
    const linkVisible = await link.waitFor({ state: 'visible', timeout: 15_000 })
      .then(() => true).catch(() => false);
    expect(linkVisible, '顶栏导航里没有「智能问答」入口（a[href="/assistant"]）').toBe(true);
    console.log(`  ↳ 导航入口文案：${(await link.textContent())?.trim()}`);

    await link.click();
    await page.waitForURL(/\/assistant/, { timeout: 15_000 });
    await expect(page.locator('.assistant-page')).toBeVisible({ timeout: 20_000 });
    console.log('  ↳ 导航入口可点，路由跳转正常');
  });
});
