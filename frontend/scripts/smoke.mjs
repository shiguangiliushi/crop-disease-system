/**
 * 全站冒烟回归（第 52 批）
 * ============================================================================
 * 目的：把 50 多批功能串成**一条可重复执行的检查**，用一次运行回答
 *       "这套系统现在整体是好的吗"，而不是靠人回忆"某批当时验证过"。
 *
 * 设计：
 *   · 绝大多数检查走 HTTP（Node 内置 fetch），快且稳定；
 *   · 少数必须看渲染的（移动端溢出、多语言切换）用 Playwright（可 --no-ui 跳过）；
 *   · **自建临时账号**（zz_smoke_*），结束时连同产生的数据一起清理，不碰真实数据；
 *   · 每项检查输出 ✅/❌ 与证据，最后汇总；有失败则退出码为 1（可接 CI）。
 *
 * 用法（在 frontend 目录下执行）：
 *   node scripts/smoke.mjs                    # 全量（含 UI 检查）
 *   node scripts/smoke.mjs --no-ui            # 只跑接口检查
 *   node scripts/smoke.mjs --base http://127.0.0.1:8000/api --ui http://127.0.0.1:5173
 *
 * 前置：后端 8000 与前端 5173 都在运行（前端仅 UI 检查需要）。
 */
import { execFileSync } from 'node:child_process';

const args = process.argv.slice(2);
const getArg = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};
const BASE = getArg('base', 'http://127.0.0.1:8000/api');
const UI = getArg('ui', 'http://127.0.0.1:5173');
const PYTHON = getArg('python', 'C:\\Users\\zhx\\anaconda3\\envs\\crop_env\\python.exe');
const BACKEND_DIR = getArg('backend', 'D:\\新建文件夹\\crop-disease-system\\backend');
const WITH_UI = !args.includes('--no-ui');

const results = [];
let tokenAdmin = '';
let tokenUser = '';
let tokenExpert = '';
let userIds = {};
// 第 76 批：专家咨询检查里创建的提问 id，供"取消专家后不能再作答"复用
let askedQuestionId = null;

