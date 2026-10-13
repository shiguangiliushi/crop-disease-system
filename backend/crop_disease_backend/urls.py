import os
import re
import sys
from pathlib import Path

# 设置项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

# 将项目根目录添加到 Python 路径
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')

import django
django.setup()

# 导入 Django 核心模块
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from django.views.static import serve as media_serve
from django.contrib.staticfiles.views import serve as static_serve

# 动态导入视图
import importlib

def import_view(module_path, class_name):
    module = importlib.import_module(module_path)
    return getattr(module, class_name)

# 导入视图
RegisterView = import_view('api.views', 'RegisterView')
LoginView = import_view('api.views', 'LoginView')
CheckAuthView = import_view('api.views', 'CheckAuthView')
LogoutView = import_view('api.views', 'LogoutView')
PestEncyclopediaViewSet = import_view('api.views', 'PestEncyclopediaViewSet')
PestDetailView = import_view('api.views', 'PestDetailView')
DetectView = import_view('api.views', 'DetectView')
PreventionDataView = import_view('api.views', 'PreventionDataView')
DetectionHistoryView = import_view('api.views', 'DetectionHistoryView')
DetectionHistoryDetailView = import_view('api.views', 'DetectionHistoryDetailView')
DetectionHistoryClearView = import_view('api.views', 'DetectionHistoryClearView')
ImageUploadView = import_view('api.views', 'ImageUploadView')
FeedbackView = import_view('api.views', 'FeedbackView')
StatisticsView = import_view('api.views', 'StatisticsView')
PestTypesView = import_view('api.views', 'PestTypesView')

