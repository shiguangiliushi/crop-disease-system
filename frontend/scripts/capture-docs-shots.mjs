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

//: 截图前把 admin 的问答历史快照到这里，跑完**原样还原**（第 205 批加）
const SNAPSHOT_PATH = path.resolve('..', 'backend', '_assistant_history_snapshot.json');

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
  'from api.models_audit import AdminAuditLog',
  'from api.audit import log_admin_action',
  'from api.serializers import CustomUserSerializer',
  `admin = get_user_model().objects.get(username='${ADMIN}')`,
  // ⚠️ 第 202 批补：**清理必须发生在截图之前**，分两块。
  //    （脚本末尾原本也有一段清理，但它只管"本次演示数据"，管不了上一次运行留下的东西，
  //      而截图拍的是**当前库里的状态** —— 所以旧数据会被拍进去。历史上就踩过：
  //      见下面那句"它们必须在截图之前清掉（只放在收尾清理里没用）"。）
  //    ① 演示帖/评论/版块：按前缀删（标题带 zz演示 是我们自己的约定）；
  "print('cleaned stale demo posts:', Post.objects.filter(title__startswith='zz演示').delete()[0])",
  "print('cleaned stale demo comments:', Comment.objects.filter(content__startswith='zz演示').delete()[0])",
  "print('cleaned stale demo boards:', (ForumBoard.objects.filter(name__startswith='zze2e演示版块').delete()[0] + ForumBoard.objects.filter(order=999).delete()[0]))",
  //    ② 操作日志：分三类清（这段逻辑原来只在收尾，现在提前到截图前，收尾保留一份做兜底）
  //       · 操作人是以 zz 开头的临时账号（历次 E2E 留下的 `zze2e_xxx` 机器名）；
  //       · detail / target_repr / target_id 里含 zz 的（测试对象）；
  //       · **演示行的孤儿快照** —— 这一条最关键：审计日志会**快照目标标题**，
  //         所以即使帖子已被删掉，日志里仍留着 `zz演示：…（帖子）`，
  //         它会**直接出现在截图里**。按"含 zz"一起清掉。
  "from django.db.models import Q",
  "print('cleaned stale audit:', AdminAuditLog.objects.filter(",
  "    Q(actor_repr__startswith='zz') | Q(detail__contains='zz') |",
  "    Q(target_repr__contains='zz') | Q(target_id__contains='zz')",
  ").exclude(detail__startswith='演示：').delete()[0])",
  // 演示版块 + 三条帖子（都归 admin，标题带 zz演示 便于清理）
  // ⚠️ 第 189 批：版块名改成**像真的**（原来叫 `zze2e演示版块`，会显示在截图里的帖子行上，
  //    既是机器名又难看）；清理仍按 `zze2e演示版块` 前缀，所以这里保留前缀只改后半段。
  // ⚠️ 第 221 批：版块名原来带 `zze2e演示版块` 前缀，会**原样显示在帖子的版块列**上
  //    （挂在 GitHub 首屏像机器名）。改成自然名字，改用 `order=999` 作清理标记
  //    —— 现有真实版块 order 只到 3，999 不会撞。
  "board, _ = ForumBoard.objects.get_or_create(name='露地蔬菜交流', defaults={'order': 999})",
  // 上一版留下的旧名版块也清掉（第 202 批起，帖/评论/日志的清理统一提到了前面）
  "print('cleaned stale old-name boards:', ForumBoard.objects.filter(name='zze2e演示版块').delete()[0])",
  "p1 = Post.objects.create(title='叶片背面这些白点是什么？', content='<p>大棚里的黄瓜，最近叶子背面出现密集白色小点，摸上去有点黏。请问是白粉虱还是别的原因？</p>', author=admin, board=board, status='published', is_pinned=True, is_essence=True, view_count=128, like_count=12)",
  "p2 = Post.objects.create(title='连续阴雨后要不要补喷一次杀菌剂？', content='<p>连着下了四天雨，棚里湿度很高，之前打的药是不是被冲掉了？</p>', author=admin, board=board, status='published', view_count=64, like_count=5)",
  "p3 = Post.objects.create(title='玉米大斑病初期求助', content='<p>叶片上出现梭形褐色斑点，边缘有黄晕，是不是大斑病？该怎么用药？</p>', author=admin, board=board, status='published', view_count=41, like_count=3)",
  // ⚠️ 第 202 批：演示帖标题**不再带 `zz演示` 前缀** —— 因为审计日志会**快照目标标题**，
  //    前缀会原样出现在「操作日志」截图里（上一版图里就是 `zz演示：叶片背面这些白点是什么？（帖子）`）。
  //    代价是不能靠标题前缀清理了，所以**把 id 传回给 Node**，收尾按 id 精确删除。
  "print('ZZ_POSTS=' + json.dumps([p1.id, p2.id, p3.id]))",
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
  //: ⚠️ 第 221 批：原来写 `post.pin` —— 那个动作**全仓都不存在**（置顶/加精没有审计），
  //: 于是日志的"动作"列显示成原始标识符 `post.pin`，直接出现在 README 截图里。
  //: 换成真实存在、中文标签也说得通的动作。
  "log_admin_action(admin, 'comment.restore', None, '演示：恢复了一条误删的评论', target_type='comment', target_id=c.id, target_repr='一条灌水评论')",
  "log_admin_action(admin, 'comment.soft_delete', None, '演示：删除了一条不当评论', target_type='comment', target_id=c.id, target_repr='一条灌水评论')",
  "log_admin_action(admin, 'user.role_change', admin, '演示：调整了一位用户的角色')",
  // 第 202 批：给「智能问答」页种**演示问答**（挂在 admin 名下）。
  // ⚠️ 三个坑都在这里踩过，逐条记下来：
  //   ① **不种就是空态**（"还没有问答记录"），README 上看不出这个功能做了什么；
  //   ② **必须清掉 admin 的历史会话**：开发库里累积的验证问答（"What is pepper
  //      bacterial spot"、"How do I treat potato late bli…"）会直接出现在左侧历史里，
  //      中英混杂、像半成品 —— 第一版截图就是这样，逐张看图才发现；
  //   ③ **不真的调模型**：截图脚本不该产生 API 费用，也不该依赖外网是否可达。
  //      所以正文直接写库（内容取自真实回答的典型结构）。
  "from datetime import timedelta",
  "from django.utils import timezone",
  "from api.models_assistant import AssistantMessage, AssistantSession",
  "from api.models import PestInfo",
  // ⚠️⚠️ 第 205 批事故与修正：这里原来删的是 **admin 的全部问答历史**。
  //    我在别处用同样的思路清理调试数据时，**误删了用户真实用过的会话**
  //    （`admin` 与 `admin123456` 两个账号都有人用，我只当它们是演示账号）。
  //    已从备份恢复 11 条，见 `docs/系统完善记录.md` 第 205 批。
  //
  //    现在的做法：**只删"没有标题或标题为空"的兜底行**是不行的 ——
  //    演示要的是"侧栏干净"，所以改成**先备份、删、跑完再还原**：
  //    跑之前把 admin 的历史序列化到临时文件，跑完原样写回。
  //    这样配图干净、又不销毁任何真实记录。
  "import json, pathlib",
  "SNAP = pathlib.Path(r'" + SNAPSHOT_PATH.replace('\\', '\\\\') + "')",
  "def _snapshot():",
  "    rows = []",
  "    for s in AssistantSession.objects.filter(user=admin).order_by('id'):",
  "        rows.append({",
  "            'title': s.title, 'pest_id': s.pest_id, 'detection_id': s.detection_id,",
  "            'created_at': s.created_at.isoformat(), 'updated_at': s.updated_at.isoformat(),",
  "            'escalated_at': s.escalated_at.isoformat() if s.escalated_at else None,",
  "            'messages': [",
  "                {'role': m.role, 'content': m.content, 'model': m.model,",
  "                 'degraded': m.degraded, 'degrade_reason': m.degrade_reason,",
  "                 'latency_ms': m.latency_ms, 'citations': m.citations, 'usage': m.usage,",
  "                 'prompt_version': m.prompt_version, 'lang': m.lang,",
  "                 'truncated': m.truncated, 'created_at': m.created_at.isoformat()}",
  "                for m in AssistantMessage.objects.filter(session=s).order_by('id')]})",
  "    SNAP.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')",
  "    return len(rows)",
  "print('被替换的演示问答数:', AssistantSession.objects.filter(user=admin).count())",
  "print('已快照真实历史:', _snapshot(), '条 →', SNAP)",
  "print('cleared admin assistant history:', AssistantSession.objects.filter(user=admin).delete()[0])",
  // ⚠️ 演示问题的长度是**照着侧栏能显示下的量**定的：第一版写
  //    "苹果黑星病打什么药？稀释倍数和安全间隔期是多少？"（23 字），侧栏显示成
  //    "…稀释倍…"（尾部被省略号吃掉）—— 截断本身是列表的正常行为，
  //    但配图里看着像半句话，所以把标题收到 10 字左右。
  "DEMO = [",
  "    ('苹果黑星病打什么药？', 'apple_scab',",
  "     '苹果黑星病的关键施药窗口是花芽露红期到落花后。可选药剂：10%苯醚甲环唑水分散粒剂1500～2000倍液、430 g/L戊唑醇悬浮剂3000～4000倍液、70%代森锰锌可湿性粉剂600～800倍液；每7～10天1次，连喷2～4次，三唑类与甲氧基丙烯酸酯类轮换使用。苹果上苯醚甲环唑等三唑类安全间隔期一般为14～21天，每季最多使用4次。具体用药请以当地植保站当期防治方案为准。',",
  "     '化学防治：以花蕾露红期和落花后为关键节点…'),",
  "    ('马铃薯晚疫病为什么不能用甲霜灵了？', 'potato_late_blight',",
  "     '因为抗药性已经很严重：2024 年全国监测显示马铃薯晚疫病菌对甲霜灵的抗性达到中高水平，高抗菌株频率超过 80%，各主产区应停用甲霜灵及其混剂。可改用烯酰吗啉、氟菌·霜霉威、霜脲氰、氟噻唑吡乙酮、三乙膦酸铝等不同作用机理的药剂，并注意轮换。具体用药请以当地植保站当期防治方案为准。',",
  "     '化学防治：发病前或初见中心病株时立即喷药…'),",
  "    ('番茄细菌性斑点病和斑疹病怎么区分？', 'tomato_bacterial_spot',",
  "     '两者是不同病原引起的两种病。细菌性斑点病由黄单胞杆菌（Xanthomonas euvesicatoria）引起，病斑较大（1-4mm）、木栓化隆起呈疮痂状，茎上纵裂，果实上为黑色疮痂状病斑且边缘开裂；细菌性斑疹病由 Pseudomonas syringae pv. tomato 引起，病斑极小（1-3mm）、不隆起，果实上只是微小黑点、不粗糙开裂。具体用药请以当地植保站当期防治方案为准。',",
  "     '症状描述：叶片初现水渍状黄绿色小圆点…'),",
  "    ('草莓健康栽培要注意什么？', 'strawberry_healthy',",
  "     '重点在土壤与水分管理：选用脱毒壮苗、高垄栽培配滴灌，避免大水漫灌；生长期及时摘除老叶病叶、疏花疏果控制负载；施肥以有机肥为主、配施磷钾与钙镁硼，避免偏施氮肥；花果期严格遵守农药安全间隔期。具体管理请结合当地栽培习惯与植保站指导。',",
  "     '健康生长条件：喜冷凉湿润…'),",
  "]",
  "for idx, (q, ident, ans, snippet) in enumerate(DEMO):",
  "    pest = PestInfo.objects.filter(english_identifier=ident).first()",
  "    sess = AssistantSession.objects.create(user=admin, title=q, pest=pest)",
  "    AssistantMessage.objects.create(session=sess, role='user', content=q)",
  "    AssistantMessage.objects.create(session=sess, role='assistant', content=ans,",
  "                                    citations=[{'pest_id': pest.id if pest else None,",
  "                                                'label': pest.name if pest else '',",
  "                                                'snippet': snippet}])",
  "    # updated_at 是 auto_now，只能建完再 update —— 让四条历史有先后，看起来像真的用过",
  "    AssistantSession.objects.filter(pk=sess.pk).update(",
  "        updated_at=timezone.now() - timedelta(hours=idx * 5 + 1))",
  "print('ZZ_SESSIONS=' + str(AssistantSession.objects.filter(user=admin).count()))",
  // 给 admin 签发 token + 登录接口同款的 user 数据
  'token, _ = Token.objects.get_or_create(user=admin)',
  "print('ZZ_TOKEN=' + token.key)",
  "print('ZZ_USER=' + json.dumps(CustomUserSerializer(admin).data, ensure_ascii=False))",
  "print('ZZ_PID=' + str(p1.id))",
]);
const token = /ZZ_TOKEN=(\S+)/.exec(seedOutput)?.[1];
const userJson = /ZZ_USER=(.+)/.exec(seedOutput)?.[1];
//: 本次演示帖的 id —— 收尾按 id 精确清理（标题已改成"像真的"，不能再靠前缀）
const demoPostIds = JSON.parse(/ZZ_POSTS=(\[[^\]]*\])/.exec(seedOutput)?.[1] || '[]');
if (!token || !userJson) {
  console.error('❌ 没能从 Django 拿到 admin 的 token/user：', seedOutput);
  process.exit(1);
}
if (!demoPostIds.length) {
  console.error('❌ 没拿到演示帖 id（ZZ_POSTS），收尾会清不干净：', seedOutput);
  process.exit(1);
}
log(`演示帖 id: ${demoPostIds.join(', ')}`);
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

