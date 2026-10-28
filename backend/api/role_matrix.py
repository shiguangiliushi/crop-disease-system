"""
信息编辑员「各自的功能」—— 唯一的一张权限矩阵表（第 178 批）
================================================================================

## 为什么要有这张表

第 124/128/151 批把权限收口成了"能力 + 内容模块"（见 `capabilities.py`），
代码侧是干净的。但**没有一处能一眼看懂**"勾了「新闻管理」的编辑员到底能干什么"：

* 权限判定散在 26 处视图体内（`has_content_module(...)`）；
* 前端侧栏是另一份列表（`AdminLayout.vue` 的 navItems）；
* 文档里只有零散注释。

结果就是"出了问题只能翻代码"，而且**没人能验证**矩阵有没有腐烂 ——
比如某天有人给新闻接口写了 `MODULE_PESTS`，测试不会响。

这个文件把"谁能调什么"写成**一张显式的表**，然后：

* `manage.py role_matrix` 打印它（含"某个人实际能看到哪几页"）；
* `api.tests.RoleMatrixTests` 拿它**真的去请求**每个接口，验证 允许的没被 403、
  不允许的一律 403 —— 表一旦与代码不一致，测试立刻红；
* `manage.py role_matrix --write-docs` 生成 `docs/角色与权限矩阵.md`（文档不再是手抄的）。

## 表怎么读

每行是 `(method, path, allow, note)`：

* `allow` 是**允许的角色/能力集合**，语义是"其中之一即可"（与代码里的 or 一致）；
* 取值：`'review'`/`'forum'`/`'news'`/`'pests'`/`'feedback'` = 内容模块；
  `'USER_ADMIN'` = 用户管理能力；`'BROADCAST'` = 对全体发声能力；
  `'FULL_ADMIN'` = 仅全权管理员（不可逆动作）；
* `note` 说明这个接口干什么 —— 它会进文档，所以写人话。

⚠️ **改代码时也要改这张表**：这是刻意的 —— 表变了，`--write-docs` 与测试才会跟着动，
否则文档与测试就成了摆设。
"""

#: 内容模块 → 它解锁的管理端页面（与 frontend/src/components/AdminLayout.vue 的 navItems 对应）
#:
#: 第 183 批：`review` 与 `forum` 现在指向**同一页** ——
#: 原来的 `/admin/review`（内容审核）、`/admin/forum`（论坛管理）、`/admin/comments`（评论管理）
#: 三页合并成了 `/admin/content`「内容管理」（页内三个页签：帖子 / 评论 / 举报）。
#: 这三个页签里，帖子与评论是 review **或** forum 任一即可（与后端 `is_moderator()` /
#: `_reject_non_moderator` 同口径）；**举报从第 189 批起也归这两个模块**
#: （此前只给全权管理员），但只放开"看与处置"这一半 ——
#: 举报人身份与"同时隐藏内容"仍只给全权管理员，见 ENDPOINT_RULES 里
#: `/api/reports/` 那两行与 `views_report._can_see_reporter()`。
MODULE_PAGES = {
    'review': ['/admin/content'],
    'forum': ['/admin/content'],
    'news': ['/admin/news'],
    'pests': ['/admin/pests'],
    'feedback': ['/admin/feedback'],
}

#: 内容模块 → 中文名（与 capabilities.MODULE_LABELS 保持一致）
MODULE_LABELS = {
    'review': '内容审核',
    'forum': '论坛交流',
    'news': '新闻管理',
    'pests': '病害百科',
    'feedback': '意见反馈',
}

#: 三个能力各自解锁的页面（内容页由模块决定，所以这里只列非内容的）
#:
#: 第 186 批：`BROADCAST` 从 `/admin/boards` 改成 `/admin/health` —— 版块管理并入了
#: 「系统」页（`/admin/health?tab=boards`，旧地址 `/admin/boards` 前端重定向过来）。
#: ⚠️ 这一行说的是"**这一页有他能用的东西**"，不是"整页都给他"：
#: BROADCAST 的人进「系统」页**只看到「版块管理」一个页签**，系统健康与操作日志
#: 两个页签不画给他（那两条接口是仅全权管理员，见 FULL_ADMIN_PAGES 与 ENDPOINT_RULES）。
#: 页签按权限显示这件事由 `AdminSystemHubView.vue` 的 tabs 负责，
#: 后端对应的是 `/api/admin/health/` 与 `/api/admin/audit-logs/` 的 `IsFullAdmin` 门禁。
CAPABILITY_PAGES = {
    'USER_ADMIN': ['/admin/users'],   # 第 184 批：识别记录并入用户管理页的页签
    'BROADCAST': ['/admin/health'],   # 第 186 批：版块管理成为「系统」页的页签
}

