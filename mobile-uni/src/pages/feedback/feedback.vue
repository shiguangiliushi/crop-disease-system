<template>
  <view class="page">
    <view class="card">
      <text class="label">{{ t('feedbackForm.category') }}</text>
      <view class="chips">
        <text
          v-for="option in categories"
          :key="option.value"
          class="chip"
          :class="{ active: form.category === option.value }"
          @click="form.category = option.value"
        >{{ option.label }}</text>
      </view>

      <text class="label">{{ t('feedbackForm.content') }}</text>
      <textarea
        v-model="form.suggestion"
        class="textarea"
        maxlength="500"
        :placeholder="t('feedbackForm.contentPlaceholder')"
      />

      <text class="label">{{ t('feedbackForm.contact') }}</text>
      <input v-model="form.contact" class="input" maxlength="50" :placeholder="t('feedbackForm.contactPlaceholder')" />
    </view>

    <button class="btn-primary" :disabled="submitting" @click="submit">
      {{ submitting ? t('common.loading') : t('feedbackForm.submit') }}
    </button>
  </view>
</template>

<script setup>
/** 意见反馈（第 269 批）—— 建议/问题/其他 + 联系方式；图片上传留待真机阶段 */
import { computed, reactive, ref } from 'vue'
import { t } from '@/i18n'
import { submitFeedback } from '@/api/feedback'

const submitting = ref(false)
const form = reactive({ category: 'suggestion', suggestion: '', contact: '' })

const categories = computed(() => [
  { value: 'suggestion', label: t('feedbackForm.typeSuggestion') },
  { value: 'bug', label: t('feedbackForm.typeBug') },
  { value: 'other', label: t('feedbackForm.typeOther') },
])

async function submit() {
  const text = form.suggestion.trim()
  if (!text) {
    uni.showToast({ title: t('feedbackForm.empty'), icon: 'none' })
    return
  }
  submitting.value = true
  try {
    await submitFeedback({ category: form.category, suggestion: text, contact: form.contact.trim() })
    uni.showToast({ title: t('feedbackForm.submitted'), icon: 'success' })
    form.suggestion = ''
    form.contact = ''
  } catch (error) {
    uni.showToast({ title: error?.message || t('feedbackForm.failed'), icon: 'none' })
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.page { min-height: 100vh; background: #f6f8f7; padding: 24rpx; box-sizing: border-box; }
.card { background: #fff; border-radius: 20rpx; padding: 24rpx; margin-bottom: 28rpx; }
.label { display: block; font-size: 24rpx; color: #566b60; margin: 8rpx 0 12rpx; }
.chips { display: flex; gap: 12rpx; flex-wrap: wrap; margin-bottom: 12rpx; }
.chip { padding: 10rpx 24rpx; border-radius: 999rpx; background: #f2f6f3; color: #566b60; font-size: 26rpx; }
.chip.active { background: #2f855a; color: #fff; }
.textarea { width: 100%; min-height: 200rpx; background: #f7faf8; border-radius: 12rpx; padding: 16rpx; font-size: 26rpx; }
.input { background: #f7faf8; border-radius: 12rpx; padding: 16rpx; font-size: 26rpx; }
.btn-primary { background: #2f855a; color: #fff; border-radius: 999rpx; font-size: 28rpx; height: 84rpx; line-height: 84rpx; }
</style>
