<template>
  <view class="page">
    <view class="head">
      <text class="title">{{ t('auth.forgotTitle') }}</text>
      <text class="subtitle">{{ t('auth.forgotSubtitle') }}</text>
    </view>

    <view class="card">
      <view class="field">
        <text class="label">{{ t('auth.accountLabel') }}</text>
        <input
          v-model="account"
          class="input"
          :placeholder="t('auth.accountPlaceholder')"
          placeholder-class="ph"
          :disabled="loading"
          @confirm="onSubmit"
        />
      </view>

      <button class="btn-primary" :disabled="loading" @click="onSubmit">
        {{ loading ? t('auth.sending') : t('auth.sendReset') }}
      </button>
    </view>

    <view v-if="sent" class="sent">
      <text class="sent-title">{{ t('auth.forgotSentTitle') }}</text>
      <text class="sent-body">{{ t('auth.forgotSentBody') }}</text>
      <text class="sent-tip">{{ t('auth.forgotNotReceived') }}</text>
      <text class="link" @click="goLogin">{{ t('auth.backToLogin') }}</text>
    </view>
  </view>
</template>

<script setup>
/**
 * 忘记密码（第 237 批）
 *
 * 与 H5 一致：只发重置链接，**不在前端判断账号是否存在** ——
 * 后端对"存在/不存在"返回同样话术（防账号枚举），前端一律按"已发送"提示。
 */
import { ref } from 'vue'
import { t } from '@/i18n'
import { requestPasswordReset } from '@/utils/api'

const account = ref('')
const loading = ref(false)
const sent = ref(false)

async function onSubmit() {
  if (loading.value) return
  const value = account.value.trim()
  if (!value) {
    uni.showToast({ title: t('auth.accountRequired'), icon: 'none' })
    return
  }
  loading.value = true
  try {
    await requestPasswordReset(value)
    sent.value = true
  } catch (error) {
    uni.showToast({ title: error.message || t('auth.sendFailed'), icon: 'none' })
  } finally {
    loading.value = false
  }
}

function goLogin() {
  uni.reLaunch({ url: '/pages/login/login' })
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  padding: 48rpx 40rpx;
  box-sizing: border-box;
  background: #fff;
}

.head {
  margin-bottom: 32rpx;
}

.title {
  display: block;
  font-size: 44rpx;
  font-weight: 700;
}

.subtitle {
  display: block;
  margin-top: 12rpx;
  color: #8b9a91;
  font-size: 26rpx;
  line-height: 1.6;
}

.field {
  border-bottom: 1rpx solid #eef1ef;
  padding: 24rpx 0;
  display: flex;
  align-items: center;
  gap: 20rpx;
}

.label {
  width: 180rpx;
  color: #55665a;
  font-size: 26rpx;
}

.input {
  flex: 1;
  font-size: 28rpx;
  height: 60rpx;
}

.ph {
  color: #b7c2bb;
}

.btn-primary {
  margin-top: 40rpx;
}

.sent {
  margin-top: 40rpx;
  padding: 32rpx;
  border-radius: 20rpx;
  background: #f2f8f4;
}

.sent-title {
  display: block;
  font-size: 30rpx;
  font-weight: 600;
  color: #2f855a;
}

.sent-body {
  display: block;
  margin-top: 12rpx;
  color: #55665a;
  font-size: 26rpx;
  line-height: 1.7;
}

.sent-tip {
  display: block;
  margin-top: 12rpx;
  color: #8b9a91;
  font-size: 24rpx;
  line-height: 1.6;
}

.link {
  display: block;
  margin-top: 24rpx;
  color: #2f855a;
  font-size: 26rpx;
  font-weight: 600;
}
</style>
