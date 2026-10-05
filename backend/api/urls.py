"""
注意：本文件当前**没有被 ROOT_URLCONF 使用**。

项目实际生效的路由配置是 `crop_disease_backend/urls.py`
（settings.py 中 ROOT_URLCONF = 'crop_disease_backend.urls'，其内部的
api_urlpatterns 才是真正注册到 /api/ 下的路由）。

保留本文件仅为历史兼容与参考：新增/修改接口时请改
`crop_disease_backend/urls.py`，否则不会生效。两份文件的接口列表已尽量保持一致。

之所以不直接删除，是因为项目没有可用的版本控制（.git 已损坏），
删除不可回滚；确认无用后再清理。
"""

from django.urls import path, include  # 导入Django的URL路由和包含功能
from rest_framework.routers import DefaultRouter  # 导入DRF的默认路由器
from .views import (  # 从当前应用的views模块导入视图类
    RegisterView, LoginView, CheckAuthView, LogoutView,
    PestEncyclopediaViewSet, PestDetailView, DetectView,
    PreventionDataView, DetectionHistoryView, DetectionHistoryDetailView, PestTypesView,
    FeedbackView, StatisticsView, DetectionReportView
)
from .news_views import NewsViewSet  # 导入新的NewsViewSet
from .views_user import UserProfileView, UserStatsView, UserPostsView, UserListView  # 从用户视图模块导入用户相关视图
from .views_user import UserAvatarView, UserPasswordChangeView  # 第23批：头像 / 修改密码
from .views_user import UserCommentsView  # 第25批：用户的评论列表
from .views_forum import ForumBoardViewSet, PostViewSet, CommentViewSet, \
    LikeViewSet  # 从论坛视图模块导入论坛相关视图  # , FavoriteViewSet

# 创建主路由器
router = DefaultRouter()  # 实例化默认路由器
router.register(r'feedback', FeedbackView, basename='feedback')  # 注册反馈API端点
router.register(r'news', NewsViewSet, basename='news')  # 注册新闻API端点
# 注意：我们暂时不注册pests到router，以避免URL冲突
# router.register(r'pests', PestEncyclopediaViewSet, basename='pest-encyclopedia')  # 注册病害百科API端点

# 创建论坛子应用路由器
forum_router = DefaultRouter()  # 实例化论坛专用路由器
forum_router.register(r'boards', ForumBoardViewSet, basename='forum-board')  # 注册论坛版块API端点
forum_router.register(r'posts', PostViewSet, basename='post')  # 注册帖子API端点
forum_router.register(r'likes', LikeViewSet, basename='like')  # 注册点赞API端点
# forum_router.register(r'favorites', FavoriteViewSet, basename='favorite')  # 注册收藏API端点（已注释）

# 嵌套路由 - 帖子的评论
posts_router = DefaultRouter()  # 实例化帖子评论专用路由器
posts_router.register(r'comments', CommentViewSet, basename='post-comment')  # 注册评论API端点

# 主URL模式
urlpatterns = [
    # 包含路由器中的URL
    path('', include(router.urls)),  # 包含主路由器的所有URL

    # Auth 认证相关路由
    path('register/', RegisterView.as_view(), name='register'),  # 用户注册端点
    path('login/', LoginView.as_view(), name='login'),  # 用户登录端点
    path('logout/', LogoutView.as_view(), name='logout'),  # 用户登出端点
    path('check-auth/', CheckAuthView.as_view(), name='check-auth'),  # 检查认证状态端点

    # 病害百科相关路由
    # 获取所有病害类型
    path('pest-types/', PestTypesView.as_view(), name='pest-types'),
    # 病害列表和创建
    path('pests/', PestEncyclopediaViewSet.as_view({'get': 'list', 'post': 'create'}), name='pest-list'),

    # 最近添加的病害（放在标识符路由之前）
    path('pests/recent/', PestEncyclopediaViewSet.as_view({'get': 'recent'}), name='recent-pests'),

    # 按主键查看 / 修改 / 删除（读取公开，写入仅管理员）—— 必须放在按标识符匹配之前
    path('pests/<int:pk>/', PestEncyclopediaViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy',
    }), name='pest-detail-by-id'),

    # 病害详情端点 - 通过英文标识符获取病害详情
    path('pests/<str:english_identifier>/', PestDetailView.as_view(), name='pest-detail'),
    
    # 其他病害相关端点
    path('pests/old/', PestEncyclopediaViewSet.as_view({'get': 'list'}), name='pest-encyclopedia-old'),  # 旧版端点
    path('pests/recent/', PestEncyclopediaViewSet.as_view({'get': 'recent'}), name='recent-pests'),  # 最近添加的病害
    
    # 其他功能端点
    path('detect/', DetectView.as_view(), name='detect'),  # 害虫检测端点
    path('preventions/', PreventionDataView.as_view(), name='preventions-data'),  # 预防措施数据
    
    # 检测历史记录相关路由
    path('detection-history/', DetectionHistoryView.as_view(), name='detection-history'),  # 检测历史列表
    path('detection-history/<int:pk>/', DetectionHistoryDetailView.as_view(), name='detection-history-detail'),  # 检测历史详情
    path('detection-history/<int:pk>/report/', DetectionReportView.as_view(), name='detection-report'),  # 检测报告下载
    
    # 害虫类型和统计信息
    path('pest-types/', PestTypesView.as_view(), name='pest-types'),  # 害虫类型列表端点
    path('statistics/', StatisticsView.as_view(), name='statistics'),  # 统计信息端点
    path('api/statistics/', StatisticsView.as_view(), name='api-statistics'),  # 兼容前端的统计信息端点

    # 新闻API
    path('news/', NewsViewSet.as_view({'get': 'list', 'post': 'create'}), name='news-list'),  # 新闻列表和创建
    path('news/<int:pk>/', NewsViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='news-detail'),  # 新闻详情、更新、删除
    path('news/latest/', NewsViewSet.as_view({'get': 'list'}), name='latest-news'),  # 最新新闻列表端点

    # 用户相关路由
    path('users/', UserListView.as_view(), name='user-list'),  # 用户列表端点
    path('users/<int:user_id>/', UserProfileView.as_view(), name='user-profile'),  # 用户资料端点
    path('users/<int:user_id>/stats/', UserStatsView.as_view(), name='user-stats'),  # 用户统计信息端点
    path('users/me/posts/', UserPostsView.as_view(), name='user-posts'),  # 用户帖子端点统计信息端点
    # 第 25 批：用户评论列表（与 crop_disease_backend/urls.py 保持一致）
    path('users/<int:user_id>/comments/', UserCommentsView.as_view(), name='user-comments'),
    # 第 23 批：头像上传/删除、修改密码（与 crop_disease_backend/urls.py 保持一致）
    path('users/<int:user_id>/avatar/', UserAvatarView.as_view(), name='user-avatar'),
    path('users/<int:user_id>/password/', UserPasswordChangeView.as_view(), name='user-password-change'),

    # 论坛相关路由
    path('forums/', include(forum_router.urls)),  # 包含论坛路由器的所有URL
    # 帖子评论路由
    path('forums/posts/<int:post_pk>/', include(posts_router.urls)),  # 包含帖子评论路由器的所有URL
    path('forums/posts/hot/', PostViewSet.as_view({'get': 'hot_posts'}), name='hot-posts'),
    
    # 统计数据已在上方定义，无需重复
]