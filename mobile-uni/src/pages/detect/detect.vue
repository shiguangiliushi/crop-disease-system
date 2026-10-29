<template>
  <view class="page">
    <view class="header">
      <view>
        <text class="hello">{{ auth.username || t('mine.guest') }}</text>
        <text class="hint">{{ t('detect.tip3') }}</text>
      </view>
      <text class="logout" @click="onLogout">{{ t('mine.logout') }}</text>
    </view>

    <view v-if="pendingCount" class="pending" @click="syncQueue">
      <text class="pending-text">{{ t('offline.pendingSync', { count: pendingCount }) }}</text>
      <text class="pending-action">{{ t('common.retry') }}</text>
    </view>

    <view class="card picker" @click="choose('camera')">
      <view v-if="!imagePath" class="empty">
        <text class="empty-icon">📷</text>
        <text class="empty-title">{{ t('detect.takePhoto') }}</text>
        <text class="empty-sub">{{ t('detect.galleryHint') }}</text>
      </view>
      <image v-else :src="imagePath" mode="aspectFit" class="preview" />
    </view>

    <view class="actions">
      <button class="btn-ghost" :disabled="loading" @click="choose('camera')">{{ t('detect.takePhoto') }}</button>
      <button class="btn-ghost" :disabled="loading" @click="choose('album')">{{ t('detect.fromGallery') }}</button>
    </view>

    <button class="btn-primary" :disabled="!imagePath || loading" @click="onDetect">
      {{ loading ? t('detect.analyzing') : t('detect.start') }}
    </button>

    <text class="tip">{{ t('result.disclaimer') }}</text>

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
import { t } from '@/i18n'
import { compressForUpload, fileSizeOf } from '@/utils/image'
import { enqueue, pending, syncAll } from '@/utils/offlineQueue'
import { onShow } from '@dcloudio/uni-app'
import BottomNav from '@/components/BottomNav.vue'
import { useAuthStore } from '@/stores/auth'
import { detectImage } from '@/utils/api'
import { TOKEN_KEY } from '@/utils/request'

const auth = useAuthStore()
const imagePath = ref('')
const loading = ref(false)
const pendingCount = ref(0)

onShow(() => {
  // 没有登录态就别停在识别页（App.onLaunch 之外的兜底）
  const token = uni.getStorageSync(TOKEN_KEY)
  if (!token) {
    uni.reLaunch({ url: '/pages/login/login' })
    return
  }
  pendingCount.value = pending().length
  if (pendingCount.value) syncQueue()
})

uni.onNetworkStatusChange((status) => {
  if (status.isConnected && pendingCount.value) syncQueue()
})

function choose(sourceType) {
  if (loading.value) return
  uni.chooseImage({
    count: 1,
    sizeType: ['compressed'],
    sourceType: [sourceType],
    success: async (res) => {
      const [path] = res.tempFilePaths || []
      if (!path) return
      // 第 239 批：先压缩再上传（压不了就用原图，不影响流程）
      const compressed = await compressForUpload(path)
      const size = await fileSizeOf(compressed)
      if (size > 5 * 1024 * 1024) {
        uni.showToast({ title: t('detect.imageTooLarge'), icon: 'none' })
        return
      }
      imagePath.value = compressed
    },
    fail: (error) => {
      // 用户点"取消"也会走 fail —— 不弹提示，别烦人
      if ((error.errMsg || '').includes('cancel')) return
      uni.showToast({ title: t('detect.failed'), icon: 'none' })
    },
  })
}

async function onDetect() {
  if (!imagePath.value || loading.value) return
  loading.value = true
  uni.showLoading({ title: t('detect.analyzing'), mask: true })
  try {
    const data = await detectImage(imagePath.value)
    uni.setStorageSync('last_result', data)
    uni.navigateTo({ url: '/pages/result/result' })
  } catch (error) {
    // 第 239 批：网络/服务异常时把图记进补传队列，恢复网络后自动补传
    enqueue(imagePath.value)
    pendingCount.value = pending().length
    uni.showToast({ title: t('detect.offline'), icon: 'none' })
  } finally {
    uni.hideLoading()
    loading.value = false
  }
}

/**
 * 把本地待补传的图逐张重试（第 239 批）
 *
 * 成功即出队、失败保留 —— 不因为一张图失败把后面都丢掉。
 */
async function syncQueue() {
  if (!pendingCount.value || loading.value) return
  loading.value = true
  try {
    const result = await syncAll(async (path) => {
      const data = await detectImage(path)
      uni.setStorageSync('last_result', data)
    })
    pendingCount.value = pending().length
    if (result.ok) uni.showToast({ title: t('offline.synced', { count: result.ok }), icon: 'none' })
    else if (result.failed) uni.showToast({ title: t('offline.syncFailed'), icon: 'none' })
  } finally {
    loading.value = false
  }
}

async function onLogout() {
  const { confirm } = await uni.showModal({
    title: t('mine.logout'),
    content: t('mine.logoutConfirm'),
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

.pending {
  margin: 0 40rpx 16rpx;
  padding: 16rpx 24rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-radius: 16rpx;
  background: #fff8e6;
}

.pending-text {
  color: #8a6d1f;
  font-size: 24rpx;
}

.pending-action {
  color: #2f855a;
  font-size: 24rpx;
  font-weight: 600;
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
