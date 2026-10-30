# 端到端测试（E2E）

真实后端 + 真实浏览器。第 103 批建立 —— 此前 `npm run test:e2e` 是空壳（脚手架默认用例断言
"`h1` 等于 You did it!"），于是每批验证都靠一次性脚本、跑完即删，改动后无法确认"上次修的东西还活着"。
**这套 E2E 第一次跑就抓到一个真 bug**（见文末）。

## 一、怎么跑

```bash
# 后端必须先起（E2E 打真实后端 + 真实数据库）

cd backend && python manage.py runserver 127.0.0.1:8000

cd frontend
npm run e2e            # 只跑 chromium（推荐）
npm run e2e:headed     # 带界面，调试用
npm run e2e:all        # chromium + firefox
npx playwright test e2e/02-safety.spec.mjs    # 单个文件
npx playwright test -g "批量删除"              # 按用例名
npx playwright show-report                    # HTML 报告
```

**前端不用手动起**：`playwright.config.ts` 的 `webServer` 是数组，桌面端 5173 与移动端 5174
都会自动拉起，已在跑的复用。后端没起时不会一片 timeout，而是直接打印：

```
E2E 前置检查失败：后端没在 http://127.0.0.1:8000 上响应。
→ 先启动后端：cd backend && python manage.py runserver 127.0.0.1:8000
```

## 二、现有用例

> 用例条数以 `npx playwright test --list` 为准，别手抄数字。

| 文件 | 覆盖什么 | 为什么值得固化 |
|---|---|---|
| `01-smoke.spec.mjs` | 健康检查 / 路由守卫 / 登录成功 / 密码错误 / 夹具账号可用 | **第 0 层**：这层红了，后面的红都不值得看 |
| `02-safety.spec.mjs` | 存储型 XSS 不执行、`token-auth` 后门仍关着、注销护栏、注销冷静期 | 全是**真实事故**（91/95/101 批），且属"接口单测全绿、浏览器里仍出事" |
| `03-admin-users.spec.mjs` | 角色筛选清干净、筛选/分页进 URL、表头排序走后端、批量删除、非管理员进不去 | 这一页改得最多（76/88/95/98/100 批） |
| `04-detection.spec.mjs` | 上传图片 → 结果（置信度/病害名/history_id）、结果卡渲染、纠错落库、匿名不能识别 | **最核心链路**，跨 4 层（表单 → MultiPartParser → YOLO → 序列化） |
| `05-mobile.spec.mjs` | 移动端登录/忘记密码、底部导航、相机入口、token 失效自愈 | 移动端是**独立应用**（Vant，零代码共享），桌面全绿不代表它好 |
| `06-assistant.spec.mjs` | 问答接口契约（检索、引用编号、无来源不回答） | "没检索到就明说"这条约束最易被悄悄改掉 |
| `07-assistant-page.spec.mjs` | 问答页交互（提问 → 流式回答 → 引用展开、历史会话） | SSE 流式问题单测盖不住，只有真浏览器 + 真后端能暴露 |

## 三、写新用例的三条约定

三条都来自"一次性脚本"反复踩的坑，已封装在 `e2e/helpers.mjs`。

### 1. 自己造数据、自己清

```js
import { registerTempUser, cleanupByPrefix, cleanupDetections, runDjango } from './helpers.mjs';

test.afterAll(() => cleanupByPrefix());            // 按 zze2e 前缀扫，连 deleted_ 一起清
test.afterAll(() => cleanupDetections(createdDetectionIds));  // 识别记录只能靠 id 清
```

**统一前缀 `zze2e`**：清理按前缀走，绝不误删真实数据。注销后变成 `deleted_<id>`，`cleanupByPrefix()` 也扫这个前缀。
识别记录的 `detection_result` 是模型预测的病害名、不是我们造的数据，所以**必须记住自己的 `history_id`**。

### 2. 断言要能看懂

```js
expectThat('地址栏带 role 参数', roleParam, 'USER');   // 失败打印"期望 X，实际 Y"
assertNoProblems();                                    // 一次抛出全部失败项
```

不要用 `expect(x).toBe(y)` —— E2E 的排查成本主要在"到底拿到了什么"。诊断信息也塞进断言标签：
`` expectThat(`没有 JS 报错（实际：${JSON.stringify(errors)}）`, errors.length, 0) `` ——
浏览器只说"Failed to load resource: 404"，不说是哪个资源。

