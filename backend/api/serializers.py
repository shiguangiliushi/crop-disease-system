"""
序列化器（第 106 批补文件级说明）
============================================================================
本文件定义"模型 ↔ JSON"的转换，以及**一批藏在读路径里的业务规则** ——
后者比字段映射更值得注意，因为它们不写在这里就只能靠读代码发现：

| 序列化器 | 容易踩的地方 |
|---|---|
| `CustomUserSerializer` | **注册用的那个**（`AllowAny`）。`role` 必须只读，否则任何人能给自己注册管理员；密码走 `password_policy`（第 106 批统一为 8 位） |
| `DetectionHistorySerializer` | 它的 `get_pest_info` **会在 GET 期间写数据库**（把模糊匹配到的病害回填到行上，第 106 批补了说明）。字段多、回退分支多，是历史列表的读路径 |
| `PestInfoForHistorySerializer` | 与上一个的**兜底字典必须保持同形** —— 兜底是手写的，加了字段容易忘（第 106 批记录） |
| `NewsSerializer` | 双语字段（`title` / `title_en`）的取用规则；列表只回摘要 |
| `AdminUserSerializer` | 管理端用户列表；含注销冷静期字段（`deletion_scheduled_for` 等，第 101 批） |

约定：**序列化器只做转换与校验，不做业务副作用** ——
上面那个"读时写库"是唯一例外，且它是为了修历史脏数据（`pest_info` 为空的老记录），
新代码不要照着写。
"""
import json
import re
import time
from rest_framework import serializers  # 导入DRF序列化器模块
from django.db.models import Count  # 导入Django计数聚合函数
from django.utils import timezone  # 第 91 批：反馈里的识别摘要要按本地时区展示
from .models import (
    CustomUser, PestInfo, PreventionMethod, DetectionHistory, 
    Feedback, News, SensitiveWord, CropHealthProfile
)  # 导入模型类
from .models_forum import Post, Comment, Like, ForumBoard  # 导入论坛模型类
# 第 124 批：对象级约束里的"管理员例外"统一用 is_full_admin()（不是能力判定）
from .capabilities import is_full_admin
# 第 106 批：密码策略唯一来源（注册 / 邮箱重置 / 修改密码三处共用）
from .password_policy import MIN_LENGTH as PASSWORD_MIN_LENGTH, validate_password


class LoginSerializer(serializers.Serializer):
    """
    用户登录序列化器
    - 验证用户名和密码
    - 返回用户信息和token
    """
    username = serializers.CharField(required=True, allow_blank=False, label='用户名')
    password = serializers.CharField(required=True, allow_blank=False, label='密码', style={'input_type': 'password'})
    
    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')
        
        if not username or not password:
            raise serializers.ValidationError('用户名和密码不能为空')
            
        return attrs


def _user_avatar_url(obj, request):
    """
    用户头像的绝对地址（供本人/公开两套用户序列化器共用）。

    - 没有头像 → 返回 None，由前端用用户名首字母兜底。
      第 23 批之前前端会去请求 https://ui-avatars.com 生成占位图 ——
      这是个**外网依赖**，断网/内网部署时头像全部裂图（与"病害百科占位图
      依赖 via.placeholder.com"是同一类问题）。
    - 文件被手工删掉时 `obj.avatar.url` 仍会返回路径，这里不做文件存在性检查
      （避免每次序列化都碰磁盘），由前端 onerror 兜底。
    """
    if not obj or not getattr(obj, 'avatar', None):
        return None
    try:
        url = obj.avatar.url
    except ValueError:
        return None
    if request is not None:
        return request.build_absolute_uri(url)
    return url


class SocialFieldsMixin:
    """
    关注/粉丝字段的**实现**（第 40 批）

    抽成 mixin 的原因：个人主页有两种序列化器 ——
      · 看**自己**（或管理员看别人）→ `UserProfileSerializer`（含 email 等，可编辑）
      · 看**别人** → `UserPublicProfileSerializer`（对外安全字段）
    如果只在后者里加社交字段，那么"我自己的主页"就拿不到关注/粉丝数，
    前端还得为"自己的主页"单独再请求一次。两种形状都带上这几个字段最省事。

    ⚠️ 注意：`SerializerMethodField` 必须在**序列化器类体里**声明 ——
    DRF 的 SerializerMetaclass 只收集"带有 `_declared_fields` 的基类"的字段，
    普通 mixin 里的 Field 不会被收进 `_declared_fields`，`Meta.fields` 里写了它就会 500。
    所以这里只放方法实现，字段声明放在两个序列化器里各写一遍。
    """

    def _viewer(self):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        return user if (user and user.is_authenticated) else None

    def get_following_count(self, obj):
        from .models_social import Follow
        return Follow.objects.filter(follower=obj).count()

    def get_follower_count(self, obj):
        from .models_social import Follow
        return Follow.objects.filter(following=obj).count()

    def get_is_following(self, obj):
        from .models_social import Follow
        viewer = self._viewer()
        if not viewer or viewer.id == obj.id:
            return False
        return Follow.objects.filter(follower=viewer, following=obj).exists()

    def get_is_self(self, obj):
        viewer = self._viewer()
        return bool(viewer and viewer.id == obj.id)

    # 第 42 批：等级与积分（等级由积分推导，见 api/models_points.py）
    def get_points(self, obj):
        from .services_points import points_summary
        return points_summary(obj)


class UserProfileSerializer(SocialFieldsMixin, serializers.ModelSerializer):  # 定义用户资料序列化器
    """用户资料序列化器（本人或管理员查看时使用，含邮箱等）"""
    avatar = serializers.SerializerMethodField()  # 定义头像字段为方法字段
    is_staff = serializers.BooleanField(read_only=True)  # 添加管理员状态字段
    # 第 40 批：社交数据（实现见 SocialFieldsMixin）
    following_count = serializers.SerializerMethodField()
    follower_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    is_self = serializers.SerializerMethodField()
    points = serializers.SerializerMethodField()  # 第 42 批

    class Meta:  # 定义元数据
        model = CustomUser  # 关联用户模型
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'role',
                  'bio', 'date_joined', 'last_login', 'avatar', 'is_staff',
                  'following_count', 'follower_count', 'is_following', 'is_self',
                  'points')  # 包含的字段（points 见第 42 批）
        read_only_fields = ('id', 'date_joined', 'last_login', 'is_staff')  # 只读字段

    def get_avatar(self, obj):  # 定义获取头像方法
        # 返回真实头像地址（第 23 批：新增 CustomUser.avatar 字段后不再是 None）
        return _user_avatar_url(obj, self.context.get('request'))


