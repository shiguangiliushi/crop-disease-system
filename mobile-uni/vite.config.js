import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'

/**
 * uni-app（Vue3 + Vite）配置
 *
 * ## 端口为什么是 5175
 *
 * 桌面端 5173、现有 H5 移动端 5174 —— uni-app 这份要能**同时**跑起来对照，
 * 所以固定 5175（`strictPort: true`：被占用就直接报错，而不是悄悄换一个端口）。
 *
 * ## 代理只给 H5 开发用
 *
 * H5 走 vite 代理到本机 Django，避免 CORS；**小程序/APP 没有代理**，
 * 那边要用 `VITE_API_BASE` 指到可访问的绝对地址（小程序还必须是 HTTPS 域名）。
 */
export default defineConfig({
  plugins: [uni()],
  server: {
    port: 5175,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '^/media/.*': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
