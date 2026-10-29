<template>
  <view class="page">
    <view class="header">
      <view>
        <text class="title">{{ t('history.title') }}</text>
        <text class="hint">{{ t('history.total', { count: total }) }}</text>
      </view>
      <text class="add" @click="goDetect">{{ t('history.emptyAction') }}</text>
    </view>

    <view v-if="loading && !items.length" class="state">
      <text class="state-text">{{ t('common.loading') }}</text>
    </view>

    <view v-else-if="!items.length" class="state">
      <text class="state-icon">🗂</text>
      <text class="state-title">{{ t('history.empty') }}</text>
      <text class="state-sub">{{ t('history.emptyAction') }}</text>
    </view>

    <view v-else class="list">
      <view
        v-for="item in items"
        :key="item.id"
        class="row"
        @click="openDetail(item)"
        @longpress="confirmDelete(item)"
      >
        <image :src="item.image" mode="aspectFill" class="thumb" />
        <view class="row-main">
          <text class="row-title">{{ item.disease }}</text>
          <text class="row-sub">{{ item.time }}</text>
        </view>
        <text class="row-conf">{{ percent(item.confidence) }}</text>
      </view>

      <view class="more">
        <text v-if="hasNext" class="more-text" @click="loadMore">{{ t('history.loadMore') }}</text>
        <text v-else class="more-text muted">{{ t('history.noMore') }}</text>
      </view>
    </view>

    <BottomNav current="history" />
  </view>
</template>

<script setup>
/**
 * 历史记录页（第 236 批）
 *
 * 交互与现有 H5 对齐：下拉刷新、滚到底加载更多、点进详情、长按删除。
 * 数据侧直接复用后端 `/api/detection-history/`（见 `api/history.js`）。
 */
import { ref } from 'vue'
import { t } from '@/i18n'
import { onPullDownRefresh, onReachBottom, onShow } from '@dcloudio/uni-app'
import BottomNav from '@/components/BottomNav.vue'
import { fetchHistory, deleteHistory } from '@/api/history'
import { TOKEN_KEY } from '@/utils/request'

const items = ref([])
const total = ref(0)
const page = ref(1)
const hasNext = ref(false)
const loading = ref(false)
const PAGE_SIZE = 10

function percent(value) {
  const number = Number(value) || 0
  const ratio = number > 1 ? number / 100 : number
  return `${Math.round(ratio * 100)}%`
}

async function load({ reset = false } = {}) {
  if (loading.value) return
  loading.value = true
  try {
    const next = reset ? 1 : page.value
    const data = await fetchHistory({ page: next, pageSize: PAGE_SIZE })
    items.value = reset ? data.items : items.value.concat(data.items)
    total.value = data.total
    page.value = next + 1
    hasNext.value = data.hasNext
  } catch (error) {
    uni.showToast({ title: error.message || t('common.requestFailed'), icon: 'none' })
  } finally {
    loading.value = false
    uni.stopPullDownRefresh()
  }
}

function loadMore() {
  if (!hasNext.value || loading.value) return
  load()
}

function openDetail(item) {
  if (!item.id) return
  uni.navigateTo({ url: `/pages/result/result?id=${item.id}` })
}

async function confirmDelete(item) {
  const result = await uni.showModal({
    title: t('history.delete'),
    content: t('history.deleteConfirm'),
    confirmText: t('history.delete'),
    confirmColor: '#c0392b',
  })
  if (!result.confirm) return
  try {
    await deleteHistory(item.id)
    items.value = items.value.filter((row) => row.id !== item.id)
    total.value = Math.max(0, total.value - 1)
    uni.showToast({ title: t('history.deleted'), icon: 'success' })
  } catch (error) {
    uni.showToast({ title: error.message || t('history.deleteFailed'), icon: 'none' })
  }
}

function goDetect() {
  uni.reLaunch({ url: '/pages/detect/detect' })
}

onPullDownRefresh(() => load({ reset: true }))
onReachBottom(loadMore)

onShow(() => {
  // 未登录直接回登录页（与识别页同一道护栏）
  if (!uni.getStorageSync(TOKEN_KEY)) {
    uni.reLaunch({ url: '/pages/login/login' })
    return
  }
  load({ reset: true })
})
</script>

<style scoped>
.page {
  min-height: 100vh;
  padding: 24rpx 0 140rpx;
  box-sizing: border-box;
}

.header {
  padding: 8rpx 40rpx 20rpx;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.title {
  display: block;
  font-size: 40rpx;
  font-weight: 700;
}

.hint {
  display: block;
  margin-top: 8rpx;
  color: #8b9a91;
  font-size: 24rpx;
}

.add {
  color: #2f855a;
  font-size: 26rpx;
  padding-top: 8rpx;
}

.state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12rpx;
  padding: 160rpx 40rpx;
  color: #8b9a91;
}

.state-icon {
  font-size: 88rpx;
}

.state-title {
  font-size: 30rpx;
  color: #1f2d26;
}

.state-sub {
  font-size: 24rpx;
}

.list {
  padding: 0 24rpx;
}

.row {
  display: flex;
  align-items: center;
  gap: 20rpx;
  padding: 20rpx;
  margin-bottom: 16rpx;
  background: #fff;
  border-radius: 20rpx;
}

.thumb {
  width: 108rpx;
  height: 108rpx;
  border-radius: 14rpx;
  background: #eef1ef;
  flex-shrink: 0;
}

.row-main {
  flex: 1;
  min-width: 0;
}

.row-title {
  display: block;
  font-size: 30rpx;
  font-weight: 600;
}

.row-sub {
  display: block;
  margin-top: 6rpx;
  color: #8b9a91;
  font-size: 22rpx;
}

.row-conf {
  color: #2f855a;
  font-size: 26rpx;
  font-weight: 600;
}

.more {
  padding: 20rpx 0 8rpx;
  text-align: center;
}

.more-text {
  color: #2f855a;
  font-size: 26rpx;
}

.more-text.muted {
  color: #b7c2bb;
}
</style>
