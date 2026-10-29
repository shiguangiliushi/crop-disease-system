<template>
  <view class="bottom-nav">
    <view
      v-for="item in items"
      :key="item.key"
      class="nav-item"
      :class="{ 'is-active': item.key === current }"
      @click="go(item)"
    >
      <text class="nav-icon">{{ item.icon }}</text>
      <text class="nav-label">{{ item.label }}</text>
    </view>
  </view>
</template>

<script setup>
/**
 * 底部导航（第 236 批）
 *
 * 为什么不用 `pages.json` 的 tabBar：
 *   · tabBar 的图标要 PNG 资源，这套代码目前**没有图标文件**（也不想为 3 个图标塞几张图进包）；
 *   · tabBar 页面之间只能用 `switchTab`，而"识别 → 结果"是 `navigateTo` 的普通页面，
 *     混用会让返回栈变得难以预测。
 * 所以用自定义组件 + `uni.reLaunch`：三个主页互相切换时清空页面栈，行为可预期。
 */
const props = defineProps({
  current: { type: String, default: 'detect' },
})

const items = [
  { key: 'detect', icon: '📷', label: '识别', path: '/pages/detect/detect' },
  { key: 'history', icon: '🗂', label: '历史', path: '/pages/history/history' },
  { key: 'mine', icon: '👤', label: '我的', path: '/pages/mine/mine' },
]

function go(item) {
  if (item.key === props.current) return
  uni.reLaunch({ url: item.path })
}
</script>

<style scoped>
.bottom-nav {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  background: #fff;
  border-top: 1rpx solid #eef1ef;
  padding-bottom: env(safe-area-inset-bottom);
  z-index: 10;
}

.nav-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4rpx;
  padding: 12rpx 0 10rpx;
  color: #8b9a91;
}

.nav-item.is-active {
  color: #2f855a;
}

.nav-icon {
  font-size: 34rpx;
  line-height: 1;
}

.nav-label {
  font-size: 20rpx;
}
</style>
