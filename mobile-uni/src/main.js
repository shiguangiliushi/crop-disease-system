import { createSSRApp } from 'vue'
import * as Pinia from 'pinia'
import App from './App.vue'

/**
 * uni-app 的入口（第 232 批）
 *
 * ⚠️ 与普通 Vue3 项目不同：必须导出 `createApp()`，并且**把 Pinia 一起返回**
 *    （`return { app, Pinia }`）—— 这是 uni-app 的多端运行时约定，
 *    直接 `app.use(createPinia())` 在小程序端会拿不到 store。
 */
export function createApp() {
  const app = createSSRApp(App)
  app.use(Pinia.createPinia())
  return { app, Pinia }
}
