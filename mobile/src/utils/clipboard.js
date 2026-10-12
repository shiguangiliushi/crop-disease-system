/**
 * 复制文本到剪贴板（第 176 批）
 * ============================================================================
 * ## 为什么不能只写 `navigator.clipboard.writeText`
 *
 * Clipboard API 只在**安全上下文**可用：`https://` 或 `localhost`。
 * 而农户手机上打开的是 `http://192.168.x.x:5174`（局域网 IP + HTTP）——
 * 浏览器会认为"不安全"，`navigator.clipboard` 直接是 `undefined` ✗。
 * 只写那一行的话，**电脑上测得好好的，到手机上点了没反应**。
 *
 * 所以这里按可靠性分三层：
 *   1. `navigator.clipboard.writeText`（HTTPS / localhost）；
 *   2. 隐藏 textarea + `document.execCommand('copy')`（老办法，HTTP 下多数手机浏览器仍可用）；
 *   3. 都失败 → 返回 false，由调用方**把文案显示出来**让用户长按复制
 *      （宁可多一步，也不能"点了没反应"）。
 *
 * @param {string} text
 * @returns {Promise<boolean>} 是否复制成功
 */
export async function copyText(text) {
  const value = String(text ?? '');
  if (!value) return false;

  // ① 标准 API（安全上下文才有）
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch (error) {
    // 用户拒绝授权、或页面失焦都会抛 —— 继续走回退，不打扰用户
    console.warn('[clipboard] Clipboard API 不可用，改用回退方案:', error?.message || error);
  }

  // ② 老办法：临时 textarea + execCommand
  try {
    const area = document.createElement('textarea');
    area.value = value;
    // 放在视口内但不可见：iOS 上 display:none / visibility:hidden 会选不中
    area.setAttribute('readonly', 'readonly');
    area.style.position = 'fixed';
    area.style.top = '0';
    area.style.left = '0';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.focus();
    area.select();
    area.setSelectionRange(0, value.length);
    const ok = document.execCommand('copy');
    document.body.removeChild(area);
    if (ok) return true;
  } catch (error) {
    console.warn('[clipboard] execCommand 复制失败:', error?.message || error);
  }

  // ③ 交给调用方兜底（弹窗展示文案）
  return false;
}

export default copyText;
