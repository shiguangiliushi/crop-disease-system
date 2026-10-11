from rest_framework import serializers  # 导入DRF序列化器模块
from django.contrib.auth import get_user_model  # 导入获取用户模型的函数
from .models_forum import ForumBoard, Post, Comment, Like, Favorite  # 导入论坛相关模型
from .models import CustomUser, PestInfo  # 导入自定义用户模型 + 第 168 批：病害标签
import logging

logger = logging.getLogger(__name__)  # 第 168 批：失效标签 id 留一条 warning
# 头像绝对地址的统一实现（第 23 批加的 CustomUser.avatar，这里复用以避免重复逻辑）
from .serializers import _user_avatar_url


class UserSimpleSerializer(serializers.ModelSerializer):  # 定义用户简单信息序列化器
    """用户简单信息序列化器

    第 25 批补充 ``avatar``：论坛各处模板早就在用 ``post.author.avatar`` /
    ``comment.author.avatar``，但当时模型没有头像字段、这里也不返回 →
    永远拿不到值（只能靠首字母兜底）。第 23 批加了真实头像后，这里同步返回。
    """

    avatar = serializers.SerializerMethodField()

    class Meta:  # 定义元数据
        model = CustomUser  # 关联用户模型
        fields = ['id', 'username', 'avatar']  # 包含的字段
        read_only_fields = fields  # 所有字段都是只读的

    def get_avatar(self, obj):
        return _user_avatar_url(obj, self.context.get('request'))


class LikeUserSerializer(serializers.ModelSerializer):  # 点赞者名单（第 25 批新增）
    """点赞者序列化器：用于「谁点赞了」名单"""

    user = UserSimpleSerializer(read_only=True)

    class Meta:
        model = Like
        fields = ['id', 'user', 'created_at']
        read_only_fields = fields


class ForumBoardSerializer(serializers.ModelSerializer):  # 定义版块序列化器
    """版块序列化器"""

    class Meta:  # 定义元数据
        model = ForumBoard  # 关联版块模型
        fields = [  # 包含的字段
            'id', 'name', 'name_en', 'description', 'description_en', 'icon', 'order',
            'is_active', 'created_at', 'post_count', 'today_posts',
            'last_updated_date'
        ]
        read_only_fields = ['created_at', 'post_count', 'today_posts', 'last_updated_date']  # 只读字段


class PestTagSerializer(serializers.ModelSerializer):
    """
    帖子上的病害标签（只读，第 168 批）

    只回渲染标签需要的字段：中文名 / 英文名 / 英文标识（用来链接到
    `/pests/<english_identifier>` 词条页）。症状、防治建议整篇不进帖子接口 ——
    标签就是一排小胶囊，点进去才看词条。
    """

    class Meta:
        model = PestInfo
        fields = ['id', 'name', 'name_en', 'english_identifier', 'crop_type', 'crop_type_en']


