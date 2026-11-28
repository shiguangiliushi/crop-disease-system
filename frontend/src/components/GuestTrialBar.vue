<template>
  <!-- 第 439 批：游客试用条（只在 is_guest 时出现） -->
  <div v-if="isGuest" class="guest-bar" role="status">
    <span class="guest-badge">
      <i class="fas fa-flask"></i>
      {{ t('guest.badge') }}
    </span>
    <span class="guest-text" :class="{ 'is-exhausted': left === 0 }">{{ hintText }}</span>
    <router-link class="guest-cta" to="/register">{{ t('guest.registerCta') }}</router-link>
  </div>
</template>

<script>
import { computed, onMounted } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { t } from '@/i18n';

/**
 * 试用条（第 439 批）
 * ------------------------------------------------------------------
 * 为什么做成组件而不是各页各写一段：
 * 识别页与问答页都要显示"还剩几次"，而次数只来自 `authStore.quota` ——
 * 两处各写一遍，迟早出现"识别页说还剩 2 次、问答页说还剩 3 次"。
 *
 * `kind` 决定显示哪一种额度（detect / ask）。
 */
export default {
  name: 'GuestTrialBar',
  props: {
    kind: {
      type: String,
      default: 'detect',
      validator: (value) => ['detect', 'ask'].includes(value),
    },
  },
  setup(props) {
    const auth = useAuthStore();
    const isGuest = computed(() => auth.isGuest);

    const left = computed(() => {
      const quota = auth.quota;
      if (!quota || quota.unlimited) return null;
      return props.kind === 'ask' ? quota.ask_left : quota.detect_left;
    });

    const hintText = computed(() => {
      if (left.value === null) return t('guest.hint');
      if (left.value <= 0) return `${t('guest.exhausted')} · ${t('guest.resetAt')}`;
      return t(props.kind === 'ask' ? 'guest.askLeft' : 'guest.detectLeft', { n: left.value });
    });

    onMounted(() => {
      // 进页面就把真实额度拉一次：store 里可能是上一个页面留下的旧值
      if (isGuest.value) auth.refreshQuota();
    });

    return { isGuest, left, hintText, t };
  },
};
</script>

<style scoped>
.guest-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin: 0 0 1rem;
  padding: 0.55rem 0.9rem;
  border-radius: 10px;
  background: #fff8e6;
  border: 1px solid #f3d79b;
  color: #7a5b16;
  font-size: 0.86rem;
  line-height: 1.5;
}

.guest-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  background: #f3d79b;
  color: #5c4510;
  font-weight: 600;
  white-space: nowrap;
}

.guest-text {
  color: #7a5b16;
}

.guest-text.is-exhausted {
  color: #b23c2b;
  font-weight: 600;
}

.guest-cta {
  margin-left: auto;
  color: #2f6b3a;
  font-weight: 600;
  text-decoration: none;
  white-space: nowrap;
}

.guest-cta:hover {
  text-decoration: underline;
}
</style>
