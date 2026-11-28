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
    // 第 439 批：**无论有没有登录态都先落到识别页**。
    //   · 有 token → 直接可用（与改动前一致）；
    //   · 没有 token → 识别页会先自动开一个游客试用（`pages/detect` 的 onShow），
    //     开不了（试用关闭 / 没网）才把人送回登录页。
    // 改前没有 token 时停在第一页（登录表单）—— 新用户打开 App 第一眼就是
    // "输账号密码"，而他要的只是拍张叶子照片。
    uni.reLaunch({ url: '/pages/detect/detect' })
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
  background: #2a7f53;
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
