import { globalIgnores } from 'eslint/config'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'
import pluginVitest from '@vitest/eslint-plugin'
import pluginPlaywright from 'eslint-plugin-playwright'
import pluginOxlint from 'eslint-plugin-oxlint'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'

// To allow more languages other than `ts` in `.vue` files, uncomment the following lines:
// import { configureVueProject } from '@vue/eslint-config-typescript'
// configureVueProject({ scriptLangs: ['ts', 'tsx'] })
// More info at https://github.com/vuejs/eslint-config-typescript/#advanced-setup

export default defineConfigWithVueTs(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue}'],
  },

  globalIgnores(['**/dist/**', '**/dist-ssr/**', '**/coverage/**']),

  pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended,

  // 第 396 批：本项目**全部是 JS**（74 个 .vue 文件统一用 `<script setup>` / `<script>`，
  // 没有 lang 属性）。`vueTsConfigs` 默认要求 `lang="ts"`，于是每个文件都报一条
  // `vue/block-lang` —— 74 条错误全是这一条规则造成的噪声，把真正的告警淹掉了。
  // 这里显式关掉它；**将来若迁到 TS，删掉这一段**（并用上面注释里的 configureVueProject）。
  {
    name: 'app/js-only-vue-blocks',
    files: ['**/*.vue'],
    rules: {
      'vue/block-lang': 'off',
    },
  },

  {
    ...pluginVitest.configs.recommended,
    files: ['src/**/__tests__/*'],
  },
  
  {
    ...pluginPlaywright.configs['flat/recommended'],
    files: ['e2e/**/*.{test,spec}.{js,ts,jsx,tsx}'],
  },
  ...pluginOxlint.configs['flat/recommended'],
  skipFormatting,
)
