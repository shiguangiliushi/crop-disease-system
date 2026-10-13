/**
 * 统一生成 README / docs 用的界面截图（第 160 批；第 189 批按页面合并改过路由）
 * ============================================================================
 * ## 为什么要重做
 *
 * 之前那 8 张图分两处来：
 *   · 农户端 4 张 ← `capture-readme-shots.mjs`（**一次性**农户账号 `zze2e_demo_xxx`）；
 *   · 管理端 4 张 ← 各管理端 E2E 脚本顺带截的（**一次性**管理员账号 `zze2e_xxx`）。
 * 于是 README 的截图里顶栏写着 `zze2e_demo_k3f9` 这种机器名 —— 挂在 GitHub 首屏很难看。
 *
 * 这个脚本用**真实的管理员账号 `admin`** 一次截全，并且：
 *   · **不需要 admin 的密码**：通过 Django 给 `admin` 签发一个 token，
 *     再用登录接口同款的 `CustomUserSerializer` 数据注入 `sessionStorage`
 *     （键名与 `utils/authStorage.js` 一致：`auth_token` / `user`）；
 *   · 演示内容（帖子/评论/操作日志）都**挂在 admin 名下**，截图里不会出现临时账号；
 *   · 识别结果那张会真的上传仓库里的苹果黑星病图片并等结果出来
 *     （所以图上显示的是**中文**病害名 + 真实症状与防治建议）。
 *
 * ## ⚠️ 第 189 批：这些截图为什么必须重截
 *
 * 第 183/184/185/186 批把管理端入口合并了（侧栏从"内容审核/论坛管理/评论管理/系统健康/
 * 操作日志/版块管理"六项变成「内容管理」+「系统」两项），而本脚本还在访问**旧地址**：
 *   · `/admin/forum` → 现在会重定向到「内容管理 · 帖子」，截出来的是**另一个页面**
 *     （README 上那张"论坛管理"图里，侧栏和面包屑都是早就没有的旧结构）；
 *   · `/admin/comments` 的"已删除"筛选落在**帖子**页签上 → 切筛选自然没生效，
 *     截出来的不是"评论可恢复"那张；
 *   · `/admin/audit-logs` → 现在是「系统 · 操作日志」页签。
 * 所以本批把地址全部改成**直接落到页签**（`/admin/content?tab=…`、`/admin/health?tab=…`），
 * 并新增一张「系统 · 系统健康」（README 的图说里一直有"系统健康"，但没有对应截图）。
 *
 * 用法：
 *   node scripts/capture-docs-shots.mjs            # 截 PNG 到 dsh-shots/
 *   python docs/tools/optimize_readme_images.py    # 再转成 WebP 入 docs/images/
 *
 * ⚠️ 只截图，不改业务数据；演示内容在结束时清理（帖子里带 `zz演示` 前缀）。
 */
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from '@playwright/test';
import { runDjango, clearThrottle } from '../e2e/helpers.mjs';

const UI = 'http://127.0.0.1:5173';
const OUT = path.resolve('dsh-shots');
const LEAF_IMAGE = path.resolve('..', 'backend', 'pests', 'Apple___Apple_scab14.jpg');
const ADMIN = 'admin';

fs.mkdirSync(OUT, { recursive: true });

const log = (text) => console.log(text);

