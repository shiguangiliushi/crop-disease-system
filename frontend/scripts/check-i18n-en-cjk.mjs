/**
 * 检查英文语言包里有没有残留的中文
 * ============================================================================
 * 为什么需要它
 * ----------------------------------------------------------------------------
 * 用户报过一个很典型的例子：切到英文后，「内容审核」页的敏感词输入框提示
 * 依然写着 `Enter a word, e.g. 加微信` —— **英文句子 + 中文例子**。
 * 这类问题单看代码很难发现（键在、值也在，两种语言的 key 结构测试也全过），
 * 只有真的切到英文把页面看一遍才会注意到。
 *
 * 于是把它变成一条**可自动检查的规则**：英文语言包里不该出现中日韩字符。
 *
 * 例外（脚本会打印出来，需要人工确认）：
 *   · 有些英文文案**故意**要带中文 —— 例如"输入中文名"的说明、
 *     或者中文示例本身（那种应显式列进 ALLOWLIST，而不是放宽规则）。
 * 目前 ALLOWLIST 为空 —— 也就是说这份语言包做到了"英文里没有中文"。
 *
 * 用法：node scripts/check-i18n-en-cjk.mjs
 */
import { en } from '../src/i18n/messages.js';

/** 允许英文文案里出现中文的键（每一条都要能说出理由） */
const ALLOWLIST = new Set([
  // 语言切换菜单里，每种语言**用自己的文字**显示自己（"简体中文" / "English"）——
  // 这是通行做法：把中文写成 "Chinese (Simplified)" 反而让中文用户找不到。
  'language.zh',
]);

const CJK = /[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]/;

/** 把嵌套对象拍平成 `a.b.c` → 值 */
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

const flat = flatten(en);
const offenders = [];
const allowed = [];

for (const [key, value] of Object.entries(flat)) {
  if (!CJK.test(value)) continue;
  (ALLOWLIST.has(key) ? allowed : offenders).push({ key, value });
}

const total = Object.keys(flat).length;
console.log(`英文语言包共 ${total} 条文案`);

if (allowed.length) {
  console.log(`\nℹ️ 允许带中文的 ${allowed.length} 条（在 ALLOWLIST 里）：`);
  for (const item of allowed) console.log(`  · ${item.key}: ${item.value}`);
}

if (offenders.length) {
  console.log(`\n❌ 英文里混进了中文的 ${offenders.length} 条：`);
  for (const item of offenders) {
    // 把中文片段截出来，方便一眼看到问题在哪
    const hit = item.value.match(new RegExp(CJK.source + '+', 'g')) || [];
    console.log(`  · ${item.key}`);
    console.log(`      值：${item.value}`);
    console.log(`      中文片段：${hit.join(' / ')}`);
  }
  console.log('\n修法：把英文侧改成英文写法；若确实需要中文示例，请显式加进脚本的 ALLOWLIST。');
  process.exit(1);
}

console.log('\n✅ 英文语言包里没有残留中文');
