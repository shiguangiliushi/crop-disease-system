"""
能力（capability）口径 —— 全项目"谁能做什么"的**唯一判定处**（第 124 批）
============================================================================

## 为什么要有这个文件

在这之前，"管理员"这个判断被**复制在约 30 处**，而且有三种并不等价的写法：

| 写法 | 语义 | 例子 |
|---|---|---|
| `permission_classes = [IsAdminUser]`（DRF 自带） | **只认 `is_staff`** | `/api/admin/users/*`、反馈、版块、敏感词 |
| `IsAdminOrReadOnly` | `is_staff` / `is_superuser` / `role='ADMIN'` | 病害百科写权限 |
| 每个模块各写一份同样的判定 | 同上 | `_is_admin(user)`（views_dashboard / views_alert / views_notify …） |

于是有两个**已经存在的不一致**（不是新角色带来的）：

1. `role='ADMIN'` 但 `is_staff=False` 的人**能**维护病害百科，**不能**用用户管理接口；
2. `is_staff=True` 但 `role='USER'` 的人两边都能用。

第 106 批的教训就是"注释只写在一处，另一个方法照旧错着"。所以要让
「信息编辑员（EDITOR）」这类角色安全地接进来，必须先让**判定只有一处实现** ——
本文件就是那一处；其余模块一律调 `has_capability()`。

## 三个能力（产品口径）

- `CONTENT`：内容生产与内容事务 —— **第 128 批起它内部再分四个模块**（见下）。
  **EDITOR 拥有的就是这个能力，且只限被授权的模块。**
- `USER_ADMIN`：用户账号与他人数据 —— 用户管理、签发重置链接、专家授予、他人识别记录。
- `BROADCAST`：对全体用户发声与系统开关 —— 系统公告、预警推送、敏感词、论坛版块。

## 内容模块（第 128 批）

`CONTENT` 拆成四个**互不干扰**的模块，按人授权（模型 `EditorModuleGrant`）：

| 模块 | 中文 | 管什么 |
|---|---|---|
| `review` | 内容审核 | 帖子审核（通过/驳回/批量）、评论软删除、置顶与加精 |
| `news` | 新闻管理 | 行业动态增删改、上下架、草稿可见 |
| `pests` | 病害百科 | 病害词条增删改、批量导入、**农事任务**（与百科同属"给农户看的农业资料"） |
| `feedback` | 意见反馈 | 查看全部反馈、回复、批量流转状态 |

规则：
- **全权管理员**（is_staff / is_superuser / role=ADMIN）四个模块**全有**（不查授权表）；
- `role='EDITOR'` 只有 `EditorModuleGrant` 里登记的那些模块；
- 其余账号一个都没有。

⚠️ 少数动作**连内容编辑也不给**（当前有两处）：删除意见反馈、硬删除评论 ——
它们是不可逆动作，用 `is_full_admin()` 判定，**不要**塞进某个模块。

另有 `require_full_admin()` 的语义：见 `has_capability` 下面的说明。

## 与历史行为的关系（很重要）

第 124 批的目标是**行为完全不变**：`is_staff` / `is_superuser` / `role='ADMIN'` 仍然是
"全权管理员"，三个能力全给。第 125 批才把 `EDITOR` 打开（`EDITOR_CAPABILITIES_ENABLED`）。
这样"收敛口径"这一步可以靠现有 508 条测试证明没改行为，再单独开权限。

`ADMIN_USER_CAPABILITIES` 这个常量表是**给前端与测试看的同一份口径**：
`/api/login/`、`/api/check-auth/`、`/api/profile/` 都把 `capabilities` 一起返回，
前端据此显示菜单与按钮（前端只做体验，真正的边界始终在后端）。
"""

from rest_framework import permissions

# ---------------------------------------------------------------------------
# 能力常量
# ---------------------------------------------------------------------------
CAP_CONTENT = 'CONTENT'
CAP_USER_ADMIN = 'USER_ADMIN'
CAP_BROADCAST = 'BROADCAST'

ALL_CAPABILITIES = (CAP_CONTENT, CAP_USER_ADMIN, CAP_BROADCAST)

# ---------------------------------------------------------------------------
# 第 125 批开关
# ---------------------------------------------------------------------------
# `False` = EDITOR 与普通用户一样（第 124 批的收敛阶段，行为与历史完全一致）；
# `True`  = EDITOR 拿到 CONTENT（**第 125 批已打开**，配套测试见
#           `api.tests.CapabilityMatrixTests`）。
# 之所以做成常量而不是直接判断角色：第 124 批需要"改结构但不变行为"，
# 这样那一批的验证（后端全量测试全绿）才有意义。
EDITOR_CAPABILITIES_ENABLED = True

#: 角色显示名（与 models.CustomUser.ROLE_CHOICES 一致，仅用于回包/日志）
ROLE_ADMIN = 'ADMIN'
ROLE_EDITOR = 'EDITOR'
ROLE_USER = 'USER'