class CommentSerializer(serializers.ModelSerializer):  # 定义评论序列化器
    """评论序列化器

    第 16 批补齐（此前字段缺失导致前端「回复」功能整块不可用）：
    - ``reply_count``：该评论下的未删除回复数。前端模板用
      ``v-if="comment.reply_count > comment.replies.length"`` 决定是否显示
      「加载更多回复」，此前后端从不返回该字段 → 按钮永远不渲染，回复列表也就
      无法展开。
    - ``reply_to``：回复目标用户（``reply_to_user``）。此前只存不返回，
      界面上「回复 @某人」的信息完全丢失。
    - ``parent``：父评论 id，便于前端判断层级。

    第 85 批新增英文译文相关字段（见 models_forum.TranslatableContentMixin）：
    - ``content_en``：英文译文（人工或机器翻译，可为空）；
    - ``translation_source`` / ``translation_stale``：前端据此显示「未翻译」
      「原文已更新」提示，而不是把中文当成英文展示。
    """
    author = UserSimpleSerializer(read_only=True)  # 作者字段使用简单用户序列化器
    is_liked = serializers.SerializerMethodField()  # 是否点赞字段为方法字段
    reply_to = UserSimpleSerializer(read_only=True, source='reply_to_user')  # 回复目标用户
    reply_count = serializers.SerializerMethodField()  # 回复数量（实时统计）
    # 第 85 批：译文状态（只读，前端用来决定是否显示"未翻译/已过期"角标）
    translation_stale = serializers.BooleanField(read_only=True)
    translation_source = serializers.CharField(read_only=True)

    class Meta:  # 定义元数据
        model = Comment  # 关联评论模型
        fields = [  # 包含的字段
            'id', 'content', 'content_en', 'author', 'like_count', 'is_liked',
            'created_at', 'updated_at', 'is_deleted',
            'parent', 'reply_to', 'reply_count',
            'translation_stale', 'translation_source',
        ]
        read_only_fields = [  # 只读字段
            'author', 'like_count', 'created_at', 'updated_at', 'is_deleted',
            'parent', 'reply_to', 'reply_count',
            'translation_stale', 'translation_source'
        ]

    def get_is_liked(self, obj):  # 定义获取是否点赞方法
        user = self.context['request'].user  # 获取当前用户
        if user.is_authenticated:  # 检查用户是否认证
            return obj.likes.filter(user=user).exists()  # 返回用户是否点赞
        return False  # 未认证用户返回False

    def get_reply_count(self, obj):  # 定义获取回复数方法
        # 列表查询会对该字段做 annotate，避免 N+1；没有注解时退回一次 count 查询
        annotated = getattr(obj, 'reply_count_annotated', None)
        if annotated is not None:
            return annotated
        return obj.replies.filter(is_deleted=False).count()


class UserCommentSerializer(CommentSerializer):
    """
    用户评论（用户资料页的「评论」标签用）—— 第 25 批新增

    需求：在用户资料里点开一条评论，要能看出**这条评论是在哪里发的**。
    因此额外带上所属帖子的 id / 标题 / 版块名。
    （不直接改 CommentSerializer：帖子详情页里每条评论都再取一次 post 会变成 N+1。）
    """

    post_id = serializers.IntegerField(read_only=True)
    post_title = serializers.CharField(source='post.title', read_only=True)
    # 第 85 批：帖子英文标题 —— 英文界面下资料页的"来自《xxx》"不再回落中文标题
    post_title_en = serializers.CharField(source='post.title_en', read_only=True)
    board_id = serializers.IntegerField(source='post.board.id', read_only=True)
    board_name = serializers.CharField(source='post.board.name', read_only=True)
    # 第 72 批：版块英文名，英文界面下资料页不再显示中文版块名
    board_name_en = serializers.CharField(source='post.board.name_en', read_only=True)

    class Meta(CommentSerializer.Meta):
        fields = CommentSerializer.Meta.fields + [
            'post_id', 'post_title', 'post_title_en', 'board_id', 'board_name', 'board_name_en',
        ]
        read_only_fields = CommentSerializer.Meta.read_only_fields + [
            'post_id', 'post_title', 'post_title_en', 'board_id', 'board_name', 'board_name_en',
        ]


