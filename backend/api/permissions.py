from rest_framework import permissions  # 导入Django REST Framework权限类
from .models_forum import ForumBoard, Post, Comment  # 导入论坛相关模型
# 第 124 批：管理员口径统一收口到 capabilities.py（此前同一个判定被复制在约 30 处）
# 第 128 批：内容能力再拆成四个模块 —— 这里守的是**病害百科**，因此问 `pests` 模块
from .capabilities import MODULE_PESTS, has_content_module, is_full_admin


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    **病害百科**维护者（`pests` 内容模块）可写、任何人可读

    - 病害百科等公共资料：所有用户（含未登录）可查看
    - 新增/修改/删除仅限具备 `pests` 模块的账号
      （全权管理员四个模块全有；信息编辑员要由超管单独勾选）

    ⚠️ 第 124 批改动：这里原来写的是
    `user.is_staff or user.is_superuser or role == 'ADMIN'` —— 与项目里的另外
    两种写法（DRF 自带的 `IsAdminUser` 只认 is_staff、各模块自己抄一份的 `_is_admin`）
    并不等价。现在统一调 `capabilities.py`，判定只有一处实现。
    ⚠️ 第 128 批改动：从笼统的 `CONTENT` 收窄到 `pests` 模块 ——
    勾了"新闻管理"的编辑员不该能改病害词条。
    """

    def has_permission(self, request, view):
        # 安全方法（GET/HEAD/OPTIONS）允许任何请求
        if request.method in permissions.SAFE_METHODS:
            return True

        return has_content_module(getattr(request, 'user', None), MODULE_PESTS)


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    对象所有者或只读权限
    允许对象所有者进行编辑/删除操作，其他用户只能读取
    """

    def has_object_permission(self, request, view, obj):
        # 读取权限允许任何请求（GET, HEAD, OPTIONS）
        if request.method in permissions.SAFE_METHODS:
            return True

        # 只有对象的所有者才有写入权限（PUT, PATCH, DELETE）
        return obj.author == request.user  # 检查当前用户是否为对象的作者


class IsModeratorOrReadOnly(permissions.BasePermission):
    """
    版主或只读权限
    允许版主和管理员进行编辑操作，其他用户只能读取
    """

    def has_permission(self, request, view):
        # 读取权限允许任何请求
        if request.method in permissions.SAFE_METHODS:
            return True

        # 检查用户是否是版主或管理员
        return request.user.is_authenticated and (  # 用户已认证且
                request.user.is_staff or  # 是管理员或
                request.user.groups.filter(name='Moderators').exists()  # 属于Moderators组
        )


class IsPostOwnerOrModerator(permissions.BasePermission):
    """
    帖子作者或版主权限
    允许帖子作者或版主编辑/删除帖子，其他用户只能读取
    """

    def has_object_permission(self, request, view, obj):
        # 读取权限允许任何请求
        if request.method in permissions.SAFE_METHODS:
            return True

        # 检查用户是否是帖子作者或版主
        is_owner = obj.author == request.user  # 当前用户是否为帖子作者
        is_moderator = request.user.is_authenticated and (  # 用户已认证且
                request.user.is_staff or  # 是管理员或
                request.user.groups.filter(name='Moderators').exists()  # 属于Moderators组
        )

        return is_owner or is_moderator  # 满足任一条件即可


class IsCommentOwnerOrPostOwner(permissions.BasePermission):
    """
    评论作者或帖子作者权限
    允许评论作者、帖子作者或版主编辑/删除评论，其他用户只能读取
    """

    def has_object_permission(self, request, view, obj):
        # 读取权限允许任何请求
        if request.method in permissions.SAFE_METHODS:
            return True

        # 检查用户是否是评论作者、帖子作者或版主
        is_comment_owner = obj.author == request.user  # 当前用户是否为评论作者
        is_post_owner = obj.post.author == request.user  # 当前用户是否为帖子作者
        is_moderator = request.user.is_authenticated and (  # 用户已认证且
                request.user.is_staff or  # 是管理员或
                request.user.groups.filter(name='Moderators').exists()  # 属于Moderators组
        )

        return is_comment_owner or is_post_owner or is_moderator  # 满足任一条件即可


class IsBoardModerator(permissions.BasePermission):
    """
    版块版主权限
    检查用户是否为特定版块的版主
    """

    def has_permission(self, request, view):
        # 获取版块ID（从URL参数或请求数据中）
        board_id = view.kwargs.get('board_id') or request.data.get('board')
        if not board_id:
            return False  # 如果没有提供版块ID，拒绝访问

        try:
            # 尝试获取版块对象
            board = ForumBoard.objects.get(id=board_id)
        except ForumBoard.DoesNotExist:
            return False  # 如果版块不存在，拒绝访问

        # 检查用户是否是版主或管理员
        return request.user.is_authenticated and (  # 用户已认证且
                request.user.is_staff or  # 是管理员或
                request.user in board.moderators.all()  # 是该版块的版主
        )


class CanEditPost(permissions.BasePermission):
    """
    是否可以编辑帖子
    检查用户是否有权限编辑特定帖子
    """

    def has_object_permission(self, request, view, obj):
        # 只有作者和版主可以编辑
        is_owner = obj.author == request.user  # 当前用户是否为帖子作者
        is_moderator = request.user.is_authenticated and (  # 用户已认证且
                request.user.is_staff or  # 是管理员或
                request.user.groups.filter(name='Moderators').exists() or  # 属于Moderators组或
                obj.board.moderators.filter(id=request.user.id).exists()  # 是该版块的版主
        )

        return is_owner or is_moderator  # 满足任一条件即可


class CanDeletePost(permissions.BasePermission):
    """
    是否可以删除帖子
    只有作者或管理员可以删除帖子（版主通常不能删除帖子）

    第 124 批：管理员条件从 `is_staff` 改为 `is_full_admin()`（is_staff / is_superuser /
    role=ADMIN）—— 与项目其它处口径一致。**不给信息编辑员（EDITOR）**：
    帖子删除不在编辑员的能力矩阵里（编辑员通过审核/驳回、软删评论做内容处置）。
    """

    def has_object_permission(self, request, view, obj):
        # 只有作者或管理员可以删除
        is_owner = obj.author == request.user  # 当前用户是否为帖子作者
        return is_owner or is_full_admin(request.user)  # 满足任一条件即可