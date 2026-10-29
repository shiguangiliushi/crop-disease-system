<template>
  <view class="page">
    <view class="brand">
      <view class="logo">叶</view>
      <text class="title">{{ t('common.appName') }}</text>
    </view>
    <text class="subtitle">{{ t('auth.loginSubtitle') }}</text>

    <view class="card">
      <view class="field">
        <text class="label">{{ t('auth.username') }}</text>
        <input
          v-model="form.username"
          class="input"
          :placeholder="t('auth.usernamePlaceholder')"
          placeholder-class="ph"
          :disabled="loading"
        />
      </view>
      <view class="field">
        <text class="label">{{ t('auth.password') }}</text>
        <input
          v-model="form.password"
          class="input"
          password
          :placeholder="t('auth.passwordPlaceholder')"
          placeholder-class="ph"
          :disabled="loading"
          @confirm="onSubmit"
        />
      </view>

      <text class="forgot" @click="goForgot">{{ t('auth.forgot') }}</text>

      <button class="btn-primary" :disabled="loading" @click="onSubmit">
        {{ loading ? t('auth.loggingIn') : t('auth.login') }}
      </button>
    </view>

    <view class="switch">
      <text class="muted">{{ t('auth.noAccount') }}</text>
      <text class="link" @click="goRegister">{{ t('auth.registerNow') }}</text>
    </view>

    <text class="tip">{{ t('result.disclaimer') }}</text>

    <!-- #ifdef APP-PLUS -->
    <view class="server-row" @click="editServer">
      <text class="server-label">{{ t('auth.server') }}</text>
      <text class="server-value">{{ serverShown }}</text>
      <text class="server-edit">{{ t('auth.serverEdit') }}</text>
    </view>
    <!-- #endif -->
  </view>
</template>

<script setup>
/**
 * 登录页（第 232 批初版 / 第 237 批补多语言与入口）
 *
 * 与现有 H5 的差异只在**存储与请求 API**（`uni.*` 替代 `localStorage`/`axios`），
 * 业务逻辑（校验 → 调登录 → 存 token → 进识别页）保持一致。
 */
import { computed, reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { t, locale } from '@/i18n'
// #ifdef APP-PLUS
import { apiBase, saveApiBase } from '@/utils/config'
// #endif

const auth = useAuthStore()
const form = reactive({ username: '', password: '' })
const loading = ref(false)

// #ifdef APP-PLUS
const serverShown = computed(() => apiBase())
// #endif

async function onSubmit() {
  if (loading.value) return
  const username = form.username.trim()
  if (!username || !form.password) {
    uni.showToast({ title: t('auth.usernameRequired'), icon: 'none' })
    return
  }
  loading.value = true
  try {
    await auth.login({ username, password: form.password })
    uni.showToast({ title: t('auth.loginSuccess'), icon: 'success' })
    setTimeout(() => {
      uni.reLaunch({ url: '/pages/detect/detect' })
    }, 300)
  } catch (error) {
    uni.showToast({ title: error.message || t('common.requestFailed'), icon: 'none' })
  } finally {
    loading.value = false
  }
}

function goRegister() {
  uni.navigateTo({ url: '/pages/register/register' })
}

function goForgot() {
  uni.navigateTo({ url: '/pages/forgot/forgot' })
}

/** 改服务器地址（仅 APP）：没有域名时只能连局域网 IP，且 IP 会变 */
async function editServer() {
  // #ifdef APP-PLUS
  const result = await uni.showModal({
    title: t('auth.serverEdit'),
    editable: true,
    placeholderText: t('auth.serverPlaceholder'),
    content: apiBase(),
    confirmText: t('common.confirm'),
    cancelText: t('common.cancel'),
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
</script>

<style scoped>
.page {
  min-height: 100vh;
  padding: 120rpx 40rpx 40rpx;
  box-sizing: border-box;
  background: #fff;
}

.brand {
  display: flex;
  align-items: center;
  gap: 20rpx;
}

.logo {
  width: 88rpx;
  height: 88rpx;
  border-radius: 24rpx;
  background: #e8f5ee;
  color: #2f855a;
  font-size: 44rpx;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.title {
  font-size: 44rpx;
  font-weight: 700;
  color: #1f2d26;
}

.subtitle {
  display: block;
  margin: 16rpx 0 56rpx;
  color: #8b9a91;
  font-size: 28rpx;
}

.field {
  border-bottom: 1rpx solid #eef1ef;
  padding: 24rpx 0;
  display: flex;
  align-items: center;
  gap: 24rpx;
}

.label {
  width: 120rpx;
  color: #55665a;
  font-size: 28rpx;
}

.input {
  flex: 1;
  font-size: 30rpx;
  height: 60rpx;
}

.ph {
  color: #b7c2bb;
}

.forgot {
  display: block;
  margin-top: 20rpx;
  text-align: right;
  color: #2f855a;
  font-size: 24rpx;
}

.btn-primary {
  margin-top: 40rpx;
}

.switch {
  margin-top: 32rpx;
  text-align: center;
  font-size: 26rpx;
}

.muted {
  color: #8b9a91;
}

.link {
  margin-left: 8rpx;
  color: #2f855a;
  font-weight: 600;
}

.tip {
  display: block;
  margin-top: 40rpx;
  text-align: center;
  color: #b7c2bb;
  font-size: 22rpx;
}

/* 第 232 批：APP 专属的服务器地址行（H5 不渲染） */
.server-row {
  margin: 56rpx 40rpx 0;
  padding: 20rpx 24rpx;
  display: flex;
  align-items: center;
  gap: 16rpx;
  border-radius: 16rpx;
  background: #f2f6f3;
}

.server-label {
  color: #8b9a91;
  font-size: 22rpx;
}

.server-value {
  flex: 1;
  color: #55665a;
  font-size: 22rpx;
  word-break: break-all;
}

.server-edit {
  color: #2f855a;
  font-size: 22rpx;
  font-weight: 600;
}
</style>
