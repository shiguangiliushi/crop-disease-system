/**
 * 语言包一致性检查：同一条文案的两种语言、以及同一术语的多种译法
 * ============================================================================
 * 背景（第 133 批发现的问题）
 * ----------------------------------------------------------------------------
 * 「英文界面里有中文」只是"值写错了"里最显眼的一种。同一类问题还有两种：
 *
 *   A. **英文侧与中文侧一字不差** —— 多半是复制过去忘了翻。
 *      注意：不是所有相同都错 —— 路由（`/detect`）、图标类名（`fas fa-camera-retro`）、
 *      语言名（"English"）本来就该两边一样，脚本按规则自动放过这些。
 *
 *   B. **同一个中文词在不同地方译成了不同的英文** —— 例如「新闻管理」在侧栏叫
 *      "News Admin"、在标签页标题里叫 "News management"、在权限模块里叫 "News admin"。
 *      用户在不同页面看到同一个功能的三个名字，会以为它们是三件不同的事。
 *      这一条用**术语表**（GLOSSARY）来管：核心名词只认一个写法（大小写敏感），
 *      确实因语境需要变体时（如单复数）显式列出可用集合。
 *
 *   C. 其余"一中文多英文"（长句、语境差异）**只列出来供人检查，不算失败** ——
 *      强行统一长句的译法只会把好英文改坏。
 *
 * 用法：
 *   node scripts/check-i18n-consistency.mjs            # A、B 不过就退出码 1；C 只打印
 *   node scripts/check-i18n-consistency.mjs --quiet    # 不打印 C 的清单
 */
import { en, zhCN } from '../src/i18n/messages.js';

const quiet = process.argv.includes('--quiet');

/** 拍平成 `a.b[0].c` → 值 */
function flatten(object, prefix = '', out = {}) {
  for (const [key, value] of Object.entries(object)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      flatten(value, path, out);
    } else if (typeof value === 'string') {
      out[path] = value;
    } else if (Array.isArray(value)) {
      value.forEach((item, index) => {
        if (typeof item === 'string') out[`${path}[${index}]`] = item;
        else if (item && typeof item === 'object') flatten(item, `${path}[${index}]`, out);
      });
    }
  }
  return out;
}

const zh = flatten(zhCN);
const eng = flatten(en);

// ---------------------------------------------------------------------------
// A. 两侧一字不差
// ---------------------------------------------------------------------------
/** 本来就该两边一样的：语言名（每种语言用自己的文字显示自己） */
const IDENTICAL_ALLOWLIST = new Set(['language.zh', 'language.en']);

/** 技术性取值：路由、图标类名、纯标识符 —— 这些与语言无关 */
const isLanguageNeutral = (value) => {
  if (!value) return true;
  if (value.startsWith('/') || value.includes('://')) return true;          // 路由 / URL
  if (/^fa[srlbd]?\s+fa-/.test(value)) return true;                          // Font Awesome
  if (/^[A-Za-z0-9_.\-/]+$/.test(value) && value.length <= 24) return true;  // 标识符（detect/CSV/…）
  if (!/[A-Za-z]/.test(value)) return true;                                  // 没有字母（符号/emoji）
  return false;
};

const identicalOffenders = Object.keys(eng)
  .filter((key) => zh[key] !== undefined && zh[key] === eng[key])
  .filter((key) => !IDENTICAL_ALLOWLIST.has(key) && !isLanguageNeutral(eng[key]))
  .map((key) => ({ key, value: eng[key] }));

