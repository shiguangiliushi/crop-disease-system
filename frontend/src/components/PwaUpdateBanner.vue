<template>
  <transition name="pwa-slide">
    <div v-if="visible" class="pwa-banner" role="status" aria-live="polite">
      <i class="fas fa-rotate-right pwa-icon" aria-hidden="true"></i>
      <span class="pwa-text">{{ t('pwa.updateReady') }}</span>
      <button type="button" class="pwa-action" @click="reloadNow">{{ t('pwa.reload') }}</button>
      <button type="button" class="pwa-close" :aria-label="t('common.close')" @click="visible = false">
        <i class="fas fa-xmark"></i>
      </button>
    </div>
  </transition>
</template>

<script setup>
/**
 * Service Worker 新版本提示（第 242 批）
 * ============================================================================
 * 现状：`public/sw.js` 已经是 `skipWaiting` + `clients.claim`，但**用户看不到任何提示** ——
 * 新版本要等用户自己关掉所有标签页再打开才会生效，中间一直跑着旧代码。
 *
 * 这个组件做两件事：
 *   1. 监听 `pwa-update-ready` 事件（由 `main.js` 在 SW 有新版本时派发）→ 显示横幅；
 *   2. 点「立即刷新」→ `postMessage('skip-waiting')` 让新 SW 接管 → 再 reload。
 *
 * ⚠️ 只在生产构建生效（SW 只在 PROD 注册）；开发环境不会有事件，横幅永远不出现。
 *    要验证 UI，可在控制台手动派发：
 *      window.dispatchEvent(new Event('pwa-update-ready'))
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const visible = ref(false)

function onReady() {
  visible.value = true
}

async function reloadNow() {
  try {
    const registration = window.__pwaRegistration
    if (registration?.waiting) {
      registration.waiting.postMessage('skip-waiting')
      // 等新 SW 接管后再刷新；拿不到 waiting 也照样刷（可能已经被别的标签页接管）
      await new Promise((resolve) => setTimeout(resolve, 300))
    }
  } catch (error) {
    console.warn('[pwa] 通知新版本失败，直接刷新', error)
  }
  window.location.reload()
}

onMounted(() => window.addEventListener('pwa-update-ready', onReady))
onBeforeUnmount(() => window.removeEventListener('pwa-update-ready', onReady))
</script>

<style scoped>
.pwa-banner {
  position: fixed;
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%);
  z-index: 4000;
  display: flex;
  align-items: center;
  gap: 12px;
  max-width: min(92vw, 520px);
  padding: 12px 16px;
  border-radius: 999px;
  background: #1f2d26;
  color: #f2f7f3;
  box-shadow: 0 12px 30px rgba(15, 31, 23, 0.28);
  font-size: 14px;
}

.pwa-icon {
  color: #7ee2b8;
}

.pwa-text {
  flex: 1;
  min-width: 0;
}

.pwa-action {
  flex-shrink: 0;
  padding: 6px 14px;
  border: none;
  border-radius: 999px;
  background: #7ee2b8;
  color: #12291d;
  font-weight: 600;
  cursor: pointer;
}

.pwa-close {
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: #9fb3a7;
  cursor: pointer;
  font-size: 14px;
}

.pwa-slide-enter-active,
.pwa-slide-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.pwa-slide-enter-from,
.pwa-slide-leave-to {
  opacity: 0;
  transform: translate(-50%, 12px);
}

@media (prefers-reduced-motion: reduce) {
  .pwa-slide-enter-active,
  .pwa-slide-leave-active {
    transition: none;
  }
}
</style>
