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

    <!-- #ifdef APP-PLUS -->
    <!-- 第 232 批：APK 里没有 vite 代理，必须连局域网 IP；把地址做成可改的，
         换 Wi-Fi 时不必重新打包（H5 走代理，不显示这一行） -->
    <view class="server-row" @click="editServer">
      <text class="server-label">服务器</text>
      <text class="server-value">{{ serverShown }}</text>
      <text class="server-edit">修改</text>
    </view>
    <!-- #endif -->
  </view>
</template>

<script setup>
/**
 * 登录页（第 232 批）
 *
 * 与现有 H5 的差异只在**存储与请求 API**（`uni.*` 替代 `localStorage`/`axios`），
 * 业务逻辑（校验 → 调登录 → 存 token → 进识别页）保持一模一样。
 */
import { computed, reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
// #ifdef APP-PLUS
import { apiBase, saveApiBase } from '@/utils/config'
// #endif

const auth = useAuthStore()
const form = reactive({ username: '', password: '' })
const loading = ref(false)

// #ifdef APP-PLUS
const serverShown = computed(() => apiBase())
// #endif

/**
 * 改服务器地址（仅 APP）。没有域名时 APK 只能连 `http://<电脑IP>:8000/api`，
 * 而电脑 IP 会随网络变化 —— 所以做成运行时可改，而不是写死在包里。
 */
async function editServer() {
  // #ifdef APP-PLUS
  const result = await uni.showModal({
    title: '服务器地址',
    editable: true,
    placeholderText: 'http://192.168.1.20:8000/api',
    content: apiBase(),
    confirmText: '保存',
    cancelText: '取消',
  })
  if (!result.confirm) return
  const value = String(result.content || '').trim()
  if (!/^https?:\/\//i.test(value)) {
    uni.showToast({ title: '请填写 http(s):// 开头的地址', icon: 'none' })
    return
  }
  saveApiBase(value)
  uni.showToast({ title: '已保存', icon: 'success' })
  // #endif
}

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