// ---------------------------------------------------------------------------
// B. 核心术语表（中文 → 允许的英文写法）
// ---------------------------------------------------------------------------
// 为什么是"允许集合"而不是单一值：有的词天然有语境差异（普通用户 → 单数/复数），
// 强行只留一个会把另一处的英文改坏。但**核心名词**（四个内容模块、角色、看板页）
// 只给一个写法 —— 它们现在是权限名，用户在侧栏、标签页、权限提示里看到它们必须一致。
const GLOSSARY = {
  数据看板: ['Dashboard'],
  用户管理: ['User management'],
  内容审核: ['Content review'],
  新闻管理: ['News management'],
  病害百科: ['Disease wiki'],
  意见反馈管理: ['Feedback management'],
  意见反馈: ['Feedback'],
  通知中心: ['Notifications'],
  信息编辑员: ['Editor'],
  系统管理员: ['System administrator'],
  普通用户: ['Regular user', 'Regular users'],
  管理员: ['Administrator', 'Admins', 'Admin'],   // 语境差异（角色名/统计卡/筛选值）

  // 后台页面名（与侧栏同源）：注意这里区分"模块名"与"页面名" ——
  // 中文侧本来就用了两个词，英文侧各给一个写法，不算冲突。
  病害百科维护: ['Disease wiki admin'],           // 页面（H1 + 标签页）；模块名是「病害百科」
  新闻列表: ['News list'],
  用户列表: ['User list'],
  反馈列表: ['Feedback list'],
  词条列表: ['Entries'],
  待审核: ['Pending review'],                     // 状态标签；第 134 批统一（原来是 Pending/Pending review 两种）
  // 内容模块名与页面名一致（第 128 批把内容拆成四块后，它们同时是权限名）：
  内容生产: ['Content'],
};

const glossaryOffenders = [];
const glossaryChecked = [];
for (const [key, zhValue] of Object.entries(zh)) {
  const accepted = GLOSSARY[zhValue];
  if (!accepted) continue;
  const enValue = eng[key];
  if (typeof enValue !== 'string') continue;
  glossaryChecked.push(key);
  if (!accepted.includes(enValue)) {
    glossaryOffenders.push({ key, zh: zhValue, en: enValue, accepted });
  }
}

// ---------------------------------------------------------------------------
// C. 其余"一中文多英文"（仅供参考）
// ---------------------------------------------------------------------------
const multiMap = new Map();
for (const [key, zhValue] of Object.entries(zh)) {
  const enValue = eng[key];
  if (typeof enValue !== 'string' || !enValue) continue;
  if (!/[\u4e00-\u9fff]/.test(zhValue)) continue;
  if (zhValue.length > 16) continue;             // 长句天然随语境变化，不列
  if (GLOSSARY[zhValue]) continue;               // 术语表已经管了
  if (!multiMap.has(zhValue)) multiMap.set(zhValue, new Map());
  const bucket = multiMap.get(zhValue);
  if (!bucket.has(enValue)) bucket.set(enValue, []);
  bucket.get(enValue).push(key);
}
const multi = [...multiMap.entries()]
  .filter(([, bucket]) => bucket.size > 1)
  .sort((a, b) => b[1].size - a[1].size);

// ---------------------------------------------------------------------------
// 报告
// ---------------------------------------------------------------------------
console.log(`语言包：中文 ${Object.keys(zh).length} 条 / 英文 ${Object.keys(eng).length} 条`);
console.log(`术语表覆盖 ${glossaryChecked.length} 个键（${Object.keys(GLOSSARY).length} 个术语）`);

let failed = false;

if (identicalOffenders.length) {
  failed = true;
  console.log(`\n❌ A. 英文侧与中文侧一字不差（像是忘了翻译）${identicalOffenders.length} 条：`);
  for (const item of identicalOffenders) console.log(`  · ${item.key} = ${JSON.stringify(item.value)}`);
  console.log('  若确实两边该一样（路由/图标/语言名），脚本已自动放过；仍报错就请人工确认。');
} else {
  console.log('\n✅ A. 没有"英文侧与中文侧一字不差"的可疑条目');
}

if (glossaryOffenders.length) {
  failed = true;
  console.log(`\n❌ B. 核心术语译法不一致 ${glossaryOffenders.length} 条：`);
  for (const item of glossaryOffenders) {
    console.log(`  · ${item.key}`);
    console.log(`      「${item.zh}」现在译成 ${JSON.stringify(item.en)}`);
    console.log(`      应当用：${item.accepted.map((v) => JSON.stringify(v)).join(' 或 ')}`);
  }
} else {
  console.log('✅ B. 核心术语译法一致');
}

if (!quiet && multi.length) {
  console.log(`\nℹ️ C. 同一中文有多种英文（多数是语境差异，供人工过一眼）：${multi.length} 组`);
  for (const [zhValue, bucket] of multi.slice(0, 25)) {
    console.log(`  「${zhValue}」 → ${[...bucket.keys()].map((v) => JSON.stringify(v)).join(' / ')}`);
  }
  if (multi.length > 25) console.log(`  …… 还有 ${multi.length - 25} 组`);
}

process.exit(failed ? 1 : 0);
