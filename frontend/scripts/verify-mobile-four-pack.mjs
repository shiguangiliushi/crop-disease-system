/**
 * 移动端「离线/健壮性四件套」浏览器回归（第 91 批）
 * ------------------------------------------------------------------
 * 移动端工程自己**没有测试依赖**（0 单测，是已知边界），而 `@playwright/test` 装在
 * `frontend/` 里 —— 所以移动端的浏览器验证脚本放在这边跑（`mobile/README.md` 里同样写明）。
 *
 * 验证四件事，每一条都是农户真实场景会踩的：
 *   ① 401 自愈：token 失效 → 自动清身份 + 跳登录页 + 明确告诉用户"登录已过期"
 *      （改前：界面仍显示已登录，各页只报"请求失败"，用户得自己想到去退出重登）
 *   ② keep-alive：识别页选好照片 → 切到"记录" → 切回来，**照片还在**
 *      （改前：组件被销毁重建，照片没了 → 在田里戴着手套重拍）
 *   ③ 忘记密码：登录页有入口、页面能打开、提交后显示"邮件已发送"
 *      （改前：移动端根本没有这一页，忘了密码 = 永久登不进）
 *   ④ 离线队列：断网时点识别 → 照片进 IndexedDB 队列 + 出现待传提示
 *      （改前：只弹一句"当前离线"，农户白拍一张）
 *
 * 用法：
 *   cd frontend && node scripts/verify-mobile-four-pack.mjs
 *   MOBILE_BASE_URL=http://192.168.1.5:5174 node scripts/verify-mobile-four-pack.mjs
 *
 * 前置：移动端 5174 + 后端 8000 已启动；审计夹具账号存在
 *      （backend/_seed_i18n_audit_tmp.py，admin 与 user 各一个）。
 */
import { chromium } from '@playwright/test';
import { writeFileSync, mkdirSync, existsSync } from 'node:fs';
import path from 'node:path';

const BASE = process.env.MOBILE_BASE_URL || 'http://127.0.0.1:5174';
const API = process.env.I18N_AUDIT_API_URL || 'http://127.0.0.1:8000';
const USER = 'zz_i18n_audit';
const PASSWORD = 'ZzI18nAudit!2026';
const SHOTS = 'dsh-shots';

const log = (...a) => console.log(...a);
let failures = 0;
const check = (label, ok, detail = '') => {
  log(`${ok ? '✓' : '✗'} ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures += 1;
};

/** 造一张真实的小 PNG，用于 file input */
function makePng(filePath) {
  const base64 =
    'iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAOklEQVR42u3OMQEAAAgDoJnc6BpjDyRg'
    + 'blXVvXsAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB4NfUAAT8jV38AAAAASUVORK5CYII=';
  writeFileSync(filePath, Buffer.from(base64, 'base64'));
  return filePath;
}

async function getToken() {
  const res = await fetch(`${API}/api/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASSWORD }),
  });
  if (!res.ok) throw new Error(`登录失败 ${res.status()}`);
  const body = await res.json();
  return { token: body.data.token, user: body.data.user };
}

