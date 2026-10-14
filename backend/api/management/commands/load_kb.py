"""`load_kb` —— 把校准版知识库导入系统的命令。

## 两种模式（**必须显式选一个**，不选会被拒绝）

    python manage.py load_kb --dry-run              # 只读比对（K1），不写任何数据
    python manage.py load_kb --apply                # 真正写库（K3）
    python manage.py load_kb --dry-run --verbose    # 额外打印每个字段的 旧长度→新长度
    python manage.py load_kb --dry-run --strict     # 有任何未匹配/缺失就退出码 1

## 为什么必须先跑 dry-run

语料入库是"一写就落地、错了要回滚"的操作，而它有两个**只能靠比对发现**的错配点：

1. **两条名字不一致**：JSON 写「番茄斑靶病」，库里叫「番茄靶斑病」；
   JSON 写「健康桃子」，库里叫「健康桃」。按名字直查会**静默漏掉**它们。
2. **重复词条风险**：`pumpkin_powdery_mildew`（南瓜白粉病）与模型类
   `Squash___Powdery_mildew` 指向同一种病 —— 写之前要先看清库里到底有几条同名词条，
   否则百科里会出现两条「南瓜白粉病」。

所以 `--dry-run` 的输出目标是：**让每一处匹配/未匹配都能被人一眼核对**，
包括"用哪种方式匹配上的"（中文名 / 别名表）以及"会删掉多少旧数据"。

## `--apply` 的有损点（只有一个，且是刻意的）

每个病害名下**先删旧防治再写新版**：`PreventionMethod` 没有唯一约束，
不先删就会每次导入翻倍。代价是旧措施被清掉 —— 所以**写入前必须有备份**：

    python manage.py backend_backup --label before-kb-import
    python manage.py backup_verify --strict

写入整体在**一个事务**里：任何一条失败都全部回滚，不会留下半套数据。
写完**再跑一次 `--dry-run`**，"将被替换"应当变成 0 —— 这就是幂等性的验收标准。

## 与 `docs/tools/check_kb_coverage.py` 的分工

那个脚本核对的是「模型 38 类 ↔ 词条 ↔ 校准版」的**覆盖面**（不读 Django）；
本命令核对的是「**落到哪一行、改哪几个字段、写几条防治**」（要走 ORM）。
两者互补：前者回答"有没有漏"，后者回答"写到哪去"。
"""
from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import CropHealthProfile, PestInfo, PreventionMethod

#: JSON 维度 → 落点。`PestInfo` 用字段名，防治用 category。**改这里就是改口径。**
DISEASE_FIELD_MAP = {
    '症状描述': ('pest', 'symptoms'),
    '发病规律': ('pest', 'description'),
    '农业防治': ('prevention', 'AGRICULTURAL'),
    '化学防治': ('prevention', 'CHEMICAL'),
    '生态防治': ('prevention', 'ECOLOGICAL'),
    '物理防治': ('prevention', 'PHYSICAL'),
    '监测预警': ('prevention', 'MONITORING'),
}

#: healthy 记录的 7 个维度 —— 目前**没有落点**（需要先建 CropHealthProfile，见 K2）
HEALTHY_DIMENSIONS = (
    '健康形态特征', '健康生长条件', '农业健康管理', '化学保护',
    '生态健康管理', '物理保护', '健康监测',
)

#: 两条已知的名字不一致。方向：**校准版 → 库**（与 check_kb_coverage.py 保持一致）。
#: ⚠️ 判断时要反查（库名 → 校准版名），写反了这两条会永远报"未匹配"。
NAME_ALIAS = {
    '番茄斑靶病': '番茄靶斑病',
    '健康桃子': '健康桃',
}
#: 库中中文名 → 校准版中文名
KB_NAME_OF = {db_name: kb_name for kb_name, db_name in NAME_ALIAS.items()}

#: 默认语料路径（相对 backend/ 的上一级）
DEFAULT_JSON = Path('..') / 'docs' / 'knowledge_base' / '作物病害知识库_校准版.json'


