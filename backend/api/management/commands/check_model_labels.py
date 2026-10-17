"""第 219 批：比对「权重里的类名」与「系统里的词条」，一条命令定位"识别对了但显示错了"。

## 这个命令是为什么写的

用户拿 `Tomato___healthy` 的图片识别，**框上写"健康番茄 1.00"，下面的病害详情却是"番茄晚疫病"**。

根因是 `ai_service.py` 里两处用了**两套类名表**：

```
框上标签 ← results[0].names[class_id]     （模型自带，39 类）
详情标识 ← AIService.class_names[class_id]（手写列表，当时只有 38 类，漏了 Background_without_leaves）
```

39 与 38 差一条，从 index 4 起**整体错位一位** —— 于是 `names[32]='Tomato___healthy'`
而 `class_names[32]='Tomato___Late_blight'`。两个数字都合法、不越界、不报错，**全程静默**。

## 这个命令做什么

三件事，全部只读，不改任何数据：

1. **权重的类名 vs 手写的 `class_names`**：逐索引比对，报出不一致（换模型后最容易踩）；
2. **权重的类名 → 能否在 `PestInfo` 里查到词条**：查不到就意味着用户会看到
   "未收录"的占位内容（这是另一类问题：词条缺失，不是错位）；
3. **`PestInfo` 里有、模型却没有的类**：这类词条永远不会被命中，属于"僵尸词条"。

## 用法

    python manage.py check_model_labels

有差异会以 `✗` 打头，全部正常则以 `✓` 打头并以退出码 0 结束。
发现不一致时**不是**去改这个命令，而是让 `class_names` 跟权重对齐
（正常路径其实已经不读它了，它只是兜底 —— 但留着错的兜底照样是地雷）。
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand

from api.ai_service import AIService

#: 权重里代表"画面里没有叶片"的类，它**不应该**在词条表里（不是病害、也不是健康植株）
BACKGROUND_CLASS = 'Background_without_leaves'


def _weights_names():
    """读权重里的类名；权重缺失或加载失败时返回 (None, 原因)。"""
    try:
        AIService()                      # 单例加载
        model = AIService.model
        if model is None:
            return None, '模型未加载（权重缺失或加载失败，先跑一次识别看日志）'
        names = getattr(model, 'names', None)
        if not isinstance(names, dict) or not names:
            return None, '权重里没有 names（老格式权重），只能依赖手写 class_names'
        return dict(names), None
    except Exception as exc:             # noqa: BLE001 - 诊断命令不该因为加载失败而崩
        return None, f'加载模型失败：{exc}'


class Command(BaseCommand):
    help = '比对权重的类名、手写 class_names 与 PestInfo 词条（只读，用于定位"识别对了但显示错了"）'

    def handle(self, *args, **options):
        from api.pest_lookup import find_pest_info

        names, err = _weights_names()
        if names is None:
            self.stdout.write(self.style.ERROR(f'✗ {err}'))
            return

        manual = list(AIService.class_names)
        problems = 0

        self.stdout.write(f'权重类数：{len(names)}    手写 class_names：{len(manual)}')

        # ── ① 权重的名字 vs 手写列表（逐索引）──────────────────────────────
        self.stdout.write('')
        self.stdout.write('① 权重 names 与手写 class_names 的逐索引比对')
        if len(names) != len(manual):
            problems += 1
            self.stdout.write(self.style.ERROR(
                f'  ✗ 数量不一致（权重 {len(names)} / 手写 {len(manual)}）'
                ' —— 差一条就会让后面所有索引整体错位一位'))
        mismatches = 0
        for index in range(max(len(names), len(manual))):
            a = names.get(index)
            b = manual[index] if index < len(manual) else None
            if a == b:
                continue
            mismatches += 1
            problems += 1
            self.stdout.write(self.style.ERROR(
                f'  ✗ [{index:2}] 权重={a!r}  手写={b!r}'))
        if not mismatches:
            self.stdout.write(self.style.SUCCESS('  ✓ 全部一致'))

        # ── ② 权重类名 → 能否查到词条 ─────────────────────────────────────
        self.stdout.write('')
        self.stdout.write('② 权重每个类能否在 PestInfo 里查到词条')
        missing = []
        for index in sorted(names):
            raw = names[index]
            if raw == BACKGROUND_CLASS:
                continue
            pest, _note = find_pest_info(raw)
            if pest is None:
                missing.append((index, raw))
        if missing:
            problems += len(missing)
            for index, raw in missing:
                self.stdout.write(self.style.ERROR(
                    f'  ✗ [{index:2}] {raw} → 查不到词条（用户会看到"未收录"的占位内容）'))
            self.stdout.write('    修法：后台补该病害的词条，或确认 english_identifier 的写法')
        else:
            self.stdout.write(self.style.SUCCESS('  ✓ 每个类都有对应词条'))

        # ── ③ 僵尸词条：库里有、模型没有 ─────────────────────────────────
        self.stdout.write('')
        self.stdout.write('③ PestInfo 里存在但模型不会输出的词条')
        from api.models import PestInfo

        #: ⚠️ **不能**直接拿 `PestInfo.english_identifier` 和权重类名比字符串：
        #: 库里的写法是 `apple_scab`，权重是 PlantVillage 风格 `Apple___Apple_scab` ——
        #: 两套命名本来就不同，直接比会把**全部**词条判成"不会被命中"（第一版就这么错了，
        #: 一屏 38 条全红，而系统明明好好的）。
        #: 正确的做法是复用 `find_pest_info` 把权重类名解析成词条，再比集合。
        reachable_ids = set()
        for raw in names.values():
            if raw == BACKGROUND_CLASS:
                continue
            pest, _note = find_pest_info(raw)
            if pest is not None:
                reachable_ids.add(pest.pk)

        zombie = [
            (p.english_identifier, p.name)
            for p in PestInfo.objects.all()
            if p.pk not in reachable_ids
        ]
        if zombie:
            #: 这一类**不一定是错**：词条可能服务于"手动录入/历史数据"。
            #: 所以用 WARNING 语义（✗ 计数但不算致命），并明确说明它不是 bug。
            self.stdout.write(self.style.WARNING(
                f'  ⚠ {len(zombie)} 条词条不会被模型命中（可能是历史/手工数据，未必是错）：'))
            for identifier, name in zombie[:10]:
                self.stdout.write(f'     · {identifier}  ({name})')
            if len(zombie) > 10:
                self.stdout.write(f'     … 还有 {len(zombie) - 10} 条')
        else:
            self.stdout.write(self.style.SUCCESS('  ✓ 没有多余词条'))

        # ── 结论 ─────────────────────────────────────────────────────────
        self.stdout.write('')
        if problems:
            self.stdout.write(self.style.ERROR(
                f'✗ 发现 {problems} 处需要处理的问题（①② 是真问题；③ 仅供参考）'))
        else:
            self.stdout.write(self.style.SUCCESS(
                '✓ 类名与词条全部对齐 —— 出现"识别对了但显示错了"就不在这里'))
