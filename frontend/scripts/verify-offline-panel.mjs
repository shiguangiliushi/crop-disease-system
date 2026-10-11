/**
 * 「离线队列失败项能被处理」端到端验证（第 162 批）
 * ============================================================================
 * 用户截图里页眉挂着「2 张同步失败」，点它却毫无反应 —— 因为：
 *   · 一条任务失败 3 次后被标记 `failed`，`pending()` 不再取它；
 *   · 指示器唯一的交互是"点一下同步"，而同步只处理 pending。
 * 于是那两条永远卡在那里：不知道是哪两张、不知道为什么失败、也不能重试或丢掉。
 *
 * 这个脚本直接往 IndexedDB 里塞两条**已失败**的任务（模拟用户那两条），然后验证：
 *   ① 页眉显示「2 张同步失败」
 *   ② 点开面板能看到两条明细（文件名 / 时间 / 已试次数 / 失败原因）
 *   ③ 「全部重试」把它们重新排队（tries 归零）→ 会真的尝试同步
 *   ④ 「全部丢弃」把它们清掉 → 页眉提示消失、队列清空
 *
 * 用法：node scripts/verify-offline-panel.mjs
 */
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';

const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

// 登录用真实 admin（token 注入，不需要密码）
clearThrottle();
const seed = runDjango([
  'import json',
  'from django.contrib.auth import get_user_model',
  'from rest_framework.authtoken.models import Token',
  'from api.serializers import CustomUserSerializer',
  "u = get_user_model().objects.get(username='admin')",
  'token, _ = Token.objects.get_or_create(user=u)',
  "print('ZZ_TOKEN=' + token.key)",
  "print('ZZ_USER=' + json.dumps(CustomUserSerializer(u).data, ensure_ascii=False))",
]);
const token = /ZZ_TOKEN=(\S+)/.exec(seed)?.[1];
const userJson = /ZZ_USER=(.+)/.exec(seed)?.[1];

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1500, height: 950 }, locale: 'zh-CN' })).newPage();
const pageErrors = [];
page.on('pageerror', (error) => pageErrors.push(String(error).slice(0, 200)));

await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
await page.evaluate(([tokenValue, userValue]) => {
  window.sessionStorage.setItem('auth_token', tokenValue);
  window.sessionStorage.setItem('user', userValue);
}, [token, userJson]);

// ---------------------------------------------------------------------------
// 造两条「已失败」的离线任务（直接写 IndexedDB，与队列的实现结构一致）
// ---------------------------------------------------------------------------
await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);

