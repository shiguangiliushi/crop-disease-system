<template>
  <view class="page">
    <view class="card" v-if="loading">
      <text class="empty">{{ t('common.loading') }}</text>
    </view>

    <view class="card" v-else-if="detection.disease">
      <view class="head">
        <image v-if="imageSrc" :src="imageSrc" mode="widthFix" class="shot" />
        <view class="meta">
          <text class="disease" @click="openWiki">{{ detection.disease }}</text>
        <text class="wiki-link" @click="openWiki">{{ t('pestWiki.viewWiki') }} ›</text>
          <text v-if="detection.disease_en" class="disease-en">{{ detection.disease_en }}</text>
          <view class="confidence">
            <text class="conf-label">{{ t('result.confidence') }}</text>
            <text class="conf-value">{{ percent }}</text>
          </view>
        </view>
      </view>

      <view v-if="detection.description" class="block">
        <text class="block-title">{{ t('result.symptoms') }}</text>
        <text class="block-text">{{ detection.description }}</text>
      </view>

      <view v-if="detection.prevention" class="block">
        <text class="block-title">{{ t('result.prevention') }}</text>
        <text class="block-text">{{ detection.prevention }}</text>
      </view>

      <view class="block">
        <text class="block-title">{{ t('result.feedbackAsk') }}</text>
        <view class="feedback-row">
          <button
            class="chip"
            :disabled="feedbackBusy || feedbackDone"
            @click="sendFeedback(true)"
          >{{ t('result.feedbackAccurate') }}</button>
          <button
            class="chip"
            :disabled="feedbackBusy || feedbackDone"
            @click="sendFeedback(false)"
          >{{ t('result.feedbackInaccurate') }}</button>
        </view>
        <text v-if="feedbackMsg" class="feedback-msg">{{ feedbackMsg }}</text>
      </view>

      <!-- 第 244 批：识别后追问助手（非流式，带 pest_identifier 让回答聚焦该病害） -->
      <view class="block ask-block">
        <text class="block-title">{{ t('auth.askTitle') }}</text>
        <textarea
          v-model="askDraft"
          class="ask-input"
          :placeholder="t('auth.askPlaceholder')"
          :disabled="askLoading"
          auto-height
          maxlength="200"
        />
        <button class="ask-send" :disabled="askLoading" @click="onAsk">
          {{ askLoading ? t('auth.asking') : t('auth.askSend') }}
        </button>
        <text v-if="askAnswer" class="ask-answer">{{ askAnswer }}</text>
      </view>

      <view v-if="detection.crop_mismatch" class="notice">
        <text class="notice-text">
          你选的作物和模型判断不一致（模型更像
          {{ detection.detected_crop || '其它作物' }}），结果以模型识别为准。
        </text>
      </view>
    </view>

    <view class="card" v-else>
      <text class="empty">{{ t('result.retry') }}</text>
    </view>

    <button class="share-btn" :disabled="shareBusy || !detection.disease" @click="onShareCard">
      {{ shareBusy ? t('common.loading') : t('shareCard.make') }}
    </button>

    <!-- 第 239 批：分享卡画布（离屏放置，只用于导出图片） -->
    <canvas canvas-id="share-card" class="share-canvas" />

    <view class="actions">
      <button class="btn-ghost" @click="again">{{ t('result.retry') }}</button>
      <button class="btn-primary small" @click="backHome">{{ t('common.back') }}</button>
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
import { t } from '@/i18n'
import { submitRecognitionFeedback } from '@/api/feedback'
import { makeShareCard } from '@/utils/shareCard'
import { askAssistant } from '@/api/assistant'
import { fetchPests } from '@/utils/api'
import { onLoad } from '@dcloudio/uni-app'
import { mediaUrl } from '@/utils/request'
import { fetchHistoryDetail } from '@/api/history'

const detection = ref({})
const loading = ref(false)

