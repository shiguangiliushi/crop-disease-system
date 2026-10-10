from django.contrib import admin  # 导入Django管理后台模块
from django.contrib.auth.admin import UserAdmin  # 导入用户管理类
from django.utils.html import format_html  # 导入HTML格式化工具
from .models import CustomUser, PestInfo, PreventionMethod, DetectionHistory, Feedback, News  # 导入模型
from .models_audit import AdminAuditLog  # 第 146 批：管理操作日志（只读注册）
from .models_forum import ForumBoard, Post, Comment, Like  # 导入论坛模型
from .models_notify import Announcement, Notification  # 第 37 批：通知与公告
# 第 49 批：专家咨询（管理员也可以在 Django 后台授予专家、审阅问答）
from .models_expert import ConsultAnswer, ConsultQuestion, ExpertProfile


@admin.register(CustomUser)  # 注册自定义用户模型到管理后台
class CustomUserAdmin(UserAdmin):  # 自定义用户管理类
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff')  # 列表显示字段
    search_fields = ('username', 'email')  # 搜索字段


@admin.register(PestInfo)  # 注册病害信息模型到管理后台
class PestInfoAdmin(admin.ModelAdmin):  # 病害信息管理类
    # 第 69 批：把英文字段也放进后台，管理员可直接校正机器生成的英文名
    list_display = ('name', 'name_en', 'crop_type', 'crop_type_en', 'english_identifier')  # 列表显示字段
    search_fields = ('name', 'name_en', 'crop_type', 'crop_type_en', 'english_identifier')  # 搜索字段
    list_filter = ('crop_type',)  # 过滤器字段
    fieldsets = (
        (None, {
            'fields': ('name', 'name_en', 'crop_type', 'crop_type_en', 'english_identifier', 'image'),
        }),
        ('正文', {
            'fields': ('symptoms', 'description'),
        }),
    )


@admin.register(PreventionMethod)  # 注册防治方法模型到管理后台
class PreventionMethodAdmin(admin.ModelAdmin):  # 防治方法管理类
    list_display = ('pest', 'get_category_display')  # 列表显示字段
    search_fields = ('pest__name',)  # 搜索字段
    list_filter = ('category', 'pest__crop_type')  # 过滤器字段

    def get_category_display(self, obj):  # 定义获取类别显示名称方法
        return obj.get_category_display()  # 返回类别显示名称

    get_category_display.short_description = 'Category'  # 设置字段显示名称


@admin.register(DetectionHistory)  # 注册检测历史模型到管理后台
class DetectionHistoryAdmin(admin.ModelAdmin):  # 检测历史管理类
    list_display = ('user', 'detection_result', 'timestamp')  # 列表显示字段
    search_fields = ('user__username', 'detection_result')  # 搜索字段
    list_filter = ('timestamp',)  # 过滤器字段


@admin.register(Feedback)  # 注册用户反馈模型到管理后台
class FeedbackAdmin(admin.ModelAdmin):  # 用户反馈管理类
    # 第 26 批：反馈扩展为通用「意见反馈」后，后台要能一眼看到类型/状态并直接流转
    list_display = ('user', 'category', 'status', 'image_preview', 'disease_name',
                    'is_correct', 'timestamp', 'handled_at')  # 列表显示字段
    search_fields = ('user__username', 'disease_name', 'suggestion', 'admin_reply')  # 搜索字段
    list_filter = ('category', 'status', 'is_correct', 'timestamp')  # 过滤器字段
    list_editable = ('status',)  # 可直接在列表里改处理状态
    readonly_fields = ('image_preview', 'timestamp')  # 只读字段
    fieldsets = (  # 编辑页分区：先看内容，再写回复
        ('反馈内容', {
            'fields': ('user', 'category', 'suggestion', 'image', 'image_preview', 'timestamp'),
        }),
        ('识别结果（仅识别结果反馈有值）', {
            'fields': ('disease_name', 'confidence', 'is_correct'),
            'classes': ('collapse',),
        }),
        # 第 91 批：纠错样本的闭环 —— 关联识别记录 + 纠正类别 + 确认状态
        ('训练样本（识别纠错专用）', {
            'fields': ('detection', 'corrected_pest', 'verify_status', 'exported_at'),
            'description': '用户点「识别不正确」并选择了正确病害的记录，确认后才会计入'
                           '导出数据集（python manage.py export_feedback_dataset）。',
            'classes': ('collapse',),
        }),
        ('处理', {
            'fields': ('status', 'admin_reply', 'handled_at'),
        }),
    )

    # 第 91 批：批量确认/排除样本 —— 一条条点开改太慢，这里给两个动作
    actions = ('confirm_samples', 'reject_samples')

    @admin.action(description='✔ 确认为训练样本（可导出）')
    def confirm_samples(self, request, queryset):
        updated = queryset.update(verify_status='confirmed')
        self.message_user(request, f'已确认 {updated} 条样本')

    @admin.action(description='✘ 排除（不进训练集）')
    def reject_samples(self, request, queryset):
        updated = queryset.update(verify_status='rejected')
        self.message_user(request, f'已排除 {updated} 条样本')

    def image_preview(self, obj):  # 定义图片预览方法
        if obj.image:  # 检查图片是否存在
            return format_html('<a href="{}" target="_blank"><img src="{}" width="100" /></a>', obj.image.url,
                               obj.image.url)  # 返回图片HTML
        return "(无图片)"  # 返回无图片提示

    image_preview.short_description = '图片预览'  # 设置字段显示名称


