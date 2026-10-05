<template>
  <!-- 私信入口（第 42 批）：图标 + 未读红点，点击进私信页 -->
  <RouterLink to="/messages" class="message-entry" :title="unread > 0 ? t('messages.unreadCount', { count: unread }) : t('messages.title')">
    <i class="fas fa-envelope"></i>
    <span v-if="unread > 0" class="message-badge">{{ unread > 99 ? '99+' : unread }}</span>
  </RouterLink>
</template>

<script>
import { onMounted, onUnmounted, ref } from 'vue';
import { RouterLink } from 'vue-router';
import { fetchMessageUnreadCount } from '@/api/message';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';  // 第 70 批：多语言（修复 _ctx.t is not a function）

export default {
  name: 'MessageEntry',
  components: { RouterLink },
  setup() {
    const { t } = useI18n();  // 必须放在 setup 内并 return，模板才能拿到
    const authStore = useAuthStore();
    const unread = ref(0);
    let timer = null;

    const load = async () => {
      if (!authStore.isAuthenticated) {
        unread.value = 0;
        return;
      }
      try {
        const data = await fetchMessageUnreadCount();
        unread.value = data?.unread || 0;
      } catch (error) {
        // 私信是附加功能，失败不打扰用户
        console.warn('获取未读私信数失败:', error);
      }
    };

    onMounted(() => {
      load();
      // 与通知铃铛一致：每 60 秒轮询，页面不可见时跳过
      timer = setInterval(() => {
        if (document.visibilityState === 'visible') load();
      }, 60000);
    });

    onUnmounted(() => {
      if (timer) clearInterval(timer);
    });

    return { unread, t };
  },
};
</script>

<style scoped>
.message-entry {
  position: relative;
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border, #e2ebe5);
  border-radius: 50%;
  background: var(--surface, #fff);
  color: var(--ink-600, #566b60);
  font-size: 15px;
  text-decoration: none;
  transition: all 0.2s ease;
}

.message-entry:hover {
  border-color: var(--brand-400, #5fb088);
  color: var(--brand-700, #1f6343);
}

.message-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: #3d7ea6;
  color: #fff;
  font-size: 10.5px;
  font-weight: 700;
  line-height: 1;
  box-shadow: 0 0 0 2px #fff;
}

/* 第 45 批（移动端）：放大到触屏友好的 42px */
@media (max-width: 768px) {
  .message-entry {
    width: 42px;
    height: 42px;
    font-size: 17px;
  }
}
</style>