/** 历史详情 → 结果页模板要的形状（字段名不一样，别硬套） */
function fromHistoryDetail(raw = {}) {
  const info = raw.pest_info || {}
  const methods = Array.isArray(info.prevention_methods) ? info.prevention_methods : []
  // 后端的字段叫 `measure`（不是 method/name）—— 写错就只剩一片空白，
  // 实测就是这么发现"防治建议"整块不显示（接口里明明有 5 条）。
  const prevention = methods
    .map((item) => (typeof item === 'string' ? item : item && (item.measure || item.method || item.name || '')))
    .filter(Boolean)
    .join('\n')
  return {
    disease: raw.disease_name || info.name || '',
    disease_en: info.name_en || '',
    confidence: raw.confidence ?? 0,
    description: raw.symptoms || info.symptoms || '',
    prevention: prevention || raw.suggestion || '',
    annotated_image: mediaUrl(raw.annotated_image_url || raw.image || ''),
    identifier: raw.english_identifier || info.english_identifier || raw.identifier || '',
    original_image: mediaUrl(raw.image || ''),
  }
}

onLoad(async (options = {}) => {
  // 从"历史"点进来时带 `?id=`，走接口取详情；从识别页进来则用本地缓存
  if (options.id) {
    loading.value = true
    try {
      historyId.value = options.id
      const raw = await fetchHistoryDetail(options.id)
      detection.value = fromHistoryDetail(raw)
    } catch (error) {
      uni.showToast({ title: error.message || t('common.requestFailed'), icon: 'none' })
      detection.value = {}
    } finally {
      loading.value = false
    }
    return
  }
  try {
    const cached = uni.getStorageSync('last_result') || {}
    detection.value = cached.detection || {}
    historyId.value = cached.history_id || null
  } catch (error) {
    console.warn('[result] 读取结果失败', error)
    detection.value = {}
  }
})

// 第 237 批：识别纠错反馈（与 H5 同一套 /api/feedback/）
const feedbackBusy = ref(false)
const feedbackDone = ref(false)
const feedbackMsg = ref('')
const historyId = ref(null)
// 第 244 批：识别后追问（复用 /api/assistant/ask/）
const askDraft = ref('')
const askAnswer = ref('')
const askLoading = ref(false)

async function onAsk() {
  const question = askDraft.value.trim()
  if (!question) {
    uni.showToast({ title: t('auth.askEmpty'), icon: 'none' })
    return
  }
  askLoading.value = true
  try {
    const result = await askAssistant({
      question,
      // 识别结果里的 model 类名（有就带上，让回答聚焦到这条病害）
      pestIdentifier: detection.value.identifier || '',
    })
    askAnswer.value = result.answer || t('auth.askFailed')
  } catch (error) {
    uni.showToast({ title: error.message || t('auth.askFailed'), icon: 'none' })
  } finally {
    askLoading.value = false
  }
}

const shareBusy = ref(false)
const shareImage = ref('')

/**
 * @param {boolean} isCorrect 用户说"准确"就只记一条；说"不准确"再让用户从病害表里挑正确答案
 *   （`corrected_pest_id` 是这条反馈能变成训练样本的关键，不能省）
 */
async function sendFeedback(isCorrect) {
  if (feedbackBusy.value || feedbackDone.value) return
  let correctedPestId = null
  let correctedName = ''

  if (!isCorrect) {
    feedbackBusy.value = true
    try {
      const pests = await fetchPests()
      if (!pests.length) {
        uni.showToast({ title: t('detect.serviceUnavailable'), icon: 'none' })
        return
      }
      const result = await uni.showActionSheet({ itemList: pests.map((item) => item.name) })
      const picked = pests[result.tapIndex]
      correctedPestId = picked.id
      correctedName = picked.name
    } catch (error) {
      return // 用户取消选择
    } finally {
      feedbackBusy.value = false
    }
  }

  feedbackBusy.value = true
  try {
    await submitRecognitionFeedback({
      diseaseName: detection.value.disease,
      isCorrect,
      confidence: detection.value.confidence,
      historyId: historyId.value,
      correctedPestId,
    })
    feedbackDone.value = true
    feedbackMsg.value = isCorrect
      ? t('result.feedbackThanks')
      : `${t('result.correctedTo')} ${correctedName}`
  } catch (error) {
    uni.showToast({ title: error.message || t('result.feedbackFailed'), icon: 'none' })
  } finally {
    feedbackBusy.value = false
  }
}

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