const seeded = await page.evaluate(async () => {
  const DB = 'crop_offline';
  const STORE = 'pending_detections';
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) {
        request.result.createObjectStore(STORE, { keyPath: 'id' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

  const blob = new Blob([new Uint8Array([1, 2, 3, 4])], { type: 'image/jpeg' });
  const now = Date.now();
  const items = [
    {
      id: `zz-failed-${now}-1`, blob, filename: 'zz离线叶片A.jpg', note: '', size: 4,
      createdAt: now - 3600_000, status: 'failed', tries: 3, lastError: '识别服务暂时不可用',
    },
    {
      id: `zz-failed-${now}-2`, blob, filename: 'zz离线叶片B.jpg', note: '', size: 4,
      createdAt: now - 1800_000, status: 'failed', tries: 3, lastError: '网络错误，请检查您的网络连接',
    },
  ];
  await new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    const store = tx.objectStore(STORE);
    store.clear();
    items.forEach((item) => store.put(item));
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  return items.map((item) => item.filename);
});
console.log('  已写入两条失败任务:', seeded.join(' / '));

// 重新载入，让指示器读取队列
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForSelector('.offline-chip', { timeout: 20_000 });
await page.waitForTimeout(2000);

// ---------------------------------------------------------------------------
// ① 页眉提示
// ---------------------------------------------------------------------------
const chipText = (await page.locator('.offline-chip').first().innerText()).trim();
check('页眉显示「2 张同步失败」', chipText.includes('2') && chipText.includes('同步失败'), chipText);
await page.screenshot({ path: 'dsh-shots/offline-chip.png', clip: { x: 0, y: 0, width: 1500, height: 70 } });

// ---------------------------------------------------------------------------
// ② 面板明细
// ---------------------------------------------------------------------------
await page.locator('.offline-chip').first().click();
await page.waitForSelector('.offline-panel', { timeout: 15_000 });
await page.waitForTimeout(800);
const panelText = await page.locator('.offline-panel').innerText();
check('面板列出了两条明细', /zz离线叶片A\.jpg/.test(panelText) && /zz离线叶片B\.jpg/.test(panelText),
  panelText.replace(/\s+/g, ' ').slice(0, 100));
check('明细里有「已尝试 3 次」', panelText.includes('已尝试 3 次'), '');
check('明细里带了失败原因', /识别服务暂时不可用|网络错误/.test(panelText), '');
check('面板有重试与丢弃入口', /重试/.test(panelText) && /丢弃/.test(panelText), '');
await page.screenshot({ path: 'dsh-shots/offline-panel.png', clip: { x: 560, y: 0, width: 840, height: 560 } });

// ---------------------------------------------------------------------------
// ③ 全部重试 → 重新排队（tries 归零）
// ---------------------------------------------------------------------------
await page.getByRole('button', { name: '全部重试' }).click();
await page.waitForTimeout(4000);

const afterRetry = await page.evaluate(async () => {
  const db = await new Promise((resolve) => {
    const request = indexedDB.open('crop_offline', 1);
    request.onsuccess = () => resolve(request.result);
  });
  const rows = await new Promise((resolve) => {
    const all = db.transaction('pending_detections', 'readonly').objectStore('pending_detections').getAll();
    all.onsuccess = () => resolve(all.result || []);
  });
  return rows.map((row) => ({ filename: row.filename, status: row.status, tries: row.tries }));
});
check('「全部重试」之后不再有 failed 状态（已重新排队）',
  afterRetry.every((row) => row.status !== 'failed'),
  JSON.stringify(afterRetry).slice(0, 140));

// ---------------------------------------------------------------------------
// ④ 丢弃 → 队列清空、提示消失
// ---------------------------------------------------------------------------
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2500);

// 重新造两条失败项（上一步已被重新排队并尝试过），再验证丢弃
await page.evaluate(async () => {
  const db = await new Promise((resolve) => {
    const request = indexedDB.open('crop_offline', 1);
    request.onsuccess = () => resolve(request.result);
  });
  const now = Date.now();
  const blob = new Blob([new Uint8Array([9])], { type: 'image/jpeg' });
  await new Promise((resolve) => {
    const tx = db.transaction('pending_detections', 'readwrite');
    const store = tx.objectStore('pending_detections');
    store.clear();
    [1, 2].forEach((index) => store.put({
      id: `zz-drop-${now}-${index}`, blob, filename: `zz待丢弃${index}.jpg`, note: '', size: 1,
      createdAt: now, status: 'failed', tries: 3, lastError: '演示',
    }));
    tx.oncomplete = () => resolve();
  });
});
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForSelector('.offline-chip', { timeout: 20_000 });
await page.waitForTimeout(2000);

await page.locator('.offline-chip').first().click();
await page.waitForSelector('.offline-panel', { timeout: 15_000 });
await page.waitForTimeout(600);
await page.getByRole('button', { name: '全部丢弃' }).click();
await page.waitForSelector('.el-message-box', { timeout: 10_000 });
await page.locator('.el-message-box__btns button').filter({ hasText: '确定' }).first().click();
await page.waitForTimeout(2500);

const finalState = await page.evaluate(async () => {
  const db = await new Promise((resolve) => {
    const request = indexedDB.open('crop_offline', 1);
    request.onsuccess = () => resolve(request.result);
  });
  const rows = await new Promise((resolve) => {
    const all = db.transaction('pending_detections', 'readonly').objectStore('pending_detections').getAll();
    all.onsuccess = () => resolve(all.result || []);
  });
  return { rows: rows.length, chip: document.querySelector('.offline-chip')?.innerText?.trim() || null };
});
check('「全部丢弃」把队列清空了', finalState.rows === 0, `剩余 ${finalState.rows} 条`);
check('页眉提示随之消失', finalState.chip === null, finalState.chip || '（已消失）');

check('全程无 JS 报错', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await browser.close();

const passed = results.filter((r) => r.ok).length;
console.log(`\n${passed}/${results.length} 项通过`);
if (passed !== results.length) {
  results.filter((r) => !r.ok).forEach((r) => console.log(`  · 失败：${r.name}`));
  process.exit(1);
}
