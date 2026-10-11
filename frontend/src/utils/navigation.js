/**
 * 返回上一页（带兜底）—— 第 165 批
 * ============================================================================
 * ## 为什么不能直接用 `router.go(-1)`
 *
 * 农户经常是**从别人分享的链接**直接打开某个页面（帖子详情、新闻、个人信息…）。
 * 这种情况下浏览器历史里**没有"上一页"**，`router.go(-1)` 的后果是：
 *   · 什么也不发生（用户以为按钮坏了）；
 *   · 或者跳出本站，回到上一个无关页面（更让人困惑）。
 *
 * ## 判据
 *
 * vue-router 4 会在 `history.state.back` 里维护"上一个路由"。
 * 它是 `null` 就说明是**直接进入**的（新标签页、分享链接、书签），
 * 这时改用调用方给的兜底地址 —— 例如帖子详情、论坛列表、首页。
 *
 * @param {string|object} fallback 没有上一页时去哪里（同 `router.push` 的入参）
 */
import router from '@/router';

export function goBackOr(fallback = '/') {
  const hasPrevious = Boolean(window.history?.state?.back);
  if (hasPrevious) {
    router.back();
    return;
  }
  router.push(fallback);
}

export default goBackOr;
