<template>
  <div class="page mine-page">

    <div class="page-pad">
      <!-- 未登录：不弹回登录页，就地引导（点"我的"多半只是想看看有没有登录） -->
      <div v-if="!auth.isAuthenticated" class="card guest-card">
        <span class="avatar avatar--guest">?</span>
        <div>
          <p class="guest-name">{{ t('mine.guest') }}</p>
          <p class="muted">{{ t('mine.guestHint') }}</p>
        </div>
        <van-button size="small" round color="#2e7d32" @click="router.push('/login')">
          {{ t('mine.goLogin') }}
        </van-button>
      </div>

      <div v-else class="card user-card">
        <img v-if="avatarUrl" class="avatar" :src="avatarUrl" :alt="auth.username" />
        <span v-else class="avatar avatar--text">{{ initial }}</span>
        <div class="user-body">
          <p class="user-name">{{ auth.username }}</p>
          <van-tag :type="auth.isAdmin ? 'primary' : 'default'" size="medium">
            {{ auth.isAdmin ? t('mine.admin') : t('mine.user') }}
          </van-tag>
        </div>
      </div>

      <div v-if="auth.isAuthenticated" class="card stats-card">
        <div class="stat">
          <strong>{{ stats.detections }}</strong>
          <span>{{ t('mine.detections') }}</span>
        </div>
        <div class="stat">
          <strong>{{ stats.posts }}</strong>
          <span>{{ t('mine.posts') }}</span>
        </div>
        <div class="stat">
          <strong>{{ stats.points }}</strong>
          <span>{{ t('mine.points') }}</span>
        </div>
      </div>

      <van-cell-group inset class="cells">
        <van-cell
          :title="t('mine.language')"
          :value="currentLocaleLabel"
          is-link
          @click="showLanguageSheet = true"
        />
        <van-cell :title="t('mine.about')" is-link @click="showAbout = true" />
        <van-cell v-if="auth.isAuthenticated" :title="t('history.title')" is-link to="/history" />
      </van-cell-group>

      <div v-if="auth.isAuthenticated" class="logout-box">
        <van-button block round plain type="danger" @click="confirmLogout">{{ t('mine.logout') }}</van-button>
        <!--
          第 95 批：注销账号
          移动端此前**完全没有注销入口**（桌面端也没有，第 95 批一起补的）。
          移动端用户想注销只能找管理员 —— 而隐私政策写的是"可申请注销"，
          所以这里必须给一个自助入口。
        -->
        <van-button block round plain class="danger-link" @click="confirmDeleteAccount">
          {{ t('mine.deleteAccount') }}
        </van-button>
      </div>

      <p class="version muted">{{ t('mine.version') }} {{ APP_VERSION }}</p>
    </div>

    <van-action-sheet
      v-model:show="showLanguageSheet"
      :actions="languageActions"
      :cancel-text="t('common.cancel')"
      @select="onSelectLanguage"
    />

    <van-dialog
      v-model:show="showAbout"
      :title="t('mine.about')"
      :message="t('mine.aboutDesc')"
      show-cancel-button
      :confirm-button-text="t('common.confirm')"
      :cancel-button-text="t('common.cancel')"
    />

    <!--
      注销账号确认（第 95 批）
      用 `before-close` 而不是 `@confirm`：注销可能失败（密码错），
      失败时**不能**把弹窗关掉 —— 否则用户以为删成功了，其实没有。
    -->
    <van-dialog
      v-model:show="deleteDialog"
      :title="t('mine.deleteAccount')"
      :show-cancel-button="true"
      :confirm-button-text="t('mine.deleteAccountConfirm')"
      :cancel-button-text="t('common.cancel')"
      :before-close="onDeleteDialogClose"
    >
      <div class="delete-dialog-body">
        <p class="delete-warn">{{ t('mine.deleteAccountWarning') }}</p>
        <ul class="delete-list">
          <li>{{ t('mine.deleteAccountItem1') }}</li>
          <li>{{ t('mine.deleteAccountItem2') }}</li>
          <li>{{ t('mine.deleteAccountItem3') }}</li>
        </ul>
        <van-field
          v-model="deletePassword"
          type="password"
          :label="t('mine.deleteAccountPassword')"
          :placeholder="t('mine.deleteAccountPasswordPlaceholder')"
        />
      </div>
    </van-dialog>
  </div>
</template>

<script setup>
/**
 * 「我的」页（移动端）
 * ----------------------------------------------------------------------------
 * 统计数字（识别次数 / 发帖 / 积分）都是**尽力而为**：任何一个接口挂了都只回落 0，
 * 不让整页打不开 —— 这些只是"看一眼"的信息，不该阻塞用户退出登录或换语言。
 */
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { showConfirmDialog, showFailToast, showSuccessToast } from 'vant';
import { fetchDetectionCount, fetchMyPoints, fetchUserStats } from '@/api/user';
import { toAbsoluteMediaUrl, formatApiError } from '@/api/http';
import { deleteMyAccount } from '@/api/account';  // 第 95 批：自助注销
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';

