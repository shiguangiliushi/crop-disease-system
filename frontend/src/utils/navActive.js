/**
 * 导航高亮判定（第 74 批从 App.vue 抽出来，便于单测）
 * ----------------------------------------------------------------------------
 * 为什么不用 vue-router 的 `.router-link-exact-active`：
 * 实测反馈出现"在 /history 页却亮了首页胶囊"这一类串页问题。项目里只有一处
 * 该类选择器、路由路径（`/` 与 `/history`）也不冲突，问题难以复现；但其根因
 * 是"谁被点亮"依赖框架的类匹配顺序与 HMR 残留状态，行为不够确定。
 *
 * 这里改为一条写死、可读、可测的规则：
 *   · 首页 `/`   —— 只在路径确实等于 `/` 时命中（用精确匹配，避免前缀匹配
 *                   导致首页在任何页面都被点亮；这是之前串页最可能的原因）；
 *   · 其它路径   —— 精确命中，或作为父级前缀命中：
 *                   /news/12              → 命中 /news（行业动态）
 *                   /pests/Apple___Scab   → 命中 /pests（病害百科）
 *                   /forum/post/3         → 命中 /forum（论坛交流）
 *
 * 保守之处：
 *   · `/news/create`（新增新闻）与 `/news` 同前缀 → 会命中"行业动态"，
 *     这是期望行为（它确实属于新闻模块）；
 *   · 尾斜杠 `/news/` 归一化为 `/news`；
 *   · 大小写敏感 —— 本项目路由全小写，不做额外宽容以免产生歧义。
 */

/** 归一化：去掉尾部斜杠（根路径除外） */
export function normalizePath(path) {
  const value = String(path || '/').split('?')[0].split('#')[0];
  if (value === '/') return '/';
  const trimmed = value.replace(/\/+$/, '');
  return trimmed === '' ? '/' : trimmed;
}

/**
 * 给定当前路径与导航目标，判断该导航项是否处于"当前页"状态
 * @param {string} currentPath 当前路由 path（如 '/history'）
 * @param {string} targetPath  导航项指向的 path（如 '/'、'/news'）
 */
export function isNavActive(currentPath, targetPath) {
  const current = normalizePath(currentPath);
  const target = normalizePath(targetPath);

  // 首页只认精确匹配
  if (target === '/') return current === '/';

  return current === target || current.startsWith(`${target}/`);
}

export default { isNavActive, normalizePath };
