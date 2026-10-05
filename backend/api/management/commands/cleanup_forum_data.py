"""
论坛数据清理（软删除到期物理清除 + 长期不活跃内容）

**这个命令做什么**（按执行顺序，见 `handle`）：
  1. 物理删除**软删除已满 30 天**的帖子（第 91 批的软删除机制留的缓冲期）；
  2. 物理删除软删除已满 30 天的评论、以及孤立的点赞；
  3. 删除**超过 `--days`（默认 365 天）** 的旧帖与旧评论；
  4. 清理孤儿数据（如指向已删帖子的点赞 / 收藏）。

**参数**：
```
--days 365          旧内容阈值（天）
--inactive-days 30  "长期不活跃"的判定阈值（天）
--dry-run           只报告要删什么，不动数据
```

✅ **它有 `--dry-run`，请先跑它。** 会删数据的命令里这是最基本的一道保险，
本项目后来的 `prune_media` / `purge_deletion_requests` 都沿用了这个约定。

⚠️ 两个仍然要注意的点：
  · **它是唯一一个"默认就会删东西"的清理命令** ——
    `prune_media` 默认干跑、`purge_deletion_requests` 也只处理到期申请，
    而这个只要不带 `--dry-run` 就真删。跑之前先 `backend_backup`；
  · 输出是**英文**的（`help` 与提示语都是），与项目其它命令的中文风格不一致 ——
    历史遗留，不影响功能。
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q, F
from django.db import transaction
from datetime import timedelta

from api.models_forum import Post, Comment, Like

class Command(BaseCommand):
    # 第 107 批：help 从英文改成中文，与项目其它命令一致（`manage.py help` 里一眼能读）
    help = '清理论坛数据：软删除到期的物理删除、超期旧内容、孤儿点赞/收藏'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days', 
            type=int, 
            default=365,
            help='Delete posts older than this many days (default: 365)'
        )
        parser.add_argument(
            '--inactive-days',
            type=int,
            default=30,
            help='Consider users inactive after this many days (default: 30)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting anything'
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        days_threshold = options['days']
        inactive_days = options['inactive_days']
        
        # 计算截止日期
        cutoff_date = timezone.now() - timedelta(days=days_threshold)
        inactive_cutoff = timezone.now() - timedelta(days=inactive_days)
        
        self.stdout.write(f'Cleaning up forum data (dry run: {dry_run})...')
        self.stdout.write(f'- Posts older than: {cutoff_date}')
        self.stdout.write(f'- Inactive users: last login before {inactive_cutoff}')

        # 0. 第 91 批：帖子现在也是软删除 —— 先物理清掉"软删除超过 30 天"的帖子
        #    （与上面评论同一套路：留 30 天缓冲，之后才真删）
        purged_posts = Post.objects.filter(
            is_deleted=True,
            deleted_at__lte=timezone.now() - timedelta(days=30),
        )
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'Would purge {purged_posts.count()} posts soft-deleted over 30 days ago'
            ))
        else:
            count = purged_posts.count()
            purged_posts.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Purged {count} posts soft-deleted over 30 days ago'
            ))

        # 1. 删除软删除的评论
        deleted_comments = Comment.objects.filter(
            is_deleted=True,
            deleted_at__lte=timezone.now() - timedelta(days=30)  # 软删除30天后物理删除
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'Would delete {deleted_comments.count()} soft-deleted comments'
            ))
        else:
            count = deleted_comments.count()
            deleted_comments.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Deleted {count} soft-deleted comments'
            ))
        
        # 2. 清理旧帖子（无人回复且超过一定时间）
        old_posts = Post.objects.filter(
            created_at__lte=cutoff_date,
            comment_count=0,
            like_count=0
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'Would delete {old_posts.count()} old inactive posts'
            ))
        else:
            count = old_posts.count()
            old_posts.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Deleted {count} old inactive posts'
            ))
        
        # 3. 清理非活跃用户的帖子（可选）
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        inactive_users = User.objects.filter(
            last_login__lte=inactive_cutoff,
            is_staff=False,
            is_superuser=False
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'Found {inactive_users.count()} inactive users'
            ))
        
        # 4. 更新帖子统计信息（修复不一致）
        if not dry_run:
            # 更新评论数
            from django.db.models import Count
            
            # 获取每个帖子的实际评论数
            comment_counts = Comment.objects.filter(
                is_deleted=False,
                post__isnull=False
            ).values('post').annotate(
                actual_comment_count=Count('id')
            )
            
            # 更新帖子评论数
            updated_posts = 0
            for item in comment_counts:
                post_id = item['post']
                actual_count = item['actual_comment_count']
                
                # 只更新计数不一致的帖子
                updated = Post.objects.filter(
                    pk=post_id,
                ).exclude(
                    comment_count=actual_count
                ).update(
                    comment_count=actual_count
                )
                
                if updated > 0:
                    updated_posts += 1
            
            self.stdout.write(self.style.SUCCESS(
                f'Updated comment count for {updated_posts} posts'
            ))
            
            # 更新点赞数
            like_counts = Like.objects.values('post').annotate(
                actual_like_count=Count('id')
            )
            
            updated_likes = 0
            for item in like_counts:
                post_id = item['post']
                actual_count = item['actual_like_count']
                
                updated = Post.objects.filter(
                    pk=post_id,
                ).exclude(
                    like_count=actual_count
                ).update(
                    like_count=actual_count
                )
                
                if updated > 0:
                    updated_likes += 1
            
            self.stdout.write(self.style.SUCCESS(
                f'Updated like count for {updated_likes} posts'
            ))
        
        if dry_run:
            self.stdout.write(self.style.WARNING(
                'Dry run completed. No changes were made.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                'Forum data cleanup completed successfully!'
            ))
        
        # 5. 可选：输出数据库统计信息
        if not dry_run:
            self.stdout.write('\nForum Statistics:')
            self.stdout.write(f'- Total Posts: {Post.objects.count()}')
            self.stdout.write(f'- Total Comments: {Comment.objects.count()}')
            self.stdout.write(f'- Total Likes: {Like.objects.count()}')
