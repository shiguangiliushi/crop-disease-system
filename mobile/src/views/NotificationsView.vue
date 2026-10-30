<template>
  <div class="notify-page">
    <div class="notify-head">
      <span class="muted">{{ t('notify.unread', { n: unread }) }}</span>
      <van-button size="mini" :disabled="!unread" @click="readAll">{{ t('notify.readAll') }}</van-button>
    </div>

    <div v-if="loading" class="loading-wrap">
      <van-loading color="var(--brand)" vertical>{{ t('common.loading') }}</van-loading>
    </div>

    <template v-else>
      <van-cell-group v-if="items.length" inset class="cells">
        <van-cell
          v-for="item in items"
          :key="item.id"
          :title="titleOf(item)"
          :label="labelOf(item)"
          is-link
          @click="openItem(item)"
        >
          <template #icon>
            <span v-if="!item.is_read" class="dot"></span>
          </template>
        </van-cell>
      </van-cell-group>
      <van-empty v-else :description="t('notify.empty')" />
    </template>
  </div>
</template>

<script setup>
/** 站内通知列表（第 261 批）—— 入口在「我的」→ 系统通知 */
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { fetchNotifications, fetchUnreadCount, markAllRead } from '@/api/notify';
import { useI18n } from '@/i18n';

const router = useRouter();
const { t, locale } = useI18n();

const loading = ref(true);
const items = ref([]);
const unread = ref(0);

const isEnglish = computed(() => String(locale.value || '').startsWith('en'));

const titleOf = (item) => (isEnglish.value ? item.title_en || item.title : item.title) || '';
const labelOf = (item) => {
  const text = (isEnglish.value ? item.message_en || item.message : item.message) || '';
  return text.slice(0, 80);
};

function openItem(item) {
  if (item.url) router.push(item.url).catch(() => {});
}

async function load() {
  loading.value = true;
  try {
    const data = await fetchNotifications();
    items.value = data.items;
    unread.value = await fetchUnreadCount();
  } catch (error) {
    console.warn('[notify] 加载通知失败', error);
    items.value = [];
  } finally {
    loading.value = false;
  }
}

async function readAll() {
  try {
    await markAllRead();
    items.value = items.value.map((row) => ({ ...row, is_read: true }));
    unread.value = 0;
  } catch (error) {
    console.warn('[notify] 全部已读失败', error);
  }
}

onMounted(load);
</script>

<style scoped>
.notify-page {
  padding: 12px;
  background: #f6f8f7;
  min-height: 100vh;
}

.notify-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 4px 10px;
}

.loading-wrap {
  display: grid;
  place-items: center;
  padding: 40px 0;
}

.cells :deep(.van-cell__title) {
  font-size: 14px;
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin: 0 8px 0 2px;
  border-radius: 50%;
  background: #e05c4b;
}
</style>
