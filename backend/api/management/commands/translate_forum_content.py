"""
批量补译用户内容的英文译文（第 85 批）

覆盖：论坛帖子、评论/回复、意见反馈（反馈内容与管理员回复）。

============================================================================
什么时候用它
----------------------------------------------------------------------------
发帖/评论时后端会**顺手**翻译一次（`settings.TRANSLATE_ON_WRITE`，默认开）。
但下面几种情况要用命令行批量补：

  · 刚配好翻译 provider —— 库里已有的历史帖子还没有译文；
  · 当时接口挂了/额度用尽，帖子里留了一堆"未翻译"；
  · 换了更好的 provider（比如从公共接口换到 DeepL），想把旧译文重做一遍。

用法（在 backend 目录下）：

    python manage.py translate_forum_content                 # 帖子+评论+反馈，只补缺的/过期的
    python manage.py translate_forum_content --kind=post
    python manage.py translate_forum_content --kind=feedback
    python manage.py translate_forum_content --ids=106,105
    python manage.py translate_forum_content --dry-run        # 只看要翻哪些，不写库
    python manage.py translate_forum_content --force           # 连人工译文也覆盖（慎用）
    python manage.py translate_forum_content --provider=libre   # 临时换 provider

退出码：0 = 全部成功（或没有需要翻的）；1 = 有失败项（已逐条打印原因）。
============================================================================
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from api import services_translate
from api.models import Feedback
from api.models_forum import Comment, Post


class Command(BaseCommand):
    help = '批量补译用户内容（帖子/评论/意见反馈）的英文译文，见 services_translate.py'

    def add_arguments(self, parser):
        parser.add_argument('--kind', choices=['post', 'comment', 'feedback', 'all'], default='all',
                            help='要翻译的内容类型（默认 all）')
        parser.add_argument('--ids', default='', help='只处理这些 id，逗号分隔（默认全部）')
        parser.add_argument('--limit', type=int, default=0, help='最多处理多少条（0 = 不限）')
        parser.add_argument('--dry-run', action='store_true', help='只列出待翻译项，不写库、不请求接口')
        parser.add_argument('--force', action='store_true',
                            help='重新翻译已过期的机器译文（**不动人工译文**）')
        parser.add_argument('--force-manual', action='store_true',
                            help='连作者/管理员手工写的英文也覆盖（危险：会丢掉人工译文）')
        parser.add_argument('--provider', default='', help='临时指定 provider（覆盖 settings）')
        parser.add_argument('--include-deleted', action='store_true',
                            help='评论默认跳过已软删除的，加上此参数则包含')

    # ── 内部工具 ────────────────────────────────────────────────────────────
    def _id_filter(self, queryset, ids):
        if ids:
            return queryset.filter(pk__in=ids)
        return queryset

    def _needs_translation(self, obj, force: bool) -> bool:
        """是否需要翻译：没译文、原文改过、或强制

        第 86 批：`--force` **不再覆盖人工译文**。第 85 批加了"作者自己填英文"的
        能力之后，"一键重刷全部译文"要是一并把人工译文冲掉，作者的工作就白做了。
        现在：
          · 默认   —— 只补"没译文 / 原文改过"的；
          · --force —— 连**机器译文**也重做（换 provider 后重刷用这个）；
          · --force-manual —— 才连人工译文一起覆盖（危险，需显式指定）。
        判断"人工译文"用 `translation_source == 'manual'`（作者提交英文时记的）。
        """
        # 第 85 批：先排除"没有值得翻译的原文"的行（例如反馈里系统写死的
        # 「识别正确/识别错误」—— 序列化器有固定映射，送机翻反而更差）
        if not services_translate.is_translatable(obj):
            return False
        fingerprint = obj.source_fingerprint()
        if not fingerprint:
            return False
        is_manual = obj.translation_source == obj.SOURCE_MANUAL and obj.has_translation
        if force and not is_manual:
            return True
        if not obj.has_translation:
            return True
        if is_manual and not force:
            # 人工译文且原文没变 → 不动；原文变了也不自动覆盖（界面会提示"译文可能过期"），
            # 需要重译就显式 --force-manual
            return False
        return obj.translation_hash != fingerprint

    def handle(self, *args, **options):
        # 第 86 批：--dry-run 不需要可用的 provider（它不翻译），所以即使自动翻译
        # 当前是关闭状态也允许列清单 —— 用户经常想先看看"会翻哪些"再决定开不开。
        if (not options['dry_run'] and not services_translate.is_enabled()
                and not options['provider']):
            self.stdout.write(self.style.WARNING(
                '当前 settings.TRANSLATE_PROVIDER=%r 且 TRANSLATE_ENABLED=%s —— 自动翻译处于关闭状态。'
                % (getattr(settings, 'TRANSLATE_PROVIDER', ''), getattr(settings, 'TRANSLATE_ENABLED', True))
            ))
            self.stdout.write('可在 .env 里设置 TRANSLATE_PROVIDER=mymemory，或用 --provider=... 临时指定。')
            self.stdout.write('（加 --dry-run 可以在不翻译的情况下先看清单）')
            return

        ids = [int(x) for x in options['ids'].split(',') if x.strip().isdigit()]
        kind = options['kind']
        force = options['force'] or options['force_manual']

        jobs = []  # [(label, obj)]
        if kind in ('post', 'all'):
            # 第 91 批：Post.active —— 软删除的帖子正文已清成占位文案，没必要翻
            qs = Post.active.all().order_by('id')
            qs = self._id_filter(qs, ids)
            # 只翻"会被别人看到的"帖子：草稿没有对外展示的英文需求
            qs = qs.exclude(status='draft')
            for post in qs:
                if self._needs_translation(post, force):
                    jobs.append((f'帖子 #{post.pk} 《{post.title[:24]}》', post))
        if kind in ('comment', 'all'):
            qs = Comment.objects.all().order_by('id')
            if not options['include_deleted']:
                qs = qs.exclude(is_deleted=True)
            qs = self._id_filter(qs, ids)
            for comment in qs:
                if self._needs_translation(comment, force):
                    jobs.append((f'评论 #{comment.pk}（帖子 #{comment.post_id}）', comment))
        if kind in ('feedback', 'all'):
            # 第 85 批：意见反馈也是人写的中文（用户写的意见 + 管理员写的回复）
            qs = Feedback.objects.all().order_by('id')
            qs = self._id_filter(qs, ids)
            for feedback in qs:
                if self._needs_translation(feedback, force):
                    preview = (feedback.suggestion or feedback.admin_reply or '')[:20]
                    jobs.append((f'反馈 #{feedback.pk}（{preview}）', feedback))

        if options['limit']:
            jobs = jobs[:options['limit']]

        flags = []
        if options['force']:
            flags.append('force(不动人工译文)')
        if options['force_manual']:
            flags.append('force-manual(含人工译文)')
        self.stdout.write(
            'provider=%s  %s  待翻译 %d 条（%s）'
            % (options['provider'] or services_translate.provider_name(),
               ' '.join(flags) or '仅补缺失/过期', len(jobs),
               '仅列出' if options['dry_run'] else '开始翻译')
        )
        for label, _ in jobs:
            self.stdout.write(f'  · {label}')
        if options['dry_run'] or not jobs:
            return

        done = 0
        failed = []
        for index, (label, obj) in enumerate(jobs, 1):
            try:
                changed = services_translate.translate_instance(
                    # 第 86 批：force 只对"机器译文"生效；人工译文必须显式 --force-manual
                    # （translate_instance 的 allow_manual_overwrite 就是这道闸）
                    obj,
                    force=force,
                    provider=options['provider'] or None,
                    allow_manual_overwrite=options['force_manual'],
                )
                if changed:
                    done += 1
                    preview = (
                        getattr(obj, 'title_en', '')
                        or getattr(obj, 'content_en', '')
                        or getattr(obj, 'suggestion_en', '')
                        or getattr(obj, 'admin_reply_en', '')
                        or ''
                    )[:60]
                    self.stdout.write(f'[{index}/{len(jobs)}] ✓ {label} → {preview}')
                else:
                    self.stdout.write(
                        f'[{index}/{len(jobs)}] - {label} 跳过'
                        '（人工译文 / 原文为空 / 已经是最新译文）'
                    )
            except Exception as exc:  # noqa: BLE001 —— 单条失败不影响其余
                failed.append((label, str(exc)))
                self.stdout.write(self.style.ERROR(f'[{index}/{len(jobs)}] ✗ {label} —— {exc}'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'完成：写入 {done} 条，跳过 {len(jobs) - done - len(failed)} 条，失败 {len(failed)} 条'))
        if failed:
            self.stdout.write(self.style.ERROR('失败明细：'))
            for label, reason in failed:
                self.stdout.write(f'  · {label}：{reason}')
            raise SystemExit(1)