async function main() {
  if (!existsSync(SHOTS)) mkdirSync(SHOTS, { recursive: true });
  const pngPath = makePng(path.join(SHOTS, '_tmp_mobile_leaf.png'));
  const { token, user } = await getToken();
  log(`已取到 token（${user.username}）`);

  const browser = await chromium.launch();
  const errors = [];

  // ═══════════════════════════════════════════════════════════════
  // ① 401 自愈
  // ═══════════════════════════════════════════════════════════════
  log('\n── ① 401 自愈 ─────────────────────────────');
  {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await ctx.addInitScript(() => {
      // 塞一个**无效** token：模拟"登录已过期"
      localStorage.setItem('mobile_token', 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef');
      localStorage.setItem('mobile_user', JSON.stringify({ id: 1, username: 'stale' }));
    });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => errors.push(`[401] ${e.message.split('\n')[0]}`));

    await page.goto(`${BASE}/history`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2500);

    const url = page.url();
    const onLogin = url.includes('/login');
    check('失效 token 访问 /history 被送到登录页', onLogin, url.replace(BASE, ''));

    const flagConsumed = await page.evaluate(() => ({
      token: localStorage.getItem('mobile_token'),
      user: localStorage.getItem('mobile_user'),
    }));
    check('本地身份已被清理', !flagConsumed.token && !flagConsumed.user,
      JSON.stringify(flagConsumed));

    const notice = await page.locator('.van-notice-bar').first().innerText().catch(() => '');
    check('登录页提示"登录已过期"', /过期|expired/i.test(notice), notice.trim() || '(没有提示条)');
    await page.screenshot({ path: `${SHOTS}/mobile-91-401-expired.png` });
    await ctx.close();
  }

  // ═══════════════════════════════════════════════════════════════
  // ② keep-alive：切 tab 不丢照片
  // ═══════════════════════════════════════════════════════════════
  log('\n── ② keep-alive（切 tab 保照片）───────────');
  {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await ctx.addInitScript(({ tk, u }) => {
      localStorage.setItem('mobile_token', tk);
      localStorage.setItem('mobile_user', JSON.stringify(u));
    }, { tk: token, u: user });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => errors.push(`[keep-alive] ${e.message.split('\n')[0]}`));

    await page.goto(`${BASE}/detect`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1200);

    // 从"相册"入口选一张图（file input 是隐藏的，直接 setInputFiles）
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(pngPath);
    await page.waitForTimeout(1200);

    const previewBefore = await page.locator('.preview img, .preview-image, img[alt]').first()
      .getAttribute('src').catch(() => null);
    const hasPreviewBefore = Boolean(previewBefore && previewBefore.startsWith('data:'));
    check('识别页已选好照片（预览是 dataURL）', hasPreviewBefore,
      previewBefore ? previewBefore.slice(0, 40) : '(没有预览)');

    // 切到"记录"再切回来
    await page.locator('.van-tabbar-item', { hasText: /记录|Records/ }).first().click();
    await page.waitForTimeout(1200);
    const onHistory = page.url().includes('/history');
    check('已切到记录页', onHistory, page.url().replace(BASE, ''));

    await page.locator('.van-tabbar-item', { hasText: /识别|Detect/ }).first().click();
    await page.waitForTimeout(1200);

    const previewAfter = await page.locator('.preview img, .preview-image, img[alt]').first()
      .getAttribute('src').catch(() => null);
    const hasPreviewAfter = Boolean(previewAfter && previewAfter.startsWith('data:'));
    check('切回来后照片**还在**（keep-alive 生效）', hasPreviewAfter,
      hasPreviewAfter ? '预览仍在' : '(照片没了)');
    await page.screenshot({ path: `${SHOTS}/mobile-91-keepalive.png` });
    await ctx.close();
  }

  // ═══════════════════════════════════════════════════════════════
  // ③ 忘记密码
  // ═══════════════════════════════════════════════════════════════
  log('\n── ③ 忘记密码入口 ─────────────────────────');
  {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => errors.push(`[forgot] ${e.message.split('\n')[0]}`));

    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1200);

    const link = page.locator('a[href="/forgot-password"]');
    check('登录页有「忘记密码」入口', await link.count() > 0);

    // 法务链接应指向桌面端（不再是 /terms 死链）
    const legalHref = await page.locator('.auth-terms a').first().getAttribute('href').catch(() => null);
    check('法务链接指向真实法务页（不是 /terms 死链）',
      Boolean(legalHref && /^https?:\/\//.test(legalHref)), legalHref || '(没有法务链接)');

    await page.goto(`${BASE}/forgot-password`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(800);
    await page.locator('input').first().fill('zz_i18n_audit@example.invalid');
    await page.locator('button[type="submit"], .van-button--primary').first().click();
    await page.waitForTimeout(2000);

    const body = await page.locator('body').innerText();
    check('提交后显示"邮件已发送"', /邮件已发送|Email sent/.test(body),
      body.includes('邮件已发送') ? '已提示' : body.slice(0, 60).replace(/\n/g, ' '));
    await page.screenshot({ path: `${SHOTS}/mobile-91-forgot.png` });
    await ctx.close();
  }

  // ═══════════════════════════════════════════════════════════════
  // ④ 离线队列
  // ═══════════════════════════════════════════════════════════════
  log('\n── ④ 离线队列（断网时不再白拍）─────────────');
  {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await ctx.addInitScript(({ tk, u }) => {
      localStorage.setItem('mobile_token', tk);
      localStorage.setItem('mobile_user', JSON.stringify(u));
    }, { tk: token, u: user });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => errors.push(`[offline] ${e.message.split('\n')[0]}`));

    await page.goto(`${BASE}/detect`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1200);

    await page.locator('input[type="file"]').first().setInputFiles(pngPath);
    await page.waitForTimeout(1000);

    // 断网（Playwright 的离线模式会同时让 navigator.onLine=false）
    await ctx.setOffline(true);
    await page.waitForTimeout(500);

    await page.locator('button', { hasText: /开始识别|Start detection/ }).first().click();
    await page.waitForTimeout(2500);

    const bodyText = await page.locator('body').innerText();
    check('提示已离线保存', /已离线保存|Saved offline/.test(bodyText),
      bodyText.includes('已离线保存') ? '已提示' : '(没有提示)');

    // 首选项若出现"确认"按钮，点掉
    const confirmBtn = page.locator('.van-dialog__confirm');
    if (await confirmBtn.count()) {
      await confirmBtn.first().click();
      await page.waitForTimeout(600);
    }

    // 队列里应该有 1 条（直接读 IndexedDB）
    const queued = await page.evaluate(() => new Promise((resolve) => {
      const req = indexedDB.open('crop_mobile_offline', 1);
      req.onsuccess = () => {
        const db = req.result;
        const tx = db.transaction('pending_detections', 'readonly');
        const all = tx.objectStore('pending_detections').getAll();
        all.onsuccess = () => resolve(all.result.map((i) => ({ id: i.id, size: i.size, status: i.status })));
        all.onerror = () => resolve([]);
      };
      req.onerror = () => resolve([]);
    }));
    check('照片已进 IndexedDB 离线队列', queued.length >= 1, JSON.stringify(queued));

    // 离线状态条应出现
    await page.waitForTimeout(800);
    const bar = await page.locator('.offline-bar').count();
    check('底部出现离线/待传状态条', bar > 0, `匹配 ${bar} 个`);
    await page.screenshot({ path: `${SHOTS}/mobile-91-offline-queue.png` });

    // 恢复联网 → 状态条点击触发补传（这里只验证"能触发"，不校验识别结果）
    await ctx.setOffline(false);
    await page.waitForTimeout(1500);
    const barText = await page.locator('.offline-bar').first().innerText().catch(() => '');
    log(`   恢复联网后状态条文案：${barText.replace(/\n/g, ' ').trim() || '(已消失，说明已补传完)'}`);

    await ctx.close();
  }

  await browser.close();
  log(`\n页面 JS 报错：${errors.length ? `\n  ${errors.join('\n  ')}` : '无'}`);
  check('全程无 JS 报错', errors.length === 0);

  log(`\n结论：${failures === 0 ? '✅ 四件套全部通过' : `❌ ${failures} 项未通过`}`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error('脚本自身出错：', err?.stack || String(err));
  process.exit(2);
});