// 第 202 批新增：**智能问答页**（第 198 批做的独立问答页）。
// ⚠️ 演示会话必须**先种好**（见上面的 seed 段），否则截出来是空态。
//    种的时候走的是"直接写库"，所以这张图**不产生任何模型调用费用**，
//    也不受外网可用性影响 —— 截图脚本不该有这种外部依赖。
await goto('/assistant', '.assistant-page', 2500);
// 点左侧第一条历史，让中间显示完整问答（新会话默认是空的欢迎态）
const firstSession = page.locator('.assistant-side-item').first();
if (await firstSession.count()) {
  await firstSession.click();
  await page.waitForTimeout(1500);
}
await shoot('farmer-assistant.png');

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
// ⑤ 清理演示内容（admin 的 token 留着不影响）
//
// ⚠️ 第 202 批：演示帖按 **id** 清，不再按标题前缀 —— 因为演示帖标题已经改成
//    "像真的"（不带 `zz演示`），前缀清理会失效。id 从 seed 段的 `ZZ_POSTS` 拿。
//    另外**清理的主体已经在 seed 段之前跑过一次**（截图拍的是当前库状态，
//    上一次运行留下的东西必须在那之前清掉），这里只是收尾兜底。
// ---------------------------------------------------------------------------
clearThrottle();
runDjango([
  'import json',
  'from api.models_forum import Comment, ForumBoard, Post',
  'from api.models_audit import AdminAuditLog',
  `demo_ids = ${JSON.stringify(demoPostIds)}`,
  "print('cleaned demo posts:', Post.objects.filter(id__in=demo_ids).delete()[0])",
  // 兜底：万一有更早版本留下的、带前缀的演示帖
  "print('cleaned legacy prefixed posts:', Post.objects.filter(title__startswith='zz演示').delete()[0])",
  "print('cleaned comments:', Comment.objects.filter(content__startswith='zz演示').delete()[0])",
  "print('cleaned boards:', (ForumBoard.objects.filter(name__startswith='zze2e演示版块').delete()[0] + ForumBoard.objects.filter(order=999).delete()[0]))",
  // ⚠️ 操作日志会**快照目标标题**，所以删掉演示帖后日志里仍留着那些标题 ——
  //    必须同时清掉日志行（按演示帖 id 定位 target_id）。
  `print('cleaned demo audit:', AdminAuditLog.objects.filter(target_id__in=[str(i) for i in demo_ids]).delete()[0])`,
  "from api.models_assistant import AssistantSession",
  // ⚠️ 收尾把演示问答清掉；**随后在下一步从快照还原真实历史**（第 205 批）。
  //    原来这里的注释写的是"按 admin 的全部问答历史清，代价是会把 admin 自己问过的记录一并删掉"
  //    —— 那个"代价"后来真的造成了事故：我用同样的思路清理调试数据时，
  //    **误删了用户真实用过的 11 条会话**（`admin` 与 `admin123456` 两个账号都有人用）。
  //    现在的约定：**任何"清空某人的历史"都必须先快照、跑完还原**，不做不可逆删除。
  "print('cleaned demo assistant sessions:', AssistantSession.objects.filter(user__username='admin').delete()[0])",
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

// ---------------------------------------------------------------------------
// ⑥ 从快照**还原** admin 的真实问答历史（第 205 批）
//
// 这一步是上面"清空 admin 历史"的配套：快照在 seed 段开头写过一份，
// 现在原样写回。**没有这一步，这个脚本就是不可逆地销毁数据**。
// ---------------------------------------------------------------------------
runDjango([
  'import json, pathlib',
  'from datetime import datetime, timezone as dt_timezone',
  'from django.contrib.auth import get_user_model',
  'from api.models_assistant import AssistantMessage, AssistantSession',
  "admin = get_user_model().objects.get(username='admin')",
  `SNAP = pathlib.Path(r'${SNAPSHOT_PATH.replace(/\\/g, '\\\\')}')`,
  'if not SNAP.is_file():',
  "    print('没有快照文件，跳过还原')",
  'else:',
  '    rows = json.loads(SNAP.read_text(encoding="utf-8"))',
  '    def aware(v):',
  '        if not v:',
  '            return None',
  '        dt = datetime.fromisoformat(v)',
  '        return dt if dt.tzinfo else dt.replace(tzinfo=dt_timezone.utc)',
  '    restored = 0',
  '    for row in rows:',
  '        s = AssistantSession.objects.create(',
  "            user=admin, title=row['title'], pest_id=row['pest_id'],",
  "            detection_id=row['detection_id'], escalated_at=aware(row['escalated_at']))",
  '        AssistantSession.objects.filter(pk=s.pk).update(',
  "            created_at=aware(row['created_at']), updated_at=aware(row['updated_at']))",
  "        for m in row['messages']:",
  '            msg = AssistantMessage.objects.create(',
  "                session=s, role=m['role'], content=m['content'], model=m['model'],",
  "                degraded=m['degraded'], degrade_reason=m['degrade_reason'],",
  "                latency_ms=m['latency_ms'], citations=m['citations'], usage=m['usage'],",
  "                prompt_version=m['prompt_version'], lang=m['lang'], truncated=m['truncated'])",
  '            AssistantMessage.objects.filter(pk=msg.pk).update(created_at=aware(m["created_at"]))',
  '        restored += 1',
  "    print('restored assistant history:', restored, '条')",
  '    SNAP.unlink(missing_ok=True)',
]);
log('admin 问答历史已还原（快照文件已删除）');
log('下一步：python docs/tools/optimize_readme_images.py');
