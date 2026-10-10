# 农作物病害识别系统 · 移动端（H5）

> 第 75 批新增。本工程与桌面客户端 `../frontend` 是**两个独立工程、共用同一个后端**
> （`../backend`，Django，默认 `http://127.0.0.1:8000`）。

## 一、为什么要拆成两端

| | 桌面客户端 `frontend/` | 移动端 `mobile/` |
|---|---|---|
| 端口 | 5173 | **5174** |
| 面向 | 管理、论坛、百科、批量操作、看板 | **农户在田里**：拍照识别、识别记录、我的 |
| UI 库 | Element Plus + Bootstrap | Vant（移动端组件） |
| 登录态 | `sessionStorage`（按标签页隔离，支持同浏览器多账号） | `localStorage`（手机浏览器进程随时被回收，必须持久登录） |
| 接口 | `/api/*`（绝对地址，默认 127.0.0.1:8000） | `/api/*`（**相对地址 + vite 代理**，手机访问电脑 IP 也能用） |

拆开的原因不是"好看"，而是两端的取舍恰好相反：
手机屏幕塞不下论坛/看板这类高信息密度页面，而桌面端也不需要为"单手、戴手套、强光下点击"重新设计交互。
**代码零共享**（各自一份 `camera.js` / `i18n`），换来的是改一端不会波及另一端。

## 二、快速开始

```bash
# 1) 后端（必须先起来，两端都依赖它）
cd ../backend && python manage.py runserver        # http://127.0.0.1:8000

# 2) 移动端
cd ../mobile
npm install
npm run dev                                        # http://localhost:5174
```

手机实机调试：电脑与手机连同一个 Wi-Fi，用电脑的局域网 IP 访问
`http://<电脑IP>:5174`（dev server 监听 `host: '0.0.0.0'` —— 刻意不用 `host: true`，
因为它会解析成 `::`、Windows 上排障困难；vite 会把 `/api`、`/media` 代理到本机后端）。

Windows 上也可以直接双击**项目外层目录**（仓库的上一级，与 `start_project.bat` 同级）的
`start_mobile.bat`（会同时拉起后端 + 移动端）。它**不在仓库里** —— 属于本机启动脚本，
不随代码发布。

## 三、📷 拍照：两条路径（这是本端最需要理解的一点）

`src/utils/camera.js` + `src/components/CameraCapture.vue` 实现了**页面内取景拍照**：
`getUserMedia` 实时预览 → 快门抓帧 → canvas 编码成 JPEG → 直接进识别流程。

但浏览器的硬限制决定了**必须有降级路径**：

| 访问方式 | `navigator.mediaDevices` | 行为 |
|---|---|---|
| `https://…`（安全上下文） | 有 | ✅ 页面内取景 + 快门 + 前后摄像头切换（+支持时补光） |
| `http://localhost:5174` 或 `127.0.0.1` | 有（localhost 被视作安全上下文） | ✅ 同上（桌面端/本机调试属于这种情况） |
| `http://192.168.x.x:5174`（局域网，农户真实用法） | **不存在** | ⚠️ 自动降级：提示原因并唤起**系统相机**（`<input capture="environment">`） |
| 权限被拒绝 / 摄像头被占用 | 有但失败 | ⚠️ 取景框内给出可读原因 + 「重试」/「改用系统相机」按钮 |

即：**手机通过局域网 IP 访问时，拍照走的是系统相机，页面内取景用不了。** 这不是 bug，
是浏览器的安全策略（明文 http 不允许访问摄像头）。想在手机上用页面内取景，三选一：

1. 给站点配 **HTTPS**（自签证书也行，手机装一次根证书）；
2. 用 Chrome 的 `chrome://flags/#unsafely-treat-insecure-origin-as-secure` 把
   `http://<电脑IP>:5174` 加进白名单（仅调试用）；
3. 用 `adb reverse tcp:5174 tcp:5174` 把手机上的 `localhost:5174` 映射到电脑（Android 调试）。

无论哪条路径，拍到的图片都会先本地压缩（长边 1600px / JPEG 0.85）再上传 ——
田间弱网下省流量，也避免撞到后端 5MB 上限。

