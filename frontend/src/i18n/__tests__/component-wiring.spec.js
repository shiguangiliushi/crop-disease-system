/**
 * 组件 i18n 接线自检（第 70 批，第 71 批扩充）
 * ------------------------------------------------------------------
 * 背景：本项目有两种组件写法 ——
 *   ① `<script setup>`：顶层绑定自动暴露给模板；
 *   ② `<script>` + `export default { setup() {…} }`：**必须把 `t` 放进 return**。
 * 第 64/67/68 批接连在 ② 上踩坑（MessagesView / MessageEntry / NotificationBell / EditPostView）：
 * 模板里写了 `t(...)`，但 `setup()` 没有返回 `t` —— 运行时整块渲染报
 * `TypeError: _ctx.t is not a function`（**type-check 不会报**，只有打开页面才会发现）。
 *
 * 第 71 批补充：同一个坑不止发生在 `t` 上。真实事故：
 *   · FeedbackCenterView 的 `categoryLabel` / `statusLabel` 没 return
 *     → 意见反馈页整页抛 `_ctx.categoryLabel is not a function`；
 *   · UserProfileView 的 `userId` 没 return
 *     → `<ReportDialog :target-id="userId">` 恒为 undefined，"举报用户"点了没反应。
 * 所以这里把规则**从 t 推广到所有"在 setup 里定义、模板里调用/引用"的标识符**。
 *
 * 判定方式（静态、无需挂载组件）：
 *   1. 收集模板里出现的标识符（去掉 v-for / slot 作用域变量、$ 全局、关键字、局部声明）；
 *   2. 收集 setup() 内 `const/let/function/...` 声明的顶层名字；
 *   3. 若某名字在 (2) 里定义、但不在 setup 的 `return {…}` 里 → 报错。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = join(process.cwd(), 'src');

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (name === '_deprecated') continue;  // 废弃组件不参与
      out.push(...walk(path));
    } else if (name.endsWith('.vue')) {
      out.push(path);
    }
  }
  return out;
}

/** 取出 <template>…</template> 主体 */
function templateOf(source) {
  const m = source.match(/<template>([\s\S]*)<\/template>/);
  return m ? m[1] : '';
}

