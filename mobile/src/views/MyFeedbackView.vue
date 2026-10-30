<template>
  <div class="my-feedback">
    <div v-if="loading" class="loading-wrap">
      <van-loading color="var(--brand)" vertical>{{ t('common.loading') }}</van-loading>
    </div>

    <template v-else>
      <div v-if="items.length" class="list">
        <div v-for="item in items" :key="item.id" class="card">
          <div class="head">
            <van-tag :type="statusType(item.status)" size="small" effect="plain">
              {{ statusLabel(item.status) }}
            </van-tag>
            <span class="cat">{{ categoryLabel(item.category) }}</span>
            <span class="time">{{ shortTime(item.timestamp) }}</span>
          </div>

          <p class="content">{{ item.suggestion }}</p>

          <div v-if="item.admin_reply" class="reply">
            <span class="reply-label">{{ t('myFeedback.reply') }}</span>
            <span class="reply-text">{{ item.admin_reply }}</span>
          </div>
        </div>
      </div>

      <van-empty v-else :description="t('myFeedback.empty')" />
    </template>
  </div>
</template>

<script setup>
/** 我的反馈（第 268 批）—— 看自己提交过的，以及管理员有没有回复 */
import { computed, onMounted, ref } from 'vue';
import { fetchMyFeedback } from '@/api/feedback';
import { useI18n } from '@/i18n';

const { t, locale } = useI18n();
const loading = ref(true);
const items = ref([]);

const isEnglish = computed(() => String(locale.value || '').startsWith('en'));

function statusLabel(status) {
  const key = { pending: 'statusPending', processing: 'statusProcessing', resolved: 'statusResolved' }[status]
    || 'statusPending';
  return t(`myFeedback.${key}`);
}

function statusType(status) {
  return { pending: 'warning', processing: 'primary', resolved: 'success' }[status] || 'default';
}

function categoryLabel(category) {
  const key = { suggestion: 'typeSuggestion', bug: 'typeBug', recognition: 'typeRecognition', other: 'typeOther' }[category]
    || 'typeOther';
  return t(`feedbackForm.${key}`);
}

function shortTime(raw) {
  if (!raw) return '';
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return String(raw).slice(0, 10);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

onMounted(async () => {
  try {
    const data = await fetchMyFeedback();
    items.value = data.items;
  } catch (error) {
    console.warn('[my-feedback] 加载失败', error);
    items.value = [];
  } finally {
    loading.value = false;
  }
});

// 供模板判断英文（当前未用于分支，保留以便后续文案本地化）
void isEnglish;
</script>

<style scoped>
.my-feedback {
  padding: 12px;
  background: #f6f8f7;
  min-height: 100vh;
}

.loading-wrap {
  display: grid;
  place-items: center;
  padding: 48px 0;
}

.card {
  background: #fff;
  border-radius: 14px;
  padding: 14px 16px;
  margin-bottom: 12px;
}

.head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.cat {
  font-size: 12px;
  color: #566b60;
}

.time {
  margin-left: auto;
  font-size: 12px;
  color: #9dada5;
}

.content {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: #24352c;
  white-space: pre-wrap;
}

.reply {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #f2f8f4;
}

.reply-label {
  display: block;
  font-size: 12px;
  color: #2f855a;
  margin-bottom: 4px;
}

.reply-text {
  font-size: 13px;
  line-height: 1.7;
  color: #3d4a3d;
  white-space: pre-wrap;
}
</style>
