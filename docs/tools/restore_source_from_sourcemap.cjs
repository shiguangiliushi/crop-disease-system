/**
 * 从生产构建的 sourcemap 里还原被误伤的源文件
 * ============================================================================
 * 什么时候用
 * ----------------------------------------------------------------------------
 * 如果不小心把某个前端源文件写成了 0 字节（本项目的真实事故：用 PowerShell 的
 * `Set-Content` 写带变量的多行字符串，命令失败时**先截断再报错**），
 * 只要 `frontend/dist/assets/*.js.map` 还在，就能把当时的**原始源码**捞回来 ——
 * sourcemap 里的 `sourcesContent` 存的就是完整源码（含注释与缩进），不是压缩后的。
 *
 * ⚠️ 两个必须知道的限制
 *   1. 它还原的是**上一次生产构建时**的版本：那之后新加的改动要重新应用
 *      （git diff 帮不上忙，因为这些改动通常还没提交）；
 *   2. 要先确认 dist 不是"很久以前"的构建产物，否则会退回到很老的版本。
 *
 * 用法
 * ----------------------------------------------------------------------------
 *   cd crop-disease-system
 *   node docs/tools/restore_source_from_sourcemap.cjs src/i18n/messages.js
 *   node docs/tools/restore_source_from_sourcemap.cjs src/views/AdminUsersView.vue
 * （路径相对 `frontend/`，脚本会自己拼 `frontend/` 前缀并写回原位置。）
 *
 * 本脚本在 .js 一律被当成 ESM 的项目里必须用 `.cjs` 后缀（见 frontend/package.json
 * 的 "type": "module"）。
 *
 * 教训（比脚本本身更重要）
 * ----------------------------------------------------------------------------
 * 改源码一律用编辑工具（编辑器/补丁），**不要**用 `Set-Content` 配多行插值字符串 ——
 * 它在参数解析失败时会先把文件清空。真要批量替换，先 `git status` 确认可回滚，
 * 或者先把原文件复制一份。
 */
const fs = require('fs');
const path = require('path');

const distDir = 'crop-disease-system/frontend/dist/assets';
const target = process.argv[2];

if (!target) {
  console.error('用法: node docs/tools/restore_source_from_sourcemap.cjs <源码相对路径，如 src/i18n/messages.js>');
  process.exit(1);
}

// 兼容"从仓库根跑"与"从 frontend/ 跑"两种姿势
const distCandidates = [distDir, 'dist/assets'];
const dist = distCandidates.find((dir) => fs.existsSync(dir));
if (!dist) {
  console.error('找不到 dist/assets —— 先跑一次 `npm run build-only`（要开 sourcemap）');
  process.exit(1);
}

const maps = fs.readdirSync(dist).filter((f) => f.endsWith('.js.map'));
let restored = null;
for (const file of maps) {
  let map;
  try {
    map = JSON.parse(fs.readFileSync(path.join(dist, file), 'utf8'));
  } catch {
    continue;
  }
  const idx = (map.sources || []).findIndex((s) => s.endsWith(target));
  if (idx >= 0 && map.sourcesContent && map.sourcesContent[idx]) {
    restored = { mapFile: file, content: map.sourcesContent[idx] };
    break;
  }
}

if (!restored) {
  console.error(`没有找到包含 ${target} 的 sourcemap（它可能被打进了别的 chunk，或构建时没开 sourcemap）`);
  process.exit(1);
}

const outPath = path.join('crop-disease-system/frontend', target);
fs.writeFileSync(outPath, restored.content, 'utf8');
console.log(`已从 ${restored.mapFile} 还原 ${target}：${restored.content.length} 字符 / ${restored.content.split('\n').length} 行`);
