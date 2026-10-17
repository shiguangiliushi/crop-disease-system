"""
环境自检（第 94 批）

==================================================================
为什么需要它
==================================================================
`requirements.txt` 曾经只有 8 行、且**装不出可运行的环境**（缺
django-cors-headers / django-filter / reportlab，版本也与开发环境全不一致）。
问题不是"少了几个包"，而是**这件事没有任何人会发现**，直到某天有人真的按它装一次 ——
而那时通常已经是在部署现场了。

这个命令把"环境对不对"变成一条可以随时跑、可以在 CI 里跑的检查：

    python manage.py check_env              # 人看的报告
    python manage.py check_env --strict     # 有缺失/不一致就退出码 1（CI 用）

它做四件事：
  1. 对照 `requirements.txt` 检查每个包的**实际安装版本**是否符合约束；
  2. 检查 `INSTALLED_APPS` 里依赖的第三方应用是否真的装上了（django-cors-headers、
     django-filter 这两个就是历史上漏掉的）；
  3. 检查关键运行时能力：数据库连通、缓存可用、迁移是否都应用了、模型文件在不在；
  4. 把**生产模式下容易忘的开关**列出来（DEBUG / SECRET_KEY / ALLOWED_HOSTS /
     HTTPS 相关），但只提示不拦截 —— 因为开发环境本来就该是 DEBUG=True。

设计原则：**只报告，不修改**。任何"帮你自动修好"的行为都会让环境问题更难理解。
"""
from __future__ import annotations

import importlib
import re
import os
import platform
import sys
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand

#: requirements.txt 里的版本运算符（只支持这几种，够用）
_VERSION_RE = re.compile(r'^\s*([A-Za-z0-9_.\-]+)\s*(==|>=|<=|~=|>|<)?\s*([0-9][\w.\-]*)?')


def _parse_requirements(path: Path) -> list[tuple[str, str, str]]:
    """解析 requirements 文件 → [(包名, 运算符, 版本)]，注释与空行跳过"""
    result = []
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line or line.startswith('-'):
            continue
        match = _VERSION_RE.match(line)
        if not match:
            continue
        name, op, version = match.group(1), match.group(2) or '', match.group(3) or ''
        result.append((name, op, version))
    return result


def _installed_version(package: str) -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError, version
        return version(package)
    except Exception:  # noqa: BLE001  没装 / 元数据坏了
        return None


def _satisfies(installed: str, op: str, wanted: str) -> bool:
    """版本比较。用 packaging 做语义化比较；它没装时退化为**只比字符串相等**并提示。"""
    if not op or not wanted:
        return True
    try:
        from packaging.version import Version
        left, right = Version(installed), Version(wanted)
    except Exception:  # noqa: BLE001
        return installed == wanted
    return {
        '==': left == right,
        '>=': left >= right,
        '<=': left <= right,
        '>': left > right,
        '<': left < right,
        '~=': left >= right and left.release[: len(right.release) - 1] == right.release[:-1],
    }.get(op, True)


