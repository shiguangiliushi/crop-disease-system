<template>
  <view class="page">
    <view class="profile">
      <view class="avatar">{{ initial }}</view>
      <view class="who">
        <text class="name">{{ auth.username || '未登录' }}</text>
        <text class="role">{{ roleText }}{{ levelText ? ' · ' + levelText : '' }}</text>
      </view>
    </view>

    <view class="stats">
      <view class="stat">
        <text class="stat-value">{{ stats.detections }}</text>
        <text class="stat-label">识别</text>
      </view>
      <view class="stat">
        <text class="stat-value">{{ stats.posts }}</text>
        <text class="stat-label">发帖</text>
      </view>
      <view class="stat">
        <text class="stat-value">{{ stats.points }}</text>
        <text class="stat-label">积分</text>
      </view>
    </view>

    <view class="card menu">
      <view class="menu-item" @click="goHistory">
        <text class="menu-icon">🗂</text>
        <text class="menu-label">我的识别记录</text>
        <text class="menu-arrow">›</text>
      </view>
      <view class="menu-item" @click="showAbout">
        <text class="menu-icon">ℹ️</text>
        <text class="menu-label">关于本应用</text>
        <text class="menu-arrow">›</text>
      </view>
      <!-- #ifdef APP-PLUS -->
      <view class="menu-item" @click="editServer">
        <text class="menu-icon">🌐</text>
        <text class="menu-label">服务器地址</text>
        <text class="menu-value">{{ serverShown }}</text>
        <text class="menu-arrow">›</text>
      </view>
      <!-- #endif -->
    </view>

    <button class="logout" @click="onLogout">退出登录</button>

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
import { onShow } from '@dcloudio/uni-app'
import BottomNav from '@/components/BottomNav.vue'
import { useAuthStore } from '@/stores/auth'
import { fetchDetectionCount, fetchMyPoints, fetchUserStats } from '@/api/profile'
import { TOKEN_KEY } from '@/utils/request'
// #ifdef APP-PLUS
import { apiBase, saveApiBase } from '@/utils/config'
// #endif

const auth = useAuthStore()
const stats = reactive({ detections: 0, posts: 0, points: 0 })
const levelName = ref('')

const initial = computed(() => (auth.username || '?').slice(0, 1).toUpperCase())

const roleText = computed(() => {
  const role = auth.user?.role
  return { ADMIN: '管理员', EDITOR: '信息编辑员', USER: '农户' }[role] || '农户'
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
    title: '农作物病害识别',
    content: 'uni-app 版 v0.1.0\n识别结果仅供参考，实际防治请以当地植保部门意见为准。',
    showCancel: false,
    confirmText: '知道了',
  })
}

async function editServer() {
  // #ifdef APP-PLUS
  const result = await uni.showModal({
    title: '服务器地址',
    editable: true,
    placeholderText: 'http://192.168.1.20:8000/api',
    content: apiBase(),
    confirmText: '保存',
  })
  if (!result.confirm) return
  const value = String(result.content || '').trim()
  if (!/^https?:\/\//i.test(value)) {
    uni.showToast({ title: '请填写 http(s):// 开头的地址', icon: 'none' })
    return
  }
  saveApiBase(value)
  uni.showToast({ title: '已保存', icon: 'success' })
  // #endif
}

async function onLogout() {
  const result = await uni.showModal({
    title: '退出登录',
    content: '退出后需要重新输入账号密码',
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
