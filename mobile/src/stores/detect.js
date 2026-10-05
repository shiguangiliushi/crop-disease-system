/**
 * 当前识别结果（移动端）
 * ----------------------------------------------------------------------------
 * 识别页拍完 → 跳结果页，两页之间需要一个"结果"载体。
 * 用 store + sessionStorage 而不是路由 query：
 *   · 结果里有症状/防治的长文本，塞进 URL 又长又难读；
 *   · 手机上"识别完切去相册/微信再切回来"很常见，浏览器回收标签页后
 *     页面会重新加载 —— 只放内存里结果就没了，得重新拍（田间条件可能已变）。
 * sessionStorage 关掉标签页即失效，不会长期占空间；图片只存服务器地址，不存 base64。
 */
import { defineStore } from 'pinia';
import { ref } from 'vue';

const STORAGE_KEY = 'mobile_last_result';
const MAX_AGE_MS = 2 * 60 * 60 * 1000; // 超过 2 小时不再恢复：田间情况可能已变

function loadPersisted() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw);
    if (!saved?.disease || Date.now() - (saved.savedAt || 0) > MAX_AGE_MS) {
      sessionStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return saved;
  } catch {
    return null;
  }
}

export const useDetectStore = defineStore('detect', () => {
  const result = ref(loadPersisted());
  const chosenFile = ref(null); // 本次识别用的原图，提交纠错反馈时要带上（不持久化）

  function setResult(next) {
    result.value = next;
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ ...next, savedAt: Date.now() }));
    } catch (error) {
      console.warn('[detect] 结果持久化失败:', error?.message || error);
    }
  }

  function setChosenFile(file) {
    chosenFile.value = file;
  }

  function clear() {
    result.value = null;
    chosenFile.value = null;
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* 忽略 */
    }
  }

  return { result, chosenFile, setResult, setChosenFile, clear };
});
