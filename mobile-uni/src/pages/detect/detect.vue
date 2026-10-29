<template>
  <view class="page">
    <view class="header">
      <view>
        <text class="hello">你好，{{ auth.username || '种植户' }}</text>
        <text class="hint">拍一张叶片照片，几秒内给出病害与防治建议</text>
      </view>
      <text class="logout" @click="onLogout">退出</text>
    </view>

    <view class="card picker" @click="choose('camera')">
      <view v-if="!imagePath" class="empty">
        <text class="empty-icon">📷</text>
        <text class="empty-title">点击拍照</text>
        <text class="empty-sub">也可以从相册选一张</text>
      </view>
      <image v-else :src="imagePath" mode="aspectFit" class="preview" />
    </view>

    <view class="actions">
      <button class="btn-ghost" :disabled="loading" @click="choose('camera')">拍照</button>
      <button class="btn-ghost" :disabled="loading" @click="choose('album')">从相册选</button>
    </view>

    <button class="btn-primary" :disabled="!imagePath || loading" @click="onDetect">
      {{ loading ? '识别中…' : '开始识别' }}
    </button>

    <text class="tip">支持 JPG / PNG，单张不超过 5MB；结果仅供参考。</text>

    <!-- 第 236 批：三个主页（识别 / 历史 / 我的）用同一个底部导航 -->
    <BottomNav current="detect" />
  </view>
</template>

<script setup>
/**
 * 识别页（第 232 批）—— 整个 APP 的核心，先做它
 *
 * 相机/相册统一走 `uni.chooseImage`：小程序没有 `getUserMedia`，
 * 现有 H5 的实时取景（`camera.js`）在小程序端**无法复用**，这是当初评估里就点明的
 * "UI 层要重写"的一部分。uni-app 这里一次调用三端都能用。
 */
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import BottomNav from '@/components/BottomNav.vue'
import { useAuthStore } from '@/stores/auth'
import { detectImage } from '@/utils/api'
import { TOKEN_KEY } from '@/utils/request'

const auth = useAuthStore()
const imagePath = ref('')
const loading = ref(false)

onShow(() => {
  // 没有登录态就别停在识别页（App.onLaunch 之外的兜底）
  const token = uni.getStorageSync(TOKEN_KEY)
  if (!token) {
    uni.reLaunch({ url: '/pages/login/login' })
  }
})

function choose(sourceType) {
  if (loading.value) return
  uni.chooseImage({
    count: 1,
    sizeType: ['compressed'],
    sourceType: [sourceType],
    success: (res) => {
      const [path] = res.tempFilePaths || []
      if (path) imagePath.value = path
    },
    fail: (error) => {
      // 用户点"取消"也会走 fail —— 不弹提示，别烦人
      if ((error.errMsg || '').includes('cancel')) return
      uni.showToast({ title: '打开相机/相册失败', icon: 'none' })
    },
  })
}

async function onDetect() {
  if (!imagePath.value || loading.value) return
  loading.value = true
  uni.showLoading({ title: '识别中…', mask: true })
  try {
    const data = await detectImage(imagePath.value)
    uni.setStorageSync('last_result', data)
    uni.navigateTo({ url: '/pages/result/result' })
  } catch (error) {
    uni.showToast({ title: error.message || '识别失败', icon: 'none' })
  } finally {
    uni.hideLoading()
    loading.value = false
  }
}

async function onLogout() {
  const { confirm } = await uni.showModal({
    title: '退出登录',
    content: '退出后需要重新输入账号密码',
  })
  if (!confirm) return
  await auth.logout()
  uni.reLaunch({ url: '/pages/login/login' })
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  /* 第 236 批：底部导航是 fixed，留出它的高度（+ 安全区） */
  padding: 24rpx 0 calc(150rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
}

.header {
  padding: 8rpx 40rpx 24rpx;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.hello {
  display: block;
  font-size: 40rpx;
  font-weight: 700;
}

.hint {
  display: block;
  margin-top: 8rpx;
  color: #8b9a91;
  font-size: 24rpx;
}

.logout {
  color: #8b9a91;
  font-size: 26rpx;
  padding: 8rpx 0 8rpx 24rpx;
}

.picker {
  height: 620rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12rpx;
}

.empty-icon {
  font-size: 88rpx;
}

.empty-title {
  font-size: 32rpx;
  font-weight: 600;
}

.empty-sub {
  font-size: 24rpx;
  color: #8b9a91;
}

.preview {
  width: 100%;
  height: 100%;
}

.actions {
  display: flex;
  gap: 24rpx;
  padding: 8rpx 40rpx;
}

.btn-ghost {
  flex: 1;
  background: #eef1ef;
  color: #2f855a;
  border-radius: 999rpx;
  font-size: 28rpx;
  height: 80rpx;
  line-height: 80rpx;
}

.btn-primary {
  margin: 40rpx;
}

.tip {
  display: block;
  text-align: center;
  color: #b7c2bb;
  font-size: 22rpx;
}
</style>
