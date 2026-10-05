<template>
  <!--
    离线状态条（移动端，第 91 批）
    ------------------------------------------------------------------
    只在"断网中"或"还有照片没传上去"时出现，平时不占屏幕。
    点击立即补传；联网恢复后自动补传一次（见 utils/offlineSync.js）。

    放在底部导航上方而不是顶栏：农户单手拿手机时，拇指区在下面，
    而且顶栏在识别页已经被"拍照/相册"占满了。
  -->
  <transition name="van-slide-up">
    <div
      v-if="visible"
      class="offline-bar"
      :class="{ 'is-offline': !online }"
      @click="handleClick"
    >
      <van-icon :name="online ? 'upgrade' : 'warning-o'" />
      <span class="offline-text">{{ label }}</span>
      <van-loading v-if="syncing" size="14" color="#8a5a12" />
      <van-icon v-else-if="online && counts.pending" name="replay" />
    </div>
  </transition>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { showFailToast, showSuccessToast, showToast } from 'vant';
import { getOfflineQueue } from '@/utils/offlineStorage';
import { isBrowserOnline, syncPendingQueue } from '@/utils/offlineSync';
import { useI18n } from '@/i18n';

const { t } = useI18n();

const online = ref(isBrowserOnline());
const counts = ref({ total: 0, pending: 0, failed: 0 });
const syncing = ref(false);

const visible = computed(() => !online.value || counts.value.total > 0);

const label = computed(() => {
  if (!online.value) {
    return counts.value.pending
      ? t('offline.pendingOffline', { count: counts.value.pending })
      : t('offline.offline');
  }
  if (counts.value.pending) return t('offline.pendingSync', { count: counts.value.pending });
  if (counts.value.failed) return t('offline.failed', { count: counts.value.failed });
  return '';
});

const refreshCounts = async () => {
  try {
    counts.value = await getOfflineQueue().count();
  } catch (error) {
    console.warn('[offline] 读取队列失败:', error);
  }
};

const sync = async ({ silent = false } = {}) => {
  if (syncing.value) return;
  syncing.value = true;
  try {
    const summary = await syncPendingQueue();
    await refreshCounts();
    if (summary.offline) {
      if (!silent) showToast(summary.message);
    } else if (summary.total > 0) {
      showSuccessToast(summary.message + (summary.names.length ? `：${summary.names.join('、')}` : ''));
    }
  } catch (error) {
    console.error('[offline] 同步失败:', error);
    if (!silent) showFailToast(t('offline.syncFailed'));
  } finally {
    syncing.value = false;
  }
};

const handleClick = () => {
  if (!online.value) {
    showToast(t('offline.offlineHint'));
    return;
  }
  sync();
};

const handleOnline = async () => {
  online.value = true;
  await refreshCounts();
  // 联网恢复 → 自动补传，不需要用户点
  if (counts.value.pending) sync({ silent: true });
};

const handleOffline = () => {
  online.value = false;
  refreshCounts();
};

const handleQueueChanged = () => refreshCounts();

onMounted(() => {
  refreshCounts();
  window.addEventListener('online', handleOnline);
  window.addEventListener('offline', handleOffline);
  window.addEventListener('offline-queue-changed', handleQueueChanged);
  // 打开页面时如果在线且有积压，直接补传
  if (online.value) sync({ silent: true });
});

onUnmounted(() => {
  window.removeEventListener('online', handleOnline);
  window.removeEventListener('offline', handleOffline);
  window.removeEventListener('offline-queue-changed', handleQueueChanged);
});
</script>

<style scoped>
.offline-bar {
  position: fixed;
  left: 12px;
  right: 12px;
  /* 底部导航之上（TabBar 高约 50px + 安全区） */
  bottom: calc(env(safe-area-inset-bottom, 0px) + 58px);
  z-index: 120;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 12px;
  background: #fdf6ea;
  border: 1px solid #f0d9b0;
  color: #8a5a12;
  font-size: 0.82rem;
  font-weight: 600;
  box-shadow: 0 6px 18px rgba(19, 58, 41, 0.12);
}

.offline-bar.is-offline {
  background: #fdecea;
  border-color: #f3c9c3;
  color: #a32f22;
}

.offline-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
