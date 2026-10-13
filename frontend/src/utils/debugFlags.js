/**
 * 调试面板开关（第 188 批）
 * ============================================================================
 * ## 为什么不再用「开发模式就显示」
 *
 * 编辑帖子页顶部原来有一块「▶ 开发信息（仅开发模式显示，点开查看）」，判定是
 * `import.meta.env.DEV` —— 本意是"自测时方便"，但结果是：**只要用 `npm run dev`
 * 打开页面它就一定在**。开发时自己看还好，问题出在两种情况：
 *
 *   · 给用户/评审演示时，页面顶部挂着一条"开发信息"，看起来像没做完；
 *   · 用户自己就是用 dev server 在跑这套系统（本项目就是这么用的），
 *     于是他每次编辑帖子都会看到它，而他并不需要。
 *
 * 所以改成**显式开关**：默认不显示，要看的人才打开。
 *
 * ## 两种打开方式（都不需要改代码）
 *
 * 1. `VITE_SHOW_DEBUG_PANEL=true` 写进 `frontend/.env.development`，重启 dev server。
 *    适合"这一整轮开发我都想看"。
 *
 * 2. 浏览器控制台执行一次，然后刷新页面：
 *
 *        localStorage.setItem('dsh_debug_panel', '1')     // 打开
 *        localStorage.removeItem('dsh_debug_panel')       // 关掉
 *
 *    适合"临时看一眼"。之所以要刷新：这个值在模块加载时读一次（见下），
 *    不做响应式 —— 调试开关不值得为它引一条 watch。
 *
 * 生产构建里 `import.meta.env.DEV` 恒为 false，所以即使有人在生产环境手动写了
 * localStorage 也不会显示；开关**只在开发模式生效**。
 */

const LS_KEY = 'dsh_debug_panel';

/** 环境变量开关（可选，写进 .env.development 即生效） */
const byEnv = String(import.meta.env.VITE_SHOW_DEBUG_PANEL || '').toLowerCase() === 'true';

/** localStorage 开关（临时用；隐私模式下访问会抛错，兜住） */
function byLocalStorage() {
  try {
    return window.localStorage.getItem(LS_KEY) === '1';
  } catch {
    return false;
  }
}

/** 是否显示调试面板：**开发模式** + 上述任一开关打开 */
export const showDebugPanel = Boolean(import.meta.env.DEV) && (byEnv || byLocalStorage());

export default showDebugPanel;
