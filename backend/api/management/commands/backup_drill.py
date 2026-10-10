"""
备份恢复演练（第 154 批）

    python manage.py backup_drill --yes

## 为什么要做成命令

`docs/备份与恢复.md` 第六节早就写了这份演练步骤，但**一直是手工跑的** ——
我在第 153 批核查时发现文档里那句"脚本留在 `frontend/scripts/`"根本无法复查
（那里 31 个脚本全是功能回归）。而"有备份"和"能恢复"是两件事：
**没演练过的备份等于没有备份**，因为它可能缺表、缺媒体、或者恢复命令本身就是坏的。

固化成命令之后，它可以：① 随时手动跑；② 挂到定时任务里定期演练（建议在**另一套数据**上）；
③ 出问题时给出逐项 PASS/FAIL，而不是"我记得上次是好的"。

## 它做的五步（与文档一致）

```
① 造两样"独有的东西"：一条特殊标题的帖子 + 一张独有的上传图片（记下 sha256）
② 备份（backend_backup --label drill）
③ 破坏：删掉那条帖子、删掉那张图片、删掉 N 条识别记录
④ 恢复（backend_restore <名字> --yes --overwrite-media）
⑤ 验证：帖子回来了、图片回来了且**校验和一致**、识别记录条数回到备份时的值
```

## 安全设计（它会**改写数据库**，所以门开得很窄）

- **必须显式 `--yes`**：没有它只打印计划，什么都不做；
- **默认只允许 `DEBUG=True`**（开发/测试库）。生产要演练请用**另一套数据/另一台机器**，
  确实要在生产跑就得额外加 `--force`，并且心里清楚"这几秒里别人写入的数据会被回滚"；
- 恢复命令自己会用 SQLite **在线备份 API** 写回（而不是 copy2），所以不怕有连接开着；
  但**本进程**的连接里还缓存着旧数据，所以恢复前后都要 `connections.close_all()`；
- 失败时**保留**那次演练备份并把名字打在屏幕上（它是你回到原状态的唯一凭证），
  成功时才按 `--keep` 决定是否删除。

## 与"备份是否可信"的关系

这一步补上之后，`docs/备份与恢复.md` 里的承诺才是可验证的：
**备份 → 破坏 → 恢复 → 逐项核对**，每一步都有输出。
"""
import hashlib
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.utils import timezone

from ... import backup_utils as bu

#: 演练用的标记前缀（方便一眼认出、也方便残留时手工清）
POST_PREFIX = 'zz演练标记帖'
IMAGE_PREFIX = 'zz_drill_'
#: 破坏阶段删掉几条识别记录
DETECTIONS_TO_DELETE = 3
#: 一张 1×1 的合法 PNG（不依赖 Pillow，也不需要外部文件）
TINY_PNG = bytes.fromhex(
    '89504e470d0a1a0a0000000d494844520000000100000001080600000'
    '01f15c4890000000a49444154789c6300010000050001'
    '0d0a2db40000000049454e44ae426082',
)