class UserPublicProfileSerializer(SocialFieldsMixin, serializers.ModelSerializer):
    """
    公开的用户资料（他人查看时使用）

    说明：UserProfileSerializer 含 email / last_login 等敏感字段，而 /api/users/{id}/
    原本对匿名用户也会返回这些信息（任何人都能遍历用户收集邮箱）。对外展示改用本序列化器。

    第 40 批：两种序列化器都带上社交数据
    （关注数 / 粉丝数 / 我是否已关注 / 是不是我自己）。
    """
    avatar = serializers.SerializerMethodField()
    # 第 40 批：社交数据（实现见 SocialFieldsMixin）
    following_count = serializers.SerializerMethodField()
    follower_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    is_self = serializers.SerializerMethodField()
    # 第 42 批：积分与等级 —— 必须在这里**显式声明**，否则 DRF 会回退去读模型的
    # `CustomUser.points` 整数字段，前端拿到的是数字而不是 {points, level, ...} 汇总。
    points = serializers.SerializerMethodField()

    class Meta:  # 定义元数据
        model = CustomUser  # 关联用户模型
        fields = (
            'id', 'username', 'first_name', 'last_name', 'role', 'bio', 'date_joined', 'avatar',
            'following_count', 'follower_count', 'is_following', 'is_self',
            'points',  # 第 42 批：积分与等级
        )
        read_only_fields = fields

    def get_avatar(self, obj):
        return _user_avatar_url(obj, self.context.get('request'))


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """用户资料更新（仅允许修改这几个安全字段）"""

    class Meta:  # 定义元数据
        model = CustomUser  # 关联用户模型
        fields = ('first_name', 'last_name', 'email', 'bio')

    def validate_email(self, value):
        value = (value or '').strip()
        if not value:
            return value
        queryset = CustomUser.objects.filter(email__iexact=value)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('该邮箱已被其他账号使用')
        return value

    def validate_first_name(self, value):
        return (value or '').strip()

    def validate_last_name(self, value):
        return (value or '').strip()


class UserStatsSerializer(serializers.ModelSerializer):  # 定义用户统计信息序列化器
    """用户统计信息序列化器"""
    post_count = serializers.IntegerField(read_only=True)  # 帖子数量字段
    comment_count = serializers.IntegerField(read_only=True)  # 评论数量字段
    like_count = serializers.IntegerField(read_only=True)  # 点赞数量字段

    class Meta:  # 定义元数据
        model = CustomUser  # 关联用户模型
        fields = ('post_count', 'comment_count', 'like_count')  # 包含的字段


class AdminUserSerializer(serializers.ModelSerializer):
    """
    管理端用户列表 / 详情序列化器（第 76 批）

    背景：管理后台此前**没有用户管理**入口 —— 管理员只能看帖子、反馈、新闻，
    想看"平台上有哪些用户、谁是专家、谁最近登录过"只能进 Django 自带的 /admin/。
    本序列化器专供 `/api/admin/users/`，字段按"管理员排查问题"的需要选：

      · 身份：`role` / `role_display` / `is_staff` / `is_superuser` / `is_active`
      · 专家：`is_expert` / `expert_title` / `expert_specialties` / `expert_granted_at`
      · 活跃度：`post_count` / `comment_count` / `detection_count` / `points`
      · 时间：`date_joined` / `last_login`

    ⚠️ 计数优先读 queryset 上的 `annotate()`（列表页一次查询解决 N+1），
    没有注解时（例如详情接口直接取单个对象）才回退成实时 count。
    ⚠️ 邮箱等字段只对管理员可见 —— 本序列化器**只能**挂在 IsAdminUser 的接口上。
    """

    avatar = serializers.SerializerMethodField()
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    # 第 128 批：编辑员的**内容模块**（前端列表/弹窗要显示"编辑员（新闻管理、意见反馈）"）
    content_modules = serializers.SerializerMethodField()
    content_modules_display = serializers.SerializerMethodField()
    is_expert = serializers.SerializerMethodField()
    expert_title = serializers.SerializerMethodField()
    expert_specialties = serializers.SerializerMethodField()
    expert_granted_at = serializers.SerializerMethodField()
    post_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    detection_count = serializers.SerializerMethodField()
    points = serializers.IntegerField(read_only=True)

    class Meta:
        model = CustomUser
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name', 'avatar',
            'role', 'role_display', 'is_staff', 'is_superuser', 'is_active',
            # 第 128 批：编辑员的内容模块（只在 role=EDITOR 时有值）
            'content_modules', 'content_modules_display',
            'is_expert', 'expert_title', 'expert_specialties', 'expert_granted_at',
            'post_count', 'comment_count', 'detection_count', 'points',
            'date_joined', 'last_login',
            # 第 95 批：注销状态（`?include_deleted=true` 审计时要用它区分）
            'is_deleted', 'deleted_at',
            # 第 101 批：注销冷静期（申请时间 / 计划删除时间 / 剩余天数）
            'deletion_requested_at', 'deletion_scheduled_for', 'deletion_days_left',
        )
        read_only_fields = fields

    # -- 内部工具 ---------------------------------------------------------
    def get_avatar(self, obj):
        return _user_avatar_url(obj, self.context.get('request'))

    # -- 第 128 批：编辑员的内容模块 ----------------------------------------
    def get_content_modules(self, obj):
        """
        该账号实际拥有的内容模块（全权管理员 → 四个全给；编辑员 → 授权表里的）

        只对 `role='EDITOR'` 与全权管理员有意义：普通用户返回空数组
        （前端据此决定"改角色弹窗里勾哪些框"）。
        """
        from .capabilities import content_modules_of

        if getattr(obj, 'role', None) == 'EDITOR' or is_full_admin(obj):
            return content_modules_of(obj)
        return []

    def get_content_modules_display(self, obj):
        """模块的中文名列表（列表里直接显示，省得前端再翻译一次）"""
        from .capabilities import MODULE_LABELS

        return [MODULE_LABELS[module] for module in self.get_content_modules(obj)]

    def _expert_profile(self, obj):
        """
        取专家档案。

        注意：撤销专家走的是 `is_active=False`（软删除），所以这里**必须**
        判 `is_active`，否则"已取消专家"在用户管理页仍显示成专家。
        """
        profile = getattr(obj, 'expert_profile', None)
        if profile is None or not profile.is_active:
            return None
        return profile

    def _annotated_or_count(self, obj, field, related_name):
        value = getattr(obj, field, None)
        if value is not None:
            return value
        return getattr(obj, related_name).count()

    # -- 字段实现 ---------------------------------------------------------
    def get_is_expert(self, obj):
        return self._expert_profile(obj) is not None

    def get_expert_title(self, obj):
        profile = self._expert_profile(obj)
        return profile.title if profile else ''

    def get_expert_specialties(self, obj):
        profile = self._expert_profile(obj)
        return profile.specialty_list if profile else []

    def get_expert_granted_at(self, obj):
        profile = self._expert_profile(obj)
        return profile.created_at if profile else None

    def get_post_count(self, obj):
        return self._annotated_or_count(obj, 'post_count', 'forum_posts')

    def get_comment_count(self, obj):
        return self._annotated_or_count(obj, 'comment_count', 'forum_comments')

    def get_detection_count(self, obj):
        # DetectionHistory.user 没有写 related_name，所以反向访问器是默认的
        # `detectionhistory_set`（而 annotate 里用的是查询名 `detectionhistory`）。
        return self._annotated_or_count(obj, 'detection_count', 'detectionhistory_set')