const APP_VERSION = '0.1.0';

const router = useRouter();
const auth = useAuthStore();
const { t, locale, setLocale, locales } = useI18n();

const stats = ref({ detections: 0, posts: 0, points: 0 });
const showLanguageSheet = ref(false);
const showAbout = ref(false);

const initial = computed(() => (auth.username || '?').slice(0, 1).toUpperCase());
const avatarUrl = computed(() => toAbsoluteMediaUrl(auth.user?.avatar || ''));
const currentLocaleLabel = computed(
  () => locales.find((item) => item.value === locale.value)?.label || locales[0].label,
);
const languageActions = computed(() =>
  locales.map((item) => ({ name: item.label, value: item.value })),
);

const loadStats = async () => {
  if (!auth.isAuthenticated || !auth.userId) {
    stats.value = { detections: 0, posts: 0, points: 0 };
    return;
  }
  const [detections, userStats, points] = await Promise.all([
    fetchDetectionCount(),
    fetchUserStats(auth.userId),
    fetchMyPoints(),
  ]);
  stats.value = { detections, posts: userStats.postCount, points: points.points };
};

const onSelectLanguage = (action) => {
  setLocale(action.value);
  showLanguageSheet.value = false;
};

const confirmLogout = async () => {
  try {
    await showConfirmDialog({
      title: t('mine.logout'),
      message: t('mine.logoutConfirm'),
      confirmButtonColor: '#d9534f',
    });
  } catch {
    return;
  }
  await auth.logout();
  showSuccessToast(t('mine.loggedOut'));
  router.replace('/detect');
};

/**
 * 注销账号（第 95 批）
 *
 * 移动端上不做"输入用户名/DELETE 确认"那一套（软键盘打字在田里很烦），
 * 改为**两段确认**：第一段说明后果 + 输入密码，第二段再确认一次。
 * 服务端仍然要求 `confirm=DELETE` 且校验密码 —— 前端只是引导，不是护栏。
 */
const deleteDialog = ref(false);
const deletePassword = ref('');
const deleting = ref(false);

const confirmDeleteAccount = () => {
  deletePassword.value = '';
  deleteDialog.value = true;
};

/**
 * 弹窗关闭前的钩子：只有"密码正确、服务端删除成功"才允许关闭。
 * 返回 false 会把弹窗留在原地（Vant 的 before-close 语义）。
 */
const onDeleteDialogClose = async (action) => {
  if (action !== 'confirm') return true;      // 点取消 → 直接关
  if (!deletePassword.value) {
    showFailToast(t('mine.deleteAccountPasswordRequired'));
    return false;
  }
  if (deleting.value) return false;
  deleting.value = true;
  try {
    await deleteMyAccount({ password: deletePassword.value });
    showSuccessToast(t('mine.deleteAccountOk'));
    auth.clearAuth();          // 后端已删 Token，本地也要清干净
    router.replace('/detect'); // 账号没了，回识别页（游客态）而不是登录页
    return true;
  } catch (error) {
    showFailToast(formatApiError(error, t('mine.deleteAccountFailed')));
    return false;             // 失败不关弹窗，用户可以改密码重试
  } finally {
    deleting.value = false;
  }
};

onMounted(loadStats);
// 登录/退出后刷新统计（同一个页面内切换账号不会重新 mount）
watch(() => auth.userId, loadStats);
</script>

<style scoped>
.mine-page {
  min-height: 100vh;
}

.guest-card,
.user-card {
  display: flex;
  align-items: center;
  gap: 12px;
}

.guest-card > div {
  flex: 1;
}

.avatar {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  object-fit: cover;
  flex: 0 0 auto;
  background: #e8f5e9;
}

.avatar--guest,
.avatar--text {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #2e7d32;
  font-size: 1.2rem;
  font-weight: 700;
}

.guest-name,
.user-name {
  margin: 0 0 4px;
  font-size: 1.05rem;
  font-weight: 600;
}

.user-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}

.stats-card {
  display: flex;
  justify-content: space-around;
  text-align: center;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat strong {
  font-size: 1.25rem;
  color: #2e7d32;
}

.stat span {
  font-size: 0.8rem;
  color: #6f806f;
}

.cells {
  margin-bottom: 18px;
}

.logout-box {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 第 95 批：注销账号（比退出登录更危险，用弱化的文字按钮区分开） */
.danger-link {
  --van-button-default-color: #8a8a8a;
  color: #8a8a8a !important;
  border-color: #e2e2e2 !important;
  font-size: 0.86rem;
}

.delete-dialog-body {
  padding: 14px 16px 6px;
  text-align: left;
}

.delete-warn {
  margin: 0 0 8px;
  font-size: 0.86rem;
  color: #a32f22;
  font-weight: 600;
}

.delete-list {
  margin: 0 0 10px;
  padding-left: 18px;
  font-size: 0.82rem;
  line-height: 1.7;
  color: #55665a;
}

.version {
  text-align: center;
  margin-top: 18px;
  font-size: 0.78rem;
}
</style>
