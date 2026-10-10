/**
 * 检查：每个路由都有对应的 `docTitle.<路由名>` 文案
 * ============================================================================
 * 起因（第 152 批）：`docTitle` 是**按路由名动态查**的
 * （`src/router/index.js` 里 `docTitle.${routeName}`），所以缺键时
 * **不会报错**，只在浏览器控制台留一句 `[i18n] 缺少文案：docTitle.admin-comments`
 * —— 页面照常能开，标签页标题却回退成默认值。
 * 第 147/148/149 批新加的评论管理/操作日志/论坛管理三页就这么漏了三个键，
 * 直到跑端到端时才在控制台里看到。
 *
 * 这个脚本把"每条路由都要有 docTitle"变成一条**可执行的检查**，接进 `npm run check`。
 *
 * 用法：node scripts/check-doc-titles.mjs
 * 退出码：0 = 全部有；1 = 有缺失（并列出是哪几条路由）
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const root = path.resolve(import.meta.dirname, '..');
const routerFile = path.join(root, 'src', 'router', 'index.js');
const messagesFile = path.join(root, 'src', 'i18n', 'messages.js');

const routerSource = fs.readFileSync(routerFile, 'utf8');
// 路由表里的 `name: 'xxx',` —— 只匹配行首带缩进的写法，避免把别处的 name 抓进来
const routeNames = [...routerSource.matchAll(/^\s*name: '([^']+)',/gm)].map((m) => m[1]);

const { zhCN, en } = await import(pathToFileURL(messagesFile).href);
const missingZh = routeNames.filter((name) => zhCN.docTitle?.[name] === undefined);
const missingEn = routeNames.filter((name) => en.docTitle?.[name] === undefined);

console.log(`检查 ${routeNames.length} 条路由的 docTitle 文案`);

if (missingZh.length || missingEn.length) {
  console.error('\n❌ 以下路由缺少 docTitle 文案（标签页标题会回退成默认值）：');
  for (const name of missingZh) console.error(`   · ${name}（中文缺）`);
  for (const name of missingEn) console.error(`   · ${name}（英文缺）`);
  console.error('\n补法：在 messages.js 的 docTitle 命名空间里加上同名键（中英各一条）。');
  process.exit(1);
}

console.log('✅ 每条路由都有 docTitle 文案（中英齐全）');
