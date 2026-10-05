from rest_framework import permissions  # 导入Django REST Framework权限类
from .models_forum import ForumBoard, Post, Comment  # 导入论坛相关模型


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    管理员可写、任何人可读
    - 病害百科等公共资料：所有用户（含未登录）可查看
    - 新增/修改/删除仅限管理员（is_staff / is_superuser / role=ADMIN）
    """

    def has_permission(self, request, view):
        # 安全方法（GET/HEAD/OPTIONS）允许任何请求
        if request.method in permissions.SAFE_METHODS:
            return True

        user = request.user
        if not user or not user.is_authenticated:
            return False

        return bool(
            user.is_staff or
            user.is_superuser or
            getattr(user, 'role', None) == 'ADMIN'
        )


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
    """

    def has_object_permission(self, request, view, obj):
        # 只有作者或管理员可以删除
        is_owner = obj.author == request.user  # 当前用户是否为帖子作者
        is_admin = request.user.is_authenticated and request.user.is_staff  # 用户已认证且是管理员

        return is_owner or is_admin  # 满足任一条件即可