class Command(BaseCommand):
    help = '对照 requirements.txt 检查运行环境（缺包 / 版本不符 / 迁移未应用 / 关键能力）'

    def add_arguments(self, parser):
        parser.add_argument('--strict', action='store_true',
                            help='有缺失或不一致时以退出码 1 结束（CI 用）')
        parser.add_argument('--requirements', default='requirements.txt',
                            help='要对照的 requirements 文件（默认 requirements.txt）')
        parser.add_argument('--quiet', action='store_true', help='只输出问题')
        # 第 157 批：`--json` 让**管理端的「系统健康」页**直接复用这套检查，
        # 而不是在接口里再写一遍（"同一个检查写两份"正是本项目反复强调要避免的）。
        parser.add_argument('--json', dest='as_json', action='store_true',
                            help='以 JSON 输出（给接口/监控用；不打印人能读的报告）')

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        strict = options['strict']
        quiet = options['quiet']
        as_json = options.get('as_json', False)
        base = Path(settings.BASE_DIR)
        req_path = Path(options['requirements'])
        if not req_path.is_absolute():
            req_path = base / req_path

        self.problems: list[str] = []
        self.warnings: list[str] = []
        #: 结构化结果（每一条 = 一个检查项），给 --json 与管理端健康页用
        self.results: list[dict] = []
        #: `--json` 模式下**只**输出 JSON —— 否则 stdout 里前面还混着人读报告，
        #: 监控侧 `json.loads(stdout)` 直接失败（第一版就是这样）
        self._silent = as_json

        # ══════════════════════════════════════════════════════════════════
        # 第 223 批：**先报跑在哪个解释器上**
        #
        # 起因：管理端「系统健康」爆红 7 项，全是"依赖版本不符"；而 `requirements.txt`
        # 与项目那套 conda 环境（`crop_env`）**逐项一致** —— 真正的原因是 dev server
        # 跑在仓库里一份 gitignored 的旧 `backend/venv` 上。
        #
        # 没有这一行时，第一反应必然是"依赖装坏了"，接着就是去升级 torch（几百 MB、
        # 风险极高）—— 而真正该做的是换个解释器。**环境问题的第一诊断信息是解释器路径**。
        # ══════════════════════════════════════════════════════════════════
        self._section('〇、运行环境（版本不符时先看这里）', quiet)
        in_venv = sys.prefix != getattr(sys, 'base_prefix', sys.prefix)
        self._ok(f'解释器：{sys.executable}', quiet)
        #: ⚠️ 第 223 批：**conda 环境不算 venv**。
        #: conda 里 `sys.prefix == sys.base_prefix`（它不使用 venv 那套语义），
        #: 只看 venv 判据会把 conda 环境报成「系统/基础环境」—— 而本项目的约定环境
        #: 恰恰就是 conda 的 `crop_env`。报错成"系统环境"会把人引到完全错误的方向。
        conda_prefix = os.environ.get('CONDA_PREFIX') or ''
        looks_conda = bool(conda_prefix) or '\\envs\\' in sys.prefix or '/envs/' in sys.prefix
        if in_venv:
            env_desc = f'虚拟环境：{sys.prefix}'
        elif looks_conda:
            env_desc = f'conda 环境：{conda_prefix or sys.prefix}'
        else:
            env_desc = '系统/基础环境（未使用虚拟环境或 conda）'
        self._ok(f'Python {platform.python_version()}（{env_desc}）', quiet)
        #: 仓库里自带一份 venv 是**最容易被误用**的情形：它 gitignored、不会同步，
        #: 却和项目共用同一个 BASE_DIR。命中时直接点出来。
        repo_venv = str(base) in sys.prefix or str(base) in str(Path(sys.executable).parent)
        if in_venv and repo_venv:
            self._warn(
                '使用的解释器位于**仓库目录内**（通常是某次本地临时建的 venv）。'
                '它不是项目约定的环境、也不随仓库同步 —— 若依赖版本不符，'
                '请改用项目约定的解释器再跑一次，而不是去升级包',
                quiet=quiet,
            )

        self._section('一、依赖包（对照 %s）' % req_path.name, quiet)
        if not req_path.exists():
            self.problems.append(f'找不到 {req_path}')
            self._bad(f'找不到 {req_path}')
        else:
            self._check_requirements(req_path, quiet)

        self._section('二、INSTALLED_APPS 依赖的第三方应用', quiet)
        self._check_installed_apps(quiet)

        self._section('三、运行时能力', quiet)
        self._check_runtime(quiet)

        self._section('四、生产模式开关（仅提示）', quiet)
        self._check_production_switches(quiet)

        if as_json:
            import json as _json
            self.stdout.write(_json.dumps({
                'ok': not self.problems,
                'problems': self.problems,
                'warnings': self.warnings,
                'results': self.results,
            }, ensure_ascii=False))
            if strict and self.problems:
                raise SystemExit(1)
            return

        #: 第 223 批：版本不符时把"先确认解释器"写进提示里 —— 否则看报告的人
        #: 只会想到升级包，而升级 torch 这种动作代价极高、且常常根本不是问题所在。
        if any('版本不符' in item for item in self.problems):
            self.warnings.append(
                f'有依赖版本不符：先确认这次跑的是不是约定的解释器（本次：{sys.executable}）。'
                f'{req_path.name} 对应的可能是另一套环境 —— 换解释器重跑，往往就不红了'
            )

        # ---------------- 汇总 ----------------
        self.stdout.write('')
        if self.problems:
            self.stdout.write(self.style.ERROR(f'✗ {len(self.problems)} 个问题：'))
            for item in self.problems:
                self.stdout.write(self.style.ERROR(f'  · {item}'))
        if self.warnings:
            self.stdout.write(self.style.WARNING(f'⚠ {len(self.warnings)} 条提示：'))
            for item in self.warnings:
                self.stdout.write(self.style.WARNING(f'  · {item}'))
        if not self.problems:
            self.stdout.write(self.style.SUCCESS('✓ 环境自检通过（依赖、应用、数据库、迁移、模型文件）'))

        if strict and self.problems:
            raise SystemExit(1)

    # ------------------------------------------------------------------
    def _record(self, level, text, section=None):
        """记一条结构化结果（第 157 批）—— 让 `--json` 与健康页拿到的是数据而不是文本"""
        self.results.append({
            'level': level,                 # ok / warn / fail
            'text': text,
            'section': section or getattr(self, '_current_section', ''),
        })

    def _section(self, title, quiet):
        self._current_section = title
        if not quiet and not self._silent:
            self.stdout.write(self.style.MIGRATE_HEADING(f'\n{title}'))

    def _ok(self, text, quiet):
        self._record('ok', text)
        if not quiet and not self._silent:
            self.stdout.write(f'  ✓ {text}')

    def _bad(self, text):
        self._record('fail', text)
        if not self._silent:
            self.stdout.write(self.style.ERROR(f'  ✗ {text}'))

    def _warn(self, text, quiet=False):
        self._record('warn', text)
        if not quiet and not self._silent:
            self.stdout.write(self.style.WARNING(f'  ⚠ {text}'))

    # ------------------------------------------------------------------
    def _check_requirements(self, req_path: Path, quiet: bool):
        entries = _parse_requirements(req_path)
        if not entries:
            self.warnings.append(f'{req_path.name} 里没有解析到任何依赖')
            return
        for name, op, wanted in entries:
            installed = _installed_version(name)
            if installed is None:
                self.problems.append(f'{name} 未安装（{req_path.name} 要求 {op}{wanted}）')
                self._bad(f'{name:24s} 未安装')
                continue
            if not _satisfies(installed, op, wanted):
                self.problems.append(
                    f'{name} 版本不符：已装 {installed}，要求 {op}{wanted}'
                )
                self._bad(f'{name:24s} 已装 {installed}，要求 {op}{wanted}')
                continue
            self._ok(f'{name:24s} {installed}', quiet)

    def _check_installed_apps(self, quiet: bool):
        """
        逐个 import `INSTALLED_APPS` 里的第三方应用。

        为什么单独查这一项：django-cors-headers 与 django-filter **曾经就是漏装的** ——
        `INSTALLED_APPS` 里写着它们，代码里用着它们，但 requirements.txt 里没有，
        于是"照文档装一次"必然启动失败。这条检查就是专门防这个的。
        """
        for entry in settings.INSTALLED_APPS:
            # 本地应用不用查（已经在跑了）；Django 自带的也跳过
            if entry == 'api' or entry.startswith('django.'):
                continue
            try:
                module = importlib.import_module(entry)
                # django-filter 的包名是 django_filters，但应用名写的是 'django_filters'，
                # 这里只验证"能导入"，包名与版本由第一节的 requirements 对照负责
                version = getattr(module, '__version__', '')
                suffix = f'（{version}）' if version else ''
                self._ok(f'{entry} 可导入{suffix}', quiet)
            except Exception as exc:  # noqa: BLE001
                self.problems.append(f'INSTALLED_APPS 里的 {entry} 导入失败：{exc}')
                self._bad(f'{entry} 导入失败：{exc}')

    def _check_runtime(self, quiet: bool):
        # 1) 数据库
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            engine = settings.DATABASES['default']['ENGINE'].rsplit('.', 1)[-1]
            self._ok(f'数据库连接正常（{engine}）', quiet)
        except Exception as exc:  # noqa: BLE001
            self.problems.append(f'数据库连接失败：{exc}')
            self._bad(f'数据库连接失败：{exc}')

        # 2) 缓存（限流计数器依赖它；生产若还是 LocMem，多 worker 会各算一份）
        try:
            from django.core.cache import cache
            cache.set('__check_env__', '1', 5)
            ok = cache.get('__check_env__') == '1'
            backend = settings.CACHES['default']['BACKEND'].rsplit('.', 1)[-1]
            shared = getattr(settings, 'CACHE_IS_SHARED', None)
            if ok:
                self._ok(f'缓存可用（{backend}，跨进程共享={shared}）', quiet)
                if not settings.DEBUG and not shared:
                    self.warnings.append(
                        f'生产模式下的缓存是 {backend}（**不跨进程**）：多 worker 下限流计数各算一份，'
                        '等于限流失效。请设 DJANGO_CACHE_URL=redis://127.0.0.1:6379/1 '
                        '（并安装 redis 包，见 requirements-prod.txt）。'
                    )
                    self._warn(f'缓存 {backend} 不跨进程：多 worker 下限流会失效')
            else:
                self.problems.append('缓存读写异常')
                self._bad('缓存读写异常')
        except Exception as exc:  # noqa: BLE001
            self.problems.append(f'缓存不可用：{exc}')
            self._bad(f'缓存不可用：{exc}')

        # 3) 迁移是否都应用了
        try:
            from django.db import connection
            from django.db.migrations.executor import MigrationExecutor
            executor = MigrationExecutor(connection)
            # ⚠️ 用 migration_plan()，不要用 migrate(..., plan=True)：
            # 后者在新版 Django 里返回的是 bool（"有没有执行"），不是计划列表，
            # 拿它去判空会得到 "'bool' object is not iterable"。
            pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
            if pending:
                self.problems.append(f'有 {len(pending)} 个迁移未应用（跑 migrate）')
                self._bad(f'有 {len(pending)} 个迁移未应用 —— 请执行 python manage.py migrate')
            else:
                self._ok('迁移已全部应用', quiet)
        except Exception as exc:  # noqa: BLE001
            self.warnings.append(f'无法检查迁移状态：{exc}')

        # 4) 识别模型文件（按**实际加载优先级**报，不要只看文件大小）
        from pathlib import Path as _P
        api_dir = _P(settings.BASE_DIR) / 'api'
        #: ⚠️ 第 223 批：这里的候选**必须与 `ai_service` 完全一致**。
        #:
        #: 原来多列了一个「兜底（仓库根 yolov8n.pt）」，而 `ai_service.__new__` 只会尝试
        #: `api/newmodels/best.pt` → `api/models/best.pt`，**从不加载仓库根的 yolov8n.pt**。
        #: 于是当两处权重都缺、只剩 yolov8n.pt 时，报告会显示「✓ 模型文件：yolov8n.pt」，
        #: 而识别接口实际返回 503 —— **假绿**，比没检查更糟。
        #:
        #: 同时把"多份权重"的提示改准：
        #:   · 首选在位、回退也在 → **正常**（回退就是为此存在的），不再报警；
        #:   · 首选缺失、只能用回退 → **要提醒**（回退权重类数更少，识别面会变窄）；
        #:   · 两处都缺 → 识别必然 503，按问题上报（不再只是提示）。
        candidates = [
            ('首选（api/newmodels/）', api_dir / 'newmodels' / 'best.pt'),
            ('回退（api/models/）', api_dir / 'models' / 'best.pt'),
        ]
        preferred_path = candidates[0][1]
        picked = next(((label, path) for label, path in candidates if path.exists()), None)
        if picked:
            label, path = picked
            others = [p for _, p in candidates if p.exists() and p != path]
            note = ''
            if others:
                note = '；回退权重也在（api/models/best.pt，正常保留）'
            #: 仓库根那份 yolov8n.pt 是 ultralytics 下载的基础模型，**不在加载链路上** ——
            #: 提一句就够，不该混进"候选"里，也不该变成警告。
            stray = _P(settings.BASE_DIR) / 'yolov8n.pt'
            if stray.exists():
                note += '；另有仓库根 yolov8n.pt（ultralytics 基础模型，不参与识别）'
            self._ok(
                f'模型文件：{path.relative_to(_P(settings.BASE_DIR))}'
                f'（{label}，{path.stat().st_size / 1024 / 1024:.1f} MB）{note}', quiet
            )
            if path != preferred_path:
                self.warnings.append(
                    '首选权重 api/newmodels/best.pt 不存在，正在用**回退权重** api/models/best.pt '
                    '—— 它的病害类数更少，能识别的范围比首选的窄'
                )
        else:
            #: 两处都没有 = 识别必然 503，这是**问题**而不是提示
            msg = '没找到模型权重（api/newmodels/best.pt 与 api/models/best.pt 都不存在）—— 识别接口会返回 503'
            self.problems.append(msg)
            self._bad(msg)

        # 5) 媒体/静态目录可写（上传头像、帖子配图要用）
        for name in ('MEDIA_ROOT', 'STATIC_ROOT'):
            path = _P(getattr(settings, name, '') or '')
            if not str(path):
                continue
            try:
                path.mkdir(parents=True, exist_ok=True)
                probe = path / '.check_env_probe'
                probe.write_text('ok', encoding='utf-8')
                probe.unlink()
                self._ok(f'{name} 可写：{path}', quiet)
            except Exception as exc:  # noqa: BLE001
                self.warnings.append(f'{name} 不可写或创建失败：{exc}')

        # 6) 注销冷静期：有没有**到期却还没执行**的申请（第 101 批）
        #
        # 为什么值得单独查：冷静期到期是**定时任务**触发的，没有任何请求会触发它。
        # 定时任务没挂上 / 挂了没跑，后果是"用户以为账号已注销，个人信息却还在库里" ——
        # 属于"说好的事没做"，比不能注销更糟。这里把积压数量显式报出来。
        try:
            from django.utils import timezone as _tz
            from api.models import CustomUser as _User
            pending = _User.objects.filter(
                is_deleted=False, deletion_scheduled_for__isnull=False,
                deletion_scheduled_for__lte=_tz.now(),
            ).count()
            waiting = _User.objects.filter(
                is_deleted=False, deletion_scheduled_for__isnull=True,
                deletion_requested_at__isnull=False,
            ).count()
            if pending:
                self.warnings.append(
                    f'有 {pending} 个注销申请已到期但**尚未执行**：'
                    '请挂上定时任务 `manage.py purge_deletion_requests`'
                    '（未配置的话用户以为账号已删，实际个人信息仍在库里）'
                )
                self._warn(f'注销冷静期到期未执行：{pending} 个')
            elif waiting:
                self._ok(f'注销冷静期进行中：{waiting} 个（到期后由定时任务执行）', quiet)
            else:
                self._ok('没有待执行的注销申请', quiet)
        except Exception as exc:  # noqa: BLE001
            self.warnings.append(f'无法检查注销申请状态：{exc}')

        # 7) 备份新鲜度（第 102 批）
        #
        # 为什么放进环境自检：备份是**唯一**能在"数据被删/库损坏"时救命的东西，
        # 而它的失败方式是安静的 —— 定时任务挂了没人知道，直到真出事那天。
        # 这里只做"有没有 / 多久没成功 / 最新一份能不能读出条数"三件事。
        try:
            from api import backup_utils as _bu

            root = _bu.backup_root()
            backups = [p for p in _bu.list_backups(root) if (p / _bu.MANIFEST_NAME).exists()]
            if not backups:
                self.warnings.append(
                    f'没有任何备份（{root} 下为空）：请跑 `manage.py backend_backup`，'
                    '并挂上定时任务（见 docs/备份与恢复.md）'
                )
                self._warn(f'没有任何备份：{root}')
            else:
                latest = backups[0]
                manifest = _bu.read_json(latest / _bu.MANIFEST_NAME)
                created = str(manifest.get('created_at') or '')
                age_hours = None
                if created:
                    from datetime import datetime
                    try:
                        parsed = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        age_hours = (timezone.now() - parsed).total_seconds() / 3600
                    except Exception:  # noqa: BLE001
                        age_hours = None

                size = _bu.human_size(manifest.get('total_bytes') or 0)
                if age_hours is None:
                    self._ok(f'最新备份：{latest.name}（{size}）', quiet)
                elif age_hours > 72:
                    self.warnings.append(
                        f'最新备份已 {age_hours / 24:.1f} 天前（{latest.name}）：'
                        '定时任务可能没跑，请检查'
                    )
                    self._warn(f'最新备份已 {age_hours / 24:.1f} 天前')
                else:
                    self._ok(f'最新备份：{latest.name}（{size}，{age_hours:.1f} 小时前）', quiet)
        except Exception as exc:  # noqa: BLE001
            self.warnings.append(f'无法检查备份状态：{exc}')

    def _check_production_switches(self, quiet: bool):
        """
        只提示、不拦截。

        开发环境 DEBUG=True 是**正确**的；这里列出的是"上线前必须确认"的几项，
        让人在部署前来得及看见，而不是等出事。
        """
        items = []
        if settings.DEBUG:
            items.append('DJANGO_DEBUG=True（开发模式；生产必须 False）')
        if '*' in settings.ALLOWED_HOSTS:
            items.append('DJANGO_ALLOWED_HOSTS=*（生产请写具体域名/IP）')
        if not getattr(settings, 'SECURE_SSL_REDIRECT', False):
            items.append('SECURE_SSL_REDIRECT 未开（生产走 HTTPS 时建议开）')
        if not getattr(settings, 'SECURE_HSTS_SECONDS', 0):
            items.append('SECURE_HSTS_SECONDS=0（上 HTTPS 稳定后再开 HSTS）')
        if settings.EMAIL_BACKEND.endswith('console.EmailBackend'):
            items.append('邮件走控制台后端（找回密码的链接会打进日志，生产请配 SMTP）')

        if not items:
            self._ok('生产开关看起来都已设置', quiet)
            return
        for item in items:
            self._warn(item)