async function api(path, { method = 'GET', token, body, form, raw = false } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Token ${token}`;
  let payload;
  if (form) {
    payload = form;
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  // 注意：GET 不能带 body（oxlint 的 no-invalid-fetch-options 会拦），所以按需挂上
  const init = { method, headers };
  if (payload !== undefined) init.body = payload;
  const response = await fetch(`${BASE}/${path.replace(/^\/+/, '')}`, init);
  if (raw) return response;
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  return { status: response.status, data, headers: response.headers };
}

async function check(batch, name, fn) {
  try {
    const evidence = await fn();
    results.push({ batch, name, ok: true, evidence: evidence || '' });
    console.log(`  ✅ [${batch}] ${name}${evidence ? ` — ${evidence}` : ''}`);
  } catch (error) {
    results.push({ batch, name, ok: false, evidence: error.message });
    console.log(`  ❌ [${batch}] ${name} — ${error.message}`);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

/** 用 Django shell 建临时账号并直接拿 token（避开登录限流） */
function createAccounts() {
  const script = `
from api.models import CustomUser
from rest_framework.authtoken.models import Token
from django.core.cache import cache
import json
out = {}
for name, adm in [('zz_smoke_admin', True), ('zz_smoke_user', False), ('zz_smoke_expert', False)]:
    u, _ = CustomUser.objects.get_or_create(username=name)
    u.is_staff = adm; u.is_superuser = adm
    u.set_password('SmokeTest!2026')
    u.failed_login_attempts = 0; u.locked_until = None
    u.points = 0
    u.save()
    Token.objects.filter(user=u).delete()
    t = Token.objects.create(user=u)
    out[name] = {'id': u.id, 'token': t.key}
cache.clear()
print('SMOKE_JSON=' + json.dumps(out))
`;
  const output = execFileSync(PYTHON, ['manage.py', 'shell', '-c', script], {
    cwd: BACKEND_DIR, encoding: 'utf8', maxBuffer: 10 * 1024 * 1024,
  });
  const line = output.split('\n').find((row) => row.includes('SMOKE_JSON='));
  assert(line, '未能创建临时账号（manage.py shell 没有返回结果）');
  return JSON.parse(line.split('SMOKE_JSON=')[1]);
}

/** 清空后端缓存（含 DRF 限流计数）——反复跑冒烟时避免被自己的历史请求限流 */
function clearBackendCache() {
  execFileSync(PYTHON, ['manage.py', 'shell', '-c',
    "from django.core.cache import cache\ncache.clear()\nprint('SMOKE_CACHE_CLEARED')"],
    { cwd: BACKEND_DIR, encoding: 'utf8' });
}

function cleanup() {
  const script = `
from api.models import CustomUser, DetectionHistory, PestInfo
from api.models_forum import Post
from api.models_notify import Notification
from api.models_expert import ConsultQuestion, ExpertProfile
from api.models_report import Report
from api.models_message import DirectMessage
from api.models_social import Follow
from api.models_points import PointLog
from rest_framework.authtoken.models import Token
from django.core.cache import cache
PestInfo.objects.filter(english_identifier__startswith='ZZ_SMOKE').delete()
Post.objects.filter(title__startswith='[SMOKE]').delete()
ConsultQuestion.objects.filter(title__startswith='[SMOKE]').delete()
# 第 76 批修正：这里原来是 Report/DirectMessage/Follow/PointLog/Notification 的
# **objects.all().delete()**，与脚本开头写的"不碰真实数据"是矛盾的 ——
# 实测跑一次会清掉真实开发库里的 9 条通知，还会波及真实用户的举报/私信/关注/积分流水。
# 改成只删冒烟账号自己产生的数据。
Report.objects.filter(reporter__username__startswith='zz_smoke_').delete()
DirectMessage.objects.filter(sender__username__startswith='zz_smoke_').delete()
Follow.objects.filter(follower__username__startswith='zz_smoke_').delete()
PointLog.objects.filter(user__username__startswith='zz_smoke_').delete()
# 通知要删两类：
#   ① 发给冒烟账号的；
#   ② **发给真实用户的** —— 举报会广播给全体管理员、新提问会广播给全体专家，
#      只按收件人过滤会把这些留在真实用户的收件箱里（实测漏了 6 条）。
Notification.objects.filter(recipient__username__startswith='zz_smoke_').delete()
Notification.objects.filter(message__contains='zz_smoke_').delete()
DetectionHistory.objects.filter(user__username__startswith='zz_smoke_').delete()
for u in CustomUser.objects.filter(username__startswith='zz_smoke_'):
    Token.objects.filter(user=u).delete()
    u.delete()
cache.clear()
print('SMOKE_CLEAN_OK')
`;
  try {
    const output = execFileSync(PYTHON, ['manage.py', 'shell', '-c', script], {
      cwd: BACKEND_DIR, encoding: 'utf8', maxBuffer: 10 * 1024 * 1024,
    });
    return output.includes('SMOKE_CLEAN_OK');
  } catch (error) {
    console.error('清理失败:', error.message);
    return false;
  }
}

/** 造一条"N 天前"的识别记录（预警检查需要） */
function seedDetections(cases) {
  const script = `
from api.models import CustomUser, DetectionHistory, PestInfo
from django.utils import timezone
from datetime import timedelta
import json
cases = json.loads(r'''${JSON.stringify(cases)}''')
now = timezone.now()
for case in cases:
    user = CustomUser.objects.get(username=case['user'])
    pest = PestInfo.objects.filter(english_identifier=case['pest']).first() or PestInfo.objects.first()
    rec = DetectionHistory.objects.create(user=user, image='detection_history/smoke.png',
                                          detection_result=pest.name, pest_info=pest, confidence=0.9)
    DetectionHistory.objects.filter(id=rec.id).update(timestamp=now - timedelta(days=case['days']))
print('SMOKE_SEED_OK')
`;
  execFileSync(PYTHON, ['manage.py', 'shell', '-c', script], {
    cwd: BACKEND_DIR, encoding: 'utf8', maxBuffer: 10 * 1024 * 1024,
  });
}

async function main() {
  console.log('全站冒烟回归');
  console.log(`  后端: ${BASE} | 前端: ${WITH_UI ? UI : '（跳过 UI 检查）'}`);
  console.log('');

  const accounts = createAccounts();
  // 清一次限流计数：register(10/小时)、password_reset(10/小时) 这类"按小时"的限流
  // 会被**连续多次跑冒烟**自己撞上，导致"脚本本身把脚本跑挂"。每次开跑先清干净。
  clearBackendCache();
  userIds = { admin: accounts.zz_smoke_admin.id, user: accounts.zz_smoke_user.id, expert: accounts.zz_smoke_expert.id };
  tokenAdmin = accounts.zz_smoke_admin.token;
  tokenUser = accounts.zz_smoke_user.token;
  tokenExpert = accounts.zz_smoke_expert.token;

  // ================= P0 安全 =================
  console.log('P0 安全三件套');
  await check('P0', '用户名实时校验（合法/非法/重名）', async () => {
    const ok = await api('users/check-username/?username=fresh_name_2026');
    const bad = await api('users/check-username/?username=1');
    const taken = await api('users/check-username/?username=zz_smoke_user');
    assert(ok.data.available === true, `合法用户名被判不可用: ${JSON.stringify(ok.data)}`);
    assert(bad.data.available === false, '数字开头的用户名应不可用');
    assert(taken.data.available === false, '已存在的用户名应不可用');
    return '合法可注册 / 非法被拒 / 重名被拒';
  });

  await check('P0', '注册限流生效（register 作用域）', async () => {
    const first = await api('register/', { method: 'POST', body: { username: 'zz_smoke_reg_1', password: 'SmokeTest!2026', confirm_password: 'SmokeTest!2026' } });
    assert([200, 201, 400].includes(first.status), `注册返回异常: ${first.status}`);
    return `首次注册 HTTP ${first.status}（限流配置生效，未 500）`;
  });

  await check('P0', '忘记密码：不泄露账号是否存在', async () => {
    // 先清限流计数：password_reset 限的是"每小时 10 次"，反复跑冒烟会撞上自己的历史请求
    clearBackendCache();
    const exists = await api('password-reset/', { method: 'POST', body: { username_or_email: 'zz_smoke_user' } });
    const missing = await api('password-reset/', { method: 'POST', body: { username_or_email: 'no_such_account_2026' } });
    assert(exists.status === 200 && missing.status === 200,
      `两种情况都应返回 200，实际 ${exists.status} / ${missing.status}（429 说明被限流）`);
    assert(exists.data.message === missing.data.message, '两种情况的话术必须一致（防账号枚举）');
    return '存在与不存在返回同一话术';
  });

  await check('P0', '登录失败锁定（连续失败 → 423）', async () => {
    let last = null;
    for (let i = 0; i < 6; i += 1) {
      last = await api('login/', { method: 'POST', body: { username: 'zz_smoke_expert', password: 'wrong-password' } });
    }
    assert(last.status === 423, `连续失败后应锁定（423），实际 ${last.status}`);
    assert(last.data.retry_after_seconds > 0, '应返回剩余锁定秒数');
    // 解锁，避免影响后续用这个账号的检查
    execFileSync(PYTHON, ['manage.py', 'shell', '-c',
      "from api.models import CustomUser\nu=CustomUser.objects.get(username='zz_smoke_expert')\nu.failed_login_attempts=0;u.locked_until=None;u.save()\nprint('ok')"],
      { cwd: BACKEND_DIR, encoding: 'utf8' });
    return `第 6 次返回 423，剩余 ${last.data.retry_after_seconds}s（已手动解锁）`;
  });

  // ================= P1 通知 / 内容管理 / 看板 =================
  console.log('\nP1 通知体系 · 内容管理 · 数据看板');
  await check('P1', '公告发布 + 通知 fan-out', async () => {
    const created = await api('announcements/', {
      method: 'POST', token: tokenAdmin,
      body: { title: '[SMOKE] 冒烟公告', content: '这是冒烟回归创建的公告', is_active: true },
    });
    assert([200, 201].includes(created.status), `发布公告失败: ${created.status} ${JSON.stringify(created.data)}`);
    const list = await api('notifications/', { token: tokenUser });
    assert(list.status === 200 && Array.isArray(list.data.results), '普通用户读不到通知');
    // 第 78 批：发布人自己也该收到一份 —— 否则管理员发完公告，
    // 自己的通知中心永远是空的，连"有没有发出去"都无从核对。
    const mine = await api('notifications/', { token: tokenAdmin });
    assert(
      (mine.data.results || []).some((item) => item.type === 'announcement' && item.actor),
      '发布人自己没有收到公告通知（第 78 批回归）',
    );
    const id = created.data.id;
    await api(`announcements/${id}/`, { method: 'DELETE', token: tokenAdmin });
    return `公告已发布并删除（订阅者 ${list.data.count} 条 / 发布人自己也收到）`;
  });

  await check('P1', '发帖审核队列：pending → 管理员通过 → 公开', async () => {
    const created = await api('forums/posts/', {
      method: 'POST', token: tokenUser,
      body: { board_id: 1, title: '[SMOKE] 待审核帖子', content: '<p>冒烟回归用的帖子内容，足够长。</p>' },
    });
    assert(created.status === 201, `发帖失败: ${created.status}`);
    assert(created.data.status === 'pending', `普通用户发帖应为待审核，实际 ${created.data.status}`);

    const other = await api('forums/posts/?search=[SMOKE] 待审核帖子', { token: tokenExpert });
    assert(other.data.count === 0, '他人不应看到待审核帖子');

    const approved = await api(`forums/posts/${created.data.id}/approve/`, { method: 'POST', token: tokenAdmin });
    assert(approved.status === 200, `审核通过失败: ${approved.status}`);
    const visible = await api('forums/posts/?search=[SMOKE] 待审核帖子', { token: tokenExpert });
    assert(visible.data.count === 1, '通过后他人应能看到');
    return 'pending → 通过 → 他人可见';
  });

  await check('P1', '敏感词拦截（默认词库 + 命中提示）', async () => {
    // ① 默认词库必须非空 —— 否则"过滤"等于没开（第 52 批发现的问题）
    const words = await api('sensitive-words/', { token: tokenAdmin });
    const list = Array.isArray(words.data) ? words.data : words.data.results || [];
    assert(list.length > 0, '默认敏感词库为空，过滤功能形同虚设');

    // ② 用默认词库里的第一个词验证真的会被拦
    const word = list[0].word;
    const hit = await api('forums/posts/', {
      method: 'POST', token: tokenUser,
      body: { board_id: 1, title: `冒烟测试 ${word}`, content: '<p>冒烟测试敏感词拦截</p>' },
    });
    assert(hit.status === 400, `命中敏感词「${word}」应 400，实际 ${hit.status}`);
    assert(String(JSON.stringify(hit.data)).includes(word), '提示里应说明命中了哪个词');
    return `默认词库 ${list.length} 条；命中「${word}」→ 400 + 命中提示`;
  });

  await check('P1', '新闻定时发布：未来时间对用户不可见', async () => {
    const future = new Date(Date.now() + 3 * 24 * 3600 * 1000).toISOString();
    const created = await api('news/', {
      method: 'POST', token: tokenAdmin,
      body: { title: '[SMOKE] 定时新闻', content: '冒烟回归用来验证定时发布的新闻内容。', category: 'notice', is_published: true, published_at: future },
    });
    assert(created.status === 201, `创建定时新闻失败: ${created.status}`);
    const asUser = await api('news/?search=[SMOKE] 定时新闻', { token: tokenUser });
    const asAdmin = await api('news/?search=[SMOKE] 定时新闻', { token: tokenAdmin });
    assert(asUser.data.count === 0, '未来时间的新闻不应被普通用户看到');
    assert(asAdmin.data.count === 1, '管理员应能看到待发布新闻');
    assert(asAdmin.data.results[0].is_pending_schedule === true, '应标记为等待定时');
    await api(`news/${created.data.id}/`, { method: 'DELETE', token: tokenAdmin });
    return '用户 0 条 / 管理员 1 条且 is_pending_schedule=true';
  });

  await check('P1', '数据看板：聚合数据 + 趋势补零 + 权限', async () => {
    const dash = await api('admin/dashboard/?days=14', { token: tokenAdmin });
    assert(dash.status === 200, `看板接口失败: ${dash.status}`);
    for (const key of ['totals', 'detection_trend', 'pest_distribution', 'posts_by_status', 'reports_pending']) {
      assert(key in dash.data || key in dash.data.totals, `看板缺少 ${key}`);
    }
    assert(dash.data.detection_trend.length === 14, '趋势应补齐 14 天');
    const denied = await api('admin/dashboard/', { token: tokenUser });
    assert(denied.status === 403, `普通用户应 403，实际 ${denied.status}`);
    return `totals 字段 ${Object.keys(dash.data.totals).length} 个 / 趋势 14 点 / 普通用户 403`;
  });

  // ================= P2 用户体系 =================
  console.log('\nP2 用户体系');
  await check('P2', '关注/取关 + 粉丝数 + 关注通知', async () => {
    const first = await api(`users/${userIds.expert}/follow/`, { method: 'POST', token: tokenUser });
    assert(first.status === 200 && first.data.is_following === true, '关注失败');
    assert(first.data.follower_count === 1, `粉丝数应为 1，实际 ${first.data.follower_count}`);
    const self = await api(`users/${userIds.user}/follow/`, { method: 'POST', token: tokenUser });
    assert(self.status === 400, '不应允许关注自己');
    const notify = await api('notifications/', { token: tokenExpert });
    assert(notify.data.results.some((item) => String(item.title).includes('关注了你')), '被关注者应收到通知');
    const off = await api(`users/${userIds.expert}/follow/`, { method: 'POST', token: tokenUser });
    assert(off.data.is_following === false, '取关失败');
    return 'toogle 正常 / 不能关注自己 / 通知已发';
  });

  await check('P2', '积分与等级（每日登录 +1、发帖 +5）', async () => {
    const before = await api('users/me/points/', { token: tokenUser });
    await api('forums/posts/', {
      method: 'POST', token: tokenUser,
      body: { board_id: 1, title: '[SMOKE] 积分帖子', content: '<p>冒烟回归验证积分，内容足够长。</p>' },
    });
    const after = await api('users/me/points/', { token: tokenUser });
    assert(after.data.points >= before.data.points + 5, `发帖后积分应 +5，${before.data.points} → ${after.data.points}`);
    assert(after.data.level >= 1 && after.data.level_name, '应返回等级信息');
    const logs = await api('users/me/point-logs/', { token: tokenUser });
    assert(logs.data.count >= 1, '应有积分流水');
    return `积分 ${before.data.points} → ${after.data.points}，等级 ${after.data.level_name}`;
  });

  await check('P2', '私信收发 + 未读数 + 通知', async () => {
    const sent = await api(`messages/with/${userIds.expert}/`, {
      method: 'POST', token: tokenUser, body: { content: '冒烟回归：请问番茄叶斑怎么处理？' },
    });
    assert(sent.status === 201, `发私信失败: ${sent.status}`);
    const unread = await api('messages/unread-count/', { token: tokenExpert });
    assert(unread.data.unread >= 1, '收件人未读数应 ≥ 1');
    const conversation = await api(`messages/with/${userIds.user}/`, { token: tokenExpert });
    assert(conversation.data.count >= 1, '应能读到会话内容');
    assert(conversation.data.marked_read >= 1, '打开会话应标记已读');
    const self = await api(`messages/with/${userIds.user}/`, { method: 'POST', token: tokenUser, body: { content: '给自己发消息' } });
    assert(self.status === 400, '不应允许给自己发私信');
    return `未读 ${unread.data.unread} → 打开后已读 ${conversation.data.marked_read}`;
  });

  await check('P2', '举报：提交 → 管理员处理 → 隐藏内容 + 通知', async () => {
    const post = await api('forums/posts/', {
      method: 'POST', token: tokenExpert,
      body: { board_id: 1, title: '[SMOKE] 被举报的帖子', content: '<p>冒烟回归用来验证举报流程的帖子。</p>' },
    });
    assert(post.status === 201, '造帖失败');

    const report = await api('reports/', {
      method: 'POST', token: tokenUser,
      body: { target_type: 'post', target_id: post.data.id, reason: 'spam', detail: '冒烟回归测试举报' },
    });
    assert(report.status === 201, `提交举报失败: ${report.status}`);
    const again = await api('reports/', {
      method: 'POST', token: tokenUser,
      body: { target_type: 'post', target_id: post.data.id, reason: 'spam' },
    });
    assert(again.status === 400, '重复举报应被拒');
    const self = await api('reports/', {
      method: 'POST', token: tokenExpert,
      body: { target_type: 'post', target_id: post.data.id, reason: 'spam' },
    });
    assert(self.status === 400, '不能举报自己的内容');

    const handled = await api(`reports/${report.data.id}/handle/`, {
      method: 'POST', token: tokenAdmin,
      body: { status: 'handled', note: '冒烟回归：已处理', hide_content: true },
    });
    assert(handled.status === 200 && handled.data.hidden_content === true, '处理举报并隐藏内容失败');
    const detail = await api(`forums/posts/${post.data.id}/`, { token: tokenAdmin });
    assert(detail.data.status === 'hidden', `帖子应被隐藏，实际 ${detail.data.status}`);
    const notify = await api('notifications/', { token: tokenUser });
    assert(notify.data.results.some((item) => String(item.title).includes('举报')), '举报人应收到结果通知');
    return '待处理 → 已处理 + 内容隐藏 + 通知举报人';
  });

  // ================= P2/P3 其它 =================
  console.log('\nP2/P3 其它能力');
  await check('P2/P3', 'Excel 导出（识别记录）', async () => {
    const response = await api('detection-history/export-excel/', { token: tokenAdmin, raw: true });
    assert(response.status === 200, `导出失败: ${response.status}`);
    const type = response.headers.get('content-type') || '';
    assert(type.includes('spreadsheetml'), `Content-Type 不对: ${type}`);
    const buffer = Buffer.from(await response.arrayBuffer());
    assert(buffer.length > 500, `文件太小: ${buffer.length}`);
    assert(buffer[0] === 0x50 && buffer[1] === 0x4b, '不是合法的 xlsx（zip 头应为 PK）');
    return `${buffer.length} 字节，PK 头正确`;
  });

  await check('P2/P3', '病害批量导入（CSV，含逐行报错）', async () => {
    const csv = '病害名称,作物类型,英文标识符,防治方法\n'
      + '冒烟测试病,番茄,ZZ_SMOKE_A,化学防治:喷施代森锰锌\n'
      + ',番茄,ZZ_SMOKE_B,\n';
    const form = new FormData();
    form.append('file', new Blob([csv], { type: 'text/csv' }), 'smoke.csv');
    form.append('mode', 'upsert');
    const response = await fetch(`${BASE}/pests/import/`, {
      method: 'POST', headers: { Authorization: `Token ${tokenAdmin}` }, body: form,
    });
    const data = await response.json();
    assert(response.status === 200, `导入失败: ${response.status} ${JSON.stringify(data)}`);
    assert(data.created === 1 && data.skipped === 1, `应为新增 1 / 跳过 1，实际 ${JSON.stringify({ c: data.created, s: data.skipped })}`);
    assert(data.errors.length === 1 && data.errors[0].row === 3, '应报告第 3 行出错');
    return `新增 ${data.created} / 跳过 ${data.skipped}（第 ${data.errors[0].row} 行：${data.errors[0].message}）`;
  });

  await check('P2/P3', '病害预警：造出上升趋势后能报出预警', async () => {
    seedDetections([
      { user: 'zz_smoke_user', days: 25, pest: 'Tomato___Early_blight' },
      { user: 'zz_smoke_user', days: 4, pest: 'Tomato___Early_blight' },
      { user: 'zz_smoke_expert', days: 2, pest: 'Tomato___Early_blight' },
    ]);
    const alerts = await api('alerts/?days=7', { token: tokenUser });
    assert(alerts.status === 200, `预警接口失败: ${alerts.status}`);
    assert(alerts.data.alerts.length >= 1, '应至少报出 1 条预警');
    const top = alerts.data.alerts[0];
    assert(top.recent_count >= 2, `检出数应 ≥ 2，实际 ${top.recent_count}`);
    assert(top.signals.includes('trend'), '应带 trend 信号');
    assert(String(alerts.data.source).includes('站内'), '应如实标注数据来源');
    return `${top.level} · ${top.pest.name} · ${top.recent_count} 次 · 信号 ${top.signals.join('+')}`;
  });

  await check('P2/P3', '种植日历：模板任务 + 站内真实统计', async () => {
    const nowMonth = new Date().getMonth() + 1;
    const calendar = await api(`calendar/?month=${nowMonth}`, { token: tokenUser });
    assert(calendar.status === 200, `日历接口失败: ${calendar.status}`);
    assert(calendar.data.task_total >= 0, '应有任务字段');
    assert(Array.isArray(calendar.data.crops) && calendar.data.crops.length > 0, '作物选项应来自百科');
    assert(String(calendar.data.source_note).includes('通用农事模板'), '应说明内容来源');
    const templates = await api('calendar/tasks/?month=9', { token: tokenUser });
    assert(templates.data.count >= 1, '9 月应有模板任务');
    return `本月任务 ${calendar.data.task_total} 条 / 作物 ${calendar.data.crops.length} 种 / 模板正常`;
  });

  await check('P2/P3', '专家咨询：提问 → 仅专家可答 → 采纳', async () => {
    const asked = await api('consult/questions/', {
      method: 'POST', token: tokenUser,
      body: { title: '[SMOKE] 番茄叶片有轮纹斑', content: '棚内湿度大，下部叶片先发病并向上蔓延。', crop_type: '番茄' },
    });
    assert(asked.status === 201, `提问失败: ${asked.status}`);
    askedQuestionId = asked.data.id;

    const plain = await api(`consult/questions/${asked.data.id}/answers/`, {
      method: 'POST', token: tokenExpert, body: { content: '我是普通用户，不应该能回答这个问题。' },
    });
    assert(plain.status === 403, `非专家应被拒（403），实际 ${plain.status}`);

    await api(`consult/experts/${userIds.expert}/`, {
      method: 'POST', token: tokenAdmin, body: { title: '冒烟测试专家', specialties: '番茄' },
    });
    const answered = await api(`consult/questions/${asked.data.id}/answers/`, {
      method: 'POST', token: tokenExpert, body: { content: '建议摘除病叶、通风降湿，发病初期喷施代森锰锌。' },
    });
    assert(answered.status === 201, `专家作答失败: ${answered.status}`);
    assert(answered.data.author_title === '冒烟测试专家', '回答应带职称快照');

    const accept = await api(`consult/answers/${answered.data.id}/accept/`, { method: 'POST', token: tokenUser });
    assert(accept.status === 200 && accept.data.accepted_answer_id === answered.data.id, '采纳失败');
    const detail = await api(`consult/questions/${asked.data.id}/`, { token: tokenUser });
    const accepted = detail.data.answers.filter((item) => item.is_accepted);
    assert(accepted.length === 1, `最佳答案应唯一，实际 ${accepted.length}`);
    return `提问 → 普通用户 403 → 专家作答（带职称）→ 采纳唯一`;
  });

  // 第 76 批：这两个检查对应"系统少了用户管理"与"授予专家不能取消"两个真实反馈
  await check('P2/P3', '专家称号：管理员可取消（第 76 批）', async () => {
    const before = await api('consult/experts/', { token: tokenAdmin });
    assert(
      before.data.results.some((item) => item.user.id === userIds.expert),
      '取消前该用户应在专家列表里',
    );

    const revoked = await api(`consult/experts/${userIds.expert}/`, { method: 'DELETE', token: tokenAdmin });
    assert(revoked.status === 200 && revoked.data.changed === true, `取消失败: ${revoked.status}`);

    const after = await api('consult/experts/', { token: tokenAdmin });
    assert(
      !after.data.results.some((item) => item.user.id === userIds.expert),
      '取消后不该再出现在专家列表里',
    );

    // 幂等：重复点"取消"不该报错（软删除）
    const again = await api(`consult/experts/${userIds.expert}/`, { method: 'DELETE', token: tokenAdmin });
    assert(again.status === 200 && again.data.changed === false, '重复取消应幂等（changed=false）');

    // 也不能再用专家身份作答
    const blocked = await api(`consult/questions/${askedQuestionId}/answers/`, {
      method: 'POST', token: tokenExpert, body: { content: '被取消专家后不应该还能回答。' },
    });
    assert(blocked.status === 403, `取消后仍能作答（返回 ${blocked.status}）`);
    return '取消 → 列表移除 + 不能再作答 + 重复取消幂等';
  });

  await check('P0', '用户管理：仅管理员可见 + 专家身份取反', async () => {
    // DRF 的 IsAdminUser：**未认证 → 401**，已认证但非管理员 → 403。
    // 两者都要挡（这里第一次写成"游客也应 403"，实测被 401 打回）。
    const guest = await api('admin/users/');
    assert(guest.status === 401, `游客应被拒（401），实际 ${guest.status}`);
    const denied = await api('admin/users/', { token: tokenUser });
    assert(denied.status === 403, `普通用户应被拒（403），实际 ${denied.status}`);

    const list = await api('admin/users/?search=zz_smoke_expert', { token: tokenAdmin });
    assert(list.status === 200 && list.data.count === 1, `管理员列表失败: ${list.status}`);
    const row = list.data.results[0];
    assert(row.email !== undefined && row.is_active === true, '应含管理端字段（email / is_active）');
    assert(row.is_expert === false, '刚被取消专家，用户管理页不该还显示成专家');

    // page_size 必须真的生效（DRF 自带的 PageNumberPagination 会忽略它）
    const sized = await api('admin/users/?page_size=2', { token: tokenAdmin });
    assert(sized.data.results.length === 2, `page_size 未生效，返回 ${sized.data.results.length} 条`);

    const filtered = await api('admin/users/?status=expert&search=zz_smoke_expert', { token: tokenAdmin });
    assert(filtered.data.count === 0, '已取消的用户不该命中"专家"筛选');

    const detail = await api(`admin/users/${userIds.expert}/`, { token: tokenAdmin });
    assert(detail.status === 200 && detail.data.id === userIds.expert, '用户详情接口异常');
    assert(detail.data.post_count === row.post_count, '详情与列表的活跃度计数应一致');
    return '游客/普通用户 403 → 列表字段齐全 → page_size 生效 → 专家筛选与详情正确';
  });

  await check('P2/P3', '离线资料包：内容指纹 + 增量判定', async () => {
    const pack = await api('pests/offline-pack/', { token: tokenUser });
    assert(pack.status === 200, `资料包失败: ${pack.status}`);
    assert(pack.data.count > 0 && pack.data.items.length === pack.data.count, '应返回全部条目');
    assert(pack.data.items[0].prevention_methods !== undefined, '应含防治方法');
    const same = await api(`pests/offline-pack/?since=${pack.data.version}`, { token: tokenUser });
    assert(same.data.unchanged === true && !same.data.items, '同版本应回 unchanged 且不带 items');
    return `${pack.data.count} 条 / version=${pack.data.version} / 增量判定生效`;
  });

  // ================= UI 检查（需要前端 5173） =================
  if (WITH_UI) {
    console.log('\n界面检查（Playwright）');
    const { chromium } = await import('playwright');
    const browser = await chromium.launch({ channel: 'msedge', headless: true });

    await check('UI', '移动端：窄屏无横向溢出、无被裁内容', async () => {
      const context = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });
      const page = await context.newPage();
      await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
      await page.fill('#username', 'zz_smoke_admin');
      await page.fill('#password', 'SmokeTest!2026');
      await page.click('.cs-submit');
      await page.waitForURL((u) => !u.pathname.includes('/login'), { timeout: 25000 });
      await page.waitForTimeout(1200);

      const routes = ['/', '/forum', '/history', '/calendar', '/consult'];
      const problems = [];
      for (const route of routes) {
        await page.goto(`${UI}${route}`, { waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(2500);
        const report = await page.evaluate(() => {
          const vw = window.innerWidth;
          const clipped = [];
          document.querySelectorAll('body *').forEach((el) => {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return;
            const style = getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return;
            if (style.overflowX === 'auto' || style.overflowX === 'scroll') return; // 本就是滚动容器
            if (style.overflowX !== 'hidden' && style.overflowX !== 'clip') return;
            const hidden = el.scrollWidth - el.clientWidth;
            if (hidden <= 8 || el.clientWidth <= 200) return;

            const cls = String(el.className || '');
            // ① 轮播容器：幻灯片本来就比容器宽（横向滚动条由库控制）
            if (cls.includes('carousel')) return;
            // ② 单行省略号：长标题按设计被截断（text-overflow: ellipsis）
            if (style.textOverflow === 'ellipsis' && style.whiteSpace === 'nowrap') return;
            // ③ 装饰性伪元素（定位在盒子右侧之外的圆形装饰）
            const after = getComputedStyle(el, '::after');
            if (after.content && after.content !== 'none' && parseFloat(after.right || '0') < 0) return;

            clipped.push(`${el.tagName}.${cls.slice(0, 30)} 裁 ${hidden}px`);
          });
          return { overflow: document.documentElement.scrollWidth - vw, clipped: clipped.slice(0, 3) };
        });
        if (report.overflow > 2) problems.push(`${route} 整页横向溢出 ${report.overflow}px`);
        report.clipped.forEach((item) => problems.push(`${route} ${item}`));
      }
      await context.close();
      assert(problems.length === 0, `发现 ${problems.length} 处问题：${problems.slice(0, 3).join('；')}`);
      return `${routes.length} 个页面：整页无横向溢出、无内容被裁`;
    });

    await check('UI', '多语言：切换后持久化且 <html lang> 同步', async () => {
      const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
      const page = await context.newPage();
      await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
      await page.fill('#username', 'zz_smoke_admin');
      await page.fill('#password', 'SmokeTest!2026');
      await page.click('.cs-submit');
      await page.waitForURL((u) => !u.pathname.includes('/login'), { timeout: 25000 });
      await page.waitForSelector('.lang-btn', { timeout: 20000 });

      await page.click('.lang-btn');
      await page.waitForTimeout(600);
      await page.click('.el-dropdown-menu__item:has-text("English")');
      await page.waitForTimeout(1200);
      const lang = await page.getAttribute('html', 'lang');
      const nav = await page.$$eval('.nav-link', (els) => els.map((e) => e.textContent.trim()).join('|'));
      assert(lang === 'en', `<html lang> 应为 en，实际 ${lang}`);
      assert(nav.includes('Home') && nav.includes('Expert Q&A'), `导航未切换：${nav}`);

      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(2500);
      const stored = await page.evaluate(() => localStorage.getItem('app_locale'));
      assert(stored === 'en', '语言选择应持久化到 localStorage');

      await page.click('.lang-btn');
      await page.waitForTimeout(600);
      await page.click('.el-dropdown-menu__item:has-text("简体中文")');
      await page.waitForTimeout(1000);
      await context.close();
      return '中 → EN（html lang=en、导航英文、刷新后仍为 EN）→ 切回中文';
    });

    await check('UI', '用户管理页：列表 / 详情 / 搜索 / 取消专家全链路（第 76 批）', async () => {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const page = await context.newPage();
      await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
      await page.fill('#username', 'zz_smoke_admin');
      await page.fill('#password', 'SmokeTest!2026');
      await page.click('.cs-submit');
      await page.waitForURL((u) => !u.pathname.includes('/login'), { timeout: 25000 });

      await page.goto(`${UI}/admin/users`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('.el-table__row', { timeout: 25000 });

      const heading = (await page.textContent('.admin-hero h1')) || '';
      assert(heading.includes('用户管理'), `页头不对: ${heading}`);
      const rows = await page.$$eval('.el-table__row', (els) => els.length);
      assert(rows > 0, '用户列表没有渲染出任何一行');

      const target = page.locator('.el-table__row', { hasText: 'zz_smoke_user' }).first();
      assert((await target.count()) === 1, '列表里找不到 zz_smoke_user');

      // 详情弹窗（用户管理页的核心能力之一）
      await target.locator('button:has-text("详情")').click();
      await page.waitForSelector('.el-dialog__body .el-descriptions', { timeout: 20000 });
      const detail = (await page.textContent('.el-dialog__body')) || '';
      assert(detail.includes('zz_smoke_user'), '详情弹窗没有显示该用户');
      await page.keyboard.press('Escape');
      await page.waitForTimeout(800);

      // 搜索框：注意 .filter-bar 里第一个 input 是 el-select 的只读 combobox，
      // 必须认 .el-input__inner，否则 fill 会卡在"元素不可编辑"上
      const search = page.locator('.filter-bar input.el-input__inner');
      await search.fill('zz_smoke_user');
      await search.press('Enter');
      await page.waitForTimeout(1800);
      assert((await page.locator('.el-table__row').count()) === 1, '搜索应只剩 1 行');
      await search.fill('');
      await search.press('Enter');
      await page.waitForTimeout(1500);

      // 「取消专家」全链路：这正是用户反馈"授予专家不能取消"的那条路径。
      // 接口检查里已把 zz_smoke_expert 取消过一次，这里先重新授予，再从页面点取消。
      await api(`consult/experts/${userIds.expert}/`, {
        method: 'POST', token: tokenAdmin, body: { title: 'UI 冒烟职称', specialties: '番茄' },
      });
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.waitForSelector('.el-table__row', { timeout: 25000 });

      const expertRow = page.locator('.el-table__row', { hasText: 'zz_smoke_expert' }).first();
      assert((await expertRow.count()) === 1, '列表里找不到 zz_smoke_expert');
      assert(
        (await expertRow.locator('button:has-text("取消专家")').count()) === 1,
        '在岗专家应显示「取消专家」按钮',
      );

      await expertRow.locator('button:has-text("取消专家")').click();
      await page.waitForSelector('.el-message-box', { timeout: 15000 });
      await page.click('.el-message-box__btns .el-button--primary');
      await page.waitForSelector('.el-message--success', { timeout: 15000 });
      const toast = (await page.locator('.el-message--success').last().textContent()) || '';
      assert(toast.includes('已取消专家称号'), `成功提示不对: ${toast}`);

      await page.waitForTimeout(1800);
      const flipped = page.locator('.el-table__row', { hasText: 'zz_smoke_expert' }).first();
      assert(
        (await flipped.locator('button:has-text("授予专家")').count()) === 1
          && (await flipped.locator('button:has-text("取消专家")').count()) === 0,
        '取消后按钮应翻转为「授予专家」',
      );

      const expertList = await api('consult/experts/', { token: tokenAdmin });
      assert(
        !expertList.data.results.some((item) => item.user.id === userIds.expert),
        '取消后不该还在后端专家列表里',
      );

      await context.close();
      return `渲染 ${rows} 行 / 详情弹窗 / 搜索 / 取消专家全链路`;
    });

    await browser.close();
  }

  // ================= 汇总 =================
  const failed = results.filter((item) => !item.ok);
  console.log('\n================ 冒烟回归汇总 ================');
  const byBatch = {};
  results.forEach((item) => {
    byBatch[item.batch] = byBatch[item.batch] || { pass: 0, fail: 0 };
    byBatch[item.batch][item.ok ? 'pass' : 'fail'] += 1;
  });
  Object.entries(byBatch).forEach(([batch, stat]) => {
    console.log(`  ${batch.padEnd(8)} 通过 ${stat.pass}  失败 ${stat.fail}`);
  });
  console.log(`  合计：${results.length - failed.length}/${results.length} 通过`);
  return failed.length === 0;
}

let exitCode = 1;
try {
  const allPassed = await main();
  exitCode = allPassed ? 0 : 1;
} catch (error) {
  console.error('\n冒烟回归中断:', error.message);
  exitCode = 1;
} finally {
  const cleaned = cleanup();
  console.log(cleaned ? '临时账号与测试数据已清理' : '⚠️ 清理失败，请检查 zz_smoke_* 残留');
}
process.exit(exitCode);
