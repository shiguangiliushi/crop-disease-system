# 农作物病害识别系统 · 移动端（H5）

农户在田里用的 H5 客户端（`mobile/`，端口 **5174**）：登录/注册/忘记密码 → 拍照识别 → 结果（可点进病害百科）→
识别记录 → 我的。与桌面端 `../frontend` 是**两个独立工程、共用同一个后端**（`../backend`，Django）。

## 一、为什么拆两端

| | 桌面 `frontend/`（5173） | 移动 `mobile/`（5174） |
|---|---|---|
| 面向 | 管理、论坛、百科、批量操作、看板 | **单手、戴手套、强光下**的拍照识别 |
| UI 库 | Element Plus + Bootstrap | Vant |
| 登录态 | `sessionStorage`（按标签页隔离，支持同浏览器多账号） | `localStorage`（手机进程随时被回收，必须持久登录） |
| 接口 | `/api/*` 绝对地址 | `/api/*` **相对地址 + vite 代理**（手机访问电脑 IP 也能用） |

手机屏幕塞不下论坛/看板这类高密度页面，桌面端也不需要为田间交互重做设计。
**代码零共享**（各一份 `camera.js` / `i18n`），改一端不波及另一端。

## 二、快速开始

```bash
cd ../backend && python manage.py runserver      # http://127.0.0.1:8000（两端都依赖）
cd ../mobile && npm install && npm run dev       # http://localhost:5174
```

- **真机调试**：电脑与手机同一 Wi-Fi，访问 `http://<电脑IP>:5174`。dev server 监听
  `host: '0.0.0.0'`（刻意不用 `host: true` —— 它解析成 `::`，Windows 上难排障），
  vite 把 `/api`、`/media` 代理到本机后端。
- Windows 上可双击仓库上一级的 `start_mobile.bat`（同时拉起后端 + 移动端）；
  它**不在仓库里**，属本机启动脚本。

## 三、拍照：两条路径（本端最需要理解的一点）

`src/utils/camera.js` + `src/components/CameraCapture.vue` 实现**页面内取景**：
`getUserMedia` 实时预览 → 快门抓帧 → canvas 编码 JPEG → 直接进识别。浏览器安全策略决定了必须有降级：

| 访问方式 | `navigator.mediaDevices` | 行为 |
|---|---|---|
| `https://…`（安全上下文） | 有 | ✅ 页面内取景 + 快门 + 前后摄像头切换（+支持时补光） |
| `http://localhost` / `127.0.0.1` | 有（localhost 视为安全） | ✅ 同上 |
| `http://192.168.x.x:5174`（农户真实用法） | **不存在** | ⚠️ 降级：提示原因并唤起**系统相机**（`<input capture="environment">`） |
| 权限被拒 / 摄像头被占 | 有但失败 | ⚠️ 取景框内给出原因 + 「重试」/「改用系统相机」 |

**手机走局域网 IP 时用的是系统相机，这不是 bug**，是"明文 http 不允许访问摄像头"。想在手机上用页面内取景：

1. 给站点配 **HTTPS**（自签证书也行，手机装一次根证书）；
2. 调试用 `chrome://flags/#unsafely-treat-insecure-origin-as-secure` 把 `http://<电脑IP>:5174` 加白名单；
3. Android 调试用 `adb reverse tcp:5174 tcp:5174`，手机上访问 `localhost:5174`。

无论哪条路径，图片都会先本地压缩（长边 1600px / JPEG 0.85）再上传 —— 田间弱网省流量，也避免撞后端 5MB 上限。

## 四、目录结构

```
mobile/
├─ src/
│  ├─ api/            http.js（Token/CSRF/错误文案/**401 自愈**）、auth.js、account.js（注销/冷静期）、
│  │                  detection.js、history.js、user.js、content.js
│  ├─ components/     CameraCapture.vue（整屏取景）、TabBar.vue、OfflineIndicator.vue（离线/待传提示）
│  ├─ i18n/           极简多语言（zh-CN / en，缺翻译回落中文）
│  ├─ router/         7 个页面（8 条路由，`/result` 与 `/result/:id` 共用 ResultView）+ 登录守卫
│  ├─ stores/         auth.js（登录态/持久化/clearAuth）、detect.js（当前识别结果，sessionStorage 恢复）
│  ├─ utils/          camera.js、image.js（压缩）、detectionResult.js（两处结果统一整形，**保留 identifier**）、
│  │                  authStorage.js、offlineQueue/offlineStorage/offlineSync（离线队列）
│  └─ views/          LoginView / RegisterView / ForgotPasswordView / DetectView / ResultView / HistoryView / MineView / PestDetailView
├─ scripts/           check-i18n-symmetry.mjs（中英 key 对称性自检）
├─ vite.config.js     端口 5174、host: '0.0.0.0'、/api 与 /media 代理
└─ .env.development   VITE_API_BASE_URL=/api；VITE_LEGAL_BASE_URL（法务页地址）
```

## 五、接口契约速查