class CustomUserSerializer(serializers.ModelSerializer):  # 定义用户序列化器
    """
    注册用的用户序列化器（**这是公开接口 AllowAny 的那一个**）。

    为什么特意在类上写这一句（第 106 批补）：本序列化器只被 `RegisterView` 使用，
    而注册接口是匿名的 —— 这决定了下面两条约束**不能动**：
      · `role` 必须只读（否则任何人能给自己注册出管理员）；
      · `password` 必须走统一密码策略，不能比别的入口松。

    改前这里的 `min_length` 是 **6**，而「修改密码」要求 **8** ——
    于是同一套系统里"注册能过但改不成"的密码是存在的（第 106 批统一为 8）。
    """

    class Meta:  # 定义元数据
        model = CustomUser  # 关联用户模型
        # ⚠️ password 必须列进 fields：只写 extra_kwargs 是不够的。
        # 之前 fields 里没有 password，DRF 根本不会接收它，validated_data 里也就没有
        # password → create() 里 CustomUser.objects.create_user(**validated_data) 相当于
        # 不传密码 → Django 会设置“不可用密码”（has_usable_password() == False）。
        # 实测后果：注册接口返回 201，但用同一组账号密码永远登录不上。
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'role', 'password')  # 包含的字段
        extra_kwargs = {  # 额外参数
            # write_only：保证任何响应体里都不会出现密码
            # 第 106 批：min_length 取自统一策略（8），不再写死一个和别处不同的数字。
            # 真正的规则（含"不能纯数字"与 Django 内置弱口令校验）在
            # `validate_password` 里，因为 DRF 的 min_length 只能表达长度。
            'password': {'write_only': True, 'min_length': PASSWORD_MIN_LENGTH},  # 密码字段只写
            # 🔒 关键安全约束：role 必须只读。
            # 本序列化器只被 RegisterView 使用，而注册接口是 AllowAny（任何人可访问）；
            # 若 role 可写，攻击者只要 POST {"username":..., "password":..., "role":"ADMIN"}
            # 就能给自己注册出管理员账号，进而修改/删除病害百科、他人新闻、
            # 读取与清空所有人的识别历史。管理员的 role 只能由后台/管理员修改。
            'role': {'read_only': True},
        }

    def validate_password(self, value):  # 第 106 批：密码策略统一走 password_policy
        """
        字段级校验：长度 / 纯数字 / 常见弱口令 / 与用户名过于相似。

        放在字段级（而不是 `validate()`）是为了让错误挂在 `password` 字段上，
        前端能直接把消息显示在密码输入框下面。
        """
        problem = validate_password(value)
        if problem:
            raise serializers.ValidationError(problem)
        return value

    def create(self, validated_data):  # 定义创建方法
        user = CustomUser.objects.create_user(**validated_data)  # 创建用户
        return user  # 返回用户对象

    # 第 35 批：服务端强校验用户名格式与唯一性
    # （此前注册只靠前端提示，服务端对格式没有任何约束：
    #   1 个字符的用户名、含空格/特殊符号的用户名都能注册成功。）
    def validate_username(self, value):
        from .views_user import validate_username_format  # 局部导入避免循环依赖
        username = (value or '').strip()
        ok, message = validate_username_format(username)
        if not ok:
            raise serializers.ValidationError(message)
        return username

    def validate_email(self, value):
        """邮箱可选，但填了就必须唯一（找回密码要靠它）"""
        email = (value or '').strip()
        if email and CustomUser.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('该邮箱已被其他账号使用')
        return email


class PreventionMethodSerializer(serializers.ModelSerializer):
    """
    防治方法序列化器
    - 用于序列化防治方法数据
    - 包含防治类别、具体措施等信息
    """
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    
    class Meta:
        model = PreventionMethod
        fields = ['id', 'category', 'category_display', 'measure', 'measure_en', 'pest']
        read_only_fields = ['id']


# New Serializer for the List View (more lightweight)
class PestInfoListSerializer(serializers.ModelSerializer):  # 定义病害信息列表序列化器
    image = serializers.SerializerMethodField()  # 定义图片字段为方法字段

    class Meta:  # 定义元数据
        model = PestInfo  # 关联病害信息模型
        fields = ('id', 'name', 'name_en', 'crop_type', 'crop_type_en', 'symptoms', 'symptoms_en',
                  'english_identifier', 'image', 'scientific_name')  # 包含的字段
        # 第 192 批补 `scientific_name`：列表页展示学名是常见需求，且它很短（最长 60 字），
        # 不会让这个"轻量"序列化器变重。**不加 `sources`** —— 那是详情才需要的。

    def get_image(self, obj):  # 定义获取图片方法
        if obj.image and hasattr(obj.image, 'url'):  # 检查图片是否存在
            return obj.image.url  # 返回图片URL
        return ''  # 返回空字符串


