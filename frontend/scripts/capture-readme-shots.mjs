/**
 * 为 README 采集农户端截图（第 153 批）
 * ============================================================================
 * 起因：仓库里 33 张截图**全是管理端与登录页**，README（简历上挂的那个链接的首屏）
 * 却一张图都没有 —— 而截图目录 `frontend/dsh-shots/` 是 gitignore 的，GitHub 上看不到。
 *
 * 这个脚本做两件事：
 *   ① 用一个临时农户账号跑一遍农户端的核心页面（含**真实识别**：上传样图、等推理结果）；
 *   ② 截图后按宽度 1200 缩放，输出到 `docs/images/`（**入库**目录）供 README 引用。
 *
 * 用法：node scripts/capture-readme-shots.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const suffix = Math.random().toString(36).slice(2, 6);
const password = 'ZzE2e!2026pw';
const farmerName = `zze2e_demo_${suffix}`;
const boardName = `zze2e演示版块${suffix}`;
const outDir = path.resolve('..', 'docs', 'images');
const sample = path.resolve('..', 'backend', 'pests', 'Apple___Apple_scab14.jpg');

fs.mkdirSync(outDir, { recursive: true });

const cleanup = () => {
  clearThrottle();
  try {
    runDjango([
      'from django.contrib.auth import get_user_model',
      'from api.models_forum import Comment, Post, ForumBoard',
      "print('cleaned posts:', Post.objects.filter(title__startswith=\"zz演示\").delete()[0])",
      "print('cleaned boards:', ForumBoard.objects.filter(name__startswith='zze2e演示版块').delete()[0])",
      'U = get_user_model()',
      "print('cleaned users:', U.objects.filter(username__startswith='zze2e_demo_').delete()[0])",
    ]);
  } catch (error) {
    console.error('清理失败（忽略）:', error?.message || error);
  }
};
process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });

// ---------------------------------------------------------------------------
// 造数据：一个农户 + 一条置顶精华帖 + 一条普通帖 + 一条评论
// ---------------------------------------------------------------------------
clearThrottle();
runDjango([
  'from django.contrib.auth import get_user_model',
  'from api.models_forum import Comment, Post, ForumBoard',
  'U = get_user_model()',
  `u = U.objects.create_user(username='${farmerName}', password='${password}', role='USER')`,
  "u.first_name = '李'",
  "u.last_name = '农户'",
  "u.save(update_fields=['first_name', 'last_name'])",
  `b = ForumBoard.objects.create(name='${boardName}', order=900)`,
  // ⚠️ JS 里相邻字符串必须显式 + 拼接（我第一版直接换行写，成了语法错误）
  "p1 = Post.objects.create("
  + "title='zz演示：叶片背面这些白点是什么？', "
  + "content='<p>大棚里的黄瓜，最近叶子背面出现密集白色小点，摸上去有点黏。请问是白粉虱还是别的原因？</p>', "
  + "author=u, board=b, status='published', is_pinned=True, is_essence=True, "
  + 'view_count=128, like_count=12)',
  "Post.objects.create("
  + "title='zz演示：连续阴雨后要不要补喷一次杀菌剂？', "
  + "content='<p>连着下了四天雨，棚里湿度很高，之前打的药是不是被冲掉了？</p>', "
  + "author=u, board=b, status='published', view_count=64, like_count=5)",
  "Post.objects.create("
  + "title='zz演示：玉米大斑病初期求助', "
  + "content='<p>叶片上出现梭形褐色斑点，边缘有黄晕，是不是大斑病？该怎么用药？</p>', "
  + "author=u, board=b, status='published', view_count=41, like_count=3)",
  "Comment.objects.create(post=p1, author=u, content='补充：早上看更明显，中午会飞起来一片。')",
  "p1.update_comment_count()",
  "print('seeded')",
]);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e).slice(0, 160)));

const shoot = async (name) => {
  const file = path.join(outDir, name);
  await page.screenshot({ path: file, fullPage: false });
  const kb = Math.round(fs.statSync(file).size / 1024);
  console.log(`  📷 ${name}（${kb} KB）`);
};

clearThrottle();
await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('input[type="password"]', { timeout: 30_000 });
await page.locator('input#username, input[type="text"]').first().fill(farmerName);
await page.locator('input[type="password"]').first().fill(password);
await page.locator('button[type="submit"]').first().click();
await page.waitForTimeout(3500);

// ① 首页（识别入口所在）
await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2500);
await shoot('farmer-home.png');

// ② 识别页：**真上传一张叶片图**，等推理结果
await page.goto(`${UI}/detect`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2000);
const fileInput = page.locator('input[type="file"]').first();
await fileInput.setInputFiles(sample);
await page.waitForTimeout(1500);
// ⚠️ 选图之后还要**点「开始识别」**才会推理。
// 第一版我只等了文本"识别结果"，结果被页面下方说明文字（"查看病害详情与防治方案"那排）
// 误命中 —— 截出来的是"已选好图、待点按钮"的状态，不是识别结果。
await page.locator('button', { hasText: '开始识别' }).first().click();
console.log('  已点「开始识别」，等待推理结果…');
try {
  // 结果区有稳定类名：.results-container / .confidence-chip（见 DetectView.vue）
  await page.waitForSelector('.results-container', { timeout: 120_000 });
  await page.waitForSelector('.confidence-chip', { timeout: 30_000 });
  await page.waitForTimeout(2500);
  console.log('  ✓ 识别结果已出现（真实模型推理）');
} catch (error) {
  console.log('  ⚠️ 没等到结果区：', error.message.slice(0, 80));
  await page.waitForTimeout(1500);
}
await shoot('farmer-detect-result.png');

// ③ 论坛交流（能看到置顶/精华标签）
await page.goto(`${UI}/forum`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3000);
await shoot('farmer-forum.png');

// ④ 病害百科
await page.goto(`${UI}/pests`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3000);
await shoot('farmer-wiki.png');

await browser.close();
clearThrottle();
console.log('JS 报错：', errors.length ? errors.slice(0, 3).join(' | ') : '（无）');
console.log('输出目录：', outDir);
