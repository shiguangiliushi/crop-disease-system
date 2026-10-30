from django.db import models  # 导入Django模型模块
from django.conf import settings  # 导入Django配置模块
from django.contrib.auth import get_user_model  # 导入获取用户模型的函数
from django.utils import timezone  # 导入时区相关工具

# 第 85 批：用户内容的英文译文元数据基类（论坛帖子/评论 与 意见反馈 共用）
# 定义在 models_i18n.py：反馈在 models.py 里，跨模块 import 模型文件容易出现
# "谁先加载"的隐式依赖，抽出来两边都只依赖那一个模块。
from .models_i18n import TranslatableContentMixin  # noqa: F401

User = get_user_model()  # 获取当前项目的用户模型


class ActivePostManager(models.Manager):
    """
    未删除的帖子（第 91 批）

    背景：帖子的"删除"此前是**硬删除**，而 `Comment.post` / `Like.post` / `Favorite.post`
    都是 `CASCADE` —— 管理员删一条帖子，会**不可恢复地**连带删掉别人写的所有评论与点赞
    （评论早就是软删除，只有帖子不是，口径不一致）。

    现在帖子也走软删除（`is_deleted=True`），于是"哪些帖子算存在"这件事必须有个统一口径，
    否则漏掉一处就会出现"删了还在列表里"或"删了详情却还能打开"。
    统一用 `Post.active`，别再手写 `.filter(is_deleted=False)`。
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class ForumBoard(models.Model):
    """论坛版块"""
    name = models.CharField('版块名称', max_length=50)  # 版块名称字段，最大长度50字符
    description = models.TextField('版块描述', blank=True)  # 版块描述字段，允许为空
    # 第 72 批：版块是管理员维护的内容数据，英文界面下需要英文名与说明
    name_en = models.CharField('版块名称（英文）', max_length=50, blank=True, default='')
    description_en = models.TextField('版块描述（英文）', blank=True, default='')
    icon = models.CharField('图标', max_length=50, default='forum')  # 版块图标字段，默认值为'forum'
    order = models.PositiveIntegerField('排序', default=0)  # 排序字段，正整数，默认值为0
    is_active = models.BooleanField('是否启用', default=True)  # 是否启用字段，布尔值，默认启用
    post_count = models.PositiveIntegerField('帖子总数', default=0)  # 帖子总数统计字段
    today_posts = models.PositiveIntegerField('今日发帖数', default=0)  # 今日发帖数统计字段
    last_updated_date = models.DateField('最后更新日期', auto_now=True)  # 最后更新日期字段，自动设置为当前日期
    created_at = models.DateTimeField('创建时间', auto_now_add=True)  # 创建时间字段，自动设置为创建时间
    updated_at = models.DateTimeField('更新时间', auto_now=True)  # 更新时间字段，自动设置为更新时间

    class Meta:
        verbose_name = '论坛版块'  # 单数名称
        verbose_name_plural = verbose_name  # 复数名称（与单数相同）
        ordering = ['order', '-created_at']  # 默认排序：先按order升序，再按创建时间降序

    def __str__(self):
        return self.name  # 返回版块名称作为字符串表示

    def update_post_count(self):
        """更新今日发帖数"""
        today = timezone.localdate()  # 获取当前日期

        # 如果最后更新日期不是今天，重置计数器
        if self.last_updated_date != today:
            self.today_posts = 0  # 重置今日发帖数
            self.last_updated_date = today  # 更新最后更新日期

        # 增加今日发帖数
        self.today_posts += 1  # 今日发帖数加1
        self.save(update_fields=['today_posts', 'last_updated_date'])  # 保存更新字段

    def recompute_post_count(self, *, save: bool = True) -> int:
        """按实际帖子数**重算** `post_count`（第 213 批）。

        ## 为什么需要它

        `post_count` 是**冗余缓存字段**：发帖时 `F('post_count') + 1`、删帖时 `- 1`
        （见本文件 `Post.save` / 软删除路径）。任何**绕过 `save()`** 的操作
        —— 批量删、数据导入、直接改库、历史迁移 —— 都会让它单向漂移。
        实测本机已漂到 **239**，而真实只有 **7** 条。

        接口层已改为实时统计（`ForumBoardSerializer.get_post_count`），
        所以前端看不到错数；但 **Django admin 与任何直读该字段的地方**仍会显示。
        这个方法用于把缓存值拉回真实值。

        ⚠️ 只**重算**，不删改任何帖子 —— 计数是派生数据，重算永远是安全的。
        """
        real = self.posts.filter(is_deleted=False).count()
        if save and self.post_count != real:
            ForumBoard.objects.filter(pk=self.pk).update(post_count=real)
            self.post_count = real
        return real


class Post(TranslatableContentMixin):
    """帖子"""
    STATUS_CHOICES = (  # 帖子状态选项
        ('draft', '草稿'),  # 草稿状态
        ('pending', '待审核'),  # 第 38 批：待审核（普通用户发帖先进这里，审核通过才对他人可见）
        ('published', '已发布'),  # 已发布状态
        ('hidden', '隐藏'),  # 隐藏状态
    )

    title = models.CharField('标题', max_length=200)  # 帖子标题字段，最大长度200字符
    # 第 85 批：英文标题/正文（人工填写或机器翻译，见 TranslatableContentMixin）
    title_en = models.CharField('标题（英文）', max_length=200, blank=True, default='')
    content = models.TextField('内容')  # 帖子内容字段，文本类型
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name='forum_posts')  # 作者外键，级联删除
    board = models.ForeignKey(ForumBoard, on_delete=models.CASCADE, related_name='posts')  # 所属版块外键，级联删除
    status = models.CharField('状态', max_length=10, choices=STATUS_CHOICES, default='published')  # 状态字段，使用状态选项
    view_count = models.PositiveIntegerField('浏览次数', default=0)  # 浏览次数统计字段
    like_count = models.PositiveIntegerField('点赞数', default=0)  # 点赞数统计字段
    comment_count = models.PositiveIntegerField('评论数', default=0)  # 评论数统计字段
    last_comment_at = models.DateTimeField('最后评论时间', null=True, blank=True)  # 最后评论时间字段，允许为空
    is_pinned = models.BooleanField('是否置顶', default=False)  # 是否置顶字段，布尔值，默认不置顶
    is_essence = models.BooleanField('是否精华', default=False)  # 是否精华字段，布尔值，默认非精华
    # 第 91 批：软删除。删帖不再 `DELETE` 掉整行 —— 见 ActivePostManager 的说明。
    is_deleted = models.BooleanField('是否删除', default=False, db_index=True)
    deleted_at = models.DateTimeField('删除时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)  # 创建时间字段，自动设置为创建时间
    updated_at = models.DateTimeField('更新时间', auto_now=True)  # 更新时间字段，自动设置为更新时间

    objects = models.Manager()  # 默认管理器：**含**已删除（后台/备份/清理等场景需要）
    active = ActivePostManager()  # 业务口径：只含未删除

    # 第 168 批：病害标签（评审意见："不能给帖子打『苹果黑星病』这种标签，
    # 后期没法按病害聚合讨论"）。
    #
    # 为什么指向 PestInfo 而不是存一串名字：
    #   · 病害名有中英两份（`name` / `name_en`），存名字就得决定存哪个，
    #     而且改名/翻译更新之后老帖子就"对不上"了；
    #   · 指向词条才能做聚合（"这个病大家都遇到过什么"），也才能让词条页反向列出相关讨论。
    # 用字符串引用模型：Post 在 models_forum.py，PestInfo 在 models.py，
    # 直接 import 会绕成环形依赖（models.py 里也有引用论坛模型的地方）。
    pests = models.ManyToManyField(
        'api.PestInfo',
        blank=True,
        related_name='forum_posts',
        verbose_name='相关病害',
        help_text='这篇帖子讨论的病害（可多选，用于按病害聚合讨论）',
    )

    class Meta:
        verbose_name = '帖子'  # 单数名称
        verbose_name_plural = verbose_name  # 复数名称（与单数相同）
        ordering = ['-is_pinned', '-last_comment_at', '-created_at']  # 默认排序：先按置顶降序，再按最后评论时间降序，最后按创建时间降序

    def __str__(self):
        return self.title  # 返回帖子标题作为字符串表示

    def translation_source_texts(self):
        """第 85 批：标题与正文都参与指纹（改标题也要重译）"""
        return [self.title, self.content]

    @property
    def display_title_en(self):
        """英文标题的**兜底取值**：没有译文时回落中文标题（前端同款规则）"""
        return (self.title_en or '').strip() or self.title

    def update_comment_count(self):
        self.comment_count = self.comments.filter(is_deleted=False).count()  # 更新评论数为未删除评论的数量
        last_comment = self.comments.filter(is_deleted=False).order_by('-created_at').first()  # 获取最后一条未删除评论
        self.last_comment_at = last_comment.created_at if last_comment else None  # 设置最后评论时间
        self.save(update_fields=['comment_count', 'last_comment_at'])  # 保存更新字段

    def soft_delete(self):
        """
        软删除（第 91 批）

        只把标题/正文替换成占位文案并打上标记，**不删任何关联行**：
        评论、回复、点赞、收藏、@通知全部留在库里（只是帖子本身不再可见）。

        为什么不像评论那样保留原内容：帖子的软删除只允许**作者本人或管理员**调用
        （见 `CanDeletePost`），删除是明确意图；正文留着会让"删过的帖子"在数据库里
        继续保存用户内容，与"用户要求删除"的预期不符。标题同样要清掉 ——
        很多接口（收藏列表、用户资料页的"我的帖子"）会单独取标题。
        """
        self.title = '[已删除]'
        self.title_en = ''
        self.content = '[该帖子已被删除]'
        self.content_en = ''
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.is_pinned = False
        self.is_essence = False
        self.save(update_fields=[
            'title', 'title_en', 'content', 'content_en',
            'is_deleted', 'deleted_at', 'is_pinned', 'is_essence', 'updated_at',
        ])

    def save(self, *args, **kwargs):
        # 第 256 批：保存时净化富文本（不再只依赖前端渲染前净化）
        from .utils_html import sanitize_html as _sanitize_html
        if getattr(self, "content", None):
            self.content = _sanitize_html(self.content)
        from django.db.models import F  # 导入F表达式用于数据库操作
        from django.utils import timezone  # 导入时区相关工具
        import logging  # 导入日志模块

        logger = logging.getLogger(__name__)  # 获取日志记录器
        is_new = self._state.adding  # 检查是否是新建对象

        # 保存帖子
        super().save(*args, **kwargs)  # 调用父类保存方法

        if is_new and self.status == 'published':  # 如果是新帖子且状态为已发布
            # 使用 select_for_update 锁定版块记录，防止并发问题
            board = type(self.board).objects.select_for_update().get(pk=self.board.pk)  # 锁定版块记录
            now = timezone.now()  # 获取当前时间
            today = now.date()  # 获取当前日期

            logger.info(
                f"处理新帖子保存 - 帖子ID: {self.id}, 版块ID: {board.id}, 当前日期: {today}, 版块最后更新: {board.last_updated_date}")  # 记录日志

            # 使用原子操作更新版块统计信息
            if board.last_updated_date != today:  # 如果版块最后更新日期不是今天
                # 新的一天，重置今日发帖数
                board.today_posts = 1  # 重置今日发帖数为1
                board.last_updated_date = today  # 更新最后更新日期为今天
                logger.info(f"新版块日期 - 重置今日发帖数为1, 版块: {board.name}")  # 记录日志
            else:
                # 同一天，增加发帖数
                board.today_posts = board.today_posts + 1  # 今日发帖数加1
                logger.info(f"更新今日发帖数 - 版块: {board.name}, 新值: {board.today_posts + 1}")  # 记录日志

            # 更新总帖子数
            board.post_count = F('post_count') + 1  # 使用F表达式原子增加总帖子数

            try:
                board.save(update_fields=['post_count', 'today_posts', 'last_updated_date'])  # 保存版块更新
                # ⚠️ 第 107 批修：这里原来写 `总发帖: {board.post_count + 1}`，
                #    但 `board.post_count` 此时**就是 `F('post_count') + 1` 这个表达式对象**
                #    （上面刚赋的值），再加 1 只会打印成
                #    `F(post_count) + Value(1) + Value(1)` —— 日志里既看不出真实值，
                #    又容易让人以为"加了两次"。真实值要重新查库才知道，
                #    所以这里只报告"已更新"以及今日发帖数（那是普通整数，可直接打印）。
                logger.info(
                    "版块统计信息更新成功 - 版块: %s, 今日发帖: %s, 总发帖: (原子自增)",
                    board.name, board.today_posts,
                )
            except Exception as e:
                logger.error("更新版块统计信息失败 - 版块ID: %s, 错误: %s", board.id, e, exc_info=True)
                raise  # 重新抛出异常

    def delete(self, *args, **kwargs):
        """
        删除帖子时更新版块统计信息
        """
        from django.db.models import F  # 导入F表达式用于数据库操作
        from django.utils import timezone  # 导入时区相关工具
        import logging  # 导入日志模块

        logger = logging.getLogger(__name__)  # 获取日志记录器

        # 只在帖子已发布状态时更新统计
        if self.status == 'published':  # 如果帖子状态是已发布
            try:
                # 使用 select_for_update 锁定版块记录
                board = type(self.board).objects.select_for_update().get(pk=self.board.pk)  # 锁定版块记录
                now = timezone.now()  # 获取当前时间
                today = now.date()  # 获取当前日期

                logger.info(f"处理删除帖子 - 帖子ID: {self.id}, 版块ID: {board.id}")  # 记录日志

                # 更新总帖子数
                if board.post_count > 0:  # 如果总帖子数大于0
                    board.post_count = F('post_count') - 1  # 使用F表达式原子减少总帖子数

                # 如果是今天的帖子，更新今日发帖数
                if self.created_at.date() == today and board.today_posts > 0:  # 如果帖子是今天创建且今日发帖数大于0
                    board.today_posts = F('today_posts') - 1  # 使用F表达式原子减少今日发帖数

                # 保存版块更新
                update_fields = ['post_count']  # 需要更新的字段列表
                if self.created_at.date() == today:  # 如果帖子是今天创建
                    update_fields.append('today_posts')  # 添加今日发帖数字段到更新列表

                board.save(update_fields=update_fields)  # 保存版块更新
                logger.info(f"版块统计信息更新成功 - 版块: {board.name}, 总发帖: {board.post_count - 1}")  # 记录日志

            except Exception as e:
                logger.error(f"更新版块统计信息失败 - 版块ID: {getattr(board, 'id', 'unknown')}, 错误: {str(e)}",
                             exc_info=True)  # 记录错误日志

        # 调用父类的删除方法
        return super().delete(*args, **kwargs)  # 调用父类删除方法


class Comment(TranslatableContentMixin):
    """评论"""
    content = models.TextField('内容')  # 评论内容字段，文本类型
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name='forum_comments')  # 作者外键，级联删除
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')  # 所属帖子外键，级联删除
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True,
                               related_name='replies')  # 父评论外键，允许为空，用于回复
    reply_to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, 
                                    null=True, blank=True, related_name='replied_by_comments',
                                    verbose_name='回复给')  # 回复给哪个用户，允许为空
    is_deleted = models.BooleanField('是否删除', default=False)  # 是否删除字段，布尔值，默认未删除
    # 第 152 批：软删除时把**原文**转存到这里 —— 否则"删除"就是不可恢复的
    # （第 17 批的做法是直接把 content 覆盖成 `[已删除]`）。
    # 控制台的「恢复」按钮靠它把内容放回去；本批之前删掉的评论这里是空的（无法恢复）。
    original_content = models.TextField('删除前的原文', blank=True, default='')
    # 谁删的：作者本人删 vs 版主删，恢复前应当让管理员知道（作者的心意不该被随手推翻）
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deleted_comments', verbose_name='删除人',
    )
    like_count = models.PositiveIntegerField('点赞数', default=0)  # 点赞数统计字段
    created_at = models.DateTimeField('创建时间', auto_now_add=True)  # 创建时间字段，自动设置为创建时间
    updated_at = models.DateTimeField('更新时间', auto_now=True)  # 更新时间字段，自动设置为更新时间

    class Meta:
        verbose_name = '评论'  # 单数名称
        verbose_name_plural = verbose_name  # 复数名称（与单数相同）
        ordering = ['created_at']  # 默认排序：按创建时间升序

    def __str__(self):
        return f"{self.author.username}的评论"  # 返回评论作者的用户名作为字符串表示

    def translation_source_texts(self):
        """第 85 批：评论只有正文需要翻译"""
        return [self.content]

    def save(self, *args, **kwargs):
        # 第 256 批：保存时净化富文本（不再只依赖前端渲染前净化）
        from .utils_html import sanitize_html as _sanitize_html
        if getattr(self, "content", None):
            self.content = _sanitize_html(self.content)
        super().save(*args, **kwargs)  # 调用父类保存方法
        if not self.is_deleted and not self.parent:  # 如果评论未删除且不是回复评论
            self.post.update_comment_count()  # 更新帖子的评论计数

    def delete(self, *args, **kwargs):
        """删除评论后刷新所属帖子的评论数

        第 17 批补充：此前只有 save() 里维护 post.comment_count，而 save() 的条件是
        「未删除且不是回复」——
          - 软删除（is_deleted=True 后 save）会**跳过**该分支；
          - 硬删除（instance.delete()）根本不经过 save()。
        结果是删评论后帖子上的「评论数」一直偏高（数据库中已实际出现 4 个帖子存在
        这种偏差，属长期积累）。这里显式重算一次。
        """
        post_id = self.post_id  # 删除前先取出外键，避免删除后取不到
        result = super().delete(*args, **kwargs)
        post = Post.objects.filter(pk=post_id).first()  # 帖子可能已被级联删除
        if post:
            post.update_comment_count()
        return result


class Like(models.Model):
    """点赞"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='forum_likes')  # 用户外键，级联删除
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes', null=True, blank=True)  # 帖子外键，允许为空
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='likes', null=True,
                                blank=True)  # 评论外键，允许为空
    created_at = models.DateTimeField('创建时间', auto_now_add=True)  # 创建时间字段，自动设置为创建时间

    class Meta:
        verbose_name = '点赞'  # 单数名称
        verbose_name_plural = verbose_name  # 复数名称（与单数相同）
        unique_together = [  # 唯一性约束
            ['user', 'post'],  # 用户和帖子的组合必须唯一
            ['user', 'comment'],  # 用户和评论的组合必须唯一
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # 调用父类保存方法
        # 更新点赞数
        #
        # 第 16 批修复：这里原来写的是 self.post.likes.count() / self.comment.likes.count()。
        # 反向管理器在**实例来自带 prefetch_related('likes') 的查询集**时会直接读
        # 预取缓存（Django 的 QuerySet.count() 遇到已填充的 _result_cache 会直接返回
        # len(缓存)，不再查库）。评论点赞接口取的评论对象正好来自
        # CommentViewSet.get_queryset() 的 prefetch_related('likes')，缓存里是点赞前的
        # 空列表 → 计数恒为 0，表现为「点赞成功但点赞数一直是 0，刷新后仍为 0」。
        # 改为显式查询计数，绕开预取缓存。
        if self.post_id:  # 如果是给帖子点赞
            post = self.post
            post.like_count = Like.objects.filter(post_id=self.post_id).count()
            post.save(update_fields=['like_count'])  # 保存帖子更新
        elif self.comment_id:  # 如果是给评论点赞
            comment = self.comment
            comment.like_count = Like.objects.filter(comment_id=self.comment_id).count()
            comment.save(update_fields=['like_count'])  # 保存评论更新

    def delete(self, *args, **kwargs):
        # 删除时更新点赞数
        post_id = self.post_id  # 保存帖子外键
        comment_id = self.comment_id  # 保存评论外键
        super().delete(*args, **kwargs)  # 调用父类删除方法
        # 同 save()：显式计数，避免命中 prefetch 缓存导致计数不更新
        # （用 filter().first() 而非 get()：级联删除等场景下目标可能已不存在）
        if post_id:  # 如果是帖子点赞
            post = Post.objects.filter(pk=post_id).first()
            if post:
                post.like_count = Like.objects.filter(post_id=post_id).count()
                post.save(update_fields=['like_count'])  # 保存帖子更新
        elif comment_id:  # 如果是评论点赞
            comment = Comment.objects.filter(pk=comment_id).first()
            if comment:
                comment.like_count = Like.objects.filter(comment_id=comment_id).count()
                comment.save(update_fields=['like_count'])  # 保存评论更新


class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_favorites')  # 用户外键，级联删除
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='favorited_by')  # 帖子外键，级联删除
    created_at = models.DateTimeField(auto_now_add=True)  # 创建时间字段，自动设置为创建时间

    class Meta:
        unique_together = ('user', 'post')  # 用户和帖子的组合必须唯一
        ordering = ['-created_at']  # 默认排序：按创建时间降序
        verbose_name = '论坛收藏'  # 单数名称
        verbose_name_plural = verbose_name  # 复数名称（与单数相同）

    def __str__(self):
        return f'{self.user.username}收藏了{self.post.title}'  # 返回收藏信息作为字符串表示