#: 任何能进后台的人都能看的页面（只读聚合，没有他人明细）
COMMON_PAGES = ['/admin/dashboard']

#: 仅全权管理员能看的页面
#:
#: 第 185 批：这一档原来有两页（`/admin/health` 系统健康、`/admin/audit-logs` 操作日志），
#: 现在合并成**一页两页签**（`/admin/health?tab=health|audit`，侧栏一项「系统」）——
#: 两者本来就是同一档：系统健康会暴露服务器路径与部署细节，操作日志显示"谁对谁做了什么"。
#: `/admin/audit-logs` 仍是**保留下来的旧地址**（前端重定向到 `?tab=audit`），
#: 但它不再是侧栏入口，所以不在这张"页面"表里（与第 183/184 批对旧地址的处理一致）。
#:
#: ⚠️ 第 186 批：`/admin/health` **同时**出现在 `CAPABILITY_PAGES['BROADCAST']` 里 ——
#: 同一页被两档共用（BROADCAST 的人只为「版块管理」页签而来）。所以这一行**不能**读成
#: "整页都给全权管理员"：它说的是"这一页里**有**仅全权管理员能用的东西"
#: （系统健康与操作日志两个页签、以及 `/api/admin/health/`、`/api/admin/audit-logs/`
#: 两条接口）；反过来，BROADCAST 的人在这一页只画「版块管理」一个页签。
#: 两条边界由 `RoleMatrixTests.test_broadcast_capability_unlocks_the_system_page` 钉住。
FULL_ADMIN_PAGES = ['/admin/health', '/admin/assistant']

