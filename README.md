# 智能农作物叶片病虫害识别系统

上传叶片照片，得到**病害名称、置信度与防治建议**；配套病害百科、识别历史、预警、种植日历、
智能问答、专家咨询、论坛，以及完整管理后台。

> 桌面端 + 移动端（Vant H5 / uni-app）共用一个 Django REST 后端；识别用 YOLOv8 目标检测，
> **结果仅供参考**。逐条实现说明见 [`docs/系统完善记录.md`](docs/系统完善记录.md)。

![识别结果](docs/images/farmer-detect-result.webp)

## 功能

| 端 | 模块 | 能力 |
|---|---|---|
| 农户 | 病虫害识别 | 上传/拍照，返回病害名、置信度、标注框；可先选作物减少误判；下载报告 |
| 农户 | 智能问答 | 只依据站内知识库作答并带来源编号，查不到就明说；可上传叶片照片当"锚点"（图不落盘） |
| 农户 | 识别后追问 | 识别结果页直接问助手，回答锚定该病害并给出来源 |
| 农户 | 病害百科 | 38 类词条（26 病害 + 12 健康）、症状与防治、溯源来源、中英双语 |
| 农户 | 预警 / 日历 | 当期高发病害（未登录可看）；农事任务按月 + 识别记录分布 |
| 农户 | 社区 | 专家咨询、论坛（发帖/评论/点赞收藏/草稿/置顶加精）、私信、通知、举报 |
| 管理 | 内容 | 帖子 / 评论 / 举报三个页签（含已删除追溯、敏感词库） |
| 管理 | 用户 | 停用·恢复、角色与模块授权、开通编辑员、签发重置链接、注销冷静期 |
| 管理 | 百科 / 新闻 / 反馈 | 词条增删改与批量导入、行业动态、意见反馈流转 |
| 管理 | 系统 | 操作日志（23 类动作，只读）、系统健康（环境自检 + 14 天趋势）、助手质量看板、版块管理 |

权限：**3 档能力**（`CONTENT` / `USER_ADMIN` / `BROADCAST`）+ **全权标记**（`FULL_ADMIN`）
× **5 个内容模块**（`review` / `forum` / `news` / `pests` / `feedback`）。
原则：**可逆的审核动作给编辑员，不可逆动作只给全权管理员**。
接口级矩阵见 [`docs/角色与权限矩阵.md`](docs/角色与权限矩阵.md)（脚本生成，勿手改）。

## 界面

| | |
|---|---|
| ![识别首页](docs/images/farmer-home.webp) | ![病害百科](docs/images/farmer-wiki.webp) |
| ![智能问答](docs/images/farmer-assistant-answer.webp) | ![论坛](docs/images/farmer-forum.webp) |
| ![数据看板](docs/images/admin-dashboard.webp) | ![系统健康](docs/images/admin-health.webp) |

> 截图由 `frontend/scripts/capture-docs-shots.mjs` 重截、`docs/tools/optimize_readme_images.py`
> 转 WebP；**改界面后请重跑这两个脚本**（第 189 批因漏跑，图上还是已合并掉的侧栏入口）。

## 技术栈与结构

```
backend/    Django 5.2 + DRF（SQLite、YOLOv8；含 gunicorn.conf.py / Dockerfile）
frontend/   桌面端 Vue 3 + Element Plus + Vite   :5173
mobile/     移动端 Vue 3 + Vant + Vite           :5174（独立应用）
mobile-uni/ 移动端 uni-app（H5 :5175，后续出小程序/APP）
docs/       设计与运维文档、README 配图、工具脚本；tools/ 开发辅助；deploy/ 反代示例
```

识别链路：`图片 → Django → YOLOv8（backend/api/newmodels/best.pt，39 类）→ 标注图 + 词条映射 → 结构化结果`。

> 换模型后先跑 `python manage.py check_model_labels`：**权重里的类名是唯一权威**，
> 与词条错位会"框上 A、详情 B"且全程静默。

## 快速开始

