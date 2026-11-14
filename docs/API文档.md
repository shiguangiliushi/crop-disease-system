# API 文档（OpenAPI 3 / drf-spectacular）

> 本文是**接入与使用说明**，不是接口清单。接口清单由代码自动生成，
> 见 `docs/openapi.yaml`（生成命令见第 2 节）。
> 手写文档（`docs/系统完善记录.md`、`docs/角色与权限矩阵.md` 等）继续保留；
> 自动生成的 schema 与手写文档**可能不一致，以代码与实际响应为准**。

## 1. 这是什么

后端此前只有手写文档，没有机器可读的 API 描述。现在接入
[drf-spectacular](https://github.com/tfranzel/drf-spectacular)：

| 能力 | 位置 |
| --- | --- |
| 依赖 | `backend/requirements.txt` → `drf-spectacular==0.30.0` |
| 应用注册 / schema 生成器 / 文档元信息 | `backend/crop_disease_backend/settings.py`（`INSTALLED_APPS`、`REST_FRAMEWORK['DEFAULT_SCHEMA_CLASS']`、`SPECTACULAR_SETTINGS`） |
| 两个路由（**仅管理员**） | `backend/crop_disease_backend/urls.py` → `name='schema'`、`name='swagger-ui'` |
| 生成产物 | `docs/openapi.yaml`（OpenAPI 3.0.3） |

修改代码后重新生成即可，不需要手工维护接口清单。

## 2. 生成 OpenAPI 3 schema

在 `backend/` 目录下执行（Windows 示例，解释器按本机环境替换）：

```powershell
cd D:\新建文件夹\crop-disease-system\backend
C:\Users\zhx\anaconda3\envs\crop_env\python.exe manage.py spectacular --file ..\docs\openapi.yaml
```

- 成功时退出码为 0，正常输出是空（schema 直接写入文件）。
- 也可输出 JSON：`manage.py spectacular --file ..\docs\openapi.json --format openapi-json`。
- 生成耗时约十几秒（本机实测），文件约 **256 KB / 262,004 字节 / 144 条 path**。
  小于 2 MB，可以随仓库提交；若将来膨胀超过 2 MB 就**不要提交**，只保留本文的生成命令。
- 建议在改完接口后重新生成并 `git diff`：schema 的差异就是接口契约的变更。

### ⚠️ 不要加 `--fail-on-warn`

本项目的 schema 是**尽力生成**（graceful fallback）：手写 `APIView`、自定义认证类等
会让 drf-spectacular 打 warning / error，但 schema 仍然可用。加 `--fail-on-warn`
会把这类"未完美标注"判成失败，导致 CI 红掉却无法修（需要逐个视图标注，见第 4 节）。

## 3. 在线文档（Swagger UI，仅管理员）

启动后端：

```powershell
cd D:\新建文件夹\crop-disease-system\backend
C:\Users\zhx\anaconda3\envs\crop_env\python.exe manage.py runserver
```

| 地址 | 内容 |
| --- | --- |
| <http://127.0.0.1:8000/api/schema/> | OpenAPI 3 schema（YAML，Swagger UI 从这里加载） |
| <http://127.0.0.1:8000/api/docs/> | Swagger UI 在线文档 |

**访问权限：仅管理员**（`IsAdminUser`，即 `is_staff=True`）。医生 / 编辑员 / 普通用户
一律 **403** —— 内部接口清单不对非管理员开放。匿名访问同样是 **403**。

浏览器访问方式（本项目全局认证只认 Token，这两个文档视图**额外**放行了会话）：

1. 先在 <http://127.0.0.1:8000/admin/> 用管理员账号登录（建立会话）；
2. 再打开 <http://127.0.0.1:8000/api/docs/>。

用 curl / 脚本访问（带管理员 Token，适用于 `Token` 或 `DeviceToken`）：

```bash
curl -H "Authorization: Token <管理员token>" http://127.0.0.1:8000/api/schema/
```

> 说明：`_DOC_AUTHENTICATION_CLASSES`（见 `urls.py`）**只作用于这两个文档视图**，
> 没有写进全局 `REST_FRAMEWORK`。全局若加 `SessionAuthentication` 会造成
> "界面显示 A、服务端按 B 执行"的身份错位（第 19 批已论证），别那么做。

> Swagger UI 的 JS/CSS 默认来自 jsDelivr CDN（`SPECTACULAR_SETTINGS['SWAGGER_UI_DIST']`
> 默认值）。**内网 / 断网环境**下页面能打开但 UI 不渲染：需要另装
> `drf-spectacular-sidecar`，并把 `SWAGGER_UI_DIST` 设为 `'SIDECAR'`。

## 4. schema 警告怎么处理

### 4.1 当前基线（2026-11-15，`drf-spectacular 0.30.0`，本机实测）

命令输出末尾的统计：

```text
Schema generation summary:
Warnings: 283 (161 unique)
Errors:   393 (80 unique)
```

> 这个数字会随代码变化，**不是门禁指标**。重新生成后若数量明显上升，按下表定位新增项。

按"唯一告警"分类：

| 类型 | 数量 | 原因 | 处理建议 |
| --- | --- | --- | --- |
| `Error [View]: unable to guess serializer` | 80 | 手写 `APIView` 没有 `serializer_class` / `get_serializer`，也没有 `@extend_schema` | 加 `@extend_schema(request=..., responses=...)`；或让视图改用 `GenericAPIView`。**这些视图目前不会出现在 schema 里**（drf-spectacular 会整条跳过） |
| `Warning [View]: could not resolve authenticator DeviceTokenAuthentication` | 93 | 自定义认证类 `api.authentication.DeviceTokenAuthentication` 没有对应的 `OpenApiAuthenticationExtension` | 写一个 extension 类（见 4.2），一次可消除整类告警 |
| `Warning [View]: unable to resolve type hint for function "get_xxx"` | 55 | `SerializerMethodField` 的 `get_xxx` 方法没有返回类型注解 | 在方法上加注解：`def get_xxx(self, obj) -> str:`（或 `-> int` / `-> bool` / `-> list[...]`） |
| `Warning: operationId "..." has collisions` | 9 | 列表/详情路由由同一个方法名生成，operationId 撞名 | 可忽略（已自动加数字后缀）；需要固定 id 时加 `@extend_schema(operation_id=...)` |
| `Warning: could not derive type of path parameter "id"` | 2 | 专家咨询路由两处 `<user_id>` / `<id>` 未能在 viewset 中推导类型 | `@extend_schema(parameters=[OpenApiParameter(...)])` 显式声明 |
| `Warning: enum naming ... "status"` | 1 | 多个 `status` 选项集名称冲突（已自动改名 `StatusC30Enum`） | 在 `SPECTACULAR_SETTINGS['ENUM_NAME_OVERRIDES']` 里登记名称即可 |
| `Warning: could not resolve serializer field "FlexibleJSONField"` | 1 | 自定义 JSON 字段没有 OpenAPI 映射，按 `string` 兜底 | 用 `@extend_schema_field(OpenApiTypes.OBJECT)` 标注 |

### 4.2 消除 `DeviceTokenAuthentication` 告警的示例

新增一个 extension 文件（例如 `backend/api/schema_extensions.py`，并在 `api` 应用的
`AppConfig.ready()` 里导入一次），内容大致为：

```python
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class DeviceTokenAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'api.authentication.DeviceTokenAuthentication'
    name = 'deviceToken'   # Swagger UI 的 securitySchemes 名称

    def get_security_definition(self, auto_schema):
        return {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': 'Token <key>（DeviceToken 或旧 Token）',
        }
```

> 本次任务只做"接入"，**没有**逐个视图加 `@extend_schema`、也没有新增 extension。
> 所以 80 个 `unable to guess serializer` 对应的接口在 schema 里缺失是**已知现状**，
> 不是回归；需要它们进文档时按上表逐条补标注即可。

## 5. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| 浏览器打开 `/api/docs/` 是 403 | 未在 `/admin/` 登录、登录的不是管理员，或用了无痕窗口（没有会话） |
| 文档页白屏 / 无样式 | Swagger UI 静态资源来自 CDN，内网/断网环境见第 3 节末尾的 sidecar 说明 |
| schema 里找不到某个接口 | 大概率是该视图被 `unable to guess serializer` 跳过（见 4.1 第一行） |
| `manage.py spectacular` 报 `ImproperlyConfigured` | 生产配置自检拦截（`DJANGO_DEBUG=False` 且密钥/`ALLOWED_HOSTS` 未配）；按提示设置环境变量，或临时 `DJANGO_ALLOW_INSECURE=1` |
| schema 与手写文档不一致 | 自动生成以代码为准；发现手写文档过期时顺手更新，或给视图补 `@extend_schema` |
