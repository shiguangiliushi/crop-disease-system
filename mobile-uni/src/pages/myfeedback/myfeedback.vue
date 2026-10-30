<template>
  <view class="page">
    <view v-if="loading" class="loading">{{ t('common.loading') }}</view>

    <template v-else>
      <view v-if="items.length">
        <view v-for="item in items" :key="item.id" class="card">
          <view class="head">
            <text class="tag" :class="item.status">{{ statusLabel(item.status) }}</text>
            <text class="cat">{{ categoryLabel(item.category) }}</text>
            <text class="time">{{ shortTime(item.timestamp) }}</text>
          </view>
          <text class="content">{{ item.suggestion }}</text>
          <view v-if="item.admin_reply" class="reply">
            <text class="reply-label">{{ t('myFeedback.reply') }}</text>
            <text class="reply-text">{{ item.admin_reply }}</text>
          </view>
        </view>
      </view>
      <view v-else class="empty">{{ t('myFeedback.empty') }}</view>
    </template>
  </view>
</template>

<script setup>
/** 我的反馈（第 270 批）—— 看自己提过什么、管理员是否回复 */
import { onMounted, ref } from 'vue'
import { t } from '@/i18n'
import { fetchMyFeedback } from '@/api/feedback'

const loading = ref(true)
const items = ref([])

function statusLabel(status) {
  const key = { pending: 'statusPending', processing: 'statusProcessing', resolved: 'statusResolved' }[status]
    || 'statusPending'
  return t(`myFeedback.${key}`)
}

function categoryLabel(category) {
  const key = { suggestion: 'typeSuggestion', bug: 'typeBug', recognition: 'typeRecognition', other: 'typeOther' }[category]
    || 'typeOther'
  return t(`feedbackForm.${key}`)
}

function shortTime(raw) {
  if (!raw) return ''
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return String(raw).slice(0, 10)
  return `${date.getMonth() + 1}/${date.getDate()}`
}

onMounted(async () => {
  try {
    const data = await fetchMyFeedback()
    items.value = data.items
  } catch (error) {
    console.warn('[my-feedback] 加载失败', error)
    items.value = []
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.page { min-height: 100vh; background: #f6f8f7; padding: 24rpx; box-sizing: border-box; }
.loading, .empty { padding: 80rpx 0; text-align: center; color: #8b9a91; font-size: 26rpx; }
.card { background: #fff; border-radius: 20rpx; padding: 24rpx; margin-bottom: 20rpx; }
.head { display: flex; align-items: center; gap: 12rpx; margin-bottom: 12rpx; }
.tag { padding: 4rpx 14rpx; border-radius: 999rpx; font-size: 22rpx; background: #fff6e5; color: #a8761a; }
.tag.processing { background: #eef4ff; color: #2c5aa0; }
.tag.resolved { background: #eef7f1; color: #2f855a; }
.cat { font-size: 22rpx; color: #566b60; }
.time { margin-left: auto; font-size: 22rpx; color: #9dada5; }
.content { font-size: 26rpx; line-height: 1.7; color: #24352c; }
.reply { margin-top: 16rpx; padding: 16rpx; border-radius: 12rpx; background: #f2f8f4; }
.reply-label { display: block; font-size: 22rpx; color: #2f855a; margin-bottom: 6rpx; }
.reply-text { font-size: 24rpx; line-height: 1.7; color: #3d4a3d; }
</style>
