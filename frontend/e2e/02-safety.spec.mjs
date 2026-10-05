/**
 * 安全回归：历史上真实出过事的几条（第 103 批）
 * ============================================================================
 * 这些用例来自第 91 / 95 / 101 批的**真实事故**，不是"顺手加个测试"：
 *
 *   1. 存储型 XSS —— 帖子/评论用 `v-html` 渲染，只把 `\n` 换成 `<br>`，
 *      任何人发一条带 `<img onerror>` 的帖子就能在别人浏览器里执行脚本；
 *   2. 登录后门 `/api/token-auth/` —— DRF 自带的端点，`throttle_classes = ()`，
 *      完全绕过失败计数与限流，等于给撞库开了个不限速的口子；
 *   3. 注销护栏 —— 管理员不能删自己、不能删超级管理员；冷静期内可取消。
 *
 * 这类回归最适合 E2E：**它们都是"接口层的单元测试全绿、真实浏览器里仍然出事"
 * 的类型**（XSS 尤其是 —— 净化只在渲染时生效）。
 */
import { test, expect } from '@playwright/test';
import {
  api,
  cleanupByPrefix,
  clearThrottle,
  expectThat,
  assertNoProblems,
  login,
  loginAs,
  registerTempUser,
  resetChecks,
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

const PAYLOAD = '<img src=x onerror="window.__zze2e_xss=1">';

test.describe('安全回归（历史事故）', () => {
  test.beforeEach(() => resetChecks());
  test.afterAll(() => {
    cleanupByPrefix();
  });

  test('发帖内容里的脚本不会被执行（存储型 XSS）', async ({ page }) => {
    const session = await login();

    // ① 通过接口发一条带 payload 的帖子 —— 这一步必须**原样存进去**
    //    （如果后端就把它洗掉了，那这条用例测不到"渲染时有没有再洗一遍"）
    const boards = await api('/api/forums/boards/', { token: session.token });
    const boardId = (boards.json?.results ?? boards.json)?.[0]?.id;
    expectThat('拿到一个版块', typeof boardId === 'number', true);

    const created = await api('/api/forums/posts/', {
      method: 'POST',
      token: session.token,
      body: {
        board_id: boardId,
        title: `${TEMP_PREFIX} XSS 回归`,
        content: `前文${PAYLOAD}后文`,
      },
    });
    expectThat('帖子创建成功', created.status === 201 || created.status === 200, true);
    const postId = (created.json?.data ?? created.json)?.id;
    expectThat('拿到帖子 id', typeof postId === 'number', true);

    // ② 在真实浏览器里打开它
    const errors = watchPageErrors(page);
    await loginAs(page, session);
    await page.goto(`/forum/post/${postId}`);
    await page.waitForTimeout(2500);

    // ③ 核心断言：脚本没被执行
    const executed = await page.evaluate(() => Boolean(window.__zze2e_xss));
    expectThat('payload 没有被执行', executed, false);

    // ④ 断言"不可执行"，而不是断言"标签消失"
    //
    // ⚠️ 这里踩过两次**假失败**，都是断言写过头：
    //    ① 断言"渲染结果里没有 src=x 这种畸形图片标签" → 红了。
    //       诊断后发现净化其实**是生效的**：
    //         接口里存的：<img src=x onerror="window.__zze2e_xss=1">
    //         渲染出来的：<img src="x">            ← onerror 被 DOMPurify 剥掉
    //       `<img src="x">` 只是加载失败的安全残骸，不是漏洞。净化器的职责是
    //       "去掉可执行的部分"，不是"保持 HTML 好看"。
    //    ② 断言"整个 body 里没有 script 标签" → 又红了。
    //       原因更蠢：**页面本来就有 script**（Vite 注入的模块脚本、JSON-LD）。
    //       所以检查范围必须是**渲染正文的那个容器**，而不是整个文档。
    //    正确判据三条：没执行、正文里没有事件属性、正文里没有 script 标签。
    const contentHtml = await page.locator('.post-content').first().innerHTML()
      .catch(() => '');
    expectThat('拿到正文容器', contentHtml.length > 0, true);
    expectThat('正文里没有 onerror 属性', /onerror\s*=/i.test(contentHtml), false);
    expectThat('正文里没有 script 标签', /<script[\s>]/i.test(contentHtml), false);
    expectThat('正文里没有 javascript: 链接', /javascript:/i.test(contentHtml), false);
    expectThat('正文里有前文', contentHtml.includes('前文'), true);
    expectThat('正文里有后文', contentHtml.includes('后文'), true);

    // ⑤ 顺手确认页面没因为净化而报错
    expectThat('没有 JS 报错', errors.length, 0);

    // 清理这条帖子（软删除接口）
    await api(`/api/forums/posts/${postId}/`, { method: 'DELETE', token: session.token });
    assertNoProblems();
  });

  test('DRF 自带的 token-auth 后门保持关闭', async () => {
    // 这条端点在 91 批被移除：它与 /api/login/ 功能重叠，却完全绕过失败计数与限流
    const { status } = await api('/api/token-auth/', {
      method: 'POST',
      body: { username: 'zz_i18n_audit', password: 'ZzI18nAudit!2026' },
    });
    expectThat('POST /api/token-auth/ 返回 404', status, 404);

    // 正门仍然可用（证明"移除后门"没有把登录一起弄坏）
    const normal = await api('/api/login/', {
      method: 'POST',
      body: { username: 'zz_i18n_audit', password: 'ZzI18nAudit!2026' },
    });
    expectThat('POST /api/login/ 仍可登录', normal.status, 200);
    assertNoProblems();
  });

  test('注销护栏：不能删自己、不能删超级管理员', async ({ page }) => {
    const session = await login();
    const errors = watchPageErrors(page);
    await loginAs(page, session);
    await page.goto('/admin/users');
    await page.waitForSelector('.el-table__row', { timeout: TABLE_WAIT_MS });

    // 界面上：自己那一行的勾选框必须是禁用的（护栏在 UI 也拦一道）
    const selfRowDisabled = await page.evaluate((username) => {
      const rows = [...document.querySelectorAll('.el-table__row')];
      const row = rows.find((tr) => tr.innerText.includes(username));
      if (!row) return null;
      const box = row.querySelector('input[type="checkbox"]');
      return box ? box.disabled : null;
    }, session.user.username);
    expectThat('自己那一行勾选框禁用', selfRowDisabled, true);

    // 接口上：直接删自己必须被拒（前端禁用只是第一道）
    const del = await api(`/api/admin/users/${session.user.id}/`, {
      method: 'DELETE',
      token: session.token,
      body: { confirm: session.user.username },
    });
    expectThat('接口拒绝删除自己', del.status, 400);

    // 超级管理员同样不可删（即使操作者也是超管）
    const superuser = await api('/api/admin/users/', {
      token: session.token,
      raw: false,
    });
    const su = (superuser.json?.results ?? []).find((u) => u.is_superuser);
    if (su) {
      const delSu = await api(`/api/admin/users/${su.id}/`, {
        method: 'DELETE',
        token: session.token,
        body: { confirm: su.username },
      });
      expectThat('接口拒绝删除超级管理员', delSu.status, 400);
    }

    expectThat('没有 JS 报错', errors.length, 0);
    assertNoProblems();
  });

  test('注销冷静期：申请后登不上，但可凭密码取消', async () => {
    // ⚠️ 登录接口按 IP 限流 10/分钟，而这一整个 spec 会登录好几次
    //    （夹具账号 + 临时账号 + 注销后重登），实测撞 429 —— 表现像"功能坏了"。
    //    这些用例验证的是"注销/取消"的逻辑，不是限流，所以先把计数清零。
    clearThrottle();

    const temp = await registerTempUser('grace');

    // 申请注销
    const applied = await api('/api/users/me/delete/', {
      method: 'POST',
      token: temp.token,
      body: { password: temp.password, confirm: 'DELETE' },
    });
    expectThat('申请成功', applied.status, 200);
    expectThat('返回冷静期天数', typeof applied.json?.grace_days, 'number');

    // 冷静期内登不上，但提示必须说"可取消"（否则用户以为密码记错了）
    const blocked = await api('/api/login/', {
      method: 'POST',
      body: { username: temp.username, password: temp.password },
    });
    expectThat('冷静期内登录被拒', blocked.status, 403);
    expectThat('返回码标明可取消', blocked.json?.code, 'account_pending_deletion');

    // 取消注销（这个接口**允许匿名** —— 账号已停用，拿不到 Token）
    const cancelled = await api('/api/users/me/cancel-deletion/', {
      method: 'POST',
      body: { username: temp.username, password: temp.password },
    });
    expectThat('取消成功', cancelled.status, 200);
    expectThat('取消后直接签发 Token', typeof cancelled.json?.token, 'string');

    // 恢复后能正常登录
    const relogin = await api('/api/login/', {
      method: 'POST',
      body: { username: temp.username, password: temp.password },
    });
    expectThat('取消后可以登录', relogin.status, 200);
    assertNoProblems();
  });
});
