/**
 * 智能回答助手抽屉的端到端用例（第 194 批）
 * ============================================================================
 * 验的是"识别完能不能就地追问"这条完整链路：
 *   识别出结果 → 点"问一下助手" → 点快捷问题 → 拿到真实回答（带来源引用）
 *
 * 为什么必须走浏览器而不是只跑后端测试：
 *   · 后端单测（`api.tests.AssistantTests`）验的是链路与降级，**不验界面**；
 *   · 这一批里真出过一个只有界面检查能发现的问题 —— `el-drawer` **没在
 *     `plugins/element-plus.js` 注册**，漏注册不会报错，只会渲染成未知元素、
 *     点了没反应。`npm run check:components` 当场报出来了，这条用例是第二道网。
 *
 * ⚠️ 这条用例会**真的调用大模型**（后端 `LLM_ENABLED=True` 时）：
 *    · 每次跑会计费（一次问答约几千 prompt tokens）；
 *    · 需要外网可达 api.deepseek.com；
 *    · 回答内容由模型生成，所以断言只能验**结构**（有引用、有长度、有免责句），
 *      不能验具体措辞 —— 否则模型换个说法就假红。
 *   若不想花钱/无外网：把后端 `LLM_ENABLED=False` 再跑，此时走降级分支
 *   （回答是词条原文 + "AI 暂不可用"），本用例会自动改用宽松断言。
 */
import { test, expect } from '@playwright/test';
import { readdirSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  BACKEND_DIR,
  assertNoProblems,
  cleanupByPrefix,
  gotoAuthed,
  loginAs,
  registerTempUser,
  resetChecks,
  watchPageErrors,
} from './helpers.mjs';

/** 找一张"够小、够真"的测试图（与 04-detection 同一口径：CPU 推理不能被大图拖爆） */
function pickTestImage() {
  const dir = resolve(BACKEND_DIR, 'media/detection_history');
  let names = [];
  try {
    names = readdirSync(dir);
  } catch {
    return null;
  }
  const candidate = names
    .filter((n) => /\.(jpe?g|png)$/i.test(n))
    .map((n) => ({ name: n, path: resolve(dir, n), size: statSync(resolve(dir, n)).size }))
    .filter((f) => f.size > 10 * 1024 && f.size < 800 * 1024)
    .sort((a, b) => a.size - b.size)[0];
  return candidate || null;
}

