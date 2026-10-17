# 端到端测试（E2E）

> 第 103 批建立。在此之前 `npm run test:e2e` 是个**空壳**：
> 配置文件是 Vite 脚手架默认值，唯一的用例 `e2e/vue.spec.ts` 断言
> `h1` 等于 `"You did it!"`（模板的欢迎语）—— 也就是说这条命令**从来没验证过本项目的任何功能**。
>
> 结果就是：第 91~102 批期间为了验证功能，写了十几个"一次性脚本"，跑完就删。
> 每次都要重新踩同样的坑（选择器怎么写、限流怎么绕、数据怎么清），
> 而且**没法在改动之后再确认"上次修的东西还活着"**。
> 第 103 批的 E2E 一上来就抓到了一个真 bug（见文末），这就是它的价值。

---

## 一、怎么跑

```bash
# 后端必须先跑起来（E2E 打真实后端 + 真实数据库）
cd backend && python manage.py runserver 127.0.0.1:8000

# 另一终端
cd frontend
npm run e2e              # 只跑 chromium（推荐，约 3.5 分钟 / 24 条）
npm run e2e:headed       # 带界面看过程（调试用）
npm run e2e:all          # 跑全部浏览器项目（chromium + firefox）
npx playwright test e2e/02-safety.spec.mjs          # 只跑某个文件
npx playwright test -g "批量删除"                     # 只跑名字匹配的用例
npx playwright show-report                            # 看 HTML 报告
```

**前端不用手动起**：`playwright.config.ts` 的 `webServer` 是**数组**，
桌面端（5173）与移动端（5174）都会自动拉起，已经在跑的直接复用。

后端没起时不会"一片 timeout"，而是直接告诉你：

```
E2E 前置检查失败：后端没在 http://127.0.0.1:8000 上响应。
→ 先启动后端：cd backend && python manage.py runserver 127.0.0.1:8000
（E2E 打的是真实后端与真实数据库，不会自动启动它 —— 否则可能测到另一套数据）
```

---

## 二、现有的用例

> ⚠️ 第 219 批核对：原先这里只列了 5 个 spec（01~05）。后来新增了
> `06-assistant.spec.mjs`、`07-assistant-page.spec.mjs`（智能问答），
> 用例条数也随之变化 —— 以 `npx playwright test --list` 为准，别再手抄数字。

| 文件 | 覆盖什么 | 为什么值得固化 |
|---|---|---|
| `01-smoke.spec.mjs` | 健康检查 / 路由守卫 / 登录成功 / 密码错误 / 夹具账号可用 | **第 0 层**：这一层红了，后面的红都不值得看 |
| `02-safety.spec.mjs` | 存储型 XSS 不会执行、`token-auth` 后门仍关着、注销护栏、注销冷静期 | 全是**真实出过的事故**（第 91/95/101 批），而且都是"接口单测全绿、浏览器里仍出事"的类型 |
| `03-admin-users.spec.mjs` | 角色筛选能清干净、筛选/分页进 URL、表头排序走后端、批量删除、非管理员进不去 | 这一页被改得最多（76/88/95/98/100 批），也最容易改坏 |
| `04-detection.spec.mjs` | 上传图片 → 拿到结果（置信度/病害名/history_id）、识别页能渲染结果卡、纠错落库进训练样本池、匿名不能识别 | 系统**最核心的链路**，跨 4 层（表单 → MultiPartParser → YOLO 推理 → 序列化） |
| `05-mobile.spec.mjs` | 移动端登录页/忘记密码、底部导航、识别页相机入口、token 失效自愈 | 移动端是**独立应用**（`mobile/`，Vant，零代码共享）—— 桌面端全绿完全不能说明它是好的 |
| `06-assistant.spec.mjs` | 智能问答接口契约（检索、引用编号、无来源不回答） | 助手是**新增的一条链路**，且"没检索到就明说"这条约束最容易在重构时被悄悄改掉 |
| `07-assistant-page.spec.mjs` | 问答页交互（提问→流式回答→引用可展开、历史会话） | 流式渲染（SSE）的问题单测盖不住：只有真浏览器 + 真后端才能暴露 |

---

## 三、写新用例的约定

三条约定来自"一次性脚本"反复踩的坑，都在 `e2e/helpers.mjs` 里封装好了：

### 1. 自己造数据、自己清

```js
import { registerTempUser, cleanupByPrefix, cleanupDetections, runDjango } from './helpers.mjs';

test.afterAll(() => cleanupByPrefix());      // 按 zze2e 前缀扫，连 deleted_ 一起清

// 识别记录**没法按前缀清** —— 它的 detection_result 是模型预测的病害名，不是我们造的数据。
// 所以识别类用例必须记住自己的 history_id：
test.afterAll(() => cleanupDetections(createdDetectionIds));
```

**统一前缀 `zze2e`**：清理按前缀走，绝不误删真实数据。注销后会变成 `deleted_<id>`，
所以 `cleanupByPrefix()` 连这个前缀也一起扫。

### 2. 断言要能看懂

```js
expectThat('地址栏带 role 参数', roleParam, 'USER');   // 失败时打印"期望 X，实际 Y"
assertNoProblems();                                    // 一次抛出全部失败项
```

不要用 `expect(x).toBe(y)` —— E2E 的排查成本主要在"到底拿到了什么"。
诊断类信息也直接塞进断言标签里，例如
`` expectThat(`没有 JS 报错（实际：${JSON.stringify(errors)}）`, errors.length, 0) `` ——
浏览器只报"Failed to load resource: 404"，**不说是哪个资源**，不带上就只能猜。