# 从其他模块导入视图
UserProfileView = import_view('api.views_user', 'UserProfileView')
UserStatsView = import_view('api.views_user', 'UserStatsView')
UserPostsView = import_view('api.views_user', 'UserPostsView')
UserListView = import_view('api.views_user', 'UserListView')
# 第 76 批：管理端用户管理（用户管理页此前完全缺失）
AdminUserListView = import_view('api.views_user', 'AdminUserListView')
AdminUserDetailView = import_view('api.views_user', 'AdminUserDetailView')
# 第 120 批：管理员给用户签发一次性密码重置链接
AdminUserResetLinkView = import_view('api.views_user', 'AdminUserResetLinkView')
# 第 127 批：调整角色（仅超级管理员，且只能在 信息编辑员 ↔ 普通用户 之间调）
AdminUserRoleView = import_view('api.views_user', 'AdminUserRoleView')
# 第 131 批：开通编辑员账号（仅超管；无可用密码 + 一次性设置密码链接）
AdminUserCreateEditorView = import_view('api.views_user', 'AdminUserCreateEditorView')
# 第 137 批：停用 / 恢复账号（补上"有「已禁用」筛选却没有停用入口"的缺口）
AdminUserStatusView = import_view('api.views_user', 'AdminUserStatusView')
# 第 146 批：管理操作日志（只读，仅全权管理员）
AdminAuditLogListView = import_view('api.views_audit', 'AdminAuditLogListView')
AdminAuditLogActionsView = import_view('api.views_audit', 'AdminAuditLogActionsView')
# 第 157 批：系统健康（复用 check_env 的检查，仅全权管理员）
AdminHealthView = import_view('api.views_system_health', 'AdminHealthView')
# 第 179 批：权限矩阵（给"开通编辑员"对话框用，与自查命令同一份数据）
AdminRoleMatrixView = import_view('api.views_role_matrix', 'AdminRoleMatrixView')
# 第 149 批：控制台的评论管理（全局列表 + 软删/硬删/批量软删）
AdminCommentListView = import_view('api.views_comments_admin', 'AdminCommentListView')
AdminCommentSoftDeleteView = import_view('api.views_comments_admin', 'AdminCommentSoftDeleteView')
AdminCommentRestoreView = import_view('api.views_comments_admin', 'AdminCommentRestoreView')
AdminCommentHardDeleteView = import_view('api.views_comments_admin', 'AdminCommentHardDeleteView')
AdminCommentBulkDeleteView = import_view('api.views_comments_admin', 'AdminCommentBulkDeleteView')
# 第 172 批：控制台「识别记录」（跨用户看识别历史；删除仅全权管理员）
AdminDetectionListView = import_view('api.views_detections_admin', 'AdminDetectionListView')
AdminDetectionDeleteView = import_view('api.views_detections_admin', 'AdminDetectionDeleteView')
UserCommentsView = import_view('api.views_user', 'UserCommentsView')  # 第 25 批：用户的评论列表
# 第 23 批：用户资料完善（真实头像 + 修改密码）
UserAvatarView = import_view('api.views_user', 'UserAvatarView')
UserPasswordChangeView = import_view('api.views_user', 'UserPasswordChangeView')
# 第 95 批：自助注销账号
AccountDeleteView = import_view('api.views_user', 'AccountDeleteView')
# 第 101 批：冷静期内取消注销
AccountCancelDeletionView = import_view('api.views_user', 'AccountCancelDeletionView')
# 第 35 批：账号安全（用户名实时校验 / 找回密码）
UsernameAvailabilityView = import_view('api.views_user', 'UsernameAvailabilityView')
SiteConfigView = import_view('api.views_user', 'SiteConfigView')  # 第 38 批
SensitiveWordViewSet = import_view('api.views_sensitive', 'SensitiveWordViewSet')  # 第 38 批
AdminDashboardView = import_view('api.views_dashboard', 'AdminDashboardView')  # 第 39 批：数据看板
# 第 91 批：识别纠错样本的闭环度量（攒了多少可训练样本 / 误判率下钻到病害）
AdminFeedbackDatasetStatsView = import_view(
    'api.views_dashboard', 'AdminFeedbackDatasetStatsView'
)
# 第 40 批：关注 / 粉丝
FollowToggleView = import_view('api.views_social', 'FollowToggleView')
FollowListView = import_view('api.views_social', 'FollowListView')
MyFollowingStatsView = import_view('api.views_social', 'MyFollowingStatsView')
FollowSuggestionView = import_view('api.views_social', 'FollowSuggestionView')
UserSearchView = import_view('api.views_social', 'UserSearchView')  # 第 112 批：发起私信时搜人
# 第 41 批：举报
ReportViewSet = import_view('api.views_report', 'ReportViewSet')
ReportHandleView = import_view('api.views_report', 'ReportHandleView')
# 第 42 批：私信 + 等级积分
ConversationListView = import_view('api.views_message', 'ConversationListView')
ConversationDetailView = import_view('api.views_message', 'ConversationDetailView')
MessageUnreadCountView = import_view('api.views_message', 'MessageUnreadCountView')
MyPointsView = import_view('api.views_points', 'MyPointsView')
MyPointLogsView = import_view('api.views_points', 'MyPointLogsView')
PointLevelsView = import_view('api.views_points', 'PointLevelsView')
# 第 44 批：病害批量导入
PestImportView = import_view('api.views_pest_import', 'PestImportView')
PestImportTemplateView = import_view('api.views_pest_import', 'PestImportTemplateView')
# 第 46 批：病害预警
AlertListView = import_view('api.views_alert', 'AlertListView')
AlertNotifyView = import_view('api.views_alert', 'AlertNotifyView')
# 第 47 批：种植日历
CalendarView = import_view('api.views_calendar', 'CalendarView')
CalendarCropOptionsView = import_view('api.views_calendar', 'CalendarCropOptionsView')
CalendarTaskListView = import_view('api.views_calendar', 'CalendarTaskListView')
CalendarTaskDetailView = import_view('api.views_calendar', 'CalendarTaskDetailView')
# 第 49 批：专家咨询
QuestionListView = import_view('api.views_expert', 'QuestionListView')
QuestionDetailView = import_view('api.views_expert', 'QuestionDetailView')
AnswerCreateView = import_view('api.views_expert', 'AnswerCreateView')
AnswerAcceptView = import_view('api.views_expert', 'AnswerAcceptView')
ExpertListView = import_view('api.views_expert', 'ExpertListView')
# 第 50 批：离线资料包
PestOfflinePackView = import_view('api.views_offline', 'PestOfflinePackView')
PasswordResetRequestView = import_view('api.views_user', 'PasswordResetRequestView')
PasswordResetConfirmView = import_view('api.views_user', 'PasswordResetConfirmView')
# 第 37 批：通知与公告
NotificationViewSet = import_view('api.views_notify', 'NotificationViewSet')
AnnouncementViewSet = import_view('api.views_notify', 'AnnouncementViewSet')
AnnouncementLatestView = import_view('api.views_notify', 'AnnouncementLatestView')

