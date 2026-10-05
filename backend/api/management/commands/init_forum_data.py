"""
初始化论坛演示数据（版块 + 示例帖子 / 评论 / 点赞）

**用途**：给人看演示、或本地开发时想有一点"看起来像真的"内容。
用 `Faker` 生成用户名与正文。

⚠️ 三个必须知道的点：
  1. **这是演示数据，不要在生产库上跑**。它会创建一批假用户与假帖子；
  2. 需要装 `Faker`（`requirements.txt` 里有，但它是"开发依赖"性质）；
  3. 版块的名字与顺序**是产品约定**（`ForumBoard`），
     `init_forum_boards.py` 只建版块、不造内容 —— 两个命令的分工别混。
"""
from django.core.management.base import BaseCommand  # 导入Django管理命令基类
from django.contrib.auth import get_user_model  # 导入获取用户模型函数
from django.utils import timezone  # 导入时区处理模块
from django.db import transaction  # 导入数据库事务模块
import random  # 导入随机数生成模块
from faker import Faker  # 导入Faker库用于生成测试数据

from api.models_forum import ForumBoard, Post, Comment, Like  # 从论坛模型模块导入相关模型

User = get_user_model()  # 获取用户模型


class Command(BaseCommand):  # 定义自定义管理命令类
    help = 'Initialize forum with test data'  # 命令帮助文本

    def add_arguments(self, parser):  # 定义命令参数
        parser.add_argument('--users', type=int, default=10, help='Number of test users to create')  # 添加用户数量参数
        parser.add_argument('--posts', type=int, default=50, help='Number of test posts to create')  # 添加帖子数量参数
        parser.add_argument('--comments', type=int, default=200, help='Number of test comments to create')  # 添加评论数量参数

    def handle(self, *args, **options):  # 定义命令处理逻辑
        fake = Faker('zh_CN')  # 创建中文Faker实例

        # 确保至少有一个管理员用户
        admin, created = User.objects.get_or_create(  # 获取或创建管理员用户
            username='admin',  # 用户名
            defaults={  # 默认值
                'email': 'admin@example.com',  # 邮箱
                'is_staff': True,  # 是员工
                'is_superuser': True,  # 是超级用户
                'is_active': True  # 激活状态
            }
        )
        if created:  # 如果是新创建的
            admin.set_password('admin123')  # 设置密码
            admin.save()  # 保存用户
            self.stdout.write(self.style.SUCCESS('Created admin user: admin/admin123'))  # 打印成功信息

        # 创建版主用户
        moderator, created = User.objects.get_or_create(  # 获取或创建版主用户
            username='moderator',  # 用户名
            defaults={  # 默认值
                'email': 'moderator@example.com',  # 邮箱
                'is_staff': False,  # 不是员工
                'is_active': True  # 激活状态
            }
        )
        if created:  # 如果是新创建的
            moderator.set_password('moderator123')  # 设置密码
            moderator.save()  # 保存用户
            moderator.groups.create(name='Moderators')  # 创建版主组
            self.stdout.write(self.style.SUCCESS('Created moderator user: moderator/moderator123'))  # 打印成功信息

        # 创建普通测试用户
        test_users = [admin, moderator]  # 初始化用户列表
        for i in range(options['users']):  # 循环创建指定数量的用户
            username = f'testuser{i + 1}'  # 生成用户名
            user, created = User.objects.get_or_create(  # 获取或创建用户
                username=username,  # 用户名
                defaults={  # 默认值
                    'email': f'{username}@example.com',  # 邮箱
                    'is_active': True  # 激活状态
                }
            )
            if created:  # 如果是新创建的
                user.set_password('test1234')  # 设置密码
                user.save()  # 保存用户
                test_users.append(user)  # 添加到用户列表

        self.stdout.write(self.style.SUCCESS(f'Created {len(test_users)} users in total'))  # 打印用户创建总数

        # 创建版块
        boards_data = [  # 版块数据列表
            {'name': '作物病害交流', 'description': '分享作物病害识别与防治经验', 'icon': 'el-icon-cold-drink'},
            # 作物病害交流版块
            {'name': '种植技术', 'description': '农业种植技术交流与分享', 'icon': 'el-icon-cherry'},  # 种植技术版块
            {'name': '农药肥料', 'description': '农药肥料使用经验交流', 'icon': 'el-icon-watermelon'},  # 农药肥料版块
            {'name': '农业机械', 'description': '农业机械设备使用与维护', 'icon': 'el-icon-truck'},  # 农业机械版块
            {'name': '市场行情', 'description': '农产品市场行情分析', 'icon': 'el-icon-s-data'},  # 市场行情版块
            {'name': '政策法规', 'description': '农业相关政策法规解读', 'icon': 'el-icon-document'},  # 政策法规版块
            {'name': '专家问答', 'description': '向专家提问，获取专业解答', 'icon': 'el-icon-question'},  # 专家问答版块
            {'name': '休闲灌水', 'description': '轻松一刻，农友交流', 'icon': 'el-icon-chat-dot-round'},  # 休闲灌水版块
        ]

        boards = []  # 初始化版块列表
        for i, data in enumerate(boards_data, 1):  # 遍历版块数据
            board, created = ForumBoard.objects.get_or_create(  # 获取或创建版块
                name=data['name'],  # 版块名称
                defaults={  # 默认值
                    'description': data['description'],  # 版块描述
                    'icon': data['icon'],  # 版块图标
                    'order': i,  # 排序序号
                    'is_active': True  # 激活状态
                }
            )
            boards.append(board)  # 添加到版块列表

            # 为部分版块添加版主
            # 注意: 当前模型中没有moderators字段，已注释掉相关代码
            # if i % 3 == 0 and moderator not in board.moderators.all():
            #     board.moderators.add(moderator)

        self.stdout.write(self.style.SUCCESS(f'Created {len(boards)} forum boards'))  # 打印版块创建总数

        # 创建帖子
        posts = []  # 初始化帖子列表
        for i in range(options['posts']):  # 循环创建指定数量的帖子
            author = random.choice(test_users)  # 随机选择作者
            board = random.choice(boards)  # 随机选择版块

            post = Post.objects.create(  # 创建帖子
                title=fake.sentence(),  # 生成随机标题
                content=fake.text(max_nb_chars=random.randint(100, 1000)),  # 生成随机内容
                author=author,  # 作者
                board=board,  # 所属版块
                status='published',  # 状态为已发布
                view_count=random.randint(0, 1000),  # 随机浏览量
                like_count=0,  # 初始点赞数为0
                comment_count=0,  # 初始评论数为0
                is_pinned=random.random() < 0.1,  # 10%的帖子置顶
                is_essence=random.random() < 0.2,  # 20%的帖子加精
                created_at=timezone.now() - timezone.timedelta(  # 随机创建时间
                    days=random.randint(0, 30),  # 随机天数
                    hours=random.randint(0, 23),  # 随机小时
                    minutes=random.randint(0, 59)  # 随机分钟
                )
            )
            posts.append(post)  # 添加到帖子列表

            # 随机生成点赞
            likers = random.sample(test_users, k=random.randint(0, min(20, len(test_users))))  # 随机选择点赞用户
            for liker in likers:  # 遍历点赞用户
                if liker != author:  # 不能给自己点赞
                    Like.objects.get_or_create(user=liker, post=post)  # 创建点赞记录
                    post.like_count += 1  # 增加点赞计数

            # 更新帖子点赞数
            post.save(update_fields=['like_count'])  # 保存更新后的点赞数

            # 每10个帖子打印一个点
            if (i + 1) % 10 == 0:  # 每10个帖子
                self.stdout.write(f'Created {i + 1} posts...', ending='\r')  # 打印进度

        self.stdout.write(self.style.SUCCESS(f'\nCreated {len(posts)} posts'))  # 打印帖子创建总数

        # 创建评论
        comments_created = 0  # 初始化评论计数
        all_comments = []  # 存储所有评论，用于回复

        for i in range(options['comments']):  # 循环创建指定数量的评论
            post = random.choice(posts)  # 随机选择帖子
            author = random.choice(test_users)  # 随机选择作者

            # 创建评论
            comment = Comment.objects.create(  # 创建评论
                content=fake.text(max_nb_chars=random.randint(20, 200)),  # 生成随机内容
                author=author,  # 作者
                post=post,  # 所属帖子
                created_at=timezone.now() - timezone.timedelta(  # 随机创建时间
                    days=random.randint(0, 30),  # 随机天数
                    hours=random.randint(0, 23),  # 随机小时
                    minutes=random.randint(0, 59)  # 随机分钟
                )
            )

            # 随机决定是否为回复评论（如果有其他评论）
            if all_comments and random.random() < 0.3:  # 30%的评论是回复
                parent_comment = random.choice(all_comments)  # 随机选择父评论
                comment.parent = parent_comment  # 设置父评论
                comment.save(update_fields=['parent'])  # 保存更新

            all_comments.append(comment)  # 添加到所有评论列表
            comments_created += 1  # 增加评论计数

            # 更新帖子评论数
            post.comment_count = post.comments.count()  # 重新计算评论数
            post.save(update_fields=['comment_count', 'updated_at'])  # 保存更新

            # 每10条评论打印一个点
            if comments_created % 10 == 0:  # 每10条评论
                self.stdout.write(f'Created {comments_created} comments...', ending='\r')  # 打印进度

        self.stdout.write(self.style.SUCCESS(f'\nCreated {comments_created} comments'))  # 打印评论创建总数

        self.stdout.write(self.style.SUCCESS('\nForum initialization completed successfully!'))  # 打印完成信息
        self.stdout.write(self.style.SUCCESS('Admin: admin/admin123'))  # 打印管理员账号信息
        self.stdout.write(self.style.SUCCESS('Moderator: moderator/moderator123'))  # 打印版主账号信息
        self.stdout.write(self.style.SUCCESS(f'Test users: testuser1~{options["users"]}/test1234'))  # 打印测试用户账号信息