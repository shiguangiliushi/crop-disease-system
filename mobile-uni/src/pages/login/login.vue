<template>
  <view class="page">
    <view class="brand">
      <view class="logo">叶</view>
      <text class="title">农作物病害识别</text>
    </view>
    <text class="subtitle">登录后即可拍照识别病虫害</text>

    <view class="card">
      <view class="field">
        <text class="label">用户名</text>
        <input
          v-model="form.username"
          class="input"
          placeholder="请输入用户名"
          placeholder-class="ph"
          :disabled="loading"
        />
      </view>
      <view class="field">
        <text class="label">密码</text>
        <input
          v-model="form.password"
          class="input"
          password
          placeholder="请输入密码"
          placeholder-class="ph"
          :disabled="loading"
          @confirm="onSubmit"
        />
      </view>

      <button class="btn-primary" :disabled="loading" @click="onSubmit">
        {{ loading ? '登录中…' : '登录' }}
      </button>
    </view>

    <text class="tip">识别结果仅供参考，实际防治请以当地植保部门意见为准。</text>
  </view>
</template>

<script setup>
/**
 * 登录页（第 232 批）
 *
 * 与现有 H5 的差异只在**存储与请求 API**（`uni.*` 替代 `localStorage`/`axios`），
 * 业务逻辑（校验 → 调登录 → 存 token → 进识别页）保持一模一样。
 */
import { reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const form = reactive({ username: '', password: '' })
const loading = ref(false)

async function onSubmit() {
  if (loading.value) return
  const username = form.username.trim()
  if (!username || !form.password) {
    uni.showToast({ title: '请填写用户名和密码', icon: 'none' })
    return
  }
  loading.value = true
  try {
    await auth.login({ username, password: form.password })
    uni.showToast({ title: '登录成功', icon: 'success' })
    setTimeout(() => {
      uni.reLaunch({ url: '/pages/detect/detect' })
    }, 300)
  } catch (error) {
    uni.showToast({ title: error.message || '登录失败', icon: 'none' })
  } finally {
    loading.value = false
  }
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

.btn-primary {
  margin-top: 56rpx;
}

.tip {
  display: block;
  margin-top: 40rpx;
  text-align: center;
  color: #b7c2bb;
  font-size: 22rpx;
}
</style>