// ---------------------------------------------------------------------------
// ① 演示内容：都挂在 admin 名下（截图里就不会出现临时账号）
// ---------------------------------------------------------------------------
clearThrottle();
const seedOutput = runDjango([
  'import json',
  'from django.contrib.auth import get_user_model',
  'from rest_framework.authtoken.models import Token',
  'from api.models_forum import Comment, ForumBoard, Post',
  'from api.audit import log_admin_action',
  'from api.serializers import CustomUserSerializer',
  `admin = get_user_model().objects.get(username='${ADMIN}')`,
  // 演示版块 + 三条帖子（都归 admin，标题带 zz演示 便于清理）
  // ⚠️ 第 189 批：版块名改成**像真的**（原来叫 `zze2e演示版块`，会显示在截图里的帖子行上，
  //    既是机器名又难看）；清理仍按 `zze2e演示版块` 前缀，所以这里保留前缀只改后半段。
  "board, _ = ForumBoard.objects.get_or_create(name='zze2e演示版块 · 作物病害交流', defaults={'order': 900})",
  // 顺便清掉上一版留下的旧名版块 + 上一次运行留下的同名纪录，避免开发库里堆演示版块
  "print('cleaned stale demo boards:', ForumBoard.objects.filter(name='zze2e演示版块').delete()[0])",
  "Post.objects.filter(title__startswith='zz演示').delete()",
  "p1 = Post.objects.create(title='zz演示：叶片背面这些白点是什么？', content='<p>大棚里的黄瓜，最近叶子背面出现密集白色小点，摸上去有点黏。请问是白粉虱还是别的原因？</p>', author=admin, board=board, status='published', is_pinned=True, is_essence=True, view_count=128, like_count=12)",
  "Post.objects.create(title='zz演示：连续阴雨后要不要补喷一次杀菌剂？', content='<p>连着下了四天雨，棚里湿度很高，之前打的药是不是被冲掉了？</p>', author=admin, board=board, status='published', view_count=64, like_count=5)",
  "Post.objects.create(title='zz演示：玉米大斑病初期求助', content='<p>叶片上出现梭形褐色斑点，边缘有黄晕，是不是大斑病？该怎么用药？</p>', author=admin, board=board, status='published', view_count=41, like_count=3)",
  "Comment.objects.filter(content__startswith='zz演示').delete()",
  // 一条"被软删除、可恢复"的评论：评论管理页的恢复按钮要能看见
  // ⚠️ 文案里别出现引号 —— 这是嵌在 JS 字符串里的 Python 代码，
  //    第一版写了 `演示"恢复"`，直接把 JS 字符串截断成语法错误。
  "c = Comment.objects.create(post=p1, author=admin, content='zz演示：这条评论被删掉了，用来演示恢复功能')",
  "from api.views_forum import soft_delete_comment",
  'soft_delete_comment(c, by=admin)',
  "p1.update_comment_count()",
  // 几条操作日志：让"操作日志"页有内容可看（且操作人都是 admin）
  // ⚠️ target 要传**对象**（快照从 user.username / post.title 取）；想显示成自定义文字
  //    就显式给 target_repr。第一版把字符串当 target 传，页面渲染成
  //    「built-in method title of str object at 0x...」。
  "log_admin_action(admin, 'post.pin', p1, '演示：置顶了一篇求助帖', target_type='post', target_id=p1.id)",
  "log_admin_action(admin, 'comment.soft_delete', None, '演示：删除了一条不当评论', target_type='comment', target_id=c.id, target_repr='一条灌水评论')",
  "log_admin_action(admin, 'user.role_change', admin, '演示：调整了一位用户的角色')",
  // 给 admin 签发 token + 登录接口同款的 user 数据
  'token, _ = Token.objects.get_or_create(user=admin)',
  "print('ZZ_TOKEN=' + token.key)",
  "print('ZZ_USER=' + json.dumps(CustomUserSerializer(admin).data, ensure_ascii=False))",
  "print('ZZ_PID=' + str(p1.id))",
]);
const token = /ZZ_TOKEN=(\S+)/.exec(seedOutput)?.[1];
const userJson = /ZZ_USER=(.+)/.exec(seedOutput)?.[1];
if (!token || !userJson) {
  console.error('❌ 没能从 Django 拿到 admin 的 token/user：', seedOutput);
  process.exit(1);
}
const seeded = JSON.parse(userJson);
log(`以管理员 ${seeded.username}（role=${seeded.role}）身份截图`);
log(`  能力: ${(seeded.capabilities || []).join(', ') || '（未下发）'}`);

// ---------------------------------------------------------------------------
// ② 打开浏览器并注入登录态
// ---------------------------------------------------------------------------
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error).slice(0, 160)));

// 先访问一次站点，才有同源 storage 可写
await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
await page.evaluate(([tokenValue, userValue]) => {
  window.sessionStorage.setItem('auth_token', tokenValue);
  window.sessionStorage.setItem('user', userValue);
}, [token, userJson]);

const shoot = async (name) => {
  const file = path.join(OUT, name);
  await page.screenshot({ path: file, fullPage: false });
  log(`  📷 ${name}（${Math.round(fs.statSync(file).size / 1024)} KB）`);
};

const goto = async (url, selector, settle = 1800) => {
  await page.goto(`${UI}${url}`, { waitUntil: 'domcontentloaded' });
  // ⚠️ 用 `state: 'attached'`：识别页那个 file input 是 `d-none`（隐藏的），
  //    默认的 'visible' 会一直等到超时。
  if (selector) await page.waitForSelector(selector, { timeout: 30_000, state: 'attached' });
  await page.waitForTimeout(settle);
};

// ---------------------------------------------------------------------------
// ③ 农户端 4 张（顶栏现在是 admin）
// ---------------------------------------------------------------------------
log('农户端：');
await goto('/', '.home-hero, .hero, h1');
await shoot('farmer-home.png');

