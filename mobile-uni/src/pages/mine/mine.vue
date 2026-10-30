<template>
  <view class="page">
    <view class="profile">
      <view class="avatar">{{ initial }}</view>
      <view class="who">
        <text class="name">{{ auth.username || t('mine.guest') }}</text>
        <text class="role">{{ roleText }}{{ levelText ? ' · ' + levelText : '' }}</text>
      </view>
    </view>

    <view class="stats">
      <view class="stat">
        <text class="stat-value">{{ stats.detections }}</text>
        <text class="stat-label">{{ t('mine.detections') }}</text>
      </view>
      <view class="stat">
        <text class="stat-value">{{ stats.posts }}</text>
        <text class="stat-label">{{ t('mine.posts') }}</text>
      </view>
      <view class="stat">
        <text class="stat-value">{{ stats.points }}</text>
        <text class="stat-label">{{ t('mine.points') }}</text>
      </view>
    </view>

    <view class="card menu">
      <view class="menu-item" @click="goFeedback">
      <text class="menu-label">{{ t('feedbackForm.title') }}</text>
    </view>

    <view class="menu-item" @click="goProfileEdit">
      <text class="menu-label">{{ t('profileEdit.title') }}</text>
    </view>

    <view class="menu-item" @click="goNotifications">
      <text class="menu-label">{{ t('notify.title') }}</text>
      <text v-if="unread" class="menu-value">{{ unread }}</text>
    </view>

    <view class="menu-item" @click="goHistory">
        <text class="menu-icon">🗂</text>
        <text class="menu-label">{{ t('history.title') }}</text>
        <text class="menu-arrow">›</text>
      </view>
      <view class="menu-item" @click="chooseLanguage">
        <text class="menu-icon">🌐</text>
        <text class="menu-label">{{ t('mine.language') }}</text>
        <text class="menu-value">{{ currentLocaleLabel }}</text>
        <text class="menu-arrow">›</text>
      </view>
      <view class="menu-item" @click="showAbout">
        <text class="menu-icon">ℹ️</text>
        <text class="menu-label">{{ t('mine.about') }}</text>
        <text class="menu-arrow">›</text>
      </view>
      <!-- #ifdef APP-PLUS -->
      <view class="menu-item" @click="editServer">
        <text class="menu-icon">🌐</text>
        <text class="menu-label">{{ t('auth.server') }}</text>
        <text class="menu-value">{{ serverShown }}</text>
        <text class="menu-arrow">›</text>
      </view>
      <!-- #endif -->
    </view>

    <button class="danger" @click="onDeleteAccount">{{ t('mine.deleteAccount') }}</button>

    <button class="logout" @click="onLogout">{{ t('mine.logout') }}</button>

    <BottomNav current="mine" />
  </view>
</template>

<script setup>
/**
 * 「我的」页（第 236 批）
 *
 * 三块内容：身份（头像/用户名/角色）、统计（识别/发帖/积分）、菜单（记录/关于/服务器/退出）。
 * 统计接口失败一律兜底 0（见 `api/profile.js`），不让整页打不开。
 */
import { computed, reactive, ref } from 'vue'
import { currentLocaleLabel, setLocale, SUPPORTED_LOCALES, t } from '@/i18n'
import { requestAccountDeletion } from '@/utils/api'
import { onShow } from '@dcloudio/uni-app'
import BottomNav from '@/components/BottomNav.vue'
import { useAuthStore } from '@/stores/auth'
import { fetchDetectionCount, fetchMyPoints, fetchUserStats } from '@/api/profile'
import { TOKEN_KEY } from '@/utils/request'
import { fetchUnreadCount } from '@/api/notify'
// #ifdef APP-PLUS
import { apiBase, saveApiBase } from '@/utils/config'
// #endif

const auth = useAuthStore()
const stats = reactive({ detections: 0, posts: 0, points: 0 })
const levelName = ref('')
const unread = ref(0)  // 第 262 批：未读通知数

const initial = computed(() => (auth.username || '?').slice(0, 1).toUpperCase())

const roleText = computed(() => {
  const role = auth.user?.role
  return role === 'ADMIN' ? t('mine.admin') : t('mine.user')
})

const levelText = computed(() => levelName.value)

// #ifdef APP-PLUS
const serverShown = computed(() => apiBase())
// #endif

async function loadStats() {
  const userId = auth.user?.id
  const [detections, userStats, points] = await Promise.all([
    fetchDetectionCount(),
    userId ? fetchUserStats(userId) : Promise.resolve({ postCount: 0 }),
    fetchMyPoints(),
  ])
  stats.detections = detections
  stats.posts = userStats.postCount
  stats.points = points.points
  levelName.value = points.levelName || ''
}

function goHistory() {
  uni.reLaunch({ url: '/pages/history/history' })
}

function showAbout() {
  uni.showModal({
    title: t('common.appName'),
    content: 'uni-app 版 v0.1.0\n识别结果仅供参考，实际防治请以当地植保部门意见为准。',
    showCancel: false,
    confirmText: t('common.confirm'),
  })
}

