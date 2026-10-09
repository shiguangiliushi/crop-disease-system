/**
 * 检查「Element Plus 按需注册」的组件清单是否与模板一致
 * ============================================================================
 * 为什么需要这个脚本
 * ----------------------------------------------------------------------------
 * 项目把 `app.use(ElementPlus)` 换成了**按需注册**（见 src/plugins/element-plus.js），
 * 代价是：**模板里用了但没注册的组件会被当成未知自定义元素** ——
 * 界面上不会报错，只是：
 *   · 组件渲染成一行没有样式的文字/空壳；
 *   · 或者"点了没反应"（因为拿不到组件提供的上下文）。
 *
 * 这个坑已经踩过两次：
 *   1. 第 41 批：`<el-radio>` 没注册（只注册了 RadioGroup/RadioButton）——
 *      举报弹窗的"举报理由"只剩一行文字、点了没反应；
 *   2. 第 128 批：`<el-checkbox-group>` 没注册 —— 故障更隐蔽：
 *      **单个 checkbox 看起来是好的**（ElCheckbox 注册了），
 *      但它拿不到 group 的上下文，于是 v-model 完全不生效：
 *      弹窗里四个模块框全是未勾选、点一下只改 DOM，提交上去的还是老值。
 *      这个 bug 单测抓不到、后端测试也抓不到，只有真的用浏览器点一遍才会发现。
 *
 * 脚本做两件事：
 *   A. 列出**模板里用到、但 element-plus.js 里没注册**的组件（这是必须修的，退出码 1）；
 *   B. 列出**注册了但没人用**的组件（只是提示，便于下次清理）。
 *
 * 用法：node scripts/check-element-components.mjs
 */
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const pluginPath = path.join(root, 'src/plugins/element-plus.js');

/** 收集 src 下所有 .vue 模板里出现的 `el-xxx` 标签 */
function collectUsedTags(dir) {
  const used = new Map(); // el-xxx -> 出现的文件
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      for (const [tag, files] of collectUsedTags(full)) {
        const list = used.get(tag) || [];
        list.push(...files);
        used.set(tag, list);
      }
      continue;
    }
    if (!entry.name.endsWith('.vue')) continue;
    const text = fs.readFileSync(full, 'utf8');
    // 只认 <el-xxx 这种开标签（含自闭合）；不认字符串里的示例代码
    for (const match of text.matchAll(/<(el-[a-z0-9-]+)[\s/>]/g)) {
      const tag = match[1];
      const list = used.get(tag) || [];
      if (!list.includes(full)) list.push(full);
      used.set(tag, list);
    }
  }
  return used;
}

/** `el-checkbox-group` → `ElCheckboxGroup` */
const tagToComponent = (tag) => 'El' + tag
  .replace(/^el-/, '')
  .split('-')
  .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
  .join('');

const pluginText = fs.readFileSync(pluginPath, 'utf8');
// 注册列表就是 plugin 里 `const components = [...]` 那一份（不是 import 那一份：
// 有的组件 import 了却没进 components，那等于没注册）
const componentsBlock = /const components = \[([\s\S]*?)\];/.exec(pluginText);
if (!componentsBlock) {
  console.error('❌ 读不到 element-plus.js 里的 `const components = [...]` —— 脚本需要跟着插件文件一起维护');
  process.exit(1);
}
const registered = new Set(
  [...componentsBlock[1].matchAll(/\b(El[A-Za-z0-9]+)\b/g)].map((m) => m[1]),
);

const used = collectUsedTags(path.join(root, 'src'));

const missing = [];
for (const [tag, files] of used) {
  const component = tagToComponent(tag);
  if (!registered.has(component)) {
    missing.push({ tag, component, files: files.map((f) => path.relative(root, f)) });
  }
}

const usedComponents = new Set([...used.keys()].map(tagToComponent));
const unused = [...registered].filter((name) => !usedComponents.has(name)).sort();

console.log(`模板里用到的 el-* 组件：${used.size} 个`);
console.log(`element-plus.js 已注册：${registered.size} 个\n`);

if (missing.length) {
  console.log('❌ 用了但**没注册**（会渲染成未知元素，点了多半没反应）：');
  for (const item of missing) {
    console.log(`  · <${item.tag}> → 需要 ${item.component}`);
    console.log(`      出现在：${item.files.join('、')}`);
  }
  console.log('\n修法：在 src/plugins/element-plus.js 的 import 与 components 数组里都加上它。');
} else {
  console.log('✅ 模板里用到的组件都已注册');
}

if (unused.length) {
  console.log(`\nℹ️ 注册了但模板里没用到（可以清理，注意有的可能在 .js 里编程式使用）：\n  ${unused.join('、')}`);
}

process.exit(missing.length ? 1 : 0);
