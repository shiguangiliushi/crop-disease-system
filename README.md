# 智能农作物叶片病虫害识别系统

一个面向农户的**作物叶片病虫害识别与防治**平台：上传一张叶片照片，得到病害名、
置信度、防治建议；配套病害百科、识别历史、病害预警、种植日历、专家咨询、论坛交流，
以及一套管理端（用户 / 内容审核 / 新闻 / 意见反馈 / 数据集）。

```
backend/    Django 5.2 + DRF（SQLite，YOLOv8 推理）
frontend/   桌面端 Vue 3 + Element Plus + Vite（:5173）
mobile/     移动端 Vue 3 + Vant + Vite（:5174，独立应用，与桌面端零代码共享）
docs/       设计与运维文档
tools/      开发辅助脚本（注释覆盖审计等）
```

---

## 快速开始

```bash
# ── 后端（需要一个装好依赖的 Python 环境）──────────────────────────────────
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py check_env          # 环境自检：依赖/数据库/迁移/模型文件
python manage.py runserver 127.0.0.1:8000

# ── 桌面端 ────────────────────────────────────────────────────────────────
cd frontend && npm install && npm run dev     # http://127.0.0.1:5173

# ── 移动端（可选，独立应用）───────────────────────────────────────────────
cd mobile && npm install && npm run dev       # http://127.0.0.1:5174
```

> ⚠️ **首次跑之前请先看 [`docs/部署与运维.md`](docs/部署与运维.md)** ——
> 它写清了 `pip install -r requirements.txt` **照原样装不出能跑的环境**这件事，
> 以及生产启动（gunicorn + WhiteNoise）、环境变量、必须挂的几个定时任务。

---

## 目录导航（先读哪个）

| 想做的事 | 先读 |
|---|---|
| 部署 / 上线 | [`docs/部署与运维.md`](docs/部署与运维.md) |
| 备份与恢复（**含恢复演练脚本**） | [`docs/备份与恢复.md`](docs/备份与恢复.md) |
| 搞清楚"某个功能为什么长这样" | [`docs/系统完善记录.md`](docs/系统完善记录.md)（**按批次记录，含每次踩的坑**） |
| 了解注释覆盖率与方法论 | [`docs/注释覆盖审计报告.md`](docs/注释覆盖审计报告.md) |
| 跑端到端测试 | [`frontend/e2e/README.md`](frontend/e2e/README.md) |
| 环境变量都有哪些 | [`backend/.env.example`](backend/.env.example)（每项都写了取值理由） |

---

## 测试

```bash
# 后端：Django 测试（约 470 条，含权限/限流/冷静期/备份/清理等回归）
cd backend && python manage.py test api.tests --parallel 4

# 桌面端：单元测试 + 类型检查
cd frontend && npm run test:unit && npm run type-check

# 端到端（真实后端 + 真实浏览器，需要后端与前端都在跑）
cd frontend && npm run e2e

# 移动端：中英文 key 对称性检查
cd mobile && npm run check:i18n
```

---

## 几件在这个项目里"必须知道"的事

这些都不是常规 Django/Vue 常识，而是这个项目特有的、踩过坑的约定。
**改动相关代码前请先读对应说明**：

| 事项 | 说明 |
|---|---|
| **前端有两个登录态存储** | 桌面端用 `sessionStorage`（`auth_token`），移动端用 `localStorage`（`mobile_token`）。写错地方会表现成"看起来已登录、接口全 401"。 |
| **`is_active=False` 的账号登不进来** | 因为 Django 的 `ModelBackend` 直接拒绝 —— 所以**注销冷静期的判断必须放在 `authenticate()` 之前**（见 `views.LoginView`）。 |
| **点赞/评论计数只由模型层维护** | `models_forum.Like.save/delete` 会精确重算；视图**不要**再 `F()+1`（第 106 批修过一个"多算 1"的 bug）。 |
| **密码策略只有一个来源** | `api/password_policy.py`（8 位 + 禁纯数字 + 弱口令库）。注册/重置/改密三处都调它；**登录不做长度校验**（否则旧密码短的存量用户会被锁在门外）。 |
| **匿名密码校验端点必须限流** | `AccountCancelDeletionView` 允许匿名（账号已停用拿不到 Token），挂了 `ScopedRateThrottle` —— 别把限流删掉。 |
| **必须有定时任务** | 备份、校验、media 清理、注销到期执行 —— 四件事**缺哪件都是"安静的故障"**，清单见 `docs/部署与运维.md`。 |
| **改后端代码要重启** | 开发用的是 `runserver --noreload`，改了 `.py` 与 `urls.py` **不重启就不生效**（这个坑踩过三次）。 |
| **`.gitattributes` 固定了行尾** | 仓库里一律 LF。曾经因为 `\r` 让验证脚本误判过好几次。 |

---

## 许可与用途

教学 / 毕业设计用途。病害识别模型的训练数据来自公开的 PlantVillage 数据集
（38 个类别），**识别结果仅供参考**，实际防治请咨询当地植保站。
