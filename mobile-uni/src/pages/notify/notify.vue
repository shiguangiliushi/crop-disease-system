<template>
  <view class="page">
    <view class="head">
      <text class="hint">{{ t('notify.unread', { n: unread }) }}</text>
      <text class="action" @click="readAll">{{ t('notify.readAll') }}</text>
    </view>

    <view v-if="loading" class="loading">{{ t('common.loading') }}</view>

    <view v-else-if="items.length" class="list">
      <view v-for="item in items" :key="item.id" class="row">
        <view class="dot" :class="{ on: !item.is_read }"></view>
        <view class="body">
          <text class="title">{{ titleOf(item) }}</text>
          <text v-if="labelOf(item)" class="label">{{ labelOf(item) }}</text>
        </view>
      </view>
    </view>

    <view v-else class="empty">{{ t('notify.empty') }}</view>
  </view>
</template>

<script setup>
/** 站内通知（第 262 批）—— 入口在「我的」 */
import { computed, onMounted, ref } from 'vue'
import { fetchNotifications, fetchUnreadCount, markAllRead } from '@/api/notify'
// uni-app 的 i18n 直接导出 `t` 与 `locale`（没有 useI18n 这个组合式函数）
import { locale, t } from '@/i18n'
const loading = ref(true)
const items = ref([])
const unread = ref(0)

const isEnglish = computed(() => String(locale.value || '').startsWith('en'))
const titleOf = (item) => (isEnglish.value ? item.title_en || item.title : item.title) || ''
const labelOf = (item) => {
  const text = (isEnglish.value ? item.message_en || item.message : item.message) || ''
  return text.slice(0, 80)
}

async function load() {
  loading.value = true
  try {
    const data = await fetchNotifications()
    items.value = data.items
    unread.value = await fetchUnreadCount()
  } catch (error) {
    console.warn('[notify] 加载失败', error)
    items.value = []
  } finally {
    loading.value = false
  }
}

async function readAll() {
  try {
    await markAllRead()
    items.value = items.value.map((row) => ({ ...row, is_read: true }))
    unread.value = 0
  } catch (error) {
    console.warn('[notify] 全部已读失败', error)
  }
}

onMounted(load)
</script>

<style scoped>
.page { min-height: 100vh; background: #f6f8f7; padding: 24rpx; box-sizing: border-box; }
.head { display: flex; justify-content: space-between; align-items: center; padding: 0 8rpx 16rpx; }
.hint { color: #8b9a91; font-size: 24rpx; }
.action { color: #2f855a; font-size: 26rpx; }
.loading, .empty { padding: 80rpx 0; text-align: center; color: #8b9a91; font-size: 26rpx; }
.list { background: #fff; border-radius: 20rpx; overflow: hidden; }
.row { display: flex; gap: 12rpx; padding: 24rpx 20rpx; border-bottom: 1rpx solid #f0f4f1; }
.dot { width: 12rpx; height: 12rpx; border-radius: 50%; margin-top: 12rpx; background: transparent; }
.dot.on { background: #e05c4b; }
.body { flex: 1; display: flex; flex-direction: column; gap: 8rpx; }
.title { font-size: 28rpx; color: #24352c; }
.label { color: #8b9a91; font-size: 24rpx; }
</style>