#: ★ 权限矩阵：`(method, path, allow, note)`
#:
#: ⚠️ 例外：`ANY_AUTHENTICATED` 里那几条**任何登录用户**都能拿到 200（只是数据范围不同），
#: 所以它们不是"门禁"，`RoleMatrixTests` 也不会拿它们去验 403 —— 见下面那个常量的说明。
ENDPOINT_RULES = (
    # -- 内容审核 / 论坛交流（这两个模块在"评论与帖子管理"上是**或**的关系）--
    ('GET', '/api/admin/comments/', ('review', 'forum'), '控制台评论列表（跨帖子）'),
    ('POST', '/api/admin/comments/bulk-delete/', ('review', 'forum'), '批量软删除评论'),
    ('POST', '/api/admin/comments/1/soft-delete/', ('review', 'forum'), '软删除单条评论（内容置为已删除）'),
    ('DELETE', '/api/admin/comments/1/', ('FULL_ADMIN',), '彻底删除评论（不可逆）'),

    # -- 举报（第 189 批：从"仅全权管理员"改为 review/forum 也能管线索）--
    #     ⚠️ 这两行给的是"看别人的举报 + 处置（改状态/备注）"，**不包括**：
    #       · 举报人身份（`reporter.username` / `reporter.id` / `target_user_id`）→ 仅全权管理员；
    #       · `hide_content=true`（下架内容，不可逆）→ 仅全权管理员，编辑员传了也不生效。
    #     所以别把这两行读成"举报整块给编辑员了"。
    ('GET', '/api/reports/', ('review', 'forum'), '举报列表与待处理计数（举报人身份仅全权管理员可见）'),
    ('POST', '/api/reports/1/handle/', ('review', 'forum'), '处置举报（改状态 + 备注；同时隐藏内容仅全权管理员）'),

    # -- 新闻管理 --
    # ⚠️ `GET /api/news/` **不在**这张表里：它对所有人开放（农户端要读行业动态）。
    #    管理员能看到未上架草稿靠的是 `?is_published=false` 参数，而本表按**路径**组织，
    #    区分不了参数 —— 所以这里只列"编辑员专属"的写操作。
    #    （这一行是矩阵测试第一次跑时抓出来的：普通农户 GET 它返回 200，不是权限漏洞，是表写错了。）
    ('POST', '/api/news/', ('news',), '新建新闻'),
    ('PUT', '/api/news/1/', ('news',), '修改新闻'),
    ('DELETE', '/api/news/1/', ('news',), '删除新闻'),

    # -- 病害百科 --
    ('POST', '/api/pests/', ('pests',), '新建病害词条'),
    ('PUT', '/api/pests/1/', ('pests',), '修改词条'),
    ('DELETE', '/api/pests/1/', ('pests',), '删除词条'),
    ('POST', '/api/pests/import/', ('pests',), '批量导入词条'),
    ('POST', '/api/calendar/tasks/', ('pests',), '农事任务（与百科同属"给农户看的农业资料"）'),

    # -- 意见反馈 --
    # ⚠️ `GET /api/feedback/` **不在**表里：它对所有人开放，返回的是**他自己的**反馈
    #    （`FeedbackView.get_queryset` 里 `filter(user=user)`）。反馈编辑员能看到全部，
    #    靠的是**数据范围**变宽，不是权限变松 —— 权限类仍是 `IsAuthenticated`。
    #    这也是矩阵测试第二次跑时抓出来的（普通用户 GET 它返回 200，不是漏洞）。
    ('POST', '/api/feedback/1/reply/', ('feedback',), '回复反馈'),
    ('POST', '/api/feedback/bulk-status/', ('feedback',), '批量流转状态'),
    # 批量删除**比批量改状态更严**：类上是 feedback 模块，方法体内再判 is_full_admin
    # （见 views.FeedbackView.bulk_delete 的 docstring：批量不可逆，不等于"能看全部"就能一次抹掉一批）
    ('POST', '/api/feedback/bulk-delete/', ('FULL_ADMIN',), '批量删除反馈（不可逆）'),

    # -- 用户管理能力 --
    ('GET', '/api/admin/users/', ('USER_ADMIN',), '用户列表'),
    ('POST', '/api/admin/users/1/reset-link/', ('USER_ADMIN',), '签发密码重置链接'),
    ('DELETE', '/api/admin/users/1/', ('USER_ADMIN',), '删除账号'),
    ('GET', '/api/admin/detections/', ('USER_ADMIN',), '识别记录（跨用户，含用户身份）'),

    # -- 对全体发声能力 --
    ('GET', '/api/sensitive-words/', ('BROADCAST',), '敏感词列表'),
    ('POST', '/api/sensitive-words/', ('BROADCAST',), '新增敏感词'),
    ('POST', '/api/announcements/', ('BROADCAST',), '发布系统公告'),
    ('POST', '/api/forums/boards/', ('BROADCAST',), '新建论坛版块'),

    # -- 仅全权管理员 --
    ('GET', '/api/admin/health/', ('FULL_ADMIN',), '系统健康（暴露服务器路径与部署细节）'),
    ('GET', '/api/admin/audit-logs/', ('FULL_ADMIN',), '操作日志（谁对谁做了什么）'),
    # 第 228 批：看板里有别人的提问原文与模型成本，与上面两条同一档
    ('GET', '/api/admin/assistant/stats/', ('FULL_ADMIN',), '助手质量看板（降级率 / 知识库缺口）'),
)

#: **任何登录用户**都能拿到 200 的路径 —— 它们不是门禁，只是"返回的数据范围"不同
#:
#: 目前只有一条：`GET /api/reports/`（第 41 批口径，第 189 批沿用）
#:   · 有 `review`/`forum` 模块的人 → 看**别人的**举报（列表 + 待处理计数）；
#:   · 其他登录用户（含普通农户）→ 只看**自己提交的**举报（`count` 里不含别人的）。
#:
#: 为什么仍留在 `ENDPOINT_RULES` 里：这张表同时喂给**文档生成器**与**前端"编辑员能做什么"
#: 对话框**，去掉它那两处就看不到举报了。但 `RoleMatrixTests` 的身份探测必须跳过它 ——
#: 否则会得出"普通农户有举报权限"这种假结论（它拿到的其实是自己那条）。
#: 真正的门禁在"能不能看别人的"上，由 `ReportTests` 与
#: `ForumOnlyEditorTests.test_editor_can_see_and_handle_reports_but_not_reporter` 钉住。
ANY_AUTHENTICATED_PATHS = ('/api/reports/',)

