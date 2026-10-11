<template>
  <!--
    离线状态指示 + **队列面板**（第 50 批做指示；第 162 批做成可处理）
    ------------------------------------------------------------------
    只在"断网中"或"队列里有任务"时出现，避免平时占地方。

    ⚠️ 第 162 批为什么必须补一个面板：
      原来的交互是「点一下 = 立即同步」，而同步只处理 **pending** 项；
      一条任务失败 3 次后被标记为 `failed`，既不再自动重试、点一下也毫无反应 ——
      页眉上只会永远挂着一个「2 张同步失败」，用户既不知道是哪两张、
      也不知道为什么失败、更没法重试或丢掉它（用户截图问的就是这个）。
      现在点开就能看到每一条的文件名/入队时间/失败原因/已试次数，并能逐条重试、丢弃。
  -->
  <el-popover
    v-if="visible"
    placement="bottom-end"
    :width="380"
    trigger="click"
    popper-class="offline-popover"
  >
    <template #reference>
      <button type="button" class="offline-chip" :class="{ 'is-offline': !online }">
        <i :class="online ? 'fas fa-cloud-arrow-up' : 'fas fa-plug-circle-xmark'"></i>
        <span class="offline-text">{{ label }}</span>
        <i
          v-if="online && counts.pending"
          class="fas fa-rotate sync-icon"
          :class="{ 'is-spinning': syncing }"
        ></i>
      </button>
    </template>

    <div class="offline-panel">
      <h4>{{ t('offline.panelTitle') }}</h4>
      <p class="panel-hint">{{ t('offline.panelHint') }}</p>

      <!-- 待同步 -->
      <div v-if="counts.pending" class="panel-row">
        <span class="row-main">
          <i class="fas fa-hourglass-half"></i>
          {{ t('offline.pendingSync', { count: counts.pending }) }}
        </span>
        <el-button size="small" type="primary" :loading="syncing" @click="sync()">
          {{ t('offline.syncNow') }}
        </el-button>
      </div>

      <!-- 失败项：逐条列出来，能重试也能丢弃 -->
      <div v-if="failedItems.length" class="panel-failed">
        <p class="panel-subtitle">
          <i class="fas fa-triangle-exclamation"></i>
          {{ t('offline.failedTitle', { count: failedItems.length }) }}
        </p>
        <ul class="failed-list">
          <li v-for="item in failedItems" :key="item.id">
            <div class="failed-meta">
              <b>{{ item.filename || t('offline.unnamed') }}</b>
              <span>{{ formatTime(item.createdAt) }}</span>
            </div>
            <div class="failed-reason">
              {{ t('offline.triedTimes', { count: item.tries || 0 }) }}
              <template v-if="item.lastError"> · {{ item.lastError }}</template>
            </div>
            <div class="failed-actions">
              <el-button size="small" text @click="retryOne(item.id)">
                {{ t('offline.retryOne') }}
              </el-button>
              <el-button size="small" text type="danger" @click="dropOne(item.id)">
                {{ t('offline.dropOne') }}
              </el-button>
            </div>
          </li>
        </ul>
        <div class="panel-foot">
          <el-button size="small" @click="retryAll">{{ t('offline.retryAll') }}</el-button>
          <el-button size="small" type="danger" plain @click="dropAll">
            {{ t('offline.dropAll') }}
          </el-button>
        </div>
      </div>

      <p v-if="!counts.total" class="panel-empty">{{ t('offline.queueEmpty') }}</p>
    </div>
  </el-popover>
</template>

<script>
// 离线状态指示条。**组件说明写在模板顶部**（第 50 批），这里补两条约定：
//   1. 可见性判据是 `!online || counts.total > 0` —— 注意 total **包含失败项**，
//      也就是"只剩失败任务"时它依然显示（有意：失败项需要用户看到并处理，
//      藏起来等于让离线队列静默烂掉）。
//   2. ⚠️ summary.message 由同步层提供，本组件在它后面**拼了全角冒号与顿号**，
//      所以英文界面会出现中文标点。这是已知瑕疵（移动端同款组件也一样）。
//      要修应当让同步层返回**结构化的条目列表**，而不是在这里替换标点。
//      （第 162 批的面板已经是结构化的：文件名与失败原因分开渲染，不再拼标点。）
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getOfflineQueue } from '@/utils/offlineStorage';
import { isBrowserOnline, syncPendingQueue } from '@/utils/offlineSync';
import { useI18n } from '@/i18n';  // 第 71 批：离线提示语多语言
import { formatTime } from '@/utils/date';