class PostListSerializer(serializers.ModelSerializer):  # 定义帖子列表序列化器
    """帖子列表序列化器

    第 24 批补齐三个字段（此前导致"草稿其实是公开发布 / 收藏状态看不到"）：
    - ``status``（只读）：让前端能给草稿打角标；
    - ``is_draft``（只写）：前端一直发的就是这个字段，而序列化器里**没有它**，
      DRF 会静默忽略未声明的字段 —— 于是"保存草稿"实际按模型默认值建成了
      **已发布**帖子（配合前端每 30 秒的自动保存，会往论坛里灌半成品已发布帖）。
    - ``is_favorited``：当前用户是否收藏了该帖，供收藏按钮显示实心/空心。
    """
    author = UserSimpleSerializer(read_only=True)  # 作者字段使用简单用户序列化器
    board = ForumBoardSerializer(read_only=True)  # 版块字段使用版块序列化器
    board_id = serializers.PrimaryKeyRelatedField(  # 版块ID字段为主键关联字段
        queryset=ForumBoard.objects.filter(is_active=True),  # 查询集为活跃版块
        write_only=True,  # 只写字段
        source='board'  # 数据源为版块
    )
    is_liked = serializers.SerializerMethodField()  # 是否点赞字段为方法字段
    is_favorited = serializers.SerializerMethodField()  # 是否收藏字段为方法字段
    is_draft = serializers.BooleanField(write_only=True, required=False)  # 只写：草稿开关
    # 第 168 批：病害标签（评审意见：帖子不能打「苹果黑星病」这种标签，就没法按病害聚合讨论）
    #   · pest_ids（只写）：前端提交 [12, 34] 这样的词条 id；
    #   · pests（只读）：回 [{id, name, name_en, english_identifier, ...}] 供渲染标签。
    # 两个字段分开是刻意的：写只需要 id，读需要名字（否则前端还得再查一次）。
    pest_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False,
    )
    pests = PestTagSerializer(many=True, read_only=True)
    # 第 85 批：译文状态（只读）—— 前端据此显示"未翻译 / 原文已更新"角标
    translation_stale = serializers.BooleanField(read_only=True)
    translation_source = serializers.CharField(read_only=True)

    class Meta:  # 定义元数据
        model = Post  # 关联帖子模型
        fields = [  # 包含的字段
            'id', 'title', 'title_en', 'content', 'content_en', 'author', 'board', 'board_id',
            'view_count', 'like_count', 'comment_count', 'is_liked', 'is_favorited',
            'is_pinned', 'is_essence', 'status', 'is_draft', 'created_at', 'updated_at',
            'translation_stale', 'translation_source',
            'pests', 'pest_ids',   # 第 168 批：病害标签
        ]
        read_only_fields = [  # 只读字段
            'author', 'view_count', 'like_count', 'comment_count',
            'status', 'created_at', 'updated_at',
            'translation_stale', 'translation_source'
        ]

    def get_is_liked(self, obj):  # 定义获取是否点赞方法
        user = self.context['request'].user  # 获取当前用户
        if user.is_authenticated:  # 检查用户是否认证
            return obj.likes.filter(user=user).exists()  # 返回用户是否点赞
        return False  # 未认证用户返回False

    def get_is_favorited(self, obj):
        # 列表查询会在 get_queryset 里 annotate('_is_favorited')，避免 N+1；
        # 没有注解时（详情页等）退回一次 exists 查询。
        annotated = getattr(obj, '_is_favorited', None)
        if annotated is not None:
            return bool(annotated)
        user = self.context['request'].user
        if user.is_authenticated:
            return Favorite.objects.filter(user=user, post_id=obj.pk).exists()
        return False

    def _apply_draft_flag(self, validated_data):
        """把前端的 is_draft 意图翻译成模型上的 status"""
        is_draft = validated_data.pop('is_draft', None)
        if is_draft is not None:
            validated_data['status'] = 'draft' if is_draft else 'published'

    @staticmethod
    def _strip_blank_english(validated_data):
        """第 85 批：空字符串的 `*_en` 视为"前端没填"，直接丢弃

        前端保存帖子时会把整个表单回传，`title_en` / `content_en` 很可能是空串。
        若照单写入，DRF 会把已有译文覆盖成空 —— 表现为"编辑一次帖子，英文就没了"。
        （这正是本批单测 `test_empty_english_in_payload_does_not_wipe_translation`
        抓到的真实缺陷：只"不标记为人工译文"是不够的，字段本身也不能被赋值。）
        """
        for key in ('title_en', 'content_en'):
            if key in validated_data and not str(validated_data.get(key) or '').strip():
                validated_data.pop(key)
        return validated_data

    def _mark_manual_translation(self, instance, validated_data):
        """第 85 批：作者/管理员**显式**提交的英文，按"人工译文"记账

        规则（与 services_translate 的"人工优先"配套）：
          · 只认**非空**的 `*_en`。前端保存帖子时会把整个表单回传，
            `title_en` 很可能是空串 —— 若把空串当成"人工译文"，会把已有的
            自动译文抹掉，所以空值一律忽略；
          · 只有标题与正文的英文**都**齐全时才算"整篇人工译文"
            （只填一半时留给自动翻译补另一半，不锁定）；
          · 标记后 `translation_hash` 记的是当前原文的指纹，原文日后被改动
            会被识别为 translation_stale，而不会被自动翻译悄悄覆盖。
        """
        title_en = (validated_data.get('title_en') or '').strip()
        content_en = (validated_data.get('content_en') or '').strip()
        if not title_en and not content_en:
            return
        if not ((instance.title_en or '').strip() and (instance.content_en or '').strip()):
            return
        instance.mark_translated(instance.SOURCE_MANUAL)
        instance.save(update_fields=['translation_hash', 'translation_source', 'translated_at'])

    def _pop_pest_ids(self, validated_data):
        """
        取出病害标签 id 列表（第 168 批）

        `pest_ids` 是我们自己声明的 ListField，M2M 不能靠 ModelSerializer 自动落库，
        所以在这里 pop 出来、保存实例后再 ``.set()``。

        ⚠️ **只保留真实存在的词条 id**：词条被删掉后，老帖子的编辑页还会带着那个 id
        提交上来 —— 直接 400 会把用户卡在"怎么改都保存不了"的死循环里，
        悄悄丢掉失效标签更合理（同时留一条 warning 便于排查）。
        """
        ids = validated_data.pop('pest_ids', None)
        if ids is None:
            return None
        cleaned = []
        for raw in ids:
            try:
                cleaned.append(int(raw))
            except (TypeError, ValueError):
                continue
        if not cleaned:
            return []
        existing = set(PestInfo.objects.filter(id__in=cleaned).values_list('id', flat=True))
        missing = sorted(set(cleaned) - existing)
        if missing:
            logger.warning('帖子病害标签里有不存在的词条 id，已忽略: %s', missing)
        ordered, seen = [], set()
        for pid in cleaned:
            if pid in existing and pid not in seen:
                seen.add(pid)
                ordered.append(pid)
        return ordered

    def create(self, validated_data):
        self._apply_draft_flag(validated_data)
        self._strip_blank_english(validated_data)
        pest_ids = self._pop_pest_ids(validated_data)
        instance = super().create(validated_data)
        self._mark_manual_translation(instance, validated_data)
        if pest_ids is not None:
            instance.pests.set(pest_ids)
        return instance

    def update(self, instance, validated_data):
        self._apply_draft_flag(validated_data)
        self._strip_blank_english(validated_data)
        pest_ids = self._pop_pest_ids(validated_data)
        instance = super().update(instance, validated_data)
        self._mark_manual_translation(instance, validated_data)
        if pest_ids is not None:
            instance.pests.set(pest_ids)
        return instance