NewsViewSet = import_view('api.news_views', 'NewsViewSet')

# 论坛相关视图
ForumBoardViewSet = import_view('api.views_forum', 'ForumBoardViewSet')
PostViewSet = import_view('api.views_forum', 'PostViewSet')
CommentViewSet = import_view('api.views_forum', 'CommentViewSet')
LikeViewSet = import_view('api.views_forum', 'LikeViewSet')
# 第 94 批：健康检查（匿名可访问，探针用）
HealthView = import_view('api.views_health', 'HealthView')

# 创建主路由器
router = DefaultRouter(trailing_slash=True)  # 确保使用斜杠结尾
# 注册NewsViewSet
router.register(r'news', NewsViewSet, basename='news')

# 创建论坛子应用路由器
forum_router = DefaultRouter()
forum_router.register(r'boards', ForumBoardViewSet, basename='forum-board')
forum_router.register(r'posts', PostViewSet, basename='post')
forum_router.register(r'likes', LikeViewSet, basename='like')

# 嵌套路由 - 帖子的评论
posts_router = DefaultRouter()
posts_router.register(r'comments', CommentViewSet, basename='post-comment')

# API URL 配置
api_urlpatterns = [
    # 包含news路由
    path('', include(router.urls)),

    # 健康检查（第 94 批）：**匿名可访问**，负载均衡/监控探针用。
    #   /api/health/             轻量（进程 + 数据库 + 缓存）
    #   /api/health/?deep=true   额外查迁移状态与模型文件
    # 放在最前面：探针不该被任何鉴权/路由细节影响。
    path('health/', HealthView.as_view(), name='health'),
    
    # 反馈相关
    path('feedback/', FeedbackView.as_view({'get': 'list', 'post': 'create'}), name='feedback-list'),
    # 第 100 批：批量流转处理状态（仅管理员）。
    # ⚠️ 同 `reply` 一样，FeedbackView 是**显式 as_view 映射**注册的，
    #    `@action` 不会自动生成路由 —— 必须在这里手写一条，否则 404。
    path('feedback/bulk-status/', FeedbackView.as_view({'post': 'bulk_status'}),
         name='feedback-bulk-status'),
    # 第 138 批：批量删除（**仅全权管理员** —— 不可逆操作，不给内容编辑员）。
    # 同 bulk-status：FeedbackView 是显式 as_view 映射，`@action` 不会自动生成路由。
    path('feedback/bulk-delete/', FeedbackView.as_view({'post': 'bulk_delete'}),
         name='feedback-bulk-delete'),
    path('feedback/<int:pk>/', FeedbackView.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='feedback-detail'),
    # 第 27 批：管理端回复 / 流转处理状态。
    # ⚠️ FeedbackView 是用 as_view({...}) **显式映射**注册的（不是 router.register），
    # 所以 @action 装饰器不会自动生成路由，必须在这里手写一条，否则 /reply/ 会 404。
    path('feedback/<int:pk>/reply/', FeedbackView.as_view({'post': 'reply'}), name='feedback-reply'),
    
    # 认证相关
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('check-auth/', CheckAuthView.as_view(), name='check-auth'),
    # 第 91 批（安全）：这里原本还挂着 DRF 自带的
    #     path('token-auth/', obtain_auth_token, name='api_token_auth')
    # 它与 /api/login/ 功能重叠（返回同一张 Token），但**完全绕过登录防护**：
    #   · DRF 的 ObtainAuthToken 源码里 `throttle_classes = ()` —— 不限流；
    #   · 失败计数与账号锁定只写在 LoginView.post 里 —— 它也不走。
    # 于是"5 次失败锁 15 分钟 + 10/min 限流"形同虚设：改打这个端点就能无限撞库。
    # 全仓（桌面端 frontend/、移动端 mobile/）均无任何调用（grep `token-auth` 只命中本文件），
    # 所以直接摘掉路由 —— 现在访问它返回 404，与"从未存在"一致。
    # 将来若确实需要 Token 认证入口，请复用 /api/login/，不要把这一行加回来。

    # 账号安全（第 35 批）
    # 说明：`users/check-username/` 必须放在 `users/<int:user_id>/` **之前**，
    # 否则 "check-username" 会被当成 user_id 去匹配（那是 int 转换器，匹配不上会 404）。
    path('users/check-username/', UsernameAvailabilityView.as_view(), name='username-availability'),
    # 第 95 批：注销自己的账号（同样必须在 users/<int:user_id>/ 之前 ——
    # "me" 不是 int，虽然匹配不上会落到下面的 int 规则、但保持同一约定更安全）
    path('users/me/delete/', AccountDeleteView.as_view(), name='account-delete'),
    # 第 101 批：冷静期内取消注销。**允许匿名**（账号已停用、登不上，靠用户名+密码认身份），
    # 详见 AccountCancelDeletionView 的说明。
    path('users/me/cancel-deletion/', AccountCancelDeletionView.as_view(),
         name='account-cancel-deletion'),
    # 关注 / 粉丝（第 40 批）
    path('users/me/following/', FollowListView.as_view(), {'direction': 'following'}, name='my-following'),
    path('users/me/follow-stats/', MyFollowingStatsView.as_view(), name='my-follow-stats'),
    path('users/follow-suggestions/', FollowSuggestionView.as_view(), name='follow-suggestions'),
    # 第 112 批：按用户名搜索用户 —— 给"发起新私信"用。
    # 必须放在 `users/<int:user_id>/` **之前**（同 check-username 那条的理由：
    # "search" 不是 int，匹配不上 int 规则会 404）。
    path('users/search/', UserSearchView.as_view(), name='user-search'),
    path('site-config/', SiteConfigView.as_view(), name='site-config'),  # 第 38 批：发帖审核开关

    # 敏感词词库（第 38 批，仅管理员）
    path('sensitive-words/', SensitiveWordViewSet.as_view({
        'get': 'list', 'post': 'create',
    }), name='sensitive-word-list'),
    path('sensitive-words/<int:pk>/', SensitiveWordViewSet.as_view({
        'delete': 'destroy', 'patch': 'partial_update',
    }), name='sensitive-word-detail'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),

    # 通知与公告（第 37 批）
    path('notifications/', NotificationViewSet.as_view({'get': 'list'}), name='notification-list'),
    path('notifications/unread-count/', NotificationViewSet.as_view({'get': 'unread_count'}),
         name='notification-unread-count'),
    path('notifications/read-all/', NotificationViewSet.as_view({'post': 'read_all'}),
         name='notification-read-all'),
    path('notifications/<int:pk>/read/', NotificationViewSet.as_view({'post': 'read'}),
         name='notification-read'),
    path('notifications/<int:pk>/', NotificationViewSet.as_view({'delete': 'destroy'}),
         name='notification-detail'),
    # 注意：latest 必须在 <int:pk>/ 之前（这里用 int 转换器，顺序其实无所谓，但保持一致更安全）
    path('announcements/latest/', AnnouncementLatestView.as_view(), name='announcement-latest'),
    path('announcements/', AnnouncementViewSet.as_view({
        'get': 'list', 'post': 'create',
    }), name='announcement-list'),
    path('announcements/<int:pk>/', AnnouncementViewSet.as_view({
        'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy',
    }), name='announcement-detail'),

    # 病害百科
    path('pests/', PestEncyclopediaViewSet.as_view({'get': 'list', 'post': 'create'}), name='pest-list'),
    # 最近添加的病害：必须放在 pests/<str:english_identifier>/ 之前，否则会被当作标识符匹配
    path('pests/recent/', PestEncyclopediaViewSet.as_view({'get': 'recent'}), name='recent-pests'),

    # 病害批量导入（第 44 批）—— 同样必须在 pests/<str:english_identifier>/ 之前
    path('pests/import-template/', PestImportTemplateView.as_view(), name='pest-import-template'),
    path('pests/import/', PestImportView.as_view(), name='pest-import'),
    # 第 50 批：离线资料包（断网时可查阅百科）
    path('pests/offline-pack/', PestOfflinePackView.as_view(), name='pest-offline-pack'),
    # 按主键查看 / 修改 / 删除（读取公开，写入仅管理员）—— 同样必须放在标识符路由之前
    path('pests/<int:pk>/', PestEncyclopediaViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy',
    }), name='pest-detail-by-id'),
    path('pests/<str:english_identifier>/', PestDetailView.as_view(), name='pest-detail'),
    
    # 检测相关
    path('detect/', DetectView.as_view(), name='detect'),
    path('preventions/', PreventionDataView.as_view(), name='preventions-data'),
    path('pest-types/', PestTypesView.as_view(), name='pest-types'),
    
    # 检测历史
    path('detection-history/', DetectionHistoryView.as_view(), name='detection-history-list'),
    # 第 43 批：导出 Excel（必须放在 <int:pk>/ 之前，否则会被当成 pk 匹配）
    path('detection-history/export-excel/', DetectionHistoryView.as_view(http_method_names=['get']),
         name='detection-history-export-excel'),
    # 清空记录：必须放在 <int:pk> 之前（clear-all 不是整数，放在前面更直观）
    path('detection-history/clear-all/', DetectionHistoryClearView.as_view(), name='detection-history-clear-all'),
    path('detection-history/<int:pk>/', DetectionHistoryDetailView.as_view(), name='detection-history-detail'),

    # 通用图片上传（论坛发帖/编辑器插图）
    path('upload/image/', ImageUploadView.as_view(), name='image-upload'),
    
    # 统计
    path('statistics/', StatisticsView.as_view(), name='statistics'),
    
    # 用户相关
    path('users/', UserListView.as_view(), name='user-list'),
    path('users/<int:user_id>/', UserProfileView.as_view(), name='user-profile'),
    path('users/<int:user_id>/stats/', UserStatsView.as_view(), name='user-stats'),
    path('users/me/posts/', UserPostsView.as_view(), name='user-posts'),
    # 第 25 批：某个用户发表的评论（资料页「评论」标签，带"发在哪个帖子/版块"）
    path('users/<int:user_id>/comments/', UserCommentsView.as_view(), name='user-comments'),
    # 第 23 批：头像上传/删除、修改密码（注意要放在 users/<int:user_id>/ 之后，
    # 且路径段不与上面冲突）
    path('users/<int:user_id>/avatar/', UserAvatarView.as_view(), name='user-avatar'),
    path('users/<int:user_id>/password/', UserPasswordChangeView.as_view(), name='user-password-change'),
    # 第 40 批：关注 / 粉丝（放在 users/<int:user_id>/ 之后，路径段不冲突）
    path('users/<int:user_id>/follow/', FollowToggleView.as_view(), name='user-follow'),
    path('users/<int:user_id>/followers/', FollowListView.as_view(), {'direction': 'followers'},
         name='user-followers'),
    path('users/<int:user_id>/following/', FollowListView.as_view(), {'direction': 'following'},
         name='user-following'),
    
    # 论坛相关
    path('forums/', include(forum_router.urls)),
    # ⚠️ 第 100 批踩到的坑：`bulk-review` 是 `PostViewSet` 的 `detail=False` 动作，
    # router 把它注册在 **`forums/posts/bulk-review/`**（forum_router 里）。
    # 但下面那行嵌套路由 `forums/posts/<int:post_pk>/` 用的是 posts_router，
    # 它**只注册了 comments** —— `forums/posts/bulk-review/` 会先被它匹配掉，
    # 然后因为该 router 下没有 bulk-review 这个子路径而返回 **405「方法 POST 不被允许」**
    # （实测：`resolve()` 明明指向 PostViewSet，请求却是 405）。
    # 修法与下面 `hot/` 一致：**显式列在嵌套 include 之前**。
    path('forums/posts/bulk-review/', PostViewSet.as_view({'post': 'bulk_review'}),
         name='post-bulk-review'),
    path('forums/posts/<int:post_pk>/', include(posts_router.urls)),
    path('forums/posts/hot/', PostViewSet.as_view({'get': 'hot_posts'}), name='hot-posts'),

    # 管理员数据看板（第 39 批）
    path('admin/dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    # 第 91 批：识别纠错样本统计（攒了多少可用样本 / 哪类病害总被认错）
    path('admin/dataset-stats/', AdminFeedbackDatasetStatsView.as_view(), name='admin-dataset-stats'),

    # 管理端用户管理（第 76 批，仅管理员）
    path('admin/users/', AdminUserListView.as_view(), name='admin-user-list'),
    # 第 100 批：批量删除用户。**必须放在 `<int:user_id>/` 之前**（约定同其它路由）：
    # 虽然 "bulk-delete" 不是 int、匹配不上那条规则，但顺序一致更不容易出错。
    # 处理函数在 AdminUserListView.post 里按路径分流（见那里的说明）。
    path('admin/users/bulk-delete/', AdminUserListView.as_view(), name='admin-user-bulk-delete'),
    # 第 131 批：开通编辑员账号（仅超管；账号无可用密码，返回一次性设置密码链接）。
    # ⚠️ 必须放在 `<int:user_id>/` 之前 —— 虽然 "create-editor" 不是 int、匹配不上，
    #    但顺序一致更不容易出错（同 bulk-delete 的约定）。
    # 第 149 批：控制台的评论管理
    # ⚠️ `bulk-delete/` 必须放在 `<int:pk>/` 之前 —— 否则 'bulk-delete' 会被
    #    当成 pk 去匹配（int 转换失败 → 404，而不是走批量那条）。
    path('admin/comments/', AdminCommentListView.as_view(), name='admin-comments'),
    path('admin/comments/bulk-delete/', AdminCommentBulkDeleteView.as_view(),
         name='admin-comments-bulk-delete'),
    path('admin/comments/<int:pk>/restore/',
         AdminCommentRestoreView.as_view(), name='admin-comment-restore'),
    path('admin/comments/<int:pk>/soft-delete/',
         AdminCommentSoftDeleteView.as_view(), name='admin-comment-soft-delete'),
    path('admin/comments/<int:pk>/', AdminCommentHardDeleteView.as_view(),
         name='admin-comment-hard-delete'),
    # 第 146 批：管理操作日志（只读，仅全权管理员）
    # 第 157 批：系统健康（与操作日志同档：会暴露部署细节，仅全权管理员）
    path('admin/health/', AdminHealthView.as_view(), name='admin-health'),
    path('admin/role-matrix/', AdminRoleMatrixView.as_view(), name='admin-role-matrix'),
    # 第 172 批：控制台「识别记录」—— 跨用户看识别历史（USER_ADMIN 能力；
    # 删除不可逆，仅全权管理员）。注意路径与农户端的 `history/` 不是一回事：
    # 那边只看自己的记录。
    path('admin/detections/', AdminDetectionListView.as_view(), name='admin-detections'),
    path('admin/detections/<int:pk>/', AdminDetectionDeleteView.as_view(),
         name='admin-detection-delete'),
    path('admin/audit-logs/', AdminAuditLogListView.as_view(), name='admin-audit-logs'),
    path('admin/audit-logs/actions/', AdminAuditLogActionsView.as_view(),
         name='admin-audit-log-actions'),
    path('admin/users/create-editor/', AdminUserCreateEditorView.as_view(),
         name='admin-user-create-editor'),
    # 第 120 批：给某个用户签发一次性密码重置链接（管理员）。
    # 解决"账号没绑邮箱 → 自助找回密码静默失败 → 管理员忘了密码无路可走"。
    path('admin/users/<int:user_id>/reset-link/', AdminUserResetLinkView.as_view(),
         name='admin-user-reset-link'),
    # 第 127 批：调整角色（仅超级管理员，且只能在 信息编辑员 ↔ 普通用户 之间调）
    path('admin/users/<int:user_id>/role/', AdminUserRoleView.as_view(), name='admin-user-role'),
    # 第 137 批：停用 / 恢复账号。权限与删除一致（USER_ADMIN + 不能停用自己 /
    # 权限不低于自己的人）；停用时会作废对方的 token，恢复后需重新登录。
    path('admin/users/<int:user_id>/status/', AdminUserStatusView.as_view(),
         name='admin-user-status'),
    path('admin/users/<int:user_id>/', AdminUserDetailView.as_view(), name='admin-user-detail'),

    # 举报（第 41 批）
    path('reports/', ReportViewSet.as_view(), name='report-list'),
    path('reports/<int:pk>/handle/', ReportHandleView.as_view(), name='report-handle'),

    # 私信（第 42 批）
    path('messages/', ConversationListView.as_view(), name='conversation-list'),
    path('messages/unread-count/', MessageUnreadCountView.as_view(), name='message-unread-count'),
    path('messages/with/<int:user_id>/', ConversationDetailView.as_view(), name='conversation-detail'),

    # 等级与积分（第 42 批）
    path('points/levels/', PointLevelsView.as_view(), name='point-levels'),
    path('users/me/points/', MyPointsView.as_view(), name='my-points'),
    path('users/me/point-logs/', MyPointLogsView.as_view(), name='my-point-logs'),

    # 病害批量导入（第 44 批）—— 路由已上移到 pests/<str:english_identifier>/ 之前

    # 病害预警（第 46 批）
    path('alerts/', AlertListView.as_view(), name='alert-list'),
    path('alerts/notify/', AlertNotifyView.as_view(), name='alert-notify'),

    # 种植日历（第 47 批）
    path('calendar/', CalendarView.as_view(), name='calendar'),
    path('calendar/crops/', CalendarCropOptionsView.as_view(), name='calendar-crops'),
    path('calendar/tasks/', CalendarTaskListView.as_view(), name='calendar-task-list'),
    path('calendar/tasks/<int:pk>/', CalendarTaskDetailView.as_view(), name='calendar-task-detail'),

    # 专家咨询（第 49 批）
    path('consult/questions/', QuestionListView.as_view(), name='consult-question-list'),
    path('consult/questions/<int:pk>/', QuestionDetailView.as_view(), name='consult-question-detail'),
    path('consult/questions/<int:pk>/answers/', AnswerCreateView.as_view(), name='consult-answer-create'),
    path('consult/answers/<int:pk>/accept/', AnswerAcceptView.as_view(), name='consult-answer-accept'),
    path('consult/experts/', ExpertListView.as_view(), name='consult-expert-list'),
    path('consult/experts/<int:user_id>/', ExpertListView.as_view(), name='consult-expert-detail'),

    # 路由已由 router.urls 处理
]

