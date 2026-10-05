<template>
  <!-- 通知铃铛（第 37 批新增）：未读红点 + 下拉最近通知 -->
  <div ref="rootRef" class="notify-bell">
    <button
      type="button"
      class="bell-btn"
      :class="{ 'has-unread': unread > 0 }"
      :title="unread > 0 ? t('notify.unreadCount', { count: unread }) : t('notify.title')"
      @click="toggle"
    >
      <i class="fas fa-bell"></i>
      <span v-if="unread > 0" class="bell-badge">{{ unread > 99 ? '99+' : unread }}</span>
    </button>

    <transition name="notify-fade">
      <div v-if="open" class="bell-panel" @click.stop>
        <header class="bell-panel-head">
          <strong>{{ t('notify.title') }}</strong>
          <span v-if="unread > 0" class="bell-unread">{{ t('notify.unreadShort', { count: unread }) }}</span>
          <button v-if="unread > 0" type="button" class="bell-mark-all" @click="markAll">
            {{ t('notify.markAllShort') }}
          </button>
        </header>

        <div class="bell-list">
          <el-skeleton v-if="loading && items.length === 0" :rows="4" animated />

          <template v-else-if="items.length">
            <RouterLink
              v-for="item in items"
              :key="item.id"
              :to="item.url || '/notifications'"
              class="bell-item"
              :class="{ 'is-unread': !item.is_read }"
              @click="onItemClick(item)"
            >
              <span class="bell-item-icon" :class="`is-${item.type}`">
                <i :class="iconOf(item.type)"></i>
              </span>
              <span class="bell-item-body">
                <span class="bell-item-title">{{ localizedField(item, 'title') }}</span>
                <span v-if="item.message" class="bell-item-msg">{{ localizedField(item, 'message') }}</span>
                <span class="bell-item-time">{{ relativeTime(item.created_at) }}</span>
              </span>
            </RouterLink>
          </template>

          <p v-else class="bell-empty">
            <i class="fas fa-bell-slash"></i> {{ t('notify.emptyShort') }}
          </p>
        </div>

        <footer class="bell-panel-foot">
          <RouterLink to="/notifications" @click="open = false">{{ t('notify.viewAll') }}</RouterLink>
        </footer>
      </div>
    </transition>
  </div>
</template>

<script>
/**
 * 通知铃铛（第 37 批）
 * ------------------------------------------------------------------
 * 放在顶栏用户区左侧：显示未读数、点开是最近 5 条通知、可一键全部已读。
 * 未读数每 60 秒轮询一次（登录状态下），页面不可见时不轮询（省流量）。
 */
