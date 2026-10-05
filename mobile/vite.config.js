import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * 移动端（H5）独立工程
 * ----------------------------------------------------------------------------
 * 与桌面客户端（frontend/）的关系：**两个工程、同一个后端**。
 *   · 客户端 frontend  → 5173，面向大屏（管理、论坛、批量操作）
 *   · 移动端 mobile    → 5174，面向农户手机（拍照识别、识别记录、我的）
 * 二者不共享代码、不共享构建，只共享 `/api` 契约 —— 拆开的好处是
 * 移动端的重构/样式不会波及桌面端，反之亦然。
 *
 * host: true 是**必须**的：农户要能用手机连同一局域网访问
 * `http://<电脑IP>:5174` 实测。但要记住浏览器的一条硬限制：
 * **非 https 的局域网地址不暴露 navigator.mediaDevices**，
 * 所以那种访问方式下"页面内拍照"会不可用，会自动降级为系统相机
 * （见 src/utils/camera.js 与 src/components/CameraCapture.vue）。
 */
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
    extensions: ['.js', '.json', '.vue']
  },
  server: {
    port: 5174,
    // 显式绑 IPv4 全网卡（而不是 host: true 解析出的 `::`）。
    // 原因：`host: true` 在 Windows 上监听的是 `::`，能否被手机的 IPv4 请求命中
    // 取决于双栈（IPv4-mapped）行为；写死 0.0.0.0 后 netstat 里能直接看到
    // `0.0.0.0:5174`，排障时不用再猜"到底有没有监听 IPv4"。
    host: '0.0.0.0',
    strictPort: true,
    // 开发期走代理：手机访问的是 dev server，由它转发到本机 Django，
    // 这样手机端不需要在本机跑后端、也不会撞 CORS，图片（/media）同理。
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '^/media/.*': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: true
  }
})
