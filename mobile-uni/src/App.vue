<script>
/**
 * 应用外壳（第 232 批）
 *
 * 只做两件事：全局样式 + 启动时确认"有没有登录态"。
 * 退出登录后回到登录页的逻辑不在这里 —— 由 `utils/request.js` 的 401 处理统一接管
 * （一个地方处理 401，才能在"多个页面同时请求"时不重复跳转）。
 */
export default {
  onLaunch() {
    // 有 token 就直接进识别页，省掉一次"闪一下登录页"
    try {
      const token = uni.getStorageSync('uni_token')
      if (token) {
        uni.reLaunch({ url: '/pages/detect/detect' })
      }
    } catch (error) {
      console.warn('[app] 读取登录态失败', error)
    }
  },
}
</script>

<style>
/* 全局样式：uni-app 的页面组件没有 <style> 作用域问题，这里只放最基础的 */
page {
  background-color: #f5f7f6;
  color: #1f2d26;
  font-size: 28rpx;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

button::after {
  border: none;
}

.card {
  background: #fff;
  border-radius: 24rpx;
  padding: 32rpx;
  margin: 24rpx;
  box-shadow: 0 4rpx 24rpx rgba(31, 99, 67, 0.06);
}

.btn-primary {
  background: #2f855a;
  color: #fff;
  border-radius: 999rpx;
  font-size: 32rpx;
  height: 92rpx;
  line-height: 92rpx;
}

.btn-primary[disabled] {
  opacity: 0.6;
}

.muted {
  color: #8b9a91;
}
</style>
