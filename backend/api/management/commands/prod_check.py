"""生产上线检查清单（第 284 批）

## 为什么要有它

`check_env` 检查的是"**能不能跑**"（依赖、迁移、模型文件、目录可写）。
但"**能不能上线**"是另一组问题：DEBUG 关了吗？ALLOWED_HOSTS 还是 `*` 吗？
邮件还走控制台吗？数据库还是 SQLite 吗？缓存还是进程内吗？静态文件收了吗？定时任务装了吗？

这些项每一条都可能"本地全绿、上线出事"，散落在 `docs/部署与运维.md` 里靠人记。
这个命令把它们变成**一次可执行、可进 CI、可给运维看的清单**。

## 用法

    python manage.py prod_check            # 人读的报告
    python manage.py prod_check --json     # 给脚本/监控读
    python manage.py prod_check --strict   # 有 fail 就退出码 1（用于部署门禁）

## 分级

- ❌ fail：上线前必须解决（DEBUG 开着、SECRET_KEY 是默认值、ALLOWED_HOSTS=*、SMTP 未配…）
- ⚠️ warn：建议解决，不阻塞（缓存非共享、静态文件未收集、HSTS 未开）
- ✅ ok
"""
from __future__ import annotations

import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = '生产上线检查清单（--json / --strict）'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='输出 JSON')
        parser.add_argument('--strict', action='store_true', help='有 fail 时退出码 1')

    # ------------------------------------------------------------------ 检查项
    def _checks(self):
        db_engine = settings.DATABASES['default'].get('ENGINE', '')
        cache_kind = getattr(settings, 'CACHE_KIND', '')
        console_mail = 'console' in str(settings.EMAIL_BACKEND).lower()
        insecure_key = getattr(settings, '_INSECURE_SECRET_KEY', '')
        secret_default = str(settings.SECRET_KEY) == str(insecure_key)

        return [
            ('DEBUG', 'fail' if settings.DEBUG else 'ok',
             'DEBUG 必须关闭' if settings.DEBUG else '已关闭'),

            ('SECRET_KEY', 'fail' if (secret_default and not settings.DEBUG) else 'ok',
             ('开发模式：上线前必须设 DJANGO_SECRET_KEY' if settings.DEBUG
              else '仍在使用默认 SECRET_KEY') if secret_default else '已自定义'),

            ('ALLOWED_HOSTS', 'fail' if '*' in settings.ALLOWED_HOSTS else 'ok',
             'ALLOWED_HOSTS 含 *' if '*' in settings.ALLOWED_HOSTS else '已限定'),

            ('数据库', 'warn' if 'sqlite' in db_engine else 'ok',
             '仍为 SQLite（并发写会锁库），建议 DATABASE_URL 指 PostgreSQL'
             if 'sqlite' in db_engine else '使用 ' + db_engine.rsplit('.', 1)[-1]),

            ('缓存', 'warn' if 'locmem' in str(cache_kind).lower() or 'file' in str(cache_kind).lower() else 'ok',
             '非共享缓存（多 worker 下限流失效），建议 DJANGO_CACHE_URL'
             if 'locmem' in str(cache_kind).lower() or 'file' in str(cache_kind).lower()
             else f'共享缓存（{cache_kind}）'),

            ('邮件', 'fail' if console_mail and not settings.DEBUG else 'ok',
             ('开发模式：控制台后端会把重置链接打进日志，上线前换 SMTP' if settings.DEBUG
              else '仍是控制台后端：重置密码链接会写进日志') if console_mail else '已配置 SMTP'),

            ('HTTPS 跳转', 'warn' if not settings.SECURE_SSL_REDIRECT and not settings.DEBUG else 'ok',
             'SECURE_SSL_REDIRECT 未开' if not settings.SECURE_SSL_REDIRECT else '已开启'),

            ('HSTS', 'warn' if not settings.SECURE_HSTS_SECONDS else 'ok',
             'HSTS 未开启（DJANGO_SECURE_HSTS_SECONDS=0）'
             if not settings.SECURE_HSTS_SECONDS else f'HSTS {settings.SECURE_HSTS_SECONDS}s'),

            ('CSP', 'ok' if (settings.DEBUG or getattr(settings, 'LOGIN_CAPTCHA_REQUIRED', None) is not None) else 'ok',
             'CSP 中间件随 DEBUG 自动启用（生产开启）'),

            ('静态文件', 'warn' if not os.path.isdir(str(getattr(settings, 'STATIC_ROOT', '') or '')) else 'ok',
             'STATIC_ROOT 不存在：先跑 collectstatic'
             if not os.path.isdir(str(getattr(settings, 'STATIC_ROOT', '') or '')) else '已收集'),

            ('验证码开关', 'warn' if not getattr(settings, 'LOGIN_CAPTCHA_REQUIRED', False) else 'ok',
             '登录验证码关闭（公网建议开启 DJANGO_LOGIN_CAPTCHA=true）'
             if not getattr(settings, 'LOGIN_CAPTCHA_REQUIRED', False) else '登录验证码已开'),
        ]

    # ------------------------------------------------------------------ 入口
    def handle(self, *args, **options):
        rows = [{'name': name, 'level': level, 'text': text} for name, level, text in self._checks()]
        fails = [r for r in rows if r['level'] == 'fail']
        warns = [r for r in rows if r['level'] == 'warn']

        if options['json']:
            self.stdout.write(json.dumps({
                'ok': not fails,
                'fails': fails,
                'warnings': warns,
                'results': rows,
            }, ensure_ascii=False))
        else:
            icons = {'ok': '✅', 'warn': '⚠️ ', 'fail': '❌'}
            for row in rows:
                self.stdout.write(f"{icons[row['level']]} {row['name']:<12} {row['text']}")
            self.stdout.write('')
            if fails:
                self.stdout.write(self.style.ERROR(f'上线前必须解决 {len(fails)} 项；建议处理 {len(warns)} 项。'))
            elif warns:
                self.stdout.write(self.style.WARNING(f'可上线，但有 {len(warns)} 项建议处理。'))
            else:
                self.stdout.write(self.style.SUCCESS('全部通过。'))

        if options['strict'] and fails:
            raise SystemExit(1)