test.describe('智能回答助手', () => {
  /**
   * ⚠️ 自己注册临时账号，**不用夹具账号**：`helpers.login()` 默认用审计夹具
   * `zz_i18n_audit`，而它只在跑 i18n 审计脚本时才被种进库里 —— 直接跑本用例会
   * 404「用户名或密码错误」（第一次跑就是这么失败的）。
   * 按 helpers 的约定：自己造数据、跑完自己清。
   */
  test.afterAll(() => {
    try {
      cleanupByPrefix();
    } catch (error) {
      console.log(`  ↳ 清理临时账号时出错（不影响用例结论）：${error.message}`);
    }
  });

  test('识别结果页能就地追问，回答带来源引用', async ({ page }) => {
    // 走完整推理 + 一次真实问答：识别冷启动最长 21s，问答 3~6s，给足余量
    test.setTimeout(240_000);
    resetChecks();

    const image = pickTestImage();
    test.skip(!image, '没有可用的测试图片（backend/media/detection_history 下缺图）');

    const session = await registerTempUser('asst');
    const pageErrors = watchPageErrors(page);
    await loginAs(page, session);

    await gotoAuthed(page, '/detect');
    await page.waitForTimeout(1500);

    // ── 一、先做一次识别，拿到结果卡片 ────────────────────────────────
    const fileInputs = page.locator('input[type="file"]');
    await fileInputs.first().setInputFiles(image.path);
    await page.waitForTimeout(1200);

    const startBtn = page.locator('button', { hasText: /开始识别|开始检测/ }).first();
    await startBtn.click();

    const resultsReady = await page
      .waitForSelector('.result-detail-card, .confidence-chip', { timeout: 120_000 })
      .then(() => true)
      .catch(() => false);
    expect(resultsReady, '识别结果没渲染出来，后续步骤无法进行').toBe(true);

    // ── 二、追问入口必须出现（登录状态 + 有结果）──────────────────────
    const entry = page.locator('.ask-assistant-entry');
    const entryVisible = await entry
      .waitFor({ state: 'visible', timeout: 15_000 })
      .then(() => true)
      .catch(() => false);
    expect(entryVisible, '识别结果页没有出现"问一下助手"入口').toBe(true);

    const contextName = (await entry.locator('strong').textContent().catch(() => '')) || '';
    console.log(`  ↳ 追问入口标题：${contextName.trim()}`);

    // ── 三、打开抽屉 ──────────────────────────────────────────────────
    await entry.locator('button').first().click();
    const drawer = page.locator('.ask-assistant-drawer');
    const drawerVisible = await drawer
      .waitFor({ state: 'visible', timeout: 15_000 })
      .then(() => true)
      .catch(() => false);
    expect(
      drawerVisible,
      '抽屉没打开 —— 若控制台报未知元素，多半是 el-drawer 没在 plugins/element-plus.js 注册',
    ).toBe(true);

    // 顶部上下文提示要带上刚识别的病害名（证明 pest_identifier 透传了）
    const contextText = (await drawer.locator('.assistant-context').textContent().catch(() => '')) || '';
    console.log(`  ↳ 抽屉上下文：${contextText.trim()}`);
    expect(contextText.trim().length, '抽屉顶部没有显示当前追问的病害名').toBeGreaterThan(0);

    // ── 四、快捷问题：点一下就能问（省去打字）─────────────────────────
    const suggestions = drawer.locator('.assistant-suggestions button');
    const suggestionCount = await suggestions.count();
    expect(suggestionCount, '没有渲染出快捷问题按钮').toBeGreaterThan(0);
    await suggestions.nth(1).click(); // 第 2 个是"打什么药" —— 最需要引用来源的那类问题

    // 用户气泡立刻出现
    await page.waitForTimeout(600);
    const userBubbles = drawer.locator('.assistant-msg.is-user');
    expect(await userBubbles.count(), '用户提问没有回显到对话里').toBeGreaterThan(0);

    // ── 五、等助手回答 ────────────────────────────────────────────────
    // ⚠️ 这里**不能**只等 `.assistant-bubble` 出现就读数：加载中的骨架
    //    （`.assistant-typing`，内容是"正在查找词条并组织回答…"共 12 字）
    //    也是 `.assistant-bubble`，会先出现。第一版就是这么错的 ——
    //    全量套件里读到 12 字（骨架文本）判"回答太短"，单独跑却拿到 346 字真答案。
    //    正确做法：先等**骨架消失**（loading 结束），再读最后一条气泡。
    const assistantBubble = drawer.locator('.assistant-msg.is-assistant .assistant-bubble');
    const answered = await assistantBubble
      .first()
      .waitFor({ state: 'visible', timeout: 120_000 })
      .then(() => true)
      .catch(() => false);
    expect(
      answered,
      '助手没有返回回答 —— 检查后端 LLM_ENABLED / 外网是否可达（无外网时应走降级，也应有回答）',
    ).toBe(true);

    const typingGone = await drawer
      .locator('.assistant-typing')
      .waitFor({ state: 'detached', timeout: 120_000 })
      .then(() => true)
      .catch(() => false);
    expect(typingGone, '助手一直停在"思考中"状态，没有给出回答').toBe(true);

    // 取**最后一条**助手气泡：多条时 latest 才是本轮的回答
    const lastBubble = drawer.locator('.assistant-msg.is-assistant .assistant-bubble').last();
    const answerText = (await lastBubble.textContent()) || '';
    console.log(`  ↳ 回答长度：${answerText.trim().length} 字`);
    console.log(`  ↳ 回答开头：${answerText.trim().slice(0, 60)}…`);

    // ⚠️ 这条断言曾经很脆：全量套件里跑时会拿到"词条未收录"的 50 字兜底答案，
    //    单独跑却总是 346 字真答案。原因不在助手本身，而在它**依赖识别结果**：
    //    识别那一步在套件里偶发失败（前端离线分支 / 推理超时）时，页面上就没有
    //    `pest_identifier`，检索于是匹配不到词条 → 走"未收录"分支。
    //    所以这里失败时要把**抽屉里到底显示了什么**一并打出来，
    //    否则只看"回答太短"根本分不清是助手坏了还是识别没成功。
    expect(
      answerText.trim().length,
      `回答太短（${answerText.trim().length} 字），疑似走了兜底分支。\n`
      + `  抽屉上下文：${contextText.trim()}\n`
      + `  实际回答：${answerText.trim().slice(0, 200)}\n`
      + '  → 若回答是"词条未收录"，请先确认这一步的识别是否真的成功（pest_identifier 是否为空）',
    ).toBeGreaterThan(30);

    // ── 六、回答必须来自知识库（两种模式各验各的）────────────────────
    const degraded = await drawer.locator('.assistant-degrade').count();
    if (degraded > 0) {
      // 降级模式：应当明确说明"AI 暂不可用 / 未收录"等，而不是假装答了
      const hint = (await drawer.locator('.assistant-degrade').first().textContent()) || '';
      console.log(`  ↳ 降级提示：${hint.trim()}`);
      expect(hint.trim().length, '降级时没有给用户任何说明').toBeGreaterThan(0);
    } else {
      // 正常模式：必须有来源引用（"无来源不回答"是设计约定）
      const cites = drawer.locator('.assistant-cite');
      const citeCount = await cites.count();
      console.log(`  ↳ 来源引用：${citeCount} 处`);
      expect(citeCount, '正常回答里没有任何来源引用').toBeGreaterThan(0);
    }

    // ── 七、控制台不能有 JS 报错 ──────────────────────────────────────
    const realErrors = pageErrors.filter((e) => !/favicon|ResizeObserver/i.test(e));
    expect(realErrors, `页面出现 JS 报错：\n  ${realErrors.join('\n  ')}`).toEqual([]);

    // ⚠️ 本用例**不清理识别记录**：新产生的记录属于开发库的正常数据，
    //    而要清它就得记住 history_id（本用例没取）。E2E 的清理约定见 helpers.mjs
    //    里 `cleanupDetections` 的说明 —— 需要严格清理时请在那里补一次调用。
    assertNoProblems();
  });
});
