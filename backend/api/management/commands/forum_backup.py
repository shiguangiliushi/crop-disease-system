"""
论坛数据的 JSON 备份 / 恢复（**已被第 102 批的整库备份取代**）

⚠️ **这个命令目前是坏的，而且不该再用**：
  · `backup` 子命令一跑就崩 —— `timezone.now()` 没有 import（第 84 行）；
  · 它还引用了 `Post.is_featured` / `Post.is_locked` 两个**模型里不存在的字段**；
  · 就算修好，它也只覆盖论坛 5 张表（识别记录、反馈、新闻、积分、通知全不在），
    还把备份写到 `MEDIA_ROOT/forum_backups/` —— **和要保护的数据放在同一个目录**；
  · 恢复用 `input()` 交互确认（定时任务/管道里会卡死），且逐行写入没有事务。

**请改用 `manage.py backend_backup`**（整库 + 全部上传文件，带校验和与清单），
见 `docs/备份与恢复.md`。

**为什么文件还留着**：它的 JSON 结构（`users`/`boards`/`posts`/`comments`/`likes`）
对"想手工把论坛数据导成文本看看"仍有一点参考价值，
而项目的 `.git` 已损坏、没有版本控制，删掉就找不回来了。
确认不需要后可以整个删除，并同时删掉 `urls.py` 里没有任何引用的 import。
"""
import os
import json
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from api.models_forum import ForumBoard, Post, Comment, Like
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Backup or restore forum data'
    
    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='command', help='sub-command help')
        
        # 创建备份子命令
        backup_parser = subparsers.add_parser('backup', help='Backup forum data')
        backup_parser.add_argument(
            '--output', 
            type=str, 
            default=None,
            help='Output directory (default: MEDIA_ROOT/forum_backups/)'
        )
        backup_parser.add_argument(
            '--format',
            type=str,
            choices=['json', 'jsonl'],
            default='json',
            help='Output format (default: json)'
        )
        
        # 创建恢复子命令
        restore_parser = subparsers.add_parser('restore', help='Restore forum data from backup')
        restore_parser.add_argument(
            'input_file', 
            type=str, 
            help='Input backup file path'
        )
        restore_parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before restore'
        )
    
    def handle(self, *args, **options):
        command = options.get('command')
        
        if command == 'backup':
            self.backup_forum_data(
                output_dir=options['output'],
                format_type=options['format']
            )
        elif command == 'restore':
            self.restore_forum_data(
                input_file=options['input_file'],
                clear=options['clear']
            )
        else:
            self.stderr.write('Please specify a valid command: backup or restore')
            return
    
    def backup_forum_data(self, output_dir=None, format_type='json'):
        """备份论坛数据"""
        self.stdout.write('Starting forum data backup...')
        
        # 设置输出目录
        if not output_dir:
            output_dir = os.path.join(settings.MEDIA_ROOT, 'forum_backups')
            
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成带时间戳的文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(output_dir, f'forum_backup_{timestamp}.{format_type}')
        
        # 收集数据
        data = {
            'metadata': {
                'backup_time': timezone.now().isoformat(),
                'format': format_type,
                'version': '1.0',
            },
            'users': [],
            'boards': [],
            'posts': [],
            'comments': [],
            'likes': []
        }
        
        # 备份用户数据（仅必要字段）
        self.stdout.write('Backing up users...')
        for user in User.objects.all():
            data['users'].append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_active': user.is_active,
                'date_joined': user.date_joined.isoformat(),
                'last_login': user.last_login.isoformat() if user.last_login else None,
            })
        
        # 备份版块
        self.stdout.write('Backing up forum boards...')
        for board in ForumBoard.objects.all():
            moderators = list(board.moderators.values_list('id', flat=True))
            data['boards'].append({
                'id': board.id,
                'name': board.name,
                'description': board.description,
                'icon': board.icon,
                'order': board.order,
                'is_active': board.is_active,
                'moderators': moderators,
                'created_at': board.created_at.isoformat(),
                'updated_at': board.updated_at.isoformat(),
                'created_by_id': board.created_by_id,
                'updated_by_id': board.updated_by_id,
            })
        
        # 备份帖子
        self.stdout.write('Backing up posts...')
        for post in Post.objects.all():
            data['posts'].append({
                'id': post.id,
                'title': post.title,
                'content': post.content,
                'author_id': post.author_id,
                'board_id': post.board_id,
                'status': post.status,
                'view_count': post.view_count,
                'like_count': post.like_count,
                'comment_count': post.comment_count,
                'is_pinned': post.is_pinned,
                'is_featured': post.is_featured,
                'is_locked': post.is_locked,
                'created_at': post.created_at.isoformat(),
                'updated_at': post.updated_at.isoformat(),
            })
        
        # 备份评论
        self.stdout.write('Backing up comments...')
        for comment in Comment.objects.all():
            data['comments'].append({
                'id': comment.id,
                'content': comment.content,
                'author_id': comment.author_id,
                'post_id': comment.post_id,
                'parent_id': comment.parent_id,
                'reply_to_id': comment.reply_to_id,
                'status': comment.status,
                'is_deleted': comment.is_deleted,
                'deleted_at': comment.deleted_at.isoformat() if comment.deleted_at else None,
                'created_at': comment.created_at.isoformat(),
                'updated_at': comment.updated_at.isoformat(),
            })
        
        # 备份点赞
        self.stdout.write('Backing up likes...')
        for like in Like.objects.all():
            data['likes'].append({
                'id': like.id,
                'user_id': like.user_id,
                'post_id': like.post_id,
                'created_at': like.created_at.isoformat(),
            })
        
        # 保存备份文件
        self.stdout.write(f'Saving backup to {output_file}...')
        
        if format_type == 'json':
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        elif format_type == 'jsonl':
            with open(output_file, 'w', encoding='utf-8') as f:
                # 写入元数据
                f.write(json.dumps({'metadata': data['metadata']}, ensure_ascii=False) + '\n')
                # 写入数据
                for model_name in ['users', 'boards', 'posts', 'comments', 'likes']:
                    for item in data[model_name]:
                        f.write(json.dumps(
                            {model_name[:-1]: item},  # 单数形式
                            ensure_ascii=False
                        ) + '\n')
        
        self.stdout.write(self.style.SUCCESS(f'Backup completed: {output_file}'))
        # 注意：这里外层必须用双引号。原先写成 f'...{... if k != 'metadata')...}'，
        # 在 f-string 里嵌套同种引号只有 Python 3.12+（PEP 701）才合法；
        # 本项目环境是 Python 3.11.13，该文件会直接 SyntaxError ——
        # 后果是 forum_backup 命令完全无法导入，且 `manage.py help` 也会崩溃。
        self.stdout.write(f"Total items backed up: {sum(len(data[k]) for k in data if k != 'metadata')}")
    
    def restore_forum_data(self, input_file, clear=False):
        """从备份恢复论坛数据"""
        self.stdout.write(f'Restoring forum data from {input_file}...')
        
        if not os.path.exists(input_file):
            raise CommandError(f'Backup file not found: {input_file}')
        
        # 检测备份文件格式
        is_jsonl = input_file.endswith('.jsonl')
        
        # 读取备份数据
        try:
            if is_jsonl:
                data = {'metadata': {}, 'users': [], 'boards': [], 'posts': [], 'comments': [], 'likes': []}
                with open(input_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        item = json.loads(line.strip())
                        if 'metadata' in item:
                            data['metadata'] = item['metadata']
                        else:
                            for key in data.keys():
                                if key in item:
                                    data[key].append(item[key])
                                    break
            else:
                with open(input_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
        except Exception as e:
            raise CommandError(f'Failed to parse backup file: {e}')
        
        self.stdout.write(f"Backup info: {data.get('metadata', {}).get('backup_time', 'Unknown')}")
        
        if clear:
            if input('WARNING: This will delete all existing forum data. Are you sure? (y/n): ').lower() != 'y':
                self.stdout.write('Restore cancelled.')
                return
            
            self.stdout.write('Clearing existing forum data...')
            with transaction.atomic():
                Like.objects.all().delete()
                Comment.objects.all().delete()
                Post.objects.all().delete()
                ForumBoard.objects.all().delete()
        
        # 恢复数据
        self.stdout.write('Restoring data...')
        
        # 恢复用户
        if 'users' in data and data['users']:
            self.stdout.write(f'Restoring {len(data["users"])} users...')
            for user_data in data['users']:
                user_id = user_data.pop('id')
                User.objects.update_or_create(
                    id=user_id,
                    defaults=user_data
                )
        
        # 恢复版块
        if 'boards' in data and data['boards']:
            self.stdout.write(f'Restoring {len(data["boards"])} boards...')
            for board_data in data['boards']:
                moderators = board_data.pop('moderators', [])
                board_id = board_data.pop('id')
                
                # 确保创建者和更新者存在
                created_by_id = board_data.pop('created_by_id', None)
                updated_by_id = board_data.pop('updated_by_id', None)
                
                if created_by_id and not User.objects.filter(id=created_by_id).exists():
                    board_data['created_by_id'] = None
                if updated_by_id and not User.objects.filter(id=updated_by_id).exists():
                    board_data['updated_by_id'] = None
                
                board, created = ForumBoard.objects.update_or_create(
                    id=board_id,
                    defaults=board_data
                )
                
                # 恢复版主
                if moderators:
                    moderators = [uid for uid in moderators if User.objects.filter(id=uid).exists()]
                    board.moderators.set(moderators)
        
        # 恢复帖子
        if 'posts' in data and data['posts']:
            self.stdout.write(f'Restoring {len(data["posts"])} posts...')
            for post_data in data['posts']:
                post_id = post_data.pop('id')
                
                # 确保作者和版块存在
                author_id = post_data.get('author_id')
                board_id = post_data.get('board_id')
                
                if not User.objects.filter(id=author_id).exists():
                    self.stderr.write(f'Warning: User {author_id} not found, skipping post {post_id}')
                    continue
                    
                if not ForumBoard.objects.filter(id=board_id).exists():
                    self.stderr.write(f'Warning: Board {board_id} not found, skipping post {post_id}')
                    continue
                
                Post.objects.update_or_create(
                    id=post_id,
                    defaults=post_data
                )
        
        # 恢复评论
        if 'comments' in data and data['comments']:
            self.stdout.write(f'Restoring {len(data["comments"])} comments...')
            for comment_data in data['comments']:
                comment_id = comment_data.pop('id')
                
                # 确保相关外键存在
                author_id = comment_data.get('author_id')
                post_id = comment_data.get('post_id')
                parent_id = comment_data.get('parent_id')
                reply_to_id = comment_data.get('reply_to_id')
                
                if not User.objects.filter(id=author_id).exists():
                    self.stderr.write(f'Warning: User {author_id} not found, skipping comment {comment_id}')
                    continue
                    
                if not Post.objects.filter(id=post_id).exists():
                    self.stderr.write(f'Warning: Post {post_id} not found, skipping comment {comment_id}')
                    continue
                    
                if parent_id and not Comment.objects.filter(id=parent_id).exists():
                    comment_data['parent_id'] = None
                    
                if reply_to_id and not User.objects.filter(id=reply_to_id).exists():
                    comment_data['reply_to_id'] = None
                
                Comment.objects.update_or_create(
                    id=comment_id,
                    defaults=comment_data
                )
        
        # 恢复点赞
        if 'likes' in data and data['likes']:
            self.stdout.write(f'Restoring {len(data["likes"])} likes...')
            for like_data in data['likes']:
                like_id = like_data.pop('id')
                
                # 确保用户和帖子存在
                user_id = like_data.get('user_id')
                post_id = like_data.get('post_id')
                
                if not User.objects.filter(id=user_id).exists():
                    self.stderr.write(f'Warning: User {user_id} not found, skipping like {like_id}')
                    continue
                    
                if not Post.objects.filter(id=post_id).exists():
                    self.stderr.write(f'Warning: Post {post_id} not found, skipping like {like_id}')
                    continue
                
                Like.objects.update_or_create(
                    id=like_id,
                    defaults=like_data
                )
        
        self.stdout.write(self.style.SUCCESS('Forum data restore completed!'))