# ---------------------------------------------------------------------------
# 内容模块（第 128 批）
# ---------------------------------------------------------------------------
MODULE_REVIEW = 'review'      # 内容审核（审核队列 / 举报处置 / 敏感词）
# 第 151 批：把「论坛交流」从内容审核里**分出来**。
# 动机：此前"能审核"就自动"能管论坛"，想开一个**只管论坛**的编辑员做不到 ——
# 只能连审核队列、举报、敏感词一起给。现在可以只勾这一项。
# ⚠️ 两处口径要一起看：
#   · `is_moderator()`（views_forum）= review **或** forum **或** Moderators 组；
#   · 论坛管理页/评论管理页 = review **或** forum。
#   也就是 review 仍是**宽口径**（老账号不会因为这一批掉权限），forum 是更细的口径。
MODULE_FORUM = 'forum'        # 论坛交流（帖子与评论的管理，含置顶加精与帖子审核）
MODULE_NEWS = 'news'          # 新闻管理
MODULE_PESTS = 'pests'        # 病害百科（含农事任务）
MODULE_FEEDBACK = 'feedback'  # 意见反馈

#: 全部内容模块（顺序即前端展示顺序，与 models.EditorModuleGrant.MODULE_CHOICES 一致）
CONTENT_MODULES = (MODULE_REVIEW, MODULE_FORUM, MODULE_NEWS, MODULE_PESTS, MODULE_FEEDBACK)

#: 模块 → 中文名（错误提示与日志用；前端有自己的 i18n 文案）
MODULE_LABELS = {
    MODULE_REVIEW: '内容审核',
    MODULE_FORUM: '论坛交流',
    MODULE_NEWS: '新闻管理',
    MODULE_PESTS: '病害百科',
    MODULE_FEEDBACK: '意见反馈',
}


def content_modules_of(user):
    """
    该账号**实际拥有**的内容模块列表（顺序同 CONTENT_MODULES）

    · 全权管理员：四个全给（不查授权表 —— 这也是"管理员始终能干活"的保证）；
    · 编辑员：只给 `EditorModuleGrant` 里登记的；
    · 其他：空。

    ⚠️ 这里刻意**不做缓存**：一次请求可能判定多次（一个页面几个接口），
    但每次都是一条极小的 `values_list` 查询，换来的是"改了权限立刻生效"。
    真要优化，应该在请求级缓存（`request._content_modules`），而不是进程级 ——
    否则超管刚撤掉某人的模块，那人还能继续用一段时间。
    """
    if not user or not user.is_authenticated:
        return []
    if is_full_admin(user):
        return list(CONTENT_MODULES)
    if not EDITOR_CAPABILITIES_ENABLED:
        return []
    if getattr(user, 'role', None) != ROLE_EDITOR:
        return []

    from .models import EditorModuleGrant  # 局部导入：避免 models ↔ capabilities 循环依赖

    granted = set(
        EditorModuleGrant.objects.filter(user=user).values_list('module', flat=True)
    )
    return [module for module in CONTENT_MODULES if module in granted]


def has_content_module(user, module):
    """
    该账号是否拥有某个内容模块

    这是**内容侧唯一该用的判定**：病害百科的接口问 `pests`，
    新闻的问 `news`，审核的问 `review`，反馈的问 `feedback`。
    不要再写 `has_capability(user, CAP_CONTENT)` —— 那等于"任意一个模块就能干全部四块"，
    正是第 128 批要拆掉的东西（`CAP_CONTENT` 现在只表示"至少有一个模块"）。
    """
    if module not in CONTENT_MODULES:
        raise ValueError(f'未知内容模块：{module}')
    return module in content_modules_of(user)


def has_any_content_module(user):
    """是否至少有一个内容模块（侧栏里要不要显示"内容"那几项）"""
    return bool(content_modules_of(user))


def is_full_admin(user):
    """
    是否为"全权管理员"（历史上那句 `is_staff or is_superuser or role=='ADMIN'`）

    注意：**必须保留 `is_staff`** —— Django 自带的 `/admin/` 靠它进门，
    把这里改成"按能力"会让现有超管进不去自带后台。
    """
    if not user or not user.is_authenticated:
        return False
    return bool(
        user.is_staff
        or user.is_superuser
        or getattr(user, 'role', None) == ROLE_ADMIN
    )


def has_capability(user, capability):
    """
    user 是否具备某个**粗粒度**能力（全项目唯一判定处）

    · 未登录 → False
    · 全权管理员 → 三项全给
    · EDITOR → 只有 CONTENT，且**仅当他至少被授权了一个内容模块**
      （第 128 批起 CONTENT 表示"能进内容侧"，具体能碰哪一块要用
       `has_content_module(user, 'news')` 这类判定；别再拿 CONTENT 当"全都能干"）
    · 其余 → False

    ⚠️ 少数动作**不该给内容编辑**（当前两处：删除意见反馈、硬删除评论），
    那种地方请显式用 `is_full_admin(request.user)`，不要偷偷把它塞进某个能力或模块里 ——
    能力表要能一眼读懂。
    """
    if not user or not user.is_authenticated:
        return False
    if is_full_admin(user):
        return True
    if not EDITOR_CAPABILITIES_ENABLED:
        return False
    if getattr(user, 'role', None) == ROLE_EDITOR:
        # 第 128 批：CONTENT 现在 = "至少有一个内容模块"
        if capability == CAP_CONTENT:
            return has_any_content_module(user)
        return False
    return False