/**
 * 生成分享卡并预览（第 239 批）
 *
 * 用 `<canvas canvas-id>` 而不是 DOM canvas —— 三端通用（小程序/App 没有 DOM）。
 * 预览用 `uni.previewImage`：H5 可以长按保存，App 里预览页自带"保存到相册"。
 */
async function onShareCard() {
  if (shareBusy.value || !detection.value.disease) return
  shareBusy.value = true
  try {
    const path = await makeShareCard({
      canvasId: 'share-card',
      disease: detection.value.disease,
      diseaseEn: detection.value.disease_en,
      confidence: detection.value.confidence,
      footer: t('result.disclaimer'),
      labels: { confidence: t('result.confidence') },
    })
    shareImage.value = path
    uni.previewImage({ urls: [path], current: path })
  } catch (error) {
    uni.showToast({ title: error.message || t('shareCard.failed'), icon: 'none' })
  } finally {
    shareBusy.value = false
  }
}

function again() {
  uni.reLaunch({ url: '/pages/detect/detect' })
}

function backHome() {
  uni.reLaunch({ url: '/pages/detect/detect' })
}

function openWiki() {
  const keyword = detection.value?.disease || detection.value?.disease_en || ''
  if (!keyword) return
  uni.navigateTo({ url: `/pages/pest/pest?keyword=${encodeURIComponent(keyword)}` })
}
</script>

<style scoped>
.wiki-link { display: block; margin-top: 8rpx; color: #2f855a; font-size: 26rpx; }

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

.ask-block {
  margin-top: 36rpx;
}

.ask-input {
  width: 100%;
  min-height: 92rpx;
  padding: 18rpx 20rpx;
  box-sizing: border-box;
  border: 1rpx solid #e3ebe6;
  border-radius: 16rpx;
  background: #f7faf8;
  font-size: 26rpx;
}

.ask-send {
  margin-top: 16rpx;
  background: #2f855a;
  color: #fff;
  border-radius: 999rpx;
  font-size: 26rpx;
  height: 76rpx;
  line-height: 76rpx;
}

.ask-send[disabled] {
  opacity: 0.6;
}

.ask-answer {
  display: block;
  margin-top: 20rpx;
  padding: 20rpx;
  border-radius: 16rpx;
  background: #f2f8f4;
  color: #3d4a3d;
  font-size: 26rpx;
  line-height: 1.7;
  white-space: pre-wrap;
}

.feedback-row {
  display: flex;
  gap: 20rpx;
  margin-top: 8rpx;
}

.chip {
  flex: 1;
  margin: 0;
  background: #f2f6f3;
  color: #2f855a;
  border-radius: 999rpx;
  font-size: 26rpx;
  height: 72rpx;
  line-height: 72rpx;
}

.chip[disabled] {
  opacity: 0.6;
}

.feedback-msg {
  display: block;
  margin-top: 14rpx;
  color: #2f855a;
  font-size: 24rpx;
}

.share-btn {
  margin: 0 40rpx 24rpx;
  background: #fff;
  color: #2f855a;
  border: 1rpx solid rgba(47, 133, 90, 0.25);
  border-radius: 999rpx;
  font-size: 28rpx;
  height: 84rpx;
  line-height: 84rpx;
}

/* 离屏画布：不占布局，只用于导出 */
.share-canvas {
  position: fixed;
  left: -9999px;
  top: 0;
  width: 375px;
  height: 500px;
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