```bash
cd backend && pip install -r requirements.txt && python manage.py migrate
python manage.py check_env && python manage.py init_forum_boards   # 自检 + 首次初始化
python manage.py runserver 127.0.0.1:8000

cd frontend   && npm install && npm run dev        # :5173
cd mobile     && npm install && npm run dev        # :5174
cd mobile-uni && npm install && npm run dev:h5     # :5175
```

- 开发环境约定为 conda `crop_env`（Python 3.11）；生产依赖另装 `requirements-prod.txt`，
  启动与环境变量见 [`docs/部署与运维.md`](docs/部署与运维.md)。
- 移动端上线前按 [`docs/移动端真机自测清单.md`](docs/移动端真机自测清单.md) 在真机过一遍。
- 演示数据：`add_sample_news` / `add_popular_pests` / `add_detailed_pests` 等（`manage.py help` 查全部）。

## 测试

```bash
cd backend  && python manage.py test api.tests        # 后端
cd frontend && npm run test:unit && npm run type-check && npm run check   # 桌面端
cd frontend && npm run e2e                            # Playwright（真实后端 + 浏览器）
python docs/tools/check_line_endings.py               # 行尾 LF
python docs/tools/check_md_links.py                   # 文档链接/图片存在且已入库
python docs/tools/check_i18n_coverage.py              # 模板裸露中文（当前 0 条）
python docs/tools/push_and_verify.py                  # 推送后核对远端 ref
```

`npm run check` 含 6 条一致性检查（中英语言包、重复键、术语一致、Element Plus 注册、路由 docTitle）。

## 必须知道的约定

| 事项 | 说明 |
|---|---|
| 两个登录态 | 桌面 `sessionStorage.auth_token`、移动端 `localStorage.mobile_token`；写错地方会"看起来已登录、接口全 401" |
| 按设备轮换 Token | 手机与桌面可同时在线；改密码 / 停用 / 注销会吊销所有设备 |
| `is_active=False` 登录 | 被 `ModelBackend` 直接拒绝 → 停用/冷静期判断必须在 `authenticate()` **之前** |
| 软删除 | 评论可恢复（留原文）；帖子刻意不留，但删帖写审计日志 |
| 审计日志 | 管理端写操作调 `api/audit.py: log_admin_action(...)`；`detail` 绝不放凭证 |
| 计数 | 点赞/评论计数只由模型层维护，视图不要再 `F()+1` |
| 密码策略 | 唯一来源 `api/password_policy.py`；登录不做长度校验 |
| 匿名密码端点 | 必须挂 `ScopedRateThrottle`，别删限流 |
| 定时任务 | 备份 / 完整性校验 / 健康快照 / media 清理 / 注销到期，五件事缺一件都是"安静的故障" |
| 改 .py 要重启 | 开发用 `runserver --noreload` |
| 行尾 | 全仓库 LF；Django 迁移在 Windows 下是 CRLF，提交前跑行尾自检 |

## 文档导航

| 想做的事 | 先读 |
|---|---|
| 部署 / 备份 | [`docs/部署与运维.md`](docs/部署与运维.md)、[`docs/备份与恢复.md`](docs/备份与恢复.md) |
| 权限与角色设计 | [`docs/角色与权限矩阵.md`](docs/角色与权限矩阵.md)、[`docs/内容编辑角色方案.md`](docs/内容编辑角色方案.md) |
| 智能问答 / 知识库 | [`docs/智能回答助手框架.md`](docs/智能回答助手框架.md)、[`docs/知识库入库方案.md`](docs/知识库入库方案.md) |
| 为什么这样设计 | [`docs/系统完善记录.md`](docs/系统完善记录.md)（按批记录，含索引） |
| 还差哪些功能 | [`docs/功能缺口评估.md`](docs/功能缺口评估.md)（历史快照） |
| 提交与推送约定 | [`docs/提交与仓库约定.md`](docs/提交与仓库约定.md) |
| 端到端测试 | [`frontend/e2e/README.md`](frontend/e2e/README.md) |
| 环境变量 | [`backend/.env.example`](backend/.env.example)、生产模板 [`backend/.env.production.example`](backend/.env.production.example) |

## 许可

仅用于学习与研究；识别结果不构成农业防治建议。