class CropHealthProfileSerializer(serializers.ModelSerializer):  # 第 192 批：作物健康管理档案
    """
    作物健康管理档案（校准版知识库的 healthy 记录）。

    字段名刻意与 `PestInfo` 对齐：`morphology` ↔ `symptoms`、`growing_conditions` ↔ `description`，
    这样前端两处渲染逻辑可以共用同一套写法，不必记两套字段名。
    """

    class Meta:
        model = CropHealthProfile
        fields = (
            'id', 'name', 'name_en', 'crop_type', 'crop_type_en', 'scientific_name',
            'morphology', 'morphology_en', 'growing_conditions', 'growing_conditions_en',
            'care_agricultural', 'care_agricultural_en',
            'care_chemical', 'care_chemical_en',
            'care_ecological', 'care_ecological_en',
            'care_physical', 'care_physical_en',
            'care_monitoring', 'care_monitoring_en',
            'sources', 'updated_at',
        )


# Serializer for the Detail View (with all fields)
class PestInfoDetailSerializer(serializers.ModelSerializer):  # 定义病害信息详情序列化器
    image = serializers.SerializerMethodField()  # 定义图片字段为方法字段
    trigger = serializers.SerializerMethodField()  # 定义发病规律字段为方法字段
    trigger_en = serializers.SerializerMethodField()  # 第 72 批：发病规律（英文）
    prevention_methods = PreventionMethodSerializer(many=True, read_only=True)  # 定义防治方法字段
    crop_type = serializers.CharField(read_only=True)  # 添加作物类型字段
    description = serializers.CharField(read_only=True)  # 添加描述字段
    english_identifier = serializers.CharField(read_only=True)  # 添加英文标识符字段
    # 第 192 批：健康管理档案（只有 12 条「健康X」词条有；用 SerializerMethodField 而不是
    # 直接写 `health_profile`，因为 OneToOne 反向关系不存在时 DRF 会抛 RelatedObjectDoesNotExist，
    # 而不是返回 null —— 详情接口不能因为"这条没有档案"就 500）。
    health_profile = serializers.SerializerMethodField()

    class Meta:  # 定义元数据
        model = PestInfo  # 关联病害信息模型
        fields = [
            'id', 'name', 'name_en', 'crop_type', 'crop_type_en', 'english_identifier', 'image', 
            'symptoms', 'symptoms_en', 'description', 'description_en', 'trigger', 'trigger_en',
            'prevention_methods', 'scientific_name', 'sources', 'health_profile'
        ]  # 包含的字段
        # 第 192 批新增 `scientific_name` / `sources` / `health_profile`：
        # 前两个来自校准版知识库（学名 + 权威来源 URL），助手回答要引用 sources；
        # 前端此前未引用它们，加字段是纯新增。

    def get_image(self, obj):  # 定义获取图片方法
        if obj.image and hasattr(obj.image, 'url'):  # 检查图片是否存在
            return obj.image.url  # 返回图片URL
        return ''  # 返回空字符串

    def get_trigger(self, obj):  # 定义获取发病规律方法
        return obj.description or '暂无发病规律信息'  # 返回描述或默认文本

    def get_trigger_en(self, obj):  # 第 72 批：发病规律的英文版本
        return obj.description_en or obj.description or ''

    def get_health_profile(self, obj):  # 第 192 批：健康管理档案（没有就返回 None）
        profile = getattr(obj, 'health_profile', None)
        if profile is None:
            return None
        return CropHealthProfileSerializer(profile, context=self.context).data


# New serializer for history, including prevention methods
class PestInfoForHistorySerializer(serializers.ModelSerializer):  # 定义历史记录病害信息序列化器
    prevention_methods = PreventionMethodSerializer(many=True, read_only=True)  # 定义防治方法字段

    class Meta:  # 定义元数据
        model = PestInfo  # 关联病害信息模型
        fields = ['name', 'name_en', 'crop_type', 'crop_type_en', 'symptoms', 'symptoms_en',
                  'description_en', 'prevention_methods']  # 包含的字段


class FlexibleJSONField(serializers.Field):
    """
    兼容 JSON 请求体与 multipart 表单的 JSON 字段
    - application/json 请求：值已是 Python 对象，直接使用
    - multipart/form-data 请求：值是 JSON 字符串，自动解析
    """

    default_error_messages = {'invalid': '内容必须是合法的 JSON'}

    def to_internal_value(self, data):
        if isinstance(data, str):
            if not data.strip():
                return []
            try:
                data = json.loads(data)
            except (TypeError, ValueError):
                self.fail('invalid')
        return data

    def to_representation(self, value):
        return value


