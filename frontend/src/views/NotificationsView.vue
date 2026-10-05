<template>
  <div class="notifications-page">
    <!-- 返回入口（第 87 批：本页只能从顶栏通知铃铛进来，此前没有返回按钮） -->
    <BackButton />

    <!-- 页头 -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-bell"></i></span>
        <div>
          <h1>{{ t('notify.title') }}</h1>
          <p>{{ t('notify.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-button plain :loading="loading" @click="load">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
        <el-button v-if="unread > 0" class="btn-on-brand" @click="markAll">
          <i class="fas fa-check-double"></i> {{ t('notify.markAllRead', { count: unread }) }}
        </el-button>
      </div>
    </header>

    <!-- 统计 -->
    <div class="admin-stats">
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-inbox"></i></span>
        <div>
          <div class="stat-tile-value">{{ total }}</div>
          <div class="stat-tile-label">{{ t('notify.statAll') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--pending">
        <span class="stat-tile-icon"><i class="fas fa-envelope"></i></span>
        <div>
          <div class="stat-tile-value">{{ unread }}</div>
          <div class="stat-tile-label">{{ t('notify.statUnread') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--ok">
        <span class="stat-tile-icon"><i class="fas fa-comments"></i></span>
        <div>
          <div class="stat-tile-value">{{ replyCount }}</div>
          <div class="stat-tile-label">{{ t('notify.statReply') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--processing">
        <span class="stat-tile-icon"><i class="fas fa-bullhorn"></i></span>
        <div>
          <div class="stat-tile-value">{{ announcementCount }}</div>
          <div class="stat-tile-label">{{ t('notify.statAnnouncement') }}</div>
        </div>
      </div>
    </div>

    <div class="notify-layout">
      <!-- 通知列表 -->
      <section class="panel-card">
        <div class="panel-head">
          <span class="panel-icon"><i class="fas fa-list-ul"></i></span>
          <h2 class="panel-title">{{ t('notify.myNotifications') }}</h2>
          <span class="panel-count">{{ t('notify.totalCount', { count: total }) }}</span>
          <div class="panel-head-right">
            <div class="notify-tabs">
              <button
                v-for="tab in tabs"
                :key="tab.value"
                type="button"
                class="notify-tab"
                :class="{ 'is-active': activeTab === tab.value }"
                @click="switchTab(tab.value)"
              >
                {{ tab.label }}
              </button>
            </div>
          </div>
        </div>

        <div class="panel-body">
          <el-skeleton v-if="loading" :rows="5" animated />

          <el-empty v-else-if="items.length === 0" :description="activeTab === 'unread' ? t('notify.emptyUnread') : t('notify.emptyAll')" />

          <ul v-else class="notify-list">
            <li
              v-for="item in items"
              :key="item.id"
              class="notify-item"
              :class="{ 'is-unread': !item.is_read }"
            >
              <span class="notify-icon" :class="`is-${item.type}`">
                <i :class="iconOf(item.type)"></i>
              </span>

              <div class="notify-body">
                <div class="notify-title">{{ localizedField(item, 'title') }}</div>
                <p v-if="item.message" class="notify-message">{{ localizedField(item, 'message') }}</p>
                <div class="notify-meta">
                  <span class="notify-type">{{ typeLabel(item.type) }}</span>
                  <!-- 第 78 批：广播类通知（公告 / 预警推送）会给自己也留一份，
                       这里标出来，免得把"我发出去的"误读成"别人发给我的" -->
                  <span v-if="isMine(item)" class="notify-mine">
                    <i class="fas fa-paper-plane"></i> {{ t('notify.sentByMe') }}
                  </span>
                  <span><i class="fas fa-clock"></i> {{ formatTime(item.created_at) }}</span>
                  <span v-if="!item.is_read" class="notify-dot">{{ t('notify.statUnread') }}</span>
                </div>
              </div>

              <div class="notify-actions">
                <el-button
                  v-if="item.url"
                  size="small"
                  type="primary"
                  plain
                  @click="openTarget(item)"
                >
                  {{ t('notify.view') }}
                </el-button>
                <el-button v-if="!item.is_read" size="small" text @click="markRead(item)">
                  {{ t('notify.markRead') }}
                </el-button>
                <el-button size="small" text type="danger" @click="removeItem(item)">
                  <i class="fas fa-trash"></i>
                </el-button>
              </div>
            </li>
          </ul>

          <div v-if="total > pageSize" class="notify-pagination">
            <el-pagination
              background
              layout="prev, pager, next, total"
              :total="total"
              :page-size="pageSize"
              :current-page="page"
              @current-change="changePage"
            />
          </div>
        </div>
      </section>

      <!-- 侧栏：公告 + 管理员发布 -->
      <aside class="notify-side">
        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-bullhorn"></i></span>
            <h3 class="panel-title">{{ t('notify.announcementsTitle') }}</h3>
            <div v-if="isAdmin" class="panel-head-right">
              <el-button size="small" type="primary" plain @click="openAnnouncementDialog()">
                <i class="fas fa-plus"></i> {{ t('notify.publish') }}
              </el-button>
            </div>
          </div>
          <div class="panel-body">
            <el-skeleton v-if="announcementsLoading" :rows="3" animated />
            <template v-else-if="announcements.length">
              <article v-for="item in announcements" :key="item.id" class="announcement">
                <header class="announcement-head">
                  <span v-if="item.is_pinned" class="announcement-pin">
                    <i class="fas fa-thumbtack"></i> {{ t('forum.tagPinned') }}
                  </span>
                  <strong>{{ localizedField(item, 'title') }}</strong>
                </header>
                <p class="announcement-body">{{ item.content }}</p>
                <div class="announcement-meta">
                  <span>{{ item.created_by_name || t('manage.title') }}</span>
                  <span>{{ formatTime(item.created_at) }}</span>
                  <span v-if="!item.is_visible" class="is-off">{{ t('notify.disabledExpired') }}</span>
                  <span v-if="isAdmin" class="announcement-actions">
                    <el-button size="small" text @click="openAnnouncementDialog(item)">{{ t('notify.edit') }}</el-button>
                    <el-button size="small" text type="danger" @click="removeAnnouncement(item)">{{ t('notify.delete') }}</el-button>
                  </span>
                </div>
              </article>
            </template>
            <el-empty v-else :description="t('notify.emptyAnnouncements')" :image-size="70" />
          </div>
        </section>
      </aside>
    </div>

    <!-- 发布 / 编辑公告（仅管理员） -->
    <el-dialog
      v-model="announcementDialog"
      width="620px"
      top="8vh"
      :close-on-click-modal="false"
      class="form-dialog"
    >
      <template #header>
        <div class="form-dialog-head">
          <span class="form-dialog-head-icon"><i class="fas fa-bullhorn"></i></span>
          <div>
            <h3>{{ editingAnnouncement ? t('notify.editAnnouncement') : t('notify.createAnnouncement') }}</h3>
            <p>{{ t('notify.publishHint') }}</p>
          </div>
        </div>
      </template>

      <div class="form-dialog-body">
        <section class="form-section">
          <div class="form-section-head">
            <i class="fas fa-circle-info"></i>
            <h4>{{ t('notify.dialogContent') }}</h4>
            <span class="section-hint">{{ t('notify.dialogContentHint') }}</span>
          </div>

          <el-form label-position="top">
            <el-form-item :label="t('post.titleLabel')">
              <el-input v-model="announcementForm.title" maxlength="200" show-word-limit :placeholder="t('notify.dialogTitlePlaceholder')" />
            </el-form-item>
            <el-form-item :label="t('notify.dialogBody')">
              <el-input
                v-model="announcementForm.content"
                type="textarea"
                :rows="5"
                resize="none"
                :placeholder="t('notify.dialogBodyPlaceholder')"
              />
            </el-form-item>
            <el-form-item :label="t('notify.dialogSettings')">
              <div class="announcement-switches">
                <el-checkbox v-model="announcementForm.is_active">{{ t('notify.dialogActive') }}</el-checkbox>
                <el-checkbox v-model="announcementForm.is_pinned">{{ t('notify.dialogPinned') }}</el-checkbox>
              </div>
            </el-form-item>
          </el-form>
        </section>
      </div>

      <template #footer>
        <div class="form-dialog-footer">
          <span class="footer-hint"><i class="fas fa-shield-halved"></i> {{ t('notify.dialogAdminOnly') }}</span>
          <span>
            <el-button @click="announcementDialog = false">{{ t('common.cancel') }}</el-button>
            <el-button type="primary" :loading="savingAnnouncement" @click="saveAnnouncement">
              <i class="fas fa-check"></i> {{ t('profile.save') }}
            </el-button>
          </span>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script>
/**
 * 通知中心（第 37 批新增）
 * ------------------------------------------------------------------
 * 左侧：我的通知（全部 / 未读，可标记已读、删除、跳转到相关帖子）
 * 右侧：系统公告列表；管理员在这里可以直接发布 / 编辑 / 删除公告
 *       （发布后后端会给全体用户投递一条站内通知）。
 */
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useAuthStore } from '@/stores/auth';
import { formatTime } from '@/utils/date';
import { useI18n } from '@/i18n';  // 第 56 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 72 批：通知标题/摘要的英文内容
import BackButton from '@/components/BackButton.vue';  // 第 87 批：返回按钮

/** 通知类型 → i18n key（后端 type_display 是中文） */
const TYPE_KEYS = {
  reply: 'notify.typeReply',
  like: 'notify.typeLike',
  favorite: 'notify.typeFavorite',
  comment_like: 'notify.typeCommentLike',
  follow: 'notify.typeFollow',
  message: 'notify.typeMessage',
  announcement: 'notify.typeAnnouncement',
  system: 'notify.typeSystem',
};
import {
  createAnnouncement,
  deleteAnnouncement,
  deleteNotification,
  fetchAnnouncements,
  fetchNotifications,
  fetchUnreadCount,
  markAllNotificationsRead,
  markNotificationRead,
  updateAnnouncement,
} from '@/api/notify';

const ICONS = {
  reply: 'fas fa-comment-dots',
  like: 'fas fa-thumbs-up',
  favorite: 'fas fa-bookmark',
  comment_like: 'fas fa-heart',
  follow: 'fas fa-user-plus',
  message: 'fas fa-envelope',  // 第 42 批：私信
  announcement: 'fas fa-bullhorn',
  system: 'fas fa-circle-info',
};

export default {
  name: 'NotificationsView',
  components: { BackButton },  // 第 87 批：返回按钮
  setup() {
    const { t } = useI18n();  // 第 56 批：多语言
    const { localizedField } = useLocalized();  // 第 72 批
    const typeLabel = (type) => (TYPE_KEYS[type] ? t(TYPE_KEYS[type]) : type);
    const authStore = useAuthStore();
    const router = useRouter();

    const items = ref([]);
    const total = ref(0);
    const unread = ref(0);
    const loading = ref(false);
    const page = ref(1);
    const pageSize = ref(10);
    const activeTab = ref('all');

    const announcements = ref([]);
    const announcementsLoading = ref(false);
    const announcementDialog = ref(false);
    const editingAnnouncement = ref(null);
    const savingAnnouncement = ref(false);
    const announcementForm = reactive({ title: '', content: '', is_active: true, is_pinned: false });

    const isAdmin = computed(() => Boolean(authStore.isAdmin));

    /**
     * 这条通知是不是"我自己发出去的"（第 78 批）
     *
     * 广播类（公告 / 病害预警推送）现在会给发送者自己也留一份副本，
     * 否则运营者发完东西后自己的通知中心永远是空的、连有没有推成功都无从核对。
     * 互动类（回复/点赞/收藏）仍然"不给自己发"，所以这个判断只会命中广播。
     */
    const isMine = (item) => Boolean(item?.actor?.id && item.actor.id === authStore.user?.id);
    // 第 56 批：标签也走 i18n（原来写死中文，模板扫描工具抓不到，是浏览器实测发现的）
    const tabs = computed(() => [
      { value: 'all', label: t('notify.tabAll') },
      { value: 'unread', label: t('notify.tabUnread') },
    ]);

    const replyCount = computed(() =>
      items.value.filter((item) => ['reply', 'like', 'favorite', 'comment_like'].includes(item.type)).length,
    );
    const announcementCount = computed(() => items.value.filter((item) => item.type === 'announcement').length);

    const iconOf = (type) => ICONS[type] || ICONS.system;

    const load = async () => {
      loading.value = true;
      try {
        const params = { page: page.value, page_size: pageSize.value };
        if (activeTab.value === 'unread') params.unread = 1;
        const data = await fetchNotifications(params);
        items.value = data?.results || [];
        total.value = data?.count || 0;

        const countData = await fetchUnreadCount();
        unread.value = countData?.unread || 0;
      } catch (error) {
        console.error('加载通知失败:', error);
        ElMessage.error(t('notify.loadFailed'));
      } finally {
        loading.value = false;
      }
    };

    const loadAnnouncements = async () => {
      announcementsLoading.value = true;
      try {
        const params = isAdmin.value ? { all: 1, page_size: 20 } : { page_size: 20 };
        const data = await fetchAnnouncements(params);
        announcements.value = data?.results || [];
      } catch (error) {
        console.warn('加载公告失败:', error);
        announcements.value = [];
      } finally {
        announcementsLoading.value = false;
      }
    };

    const switchTab = (value) => {
      if (activeTab.value === value) return;
      activeTab.value = value;
      page.value = 1;
      load();
    };

    const changePage = (next) => {
      page.value = next;
      load();
    };

    const markRead = async (item) => {
      try {
        await markNotificationRead(item.id);
        item.is_read = true;
        unread.value = Math.max(0, unread.value - 1);
        if (activeTab.value === 'unread') load();
      } catch (error) {
        ElMessage.error(t('msg.operationFailed'));
      }
    };

    const markAll = async () => {
      try {
        await markAllNotificationsRead();
        ElMessage.success(t('notify.allReadOk'));
        load();
      } catch (error) {
        ElMessage.error(t('msg.operationFailed'));
      }
    };

    const removeItem = async (item) => {
      try {
        await deleteNotification(item.id);
        ElMessage.success(t('msg.deleteOk'));
        load();
      } catch (error) {
        ElMessage.error(t('msg.deleteFailed'));
      }
    };

    const openTarget = async (item) => {
      if (!item.is_read) await markRead(item);
      if (item.url) router.push(item.url);
    };

    const openAnnouncementDialog = (item = null) => {
      editingAnnouncement.value = item;
      announcementForm.title = item?.title || '';
      announcementForm.content = item?.content || '';
      announcementForm.is_active = item ? item.is_active : true;
      announcementForm.is_pinned = item ? item.is_pinned : false;
      announcementDialog.value = true;
    };

    const saveAnnouncement = async () => {
      if (!announcementForm.title.trim() || !announcementForm.content.trim()) {
        ElMessage.warning(t('notify.titleBodyRequired'));
        return;
      }
      savingAnnouncement.value = true;
      try {
        const payload = {
          title: announcementForm.title.trim(),
          content: announcementForm.content.trim(),
          is_active: announcementForm.is_active,
          is_pinned: announcementForm.is_pinned,
        };
        if (editingAnnouncement.value) {
          await updateAnnouncement(editingAnnouncement.value.id, payload);
          ElMessage.success(t('notify.announcementUpdated'));
        } else {
          await createAnnouncement(payload);
          ElMessage.success(t('notify.announcementPublished'));
        }
        announcementDialog.value = false;
        await Promise.all([loadAnnouncements(), load()]);
      } catch (error) {
        ElMessage.error(error?.response?.data?.detail || t('msg.savingFailedRetry'));
      } finally {
        savingAnnouncement.value = false;
      }
    };

    const removeAnnouncement = async (item) => {
      try {
        await ElMessageBox.confirm(t('notify.deleteConfirm', { title: item.title }), t('msg.confirmDelete'), {
          confirmButtonText: t('msg.delete'),
          cancelButtonText: t('msg.cancel'),
          type: 'warning',
        });
      } catch {
        return;
      }
      try {
        await deleteAnnouncement(item.id);
        ElMessage.success(t('msg.deleteOk'));
        loadAnnouncements();
      } catch (error) {
        ElMessage.error(t('msg.deleteFailed'));
      }
    };

    onMounted(() => {
      load();
      loadAnnouncements();
    });

    return {
      items,
      total,
      unread,
      loading,
      page,
      pageSize,
      activeTab,
      tabs,
      localizedField,
      typeLabel,
      announcements,
      announcementsLoading,
      announcementDialog,
      editingAnnouncement,
      savingAnnouncement,
      announcementForm,
      isAdmin,
      isMine,
      replyCount,
      announcementCount,
      iconOf,
      formatTime,
      load,
      switchTab,
      changePage,
      markRead,
      markAll,
      removeItem,
      openTarget,
      openAnnouncementDialog,
      saveAnnouncement,
      removeAnnouncement,
      t,
    };
  },
};
</script>

<style scoped>
.notifications-page {
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 24px 20px 40px;
}

/* 第 87 批：返回按钮紧贴左边缘（页面本就是左对齐块级容器，这里只留一点底距） */
.notifications-page > .back-button {
  margin-bottom: 12px;
}

.notify-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 18px;
  align-items: start;
}

.notify-tabs {
  display: flex;
  gap: 6px;
}

.notify-tab {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--surface);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-600);
  cursor: pointer;
  transition: all 0.18s ease;
}

.notify-tab.is-active {
  color: #fff;
  border-color: transparent;
  background: var(--gradient-brand);
}

/* 通知列表 */
.notify-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.notify-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 13px 14px;
  border: 1px solid var(--brand-100);
  border-radius: var(--radius);
  background: linear-gradient(160deg, #ffffff, #f8fcfa);
}

.notify-item.is-unread {
  border-color: var(--brand-300);
  background: linear-gradient(160deg, #f3fbf7, #ffffff);
}

.notify-icon {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 10px;
  font-size: 14px;
  color: var(--brand-700);
  background: var(--brand-100);
}

.notify-icon.is-like { color: #2a6fdb; background: #e9f1fd; }
.notify-icon.is-favorite { color: #b8761b; background: #fdf3e3; }
.notify-icon.is-announcement { color: #fff; background: linear-gradient(135deg, #3d9a68, #1f6343); }
.notify-icon.is-comment_like { color: #cf4436; background: #fdecea; }

.notify-body {
  flex: 1;
  min-width: 0;
}

.notify-title {
  font-size: 14px;
  font-weight: 700;
  line-height: 1.5;
  color: var(--ink-900);
}

.notify-message {
  margin: 4px 0 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--ink-600);
}

.notify-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 6px;
  font-size: 12px;
  color: var(--ink-400);
}

.notify-meta i {
  margin-right: 4px;
}

.notify-type {
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  background: var(--ink-50);
  border: 1px solid var(--border);
  color: var(--ink-500);
}

/* 第 78 批：广播类通知里"我发出去的"那份副本的标记 */
.notify-mine {
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  background: var(--brand-100);
  border: 1px solid var(--brand-200);
  color: var(--brand-800, #1a5238);
  font-weight: 700;
}

.notify-dot {
  padding: 1px 7px;
  border-radius: var(--radius-pill);
  background: #cf4436;
  color: #fff;
  font-weight: 700;
  font-size: 11px;
}

.notify-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.notify-pagination {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

/* 公告 */
.announcement {
  padding: 12px 0;
  border-bottom: 1px dashed var(--border);
}

.announcement:last-child {
  border-bottom: none;
}

.announcement-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.announcement-pin {
  padding: 1px 7px;
  border-radius: var(--radius-pill);
  background: #fdf3e3;
  color: #b8761b;
  font-size: 11px;
  font-weight: 700;
}

.announcement-head strong {
  font-size: 13.5px;
  color: var(--ink-900);
}

.announcement-body {
  margin: 0 0 8px;
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--ink-600);
  white-space: pre-wrap;
}

.announcement-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 11.5px;
  color: var(--ink-400);
}

.announcement-meta .is-off {
  color: #cf4436;
}

.announcement-actions {
  margin-left: auto;
  display: inline-flex;
  gap: 2px;
}

.announcement-switches {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
}

@media (max-width: 1080px) {
  .notify-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>

