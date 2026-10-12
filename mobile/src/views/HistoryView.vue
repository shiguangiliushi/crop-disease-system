<template>
  <div class="page history-page">

    <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
      <div class="page-pad">
        <p v-if="total" class="muted total-line">{{ t('history.total', { count: total }) }}</p>

        <van-list
          v-model:loading="loading"
          :finished="finished"
          :finished-text="items.length ? t('history.noMore') : ''"
          :error="error"
          :error-text="t('common.networkError')"
          @load="onLoad"
        >
          <van-swipe-cell v-for="item in items" :key="item.historyId" class="record-cell">
            <div class="record" @click="openDetail(item)">
              <img class="record-thumb" :src="item.annotatedImage || item.originalImage" :alt="item.disease.name" />
              <div class="record-body">
                <p class="record-name">{{ displayName(item) }}</p>
                <p class="record-meta">
                  <van-tag :type="tagType(item)" size="mini">{{ confidence(item) }}%</van-tag>
                  <span class="record-time">{{ item.timeText || item.timestamp }}</span>
                </p>
              </div>
              <span class="record-arrow">›</span>
            </div>
            <template #right>
              <van-button square type="danger" class="record-delete" :text="t('history.delete')" @click="confirmDelete(item)" />
            </template>
          </van-swipe-cell>
        </van-list>

        <!--
          第 174 批：空状态换成 van-empty —— 之前是自定义的小方块 + 一行字 + 一个写死主色的按钮，
          在一个已经全量用 Vant 的 App 里显得像"另一个 app 拼进来的页面"。
          按钮一并改成 type="primary"（走主题变量，不再写死十六进制）。
        -->
        <van-empty v-if="!items.length && !loading" :description="t('history.empty')">
          <van-button size="small" round type="primary" @click="router.push('/detect')">
            {{ t('history.emptyAction') }}
          </van-button>
        </van-empty>
      </div>
    </van-pull-refresh>
  </div>
</template>

<script setup>
/**
 * 识别记录页（移动端）
 * ----------------------------------------------------------------------------
 * 用的是后端那套 `{data:{items,total,page,total_pages}}` 分页（见 api/history.js），
 * 不是 DRF 默认的 count/results —— 这一点在桌面端已经踩过一次坑。
 *
 * 交互取舍：手机上不做"多选批量删除"（勾选状态在小屏上很折磨人），
 * 只保留左滑删除单条，且删除前必须二次确认。
 */
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { showConfirmDialog, showFailToast, showSuccessToast } from 'vant';
import { deleteHistory, fetchHistory } from '@/api/history';
import { formatApiError } from '@/api/http';
import { useI18n } from '@/i18n';

const router = useRouter();
const { t, locale } = useI18n();

const items = ref([]);
const page = ref(0);
const total = ref(0);
const loading = ref(false);
const finished = ref(false);
const refreshing = ref(false);
const error = ref(false);

const displayName = (item) =>
  locale.value === 'en' ? item.disease.nameEn || item.disease.name : item.disease.name;

const confidence = (item) => {
  const value = item.disease.confidence || 0;
  const percent = value <= 1 ? value * 100 : value;
  return Math.max(0, Math.min(100, Math.round(percent)));
};

const tagType = (item) => {
  const percent = confidence(item);
  if (percent >= 70) return 'success';
  if (percent >= 40) return 'warning';
  return 'danger';
};

const onLoad = async () => {
  error.value = false;
  try {
    const next = page.value + 1;
    const data = await fetchHistory({ page: next, page_size: 10 });

    if (refreshing.value) items.value = [];
    items.value.push(...data.items);
    total.value = data.total;
    page.value = data.page;
    finished.value = !data.hasNext;
  } catch (err) {
    error.value = true;
    finished.value = true;
    showFailToast(formatApiError(err, t('common.networkError')));
  } finally {
    loading.value = false;
    refreshing.value = false;
  }
};

const onRefresh = () => {
  page.value = 0;
  finished.value = false;
  error.value = false;
  loading.value = true;
  items.value = [];
  onLoad();
};

const openDetail = (item) => {
  router.push(`/result/${item.historyId}`);
};

const confirmDelete = async (item) => {
  try {
    await showConfirmDialog({
      title: t('history.delete'),
      message: t('history.deleteConfirm'),
      confirmButtonColor: '#d9534f',
    });
  } catch {
    return; // 用户取消
  }

  try {
    await deleteHistory(item.historyId);
    items.value = items.value.filter((row) => row.historyId !== item.historyId);
    total.value = Math.max(0, total.value - 1);
    showSuccessToast(t('history.deleted'));
  } catch (err) {
    showFailToast(formatApiError(err, t('history.deleteFailed')));
  }
};
</script>

<style scoped>
.history-page {
  min-height: 100vh;
}

.total-line {
  margin: 4px 4px 10px;
}

.record-cell {
  margin-bottom: 10px;
  border-radius: 14px;
  overflow: hidden;
}

.record {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  padding: 12px;
  border-radius: 14px;
}

.record-thumb {
  width: 64px;
  height: 64px;
  border-radius: 10px;
  object-fit: cover;
  background: #eef2ee;
  flex: 0 0 auto;
}

.record-body {
  flex: 1;
  min-width: 0;
}

.record-name {
  margin: 0 0 6px;
  font-size: 0.98rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.record-meta {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.record-time {
  font-size: 0.78rem;
  color: #85958a;
}

.record-arrow {
  color: #b6c4b6;
  font-size: 1.3rem;
}

.record-delete {
  height: 100%;
}

</style>