export default {
  name: 'OfflineIndicator',
  setup() {
    const { t } = useI18n();
    const online = ref(isBrowserOnline());
    const counts = ref({ total: 0, pending: 0, failed: 0 });
    const failedItems = ref([]);
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
        const queue = getOfflineQueue();
        counts.value = await queue.count();
        // 失败项要摆出来给用户处理（第 162 批）
        failedItems.value = await queue.failed();
      } catch (error) {
        console.warn('[offline] 读取队列失败:', error);
      }
    };

    /** 通知其它地方（移动端同款组件、识别页）队列变了 */
    const notifyChanged = () => {
      window.dispatchEvent(new CustomEvent('offline-queue-changed'));
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

    // 第 162 批：失败项的处理入口
    const retryOne = async (id) => {
      await getOfflineQueue().retry(id);
      notifyChanged();
      await refreshCounts();
      ElMessage.info(t('offline.retryQueued'));
      if (online.value) await sync();
    };

    const dropOne = async (id) => {
      try {
        await ElMessageBox.confirm(t('offline.dropConfirm'), t('offline.dropConfirmTitle'), {
          type: 'warning',
          confirmButtonText: t('common.confirm'),
          cancelButtonText: t('common.cancel'),
        });
      } catch {
        return;   // 用户取消
      }
      await getOfflineQueue().remove(id);
      notifyChanged();
      await refreshCounts();
      ElMessage.success(t('offline.dropped'));
    };

    const retryAll = async () => {
      const count = await getOfflineQueue().retryAllFailed();
      notifyChanged();
      await refreshCounts();
      ElMessage.info(t('offline.retryQueuedCount', { count }));
      if (online.value) await sync();
    };

    const dropAll = async () => {
      if (!failedItems.value.length) return;
      try {
        await ElMessageBox.confirm(
          t('offline.dropAllConfirm', { count: failedItems.value.length }),
          t('offline.dropConfirmTitle'),
          { type: 'warning', confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel') },
        );
      } catch {
        return;
      }
      const queue = getOfflineQueue();
      for (const item of failedItems.value) {
        await queue.remove(item.id);
      }
      notifyChanged();
      await refreshCounts();
      ElMessage.success(t('offline.dropped'));
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

    return {
      t,
      online,
      counts,
      failedItems,
      syncing,
      visible,
      label,
      sync,
      retryOne,
      dropOne,
      retryAll,
      dropAll,
      formatTime,
    };
  },
};
</script>

<style scoped>
.offline-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--el-color-warning-light-5, #f3d19e);
  border-radius: 999px;
  background: var(--el-color-warning-light-9, #fdf6ec);
  color: var(--el-color-warning-dark-2, #b88230);
  font-size: 12px;
  line-height: 1.6;
  cursor: pointer;
  white-space: nowrap;
}

.offline-chip.is-offline {
  border-color: var(--el-color-info-light-5, #c8c9cc);
  background: var(--el-color-info-light-9, #f4f4f5);
  color: var(--el-color-info-dark-2, #909399);
}

.sync-icon.is-spinning {
  animation: offline-spin 1s linear infinite;
}

@keyframes offline-spin {
  to { transform: rotate(360deg); }
}

.offline-panel h4 {
  margin: 0 0 6px;
  font-size: 14px;
}

.panel-hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--ink-400, #9dada5);
  line-height: 1.6;
}

.panel-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.row-main {
  font-size: 13px;
}

.panel-subtitle {
  margin: 6px 0;
  font-size: 13px;
  color: var(--el-color-warning-dark-2, #b88230);
}

.failed-list {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 260px;
  overflow-y: auto;
}

.failed-list li {
  padding: 8px 0;
  border-top: 1px dashed var(--el-border-color-lighter, #ebeef5);
}

.failed-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
}

.failed-meta span {
  color: var(--ink-400, #9dada5);
  font-size: 12px;
}

.failed-reason {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-color-danger, #f56c6c);
  word-break: break-all;
}

.failed-actions {
  display: flex;
  gap: 6px;
  margin-top: 2px;
}

.panel-foot {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.panel-empty {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--ink-400, #9dada5);
}
</style>