@admin.register(News)  # 注册新闻模型到管理后台
class NewsAdmin(admin.ModelAdmin):  # 新闻管理类
    list_display = ('title', 'source', 'author', 'created_at', 'is_published')  # 列表显示字段
    search_fields = ('title', 'content', 'author__username')  # 搜索字段
    list_filter = ('is_published', 'created_at')  # 过滤器字段


# 论坛相关模型注册
@admin.register(ForumBoard)  # 注册论坛版块模型到管理后台
class ForumBoardAdmin(admin.ModelAdmin):  # 论坛版块管理类
    list_display = ('name', 'description', 'order', 'is_active')  # 列表显示字段
    search_fields = ('name', 'description')  # 搜索字段
    list_filter = ('is_active',)  # 过滤器字段
    ordering = ('order',)  # 排序字段


@admin.register(Post)  # 注册帖子模型到管理后台
class PostAdmin(admin.ModelAdmin):  # 帖子管理类
    list_display = ('title', 'author', 'board', 'status', 'view_count', 'created_at')  # 列表显示字段
    search_fields = ('title', 'content', 'title_en', 'content_en', 'author__username')  # 搜索字段
    list_filter = ('status', 'is_pinned', 'is_essence', 'board')  # 过滤器字段
    date_hierarchy = 'created_at'  # 日期层次导航
    # 第 85 批：译文相关字段单独成组，方便管理员手工修订机器译文
    # （translation_hash / translated_at 是给程序判断"是否过期"用的，只读）
    fieldsets = (
        (None, {'fields': ('title', 'content', 'author', 'board', 'status')}),
        ('英文译文（第 85 批）', {
            'fields': ('title_en', 'content_en', 'translation_source', 'translated_at', 'translation_hash'),
            'description': (
                '留空表示"没有译文"，英文界面会显示中文原文并允许读者点「立即翻译」。'
                '这里手工填写的英文会被记为"人工翻译"，自动翻译不会覆盖它'
                '（除非执行 manage.py translate_forum_content --force）。'
            ),
        }),
        ('其它', {'fields': ('view_count', 'like_count', 'comment_count', 'is_pinned',
                            'is_essence', 'last_comment_at')}),
    )
    readonly_fields = ('translated_at', 'translation_hash')


@admin.register(Comment)  # 注册评论模型到管理后台
class CommentAdmin(admin.ModelAdmin):  # 评论管理类
    list_display = ('content_preview', 'author', 'post', 'created_at')  # 列表显示字段
    search_fields = ('content', 'content_en', 'author__username', 'post__title')  # 搜索字段
    list_filter = ('is_deleted', 'created_at')  # 过滤器字段
    # 第 85 批：同 PostAdmin，管理员可在这里修订评论译文
    fieldsets = (
        (None, {'fields': ('content', 'content_en', 'author', 'post', 'parent', 'reply_to_user')}),
        ('译文状态（第 85 批）', {
            'fields': ('translation_source', 'translated_at', 'translation_hash'),
            'description': '手工填写的英文会被记为"人工翻译"，自动翻译不会再覆盖它。',
        }),
        ('其它', {'fields': ('is_deleted', 'like_count')}),
    )
    readonly_fields = ('translated_at', 'translation_hash')

    def content_preview(self, obj):  # 定义内容预览方法
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content  # 返回内容预览

    content_preview.short_description = '评论内容'  # 设置字段显示名称


