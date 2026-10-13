/**
 * 「系统」页的页签清单（第 186 批）
 * ============================================================================
 * 为什么把这段**从组件的 computed 里提出来**（而不是留在 `AdminSystemHubView.vue`）：
 *
 * 本批的核心要求是"**页签按权限显示**"，而"只有 BROADCAST、不是全权管理员"这个档位
 * 在当前系统里**双重不可达**，用浏览器 E2E **测不了**：
 *
 *   ① **后端造不出这种账号** —— `api/capabilities.py` 的 `has_capability()` 里，
 *      `is_full_admin()`（is_staff / is_superuser / role='ADMIN'）一成立就三项能力全给
 *      并提前 return；`role='EDITOR'` 无论勾满几个内容模块都只给 CONTENT；全库也没有
 *      按能力授权的表（只有内容模块的 `EditorModuleGrant`）。
 *      后端测试 `RoleMatrixTests.test_no_account_can_hold_broadcast_without_being_a_full_admin`
 *      正面固化了这条事实。
 *   ② **前端守卫也不放行** —— 管理区要求 `requiresAdmin`，而每个后台落脚页都还有自己的
 *      capability/module（数据看板要 CONTENT + 一个内容模块、系统页要 BROADCAST……）。
 *      一个 BROADCAST-only 的身份**进不了任何一页**：合成身份一进 `/admin/**` 就被弹回
 *      农户首页，`waitForSelector('.admin-console')` 等不到东西（第 186 批实测，
 *      第一版就是这么超时的 —— 用浏览器去测一个"进不去后台"的身份没有意义）。
 *
 * 所以这里把"**给定权限，算出哪几个页签**"写成**纯函数**：不依赖 Vue、不依赖网络、
 * 不依赖账号，单测可以直接覆盖三种身份（见 `src/views/__tests__/admin-system-tabs.spec.js`）。
 * 组件只负责把返回的名字映射成文案/图标/面板组件。
 *
 * ⚠️ 这条口径与后端**同源**，改动请两边一起看：
 *   · `health` / `audit` → 仅全权管理员（`/api/admin/health/`、`/api/admin/audit-logs/`
 *     是 `is_full_admin`）；
 *   · `boards` → 全权管理员**或** `BROADCAST`（`/api/forums/boards/` 写接口是
 *     `IsBroadcastManager`）。
 *
 * 页签按权限显示是**为将来"按能力授权"预留的防御性设计**：哪天后端真的能造出
 * BROADCAST-only 的账号，这里的单测与后端那条测试会同时提醒"一起改"。
 */

/** 系统健康（仅全权管理员） */
export const TAB_HEALTH = 'health';
/** 操作日志（仅全权管理员） */
export const TAB_AUDIT = 'audit';
/** 版块管理（全权管理员 或 BROADCAST） */
export const TAB_BOARDS = 'boards';

/**
 * 按权限算出可见的页签名字（顺序即默认落点）
 *
 * @param {{ isAdmin?: boolean, hasBroadcast?: boolean }} auth
 *   `isAdmin` = 全权管理员（组件里传 `authStore.isAdmin`）；
 *   `hasBroadcast` = 有 `BROADCAST` 能力（组件里传 `hasCapability(CAP_BROADCAST)`）。
 *   ⚠️ 两者都写出来是有意的：后端 `has_capability()` 对全权管理员恒为 True，
 *   所以"BROADCAST 或全权管理员"在数据上等价于"有 BROADCAST"，但读代码的人
 *   一眼能看出这一档**不是**只有能力，避免下一个人以为漏判了管理员。
 * @returns {string[]} 例如全权管理员 `['health','audit','boards']`、
 *   只有 BROADCAST `['boards']`、两者都没有 `[]`
 */
export function adminSystemTabs({ isAdmin = false, hasBroadcast = false } = {}) {
  const tabs = [];
  if (isAdmin) tabs.push(TAB_HEALTH, TAB_AUDIT);
  if (isAdmin || hasBroadcast) tabs.push(TAB_BOARDS);
  return tabs;
}