def capabilities_of(user):
    """
    user 的能力列表（顺序稳定，便于前端与测试断言）

    回包给前端用：`/api/login/`、`/api/check-auth/`、`/api/profile/`。

    ⚠️ 第 128 批起，`CONTENT` 只表示"**至少有一个内容模块**"。
    前端显示侧栏时还要看 `content_modules_of(user)` 才知道能开哪几页。
    """
    return [cap for cap in ALL_CAPABILITIES if has_capability(user, cap)]


def has_any_capability(user):
    """能否进入管理后台（侧栏里至少有一项可看）"""
    return bool(capabilities_of(user))


def check_capability_or_403(user, capability):
    """
    给 APIView 内部用的小工具：不具备能力时直接抛 DRF 的 PermissionDenied

    返回值：None（通过）—— 失败时抛异常，调用方不用写 if not ...: return Response(403)。
    """
    from rest_framework.exceptions import PermissionDenied

    if not has_capability(user, capability):
        raise PermissionDenied('当前账号没有执行该操作的权限')


def check_content_module_or_403(user, module):
    """同上，但针对内容模块（第 128 批）：没有该模块时抛 PermissionDenied"""
    from rest_framework.exceptions import PermissionDenied

    if not has_content_module(user, module):
        raise PermissionDenied(f'当前账号没有「{MODULE_LABELS.get(module, module)}」权限')


# ---------------------------------------------------------------------------
# DRF 权限类
# ---------------------------------------------------------------------------
class HasCapability(permissions.BasePermission):
    """
    按能力判定（`permission_classes = [HasCapability.of(CAP_CONTENT)]`）

    也可以直接用下面几个具体类（更利于 grep 与阅读）：
    `IsContentManager` / `IsUserAdmin` / `IsBroadcastManager`。
    """

    capability = None
    message = '当前账号没有执行该操作的权限'

    def has_permission(self, request, view):
        return has_capability(getattr(request, 'user', None), self.capability)

    @classmethod
    def of(cls, capability):
        """按能力动态生成一个权限类（能力名进类名，报错时看得懂）"""
        if capability not in ALL_CAPABILITIES:
            raise ValueError(f'未知能力：{capability}')
        return type(f'Has{capability.title().replace("_", "")}', (cls,), {'capability': capability})


class HasContentModule(permissions.BasePermission):
    """
    按**内容模块**判定（第 128 批）

    用法：`permission_classes = [HasContentModule.of(MODULE_NEWS)]`，
    或直接用下面四个具体类（更利于 grep）：`IsReviewEditor` / `IsNewsEditor` /
    `IsPestsEditor` / `IsFeedbackEditor`。

    ⚠️ 这才是内容侧该用的权限类；`IsContentManager` 只表示"至少有一个模块"，
    用在内容接口上等于把四个模块又合并回去了。
    """

    module = None

    def has_permission(self, request, view):
        return has_content_module(getattr(request, 'user', None), self.module)

    @classmethod
    def of(cls, module):
        """按模块动态生成一个权限类"""
        if module not in CONTENT_MODULES:
            raise ValueError(f'未知内容模块：{module}')
        return type(
            f'Has{module.title()}Module', (cls,), {'module': module}
        )


class IsContentManager(HasCapability):
    """
    "能进内容侧"（至少有一个内容模块）—— 只用于**不区分模块**的内容入口

    目前只剩少数几处：数据看板（只读、聚合数字）。**具体模块的接口请用
    `HasContentModule` 的四个具体类**，否则会出现"勾了新闻的人也能改词条"。
    """

    capability = CAP_CONTENT


class IsReviewEditor(HasContentModule):
    """内容审核：帖子审核 / 评论处置 / 置顶加精"""

    module = MODULE_REVIEW


class IsNewsEditor(HasContentModule):
    """新闻管理：行业动态增删改与上下架"""

    module = MODULE_NEWS


class IsPestsEditor(HasContentModule):
    """病害百科：词条增删改、批量导入、农事任务"""

    module = MODULE_PESTS


class IsFeedbackEditor(HasContentModule):
    """意见反馈：查看全部反馈与回复"""

    module = MODULE_FEEDBACK


class IsUserAdmin(HasCapability):
    """用户与他人数据：用户管理 / 重置链接 / 专家授予 / 他人识别记录（EDITOR 不可）"""

    capability = CAP_USER_ADMIN


class IsBroadcastManager(HasCapability):
    """对全体发声与系统开关：公告 / 预警推送 / 敏感词 / 论坛版块（EDITOR 不可）"""

    capability = CAP_BROADCAST
