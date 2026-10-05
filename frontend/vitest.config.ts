import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      // 第 109 批：去掉了原来那条 `src/_deprecated/**` —— 那个目录已删除
      // （删除前先建了版本控制，需要找回时 `git show 1f54f00:frontend/src/_deprecated/...`）。
      // 留一条指向不存在目录的排除规则，只会让后来的人去找它。
      exclude: [...configDefaults.exclude, 'e2e/**'],
      root: fileURLToPath(new URL('./', import.meta.url)),
    },
  }),
)
