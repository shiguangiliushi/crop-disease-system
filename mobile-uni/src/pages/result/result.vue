<template>
  <view class="page">
    <view class="card" v-if="detection.disease">
      <view class="head">
        <image v-if="imageSrc" :src="imageSrc" mode="widthFix" class="shot" />
        <view class="meta">
          <text class="disease">{{ detection.disease }}</text>
          <text v-if="detection.disease_en" class="disease-en">{{ detection.disease_en }}</text>
          <view class="confidence">
            <text class="conf-label">置信度</text>
            <text class="conf-value">{{ percent }}</text>
          </view>
        </view>
      </view>

      <view v-if="detection.description" class="block">
        <text class="block-title">典型症状</text>
        <text class="block-text">{{ detection.description }}</text>
      </view>

      <view v-if="detection.prevention" class="block">
        <text class="block-title">防治建议</text>
        <text class="block-text">{{ detection.prevention }}</text>
      </view>

      <view v-if="detection.crop_mismatch" class="notice">
        <text class="notice-text">
          你选的作物和模型判断不一致（模型更像
          {{ detection.detected_crop || '其它作物' }}），结果以模型识别为准。
        </text>
      </view>
    </view>

    <view class="card" v-else>
      <text class="empty">没有可显示的结果，请重新识别。</text>
    </view>

    <view class="actions">
      <button class="btn-ghost" @click="again">再识别一次</button>
      <button class="btn-primary small" @click="backHome">返回主页</button>
    </view>
  </view>
</template>

<script setup>
/**
 * 结果页（第 232 批）
 *
 * 数据来自上一页存进 `uni.setStorageSync('last_result')` 的识别响应 ——
 * 不在页面间传大对象（小程序 URL 有长度限制，传 JSON 会截断）。
 */
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { mediaUrl } from '@/utils/request'

const detection = ref({})

onLoad(() => {
  try {
    const cached = uni.getStorageSync('last_result') || {}
    detection.value = cached.detection || {}
  } catch (error) {
    console.warn('[result] 读取结果失败', error)
    detection.value = {}
  }
})

const imageSrc = computed(() =>
  mediaUrl(detection.value.annotated_image || detection.value.original_image || '')
)

const percent = computed(() => {
  const value = Number(detection.value.confidence)
  if (!Number.isFinite(value)) return '—'
  // 后端给的可能是 0~1 也可能是 0~100，两种都兜住
  const ratio = value > 1 ? value / 100 : value
  return `${Math.round(ratio * 100)}%`
})

function again() {
  uni.reLaunch({ url: '/pages/detect/detect' })
}

function backHome() {
  uni.reLaunch({ url: '/pages/detect/detect' })
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  padding: 24rpx 0 48rpx;
  box-sizing: border-box;
}

.head {
  display: flex;
  flex-direction: column;
  gap: 24rpx;
}

.shot {
  width: 100%;
  border-radius: 20rpx;
  background: #eef1ef;
}

.disease {
  font-size: 44rpx;
  font-weight: 700;
}

.disease-en {
  display: block;
  margin-top: 4rpx;
  color: #8b9a91;
  font-size: 24rpx;
}

.confidence {
  margin-top: 16rpx;
  display: flex;
  align-items: baseline;
  gap: 12rpx;
}

.conf-label {
  color: #8b9a91;
  font-size: 24rpx;
}

.conf-value {
  color: #2f855a;
  font-size: 40rpx;
  font-weight: 700;
}

.block {
  margin-top: 36rpx;
}

.block-title {
  display: block;
  font-size: 30rpx;
  font-weight: 600;
  margin-bottom: 12rpx;
}

.block-text {
  display: block;
  color: #55665a;
  font-size: 26rpx;
  line-height: 1.7;
  white-space: pre-wrap;
}

.notice {
  margin-top: 28rpx;
  padding: 20rpx;
  border-radius: 16rpx;
  background: #fff8e6;
}

.notice-text {
  color: #8a6d1f;
  font-size: 24rpx;
}

.empty {
  display: block;
  text-align: center;
  color: #8b9a91;
  padding: 60rpx 0;
}

.actions {
  display: flex;
  gap: 24rpx;
  padding: 0 40rpx;
}

.btn-ghost {
  flex: 1;
  background: #eef1ef;
  color: #2f855a;
  border-radius: 999rpx;
  font-size: 28rpx;
  height: 88rpx;
  line-height: 88rpx;
}

.btn-primary.small {
  flex: 1;
  margin: 0;
  height: 88rpx;
  line-height: 88rpx;
  font-size: 28rpx;
}
</style>
