import process from 'node:process'
import { defineConfig, devices } from '@playwright/test'

/**
 * E2E 配置（第 103 批重写）
 * ============================================================================
 * 这个文件原来是脚手架生成的默认值，配套的 `e2e/vue.spec.ts` 还在断言
 * `h1` 等于 "You did it!"（Vite 模板的欢迎语）—— 也就是说
 * `npm run test:e2e` 从来没验证过这个项目的任何功能。
 *
 * 现在的约定：
 *   · **后端必须已在跑**（8000）。E2E 打的是真实后端 + 真实数据库，
 *     没跑的话 `globalSetup` 会给出明确提示，而不是让每个用例超时后一片红。
 *   · 默认只用 chromium：多浏览器对"验证功能对不对"没有增量价值，
 *     却让每次执行慢三倍。要跨浏览器时用 `--project=firefox` 单独跑。
 *   · **数据自造自清**：用例自己注册临时账号、跑完删掉（见 e2e/helpers.mjs）。
 *     所以这套用例可以直接对着开发库跑，不会污染真实数据。
 *   · reporter 默认 `list`（终端能直接看懂）。要 HTML 报告用 `--reporter=html`。
 * ============================================================================
 */

/** 后端地址（用例里直接打接口时用；与前端 vite 的 proxy 目标一致） */
export const API_BASE = process.env.E2E_API_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  testDir: './e2e',
  // 只收 *.spec.mjs：helpers / fixtures 不是用例
  testMatch: /.*\.spec\.mjs$/,
  /* 单条用例 45s：识别相关的接口在 CPU 上偶尔偏慢，30s 会假红 */
  timeout: 45 * 1000,
  expect: { timeout: 8000 },

  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  /* 用例之间会共用同一个开发库里的数据，串行跑更稳（也更好读日志） */
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',

  globalSetup: './e2e/global-setup.mjs',

  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5173',
    actionTimeout: 15 * 1000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    headless: process.env.E2E_HEADED ? false : true,
    locale: 'zh-CN',
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    // 需要跨浏览器时显式指定：npx playwright test --project=firefox
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
  ],

  /* 自动拉起**两个**前端；后端必须已经在跑（见文件头说明）。
     ⚠️ webServer 支持数组：之前只拉了桌面端的 5173，于是移动端用例（05-mobile）
        必须人手去 `cd mobile && npm run dev` —— "忘了起"会表现成一堆莫名其妙的失败。
        这里两个一起拉，`reuseExistingServer` 保证已经在跑的直接复用。 */
  webServer: [
    {
      command: 'npm run dev',
      port: 5173,
      reuseExistingServer: true,
      timeout: 60 * 1000,
    },
    {
      // 移动端是独立应用（mobile/，Vant，与桌面端零代码共享）
      command: 'npm --prefix ../mobile run dev',
      port: 5174,
      reuseExistingServer: true,
      timeout: 60 * 1000,
    },
  ],
})
