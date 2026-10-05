import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      // src/_deprecated 是已停用的备份目录（见该目录 README），其中的脚手架测试不应再参与扫描
      exclude: [...configDefaults.exclude, 'e2e/**', 'src/_deprecated/**'],
      root: fileURLToPath(new URL('./', import.meta.url)),
    },
  }),
)