import { onMounted, onUnmounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { fetchNotifications, fetchUnreadCount, markAllNotificationsRead, markNotificationRead } from '@/api/notify';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';  // 第 70 批：多语言（修复 _ctx.t is not a function）
import { useLocalized } from '@/utils/localized';  // 第 72 批：通知标题英文内容

const ICONS = {
  reply: 'fas fa-comment-dots',
  like: 'fas fa-thumbs-up',
  favorite: 'fas fa-bookmark',
  comment_like: 'fas fa-heart',
  follow: 'fas fa-user-plus',
  message: 'fas fa-envelope',
  announcement: 'fas fa-bullhorn',
  system: 'fas fa-circle-info',
};

export default {
  name: 'NotificationBell',
  setup() {
    const { t } = useI18n();  // 必须放在 setup 内并 return，模板才能拿到
    const { localizedField } = useLocalized();
    const authStore = useAuthStore();
    const router = useRouter();

    const rootRef = ref(null);
    const open = ref(false);
    const loading = ref(false);
    const unread = ref(0);
    const items = ref([]);
    let timer = null;

    const iconOf = (type) => ICONS[type] || ICONS.system;

    const relativeTime = (value) => {
      if (!value) return '';
      const diff = Date.now() - new Date(value).getTime();
      const minutes = Math.floor(diff / 60000);
      if (minutes < 1) return t('notify.justNow');
      if (minutes < 60) return t('notify.minutesAgo', { count: minutes });
      const hours = Math.floor(minutes / 60);
      if (hours < 24) return t('notify.hoursAgo', { count: hours });
      const days = Math.floor(hours / 24);
      if (days < 30) return t('notify.daysAgo', { count: days });
      return new Date(value).toLocaleDateString();
    };

    const loadUnread = async () => {
      if (!authStore.isAuthenticated) {
        unread.value = 0;
        return;
      }
      try {
        const data = await fetchUnreadCount();
        unread.value = data?.unread || 0;
      } catch (error) {
        // 通知是"锦上添花"的功能，失败不打扰用户
        console.warn('获取未读通知数失败:', error);
      }
    };

    const loadItems = async () => {
      loading.value = true;
      try {
        const data = await fetchNotifications({ page_size: 5 });
        items.value = data?.results || [];
      } catch (error) {
        console.warn('获取通知列表失败:', error);
        items.value = [];
      } finally {
        loading.value = false;
      }
    };

    const toggle = async () => {
      open.value = !open.value;
      if (open.value) {
        await Promise.all([loadItems(), loadUnread()]);
      }
    };

    const onItemClick = async (item) => {
      open.value = false;
      if (!item.is_read) {
        try {
          await markNotificationRead(item.id);
          unread.value = Math.max(0, unread.value - 1);
          item.is_read = true;
        } catch (error) {
          console.warn('标记已读失败:', error);
        }
      }
    };

    const markAll = async () => {
      try {
        await markAllNotificationsRead();
        unread.value = 0;
        items.value = items.value.map((item) => ({ ...item, is_read: true }));
      } catch (error) {
        console.warn('全部已读失败:', error);
      }
    };

    const onDocumentClick = (event) => {
      if (open.value && rootRef.value && !rootRef.value.contains(event.target)) {
        open.value = false;
      }
    };

    onMounted(() => {
      loadUnread();
      document.addEventListener('click', onDocumentClick);
      timer = setInterval(() => {
        if (document.visibilityState === 'visible') loadUnread();
      }, 60000);
    });

    onUnmounted(() => {
      document.removeEventListener('click', onDocumentClick);
      if (timer) clearInterval(timer);
    });

    return { t, localizedField, rootRef, open, loading, unread, items, iconOf, relativeTime, toggle, onItemClick, markAll, router };
  },
};
</script>

<style scoped>
.notify-bell {
  position: relative;
  display: flex;
  align-items: center;
}

.bell-btn {
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
  cursor: pointer;
  transition: all 0.2s ease;
}

.bell-btn:hover,
.bell-btn.has-unread {
  border-color: var(--brand-400, #5fb088);
  color: var(--brand-700, #1f6343);
}

/* 第 45 批（移动端）：36px 的点击区偏小（触屏建议 ≥40px），窄屏放大 */
@media (max-width: 768px) {
  .bell-btn {
    width: 42px;
    height: 42px;
    font-size: 17px;
  }
}

.bell-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: #cf4436;
  color: #fff;
  font-size: 10.5px;
  font-weight: 700;
  line-height: 1;
  box-shadow: 0 0 0 2px #fff;
}

/* 下拉面板 */
.bell-panel {
  position: absolute;
  top: 46px;
  right: 0;
  z-index: 60;
  width: 330px;
  border: 1px solid var(--brand-200, #bfe3cd);
  border-radius: var(--radius-lg, 18px);
  background: #fff;
  box-shadow: 0 18px 40px rgba(19, 58, 41, 0.16);
  overflow: hidden;
}

.bell-panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  background: linear-gradient(90deg, var(--brand-100, #ddf0e5), var(--brand-50, #f1f9f4) 60%, #fff);
  border-bottom: 1px solid var(--brand-100, #ddf0e5);
}

.bell-panel-head strong {
  font-size: 14px;
  color: var(--ink-900, #14231c);
}

.bell-unread {
  font-size: 12px;
  color: var(--brand-700, #1f6343);
}

.bell-mark-all {
  margin-left: auto;
  border: none;
  background: none;
  color: var(--brand-700, #1f6343);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  text-decoration: underline;
}

.bell-list {
  max-height: 330px;
  overflow-y: auto;
  padding: 6px;
}

.bell-item {
  display: flex;
  gap: 10px;
  padding: 10px;
  border-radius: 12px;
  text-decoration: none;
  transition: background-color 0.18s ease;
}

.bell-item:hover {
  background: var(--brand-50, #f1f9f4);
}

.bell-item.is-unread {
  background: rgba(221, 240, 229, 0.5);
}

.bell-item-icon {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 9px;
  font-size: 13px;
  color: var(--brand-700, #1f6343);
  background: var(--brand-100, #ddf0e5);
}

.bell-item-icon.is-like { color: #2a6fdb; background: #e9f1fd; }
.bell-item-icon.is-favorite { color: #b8761b; background: #fdf3e3; }
.bell-item-icon.is-announcement { color: #fff; background: linear-gradient(135deg, #3d9a68, #1f6343); }
.bell-item-icon.is-comment_like { color: #cf4436; background: #fdecea; }

.bell-item-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bell-item-title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--ink-800, #24352c);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.bell-item-msg {
  font-size: 12px;
  color: var(--ink-500, #78897f);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bell-item-time {
  font-size: 11.5px;
  color: var(--ink-400, #9dada5);
}

.bell-empty {
  margin: 0;
  padding: 28px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--ink-400, #9dada5);
}

.bell-panel-foot {
  padding: 10px;
  text-align: center;
  border-top: 1px solid var(--border, #e2ebe5);
  background: var(--ink-50, #f8fbf9);
}

.bell-panel-foot a {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--brand-700, #1f6343);
  text-decoration: none;
}

.notify-fade-enter-active,
.notify-fade-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.notify-fade-enter-from,
.notify-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