### 3. 登录态直接写存储，别每次都走登录表单

```js
const session = await login();          // 夹具账号，拿 token
await loginAs(page, session);           // 桌面端：sessionStorage
await loginAsMobile(page, session);     // 移动端：localStorage
```

只有**专门测登录**的用例才该填表单 —— 否则"登录坏了"会放大成"所有用例都红"。
**两端存储故意不同**，写错位置会得到"看起来已登录、接口全 401、然后跳登录页"：

| | 位置 | key |
|---|---|---|
| 桌面端 | `sessionStorage`（关标签页即登出） | `auth_token` / `user` |
| 移动端 | `localStorage`（手机每次重登不可接受） | `mobile_token` / `mobile_user` |

## 四、踩过的坑

| 现象 | 原因与解法 |
|---|---|
| `Element is outside of the viewport` | 管理页很长，行在折叠线以下。**用 DOM 点击**：`page.evaluate` 里 `element.click()`，不依赖几何 |
| `click()` 一直不点，日志反复 "visible, enabled and stable" | Element Plus `fixed="right"` 操作列的表格稳定性判定过不去。同上改 DOM 点击 |
| `check()` 勾了但界面没反应 | Element Plus 的 `selection-change` 只认 `.el-checkbox` 点击，原生 `check()` 不触发 |
| 索引连点两行只选到一行 | 多选会重排重渲染，按索引连点可能点到同一行（第二次反而取消）。**一条用例只勾一行** |
| 登录接口 **429** | 登录限流 10/分钟按 IP，用例多了必撞 —— 先 `clearThrottle()` 清零（清开发库缓存） |
| 等 `input[type="file"]` 可见 → 超时 | 上传入口都是**隐藏 input + 按钮转发**。`setInputFiles` 对隐藏 input 有效，别等可见 |
| 移动端 `.van-tabbar a` / `href*=` 都是 0 个 | `tabbar-item` 根节点不是 `<a>`、没有 `href`。**按可见文案点**（`hasText: '记录'`），也更贴近真实用户 |
| 断言"页面里没有 script 标签" | 页面**本来就有** script（Vite 注入）。检查范围缩到渲染正文的容器 |
| 断言"净化后标签应该消失" | 净化器只管**去掉可执行部分**：`<img src=x onerror=…>` 净化后是 `<img src="x">`，安全但标签还在。判据是"没执行 + 无事件属性 + 无 script" |
| 断言"页面上有'置信度'三个字" | 实际 UI 是可读判断（"很可能/较可能"）+ 百分比徽章，**没有这个词**。先看真实渲染再写断言 |
| 401 用例报"有 JS 报错" | token 失效本身会打一次 401，浏览器记为 console error —— **预期产物**。用 `watchPageErrors(page, { ignore: [/401/] })` 精确放行 |

### 接口响应形状别照着想象写

`04-detection` 第一版按 `data.diseases[]` 断言，实际是：

```js
{ status: 'success',
  data: { detection: { disease, disease_en, confidence, description,
                        prevention, original_image, annotated_image, bbox },
          history_id: 949 } }
```

**单个** `detection` 对象（前端 `DetectView` 自己包成数组给结果卡），记录 id 叫 `history_id`
（`detection_id` 是 `Feedback` 上的字段名）。写新接口断言前，先 `curl` 一次把真实响应打出来。

## 五、这套 E2E 第一次运行抓到的真 bug

`01-smoke` 的"匿名访问受保护页面会被送到登录页"首跑就红：匿名访问 `/admin/users`
**没有被重定向** —— 顶栏显示"登录 / 立即注册"，页面却是用户管理表格（空数据）。

根因是第 97 批的导航守卫：为"未保存修改的离开提醒"加的分支里，**放行时 `next(); return`**
把后面所有鉴权逻辑跳过了，于是 `requiresAuth` / `requiresAdmin` 在"有导航"时根本不执行。
修法是拦下时结束、放行时**不 return**，让控制流走完鉴权。

> 这条 bug 活了 6 批（97→103）：后端权限**没有**被绕过（接口仍 401/403），
> 但前端把管理页渲染给了匿名用户 —— "防线只剩一层"。
> 能活这么久的原因很直白：**当时没有任何自动化测试会去打这个 URL**，这正是建立常驻 E2E 的理由。
