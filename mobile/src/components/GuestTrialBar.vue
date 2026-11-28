<template>
  <!-- 第 439 批：游客试用条（只在 is_guest 时出现） -->
  <div v-if="isGuest" class="trial-bar">
    <span class="trial-badge">{{ t('guest.badge') }}</span>
    <span class="trial-text" :class="{ 'is-exhausted': left === 0 }">{{ hintText }}</span>
    <router-link class="trial-cta" to="/register">{{ t('guest.register') }}</router-link>
  </div>
</template>

<script setup>
/**
 * 试用条（移动端，第 439 批）
 * ----------------------------------------------------------------------------
 * 与桌面端 `components/GuestTrialBar.vue` 同一份语义、两套样式（两端是独立工程）。
 * 手机上没有问答页，所以 `kind` 只会是 `detect`。
 */
import { computed, onMounted } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';

const props = defineProps({
  kind: { type: String, default: 'detect' },
});

const auth = useAuthStore();
const { t } = useI18n();

const isGuest = computed(() => auth.isGuest);

const left = computed(() => {
  const quota = auth.quota;
  if (!quota || quota.unlimited) return null;
  return props.kind === 'ask' ? quota.ask_left : quota.detect_left;
});

const hintText = computed(() => {
  if (left.value === null) return t('guest.hint');
  if (left.value <= 0) return `${t('guest.exhausted')} · ${t('guest.resetAt')}`;
  return t('guest.detectLeft', { n: left.value });
});

onMounted(() => {
  // 进页面拉一次真实额度：store 里可能是上一次留下的旧值
  if (isGuest.value) auth.refreshQuota();
});
</script>

<style scoped>
.trial-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: 10px 0 0;
  padding: 8px 10px;
  border-radius: 10px;
  background: #fff8e6;
  border: 1px solid #f3d79b;
  color: #7a5b16;
  font-size: 12.5px;
  line-height: 1.45;
}

.trial-badge {
  flex: none;
  padding: 1px 7px;
  border-radius: 999px;
  background: #f3d79b;
  color: #5c4510;
  font-weight: 600;
}

.trial-text {
  flex: 1 1 auto;
  min-width: 0;
}

.trial-text.is-exhausted {
  color: #b23c2b;
  font-weight: 600;
}

.trial-cta {
  flex: none;
  color: #2f6b3a;
  font-weight: 600;
  text-decoration: none;
}
</style>