async function editServer() {
  // #ifdef APP-PLUS
  const result = await uni.showModal({
    title: t('auth.serverEdit'),
    editable: true,
    placeholderText: 'http://192.168.1.20:8000/api',
    content: apiBase(),
    confirmText: t('common.confirm'),
  })
  if (!result.confirm) return
  const value = String(result.content || '').trim()
  if (!/^https?:\/\//i.test(value)) {
    uni.showToast({ title: t('auth.serverInvalid'), icon: 'none' })
    return
  }
  saveApiBase(value)
  uni.showToast({ title: t('auth.serverSaved'), icon: 'success' })
  // #endif
}

async function chooseLanguage() {
  const labels = SUPPORTED_LOCALES.map((item) => item.label)
  try {
    const result = await uni.showActionSheet({ itemList: labels })
    const picked = SUPPORTED_LOCALES[result.tapIndex]
    if (picked) setLocale(picked.value)
  } catch (error) {
    // 用户取消（errMsg 含 cancel）—— 不提示
  }
}

/**
 * 注销账号（冷静期）：与 H5 一致，要密码确认。
 * ⚠️ 用 editable 的 showModal 拿密码 —— 小程序没有"密码输入弹窗"，
 *    输的内容会明文显示在弹窗里（演示够用，正式产品应换成独立页面 + password 输入框）。
 */
async function onDeleteAccount() {
  const result = await uni.showModal({
    title: t('mine.deleteAccount'),
    content: t('mine.deleteAccountWarning'),
    editable: true,
    placeholderText: t('mine.deleteAccountPasswordPlaceholder'),
    confirmText: t('mine.deleteAccount'),
    confirmColor: '#c0392b',
  })
  if (!result.confirm) return
  const password = String(result.content || '').trim()
  if (!password) {
    uni.showToast({ title: t('mine.deleteAccountPasswordRequired'), icon: 'none' })
    return
  }
  try {
    await requestAccountDeletion(password)
    uni.showToast({ title: t('mine.deleteAccountOk'), icon: 'none' })
    await auth.logout()
    setTimeout(() => uni.reLaunch({ url: '/pages/login/login' }), 1200)
  } catch (error) {
    uni.showToast({ title: error.message || t('mine.deleteAccountFailed'), icon: 'none' })
  }
}

async function onLogout() {
  const result = await uni.showModal({
    title: t('mine.logout'),
    content: t('mine.logoutConfirm'),
  })
  if (!result.confirm) return
  await auth.logout()
  uni.reLaunch({ url: '/pages/login/login' })
}

onShow(() => {
  if (!uni.getStorageSync(TOKEN_KEY)) {
    uni.reLaunch({ url: '/pages/login/login' })
    return
  }
  loadStats()
})

function goNotifications() {
  uni.navigateTo({ url: '/pages/notify/notify' })
}

onShow(() => {
  fetchUnreadCount().then((count) => {
    unread.value = count
  })
})

function goProfileEdit() {
  uni.navigateTo({ url: '/pages/profile/profile' })
}

function goFeedback() {
  uni.navigateTo({ url: '/pages/feedback/feedback' })
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  padding: 40rpx 0 140rpx;
  box-sizing: border-box;
}

.profile {
  display: flex;
  align-items: center;
  gap: 24rpx;
  padding: 0 40rpx 32rpx;
}

.avatar {
  width: 108rpx;
  height: 108rpx;
  border-radius: 50%;
  background: #e8f5ee;
  color: #2f855a;
  font-size: 44rpx;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.who {
  flex: 1;
  min-width: 0;
}

.name {
  display: block;
  font-size: 38rpx;
  font-weight: 700;
}

.role {
  display: block;
  margin-top: 6rpx;
  color: #8b9a91;
  font-size: 24rpx;
}

.stats {
  display: flex;
  margin: 0 24rpx 24rpx;
  padding: 28rpx 0;
  background: #fff;
  border-radius: 24rpx;
}

.stat {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8rpx;
}

.stat-value {
  font-size: 40rpx;
  font-weight: 700;
}

.stat-label {
  color: #8b9a91;
  font-size: 22rpx;
}

.menu {
  padding: 0;
  overflow: hidden;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 28rpx 28rpx;
  border-bottom: 1rpx solid #f2f5f3;
}

.menu-item:last-child {
  border-bottom: none;
}

.menu-icon {
  font-size: 30rpx;
}

.menu-label {
  flex: 1;
  font-size: 28rpx;
}

.menu-value {
  color: #8b9a91;
  font-size: 22rpx;
  max-width: 300rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menu-arrow {
  color: #b7c2bb;
  font-size: 32rpx;
}

.danger {
  margin: 0 40rpx 24rpx;
  background: #fff;
  color: #c0392b;
  border-radius: 999rpx;
  font-size: 28rpx;
  height: 88rpx;
  line-height: 88rpx;
}

.logout {
  margin: 40rpx;
  background: #fff;
  color: #c0392b;
  border-radius: 999rpx;
  font-size: 28rpx;
  height: 88rpx;
  line-height: 88rpx;
}
</style>
