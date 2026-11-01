/**
 * 轻触觉反馈（第 333 批）
 *
 * ## 为什么值得加
 *
 * 农户在田里常戴手套、屏幕反光，点下去"没有反馈"会以为没点中，于是连点几下。
 * 10ms 的震动是最便宜的确认。
 *
 * ## 为什么要 try/catch + 判断
 *
 * - iOS Safari **不支持** `navigator.vibrate`（调用不报错但没有效果）；
 * - 部分安卓浏览器把它挂在 `window.navigator` 之外，直接调用会抛 TypeError；
 * - 用户可在系统里关掉触感反馈，这时不应有任何报错。
 */
export function tap() {
  try {
    if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
      navigator.vibrate(10);
    }
  } catch {
    /* 静默失败：触觉是增强体验，不该影响主流程 */
  }
}

export default { tap };