@admin.register(Like)  # 注册点赞模型到管理后台
class LikeAdmin(admin.ModelAdmin):  # 点赞管理类
    list_display = ('user', 'get_content_type', 'get_content_object', 'created_at')  # 列表显示字段
    list_filter = ('created_at',)  # 过滤器字段
    search_fields = ('user__username', 'post__title', 'comment__content')  # 搜索字段
    readonly_fields = ('created_at', 'get_content_type', 'get_content_object')  # 只读字段
    date_hierarchy = 'created_at'  # 日期层次导航

    def get_content_type(self, obj):  # 定义获取内容类型方法
        if obj.post:  # 检查是否为帖子点赞
            return '帖子'  # 返回帖子类型
        elif obj.comment:  # 检查是否为评论点赞
            return '评论'  # 返回评论类型
        return '未知'  # 返回未知类型

    def get_content_object(self, obj):  # 定义获取内容对象方法
        if obj.post:  # 检查是否为帖子点赞
            return obj.post.title  # 返回帖子标题
        elif obj.comment:  # 检查是否为评论点赞
            return obj.comment.content[:50] + '...' if len(
                obj.comment.content) > 50 else obj.comment.content  # 返回评论内容预览
        return '未知'  # 返回未知对象

    get_content_type.short_description = '点赞类型'  # 设置字段显示名称
    get_content_object.short_description = '点赞对象'  # 设置字段显示名称

    fieldsets = (  # 定义字段集
        ('基本信息', {  # 基本信息字段集
            'fields': ('user', 'post', 'comment')  # 包含的字段
        }),
        ('时间信息', {  # 时间信息字段集
            'fields': ('created_at',),  # 包含的字段
            'classes': ('collapse',)  # 设置折叠样式
        }),
    )

# ============================================================================
# 通知与公告（第 37 批）
# ============================================================================
# ============================================================================
# 管理操作日志（第 146 批）—— **只读**
# ============================================================================
# 为什么只读：这张表是"谁在什么时候对谁做了什么"的凭据。
# 允许在 admin 里改它，等于让有权限的人**篡改审计记录**，那它就失去意义了。
# 所以三个动作全部禁掉，只留查看/搜索/筛选（新增只能由 `api/audit.py` 的助手写入）。
@admin.register(AdminAuditLog)
class AdminAuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor_repr', 'action', 'target_type',
                    'target_repr', 'detail_short', 'ip')
    list_filter = ('action', 'target_type', 'created_at')
    search_fields = ('actor_repr', 'target_repr', 'detail')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    list_per_page = 50

    def has_add_permission(self, request):        # 不允许手工补记录
        return False

    def has_change_permission(self, request, obj=None):   # 不允许改
        return False

    def has_delete_permission(self, request, obj=None):   # 不允许删
        return False

    @admin.display(description='说明')
    def detail_short(self, obj):
        text = obj.detail or ''
        return text if len(text) <= 60 else f'{text[:60]}…'


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'is_pinned', 'expires_at', 'created_by', 'created_at')
    list_filter = ('is_active', 'is_pinned', 'created_at')
    search_fields = ('title', 'content')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-is_pinned', '-created_at')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'recipient', 'type', 'title', 'actor', 'is_read', 'created_at')
    list_filter = ('type', 'is_read', 'created_at')
    search_fields = ('recipient__username', 'title', 'message')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


# ============================================================================
# 第 49 批：专家咨询
# ============================================================================
@admin.register(ExpertProfile)
class ExpertProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'specialties', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'title', 'specialties')
    list_editable = ('is_active',)


@admin.register(ConsultQuestion)
class ConsultQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'crop_type', 'asker', 'status', 'answer_count', 'created_at')
    list_filter = ('status', 'crop_type', 'created_at')
    search_fields = ('title', 'content', 'asker__username')
    readonly_fields = ('view_count', 'answer_count', 'created_at', 'updated_at', 'last_answer_at')


@admin.register(ConsultAnswer)
class ConsultAnswerAdmin(admin.ModelAdmin):
    list_display = ('id', 'question', 'author', 'author_title', 'is_accepted', 'created_at')
    list_filter = ('is_accepted', 'created_at')
    search_fields = ('content', 'author__username', 'question__title')
