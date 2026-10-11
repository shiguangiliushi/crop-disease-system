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
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const quiet = process.argv.includes('--quiet');

// ---------------------------------------------------------------------------
// 0. 语言包里**重复的键**（第 158 批补）
//
// 为什么必须单独查：JS 对象里同名的后一个键**静默覆盖**前一个 ——
// 也就是说重复键不会报错、不会崩，只会让其中一份文案**永远不生效**。
// 第 157 批我用脚本往 messages.js 插"系统健康"的文案时算错了行号，
// 结果 zhCN 里多出一个英文的 `health: {…}` 块：页面看着完全正常（后一个中文块胜出），
// `npm run check` 也全绿（英文块在英文对象里查，中文对象里的英文块没人看）。
// 直到第 158 批给英文补趋势文案，才发现"英文键 24 / 中文键 29"。
//
// 做法：**基于文本**扫（不能靠 import —— import 之后重复键已经被覆盖掉了），
// 用缩进跟踪"当前在哪个块里"，同一层级出现同名键就报出来。
// ---------------------------------------------------------------------------
function findDuplicateKeys(file) {
  const source = fs.readFileSync(file, 'utf8');
  const lines = source.split('\n');
  const stack = [];        // [{ indent, key, seen: Map }]
  const problems = [];

  // ⚠️ 第一版只匹配"块"键（`key: {`），于是**字符串键的重复完全抓不到** ——
  //    我造了个 `title: '重复的标题'` 去试，它一声不吭。
  //    现在两种都登记：块键与普通键（要求行尾是 `,` 或 `{`，
  //    这样多行字符串里的散文行不会被误当成键）。
  const KEY = /^(\s*)(?:'([^']+)'|([A-Za-z_$][\w$]*))\s*:\s*(.*)$/;
  // ⚠️ 第二版又误报了 30 处：`faqGroups: [ { key:..., title:... }, { key:..., title:... } ]`
  //    这种**多行数组元素**里，每个元素都有自己的 key/title，是合法的 ——
  //    但我的扫描器把它们算成了外层命名空间的键，于是"重复"满天飞。
  //    所以：单独一行的 `{` / `[` 要开一个**匿名作用域**，里面的键不与外层混。
  const BARE_OPEN = /^(\s*)[{[]\s*$/;
  const CLOSE = /^(\s*[}\]]+[,;]?\s*)$/;

  for (let index = 0; index < lines.length; index += 1) {
    const raw = lines[index];
    if (/^\s*(\/\/|\*|\/\*)/.test(raw)) continue;      // 注释行

    const closing = CLOSE.exec(raw);
    if (closing) {
      const indent = raw.length - raw.trimStart().length;
      while (stack.length && stack[stack.length - 1].indent >= indent) stack.pop();
      continue;
    }

    const bare = BARE_OPEN.exec(raw);
    if (bare) {
      const indent = bare[1].length;
      while (stack.length && stack[stack.length - 1].indent >= indent) stack.pop();
      // 匿名作用域：只用来隔离数组元素里的键，不参与"重复"统计
      stack.push({ indent, key: '(数组元素)', seen: new Map(), anonymous: true });
      continue;
    }

    const match = KEY.exec(raw);
    if (!match) continue;
    const rest = match[4].trim();
    const isBlock = rest.startsWith('{');
    const isScalar = /,$/.test(rest) || /^[^,{[]*,\s*$/.test(rest) || rest === '';
    if (!isBlock && !isScalar) continue;               // 既不是块、也不像"键: 值,"的整行

    const indent = match[1].length;
    const key = match[2] || match[3];
    while (stack.length && stack[stack.length - 1].indent >= indent) stack.pop();
    const parent = stack[stack.length - 1];
    if (parent && !parent.anonymous) {
      if (parent.seen.has(key)) {
        problems.push(`第 ${index + 1} 行：${parent.key} 里重复定义了 \`${key}\`（第一次在第 ${parent.seen.get(key)} 行）`);
      } else {
        parent.seen.set(key, index + 1);
      }
    }
    if (isBlock) stack.push({ indent, key, seen: new Map() });
  }
  return problems;
}

// ⚠️ 用 fileURLToPath：第一版用 `pathToFileURL(...).pathname` 手动拼，
//    在 Windows 上会得到 `/D:/%E6%96%B0...` 这种 URL 编码路径，readFileSync 直接 ENOENT。
const messagesFile = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../src/i18n/messages.js',
);
const duplicateProblems = findDuplicateKeys(messagesFile);

if (duplicateProblems.length) {
  console.error(`\n❌ 语言包里出现重复的键 ${duplicateProblems.length} 处（后一个会**静默覆盖**前一个）：`);
  duplicateProblems.forEach((item) => console.error(`   · ${item}`));
  process.exitCode = 1;
} else if (!quiet) {
  console.log('✅ 0. 语言包里没有重复的键（重复键会让一份文案永远不生效）');
}

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
/**
 * 本来就该两边一样的：
 *   · 语言名（每种语言用自己的文字显示自己）；
 *   · **快捷键文本**（`Ctrl+Enter` / `Ctrl+S` 在各种语言里都是这么写，
 *     第 165 批给按钮加提示时加进来的 —— 翻译它反而会误导用户按错键）。
 */
const IDENTICAL_ALLOWLIST = new Set([
  'language.zh',
  'language.en',
  'post.shortcutPublish',
  'post.shortcutDraft',
]);

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
  版块管理: ['Board management'],                 // 第 140 批新增的控制台页面（侧栏/标签页/页面标题同名）
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