/** 模板里所有 v-for / slot 作用域引入的局部名，需要排除 */
function scopeLocals(tpl) {
  const locals = new Set();
  // v-for="item in list" / v-for="(count, key) in obj" / v-for="answer in detail.answers"
  for (const m of tpl.matchAll(/v-for\s*=\s*"([^"]*)"/g)) {
    const expr = m[1];
    const inIdx = expr.indexOf(' in ');
    const ofIdx = expr.indexOf(' of ');
    const cut = inIdx >= 0 ? inIdx : ofIdx;
    if (cut < 0) continue;
    const lhs = expr.slice(0, cut);
    for (const raw of lhs.replace(/[()]/g, '').split(',')) {
      const name = raw.trim().split(/[\s=]/)[0];
      if (/^[A-Za-z_$][\w$]*$/.test(name)) locals.add(name);
    }
  }
  // #default="scope" / v-slot:foo="props"
  for (const m of tpl.matchAll(/(?:#\w[\w-]*|v-slot(?::[\w-]+)?)\s*=\s*"([^"]*)"/g)) {
    for (const raw of m[1].replace(/[{}]/g, '').split(',')) {
      const name = raw.trim().split(':').pop()?.trim();
      if (name && /^[A-Za-z_$][\w$]*$/.test(name)) locals.add(name);
    }
  }
  return locals;
}

/** 模板里被引用的标识符（去掉属性名、字符串、作用域变量、Vue 关键字） */
function templateIdentifiers(tpl, locals) {
  const KEYWORDS = new Set([
    'true', 'false', 'null', 'undefined', 'new', 'typeof', 'in', 'of', 'return',
    'if', 'else', 'void', 'delete', 'instanceof', 'this', 'Math', 'Date', 'Number',
    'String', 'Boolean', 'Array', 'Object', 'JSON', 'parseInt', 'parseFloat', 'isNaN',
  ]);
  // 先剥掉 mustache 以外的纯文本噪声，再统一在表达式里找标识符
  const exprs = [];
  for (const m of tpl.matchAll(/\{\{([\s\S]*?)\}\}/g)) exprs.push(m[1]);

  // ⚠️ 属性扫描：这里修过**两个**连环的漏检（第 96 批），两个都会让检查形同虚设
  // ---------------------------------------------------------------------------
  // ① 原来的写法是 `\s(?:…|@|…)="…"` —— 正则吃掉分隔用的空白后，**紧接着的下一个
  //    绑定前面就没有空白可匹配了**，于是只认每行第一个绑定；
  // ② 更要命的是 `(?:…|@|…)\s*=` 里**没有 `[\w-]*`**：`@` 之后还得接
  //    `current-change` 才能到 `=`，正则却直接去匹配 `=` → `@` 分支永远不成立。
  //    也就是说**事件绑定从来就没被扫描过**（`v-if="x"` 这类字面量属性反而正常，
  //    所以 32 个命中里全是 v-if / v-for / :key，一个 `@` 都没有）。
  //
  // 真实后果：我把 `loadPending` 从 setup 的 return 里删掉，测试**照样全绿**，
  // 而页面上翻页是坏的（页码变了、数据不刷新，Vue 只在控制台打一条 warning）。
  //
  // 现在的写法：`@` / `v-on:` / `:` / `v-bind:` 后面允许属性名剩余部分（`[\w-]*`），
  // 前导字符单独取出来判断是不是合法分隔（属性名不会以 `-` 开头，所以 `data-x`
  // 不会被误判成 `x`）。
  for (const m of tpl.matchAll(/[^\w](?:@|v-on:|:|v-bind:)[\w-]*\s*=\s*"([^"]*)"|[^\w](?:v-if|v-else-if|v-show|v-model[\w.:]*|v-html|v-text|v-for|v-slot[\w-]*|key|title|label|placeholder|description|alt)\s*=\s*"([^"]*)"/g)) {
    const value = m[1] !== undefined ? m[1] : m[2];
    const lead = m[0][0];
    // 合法分隔：空白、`<`（标签名刚结束）、`>`（上一个属性刚结束）、引号、括号/逗号。
    // 单独的 `-` 说明前导字符其实属于属性名（如 `data-x`），跳过。
    if (!/[\s<>"'(),]/.test(lead)) continue;
    exprs.push(value);
  }

  const found = new Set();
  for (const expr of exprs) {
    // 去掉字符串字面量，避免把 'fas fa-x' 里的词当成标识符
    const clean = expr.replace(/'[^']*'|"[^"]*"|`[^`]*`/g, ' ');
    for (const m of clean.matchAll(/(^|[^\w$.])([A-Za-z_$][\w$]*)/g)) {
      const name = m[2];
      const start = m.index + m[1].length;
      const before = clean.slice(0, start);
      // 排除属性访问 obj.name 里的 name
      if (before.endsWith('.')) continue;
      // 排除对象字面量的 key：`{ count: total }` 里的 count 是键名，不是引用
      if (/^\s*:/.test(clean.slice(start + name.length))) continue;
      if (KEYWORDS.has(name) || locals.has(name)) continue;
      if (name.startsWith('$')) continue; // $t / $refs 等全局属性
      found.add(name);
    }
  }
  return found;
}

/** setup() 里声明过的顶层名字 */
function setupDeclarations(source) {
  const setupIdx = source.indexOf('setup(');
  if (setupIdx < 0) return new Set();
  const body = source.slice(setupIdx);
  const names = new Set();
  for (const m of body.matchAll(/\b(?:const|let|var|function)\s+([A-Za-z_$][\w$]*)/g)) {
    names.add(m[1]);
  }
  // watch([a, b], …) 之类的解构声明
  for (const m of body.matchAll(/\b(?:const|let|var)\s*\{([^}]*)\}\s*=/g)) {
    for (const raw of m[1].split(',')) {
      const name = raw.trim().split(':').pop()?.trim();
      if (name && /^[A-Za-z_$][\w$]*$/.test(name)) names.add(name);
    }
  }
  return names;
}

/**
 * 第 72 批事故回归：`locale is not defined`
 * ------------------------------------------------------------------
 * HistoryView 的 formatTimestamp 里写了 `locale.value === 'en' …`，
 * 但 `<script setup>` 只解构了 `t`（`const { t } = useI18n()`），没有 `locale`。
 * 这是**运行时** ReferenceError：只有真正渲染到那一行才报，
 * 编译检查、type-check、其它测试都发现不了。
 *
 * 为什么不做通用的"未定义标识符"扫描：试过，误报太多（对象字面量的 key、
 * 模板字符串里的 CSS/HTML、中英混排文案都会被当成标识符），
 * 一个天天飘红的检查等于没有检查。所以这里只做**窄而精确**的判定：
 *
 *   ① `const { … } = useI18n()` / `useLocalized()` 这类解构，
 *      在脚本里用到 `.value` 的成员必须真的在解构名单里；
 *   ② 在 `<script setup>` 里用 `locale.value`，必须来自解构或直接 import。
 *
 * 这条规则精确覆盖本次事故，而且几乎不可能误报。
 */
function destructuredFrom(source, callee, allowedMembers) {
  // 返回 { 解构到的成员集合, 是否有解构语句 }
  const members = new Set();
  let seen = false;
  const re = new RegExp(`const\\s*\\{([^}]*)\\}\\s*=\\s*${callee}\\(`, 'g');
  for (const m of source.matchAll(re)) {
    seen = true;
    for (const raw of m[1].split(',')) {
      const name = raw.trim().split(':').pop()?.trim();
      if (name && allowedMembers.includes(name)) members.add(name);
    }
  }
  return { members, seen };
}

/** 找出被 .value 读取的标识符 */
function valueReadIdentifiers(script) {
  const found = new Set();
  const cleaned = script
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/\/\/[^\n]*/g, ' ')
    .replace(/`(?:\\.|[^`\\])*`/g, '``')
    .replace(/'(?:\\.|[^'\\])*'/g, "''")
    .replace(/"(?:\\.|[^"\\])*"/g, '""');
  for (const m of cleaned.matchAll(/(^|[^\w$.])([A-Za-z_$][\w$]*)\s*\.\s*value\b/g)) {
    found.add(m[2]);
  }
  return found;
}

/** 取出 <script> 或 <script setup> 的内容（去掉标签本身） */
function scriptOf(source) {
  const m = source.match(/<script[^>]*>([\s\S]*?)<\/script>/);
  return m ? m[1] : '';
}

/** setup() 的 return { … } 里暴露出去的名字 */
function setupReturned(source) {
  // 从最后一个 `return {` 开始（setup 的返回通常在末尾）
  const idx = source.lastIndexOf('return {');
  if (idx < 0) return new Set();
  // 简单括号配平，取到匹配的 }
  let depth = 0;
  let end = -1;
  for (let i = source.indexOf('{', idx); i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') {
      depth--;
      if (depth === 0) { end = i; break; }
    }
  }
  if (end < 0) return new Set();
  const body = source.slice(source.indexOf('{', idx) + 1, end);
  const names = new Set();
  // 去掉注释，避免把注释里的词当成名字
  const clean = body.replace(/\/\/[^\n]*/g, '').replace(/\/\*[\s\S]*?\*\//g, '');
  for (const raw of clean.split(',')) {
    const name = raw.trim().split(':')[0].split(/\s/)[0];
    if (name && /^[A-Za-z_$][\w$]*$/.test(name)) names.add(name);
  }
  return names;
}

const isOptionsApi = (source) => !source.includes('<script setup>') && /export default\s*\{/.test(source);

/**
 * 去掉注释后的**脚本部分**（第 99 批补齐）
 * ------------------------------------------------------------------
 * 这个文件里的检查几乎全是"关键字是否出现"，而**注释里也会出现关键字** ——
 * 于是注释能骗过检查。真实教训：给 NotFoundView 补 i18n 时，我在脚本顶部写了
 * 一段解释性注释（里面提到 `useI18n`），结果"模板用了 t() 但脚本没接 i18n"
 * 这条检查**当场失效**：去掉实现只留注释，它照样全绿。
 *
 * ⚠️ 只对 `<script>` 里的内容去注释，**不要对整份文件去注释**：
 * 模板里有 HTML 注释，而模板中的 markdown/代码片段可能自带块注释的起止符号；
 * 一旦前者在前、后者在后（实测 DetectView / UserProfileView 就是这样），
 * 贪婪匹配会把中间**上万字符**的模板连同后面的 i18n 接线代码一起吃掉 ——
 * 于是三个明明正确接线的组件被误报成"没接 i18n"。
 */
function stripComments(code) {
  return code
    .replace(/\/\*[\s\S]*?\*\//g, ' ')   // 块注释
    .replace(/\/\/[^\n]*/g, ' ');        // 行注释
}

/** 组件脚本（`<script>` 或 `<script setup>` 的内部），已去注释 */
function codeOf(source) {
  return stripComments(scriptOf(source));
}

/** 是否接了 i18n（`useI18n()`）—— 只看脚本，避免注释里出现关键字就误判 */
function usesI18n(source) {
  return codeOf(source).includes('useI18n');
}

/**
 * 模板里用了 `t(...)`，但脚本里**根本没接 i18n**（第 99 批新增）
 * ------------------------------------------------------------------
 * 真实事故：`NotFoundView.vue` 的模板写着 `t('notFound.title')`，
 * 但它是 `<script setup>` 且**没有** `const { t } = useI18n()` ——
 * 于是 404 页自己抛 `TypeError: _ctx.t is not a function`，用户看到的是**一片空白**，
 * 连"页面不存在"都看不到。任何拼错的地址都会撞上它。
 *
 * 为什么原来的检查抓不到：那道检查（"setup 里定义了但没 return"）有
 * `if (!usesI18n(source)) continue` 的前置条件 —— 它只覆盖"接了 i18n 的组件"。
 * 这条新检查补上另一半：**模板用了 t，脚本就必须接 i18n**。
 */
function templateUsesT(source) {
  const tpl = templateOf(source);
  return /\bt\s*\(/.test(tpl);
}

/**
 * 脚本里是否**真的拿到了 `t`**（两种合法写法都算）
 *   · `const { t } = useI18n()` —— 组件内用法（本项目主流）
 *   · `import { t } from '@/i18n'` —— 模块级用法（例如 LanguageSwitcher 的全局切换按钮）
 */
function scriptHasT(source) {
  const code = codeOf(source);
  if (code.includes('useI18n')) return true;
  return /import\s*\{[^}]*\bt\b[^}]*\}\s*from\s*['"]@\/i18n['"]/.test(code);
}

describe('组件 i18n 接线', () => {
  it('options API 的组件必须把 t 放进 setup 的 return（否则运行时 _ctx.t is not a function）', () => {
    const problems = [];

    for (const path of walk(SRC)) {
      const source = readFileSync(path, 'utf8');
      if (!usesI18n(source)) continue;                  // 没接多语言，跳过
      if (source.includes('<script setup>')) continue;  // ① 写法：自动暴露
      if (!isOptionsApi(source)) continue;              // 不是 options API

      const usesT = /\bt\(/.test(source);
      if (!usesT) continue;

      const returnsT = /return\s*\{[^}]*[\s,{]t[\s,}]/.test(source) || /return\s*\{[^}]*\bt\b[^}]*\}/.test(source);
      if (!returnsT) {
        problems.push(relative(SRC, path));
      }
    }

    expect(problems, `以下组件用了 t() 但没有从 setup 返回 t：\n${problems.join('\n')}`).toEqual([]);
  });

  it('setup 里定义、模板里用到的标识符必须全部 return（第 71 批事故回归）', () => {
    const problems = [];

    for (const path of walk(SRC)) {
      const source = readFileSync(path, 'utf8');
      if (source.includes('<script setup>')) continue;  // 自动暴露
      if (!isOptionsApi(source)) continue;

      const tpl = templateOf(source);
      if (!tpl) continue;

      const locals = scopeLocals(tpl);
      const used = templateIdentifiers(tpl, locals);
      const declared = setupDeclarations(source);
      const returned = setupReturned(source);

      // 只看"在 setup 里确实定义过"的名字：那才是漏 return，而不是模板写错
      const leaked = [...used].filter((name) => declared.has(name) && !returned.has(name));
      if (leaked.length) {
        problems.push(`${relative(SRC, path)} -> ${leaked.sort().join(', ')}`);
      }
    }

    expect(
      problems,
      `以下组件在 setup 里定义了这些名字、模板里也用到，但没有 return（运行时会 undefined）：\n${problems.join('\n')}`,
    ).toEqual([]);
  });

  it('模板里用了 t() 的组件，脚本必须真的接上 i18n（第 99 批：404 页空白回归）', () => {
    const problems = [];

    for (const path of walk(SRC)) {
      const source = readFileSync(path, 'utf8');
      if (!templateUsesT(source)) continue;
      // `$t(` 走全局属性，不需要接；只挑裸 `t(`
      const tpl = templateOf(source);
      const bareT = /(^|[^\w$.])t\s*\(/.test(tpl);
      if (!bareT) continue;
      if (scriptHasT(source)) continue;   // 已经通过 useI18n 或直接 import 拿到了 t
      problems.push(relative(SRC, path));
    }

    expect(
      problems,
      `以下组件模板里用了 t()，但脚本没有拿到 t（useI18n() 或 import { t } from '@/i18n'）：\n${problems.join('\n')}`,
    ).toEqual([]);
  });

  it('组合式 API 解构不全导致的 ReferenceError（locale is not defined 回归）', () => {
    const problems = [];

    for (const path of walk(SRC)) {
      const rel = relative(SRC, path);
      const source = readFileSync(path, 'utf8');
      const script = scriptOf(source);
      if (!script) continue;

      const valueReads = valueReadIdentifiers(script);
      if (!valueReads.size) continue;

      // ① useI18n() 解构：t / tl / locale / setLocale / locales / currentLocaleLabel
      const i18n = destructuredFrom(script, 'useI18n', [
        't', 'tl', 'locale', 'setLocale', 'locales', 'currentLocaleLabel',
      ]);
      // ② useLocalized() 解构：localizedField / useLocalizedField
      const loc = destructuredFrom(script, 'useLocalized', ['localizedField', 'useLocalizedField']);

      // 该文件是否直接 import 了 locale（模块级 ref，合法用法）
      const importsLocaleDirectly = /import\s*\{[^}]*\blocale\b[^}]*\}\s*from\s*'@\/i18n'/.test(script);

      if (valueReads.has('locale') && !importsLocaleDirectly && i18n.seen && !i18n.members.has('locale')) {
        problems.push(`${rel} -> 用了 locale.value，但 useI18n() 没解构出 locale`);
      }
      if (valueReads.has('localizedField') && loc.seen && !loc.members.has('localizedField')) {
        problems.push(`${rel} -> 用了 localizedField，但 useLocalized() 没解构出 localizedField`);
      }
      if (valueReads.has('t') && i18n.seen && !i18n.members.has('t')) {
        problems.push(`${rel} -> 用了 t，但 useI18n() 没解构出 t`);
      }
    }

    expect(
      problems,
      `以下文件的组合式 API 解构不完整（运行时会 ReferenceError）：\n${problems.join('\n')}`,
    ).toEqual([]);
  });

  it('模板里用 $t 的组件无需 return（全局属性由 i18n 插件注入）', () => {
    // 这条只是把规则写清楚：`$t` 走 app.config.globalProperties，不受上面的约束
    expect(true).toBe(true);
  });
});
