/**
 * 轻触觉反馈（第 333 批，uni-app 版）
 *
 * uni 用 `uni.vibrateShort()`；在 H5 里它内部也是调 `navigator.vibrate`，
 * 所以 iOS Safari 上同样无效 —— 失败时静默，不影响点击。
 */
export function tap() {
  try {
    if (typeof uni !== 'undefined' && typeof uni.vibrateShort === 'function') {
      uni.vibrateShort({ type: 'light' });
    }
  } catch {
    /* 静默 */
  }
}

export default { tap };
