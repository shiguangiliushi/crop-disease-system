# 桌面客户端（frontend/）

> 作物病害识别系统的桌面端：**Vue 3 + Element Plus + Vite**，默认跑在 `http://127.0.0.1:5173`。
> 后端是 `../backend`（Django，`http://127.0.0.1:8000`）；移动端是**另一个独立工程** `../mobile`。
>
> ⚠️ 本文件在第 153 批之前是 **Vite 脚手架自带的模板**（标题是 `# .`），
> 里面写的 `npm run test:e2e -- tests/example.spec.ts` 之类**在这个项目里跑不通** ——
> E2E 实际在 `e2e/*.spec.mjs`，说明见 [`e2e/README.md`](e2e/README.md)。现重写为真实说明。

## 快速开始

```bash
npm install
npm run dev          # http://127.0.0.1:5173（需要后端已在 8000 端口运行）
```

## 命令一览

| 命令 | 作用 |
|---|---|
| `npm run dev` | 开发服务器（Vite，端口 5173） |
| `npm run build` | 类型检查 + 生产构建（`run-p type-check build-only`） |
| `npm run type-check` | `vue-tsc --build`（`.vue` 里的类型错误） |
| `npm run test:unit` | Vitest 单元测试（82 条） |
| `npm run check` | **5 条一致性检查**（见下） |
| `npm run e2e` | Playwright 端到端（`--project=chromium`） |
| `npm run smoke` | 冒烟脚本（`--no-ui` 只测接口） |
| `npm run lint` / `format` | oxlint + eslint / prettier |

### `npm run check` 检查什么

| 检查 | 为什么存在 |
|---|---|
| `check:i18n-en` | 英文语言包里不能残留中文（漏译最难靠肉眼发现） |
| `check:i18n-consistency` | 中英两侧不能一字不差、核心术语译法要一致 |
| `check:components` | 模板里用到的 Element Plus 组件必须**已注册** —— 本项目按需注册，漏一个就是"页面空白" |
| `check:doc-titles` | **每条路由都要有 `docTitle` 文案**：它是按路由名动态查的，缺了不报错、只在控制台留一句警告 |

两条相关的辅助工具在仓库级 `docs/tools/`：
`check_i18n_coverage.py`（模板里还有多少裸露中文，当前 **0 条**；ICP 备案号一类走白名单）、
`check_line_endings.py`（行尾一律 LF）。

## 目录

```
src/
  api/         按后端模块拆的接口封装（每个文件对应一组端点）
  components/  通用组件（含 AdminLayout —— 管理后台外壳）
  composables/ 组合式函数（useQueryState 把筛选/分页同步进 URL 等）
  i18n/        messages.js（中英两份），键名与页面/命名空间对应
  router/      路由表 + 权限守卫（meta.capability / meta.modules）
  stores/      Pinia（auth.js 是能力与登录态的唯一来源）
  views/       页面（Admin*.vue 共 9 个是管理后台的页面）
e2e/           Playwright 用例（5 个 spec）
scripts/       按批留证的验证脚本（verify-*.mjs，24 个）与检查脚本
```

## 几条这个工程特有的约定

1. **登录态存在 `sessionStorage`（键 `auth_token`）**，移动端才用 `localStorage`（`mobile_token`）——
   写错地方会表现成"看起来已登录、接口全 401"。
2. **重复登录会让旧 token 立即失效**（第 94 批起登录会轮换并删除旧 Token）：
   写端到端脚本时别在同一个浏览器上下文里重新登录同一个账号。
3. **权限判定只认 `stores/auth.js`**：`hasCapability()`（4 档能力）与 `hasContentModule()`（5 个内容模块）。
   页面用 `meta.capability` / `meta.modules`（任一命中）声明准入，侧栏同步过滤；
   **真正的门禁在后端**，前端只是别让人白开一个空页面。
4. **筛选与分页进 URL**（`composables/useQueryState`）：新增筛选条件时记得登记，
   否则刷新/分享链接会丢（第 100 批踩过：排序没登记 → "点了表头没反应"）。
5. **Element Plus 按需注册**：新用到的组件要登记，否则 `npm run check` 会拦下（这是刻意的）。
6. **改完顺手跑 `npm run check` 与 `npm run test:unit`**；界面有改动再跑对应的 `scripts/verify-*.mjs`。