### 3. 登录态直接写存储，别每次都走登录表单

```js
const session = await login();          // 夹具账号，拿 token
await loginAs(page, session);           // 桌面端：sessionStorage
await loginAsMobile(page, session);     // 移动端：localStorage
```

只有**专门测登录**的用例才该填表单 —— 否则"登录坏了"一个问题会放大成"所有用例都红"。

> ⚠️ **桌面端与移动端的存储故意不一样**，写错地方会得到"看起来已登录、其实没登录"
> （页面正常渲染、接口全 401、然后跳登录页）：
> | | 位置 | key |
> |---|---|---|
> | 桌面端 | `sessionStorage`（关标签页就登出） | `auth_token` / `user` |
> | 移动端 | `localStorage`（手机上每次都要重登是不可接受的） | `mobile_token` / `mobile_user` |

---

## 四、踩过的坑（写用例时大概率还会遇到）

| 现象 | 原因与解法 |
|---|---|
| `Element is outside of the viewport` | 管理页很长（深绿页头 + 统计卡 + 筛选栏 + 表格），行在折叠线以下。**用 DOM 点击**：`page.evaluate` 里 `element.click()`，不依赖几何判定 |
| `click()` 一直不点，日志反复打印 "element is visible, enabled and stable" | Element Plus 带 `fixed="right"` 操作列的表格，稳定性判定过不去。同上，改用 DOM 点击 |
| `check()` 勾了但界面没反应 | Element Plus 的 `selection-change` 只认 `.el-checkbox` 的点击，原生 input 的 `check()` 不触发 |
| 索引连点两行只选到一行 | 多选会重排/重渲染行，按索引连点可能点到同一行（第二次反而取消勾选）。**一条用例只勾一行** |
| 登录接口返回 **429** | 登录限流 10/分钟按 IP。用例多了必然撞 —— 调 `clearThrottle()` 先清零（它清的是开发库缓存） |
| 等 `input[type="file"]` 可见 → 超时 | 上传入口都是**隐藏 input + 按钮转发**（`class="d-none"` / `hidden-input`）。`setInputFiles` 对隐藏 input 有效，别等它可见 |
| 移动端 `.van-tabbar a` / `href*=` 都是 0 个 | Vant 的 `tabbar-item` 根节点不是 `<a>`，也没有 `href`。**按可见文案点**（`hasText: '记录'`），这也更贴近"用户能不能用" |
| 断言"页面里没有 script 标签" | 页面**本来就有** script（Vite 注入的模块脚本）。检查范围要缩到渲染正文的容器 |
| 断言"净化后标签应该消失" | 净化器的职责是**去掉可执行的部分**，不是"保持 HTML 好看"。`<img src=x onerror=…>` 净化后是 `<img src="x">` —— 安全，但标签还在。判据应是"没执行 + 没有事件属性 + 没有 script 标签" |
| 断言"页面上有'置信度'三个字" | 实际 UI 用的是可读判断（"很可能/较可能"）+ 百分比徽章，**没有"置信度"这个词**。先看一眼真实渲染再写断言 |
| 401 用例报"有 JS 报错" | token 失效本身就会打一次 401，浏览器记成 console error —— 是**预期产物**。用 `watchPageErrors(page, { ignore: [/401/] })` 精确放行，别放宽所有 console error |

### 关于接口响应形状：**别照着想象写**

`04-detection` 第一版按 `data.diseases[]` 断言，实际是：

```js
{ status: 'success',
  data: { detection: { disease, disease_en, confidence, description,
                        prevention, original_image, annotated_image, bbox },
          history_id: 949 } }
```

**单个** `detection` 对象（前端 `DetectView` 自己包成数组给结果卡片用），
记录 id 叫 `history_id`（`detection_id` 是 `Feedback` 上的字段名）。
写新接口的断言前，先 `curl`/`fetch` 一次把真实响应打出来。


---

## 五、这套 E2E 第一次运行就抓到的真 bug

`01-smoke.spec.mjs` 的"匿名访问受保护页面会被送到登录页"**第一次跑就红了**：

> 匿名用户直接访问 `/admin/users`，**没有被重定向到登录页** ——
> 顶栏显示"登录 / 立即注册"，页面却是用户管理表格（数据为空，写着"共 0 位用户"）。

根因在第 97 批（我自己引入的）——`router/index.js` 里的导航守卫：

```js
// 第 97 批的写法（错）
if (to.fullPath !== from.fullPath) {
  const canLeave = await runLeaveGuards()
  if (!canLeave) { next(false); return }
  next(); return          // ← 这个 return 把后面**所有鉴权逻辑**跳过了
}
```

当时修的是"未保存修改的离开提醒"，为了让"无未保存内容"和"用户选择离开"两种情况都
继续往下走鉴权，结果**放行分支直接 return 了**，于是 `requiresAuth` / `requiresAdmin`
的检查在"有导航"时**根本不执行**。修法是拦下时结束、放行时**不 return**，
让控制流继续走完鉴权。

> 这条 bug 已经存在了 6 批（97→103），期间：
> · 后端权限**没有**被绕过（接口依然返回 401/403），所以不是数据泄露；
> · 但**前端把管理页面渲染给了匿名用户** —— 属于"防线只剩一层"，
>   而且用户看到的是一个空的管理页，体验莫名其妙。
>
> 它能活 6 批的原因很直白：**当时没有任何自动化测试会去打这个 URL**。
> 这也正是这批要建立常驻 E2E 的理由。