class Command(BaseCommand):
    help = '备份恢复演练：造标记物 → 备份 → 破坏 → 恢复 → 验证（第 154 批）'

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='确认执行（没有它只打印计划）')
        parser.add_argument('--force', action='store_true',
                            help='允许在 DEBUG=False 下执行（会回滚这几秒内的写入，想清楚再用）')
        parser.add_argument('--label', type=str, default='drill', help='备份标签（默认 drill）')
        parser.add_argument('--keep', action='store_true', help='成功后保留这次演练备份')
        parser.add_argument('--skip-media', action='store_true',
                            help='跳过媒体校验（只演练数据库；更快）')

    # -- 输出小工具 ---------------------------------------------------------
    def _step(self, index, text):
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n[{index}/5] {text}'))

    def _ok(self, text):
        self.stdout.write(self.style.SUCCESS(f'  ✓ {text}'))

    def _bad(self, text):
        self.stdout.write(self.style.ERROR(f'  ✗ {text}'))

    # -- 主流程 -------------------------------------------------------------
    def handle(self, *args, **options):
        from ...models import CustomUser
        from ...models_forum import Post

        if not options['yes']:
            self.stdout.write(self.style.WARNING(
                '这是**演练**命令：会删数据再用备份恢复回来（数据库内容会被改写）。\n'
                '确认无误后请重跑并加上 --yes。\n'))
            self.stdout.write('计划的五步：造标记物 → 备份 → 破坏 → 恢复 → 逐项验证')
            return

        if not settings.DEBUG and not options['force']:
            raise CommandError(
                '拒绝在 DEBUG=False 下执行：演练会回写数据库，这几秒内别人的写入会被回滚。\n'
                '生产演练请用另一套数据/另一台机器；确实要在这里跑，加 --force。')

        author = CustomUser.objects.filter(is_superuser=True).first() or CustomUser.objects.first()
        if author is None:
            raise CommandError('库里一个用户都没有，演练无从下手：先创建管理员账号。')

        # ⚠️ `Post.board` 是**必填**外键 —— 第一次真跑就栽在这里：
        #    `NOT NULL constraint failed: api_post.board_id`
        from ...models_forum import ForumBoard
        board = ForumBoard.objects.order_by('order', 'id').first()
        if board is None:
            raise CommandError('库里一个论坛版块都没有：先跑 python manage.py init_forum_boards。')

        stamp = timezone.localtime().strftime('%Y%m%d-%H%M%S')
        checks = []          # [(名称, 是否通过, 说明)]
        backup_name = None

        # ---------- ① 造标记物 ----------
        self._step(1, '造标记物（一条帖子 + 一张图片 + 识别记录基线）')
        post_title = f'{POST_PREFIX}-{stamp}'
        post = Post.objects.create(
            title=post_title, content='<p>备份恢复演练的标记帖：恢复后它必须回来。</p>',
            author=author, board=board, status='published',
        )
        self._ok(f'标记帖 #{post.id}「{post_title}」')

        media_root = Path(settings.MEDIA_ROOT)
        upload_dir = media_root / 'uploads'
        upload_dir.mkdir(parents=True, exist_ok=True)
        image_path = upload_dir / f'{IMAGE_PREFIX}{stamp}.png'
        image_path.write_bytes(TINY_PNG)
        image_digest = hashlib.sha256(TINY_PNG).hexdigest()
        self._ok(f'标记图片 {image_path.relative_to(media_root)}（sha256 {image_digest[:12]}…）')

        from ...models import DetectionHistory
        detection_total = DetectionHistory.objects.count()
        victim_ids = list(DetectionHistory.objects.order_by('-id')
                          .values_list('id', flat=True)[:DETECTIONS_TO_DELETE])
        self._ok(f'识别记录基线：共 {detection_total} 条，破坏阶段将删 {len(victim_ids)} 条')

        try:
            # ---------- ② 备份 ----------
            self._step(2, '备份（backend_backup）')
            call_command('backend_backup', label=options['label'], quiet=True)
            candidates = [p for p in bu.list_backups(bu.backup_root())
                          if options['label'] in p.name]
            if not candidates:
                raise CommandError('备份目录里找不到刚生成的备份，演练中止（这一步本身就说明有问题）')
            backup_dir = max(candidates, key=lambda p: p.name)
            backup_name = backup_dir.name
            self._ok(f'备份完成：{backup_name}（{bu.human_size(_dir_size(backup_dir))}）')

            # ---------- ③ 破坏 ----------
            self._step(3, '破坏（删帖子 / 删图片 / 删识别记录）')
            Post.objects.filter(id=post.id).delete()
            checks.append(('标记帖已删除（破坏生效）',
                           not Post.objects.filter(title=post_title).exists(), ''))
            if image_path.exists():
                image_path.unlink()
            checks.append(('标记图片已删除（破坏生效）', not image_path.exists(), ''))
            if victim_ids:
                DetectionHistory.objects.filter(id__in=victim_ids).delete()
            checks.append(('识别记录已减少（破坏生效）',
                           DetectionHistory.objects.count() < detection_total, ''))
            self._ok('破坏完成（下面就看恢复能不能全部还原）')

            # ---------- ④ 恢复 ----------
            self._step(4, '恢复（backend_restore --yes --overwrite-media）')
            # 本进程的连接里缓存着旧数据；恢复是**另一个文件写回**，必须先断开
            connections.close_all()
            call_command('backend_restore', backup_name, yes=True,
                         overwrite_media=not options['skip_media'],
                         no_safety_backup=True, skip_verify=False)
            connections.close_all()
            self._ok('恢复命令执行完毕')

            # ---------- ⑤ 验证 ----------
            self._step(5, '验证（逐项核对）')
            restored = Post.objects.filter(title=post_title).first()
            checks.append(('标记帖回来了（内容也对）',
                           bool(restored and '标记帖' in (restored.content or '')), ''))

            if options['skip_media']:
                checks.append(('媒体校验', True, '（本次 --skip-media，跳过）'))
            else:
                exists = image_path.exists()
                digest_ok = exists and hashlib.sha256(image_path.read_bytes()).hexdigest() == image_digest
                checks.append(('标记图片回来了且校验和一致', bool(digest_ok),
                               '文件不存在' if not exists else '校验和不一致'))

            now_total = DetectionHistory.objects.count()
            checks.append((f'识别记录条数回到基线（{now_total}/{detection_total}）',
                           now_total == detection_total, ''))
            if victim_ids:
                back = DetectionHistory.objects.filter(id__in=victim_ids).count()
                checks.append((f'被删的 {len(victim_ids)} 条识别记录都回来了',
                               back == len(victim_ids), f'实际回来 {back} 条'))

        except Exception as exc:  # noqa: BLE001 —— 失败也要给结论与"保留备份"的提示
            self._bad(f'演练中断：{type(exc).__name__}: {exc}')
            if backup_name:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠️ 演练备份**已保留**：{backup_name}\n'
                    f'     需要回到原状态可执行：python manage.py backend_restore {backup_name} '
                    f'--yes --overwrite-media'))
            raise

        # ---------- 结论 ----------
        self.stdout.write('\n' + '=' * 72)
        passed = 0
        for name, ok, note in checks:
            (self._ok if ok else self._bad)(f'{name}{f"（{note}）" if note and not ok else ""}')
            passed += 1 if ok else 0
        self.stdout.write('=' * 72)

        if passed != len(checks):
            if backup_name:
                self.stdout.write(self.style.WARNING(
                    f'演练备份已保留：{backup_name}（用于排查与回到原状态）'))
            raise CommandError(f'演练失败：{passed}/{len(checks)} 项通过 —— **这套备份不可信**，'
                               f'别把它当成"有备份"。')

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ 演练通过：{passed}/{len(checks)} 项 —— 备份**确实能恢复**（{backup_name}）'))

        # 收拾干净：`backend_restore` 的"安全网 4"会把替换前的库另存为
        # `db.sqlite3.pre-restore` —— 那是**含真实用户表与口令哈希的整库副本**，
        # 演练已经证明当前库是好的，就别把它留在工作区里（第 154 批实测：它当时
        # 出现在 git status 的未跟踪列表里，而 `db.sqlite3` 的忽略规则匹配不到它）。
        pre_restore = Path(settings.DATABASES['default']['NAME']).with_suffix(
            Path(settings.DATABASES['default']['NAME']).suffix + '.pre-restore')
        if pre_restore.exists():
            pre_restore.unlink()
            self.stdout.write(f'（已删除恢复过程留下的库副本 {pre_restore.name}'
                              f'；它含真实用户表，即便 .gitignore 已覆盖也不该留在工作区）')

        if not options['keep'] and backup_name:
            import shutil
            shutil.rmtree(bu.backup_root() / backup_name, ignore_errors=True)
            self.stdout.write(f'（已删除演练备份 {backup_name}；加 --keep 可保留）')


def _dir_size(path: Path) -> int:
    """备份目录总大小（给输出用）"""
    total = 0
    for item in path.rglob('*'):
        if item.is_file():
            total += item.stat().st_size
    return total
