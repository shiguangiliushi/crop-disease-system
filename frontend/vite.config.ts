import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
// 临时禁用 VueDevTools
// import VueDevTools from 'vite-plugin-vue-devtools'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueJsx(),
    // VueDevTools(),  // 临时禁用
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
    extensions: ['.js', '.ts', '.jsx', '.tsx', '.json', '.vue'],
    // 第 51 批修复：强制 Vue 运行时相关包只保留**一份**实例。
    // 构建产物曾出现 "isFunction is not a function at defineComponent"：
    // vue-router 在模块求值期调用 defineComponent，而 @vue/shared 的 isFunction
    // 还没初始化 —— 根因是 Vue 内部包被拆到了不同的 chunk/实例上（构建里同时存在
    // 两份 @vue/shared）。dedupe 是官方推荐的处理方式。
    dedupe: ['vue', '@vue/shared', '@vue/runtime-core', '@vue/runtime-dom', '@vue/reactivity']
  },
  server: {
    port: 5173,
    host: true, // 监听所有网络接口
    strictPort: true,
    open: true, // 自动打开浏览器
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path  // 保留 /api 前缀
      },
      // 媒体文件代理配置
      '^/media/.*': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // 确保不重写路径
        rewrite: (path) => path
      }
    },
    fs: {
      strict: false, // 允许访问项目根目录外的文件
      allow: ['..']
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: true,
    // 拆包：把体积大且更新频率低的依赖单独成块，减小入口包体积、提升缓存命中率
    // （优化前入口包约 2.26MB / gzip 723KB）
    //
    // ⚠️ 第 51 批修复（严重）：**绝不能把 Vue 运行时单独拆成一块**。
    // 原来这里有一条 `return 'vue'` 把 `vue` / `@vue/*` / `vue-router` / `pinia`
    // 拆成独立的 `vue` chunk，结果构建产物一加载就白屏：
    //     TypeError: isFunction is not a function
    //     at defineComponent (assets/vue-*.js)
    // 原因是 `@vue/shared` 与 `@vue/runtime-core` 被 Rolldown 分别包装成惰性模块，
    // 拆到同一 chunk 后仍出现"初始化顺序早于定义"的情况（`defineComponent` 在模块求值期
    // 就被调用，而 `isFunction` 还没赋值）。
    // 现在把 Vue 及其直接依赖留在**唯一的 vendor chunk**里：只保留"叶子型"库的单向拆包
    // （element-plus / chart / editor / pdf 都只 import vendor，不会反向引用），
    // 从结构上消除这类初始化顺序问题。
    //
    // 教训：**构建能通过 ≠ 产物能跑**。本次是真正用浏览器打开 dist 才发现的
    // （此前每轮只跑 build-only 看"是否构建成功"）。
    rollupOptions: {
      // 第 51 批临时规避：见文件末尾的说明（rolldown-vite 的模块初始化顺序问题）
      treeshake: false,
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('element-plus') || id.includes('@element-plus')) return 'element-plus';
          if (id.includes('chart.js') || id.includes('vue-chartjs')) return 'chart';
          if (id.includes('quill') || id.includes('@vueup')) return 'editor';
          if (id.includes('jspdf') || id.includes('html2canvas')) return 'pdf';
          if (id.includes('bootstrap-icons')) return 'icons';
          if (id.includes('bootstrap')) return 'bootstrap';
          // vue / @vue/* / vue-router / pinia / axios 等一律进 vendor（见上面的说明）
          return 'vendor';
        }
      }
    }
  }
})