| 用途 | 接口 | 备注 |
|---|---|---|
| 登录 / 注册 / 登出 | `POST /api/login/`、`/api/register/`、`/api/logout/` | 响应 `{status, message, data:{user, token}}`，需向下找一层 |
| 忘记密码 | `POST /api/password-reset/` | `{username_or_email}`；**账号不存在与已发送同话术**（防枚举） |
| 识别 | `POST /api/detect/` | **multipart 字段名必须是 `image`**；返回 `{status, data:{detection, history_id}}` |
| 识别记录 | `GET /api/detection-history/?page=&page_size=` | 返回 `{code, msg, data:{items,total,page,total_pages}}`（**不是** DRF 的 count/results） |
| 记录详情 / 删除 | `GET/DELETE /api/detection-history/<id>/` | |
| 纠错反馈 | `POST /api/feedback/` | `category=recognition` + `disease_name` / `is_correct` / `detection_id` / `corrected_pest_id` |
| 病害列表（纠错下拉） | `GET /api/pests/?page_size=200` | 选"正确病害"后这条反馈才是可训练样本 |
| 我的统计 | `GET /api/users/<id>/stats/`、`/api/users/me/points/` | 统计失败回落 0，不阻塞页面 |
| 识别后追问 | `POST /api/assistant/ask/` | 非流式；带 `pest_identifier`（来自 `detectionResult.identifier`）才不会降级 |

⚠️ 后端图片地址是 `request.build_absolute_uri()` 生成的**绝对地址**（`http://127.0.0.1:8000/media/…`），
手机上会指向手机自己。`src/api/http.js` 的 `toAbsoluteMediaUrl()` 把 `127.0.0.1 / localhost`
剥成相对路径、改走当前页面 origin（即 vite 代理）。

## 六、构建与部署

```bash
npm run build      # 产物在 mobile/dist
npm run preview    # 本地预览（4174）
npm run check:i18n # 中英 key 对称性自检
```

`VITE_API_BASE_URL` 默认相对路径 `/api`，部署时把 `dist/` 交给能反代 `/api` 与 `/media`
到 Django 的 Web 服务器即可；前后端分域则改完整地址（后端需放行 CORS 与 CSRF 来源）。

**`VITE_LEGAL_BASE_URL`**：移动端没有用户协议/隐私政策页（只在桌面端），登录页的两个链接指向它；
**留空则整段不显示** —— 避免"点开不是那个页面"（第 91 批前 `<a href="/terms">` 会落到兜底路由打开识别页）。

## 七、验证

端到端脚本在客户端工程（移动端本身没有测试依赖）：

```bash
cd ../frontend
npm run verify:camera   # 拍照链路（需 5174 + 5173 都启动）
npm run verify:mobile   # 401 自愈 / keep-alive / 忘记密码 / 离线队列
```

`verify:camera` 用假摄像头真跑：登录 → 拍照 → 校验 `videoWidth > 0` → 快门 → JPEG 预览 → 识别 →
断言上传体是带 `filename="photo-*.jpg"` 的真实 JPEG（含 `FF D8 FF` 头）。

| 场景 | 断言 |
|---|---|
| token 过期 | 失效 token 访问 `/history` → 落 `/login?reason=expired`、身份已清、提示"登录已过期" |
| 切 tab 丢照片 | 选好图 → 切"记录" → 切回，预览 dataURL **仍在**（`<keep-alive include="DetectView,HistoryView">`） |
| 忘记密码 | 入口存在、`/forgot-password` 能提交、话术统一；法务链接指向真实页面 |
| 断网白拍 | 离线点识别 → 照片进 IndexedDB 队列 + 待传状态条，联网自动补传 |

截图输出在 `frontend/dsh-shots/`。

## 八、范围与批次变更

只做"农户核心闭环"；论坛、百科、专家咨询、种植日历、审核、看板仍只在桌面端（路由与 i18n 已就位，按页补即可）。

| 第 91 批补的四件事 | 改前 | 改后 |
|---|---|---|
| **401 自愈** | 只看"本地有没有 token"，过期后界面仍显示已登录、只报"请求失败" | 任何请求 401 → `clearAuth()` + 跳登录页 + 提示"登录已过期" |
| **keep-alive** | 裸 `<router-view />`，切 tab 组件销毁，**拍好的照片没了** | `<keep-alive :include="['DetectView','HistoryView']">`；结果页/登录页不缓存 |
| **忘记密码** | 移动端没这页，忘密码 = 永久登不进 | `/forgot-password`：用户名或邮箱 → 重置链接（话术统一，防枚举） |
| **离线队列** | 断网点识别只弹"离线"，白拍一张 | 照片存 IndexedDB → 联网自动补传；底部状态条可手动补传 |

顺带修的两处：登录页"用户协议/隐私政策"**死链**（改为 `VITE_LEGAL_BASE_URL`）、
识别纠错接上"正确病害"（`corrected_pest_id`，缺了就不是可训练样本，导出见 `manage.py export_feedback_dataset`）。

> ⚠️ 401 拦截器**不能只删 localStorage**：`isAuthenticated` 是 `computed(() => Boolean(token.value))`，
> 读的是内存里的 ref，而 ref 只在 store 创建时初始化一次 —— 只清存储的话路由守卫仍认为已登录，
> 会把 `/login` 又弹回 `/detect`。必须调 `useAuthStore().clearAuth()`。
