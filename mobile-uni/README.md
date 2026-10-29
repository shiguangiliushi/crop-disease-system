# 移动端 · uni-app 版（第 232 批）

> 目标：**同一套代码出 H5 + 微信小程序 + Android/iOS APP**（现有 `mobile/` 的 Vant H5 保留不动）。
> 当前进度：**步骤 ①——骨架 + 登录 + 识别 + 结果三页，跑在 H5 上**。

## 为什么另起一份，而不是改 `mobile/`

微信小程序不允许加载任意 H5 页面，必须用它自己的框架写；Vant 4 依赖 DOM，在小程序里跑不了。
只要"小程序"这个需求成立，`mobile/`（Vant + vue-router）就没法直接复用 UI 层 —— 见
`旧 H5 → uni-app 迁移说明` 一节的对照表。

## 目录

```
mobile-uni/
├── index.html          H5 入口（uni-app 官方模板的 viewport 适配）
├── vite.config.js      端口 5175 + /api、/media 代理（只给 H5 开发用）
├── package.json        只装了 H5 端依赖
└── src/
    ├── App.vue         全局样式 + 启动时按登录态跳转
    ├── main.js         uni-app 约定的 createApp()（必须返回 Pinia）
    ├── pages.json      页面路由（登录 / 识别 / 结果）
    ├── manifest.json   应用信息（APP/小程序配置先留空，用到再填）
    ├── utils/
    │   ├── request.js  uni.request / uni.uploadFile 封装 + 401 统一处理
    │   └── api.js      登录、退出、识别三个接口
    ├── stores/auth.js  Pinia 登录态（uni.storage 版）
    └── pages/
        ├── login/      账号密码登录
        ├── detect/     拍照/相册 → 上传 → 识别
        └── result/     病害名/置信度/症状/防治建议
```

## 跑起来

```powershell
cd mobile-uni
npm install
npm run dev:h5        # http://127.0.0.1:5175
```

后端要先起来（`backend/` 里 `python manage.py runserver`，默认 8000），
H5 通过 vite 代理访问 `/api`、`/media`。

## 出 App 资源 / 打包 APK

```powershell
npm run build:app     # 产出 dist/build/app（HBuilderX 导入它再云打包）
```

**这台机器上没有 HBuilderX / JDK / Android SDK**（实测过），所以"出 APK"这一步
要到装好工具的机器上做。完整步骤与坑（HTTP 明文、包名、相机权限、服务器地址）见
[`docs/打包APK.md`](docs/打包APK.md)。

> APK 里没有 vite 代理：登录页底部「服务器」可填 `http://<电脑IP>:8000/api`
> （仅 APP 显示，存本地，换 Wi-Fi 不用重新打包）。

## 已经和现有 H5 对齐的约定

| 约定 | 说明 |
|---|---|
| 登录带 `device` | 登录时传 `device: 'app'`，与桌面 `web`、旧 H5 `mobile` 区分（第 231 批：每设备一张 token） |
| 上传字段名 `image` | 后端 `DetectView` 读的就是 `request.FILES['image']` |
| 401 统一处理 | `utils/request.js` 清 token + 回登录页，页面不各写一份 |
| 识别结果跨页传 | 存 `uni.setStorageSync('last_result')`，不走 URL（小程序 URL 有长度限制） |

## 旧 H5 → uni-app 迁移说明

| 现有 `mobile/` 的东西 | uni-app 里怎么做 |
|---|---|
| Vant 组件 | 换成 uni 内置组件（`view`/`text`/`button`/`input`/`image`），页面结构按 rpx 重写 |
| `axios` | `uni.request`（小程序没有 XHR） |
| `localStorage` | `uni.getStorageSync` / `setStorageSync` |
| `getUserMedia` 实时取景（`utils/camera.js`） | `uni.chooseImage` —— 小程序没有实时取景，这块**必然重写** |
| Canvas 分享卡（`utils/shareCard.js`） | `<canvas type="2d">` + `uni.canvasToTempFilePath`，暂未做 |
| IndexedDB 离线队列（`utils/offlineStorage.js`） | `uni.setStorage` 存文件路径，暂未做 |
| 图片压缩（`utils/image.js`） | `uni.compressImage`，暂未做 |

## 后续步骤

1. ✅ **骨架 + 登录 + 识别 + 结果（H5）** ← 现在这里
2. ⏳ 历史记录 / 我的（补齐页面）
3. 🟡 **Android APK**：`npm run build:app` 已能出资源包、配置与"服务器地址可改"已就绪；
   真正出 APK 需要在装了 HBuilderX 的机器上云打包（本机没有），见 `docs/打包APK.md`
4. ⏳ 微信小程序（需要 AppID + **HTTPS 备案域名**，真机预览就卡在这一步）
5. ⏳ iOS（需要 Apple 开发者账号）

## 已知限制（MVP 范围内的取舍）

- 只做了中文文案（现有 `mobile/` 有中英双语；uni-app 这版先保证功能跑通）；
- 没做图片压缩：`sizeType: ['compressed']` 交给系统压，超大图仍可能超过 5MB 上限；
- 没做离线队列：断网时直接提示重试；
- 没接"识别后追问助手"：后端 `/api/assistant/ask/` 已支持 `image`，可作下一步。
