"""`check_assistant` —— 智能回答助手自检（第 193 批，K5）。

沿用 `check_env` 的风格与退出码约定，回答四个问题：

  1. **配置齐不齐**：`LLM_*`（开关/端点/key/模型/超时）与 `ASSISTANT_*`（限流/条数）；
  2. **连通性真不真**：`--probe` 时**真的发一次请求**（默认不发，避免每次自检都花钱）；
  3. **语料在不在**：词条 / 防治 / 健康档案的条数，以及中英文字段是否已填；
  4. **链路通不通**：拿一个真实问题走一遍检索（**不调模型**），看命中与上下文长度。

`--strict` 时有任何问题退出码 1（可接 CI 或告警）。

    python manage.py check_assistant                 # 只查配置与语料
    python manage.py check_assistant --probe         # 额外发一次真实请求（会计费）
    python manage.py check_assistant --query "番茄晚疫病怎么打药"   # 换检索样例
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from api.assistant import context as context_builder
from api.assistant import guard, llm, prompts, retriever
from api.models import CropHealthProfile, PestInfo, PreventionMethod

DEFAULT_QUERY = '番茄晚疫病怎么打药'


class Command(BaseCommand):
    help = '智能回答助手自检：配置 / 语料 / 检索链路（--probe 才发真实请求）'

    def add_arguments(self, parser):
        parser.add_argument('--probe', action='store_true',
                            help='真的调一次 LLM 验证连通性（会计费；默认不调）')
        parser.add_argument('--query', default=DEFAULT_QUERY, help='检索自检用的样例问题')
        parser.add_argument('--strict', action='store_true', help='有问题时退出码 1')

    def _ok(self, text):
        self.stdout.write(f'  ✓ {text}')

    def _warn(self, text):
        self.stdout.write(self.style.WARNING(f'  ⚠ {text}'))

    def _bad(self, text):
        self.stdout.write(self.style.ERROR(f'  ✗ {text}'))

    def _section(self, title):
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n{title}'))

    def handle(self, *args, **options):
        self.problems: list[str] = []
        self.warnings: list[str] = []

        self._check_config(options['probe'])
        self._check_corpus()
        self._check_pipeline(options['query'])

        self._section('结论')
        if self.problems:
            self.stdout.write(self.style.ERROR(f'  ✗ {len(self.problems)} 个问题：'))
            for item in self.problems:
                self.stdout.write(self.style.ERROR(f'      · {item}'))
        if self.warnings:
            self.stdout.write(self.style.WARNING(f'  ⚠ {len(self.warnings)} 条提示：'))
            for item in self.warnings:
                self.stdout.write(self.style.WARNING(f'      · {item}'))
        if not self.problems and not self.warnings:
            self._ok('助手自检通过')
        if options['strict'] and (self.problems or self.warnings):
            from django.core.management.base import CommandError
            raise CommandError(f'--strict：{len(self.problems)} 个问题 / {len(self.warnings)} 条提示')

    # ── 一、配置 ──────────────────────────────────────────────────────────
    def _check_config(self, probe: bool) -> None:
        from django.conf import settings as s

        self._section('一、配置')
        self._ok(f'LLM_ENABLED={s.LLM_ENABLED}  模型={s.LLM_MODEL}  超时={s.LLM_TIMEOUT}s  上限={s.LLM_MAX_TOKENS} tokens')
        if s.LLM_API_KEY:
            self._ok(f'LLM_API_KEY 已设置（长度 {len(s.LLM_API_KEY)}，前缀 {s.LLM_API_KEY[:3]}）')
        else:
            self._bad('LLM_API_KEY 未设置 —— 助手只能降级返回词条原文')
        if not s.LLM_ENABLED:
            self._warn('LLM_ENABLED=False：助手会走降级（返回词条原文）。要真正问答请打开它')
        self._ok(f'限流 {s.ASSISTANT_RATE_PER_MINUTE} 次/分钟 · 检索 {s.ASSISTANT_TOP_K} 条 · '
                 f'会话上限 {s.ASSISTANT_SESSION_MAX_MESSAGES} 条消息 · '
                 f'带 {s.ASSISTANT_HISTORY_TURNS} 轮历史')
        self._ok(f'闸门上限 {guard.MAX_QUESTION_CHARS} 字 · 提示词版本 {prompts.PROMPT_VERSION}')

        if probe:
            self.stdout.write('  … 正在发一次真实请求（会计费）')
            info = llm.probe()
            if info['ok']:
                self._ok(f'连通性 OK：HTTP 200，{info["latency_ms"]}ms，回答「{info["answer"]}」')
                if info['actual_model'] and info['actual_model'] != info['configured_model']:
                    # 第 192 批实测本端点会把 deepseek-chat 重定向到 deepseek-flash
                    self._warn(f'配置模型 {info["configured_model"]}，实际落到 {info["actual_model"]}'
                               f'（端点侧重定向）—— LLM_MODEL 不保证精确选型')
            else:
                self._bad(f'连通性失败：{info["error"]}')

    # ── 二、语料 ──────────────────────────────────────────────────────────
    def _check_corpus(self) -> None:
        self._section('二、语料')
        pests = PestInfo.objects.count()
        preventions = PreventionMethod.objects.count()
        profiles = CropHealthProfile.objects.count()
        self._ok(f'词条 {pests} 条 · 防治 {preventions} 条 · 健康档案 {profiles} 条')

        # 空字段/英文未填都只提示：后者是 K4 的活，不该让自检变成红灯。
        # ⚠️ 统计口径：**只查病害词条**。12 条「健康X」的学名与来源存在
        #    `CropHealthProfile` 里（见 models_assistant / models.py 的 K2 设计），
        #    拿 `PestInfo` 全表统计会把它们误报成"缺学名"（第一版就是这么误报的）。
        diseases = PestInfo.objects.exclude(english_identifier__endswith='_healthy')
        no_symptom = diseases.filter(symptoms='').count()
        no_sci = diseases.filter(scientific_name='').count()
        no_src = diseases.filter(sources=[]).count()
        self._ok(f'其中病害词条 {diseases.count()} 条、健康词条 '
                 f'{PestInfo.objects.filter(english_identifier__endswith="_healthy").count()} 条')
        if no_symptom:
            self._bad(f'{no_symptom} 条病害的症状为空 —— 助手对这些病害答不出内容')
        else:
            self._ok('所有病害词条都有症状')
        if no_sci or no_src:
            self._warn(f'病害里有 {no_sci} 条缺学名 / {no_src} 条缺来源（校准版覆盖的应都有）')
        else:
            self._ok('病害的学名与来源已全覆盖')

        # 健康档案侧的完整性（那 12 条的学名/来源在这里）
        if profiles:
            hp_no_sci = CropHealthProfile.objects.filter(scientific_name='').count()
            hp_no_src = CropHealthProfile.objects.filter(sources=[]).count()
            if hp_no_sci or hp_no_src:
                self._warn(f'健康档案里有 {hp_no_sci} 条缺学名 / {hp_no_src} 条缺来源')
            else:
                self._ok('健康档案的学名与来源已全覆盖')

        filled_en = PestInfo.objects.exclude(symptoms_en='').count()
        if filled_en == 0:
            self._warn('英文字段全为空：英文界面下助手会回退中文（属 K4 范围）')

        # 防治类别齐备性：某类全缺往往是导入遗漏
        from collections import Counter
        dist = Counter(PreventionMethod.objects.values_list('category', flat=True))
        self._ok('防治类别分布：' + ' · '.join(f'{k}={v}' for k, v in sorted(dist.items())) or '（无）')

    # ── 三、链路（不调模型）──────────────────────────────────────────────
    def _check_pipeline(self, query: str) -> None:
        self._section('三、检索链路（不调模型）')
        self._ok(f'样例问题：{query!r}  意图={retriever.detect_intent(query)}')
        hits = retriever.search(query)
        if not hits:
            self._bad('检索为空 —— 这个问题会走"词条未收录"分支。检查语料是否已导入')
            return
        for hit in hits[:5]:
            self.stdout.write(f'      · {hit.pest.name:<14} score={hit.score:<4} {hit.why[:70]}')
        built = context_builder.build(hits)
        self._ok(f'上下文 {len(built.text)} 字 · 引用 {len(built.citations)} 处')
        if built.citations:
            self.stdout.write(f'      引用示例：{built.citations[0].snippet[:80]}')
        if len(built.text) > 7000:
            self._warn(f'上下文偏大（{len(built.text)} 字），单次调用成本会上去，'
                       f'可下调 ASSISTANT_TOP_K')