class Command(BaseCommand):
    help = ('导入校准版知识库：--dry-run 只读比对；--apply 真正写库（先删后写，需先备份）')

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='只读比对并打印报告，不写任何数据',
        )
        parser.add_argument(
            '--apply', action='store_true',
            help='真正写库（K3）。**有损**：先删每个病害名下的旧防治再写新版；'
                 '执行前请先备份（python manage.py backend_backup --label before-kb-import）',
        )
        parser.add_argument(
            '--json', default=str(DEFAULT_JSON),
            help=f'校准版 JSON 路径（默认 {DEFAULT_JSON}）',
        )
        parser.add_argument('--verbose', action='store_true', help='逐字段打印 旧长度 → 新长度')
        parser.add_argument('--strict', action='store_true', help='有未匹配/缺失时退出码 1')

    # ── 输出小工具（对齐 check_env.py 的写法）──────────────────────────────
    def _section(self, title: str) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n{title}'))

    def _ok(self, text: str) -> None:
        self.stdout.write(f'  ✓ {text}')

    def _warn(self, text: str) -> None:
        self.stdout.write(self.style.WARNING(f'  ⚠ {text}'))

    def _bad(self, text: str) -> None:
        self.stdout.write(self.style.ERROR(f'  ✗ {text}'))

    # ── 主流程 ────────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        self.verbose = options['verbose']
        self.problems: list[str] = []
        self.warnings: list[str] = []
        self.to_pest_fields = 0      # 将更新的 PestInfo 字段数
        self.to_prevent = 0          # 将写入的防治条数
        self.unchanged = 0           # 内容已一致的字段/防治
        self.healthy_records = 0     # healthy 记录（K2 后落 CropHealthProfile）
        self.healthy_matched = 0     # 其中能接上 PestInfo 的
        self.prev_old = 0            # 本轮涉及词条名下的现有防治条数（将被删）
        self.prev_new = 0            # 计划写入的防治条数
        self.prev_identical = 0      # 其中内容其实没变的
        self.prev_deleted = 0        # 会被真正删掉（内容不同）的

        dry_run = options['dry_run']
        apply_mode = options['apply']
        if not dry_run and not apply_mode:
            raise CommandError(
                '请显式选择模式：--dry-run（只读比对，推荐先跑）或 --apply（真正写库）。'
            )
        if dry_run and apply_mode:
            raise CommandError('--dry-run 与 --apply 不能同时使用。')

        self._check_llm_channel()
        payload = self._load_json(Path(options['json']))
        self._compare(payload)
        self._summary()
        self._maybe_report_duplicate_names()

        if apply_mode:
            self._apply(payload)

        if options['strict'] and (self.problems or self.warnings):
            raise CommandError(
                f'--strict：有 {len(self.problems)} 个问题 / {len(self.warnings)} 条提示，需要人工确认'
            )

    # ── 步骤 1：环境（顺带确认 LLM 通道配置就位）────────────────────────────
    def _check_llm_channel(self) -> None:
        import os
        self._section('一、环境')
        enabled = os.environ.get('LLM_ENABLED', '')
        key = os.environ.get('LLM_API_KEY', '')
        url = os.environ.get('LLM_API_URL', '')
        model = os.environ.get('LLM_MODEL', '')
        self._ok(f'LLM_ENABLED={enabled or "(未设置)"}  LLM_MODEL={model or "(未设置)"}')
        if key:
            self._ok(f'LLM_API_KEY 已设置（长度 {len(key)}，前缀 {key[:3]}）  URL={url}')
        else:
            self._warn('LLM_API_KEY 未设置 —— 助手将只能降级返回词条原文')
        fields = [f.name for f in PestInfo._meta.get_fields()]
        for name in ('scientific_name', 'sources'):
            if name in fields:
                self._ok(f'PestInfo.{name} 已存在')
            else:
                self._bad(f'PestInfo.{name} **不存在** —— 请先完成 K2 迁移（makemigrations + migrate）')
                self.problems.append(f'缺字段 PestInfo.{name}（K2 迁移未做）')
        if CropHealthProfile._meta.db_table:
            self._ok(f'CropHealthProfile 已建（表 {CropHealthProfile._meta.db_table}）')
        else:
            self.problems.append('缺表 CropHealthProfile（K2 迁移未做）')

    # ── 步骤 2：读 JSON ──────────────────────────────────────────────────
    def _load_json(self, path: Path) -> dict:
        self._section('二、语料文件')
        if not path.exists():
            raise CommandError(f'找不到校准版 JSON：{path.resolve()}')
        payload = json.loads(path.read_text(encoding='utf-8'))
        meta = payload.get('metadata', {})
        records = payload.get('records', [])
        self._ok(f'{path} —— {len(records)} 条记录')
        self._ok(
            f'version={meta.get("version")}  校准日期={meta.get("calibration_date")}  '
            f'自述 {meta.get("disease_count")} 病 + {meta.get("healthy_count")} 健康'
        )
        actual_disease = sum(1 for r in records if r.get('category') == 'disease')
        actual_healthy = sum(1 for r in records if r.get('category') == 'healthy')
        if actual_disease != meta.get('disease_count') or actual_healthy != meta.get('healthy_count'):
            self._bad(f'记录数与 metadata 自述不符：实际 {actual_disease} 病 + {actual_healthy} 健康')
            self.problems.append('metadata 与记录数不符')
        return payload

    # ── 步骤 3：逐条比对 ─────────────────────────────────────────────────
    def _resolve(self, record: dict) -> tuple[PestInfo | None, str]:
        """把一条 JSON 记录落到库里的词条上。返回 (词条, 匹配方式)。"""
        name = record['name']
        by_name = PestInfo.objects.filter(name=name).first()
        if by_name:
            return by_name, '中文名直配'
        # 别名：库里的名字 ← 校准版的名字
        for db_name, kb_name in KB_NAME_OF.items():
            if kb_name == name:
                hit = PestInfo.objects.filter(name=db_name).first()
                if hit:
                    return hit, f'别名表（库名「{db_name}」）'
        return None, '未匹配'

    def _compare(self, payload: dict) -> None:
        self._section('三、逐条比对（只读）')
        header = (f'{"#":>3}  {"校准版名称":<14} {"库中名称":<12} {"匹配方式":<22} '
                  f'{"防治 现有→将写":<16} {"构成":<12} 判定')
        self.stdout.write('  ' + header)
        self.stdout.write('  ' + '─' * 118)

        for index, record in enumerate(payload['records'], start=1):
            name = record['name']
            category = record.get('category')
            dims = record.get('dimensions', {})

            if category == 'healthy':
                self.healthy_records += 1
                pest, how = self._resolve(record)
                label = pest.name if pest else '（未匹配）'
                missing = [d for d in HEALTHY_DIMENSIONS if not dims.get(d)]
                if pest:
                    self.healthy_matched += 1
                    # K2 之后有了落点：这一条会写进 CropHealthProfile（按 pest 一对一）。
                    # 判定要区分"新建 / 有差异 / 已一致"，不能一律写"将更新档案" ——
                    # 写入后重跑时仍显示"将更新"会让人以为还要再写一次。
                    existing = CropHealthProfile.objects.filter(pest=pest).first()
                    if existing is None:
                        note = '将新建档案'
                    else:
                        differs = (
                            existing.name != record['name']
                            or existing.scientific_name != (record.get('scientific_name') or '')
                            or existing.sources != (record.get('sources') or [])
                            or any(
                                getattr(existing, field) != (dims.get(dim_key) or '').strip()
                                for dim_key, field in CropHealthProfile.DIMENSION_FIELDS.items()
                            )
                        )
                        note = '将更新档案' if differs else '档案已一致'
                else:
                    note = '⚠ 未匹配到词条'
                    self.warnings.append(f'healthy 记录未匹配：{name}')
                if missing:
                    self.warnings.append(f'{name} 缺少维度：{missing}')
                self.stdout.write(
                    f'  {index:>3}  {name:<14} {label:<12} {how:<22} {"—":<16} {"档案":<12} {note}'
                )
                continue

            pest, how = self._resolve(record)
            if not pest:
                self._bad(f'{index:>3}  {name} —— 未匹配到任何词条')
                self.problems.append(f'未匹配：{name}')
                continue

            # ① PestInfo 的两个知识字段
            #
            # ⚠️ `field_changes` **只在真有差异时**追加。第一版无条件追加，
            #    于是"判定"列永远算出"将更新" —— 明明 symptoms/description 长度一模一样。
            #    （表现：verbose 里打印 `symptoms: 162→162` 却判"将更新"，自相矛盾。）
            field_changes = []
            for dim_key, (target, field) in DISEASE_FIELD_MAP.items():
                if target != 'pest':
                    continue
                new_value = (dims.get(dim_key) or '').strip()
                if not new_value:
                    self.warnings.append(f'{name} 的「{dim_key}」为空')
                    continue
                old_value = (getattr(pest, field, '') or '')
                if new_value != old_value:
                    self.to_pest_fields += 1
                    field_changes.append(f'{field}: {len(old_value)}→{len(new_value)}')
                else:
                    self.unchanged += 1
                    field_changes.append(f'{field}: {len(old_value)}=同')

            # ② 防治措施：先删该 pest 的旧记录再写（该表无唯一约束，必须幂等）
            #
            # ⚠️ 这是**有损**操作：写入前会 `delete()` 该 pest 的全部旧措施。
            #    所以这里必须把"删几条、其中几条内容其实一样"如实算出来 ——
            #    只报"将写 130 条"会把"190 条被替换"这件事藏起来。
            existing_rows = list(PreventionMethod.objects.filter(pest=pest))
            existing_by_cat = {row.category: row for row in existing_rows}
            existing_total = len(existing_rows)
            planned = 0
            identical = n_new = n_changed = 0
            per_cat_notes = []
            for dim_key, (target, category_code) in DISEASE_FIELD_MAP.items():
                if target != 'prevention':
                    continue
                new_value = (dims.get(dim_key) or '').strip()
                if not new_value:
                    self.warnings.append(f'{name} 的「{dim_key}」为空')
                    continue
                planned += 1
                self.to_prevent += 1
                old_row = existing_by_cat.get(category_code)
                if old_row is None:
                    n_new += 1
                    per_cat_notes.append(f'{category_code[:4]}:新')
                elif (old_row.measure or '').strip() == new_value:
                    identical += 1
                    self.unchanged += 1
                    per_cat_notes.append(f'{category_code[:4]}:同')
                else:
                    n_changed += 1
                    per_cat_notes.append(f'{category_code[:4]}:改')
            self.prev_old += existing_total
            self.prev_new += planned
            self.prev_identical += identical
            self.prev_deleted += existing_total - identical

            # ③ 学名与来源：同样要能报"是否已一致"，
            #    否则 K3 写完再跑 dry-run 时，这一行仍会显示"将更新"（第一版就漏了这两个字段）。
            sci_new = (record.get('scientific_name') or '').strip()
            src_new = record.get('sources') or []
            sci_changed = bool(sci_new) and pest.scientific_name != sci_new
            src_changed = bool(src_new) and pest.sources != src_new
            if sci_changed:
                field_changes.append(f'scientific_name: {len(pest.scientific_name or "")}→{len(sci_new)}')
            if src_changed:
                field_changes.append(f'sources: {len(pest.sources or [])}→{len(src_new)} 条')

            # 判定必须反映**真实差异**：已写入后再跑应显示"已一致"。
            # ⚠️ 判据不能是 `field_changes` 非空 —— 它现在也包含"=同"的条目（供 verbose 展示），
            #    所以要看 `changed_any`：知识字段 / 学名 / 来源 / 防治三类里任一项变了才算要更新。
            changed_any = (
                any('→' in item for item in field_changes)   # 知识字段有实质差异
                or sci_changed or src_changed
                or n_changed > 0 or n_new > 0
            )
            verdict = '将更新' if changed_any else '已一致'
            # "构成"列是必须的：只写 `5→5` 会让人以为"没变化"，
            # 实际可能是"4 改 + 1 新增"（如草莓叶焦病：库里没有化学防治条目）。
            shape = f'{n_changed}改' + (f' {n_new}新' if n_new else '') + (f' {identical}同' if identical else '')
            self.stdout.write(
                f'  {index:>3}  {name:<14} {pest.name:<12} {how:<22} '
                f'{f"{existing_total}→{planned}":<16} {shape:<12} {verdict}'
            )
            if self.verbose:
                self.stdout.write(f'        字段：{"  ".join(field_changes)}')
                self.stdout.write(f'        防治：{"  ".join(per_cat_notes)}  （同=内容一样 改=要替换 新=原本没有）')
                old_len = sum(len((r.measure or '').strip()) for r in existing_rows)
                new_len = sum(len((dims.get(k) or '').strip()) for k, (t, _c) in DISEASE_FIELD_MAP.items() if t == 'prevention')
                self.stdout.write(f'        防治字数：{old_len} → {new_len}（{new_len - old_len:+d}）')

            if existing_total > planned:
                self.warnings.append(
                    f'{name} 现有 {existing_total} 条防治 > 计划写入 {planned} 条 —— '
                    f'多出的 {existing_total - planned} 条会被**删除**（先删后写）'
                )

    # ── 步骤 4：汇总 ─────────────────────────────────────────────────────
    def _summary(self) -> None:
        self._section('四、汇总（本次不写库）')
        total = PestInfo.objects.count()
        prev_total = PreventionMethod.objects.count()
        self._ok(f'库中词条 {total} 条 · 全库防治 {prev_total} 条')
        self._ok(f'将更新 PestInfo 知识字段 {self.to_pest_fields} 处（症状 + 发病规律）')
        self.stdout.write('')
        # 有损操作必须单独说清楚：先删后写，删掉的是"内容不同"的那些。
        # ⚠️ 这里的 130 是**这 26 个病害名下**的条数，不是全库 190（差额 = 12 个 healthy
        #    词条各自的 5 条，本轮不碰）。第一版把它写成"现有 130 条"，与"全库 190"并列时
        #    看起来像自相矛盾 —— 标签必须写清口径。
        self.stdout.write(
            f'  防治措施（**先删后写**，该表无唯一约束，所以这是有损操作）：\n'
            f'      本轮涉及词条名下的现有条数  {self.prev_old} 条（其余 {prev_total - self.prev_old} 条属于 healthy 词条，本轮不动）\n'
            f'      将写入                    {self.prev_new} 条\n'
            f'      其中内容相同              {self.prev_identical} 条（重写后一字不差）\n'
            f'      将被替换                  {self.prev_deleted} 条（**内容与新版不同，删除后以新版覆盖**）'
        )
        self.stdout.write('')
        self._ok(f'healthy 记录 {self.healthy_records} 条，其中 {self.healthy_matched} 条能接上词条'
                 f'（写入 CropHealthProfile，按 pest 一对一）')
        if self.prev_deleted > 0:
            self.warnings.append(
                f'将有 {self.prev_deleted} 条旧防治被替换（设计使然：新语料是重写版），'
                f'**K3 写入前请确认 db.sqlite3 有备份** —— 回滚只能靠备份'
            )

    # ── 步骤 5：重复词条体检（pumpkin 与 Squash 同病）──────────────────────
    def _maybe_report_duplicate_names(self) -> None:
        self._section('五、重复词条体检')
        from collections import Counter
        names = Counter(PestInfo.objects.values_list('name', flat=True))
        dupes = {name: count for name, count in names.items() if count > 1}
        if dupes:
            for name, count in dupes.items():
                self._bad(f'库里「{name}」有 {count} 条 —— 入库前先决定合并到哪一条')
                self.problems.append(f'重复词条：{name} × {count}')
        else:
            self._ok('库中没有重名词条')
        # 南瓜白粉病 / Squash 同病：确认只有一条，且它的 identifier 是什么
        pumpkin = list(PestInfo.objects.filter(
            english_identifier__in=['pumpkin_powdery_mildew', 'squash_powdery_mildew']
        ).values_list('id', 'name', 'english_identifier'))
        if pumpkin:
            for pid, pname, ident in pumpkin:
                self._ok(f'南瓜白粉病相关词条：id={pid} name={pname} identifier={ident}')
            if len(pumpkin) > 1:
                self._bad('南瓜白粉病（pumpkin / squash）在库里有**多条** —— 会让百科出现重复条目')
                self.problems.append('南瓜白粉病重复')
        else:
            self._warn('库里没有 pumpkin/squash powdery_mildew 词条 —— 与 check_kb_coverage.py 的结论不符，需复查')

        self._section('六、结论')
        if self.problems:
            self.stdout.write(self.style.ERROR(f'  ✗ {len(self.problems)} 个问题需要人工确认：'))
            for item in self.problems:
                self.stdout.write(self.style.ERROR(f'      · {item}'))
        if self.warnings:
            self.stdout.write(self.style.WARNING(f'  ⚠ {len(self.warnings)} 条提示：'))
            for item in self.warnings:
                self.stdout.write(self.style.WARNING(f'      · {item}'))
        if not self.problems and not self.warnings:
            self._ok('比对通过，可以进入 K2/K3')

    # ── 步骤 7：真正写库（K3）──────────────────────────────────────────────
    def _apply(self, payload: dict) -> None:
        """把语料写进库。**整体一个事务**：任何一条失败都全部回滚。

        有损点只有一个，且是刻意的：每个病害名下**先删旧防治再写新版**。
        `PreventionMethod` 没有唯一约束，不先删就会每次导入翻倍；
        而"先删后写"意味着旧措施会被清掉 —— 所以写入前必须有备份。
        """
        self._section('七、写入（--apply）')
        if self.problems:
            raise CommandError(
                f'存在 {len(self.problems)} 个问题，拒绝写入。请先解决（可用 --dry-run 查看）。'
            )

        pests_updated = pest_created = prevent_created = profile_new = profile_upd = 0
        with transaction.atomic():
            for record in payload['records']:
                pest, _how = self._resolve(record)
                if pest is None:
                    raise CommandError(f'写入中断：{record["name"]} 未匹配到词条')
                dims = record.get('dimensions', {})

                if record.get('category') == 'healthy':
                    profile, was_created = CropHealthProfile.objects.get_or_create(pest=pest)
                    profile.crop_type = (record.get('host_crop') or '').split(' ')[0] or pest.crop_type
                    profile.name = record['name']
                    profile.scientific_name = record.get('scientific_name', '')
                    for dim_key, field in CropHealthProfile.DIMENSION_FIELDS.items():
                        setattr(profile, field, (dims.get(dim_key) or '').strip())
                    profile.sources = record.get('sources', [])
                    profile.save()
                    profile_new += was_created
                    profile_upd += (not was_created)
                    continue

                # ① 两个知识字段 + 学名 + 来源
                changed = False
                for dim_key, (target, field) in DISEASE_FIELD_MAP.items():
                    if target != 'pest':
                        continue
                    value = (dims.get(dim_key) or '').strip()
                    if value and getattr(pest, field) != value:
                        setattr(pest, field, value)
                        changed = True
                if record.get('scientific_name') and pest.scientific_name != record['scientific_name']:
                    pest.scientific_name = record['scientific_name']
                    changed = True
                if record.get('sources') and pest.sources != record['sources']:
                    pest.sources = record['sources']
                    changed = True
                if changed:
                    pest.save(update_fields=['symptoms', 'description', 'scientific_name', 'sources'])
                    # ⚠️ 这条自增漏过一次：计数器初始化后再没加过，于是"写入 26 条知识字段"
                    #    被报成"已更新 0 条"—— 数据其实写对了，但报告说没写，比不报更糟。
                    pests_updated += 1

                # ② 防治：先删后写（该表无唯一约束，这是唯一的幂等做法）
                PreventionMethod.objects.filter(pest=pest).delete()
                for dim_key, (target, category_code) in DISEASE_FIELD_MAP.items():
                    if target != 'prevention':
                        continue
                    value = (dims.get(dim_key) or '').strip()
                    if not value:
                        continue
                    PreventionMethod.objects.create(pest=pest, category=category_code, measure=value)
                    prevent_created += 1

        self._ok(f'PestInfo 已更新 {pests_updated} 条（含学名/来源）')
        self._ok(f'PreventionMethod 已重建 {prevent_created} 条')
        self._ok(f'CropHealthProfile 新建 {profile_new} 条 / 更新 {profile_upd} 条')
        self._ok('写入完成（单事务，已提交）。建议紧接着再跑一次 --dry-run 验证幂等性：'
                 '"将被替换"应变为 0')

    # ── 步骤 8：写入后的自查 ──────────────────────────────────────────────
