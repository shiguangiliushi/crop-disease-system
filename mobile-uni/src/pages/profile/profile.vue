<template>
  <view class="page">
    <view class="card">
      <view class="field">
        <text class="label">{{ t('profileEdit.nickname') }}</text>
        <input v-model="form.firstName" class="input" maxlength="30" :placeholder="t('profileEdit.nickname')" />
      </view>
      <view class="field">
        <text class="label">{{ t('profileEdit.email') }}</text>
        <input v-model="form.email" class="input" maxlength="60" :placeholder="t('profileEdit.email')" />
      </view>
      <view class="field">
        <text class="label">{{ t('profileEdit.bio') }}</text>
        <textarea v-model="form.bio" class="input textarea" maxlength="200" :placeholder="t('profileEdit.bio')" />
      </view>
    </view>

    <button class="btn-primary" :disabled="saving" @click="save">
      {{ saving ? t('common.loading') : t('profileEdit.save') }}
    </button>
  </view>
</template>

<script setup>
/** 资料编辑（第 265 批）—— 只提交改动字段，进页面先拉资料 */
import { reactive, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { t } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import { fetchProfile, updateProfile } from '@/api/profileEdit'

const auth = useAuthStore()
const saving = ref(false)
const form = reactive({ firstName: '', email: '', bio: '' })
const original = reactive({ firstName: '', email: '', bio: '' })

function fill(profile) {
  form.firstName = profile.first_name || ''
  form.email = profile.email || ''
  form.bio = profile.bio || ''
  original.firstName = form.firstName
  original.email = form.email
  original.bio = form.bio
}

onLoad(async () => {
  fill(auth.user || {})
  const userId = auth.user?.id
  if (!userId) return
  try {
    const profile = await fetchProfile(userId)
    fill(profile)
  } catch (error) {
    console.warn('[profile] 加载失败', error)
  }
})

async function save() {
  const userId = auth.user?.id
  if (!userId) {
    uni.showToast({ title: t('profileEdit.notLoggedIn'), icon: 'none' })
    return
  }
  const payload = {}
  if (form.firstName.trim() !== original.firstName) payload.first_name = form.firstName.trim()
  if (form.email.trim() !== original.email) payload.email = form.email.trim()
  if (form.bio.trim() !== original.bio) payload.bio = form.bio.trim()

  if (!Object.keys(payload).length) {
    uni.showToast({ title: t('profileEdit.noChange'), icon: 'none' })
    return
  }

  saving.value = true
  try {
    const updated = await updateProfile(userId, payload)
    auth.user = { ...(auth.user || {}), ...updated }
    fill(updated)
    uni.showToast({ title: t('profileEdit.saved'), icon: 'success' })
  } catch (error) {
    uni.showToast({ title: error?.message || t('profileEdit.saveFailed'), icon: 'none' })
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.page { min-height: 100vh; background: #f6f8f7; padding: 24rpx; box-sizing: border-box; }
.card { background: #fff; border-radius: 20rpx; padding: 8rpx 24rpx; margin-bottom: 28rpx; }
.field { padding: 20rpx 0; border-bottom: 1rpx solid #f0f4f1; }
.field:last-child { border-bottom: none; }
.label { display: block; font-size: 24rpx; color: #8b9a91; margin-bottom: 10rpx; }
.input { font-size: 28rpx; color: #24352c; width: 100%; }
.textarea { min-height: 120rpx; }
.btn-primary { background: #2f855a; color: #fff; border-radius: 999rpx; font-size: 28rpx; height: 84rpx; line-height: 84rpx; }
</style>