class PostDetailSerializer(PostListSerializer):  # 定义帖子详情序列化器，继承自帖子列表序列化器
    """帖子详情序列化器"""
    comments = serializers.SerializerMethodField()  # 评论字段为方法字段

    class Meta(PostListSerializer.Meta):  # 继承元数据
        fields = PostListSerializer.Meta.fields + ['comments']  # 添加评论字段
        read_only_fields = PostListSerializer.Meta.read_only_fields + ['comments']  # 添加评论字段为只读

    def get_comments(self, obj):  # 定义获取评论方法
        comments = obj.comments.filter(parent__isnull=True, is_deleted=False).order_by('created_at')  # 获取顶级评论
        return CommentSerializer(
            comments, 
            many=True, 
            context={**self.context, 'nested': False}  # 添加嵌套标记
        ).data  # 返回序列化数据


class CommentCreateSerializer(serializers.ModelSerializer):  # 定义评论创建序列化器
    """评论创建序列化器"""
    reply_to = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        required=False,
        write_only=True,
        source='reply_to_user'
    )

    class Meta:  # 定义元数据
        model = Comment  # 关联评论模型
        # 第 85 批：允许作者直接带上英文译文（content_en），留空则由机器翻译补
        fields = ['content', 'content_en', 'parent', 'reply_to']  # 包含的字段
        extra_kwargs = {  # 额外参数
            'parent': {'required': False},  # 父评论非必需
            'reply_to': {'required': False},  # 回复用户非必需
            'content_en': {'required': False, 'allow_blank': True},
        }

    def validate_parent(self, value):  # 验证父评论
        if value and value.post_id != self.context['post_id']:  # 检查父评论是否属于当前帖子
            raise serializers.ValidationError("回复的评论不属于该帖子")  # 抛出验证错误
        return value  # 返回值
        
    def create(self, validated_data):
        # 获取并移除reply_to_user（如果存在）
        reply_to_user = validated_data.pop('reply_to_user', None)
        
        # 创建评论实例
        comment = Comment.objects.create(
            content=validated_data.get('content'),
            # 第 85 批：作者可自带英文译文（人工），留空则交给自动翻译
            content_en=(validated_data.get('content_en') or '').strip(),
            author=self.context['request'].user,
            post_id=self.context['post_id'],
            parent=validated_data.get('parent'),
            reply_to_user=reply_to_user
        )

        # 第 85 批：带了非空英文译文 → 记成"人工译文"，自动翻译不会再覆盖它
        if (comment.content_en or '').strip():
            comment.mark_translated(comment.SOURCE_MANUAL)
            comment.save(update_fields=['translation_hash', 'translation_source', 'translated_at'])
        
        # 如果是回复评论且没有指定reply_to_user，则设置为父评论的作者
        if comment.parent and not comment.reply_to_user:
            comment.reply_to_user = comment.parent.author
            comment.save(update_fields=['reply_to_user'])
            
        return comment

    def update(self, instance, validated_data):
        """编辑评论：第 85 批 —— 作者带来的非空 content_en 记为人工译文，空串则丢弃"""
        if 'content_en' in validated_data and not str(validated_data.get('content_en') or '').strip():
            validated_data.pop('content_en')
        instance = super().update(instance, validated_data)
        if (validated_data.get('content_en') or '').strip():
            instance.mark_translated(instance.SOURCE_MANUAL)
            instance.save(update_fields=['translation_hash', 'translation_source', 'translated_at'])
        return instance


class LikeSerializer(serializers.ModelSerializer):  # 定义点赞序列化器
    """点赞序列化器"""

    class Meta:  # 定义元数据
        model = Like  # 关联点赞模型
        fields = '__all__'  # 包含所有字段
        read_only_fields = ['user', 'created_at']  # 只读字段
        extra_kwargs = {  # 额外参数
            'post': {'required': False},  # 帖子非必需
            'comment': {'required': False}  # 评论非必需
        }

    def validate(self, attrs):  # 验证方法
        if not (attrs.get('post') or attrs.get('comment')):  # 检查是否指定了帖子或评论
            raise serializers.ValidationError("必须指定帖子或评论")  # 抛出验证错误
        if attrs.get('post') and attrs.get('comment'):  # 检查是否同时指定了帖子和评论
            raise serializers.ValidationError("不能同时指定帖子和评论")  # 抛出验证错误
        return attrs  # 返回属性


class FavoriteSerializer(serializers.ModelSerializer):  # 定义收藏序列化器
    """收藏序列化器"""

    class Meta:  # 定义元数据
        model = Favorite  # 关联收藏模型
        fields = ['id', 'user', 'post', 'created_at']  # 包含的字段
        read_only_fields = ['user', 'created_at']  # 只读字段