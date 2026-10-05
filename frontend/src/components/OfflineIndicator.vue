<template>
  <!--
    离线状态指示（第 50 批）
    ------------------------------------------------------------------
    只在"断网中"或"有离线待识别任务"时出现，避免平时占地方。
    点击可立即同步；联网恢复后会自动同步一次（见 offlineSync）。
  -->
  <div v-if="visible" class="offline-chip" :class="{ 'is-offline': !online }" @click="handleClick">
    <i :class="online ? 'fas fa-cloud-arrow-up' : 'fas fa-plug-circle-xmark'"></i>
    <span class="offline-text">{{ label }}</span>
    <i v-if="online && counts.pending" class="fas fa-rotate sync-icon" :class="{ 'is-spinning': syncing }"></i>
  </div>
</template>

<script>
// 离线状态指示条。**组件说明写在模板顶部**（第 50 批），这里补两条约定：
//   1. 可见性判据是 `!online || counts.total > 0` —— 注意 total **包含失败项**，
//      也就是"只剩失败任务"时它依然显示（有意：失败项需要用户看到并处理，
//      藏起来等于让离线队列静默烂掉）。
//   2. ⚠️ summary.message 由同步层提供，本组件在它后面**拼了全角冒号与顿号**，
//      所以英文界面会出现中文标点。这是已知瑕疵（移动端同款组件也一样）。
//      要修应当让同步层返回**结构化的条目列表**，而不是在这里替换标点。
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { getOfflineQueue } from '@/utils/offlineStorage';
import { isBrowserOnline, syncPendingQueue } from '@/utils/offlineSync';
import { useI18n } from '@/i18n';  // 第 71 批：离线提示语多语言

export default {
  name: 'OfflineIndicator',
  setup() {
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
          if (!silent) ElMessage.info(summary.message);
        } else if (summary.total > 0) {
          ElMessage.success(summary.message + (summary.names.length ? `：${summary.names.join('、')}` : ''));
        }
      } catch (error) {
        console.error('[offline] 同步失败:', error);
        if (!silent) ElMessage.error(t('offline.syncFailed'));
      } finally {
        syncing.value = false;
      }
    };

    const handleClick = () => {
      if (!online.value) {
        ElMessage.info(t('offline.offlineHint'));
        return;
      }
      sync();
    };

    const handleOnline = async () => {
      online.value = true;
      await refreshCounts();
      if (counts.value.pending) {
        // 联网恢复 → 自动补传，不需要用户点
        sync({ silent: true });
      }
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

    return { online, counts, syncing, visible, label, handleClick, t };
  },
};
</script>

<style scoped>
.offline-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 12px;
  border: 1px solid #f0d9b0;
  border-radius: var(--radius-pill, 999px);
  background: #fdf6ea;
  color: #8a5a12;
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s ease;
}

.offline-chip.is-offline {
  border-color: #f3c9c3;
  background: #fdecea;
  color: #a32f22;
}

.offline-chip:hover {
  filter: brightness(0.97);
}

.sync-icon.is-spinning {
  animation: offline-spin 1s linear infinite;
}

@keyframes offline-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 768px) {
  .offline-chip {
    height: 42px;
    font-size: 12px;
    padding: 0 10px;
  }
}
</style>
