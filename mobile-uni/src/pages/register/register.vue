<template>
  <view class="page">
    <view class="head">
      <text class="title">{{ t('auth.registerTitle') }}</text>
      <text class="subtitle">{{ t('auth.registerSubtitle') }}</text>
    </view>

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
        />
      </view>
      <view class="field">
        <text class="label">{{ t('auth.confirmPassword') }}</text>
        <input
          v-model="form.confirmPassword"
          class="input"
          password
          :placeholder="t('auth.confirmPasswordPlaceholder')"
          placeholder-class="ph"
          :disabled="loading"
        />
      </view>
      <view class="field">
        <text class="label">{{ t('auth.email') }}</text>
        <input
          v-model="form.email"
          class="input"
          type="text"
          :placeholder="t('auth.emailPlaceholder')"
          placeholder-class="ph"
          :disabled="loading"
        />
      </view>

      <!-- 第 233 批：注册强制校验验证码（后端拒绝无码请求），这里必须带上 -->
      <view class="field">
        <text class="label">{{ t('auth.captcha') }}</text>
        <input
          v-model="form.captchaCode"
          class="input"
          maxlength="4"
          :placeholder="t('auth.captchaPlaceholder')"
          placeholder-class="ph"
          :disabled="loading"
        />
        <view class="captcha-box" @click="loadCaptcha">
          <image v-if="captcha.image" :src="captcha.image" class="captcha-image" mode="aspectFill" />
          <text v-else class="captcha-loading">…</text>
        </view>
      </view>
      <text class="captcha-hint" @click="loadCaptcha">{{ t('auth.captchaRefresh') }}</text>

      <button class="btn-primary" :disabled="loading" @click="onSubmit">
        {{ loading ? t('auth.registering') : t('auth.register') }}
      </button>
    </view>

    <view class="switch">
      <text class="muted">{{ t('auth.haveAccount') }}</text>
      <text class="link" @click="goLogin">{{ t('auth.backToLogin') }}</text>
    </view>
  </view>
</template>

<script setup>
/**
 * 注册页（第 237 批）
 *
 * 与 H5 一致的三条规则：
 *   · 密码至少 8 位且不能纯数字（真源在后端 `password_policy.py`，前端只提前拦）；
 *   · **必须过验证码**（第 233 批后端已强制，无码直接 400）；
 *   · 注册成功即登录（后端随注册响应签发 token），直接进识别页。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { t } from '@/i18n'
import { fetchCaptcha } from '@/api/auth'
import { register } from '@/utils/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const form = reactive({ username: '', password: '', confirmPassword: '', email: '', captchaCode: '' })
const captcha = ref({ id: '', image: '' })
const loading = ref(false)

const captchaReady = computed(() => Boolean(captcha.value.id))

async function loadCaptcha() {
  try {
    const data = await fetchCaptcha()
    captcha.value = { id: data.id, image: data.image }
    form.captchaCode = ''
  } catch (error) {
    console.warn('[register] 加载验证码失败', error)
  }
}

onMounted(loadCaptcha)

async function onSubmit() {
  if (loading.value) return
  const username = form.username.trim()
  if (!username) {
    uni.showToast({ title: t('auth.usernameRequired'), icon: 'none' })
    return
  }
  const password = form.password || ''
  if (password.length < 8) {
    uni.showToast({ title: t('auth.passwordTooShort'), icon: 'none' })
    return
  }
  if (/^\d+$/.test(password)) {
    uni.showToast({ title: t('auth.passwordTooShort'), icon: 'none' })
    return
  }
  if (form.confirmPassword !== password) {
    uni.showToast({ title: t('auth.passwordMismatch'), icon: 'none' })
    return
  }
  if (!form.captchaCode.trim()) {
    uni.showToast({ title: t('auth.captchaRequired'), icon: 'none' })
    return
  }

  loading.value = true
  try {
    const result = await register({
      username,
      password,
      email: form.email.trim(),
      captchaId: captcha.value.id,
      captchaCode: form.captchaCode.trim(),
    })
    if (result.token && result.user) {
      // 注册即登录：把凭证存进 store，直接进识别页
      await auth.adopt({ user: result.user, token: result.token })
      uni.showToast({ title: t('auth.loginSuccess'), icon: 'success' })
      setTimeout(() => uni.reLaunch({ url: '/pages/detect/detect' }), 300)
    } else {
      uni.showToast({ title: t('auth.registerSuccess'), icon: 'success' })
      setTimeout(() => uni.reLaunch({ url: '/pages/login/login' }), 300)
    }
  } catch (error) {
    // 验证码错/过期：换一张再让用户填（旧码已被服务端消费）
    if (/验证码|captcha/i.test(error.message || '')) {
      loadCaptcha()
      uni.showToast({ title: t('auth.captchaWrong'), icon: 'none' })
    } else {
      uni.showToast({ title: error.message || t('common.requestFailed'), icon: 'none' })
    }
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
  padding: 20rpx 0;
  display: flex;
  align-items: center;
  gap: 20rpx;
}

.label {
  width: 150rpx;
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

.captcha-box {
  width: 150rpx;
  height: 60rpx;
  border: 1rpx solid rgba(47, 133, 90, 0.18);
  border-radius: 8rpx;
  background: #f4f8f5;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.captcha-image {
  width: 100%;
  height: 100%;
}

.captcha-loading {
  color: #8b9a91;
  font-size: 24rpx;
}

.captcha-hint {
  display: block;
  margin-top: 12rpx;
  text-align: right;
  color: #2f855a;
  font-size: 22rpx;
}

.btn-primary {
  margin-top: 36rpx;
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
</style>
