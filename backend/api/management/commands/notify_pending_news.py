"""
补发"到点但还没发过通知"的行业动态（第 402 批 P2-11）

    python manage.py notify_pending_news                # 最近 7 天，最多 50 条
    python manage.py notify_pending_news --days 3       # 只回看 3 天
    python manage.py notify_pending_news --limit 100
    python manage.py notify_pending_news --dry-run      # 只打印，不写通知

## 为什么需要它

"定时发布"（`published_at` 在未来）**到点时没有任何保存动作** —— 时间是自然流逝的，
`news_views.create/update` 里的"发布即通知"触达不到它。没有这条命令，订阅者
永远收不到定时新闻的通知。

## 去重口径

用 `Notification(news=<新闻>, type='news')` 是否存在判重：新建即发布 / 草稿→发布
触发的通知已经写过 news 外键，所以本命令不会重复扇出；而"漏发"的定时新闻
补发一次之后也会被同一口径排除，反复跑是幂等的。

## 可见性口径

与列表接口一致：`is_published=True` 且（`published_at` 为空 或 已到点）。
草稿与还没到点的定时新闻不会提前通知。
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from ...models import News
from ...models_notify import Notification
from ...views_news_subscription import news_subscriber_ids, notify_news_subscribers


class Command(BaseCommand):
    help = '给"已到点但还没发过订阅通知"的行业动态补发站内通知（定时发布场景）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=7,
            help='只回看最近 N 天创建的新闻（默认 7，避免把历史新闻全部补发）',
        )
        parser.add_argument(
            '--limit', type=int, default=50,
            help='一次最多处理多少条（默认 50）',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='只打印会补发哪些新闻，不写通知',
        )

    def handle(self, *args, **options):
        now = timezone.now()
        days = max(1, int(options['days']))
        limit = max(1, int(options['limit']))
        cutoff = now - timedelta(days=days)

        # 对公众可见：已发布 且（没有定时时间 或 已到点）
        visible_qs = News.objects.filter(
            is_published=True,
            created_at__gte=cutoff,
        ).filter(
            Q(published_at__isnull=True) | Q(published_at__lte=now)
        )

        # 已经发过 type='news' 通知的新闻（news 外键是第 402 批新增的去重依据）
        notified_ids = Notification.objects.filter(
            type='news', news__isnull=False,
        ).values('news_id')
        pending = list(
            visible_qs.exclude(pk__in=notified_ids).order_by('created_at', 'pk')[:limit]
        )

        if not pending:
            self.stdout.write(self.style.SUCCESS('✓ 没有需要补发通知的行业动态'))
            return

        if options['dry_run']:
            self.stdout.write(f'（dry-run）会处理 {len(pending)} 条行业动态：')
            for news in pending:
                recipients = len(news_subscriber_ids(news))
                self.stdout.write(
                    f'  · #{news.pk} {news.title[:40]} → 预计通知 {recipients} 人'
                )
            return

        processed = 0
        notified = 0
        for news in pending:
            sent = notify_news_subscribers(news)
            processed += 1
            notified += sent
            self.stdout.write(f'  · #{news.pk} {news.title[:40]} → 通知 {sent} 人')

        self.stdout.write(self.style.SUCCESS(
            f'✓ 补发完成：处理 {processed} 条行业动态，发出 {notified} 条通知'
        ))