#: 三个角色的一句话说明（文档与命令输出用）
ROLE_NOTES = {
    'ADMIN': '全权管理员：三个能力全给，五个内容模块全给（不查授权表）',
    'EDITOR': '信息编辑员：只有 CONTENT，且只限被勾选的模块；碰不到账号与他人数据，也不能对全体发声',
    'USER': '普通农户：只能用自己的识别/记录/论坛等农户端功能，进不了管理后台',
}


def allowed(allow, capabilities, modules):
    """
    按矩阵行判断"这个账号能不能调"

    @param allow: 该行的允许集合（见文件头说明）
    @param capabilities: 账号的能力列表（`capabilities_of`）
    @param modules: 账号的内容模块列表（`content_modules_of`）
    """
    for item in allow:
        if item in ('USER_ADMIN', 'BROADCAST'):
            if item in capabilities:
                return True
        elif item == 'FULL_ADMIN':
            # 全权管理员从 `capabilities` 里看不出（它三项全给）——单独传进来
            if 'FULL_ADMIN' in capabilities:
                return True
        elif item in modules:
            return True
    return False


def pages_of(capabilities, modules, is_full_admin=False):
    """
    该账号在管理后台能看到哪些页面（顺序：公共 → 能力 → 模块 → 仅全权）

    ⚠️ 第 183 批起这里会**保序去重**：`review` 与 `forum` 指向同一页
    （`/admin/content` 的三个页签里，帖子与评论两个页签两边都能进），
    同时勾了这两个模块的人不该在"能进的页面"里看到两次 `/admin/content`。
    """
    pages = list(COMMON_PAGES)
    for capability, items in CAPABILITY_PAGES.items():
        if capability in capabilities:
            pages.extend(items)
    for module in MODULE_PAGES:
        if module in modules:
            pages.extend(MODULE_PAGES[module])
    if is_full_admin:
        pages.extend(FULL_ADMIN_PAGES)
    unique = []
    for page in pages:
        if page not in unique:
            unique.append(page)
    return unique


def module_functions(module):
    """
    某个模块"能做的动作"清单（第 179 批）

    直接从矩阵表的 `note` 派生，**不手抄第二份** —— 表改了这里跟着变。
    给控制台"开通编辑员"的对话框用：勾了「新闻管理」，旁边就列出他能做哪几件事，
    授权的人不必凭记忆猜。
    """
    seen = []
    for _method, _path, allow, note in ENDPOINT_RULES:
        if module in allow and note not in seen:
            seen.append(note)
    return seen


def matrix_payload():
    """
    矩阵的 JSON 形态（第 179 批）

    控制台的"开通编辑员 / 改角色"对话框与 `role_matrix` 命令用的是**同一份数据**：
    命令给人看，接口给界面用，测试盯着两边一致。
    """
    from .capabilities import CONTENT_MODULES

    return {
        'roles': [{'key': key, 'note': note} for key, note in ROLE_NOTES.items()],
        'modules': [
            {
                'key': module,
                'label': MODULE_LABELS.get(module, module),
                'pages': MODULE_PAGES.get(module, []),
                'functions': module_functions(module),
            }
            for module in CONTENT_MODULES
        ],
        'capability_pages': CAPABILITY_PAGES,
        'common_pages': COMMON_PAGES,
        'full_admin_pages': FULL_ADMIN_PAGES,
    }


def describe_user(user):
    """
    给一个账号算出"他是谁、能干什么"（`manage.py role_matrix <username>` 用）

    刻意不做缓存：这是排查工具，要的是**此刻**的真实状态
    （"我刚给他勾了新闻，他怎么还看不到" 这类问题就靠它回答）。
    """
    from .capabilities import (
        CAP_BROADCAST, CAP_USER_ADMIN, capabilities_of, content_modules_of, is_full_admin,
    )

    caps = capabilities_of(user)
    modules = content_modules_of(user)
    full = is_full_admin(user)
    # `is_full_admin` 在能力列表里看不出来（三项全给），这里显式补一个标记给矩阵用
    matrix_caps = list(caps) + (['FULL_ADMIN'] if full else [])
    return {
        'username': getattr(user, 'username', ''),
        'role': getattr(user, 'role', ''),
        'is_full_admin': full,
        'capabilities': caps,
        'user_admin': CAP_USER_ADMIN in caps,
        'broadcast': CAP_BROADCAST in caps,
        'modules': modules,
        'pages': pages_of(caps, modules, full),
        'matrix_caps': matrix_caps,
    }
