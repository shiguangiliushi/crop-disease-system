"""
翻译 provider 自检（第 86 批）

============================================================================
为什么需要它
----------------------------------------------------------------------------
换了 provider（比如从免 key 的公共接口换成 DeepL）之后，"到底通没通"以前只能靠
发一个帖子试试 —— 出问题时也很难判断是 key 错了、还是网络不通、还是返回结构变了。
这个命令把这件事变成一条命令：

    python manage.py translate_provider_check                  # 检查 .env 里配的 provider
    python manage.py translate_provider_check --provider=deepl  # 临时试另一个
    python manage.py translate_provider_check --text="你的测试句子"
    python manage.py translate_provider_check --all             # 列出所有 provider 与所需配置

它会真的调一次接口（用一句短文本），成功则打印译文，失败则打印**具体原因**
（缺哪个环境变量 / HTTP 状态 / 返回体片段），并把配置检查表一并列出来。

退出码：0 = 成功；1 = 失败（原因已打印）。
============================================================================
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from api import services_translate

#: 自检用的样例文本：短、含农业术语，能同时验证"连得通"和"术语翻得对"
SAMPLE_TEXT = '番茄晚疫病的防治方法'


class Command(BaseCommand):
    help = '检查（并实测）当前配置的翻译 provider，见 api/services_translate.py'

    def add_arguments(self, parser):
        parser.add_argument('--provider', default='', help='临时指定 provider（默认取 settings）')
        parser.add_argument('--text', default=SAMPLE_TEXT, help='自检用的源文本')
        parser.add_argument('--all', action='store_true', help='只列出所有 provider 与所需配置')
        parser.add_argument('--no-cache', action='store_true', help='忽略译文缓存，强制真实请求')

    def handle(self, *args, **options):
        if options['all']:
            self.stdout.write('可用的翻译 provider：\n')
            for name, info in services_translate.PROVIDER_INFO.items():
                missing = services_translate.missing_provider_config(name)
                mark = '✓' if not missing else '·'
                self.stdout.write(f'  {mark} {name:<9} {info["label"]}')
                self.stdout.write(f'      需要配置：{"、".join(info["requires"]) or "（无需）"}'
                                  + (f'   当前缺少：{"、".join(missing)}' if missing else ''))
                self.stdout.write(f'      说明：{info["note"]}\n')
            self.stdout.write('在 backend/.env 里设置 TRANSLATE_PROVIDER=<名字> 即可切换。')
            return

        provider = options['provider'] or services_translate.provider_name()
        text = options['text']
        self.stdout.write(f'provider = {provider}')
        self.stdout.write(f'ENABLED  = {settings.TRANSLATE_ENABLED}')
        if provider in services_translate.PROVIDER_INFO:
            self.stdout.write(f'说明     = {services_translate.PROVIDER_INFO[provider]["note"]}')
        missing = services_translate.missing_provider_config(provider)
        if missing:
            self.stdout.write(self.style.ERROR(f'缺少配置：{"、".join(missing)}'))
            self.stdout.write('请补进 backend/.env（模板见 backend/.env.example），再重跑本命令。')
            raise SystemExit(1)

        if not services_translate.is_enabled() and not options['provider']:
            self.stdout.write(self.style.WARNING(
                '自动翻译当前是关闭状态（TRANSLATE_ENABLED=False 或 PROVIDER=none）；'
                '下面仍会实测 --provider 指定的接口。'
            ))

        if options['no_cache']:
            # 缓存键里带 provider，直接清掉本进程能看到的缓存（开发环境是 FileBasedCache）
            from django.core.cache import cache
            cache.clear()
            self.stdout.write('已清空译文缓存（--no-cache）')

        self.stdout.write(f'\n源文本：{text}')
        try:
            result = services_translate.translate_text(text, provider=provider)
        except services_translate.TranslateError as exc:
            self.stdout.write(self.style.ERROR(f'✗ 失败：{exc}'))
            raise SystemExit(1)
        except Exception as exc:  # noqa: BLE001 —— 自检命令要把任何异常都摊开给人看
            self.stdout.write(self.style.ERROR(f'✗ 异常：{type(exc).__name__}: {exc}'))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(f'✓ 译文：{result}'))
        self.stdout.write('\n配置生效。可以用下面这条命令把已有内容按新 provider 重刷：')
        self.stdout.write('  python manage.py translate_forum_content --force --provider=%s' % provider)
