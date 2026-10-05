"""
执行到期的注销申请（第 101 批）

==================================================================
为什么需要它，以及为什么必须有定时任务
==================================================================
第 101 批把"注销"改成了**冷静期**：用户申请后 15 天内可以取消，到期才真正删除。
但"到期"这件事**没有任何请求会触发它** —— 用户已经不登录了，也没有页面会去检查。
所以必须有一个每天（或每小时）跑的定时任务来收尾：

    python manage.py purge_deletion_requests            # 真正执行到期的申请
    python manage.py purge_deletion_requests --dry-run  # 只看将要删谁，不真删

部署时请挂 cron / systemd timer / 容器调度器，例如每天凌晨 3 点：

    0 3 * * * cd /path/to/backend && /path/to/python manage.py purge_deletion_requests

⚠️ **不跑这个命令的后果是"注销申请永不生效"** —— 用户以为 15 天后账号没了，
实际上个人信息一直留在库里。这比"不能注销"更糟：它是**说好的事没做**。
`check_env` 会把"有到期未处理"的申请数报出来，避免这种沉默。

==================================================================
为什么先 dry-run 再实删
==================================================================
软删除会改写用户名、清空个人信息，且**不可逆**。所以：
  · `--dry-run` 输出将影响的账号（用户名、申请时间、计划时间），不写库；
  · 实删前加 `--older-than-hours` 缓冲（默认 0，即严格按 scheduled_for）——
    留这个参数是为了应对"服务器时间被改过 / 时区错乱"这类事故，
    宁可晚删也不能误删。
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.models import CustomUser


class Command(BaseCommand):
    help = '执行已到期的账号注销申请（冷静期结束后的真正删除）'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='只列出将受影响的账号，不修改任何数据')
        parser.add_argument('--older-than-hours', type=int, default=0,
                            help='只处理"计划删除时间已过 N 小时"的账号（默认 0，严格按计划时间）')
        parser.add_argument('--limit', type=int, default=0,
                            help='本次最多处理多少个（0 = 不限；用于分批执行控风险）')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        buffer_hours = max(0, options['older_than_hours'])
        limit = max(0, options['limit'])

        cutoff = timezone.now() - timezone.timedelta(hours=buffer_hours)

        queryset = (
            CustomUser.objects
            .filter(is_deleted=False, deletion_scheduled_for__isnull=False,
                    deletion_scheduled_for__lte=cutoff)
            .order_by('deletion_scheduled_for')
        )
        total = queryset.count()
        if limit:
            queryset = queryset[:limit]

        rows = list(queryset)
        self.stdout.write(f'到期待执行的注销申请：{total} 个'
                          + (f'（本次处理前 {len(rows)} 个）' if limit else ''))

        if not rows:
            self.stdout.write(self.style.SUCCESS('没有需要处理的账号'))
            return

        now = timezone.now()
        for user in rows:
            days_ago = (now - user.deletion_scheduled_for).days
            self.stdout.write(
                f'  · id={user.id} username={user.username} '
                f'申请于 {user.deletion_requested_at:%Y-%m-%d %H:%M} '
                f'计划 {user.deletion_scheduled_for:%Y-%m-%d %H:%M}（已过期 {days_ago} 天）'
            )

        if dry_run:
            self.stdout.write(self.style.WARNING('--dry-run：未修改任何数据'))
            return

        purged = 0
        avatars = []
        for user in rows:
            # 逐个包事务：某一个账号出问题（比如关联数据异常）不该让整批回滚 ——
            # 否则会永远卡在同一个账号上，每天跑都失败，剩下的也删不掉。
            try:
                with transaction.atomic():
                    avatar = user.soft_delete(by=None, reason='grace-period-expired')
                if avatar:
                    avatars.append(avatar)
                purged += 1
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(self.style.ERROR(
                    f'  处理 id={user.id} 失败：{exc}'
                ))

        # 头像文件在事务外删（文件系统操作无法回滚，放事务里只会拖长事务）
        if avatars:
            from django.core.files.storage import default_storage
            for avatar in avatars:
                try:
                    default_storage.delete(avatar)
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(f'  删除头像文件失败 {avatar}：{exc}')

        self.stdout.write(self.style.SUCCESS(f'已执行注销：{purged} 个'))
        if purged < len(rows):
            self.stdout.write(self.style.WARNING(
                f'有 {len(rows) - purged} 个失败 —— 详见上面的错误信息，下次运行会重试'
            ))
