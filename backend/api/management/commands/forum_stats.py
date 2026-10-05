"""
论坛统计报表（导出 CSV / 直接在终端看）

**用途**：运营视角的论坛数据 —— 版块活跃度、发帖趋势、热门帖子、用户贡献榜。
支持导出 CSV 供 Excel 打开。

**为什么它比这个文件看起来更大（650 行）**：统计口径都写在里面了
（按天/小时/月的截断、去重、`Coalesce` 兜底空值），
改一个数字前先确认它属于哪个报表 —— 同一个指标在不同报表里的口径**不一样**，
这是有意的（例如"活跃用户"在趋势图里按发帖算、在贡献榜里按发帖+评论+点赞算）。

⚠️ 这个命令**不认识 `--since` 之类的相对时间**，参数是明确的起止日期；
需要"最近 N 天"请自己算好日期传进来。
"""
import os
import csv
from datetime import datetime, timedelta
from io import StringIO
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Count, Sum, Q, F, Value, CharField
from django.db.models.functions import Coalesce, TruncDate, TruncHour, TruncDay, TruncMonth
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings

from api.models_forum import ForumBoard, Post, Comment, Like
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Generate forum statistics and activity reports'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days', 
            type=int, 
            default=30,
            help='Number of days to include in the report (default: 30)'
        )
        parser.add_argument(
            '--format',
            type=str,
            choices=['console', 'csv', 'html', 'email'],
            default='console',
            help='Output format (default: console)'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Output file path (required for csv/html format)'
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Email address to send the report to (required for email format)'
        )
        parser.add_argument(
            '--period',
            type=str,
            choices=['daily', 'weekly', 'monthly'],
            default='daily',
            help='Report period (default: daily)'
        )
    
    def handle(self, *args, **options):
        days = options['days']
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        self.stdout.write(f'Generating forum statistics report for the last {days} days...')
        
        # 收集统计数据
        stats = self.collect_stats(start_date, end_date, options['period'])
        
        # 生成报告
        report = self.generate_report(stats, options['format'])
        
        # 输出报告
        if options['format'] == 'console':
            self.stdout.write(report)
        elif options['format'] in ['csv', 'html']:
            if not options.get('output'):
                raise CommandError(f'Output file path is required for {options["format"]} format')
            self.save_report(report, options['output'], options['format'])
            self.stdout.write(self.style.SUCCESS(f'Report saved to {options["output"]}'))
        elif options['format'] == 'email':
            if not options.get('email'):
                raise CommandError('Email address is required for email format')
            self.send_email(report, options['email'], start_date, end_date)
            self.stdout.write(self.style.SUCCESS(f'Report sent to {options["email"]}'))
    
    def collect_stats(self, start_date, end_date, period='daily'):
        """收集论坛统计数据"""
        # 基础统计
        stats = {
            'period': period,
            'start_date': start_date,
            'end_date': end_date,
            'time_series': [],
            'summary': {},
            'top_users': {},
            'top_boards': {},
            'popular_content': {}
        }
        
        # 确定时间序列分组
        if period == 'daily':
            time_field = TruncDay('created_at')
        elif period == 'weekly':
            time_field = TruncDay('created_at')
        else:  # monthly
            time_field = TruncMonth('created_at')
        
        # 1. 时间序列数据（新帖、评论、用户）
        posts_by_period = (
            Post.active
            .filter(created_at__range=(start_date, end_date))
            .annotate(period=time_field)
            .values('period')
            .annotate(count=Count('id'))
            .order_by('period')
        )
        
        comments_by_period = (
            Comment.objects
            .filter(created_at__range=(start_date, end_date), is_deleted=False)
            .annotate(period=time_field)
            .values('period')
            .annotate(count=Count('id'))
            .order_by('period')
        )
        
        users_by_period = (
            User.objects
            .filter(date_joined__range=(start_date, end_date), is_active=True)
            .annotate(period=time_field)
            .values('period')
            .annotate(count=Count('id'))
            .order_by('period')
        )
        
        # 合并时间序列数据
        periods = set()
        period_data = {}
        
        for item in posts_by_period:
            period = item['period'].strftime('%Y-%m-%d')
            periods.add(period)
            if period not in period_data:
                period_data[period] = {'posts': 0, 'comments': 0, 'users': 0}
            period_data[period]['posts'] = item['count']
        
        for item in comments_by_period:
            period = item['period'].strftime('%Y-%m-%d')
            periods.add(period)
            if period not in period_data:
                period_data[period] = {'posts': 0, 'comments': 0, 'users': 0}
            period_data[period]['comments'] = item['count']
        
        for item in users_by_period:
            period = item['period'].strftime('%Y-%m-%d')
            periods.add(period)
            if period not in period_data:
                period_data[period] = {'posts': 0, 'comments': 0, 'users': 0}
            period_data[period]['users'] = item['count']
        
        # 按日期排序
        sorted_periods = sorted(periods)
        for period in sorted_periods:
            stats['time_series'].append({
                'period': period,
                'posts': period_data[period]['posts'],
                'comments': period_data[period]['comments'],
                'new_users': period_data[period]['users']
            })
        
        # 2. 汇总统计
        stats['summary'] = {
            'total_posts': Post.active.filter(created_at__range=(start_date, end_date)).count(),
            'total_comments': Comment.objects.filter(created_at__range=(start_date, end_date), is_deleted=False).count(),
            'total_likes': Like.objects.filter(created_at__range=(start_date, end_date)).count(),
            'new_users': User.objects.filter(date_joined__range=(start_date, end_date), is_active=True).count(),
            'active_users': self.get_active_users_count(start_date, end_date),
            'avg_posts_per_user': self.get_avg_posts_per_user(start_date, end_date),
            'avg_comments_per_post': self.get_avg_comments_per_post(start_date, end_date),
            'most_active_hour': self.get_most_active_hour(start_date, end_date)
        }
        
        # 3. 活跃用户排行
        stats['top_users'] = {
            'by_posts': self.get_top_users_by_posts(start_date, end_date, limit=10),
            'by_comments': self.get_top_users_by_comments(start_date, end_date, limit=10),
            'by_likes': self.get_top_users_by_likes(start_date, end_date, limit=10)
        }
        
        # 4. 热门版块
        stats['top_boards'] = self.get_top_boards(start_date, end_date, limit=5)
        
        # 5. 热门内容
        stats['popular_content'] = {
            'most_viewed_posts': self.get_most_viewed_posts(limit=5),
            'most_commented_posts': self.get_most_commented_posts(start_date, end_date, limit=5),
            'most_liked_posts': self.get_most_liked_posts(start_date, end_date, limit=5)
        }
        
        return stats
    
    def get_active_users_count(self, start_date, end_date):
        """获取活跃用户数（发帖或评论）"""
        return User.objects.filter(
            Q(post__created_at__range=(start_date, end_date)) |
            Q(comment__created_at__range=(start_date, end_date), comment__is_deleted=False)
        ).distinct().count()
    
    def get_avg_posts_per_user(self, start_date, end_date):
        """计算平均每个用户的发帖数"""
        from django.db.models import FloatField
        from django.db.models.functions import Cast
        
        total_posts = Post.active.filter(created_at__range=(start_date, end_date)).count()
        active_users = self.get_active_users_count(start_date, end_date)
        
        if active_users == 0:
            return 0.0
            
        return round(total_posts / active_users, 2)
    
    def get_avg_comments_per_post(self, start_date, end_date):
        """计算平均每个帖子的评论数"""
        total_posts = Post.active.filter(created_at__range=(start_date, end_date)).count()
        total_comments = Comment.objects.filter(
            created_at__range=(start_date, end_date),
            is_deleted=False
        ).count()
        
        if total_posts == 0:
            return 0.0
            
        return round(total_comments / total_posts, 2)
    
    def get_most_active_hour(self, start_date, end_date):
        """获取最活跃的小时"""
        from django.db.models.functions import ExtractHour
        
        # 统计每个小时的发帖和评论数
        post_hours = (
            Post.active
            .filter(created_at__range=(start_date, end_date))
            .annotate(hour=ExtractHour('created_at'))
            .values('hour')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        
        comment_hours = (
            Comment.objects
            .filter(created_at__range=(start_date, end_date), is_deleted=False)
            .annotate(hour=ExtractHour('created_at'))
            .values('hour')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        
        # 合并统计结果
        hour_stats = {i: 0 for i in range(24)}
        
        for item in post_hours:
            hour_stats[item['hour']] += item['count'] * 2  # 发帖权重更高
            
        for item in comment_hours:
            hour_stats[item['hour']] += item['count']
        
        # 找出最活跃的小时
        most_active_hour = max(hour_stats.items(), key=lambda x: x[1])
        
        return {
            'hour': most_active_hour[0],
            'activity_score': most_active_hour[1],
            'formatted_time': f"{most_active_hour[0]}:00-{most_active_hour[0]+1}:00"
        }
    
    def get_top_users_by_posts(self, start_date, end_date, limit=10):
        """获取发帖最多的用户"""
        return (
            User.objects
            .filter(post__created_at__range=(start_date, end_date))
            .annotate(post_count=Count('post'))
            .order_by('-post_count')[:limit]
            .values('id', 'username', 'post_count')
        )
    
    def get_top_users_by_comments(self, start_date, end_date, limit=10):
        """获取评论最多的用户"""
        return (
            User.objects
            .filter(comment__created_at__range=(start_date, end_date), comment__is_deleted=False)
            .annotate(comment_count=Count('comment'))
            .order_by('-comment_count')[:limit]
            .values('id', 'username', 'comment_count')
        )
    
    def get_top_users_by_likes(self, start_date, end_date, limit=10):
        """获取获赞最多的用户"""
        return (
            User.objects
            .filter(post__like__created_at__range=(start_date, end_date))
            .annotate(like_count=Count('post__like'))
            .order_by('-like_count')[:limit]
            .values('id', 'username', 'like_count')
        )
    
    def get_top_boards(self, start_date, end_date, limit=5):
        """获取最活跃的版块"""
        return (
            ForumBoard.objects
            .filter(
                post__created_at__range=(start_date, end_date),
                is_active=True
            )
            .annotate(
                post_count=Count('post'),
                comment_count=Count('post__comment', filter=Q(post__comment__is_deleted=False)),
                like_count=Count('post__like')
            )
            .annotate(
                activity_score=F('post_count') + F('comment_count') * 0.5 + F('like_count') * 0.2
            )
            .order_by('-activity_score')[:limit]
            .values('id', 'name', 'post_count', 'comment_count', 'like_count', 'activity_score')
        )
    
    def get_most_viewed_posts(self, limit=5):
        """获取浏览最多的帖子"""
        return (
            Post.active
            .order_by('-view_count')[:limit]
            .values('id', 'title', 'view_count', 'author__username')
        )
    
    def get_most_commented_posts(self, start_date, end_date, limit=5):
        """获取评论最多的帖子"""
        return (
            Post.active
            .filter(
                comment__created_at__range=(start_date, end_date),
                comment__is_deleted=False
            )
            .annotate(comment_count=Count('comment'))
            .order_by('-comment_count')[:limit]
            .values('id', 'title', 'comment_count', 'author__username')
        )
    
    def get_most_liked_posts(self, start_date, end_date, limit=5):
        """获取点赞最多的帖子"""
        return (
            Post.active
            .filter(like__created_at__range=(start_date, end_date))
            .annotate(like_count=Count('like'))
            .order_by('-like_count')[:limit]
            .values('id', 'title', 'like_count', 'author__username')
        )
    
    def generate_report(self, stats, format_type='console'):
        """生成报告内容"""
        if format_type == 'csv':
            return self.generate_csv(stats)
        elif format_type == 'html':
            return self.generate_html(stats)
        else:  # console
            return self.generate_console(stats)
    
    def generate_console(self, stats):
        """生成控制台格式的报告"""
        from tabulate import tabulate
        
        output = []
        
        # 标题
        output.append("=" * 80)
        output.append(f"论坛统计报告 ({stats['start_date'].strftime('%Y-%m-%d')} 至 {stats['end_date'].strftime('%Y-%m-%d')})")
        output.append("=" * 80)
        output.append("\n[汇总统计]")
        
        # 汇总统计
        summary = stats['summary']
        summary_table = [
            ["总发帖数", summary['total_posts']],
            ["总评论数", summary['total_comments']],
            ["总点赞数", summary['total_likes']],
            ["新注册用户", summary['new_users']],
            ["活跃用户数", summary['active_users']],
            ["平均每用户发帖", f"{summary['avg_posts_per_user']:.2f}"],
            ["平均每帖评论", f"{summary['avg_comments_per_post']:.2f}"],
            ["最活跃时段", summary['most_active_hour']['formatted_time']]
        ]
        output.append(tabulate(summary_table, tablefmt="grid"))
        
        # 时间序列数据
        output.append("\n[时间序列数据]")
        if stats['time_series']:
            time_series_data = [
                [
                    item['period'], 
                    item['posts'], 
                    item['comments'], 
                    item['new_users']
                ]
                for item in stats['time_series']
            ]
            output.append(tabulate(
                time_series_data, 
                headers=["日期", "发帖数", "评论数", "新用户数"],
                tablefmt="grid"
            ))
        
        # 热门版块
        output.append("\n[热门版块]")
        if stats['top_boards']:
            boards_data = [
                [
                    i+1, 
                    item['name'], 
                    item['post_count'], 
                    item['comment_count'], 
                    item['like_count'],
                    f"{item['activity_score']:.1f}"
                ]
                for i, item in enumerate(stats['top_boards'])
            ]
            output.append(tabulate(
                boards_data,
                headers=["排名", "版块名称", "发帖数", "评论数", "点赞数", "活跃度"],
                tablefmt="grid"
            ))
        
        # 热门内容
        output.append("\n[热门内容]")
        
        # 最多浏览
        output.append("\n最多浏览的帖子:")
        if stats['popular_content']['most_viewed_posts']:
            posts_data = [
                [i+1, item['title'], item['author__username'], item['view_count']]
                for i, item in enumerate(stats['popular_content']['most_viewed_posts'])
            ]
            output.append(tabulate(
                posts_data,
                headers=["排名", "标题", "作者", "浏览数"],
                tablefmt="grid"
            ))
        
        # 最多评论
        output.append("\n最多评论的帖子:")
        if stats['popular_content']['most_commented_posts']:
            posts_data = [
                [i+1, item['title'], item['author__username'], item['comment_count']]
                for i, item in enumerate(stats['popular_content']['most_commented_posts'])
            ]
            output.append(tabulate(
                posts_data,
                headers=["排名", "标题", "作者", "评论数"],
                tablefmt="grid"
            ))
        
        # 最多点赞
        output.append("\n最多点赞的帖子:")
        if stats['popular_content']['most_liked_posts']:
            posts_data = [
                [i+1, item['title'], item['author__username'], item['like_count']]
                for i, item in enumerate(stats['popular_content']['most_liked_posts'])
            ]
            output.append(tabulate(
                posts_data,
                headers=["排名", "标题", "作者", "点赞数"],
                tablefmt="grid"
            ))
        
        # 活跃用户
        output.append("\n[活跃用户排行]")
        
        # 发帖最多
        output.append("\n发帖最多的用户:")
        if stats['top_users']['by_posts']:
            users_data = [
                [i+1, item['username'], item['post_count']]
                for i, item in enumerate(stats['top_users']['by_posts'])
            ]
            output.append(tabulate(
                users_data,
                headers=["排名", "用户名", "发帖数"],
                tablefmt="grid"
            ))
        
        # 评论最多
        output.append("\n评论最多的用户:")
        if stats['top_users']['by_comments']:
            users_data = [
                [i+1, item['username'], item['comment_count']]
                for i, item in enumerate(stats['top_users']['by_comments'])
            ]
            output.append(tabulate(
                users_data,
                headers=["排名", "用户名", "评论数"],
                tablefmt="grid"
            ))
        
        # 获赞最多
        output.append("\n获赞最多的用户:")
        if stats['top_users']['by_likes']:
            users_data = [
                [i+1, item['username'], item['like_count']]
                for i, item in enumerate(stats['top_users']['by_likes'])
            ]
            output.append(tabulate(
                users_data,
                headers=["排名", "用户名", "获赞数"],
                tablefmt="grid"
            ))
        
        return "\n".join(output)
    
    def generate_csv(self, stats):
        """生成CSV格式的报告"""
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        # 写入汇总统计
        writer.writerow(["统计项", "数值"])
        writer.writerow(["总发帖数", stats['summary']['total_posts']])
        writer.writerow(["总评论数", stats['summary']['total_comments']])
        writer.writerow(["总点赞数", stats['summary']['total_likes']])
        writer.writerow(["新注册用户", stats['summary']['new_users']])
        writer.writerow(["活跃用户数", stats['summary']['active_users']])
        writer.writerow(["平均每用户发帖", f"{stats['summary']['avg_posts_per_user']:.2f}"])
        writer.writerow(["平均每帖评论", f"{stats['summary']['avg_comments_per_post']:.2f}"])
        writer.writerow(["最活跃时段", stats['summary']['most_active_hour']['formatted_time']])
        
        # 写入时间序列数据
        writer.writerow([])
        writer.writerow(["时间序列数据"])
        writer.writerow(["日期", "发帖数", "评论数", "新用户数"])
        for item in stats['time_series']:
            writer.writerow([
                item['period'], 
                item['posts'], 
                item['comments'], 
                item['new_users']
            ])
        
        # 写入热门版块
        writer.writerow([])
        writer.writerow(["热门版块"])
        writer.writerow(["排名", "版块名称", "发帖数", "评论数", "点赞数", "活跃度"])
        for i, item in enumerate(stats['top_boards'], 1):
            writer.writerow([
                i,
                item['name'],
                item['post_count'],
                item['comment_count'],
                item['like_count'],
                f"{item['activity_score']:.1f}"
            ])
        
        # 写入热门内容
        writer.writerow([])
        writer.writerow(["最多浏览的帖子"])
        writer.writerow(["排名", "标题", "作者", "浏览数"])
        for i, item in enumerate(stats['popular_content']['most_viewed_posts'], 1):
            writer.writerow([
                i,
                item['title'],
                item['author__username'],
                item['view_count']
            ])
        
        writer.writerow([])
        writer.writerow(["最多评论的帖子"])
        writer.writerow(["排名", "标题", "作者", "评论数"])
        for i, item in enumerate(stats['popular_content']['most_commented_posts'], 1):
            writer.writerow([
                i,
                item['title'],
                item['author__username'],
                item['comment_count']
            ])
        
        writer.writerow([])
        writer.writerow(["最多点赞的帖子"])
        writer.writerow(["排名", "标题", "作者", "点赞数"])
        for i, item in enumerate(stats['popular_content']['most_liked_posts'], 1):
            writer.writerow([
                i,
                item['title'],
                item['author__username'],
                item['like_count']
            ])
        
        # 写入活跃用户
        writer.writerow([])
        writer.writerow(["活跃用户排行"])
        
        writer.writerow(["发帖最多的用户"])
        writer.writerow(["排名", "用户名", "发帖数"])
        for i, item in enumerate(stats['top_users']['by_posts'], 1):
            writer.writerow([i, item['username'], item['post_count']])
        
        writer.writerow([])
        writer.writerow(["评论最多的用户"])
        writer.writerow(["排名", "用户名", "评论数"])
        for i, item in enumerate(stats['top_users']['by_comments'], 1):
            writer.writerow([i, item['username'], item['comment_count']])
        
        writer.writerow([])
        writer.writerow(["获赞最多的用户"])
        writer.writerow(["排名", "用户名", "获赞数"])
        for i, item in enumerate(stats['top_users']['by_likes'], 1):
            writer.writerow([i, item['username'], item['like_count']])
        
        return output.getvalue()
    
    def generate_html(self, stats):
        """生成HTML格式的报告"""
        from django.template.loader import render_to_string
        
        context = {
            'stats': stats,
            'generated_at': timezone.now(),
            'title': f"论坛统计报告 ({stats['start_date'].strftime('%Y-%m-%d')} 至 {stats['end_date'].strftime('%Y-%m-%d')})"
        }
        
        # 渲染HTML模板
        html_content = render_to_string('admin/forum_stats_report.html', context)
        return html_content
    
    def save_report(self, content, file_path, format_type):
        """保存报告到文件"""
        dir_path = os.path.dirname(file_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def send_email(self, content, email, start_date, end_date):
        """发送邮件报告"""
        subject = f"论坛统计报告 ({start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')})"
        
        # 如果是HTML内容，发送HTML邮件
        if content.strip().startswith('<'):
            html_message = content
            message = "请使用支持HTML的邮件客户端查看此邮件。"
        else:
            message = content
            html_message = None
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False
        )