// 识别结果：真的上传那张苹果黑星病图片并等结果（图上应是**中文**名 + 真实症状/防治）
await goto('/detect', 'input[type="file"]', 1200);
await page.locator('input[type="file"]').first().setInputFiles(LEAF_IMAGE);
await page.waitForTimeout(800);
await page.getByRole('button', { name: '开始识别' }).first().click();
await page.waitForSelector('.results-container, .detect-disease-name', { timeout: 180_000 });
// 多等一会儿：右下角那个"识别完成!"吐司要等它自己消失，否则会被截进图里
await page.waitForTimeout(6000);
await shoot('farmer-detect-result.png');

await goto('/forum', '.post-list, .forum-list, .post-card');
await shoot('farmer-forum.png');

await goto('/pests', '.pest-card, .pest-list, .wiki-list');
await shoot('farmer-wiki.png');

// ---------------------------------------------------------------------------
// ④ 管理端 4 张
// ---------------------------------------------------------------------------
log('管理端：');

// 「内容管理 · 帖子」：这张图要展示**合并后的页面结构**（页头 + 三个页签 + 论坛管理区块）。
// ⚠️ 审核队列区块会占满整屏、把"论坛管理"挤到下面，所以截图前把它隐藏 ——
//    这只是为了取景，不改任何行为（用内联 style 藏一个区块）。
await goto('/admin/content?tab=posts', '.admin-console', 3000);
await page.evaluate(() => {
  const queue = document.querySelector('.content-post-panel > .hub-block');
  if (queue) queue.style.display = 'none';
});
await page.waitForTimeout(600);
await shoot('admin-forum.png');

// 「内容管理 · 评论」：展示**软删除可恢复**（先把"评论范围"切到"已删除"）
await goto('/admin/content?tab=comments', '.admin-console', 3000);
await page.locator('.admin-console .el-select').first().click();
await page.waitForTimeout(600);
await page.locator('.el-select-dropdown__item', { hasText: '已删除' }).first().click();
await page.waitForTimeout(2500);
await shoot('admin-comment-restore.png');

await goto('/admin/dashboard', '.admin-console', 2500);
await shoot('admin-console-dashboard.png');

// 「系统」是第 185/186 批合并出来的页面（系统健康 + 操作日志 + 版块管理三个页签）
await goto('/admin/health?tab=health', '.admin-console', 3000);
await shoot('admin-health.png');

await goto('/admin/health?tab=audit', '.admin-console', 3000);
await shoot('admin-audit-log.png');

log(errors.length ? `⚠️ 页面报错 ${errors.length} 条：${errors.slice(0, 2).join(' | ')}` : '✅ 全程无 JS 报错');

await browser.close();

// ---------------------------------------------------------------------------
// ⑤ 清理演示内容（admin 的 token 留着不影响；帖子/评论/日志按前缀删）
// ---------------------------------------------------------------------------
clearThrottle();
runDjango([
  'from api.models_forum import Comment, ForumBoard, Post',
  'from api.models_audit import AdminAuditLog',
  "print('cleaned posts:', Post.objects.filter(title__startswith='zz演示').delete()[0])",
  "print('cleaned comments:', Comment.objects.filter(content__startswith='zz演示').delete()[0])",
  "print('cleaned boards:', ForumBoard.objects.filter(name__startswith='zze2e演示版块').delete()[0])",
  "print('cleaned audit:', AdminAuditLog.objects.filter(detail__startswith='演示：').delete()[0])",
  // ⚠️ 历次 E2E 留下的临时账号（`zze2e_fa_super_x0sa`、`zzfixc_admin_…` 这类机器名）会出现在
  //    「操作日志」截图里，很难看。它们必须在**截图之前**清掉（只放在收尾清理里没用）。
  //    按"以 zz 开头、但不是本次演示行"清 —— 各批脚本都约定用 zz 前缀造临时数据。
  "print('cleaned pre-existing test-actor audit:', AdminAuditLog.objects.filter(actor_repr__startswith='zz').exclude(detail__startswith='演示：').delete()[0])",
  // 还有一类：**操作人是 admin**（共享管理员账号）、但操作对象是测试数据的行
  // （如 `删除识别记录 #1124（zz_detE2E_user · …）`）。它们的 `detail` 里**没有** zz，
  // zz 在**目标**那一列（`target_repr`）—— 所以三个字段一起查（detail / target_repr / target_id）。
  "from django.db.models import Q",
  "print('cleaned pre-existing test-target audit:', AdminAuditLog.objects.filter(Q(detail__contains='zz') | Q(target_repr__contains='zz') | Q(target_id__contains='zz')).exclude(detail__startswith='演示：').delete()[0])",
]);
log('演示内容已清理');
log('下一步：python docs/tools/optimize_readme_images.py');
