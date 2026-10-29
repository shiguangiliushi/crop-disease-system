# 打包 Android APK（步骤 ②）

> 目标：把 `mobile-uni/` 打成**能装在自己手机上**的 APK —— 不需要上架、不需要域名，
> 只要手机和电脑在同一个 Wi-Fi，连 `http://<电脑IP>:8000` 就能用。
>
> 现状（2026-10-29）：**代码侧已就绪**，`npm run build:app` 能产出 App 资源包；
> 但**这台机器上没有 HBuilderX，也没有 JDK/Android SDK**（实测过），
> 所以最后一步"出 APK"必须由你在装好工具的机器上点一次（见下）。

## 一、代码侧已经做完的部分

| 事 | 状态 |
|---|---|
| App 资源构建 | `npm run build:app` → `dist/build/app/`（0.84 MB，20 个文件） |
| 相机/存储/网络权限 | `src/manifest.json` 的 `app-plus.distribute.android.permissions` 已声明 |
| 包信息 | `manifest.json`：名称「农作物病害识别」、版本 1.0.0 / 100 |
| **服务器地址可运行时修改** | 登录页底部「服务器」一行（**仅 APP 显示**，`#ifdef APP-PLUS`）：点开填 `http://192.168.1.20:8000/api`，存 `uni.storage`，换 Wi-Fi 不用重新打包 |
| 条件编译验证 | App 包里有「服务器设置」，H5 产物里没有（已 grep 确认） |

> 为什么要有"服务器地址可改"：没有域名时 APK 只能连局域网 IP，而电脑 IP 会随网络变化。
> 写死在包里的话，每换一次网络就得重新打一次包。

## 二、路线 A：HBuilderX 云打包（推荐，最省事）

1. **装 HBuilderX（标准版即可）**：<https://www.dcloud.io/hbuilderx.html>
2. **注册并登录 DCloud 账号**（免费；云打包有免费额度，超出按时长计费）
3. 菜单 **文件 → 导入 → 从本地目录导入**，选 `mobile-uni/dist/build/app`
   - HBuilderX 会提示"未配置 appid" → 点确认，自动生成一个 DCloud appid（写回 `manifest.json` 的 `id`）
4. 右键项目 → **发行 → 原生App-云打包**，选择：
   - 平台：**Android**
   - 证书：**使用 DCloud 老版证书** 或 **勾选"自动生成证书"**（自用/演示足够；别用于上架）
   - 包名：填一个唯一的，例如 `com.cropcare.app`（**不是** manifest 里的 appid）
   - 其它：默认即可
5. 等 1~3 分钟 → 下载 APK → 传到手机安装
   （Android 会提示"未知来源安装"，允许即可）

## 三、路线 B：离线打包（要 Android Studio，约 4 GB 依赖）

适合"不想用云打包 / 要自己控制签名"的情况：

1. 装 **JDK 17** + **Android Studio**（含 Android SDK）
2. 下载 **uni-app 离线打包 SDK**：<https://nativesupport.dcloud.net.cn/AppDocs/download/android>
3. 用 Android Studio 打开 SDK 里的 `HBuilder-Integrate-AS` 工程，把
   `mobile-uni/dist/build/app` 整个目录拷进 `app/src/main/assets/apps/<appid>/www/`，
   并修改 `dcloud_control.xml` 里的 appid 与工程 `applicationId`
4. 补一条明文 HTTP（见下）后 **Build → Generate Signed Bundle / APK**

> 离线方案步骤多、版本耦合强；**只为演示的话走路线 A**。

## 四、必须注意的坑

### 1. Android 9+ 默认禁止 HTTP 明文

后端现在只有 `http://`（没有 HTTPS 域名），而 Android 从 9 起默认拒绝明文流量 ——
不处理的话 APK 里所有请求都会失败，表现是"网络连接失败"。

- 云打包：HBuilderX 的 `manifest.json` → **App 其它设置 → Android 设置**里有
  "允许 http 明文请求 / 使用明文网络流量"一类开关（不同版本位置略有差别，找不到就在
  `manifest.json` 的 `app-plus.distribute.android` 下加 `"usesCleartextTraffic": true`）
- 离线打包：`AndroidManifest.xml` 的 `<application>` 上加 `android:usesCleartextTraffic="true"`

### 2. 后端要监在 `0.0.0.0`，不是 `127.0.0.1`

```powershell
cd backend
python manage.py runserver 0.0.0.0:8000
```

`127.0.0.1` 只有本机能访问，手机连不上。Windows 防火墙还要放行 8000
（仓库根有 `fix_lan_firewall.ps1`，以管理员运行）。

### 3. 登录页先填服务器地址

APK 第一次打开 → 登录页底部「服务器」→ 填 `http://<电脑IP>:8000/api` → 再登录。
（H5 走 vite 代理，不需要这一步。）

### 4. 相机权限

首次点"拍照"会弹权限申请；拒绝后要进系统设置里手动开，否则只能从相册选。

## 五、装上之后测什么（验收清单）

- [ ] 登录（用 `admin` 或普通账号）→ 进识别页
- [ ] **拍照**识别（真机相机）→ 结果页显示病害名 / 置信度 / 防治
- [ ] 从相册选图识别
- [ ] 切到别的 App 再回来，登录态还在（`uni.storage` 没丢）
- [ ] 断网时点识别 → 有可读的失败提示，不是白屏
- [ ] 服务器地址改成错误 IP → 登录失败提示明确，再改回来能恢复

## 六、边界

- 我这边**不能**替你点 HBuilderX 的图形界面，也不能用你的 DCloud 账号做云打包；
- 但"资源包已经能构建出来、配置与条件编译都在"这件事我验证过了：
  `npm run build:app` 输出 `dist/build/app`，且 App 包里确实带上了「服务器设置」。
- 需要我继续的话，下一步可以先做**历史 / 我的**两页（步骤 ① 的剩余部分），
  等你装好 HBuilderX 再把包一次性打齐。
