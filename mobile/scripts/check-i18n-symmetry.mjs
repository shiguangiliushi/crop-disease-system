/**
 * 移动端 i18n key 对称性检查（临时脚本）
 *
 * 为什么值得单独查：t() 找不到英文会**回落中文**（界面不会空白），
 * 所以"英文缺 key"在界面上表现为"英文界面里冒出一句中文" —— 只有对着页面才看得出来。
 * 这里用静态比对代替肉眼。
 */
import { messages } from '../src/i18n/messages.js';

const zh = messages['zh-CN'];
const en = messages.en;

const missing = [];
for (const ns of Object.keys(zh)) {
  if (!en[ns]) { missing.push(`en 整个缺命名空间: ${ns}`); continue; }
  const zk = Object.keys(zh[ns]);
  const ek = Object.keys(en[ns]);
  for (const k of zk) if (!ek.includes(k)) missing.push(`en 缺 ${ns}.${k}`);
  for (const k of ek) if (!zk.includes(k)) missing.push(`zh 缺 ${ns}.${k}`);
}
for (const ns of Object.keys(en)) {
  if (!zh[ns]) missing.push(`zh 整个缺命名空间: ${ns}`);
}

const count = (o) => Object.values(o).reduce((n, v) => n + Object.keys(v).length, 0);
console.log(`命名空间: ${Object.keys(zh).length} 个`);
console.log(`key 数: zh=${count(zh)} en=${count(en)}`);
console.log(missing.length ? `\n❌ 不对称 ${missing.length} 处:\n${missing.join('\n')}` : '\n✅ 中英 key 完全对称');
process.exit(missing.length ? 1 : 0);