# 主URL配置
urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(api_urlpatterns)),
    # 添加对favicon.ico的访问支持
    re_path(r'^favicon\.ico$', static_serve, {'path': 'favicon.ico', 'document_root': settings.STATIC_ROOT}),
]

# 静态文件与媒体文件（第 94 批：生产也能托管媒体了）
# ----------------------------------------------------------------------------
# 改前这里只有 `if settings.DEBUG:` 一行 —— 于是**生产模式下 /media/ 全部 404**：
# 头像、帖子配图、病害图、识别原图都打不开（前端表现为"图片是碎的"），
# 而这类问题在开发机上永远不会出现。
#
# ⚠️ 一个必须知道的坑：**不要用 `django.conf.urls.static.static()` 挂生产路由**。
# 它的源码里写着 `elif not settings.DEBUG: return []` —— 在 DEBUG=False 下它是**静默空操作**，
# 你会以为配好了、实际什么也没挂上（本批就是这么踩了一次）。
# 这里直接用 `re_path` + `django.views.static.serve`：那个视图本身有 `safe_join` 做
# 路径越界检查，也不带 DEBUG 判断，生产可用。
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(
            r'^%s(?P<path>.*)$' % re.escape(settings.MEDIA_URL.lstrip('/')),
            media_serve,          # django.views.static.serve（文件顶部已导入）
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]