## 四、目录结构

```
mobile/
├─ src/
│  ├─ api/            http.js（统一客户端：Token/CSRF/错误文案/**401 自愈**）、auth.js、account.js（注销/冷静期）、
│  │                  detection.js、history.js、user.js、content.js
│  ├─ components/     CameraCapture.vue（整屏取景）、TabBar.vue、OfflineIndicator.vue（离线/待传提示）
│  ├─ i18n/           极简多语言（zh-CN / en，缺翻译回落中文）
│  ├─ router/         7 个页面（8 条路由，`/result` 与 `/result/:id` 共用 ResultView）+ 登录守卫
│  ├─ stores/         auth.js（登录态/持久化/clearAuth）、detect.js（当前识别结果，sessionStorage 恢复）
│  ├─ utils/          camera.js、image.js（压缩）、detectionResult.js（两处结果统一整形）、authStorage.js
│  │                  offlineQueue.js / offlineStorage.js / offlineSync.js（离线队列，第 91 批）
│  └─ views/          LoginView / RegisterView / ForgotPasswordView / DetectView / ResultView / HistoryView / MineView
├─ scripts/           check-i18n-symmetry.mjs（中英 key 对称性自检）
├─ vite.config.js     端口 5174、host:true、/api 与 /media 代理
└─ .env.development   VITE_API_BASE_URL=/api；VITE_LEGAL_BASE_URL（法务页地址）
```

## 五、用到的后端接口（契约速查）

| 用途 | 接口 | 备注 |
|---|---|---|
| 登录 / 注册 / 登出 | `POST /api/login/`、`/api/register/`、`/api/logout/` | 响应为 `{status, message, data:{user, token}}`，需向下找一层 |
| 忘记密码 | `POST /api/password-reset/` | `{username_or_email}`；**账号不存在与已发送返回同一话术**（防枚举） |
| 识别 | `POST /api/detect/` | **multipart 字段名必须是 `image`**；返回 `{status, data:{detection, history_id}}` |
| 识别记录 | `GET /api/detection-history/?page=&page_size=` | 返回 `{code, msg, data:{items,total,page,total_pages}}`（**不是** DRF 的 count/results） |
| 记录详情 / 删除 | `GET/DELETE /api/detection-history/<id>/` | |
| 纠错反馈 | `POST /api/feedback/` | `category=recognition` + `disease_name` / `is_correct` / `detection_id` / `corrected_pest_id` |
| 病害列表（纠错下拉用） | `GET /api/pests/?page_size=200` | 第 91 批：选"正确病害"才让纠错成为训练样本 |
| 我的统计 | `GET /api/users/<id>/stats/`、`/api/users/me/points/` | 统计失败只回落 0，不阻塞页面 |

⚠️ 后端图片地址是 `request.build_absolute_uri()` 生成的**绝对地址**（例如
`http://127.0.0.1:8000/media/...`）。手机上这个地址会指向手机自己，
所以 `src/api/http.js` 的 `toAbsoluteMediaUrl()` 会把 `127.0.0.1 / localhost`
剥成相对路径，改走当前页面的 origin（即 vite 代理）。

## 六、构建与部署

```bash
npm run build      # 产物在 mobile/dist
npm run preview    # 本地预览（4174）
npm run check:i18n # 中英 key 对称性自检（缺翻译会让英文界面冒出中文）
```

`VITE_API_BASE_URL` 默认是相对路径 `/api`，因此**部署时把 `dist/` 交给一个能反代
`/api` 与 `/media` 到 Django 的 Web 服务器**（Nginx / Django 直接托管 / 同一域名下的网关）即可。
若前后端分域，改成完整地址（需后端放行 CORS 与 CSRF 来源）。

**`VITE_LEGAL_BASE_URL`（法务页地址）**：移动端工程里**没有**用户协议 / 隐私政策页，
它们只在桌面端（`frontend/`）。登录页的这两个链接指向这个地址；**留空则整段不显示** ——
不会出现"点开不是那个页面"（第 91 批之前就是：`<a href="/terms">` 落到兜底路由 → 打开的是识别页）。
生产部署请填真实站点地址。

