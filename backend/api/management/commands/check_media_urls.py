"""找出（并可修复）媒体地址里的**绝对 http 地址** —— Mixed Content 的根因（第 430 批）。

## 现象

生产站跑在 HTTPS，控制台却报：

    Mixed Content: The page at 'https://…' was loaded over HTTPS,
    but requested an insecure image 'http://10.0.0.5/media/…'
    This request has been blocked; the content must be served over HTTPS.

用户看到的是**图片裂开**。而页面代码并没有写死这个地址 —— 它来自**数据**：

  1. `ImageField` / `FileField` 里存的是完整地址（早期用局域网 IP 调试时写进去的，
     后来换域名、上 HTTPS 也没跟着变）；
  2. 富文本正文（帖子/新闻/病害描述）里的 `<img src="http://…/media/…">`，
     它绕过所有 `:src` 绑定，浏览器直接按 HTML 里的地址去取。

## 这个命令做什么

扫**所有模型**的 `FileField` / `ImageField` 与 `TextField`，把
`http://<任意 host>/media/…` 改成**相对路径**：

| 字段类型 | 改前 | 改后 |
|---|---|---|
| `FileField` / `ImageField`（存的是相对 MEDIA_ROOT 的路径） | `http://10.0.0.5/media/pest_images/x.jpg` | `pest_images/x.jpg` |
| `TextField`（存的是 HTML） | `<img src="http://10.0.0.5/media/news/a.jpg">` | `<img src="/media/news/a.jpg">` |

**为什么改成相对路径而不是 https://**：那个 host 往往是个没有证书的 IP，
换成 https 只会从"被拦"变成"连不上"。相对路径用当前页面的协议与域名，
一份数据在 http 开发环境和 https 生产环境都对。

只认 `/media/`（`settings.MEDIA_URL`）开头：外部图床一律不动 —— 它们的域名不归我们管。

## 用法

    python manage.py check_media_urls                # 只报告（默认，不动数据）
    python manage.py check_media_urls --samples 10   # 每个字段多列几条样例
    python manage.py check_media_urls --fix          # 真的改写

建议顺序：先不加 `--fix` 看一眼命中多少条、样例对不对，再执行。
`--fix` 用 `queryset.update()` 而不是 `save()`：后者会触发翻译/指纹等钩子，
而这次改的只是 URL 前缀，不该惊动那些逻辑。

## 为什么遍历 `apps.get_models()`

手写模型清单的话，**以后新增一个带图片的模型没人会回来改这个命令** ——
那批坏数据就永远查不出来（`prune_media` 也是同一条理由）。
"""
from __future__ import annotations

import re

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models

#: 兜底：字段值里只要出现 `http…://…/media/…` 就算命中
_ABSOLUTE_MEDIA = re.compile(
    r'https?://[^/\s"\'<>()]+(?P<path>/media/[^"\s\'<>()]+)'
)


class Command(BaseCommand):
    help = '找出（并可修复）媒体地址里的绝对 http 地址（Mixed Content 根因）'

    def add_arguments(self, parser):
        parser.add_argument('--fix', action='store_true', help='真的改写（默认只报告）')
        parser.add_argument('--samples', type=int, default=5, help='每个字段最多列几条样例（默认 5）')

    def handle(self, *args, **options):
        fix = bool(options['fix'])
        samples = max(0, int(options['samples'] or 0))
        media_prefix = '/media/'
        total = 0

        for model in apps.get_models():
            if model._meta.abstract or not model._meta.managed:
                continue
            for field in model._meta.get_fields():
                if not getattr(field, 'concrete', False):
                    continue
                if isinstance(field, (models.FileField, models.ImageField)):
                    total += self._scan_file_field(model, field, fix=fix, samples=samples)
                elif isinstance(field, models.TextField):
                    total += self._scan_text_field(model, field, fix=fix, samples=samples,
                                                    media_prefix=media_prefix)

        if total == 0:
            self.stdout.write(self.style.SUCCESS('✅ 没有发现绝对 http 的媒体地址'))
            return
        if fix:
            self.stdout.write(self.style.SUCCESS(f'已改写 {total} 处；建议再跑一次确认归零'))
        else:
            self.stdout.write(self.style.WARNING(
                f'发现 {total} 处（**未改动**）。确认样例无误后加 --fix 执行'))

    # ── 两类字段 ───────────────────────────────────────────────────────────
    def _scan_file_field(self, model, field, *, fix: bool, samples: int) -> int:
        """`ImageField` / `FileField`：值是**相对 MEDIA_ROOT 的路径**，所以只留 `/media/` 之后那段。"""
        label = f'{model._meta.label}.{field.name}'
        try:
            queryset = model._default_manager.filter(**{f'{field.attname}__startswith': 'http'})
            rows = list(queryset.values_list('pk', field.attname)[:5000])
        except Exception:  # noqa: BLE001 —— 某个模型的字段不可查询（自定义 manager）就跳过
            return 0

        hits = []
        for pk, value in rows:
            new = self._file_value(value)
            if new:
                hits.append((pk, value, new))
        return self._report_and_maybe_fix(model, field, hits, fix=fix, samples=samples,
                                          label=label, db_field=field.attname)

    def _scan_text_field(self, model, field, *, fix: bool, samples: int, media_prefix: str) -> int:
        """`TextField`：HTML 里的 `<img src="http://…/media/…">` 改成相对路径。"""
        label = f'{model._meta.label}.{field.name}'
        try:
            queryset = (model._default_manager
                        .filter(**{f'{field.name}__contains': media_prefix})
                        .filter(**{f'{field.name}__contains': 'http'})
                        .values_list('pk', field.name)[:5000])
            rows = list(queryset)
        except Exception:  # noqa: BLE001
            return 0

        hits = []
        for pk, value in rows:
            if not value:
                continue
            new = _ABSOLUTE_MEDIA.sub(r'\g<path>', value)
            if new != value:
                hits.append((pk, value, new))
        return self._report_and_maybe_fix(model, field, hits, fix=fix, samples=samples,
                                          label=label, db_field=field.name)

    # ── 共用 ───────────────────────────────────────────────────────────────
    @staticmethod
    def _file_value(value) -> str:
        """`http://host/media/a/b.jpg` → `a/b.jpg`；不是这种形态就返回空串。"""
        text = str(value or '').strip()
        if not text.lower().startswith('http'):
            return ''
        match = _ABSOLUTE_MEDIA.search(text)
        if not match:
            return ''
        path = match.group('path')            # /media/a/b.jpg
        return path[len('/media/'):].lstrip('/')

    def _report_and_maybe_fix(self, model, field, hits, *, fix, samples, label, db_field) -> int:
        if not hits:
            return 0
        self.stdout.write(f'\n{label}：{len(hits)} 条')
        for pk, old, new in hits[:samples]:
            if isinstance(field, (models.FileField, models.ImageField)):
                shown_old, shown_new = old, new
            else:
                # 文本字段只截前后一小段，够看出对错又不刷屏
                shown_old, shown_new = _clip(old), _clip(new)
            self.stdout.write(f'  #{pk}  {shown_old}\n        → {shown_new}')
        if len(hits) > samples:
            self.stdout.write(f'  …另有 {len(hits) - samples} 条')

        if fix:
            for pk, _old, new in hits:
                model._default_manager.filter(pk=pk).update(**{db_field: new})
            self.stdout.write(self.style.SUCCESS(f'  ✓ 已改写 {len(hits)} 条'))
        return len(hits)


def _clip(text: str, width: int = 120) -> str:
    text = str(text or '')
    if len(text) <= width:
        return text
    return f'{text[:width]}…（共 {len(text)} 字）'
