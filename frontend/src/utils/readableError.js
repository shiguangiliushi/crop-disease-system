/**
 * 把后端错误文案"人话化"（第 165 批）
 * ============================================================================
 * 后台的 `detail` / `message` 有两种来源：
 *   · 我们自己写的**中文**提示（"未检测到图片文件"、"积分不足"…）→ 直接给用户看，很有用；
 *   · DRF / Django 的**英文技术文案**（"Authentication credentials were not provided."、
 *     "Invalid token."、"Expected a list of items but got type \"dict\"."…）→
 *     直接弹给农户等于没说，还像报错（评审意见点名）。
 *
 * 判据很简单：**含中日韩字符就用它，否则用调用方给的友好兜底**。
 * 技术原文仍留在控制台（调用方已经 console.error 过），排查不受影响。
 *
 * @param {unknown} raw 后端返回的 detail / message
 * @param {string} fallback 友好兜底文案
 */
const CJK = /[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/;

export function pickReadableMessage(raw, fallback) {
  const text = typeof raw === 'string' ? raw.trim() : '';
  if (!text) return fallback;
  if (!CJK.test(text)) return fallback;      // 英文/纯符号 → 不要弹给用户
  return text.length > 140 ? `${text.slice(0, 140)}…` : text;
}

export default pickReadableMessage;