## 七、验证

端到端脚本在客户端工程里（复用其 Playwright 依赖；移动端工程本身**没有测试依赖**）：

```bash
cd ../frontend
npm run verify:camera      # 拍照链路（需要 mobile 5174 + frontend 5173 都启动）
npm run verify:mobile      # 第 91 批「四件套」：401 自愈 / keep-alive / 忘记密码 / 离线队列
```

`verify:camera` 会用 Chromium/Edge 的**假摄像头**真跑一遍：登录 → 点「拍照」→ 校验取景框真的出画面
（`videoWidth > 0`）→ 点快门 → 校验生成了 JPEG 预览 → 走完识别 → 校验结果页文案，
并断言上传的 multipart body 里确实是一张带 `filename="photo-*.jpg"` 的真实 JPEG（含 `FF D8 FF` 头）。

`verify:mobile` 覆盖第 91 批补齐的四件事，每条都对应用户会立刻卡住的场景：

| 场景 | 断言 |
|---|---|
| token 过期 | 用失效 token 访问 `/history` → 落到 `/login?reason=expired`、本地身份已清、页面提示"登录已过期" |
| 切 tab 丢照片 | 识别页选好图 → 切到"记录" → 切回来，预览 dataURL **仍在** |
| 忘记密码 | 登录页有入口、`/forgot-password` 能提交、显示"邮件已发送"；法务链接指向真实页面 |
| 断网白拍 | 离线时点识别 → 照片进 IndexedDB 队列、出现待传状态条 |

截图输出在 `frontend/dsh-shots/`。

## 八、首批范围（有意不含）

移动端目前只做"农户核心闭环"：**登录/注册/忘记密码 → 拍照识别 → 结果 → 识别记录 → 我的**。
论坛、病害百科、专家咨询、种植日历、内容审核、数据看板等仍只在桌面客户端提供
（详见 `../docs/功能缺口评估.md`）。后续要加，按页面逐个补即可，路由与 i18n 已就位。

## 九、第 91 批补的四件事（离线与健壮性）

| 项 | 改前 | 改后 |
|---|---|---|
| **401 自愈** | `isAuthenticated` 只看"本地有没有 token"；过期后界面仍显示已登录，各页只报"请求失败"，用户得自己想到去退出重登 | 任何请求 401 → 清身份（走 store 的 `clearAuth()`）+ 跳登录页 + 提示"登录已过期" |
| **keep-alive** | 裸 `<router-view />`：切一下 tab 组件即销毁，**拍好的照片没了**，得重拍 | `<keep-alive :include="['DetectView','HistoryView']">`；结果页/登录页不缓存（要按路由参数重新取数） |
| **忘记密码** | 移动端没有这一页，忘了密码 = 永久登不进 | `/forgot-password`：输入用户名或邮箱 → 发重置链接（话术统一，防账号枚举） |
| **离线队列** | 断网点识别只弹一句"当前处于离线状态"，白拍一张 | 照片存 IndexedDB → 联网自动补传识别；底部状态条可点手动补传 |

另外顺手修掉两处：**登录页的"用户协议/隐私政策"是死链**（`<a href="/terms">` 在移动端没有该路由，
会落到兜底 redirect → 打开的是识别页；现在指向 `VITE_LEGAL_BASE_URL`，未配置则不显示），
以及**识别纠错接上了"正确病害"**（`corrected_pest_id`）—— 只有带上正确类别，这条反馈才能
变成可训练样本（后端 `Feedback.corrected_pest`，导出见 `manage.py export_feedback_dataset`）。

> ⚠️ 一个踩过的坑记在这里：401 拦截器**不能只删 localStorage**。移动端的
> `isAuthenticated` 是 `computed(() => Boolean(token.value))`，读的是**内存里的 ref**，
> 而 ref 只在 store 创建时初始化一次 —— 只清存储的话路由守卫仍认为已登录，
> 会把刚跳到的 `/login` 又弹回 `/detect`（实测现象：身份清了，人却没回登录页）。
> 正确做法是调用 `useAuthStore().clearAuth()`。