class PestInfoWriteSerializer(serializers.ModelSerializer):
    """
    病害百科写入序列化器（新增/修改，仅管理员可用）
    - 覆盖病害基本信息与图片
    - 可通过 prevention_methods 一次性提交防治方法列表（整体替换）
    - clear_image=true 时移除已有图片
    """

    image = serializers.ImageField(required=False, allow_null=True)
    prevention_methods = FlexibleJSONField(required=False, write_only=True)
    clear_image = serializers.BooleanField(required=False, write_only=True, default=False)

    class Meta:
        model = PestInfo
        fields = [
            'id', 'name', 'name_en', 'crop_type', 'crop_type_en', 'symptoms', 'symptoms_en',
            'english_identifier', 'description', 'description_en', 'image', 'clear_image',
            'prevention_methods',
        ]
        read_only_fields = ['id']

    def validate_name(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('病害名称不能为空')
        return value

    def validate_crop_type(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('作物类型不能为空')
        return value

    def validate_english_identifier(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('英文标识符不能为空')
        return value

    def validate_prevention_methods(self, value):
        """校验防治方法列表，过滤掉完全空白的条目"""
        if value in (None, ''):
            return []

        if not isinstance(value, list):
            raise serializers.ValidationError('防治方法必须是数组')

        valid_categories = {item[0] for item in PreventionMethod.CATEGORY_CHOICES}
        cleaned = []

        for index, item in enumerate(value, start=1):
            if not isinstance(item, dict):
                raise serializers.ValidationError(f'第 {index} 条防治方法格式不正确')

            category = str(item.get('category') or '').strip()
            measure = str(item.get('measure') or '').strip()

            # 允许前端保留空行，直接忽略
            if not category and not measure:
                continue

            if category not in valid_categories:
                raise serializers.ValidationError(f'第 {index} 条防治方法的类别不合法')
            if not measure:
                raise serializers.ValidationError(f'第 {index} 条防治方法缺少具体措施')

            cleaned.append({'category': category, 'measure': measure})

        return cleaned

    def _sync_prevention_methods(self, pest, methods):
        """整体替换该病害的防治方法"""
        pest.prevention_methods.all().delete()
        if methods:
            PreventionMethod.objects.bulk_create([
                PreventionMethod(pest=pest, category=method['category'], measure=method['measure'])
                for method in methods
            ])

    def create(self, validated_data):
        methods = validated_data.pop('prevention_methods', [])
        clear_image = validated_data.pop('clear_image', False)
        if clear_image:
            validated_data['image'] = None

        pest = PestInfo.objects.create(**validated_data)
        if methods:
            self._sync_prevention_methods(pest, methods)
        return pest

    def update(self, instance, validated_data):
        methods = validated_data.pop('prevention_methods', None)
        clear_image = validated_data.pop('clear_image', False)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if clear_image:
            instance.image = None

        instance.save()

        if methods is not None:
            self._sync_prevention_methods(instance, methods)

        return instance

    def to_representation(self, instance):
        """写入后返回与详情接口一致的结构，方便前端直接刷新"""
        return PestInfoDetailSerializer(instance, context=self.context).data


import logging  # 导入日志模块

logger = logging.getLogger(__name__)  # 获取日志记录器


from django.utils import timezone
from django.conf import settings

class DetectionHistorySerializer(serializers.ModelSerializer):  # 定义检测历史序列化器
    user = serializers.SerializerMethodField()  # 定义用户字段为方法字段
    pest_info = serializers.SerializerMethodField()  # 定义病害信息字段为方法字段
    image = serializers.SerializerMethodField()  # 定义图片字段为方法字段
    disease_name = serializers.SerializerMethodField()  # 定义病害名称字段为方法字段
    symptoms = serializers.SerializerMethodField()  # 定义症状字段为方法字段
    suggestion = serializers.SerializerMethodField()  # 定义建议字段为方法字段
    annotated_image_url = serializers.SerializerMethodField()  # 定义标注图片URL字段为方法字段
    timestamp_formatted = serializers.SerializerMethodField()  # 添加格式化时间字段

    def get_user(self, obj):
        if obj.user:
            return {
                'id': obj.user.id,
                'username': obj.user.username,
                'is_staff': obj.user.is_staff
            }
        return None

    def get_pest_info(self, obj):  # 定义获取病害信息方法
        """Custom getter for pest_info with detailed debugging"""
        logger.debug(f'[DEBUG] Getting pest_info for DetectionHistory ID: {obj.id}')  # 记录调试信息

        # 检查 pest_info 是否存在
        if not hasattr(obj, 'pest_info'):  # 检查属性是否存在
            logger.warning(f'[WARNING] DetectionHistory {obj.id} has no pest_info attribute')  # 记录警告信息
            return None  # 返回空值

        if obj.pest_info is None:  # 检查病害信息是否为空
            logger.warning(  # 记录警告信息
                f"[WARNING] DetectionHistory {obj.id} has pest_info=None. "
                f"Detection result: {getattr(obj, 'detection_result', 'N/A')}. "
                f"Created at: {getattr(obj, 'timestamp', 'N/A')}"
            )
            # 尝试通过 detection_result 查找对应的 PestInfo
            if hasattr(obj, 'detection_result') and obj.detection_result:  # 检查检测结果是否存在
                try:  # 尝试查找匹配的病害信息
                    from django.db.models import Q  # 导入查询工具
                    from .models import PestInfo  # 导入病害信息模型

                    # 尝试通过 detection_result 查找匹配的 PestInfo
                    matching_pest = PestInfo.objects.filter(  # 查询匹配的病害信息
                        Q(name__icontains=obj.detection_result) |  # 名称包含检测结果
                        Q(english_identifier__iexact=obj.detection_result)  # 英文标识符匹配检测结果
                    ).first()  # 获取第一个匹配项

                    if matching_pest:  # 检查是否找到匹配项
                        logger.info(
                            f'[INFO] Found matching pest_info for detection_result "{obj.detection_result}": {matching_pest.id} - {matching_pest.name}')  # 记录信息
                        # 更新记录以修复关联
                        obj.pest_info = matching_pest  # 设置病害信息
                        obj.save(update_fields=['pest_info'])  # 保存更新
                        return PestInfoForHistorySerializer(matching_pest, context=self.context).data  # 返回序列化数据
                    else:  # 如果未找到匹配项
                        logger.warning(
                            f'[WARNING] No matching PestInfo found for detection_result: {obj.detection_result}')  # 记录警告信息
                except Exception as e:  # 捕获异常
                    logger.error(f'[ERROR] Error trying to find matching PestInfo: {str(e)}')  # 记录错误信息
            return None  # 返回空值

        try:  # 尝试序列化病害信息
            # 记录详细的 pest_info 信息
            logger.debug(  # 记录调试信息
                f'[DEBUG] Found pest_info for DetectionHistory {obj.id}:\n'
                f'  - PestInfo ID: {obj.pest_info.id}\n'
                f'  - Name: {getattr(obj.pest_info, "name", "N/A")}\n'
                f'  - Detection result: {getattr(obj, "detection_result", "N/A")}'
            )

            # 使用原始序列化器但添加更多错误处理
            serialized_data = PestInfoForHistorySerializer(obj.pest_info, context=self.context).data  # 序列化数据
            if not serialized_data.get('name'):  # 检查名称是否存在
                logger.warning(f'[WARNING] Serialized pest_info has no name. Raw data: {serialized_data}')  # 记录警告信息
            return serialized_data  # 返回序列化数据

        except Exception as e:  # 捕获异常
            logger.error(  # 记录错误信息
                f'[ERROR] Error serializing pest_info for DetectionHistory {obj.id}: {str(e)}\n'
                f'  - PestInfo ID: {obj.pest_info.id if obj.pest_info else "None"}\n'
                f'  - Error type: {type(e).__name__}\n'
                f'  - Detection result: {getattr(obj, "detection_result", "N/A")}'
            )
            # 返回一个包含基本信息的字典，而不是 None
            if obj.pest_info:  # 检查病害信息是否存在
                return {  # 返回基本信息
                    'id': obj.pest_info.id,  # ID
                    'name': getattr(obj.pest_info, 'name', '未知病害'),  # 名称
                    'crop_type': getattr(obj.pest_info, 'crop_type', '未知作物'),  # 作物类型
                    'symptoms': getattr(obj.pest_info, 'symptoms', '暂无症状描述'),  # 症状
                    'prevention_methods': []  # 防治方法
                }
            return None  # 返回空值

    class Meta:  # 定义元数据
        model = DetectionHistory  # 关联检测历史模型
        fields = [  # 包含的字段
            'id', 'user', 'image', 'detection_result', 'pest_info',
            'timestamp', 'timestamp_formatted', 'confidence', 'disease_name', 'symptoms',
            'suggestion', 'annotated_image_url'
        ]
        
    def get_timestamp_formatted(self, obj):
        """Format the timestamp in the user's local timezone"""
        if not obj.timestamp:
            return None
            
        # Convert to local timezone if timezone is set in settings
        if hasattr(settings, 'TIME_ZONE'):
            local_tz = timezone.get_default_timezone()
            local_time = timezone.localtime(obj.timestamp, timezone=local_tz)
        else:
            local_time = obj.timestamp
            
        # Format the datetime as a string in the format: YYYY-MM-DD HH:MM:SS
        return local_time.strftime('%Y-%m-%d %H:%M:%S')

    def get_image(self, obj):  # 定义获取图片方法
        if not obj.image:  # 检查图片是否存在
            return None  # 返回空值

        request = self.context.get('request')  # 获取请求对象
        try:  # 尝试构建图片URL
            # 确保URL以斜杠开头
            url = obj.image.url  # 获取图片URL
            if not url.startswith('/'):  # 检查是否以斜杠开头
                url = '/' + url  # 添加斜杠

            # 构建完整的URL
            if request is not None:  # 检查请求对象是否存在
                return request.build_absolute_uri(url)  # 返回绝对URL
            else:  # 如果请求对象不存在
                # 如果没有request对象，返回完整URL（使用settings中的配置）
                from django.conf import settings
                base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
                return f"{base_url.rstrip('/')}{url}"

        except Exception as e:  # 捕获异常
            logger = logging.getLogger(__name__)  # 获取日志记录器
            logger.error(f"Error generating image URL: {str(e)}")  # 记录错误信息
            return None  # 返回空值

    def get_disease_name(self, obj):
        # 优先从关联的pest_info获取病害名称
        if obj.pest_info:
            return getattr(obj.pest_info, 'name', None) or obj.detection_result or '未知病害'
        # 如果没有关联的pest_info，则使用detection_result
        return obj.detection_result or '未知病害'

    def get_symptoms(self, obj):  # 定义获取症状方法
        if not obj.pest_info:  # 检查病害信息是否存在
            return '该病害暂无详细症状描述'  # 返回默认文本
        return obj.pest_info.symptoms  # 返回症状

    def get_suggestion(self, obj):  # 定义获取建议方法
        if not obj.pest_info:  # 检查病害信息是否存在
            return '未找到匹配的病害信息，建议重新识别或联系管理员。'  # 返回默认文本
        return ''  # 返回空字符串

    def get_annotated_image_url(self, obj):  # 定义获取标注图片URL方法
        if not obj.annotated_image:  # 检查标注图片是否存在
            return None  # 返回空值

        request = self.context.get('request')  # 获取请求对象
        try:  # 尝试构建标注图片URL
            # 确保URL以斜杠开头
            url = obj.annotated_image.url  # 获取标注图片URL
            if not url.startswith('/'):  # 检查是否以斜杠开头
                url = '/' + url  # 添加斜杠

            # 构建完整的URL
            if request is not None:  # 检查请求对象是否存在
                return request.build_absolute_uri(url)  # 返回绝对URL
            else:  # 如果请求对象不存在
                # 如果没有request对象，返回相对URL
                return url  # 返回相对URL

        except Exception as e:  # 捕获异常
            logger = logging.getLogger(__name__)  # 获取日志记录器
            logger.error(f"Error generating annotated image URL: {str(e)}")  # 记录错误信息
            return None  # 返回空值


# 用户反馈序列化器
class FeedbackSerializer(serializers.ModelSerializer):  # 定义用户反馈序列化器
    """
    用户反馈序列化器

    第 26 批：
    - 新增 反馈类型 / 处理状态 / 管理员回复 / 处理时间，支撑独立的「意见反馈」页面；
    - `status` / `admin_reply` / `handled_at` **只读**（由管理员在后台流转，用户不能自评"已处理"）；
    - `disease_name` / `is_correct` 改为可选（一般性意见没有识别结果）；
    - 补 `image_url` 绝对地址，列表里可直接显示缩略图。
    """
    user = serializers.ReadOnlyField(source='user.username')  # 定义用户字段为只读
    image_url = serializers.SerializerMethodField()
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    #: 第 79 批：反馈里的病害名是**提交时的中文快照**（`disease_name` 不是外键），
    #: 英文界面下原来一直显示中文。这里按名字回查百科，补一个英文名（查不到则为空，
    #: 前端 `localizedField` 会回落到原文，不会出现空白）。
    disease_name_en = serializers.SerializerMethodField()
    suggestion_en = serializers.SerializerMethodField()
    #: 第 85 批：管理员回复也是人写的中文，英文界面下同样需要译文。
    #: 这个字段直接对应模型字段（可由管理员在 admin 里手工填写，也可由翻译命令回填）。
    admin_reply_en = serializers.CharField(required=False, allow_blank=True)
    translation_stale = serializers.BooleanField(read_only=True)
    translation_source = serializers.CharField(read_only=True)

    # ------------------------------------------------------------------
    # 第 91 批：识别纠错 → 训练样本的链路
    # ------------------------------------------------------------------
    #: 前端一直在传 `detection_id`（DetectView.vue / mobile api/detection.js），
    #: 但模型与序列化器都没有这个字段 —— 参数被**静默丢弃**。这里接上：
    #: 用 `source='detection'` 让请求体里的键就是前端已经在用的 `detection_id`。
    detection_id = serializers.PrimaryKeyRelatedField(
        source='detection', queryset=DetectionHistory.objects.all(),
        required=False, allow_null=True,
    )
    corrected_pest_id = serializers.PrimaryKeyRelatedField(
        source='corrected_pest', queryset=PestInfo.objects.all(),
        required=False, allow_null=True,
    )
    #: 只读回显：管理员在反馈列表里要能看出"这条纠错指的是哪条识别、纠正成了什么"
    detection_summary = serializers.SerializerMethodField()
    corrected_pest_name = serializers.SerializerMethodField()
    is_trainable = serializers.BooleanField(read_only=True)  # 模型属性，只读透出

    class Meta:  # 定义元数据
        model = Feedback  # 关联用户反馈模型
        fields = [  # 包含的字段
            'id', 'user', 'category', 'category_display', 'image', 'image_url',
            'disease_name', 'disease_name_en', 'confidence', 'is_correct', 'suggestion',
            'suggestion_en', 'admin_reply_en', 'translation_stale', 'translation_source',
            'status', 'status_display', 'admin_reply', 'handled_at', 'timestamp',
            # 第 91 批
            'detection_id', 'detection_summary', 'corrected_pest_id', 'corrected_pest_name',
            'verify_status', 'exported_at', 'is_trainable',
        ]
        read_only_fields = ['id', 'timestamp', 'status', 'admin_reply', 'handled_at',
                            'translation_stale', 'translation_source', 'exported_at',
                            # 第 91 批：样本确认状态**只能由管理员改**（Django admin 的
                            # 批量动作），普通用户不能自己把反馈标成"已确认" ——
                            # 否则"人工确认"这道闸门等于没有，样本池会被自助灌水。
                            'verify_status']

    def get_detection_summary(self, obj):
        """这条纠错对应哪条识别：时间 + 当时的结论 + 置信度（管理员复查用）"""
        detection = obj.detection
        if detection is None:
            return ''
        when = timezone.localtime(detection.timestamp).strftime('%Y-%m-%d %H:%M') \
            if detection.timestamp else ''
        conf = f'{detection.confidence:.0%}' if detection.confidence is not None else '—'
        return f'{when} · {detection.detection_result} · {conf}'

    def get_corrected_pest_name(self, obj):
        """纠正为的病害名（按当前语言给英文名，缺失回落中文）"""
        pest = obj.corrected_pest
        if pest is None:
            return ''
        return getattr(pest, 'name_en', '') or pest.name

    #: 「识别正确 / 识别错误」是**旧版本前端写死的按钮文案**（第 79 批已改成走 i18n），
    #: 库里 13+3 条历史反馈存的就是这两句中文。它们不是用户敲的字，翻成英文是对的；
    #: 用户自己写的正文（如「这是健康草莓叶片…」）不在此表，保持原样。
    SYSTEM_SUGGESTION_EN = {
        '识别正确': 'Marked correct',
        '识别错误': 'Marked incorrect',
    }

    #: 识别流程生成的"健康"复合名，形如「作物健康 (苹果)」
    HEALTHY_NAME_PATTERN = re.compile(r'^作物健康\s*[(（](.+?)[)）]$')

    def _get_maps(self):
        """一条 SQL 取中英对照，并在本次序列化内缓存（列表页避免 N+1）"""
        cache = getattr(self, '_content_en_maps', None)
        if cache is None:
            from .services_content_i18n import pest_en_maps
            cache = pest_en_maps()  # (病害名映射, 作物名映射)
            self._content_en_maps = cache
        return cache

    def get_disease_name_en(self, obj):
        name = (obj.disease_name or '').strip()
        if not name:
            return ''
        name_map, crop_map = self._get_maps()
        healthy = self.HEALTHY_NAME_PATTERN.match(name)
        if healthy:
            crop_en = crop_map.get(healthy.group(1).strip(), '')
            return f'Healthy ({crop_en})' if crop_en else ''
        return name_map.get(name, '')

    def get_suggestion_en(self, obj):
        """第 85 批：反馈内容的英文取值（**先看系统固定映射，再看数据库译文**）

        「识别正确 / 识别错误」是旧版本前端写死的按钮文案，不是用户敲的字，
        有确定的中英对照；它们**优先**用这张表 —— 否则一旦库里有历史机翻结果
        （实测公共接口给的是 "Identify Correctly"，还不如固定映射准确），
        英文界面就会显示这句。用户自己写的正文则用数据库里的译文（人工或机器），
        取不到就返回空串，前端 `localizedField` 会回落到原文。
        """
        fixed = self.SYSTEM_SUGGESTION_EN.get((obj.suggestion or '').strip())
        if fixed:
            return fixed
        return (getattr(obj, 'suggestion_en', '') or '').strip()

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        try:
            url = obj.image.url
        except ValueError:
            return None
        return request.build_absolute_uri(url) if request is not None else url

    def validate(self, attrs):
        """反馈内容不能为空：至少要有文字或图片"""
        instance = self.instance
        content = attrs.get('suggestion', instance.suggestion if instance else '')
        has_image = bool(attrs.get('image') or (instance and instance.image))
        if not (content or '').strip() and not has_image:
            raise serializers.ValidationError({'suggestion': ['请填写反馈内容（或上传一张图片）']})

        # 第 91 批：纠错只能关联**自己**的识别记录。
        # 不校验的话，任何人传别人的 detection_id 就能把反馈挂到别人的识别结果上
        # （反馈是公开可查的，等于泄露"某人某时识别了什么"）。
        #
        # 第 124 批：管理员例外条件从 `is_staff` 改为 `is_full_admin()`
        # —— 原来只认 is_staff，漏了 is_superuser 与 role=ADMIN。
        # ⚠️ 这里**刻意不用能力判定**：它是对象级约束（防越权挂靠），不是"内容维护权限"。
        # 换成 has_capability(CONTENT) 会让信息编辑员能把反馈挂到别人的识别记录上，
        # 那是权限放大而不是收敛。
        detection = attrs.get('detection')
        request = self.context.get('request')
        if detection is not None and request is not None:
            user = getattr(request, 'user', None)
            if detection.user_id != getattr(user, 'id', None) and not is_full_admin(user):
                raise serializers.ValidationError(
                    {'detection_id': ['只能关联你自己的识别记录']}
                )
        return attrs


# 行业新闻序列化器
class NewsSerializer(serializers.ModelSerializer):  # 定义行业新闻序列化器
    author_name = serializers.ReadOnlyField(source='author.username')  # 定义作者名字段为只读
    image_url = serializers.SerializerMethodField()  # 定义图片URL字段为方法字段
    created_at_formatted = serializers.SerializerMethodField()  # 定义格式化创建时间字段为方法字段
    image = serializers.ImageField(required=False, allow_null=True)  # 添加image字段用于文件上传
    tags = serializers.CharField(required=False, allow_blank=True)  # 添加tags字段
    clear_image = serializers.BooleanField(required=False, write_only=True, default=False)  # 置 true 表示移除封面图
    # 第 38 批：定时发布状态（前端用来显示"定时"角标）
    is_pending_schedule = serializers.BooleanField(read_only=True)

    class Meta:  # 定义元数据
        model = News  # 关联行业新闻模型
        fields = [  # 包含的字段
            'id', 'title', 'title_en', 'content', 'content_en',
            'image', 'image_url', 'source', 'source_en', 'author_name',
            'is_published', 'published_at', 'is_pending_schedule',
            'created_at', 'created_at_formatted', 'updated_at',
            'category', 'tags', 'clear_image'
        ]
        read_only_fields = ['author', 'created_at', 'updated_at']  # 只读字段

    def get_image_url(self, obj):  # 定义获取图片URL方法
        if hasattr(obj, 'image') and obj.image:  # 检查图片是否存在
            try:
                if hasattr(obj.image, 'url') and obj.image.url:  # 检查是否有url属性且不为空
                    request = self.context.get('request')  # 获取请求对象
                    if request is not None:  # 检查请求对象是否存在
                        # 构建完整URL并添加时间戳防止缓存
                        url = request.build_absolute_uri(obj.image.url)
                        return f"{url}?t={int(time.time())}"
                    # 如果没有request对象，尝试返回相对URL
                    return obj.image.url
            except Exception as e:
                logger.warning("获取图片 URL 失败: %s", e)
                return None
        return None  # 返回空值

    def get_created_at_formatted(self, obj):  # 定义获取格式化创建时间方法
        if hasattr(obj, 'created_at') and obj.created_at:  # 检查created_at是否存在
            return obj.created_at.strftime('%Y-%m-%d %H:%M')  # 返回格式化时间
        return None  # 返回空值

    def validate_title(self, value):
        """
        标题去空格，并拒绝"同标题重复建档"。

        背景（真实数据）：`News.title` 上没有唯一约束，库里曾出现两条
        **标题与正文逐字节相同**的记录（id=25 已下架、id=27 仍已发布）。
        管理员下架了其中一条，用户在列表里看到的却是另一条，
        表现为"下架了用户还能看见"——排查时极容易被误判成发布状态过滤失效。

        这里在写入层拦一道：新建/改名时若已存在同标题（忽略大小写）记录，
        直接返回 400 并给出可操作的提示，从源头避免再产生重复新闻。
        编辑时排除自身，因此"只改正文不改标题"不会误报。
        """
        title = (value or '').strip()
        if not title:
            raise serializers.ValidationError('新闻标题不能为空')

        # 编辑时若标题没变，直接放行。
        # 原因：库里若已存在同标题的历史重复记录（如 id=25/27），
        # "只改正文/发布状态、不动标题"的编辑会被下面的查重拦成 400
        # —— 等于历史重复数据永远改不了，管理员点保存只会看到"保存失败"。
        # 保持标题不变并不产生新的重复，所以这里直接返回。
        if self.instance is not None:
            current = (self.instance.title or '').strip()
            if title.lower() == current.lower():
                return title

        queryset = News.objects.filter(title__iexact=title)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)

        existed = queryset.first()
        if existed is not None:
            raise serializers.ValidationError(
                f'已存在同标题的新闻（ID: {existed.id}，'
                f'{"已发布" if existed.is_published else "未发布"}）。'
                '请直接编辑该条记录，或改用不同的标题。'
            )
        return title

    def create(self, validated_data):
        """创建新闻（图片由 ModelSerializer 默认逻辑写入）"""
        validated_data.pop('clear_image', None)

        # 处理tags字段（兼容传入数组的情况）
        tags = validated_data.get('tags')
        if tags and isinstance(tags, list):
            validated_data['tags'] = ','.join(tags)

        return super().create(validated_data)

    def update(self, instance, validated_data):
        """
        更新新闻

        注意：DRF 在 HTML 表单提交时会把空值 image='' 归一化成 None，
        因此不能用 `image == ''` 判断“是否要删除封面图”。
        这里统一处理三种情况：显式移除（clear_image / image=None）、替换、保持不变。
        """
        clear_image = validated_data.pop('clear_image', False)
        has_image_field = 'image' in validated_data
        image = validated_data.pop('image', None)

        # 处理tags字段（兼容传入数组的情况）
        if 'tags' in validated_data and isinstance(validated_data['tags'], list):
            validated_data['tags'] = ','.join(validated_data['tags'])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        should_clear = clear_image or (has_image_field and image is None)
        if should_clear:
            if instance.image:
                instance.image.delete(save=False)
            instance.image = None
        elif image is not None:
            if instance.image:
                instance.image.delete(save=False)
            instance.image = image

        instance.save()
        return instance


class PostListSerializer(serializers.ModelSerializer):
    """帖子列表序列化器"""
    author_name = serializers.ReadOnlyField(source='author.username')
    author_avatar = serializers.SerializerMethodField()
    board_name = serializers.ReadOnlyField(source='board.name')
    created_at_formatted = serializers.SerializerMethodField()
    updated_at_formatted = serializers.SerializerMethodField()
    comment_count = serializers.IntegerField(read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    view_count = serializers.IntegerField(read_only=True)
    is_pinned = serializers.BooleanField(read_only=True)
    is_essence = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Post
        fields = [
            'id', 'title', 'content', 'author', 'author_name', 'author_avatar',
            'board', 'board_name', 'status', 'status_display', 'view_count',
            'like_count', 'comment_count', 'is_pinned', 'is_essence',
            'created_at', 'created_at_formatted', 'updated_at', 'updated_at_formatted'
        ]
        read_only_fields = ['author', 'created_at', 'updated_at']
    
    def get_author_avatar(self, obj):
        """获取作者头像"""
        # 这里可以根据需要返回用户头像的URL
        # 例如：return obj.author.avatar.url if obj.author.avatar else None
        return None
    
    def get_created_at_formatted(self, obj):
        """格式化创建时间"""
        return obj.created_at.strftime('%Y-%m-%d %H:%M')
    
    def get_updated_at_formatted(self, obj):
        """格式化更新时间"""
        return obj.updated_at.strftime('%Y-%m-%d %H:%M') if obj.updated_at else ''

class SensitiveWordSerializer(serializers.ModelSerializer):
    """
    敏感词（第 38 批）

    第 135 批：加 `word_en`（**英文对照，只用于显示**）。词条本身是被拦截的字面串，
    中文词库在英文界面下就是一串中文，英文管理员看不出拦的是什么 —— 给它一句英文说法。
    ⚠️ 匹配只看 `word`（见 api/sensitive.py），`word_en` 不参与拦截。
    """
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = SensitiveWord
        fields = ['id', 'word', 'word_en', 'category', 'category_display',
                  'is_active', 'note', 'created_at']
        read_only_fields = ['created_at', 'category_display']

    def validate_word(self, value):
        word = (value or '').strip()
        if not word:
            raise serializers.ValidationError('敏感词不能为空')
        return word

    def validate_word_en(self, value):
        return (value or '').strip()
