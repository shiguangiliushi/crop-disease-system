"""
抓取行业资讯订阅源（RSS 2.0 / Atom）→ 新闻草稿（第 404 批，P2-10 内容生产半自动化）

    python manage.py fetch_news_feeds --file feed.xml
    python manage.py fetch_news_feeds --url https://example.com/feed.xml --category tech
    python manage.py fetch_news_feeds --url A --url B --limit 20 --dry-run

## 为什么"只落草稿"

外部抓来的内容没有经过人工核对（标题党、旧闻、错别字、非农业内容都可能混进来），
直接发布等于把审核责任交给订阅源。所以一律 `is_published=False`，由编辑在
管理端过一遍再发布；`--dry-run` 还能先看会进哪些标题。

## 为什么用文件也能跑

`--file` 是给**离线/测试**用的：真实订阅源会变、还可能断网，测试拿固定 XML
才能断言解析口径（这也是本命令的测试不联网的原因）。

## 去重

按 `external_url`（非空时）或标题（忽略大小写、strip 后）判重：同一个订阅源
每天抓一次，已经入过库的条目必须 skipped，否则跑两次就是两倍草稿。
"""
import html
import logging
import re
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests
from django.core.management.base import BaseCommand, CommandError

from ...models import News

logger = logging.getLogger(__name__)

#: Atom 命名空间（RSS 2.0 没有命名空间）
ATOM_NS = '{http://www.w3.org/2005/Atom}'

#: 每个 feed 默认最多处理多少条（订阅源动辄上百条，先只取最近的，避免一次灌爆草稿箱）
DEFAULT_LIMIT = 10
MAX_LIMIT = 50

#: content 字段（<p> 段落 HTML）的总长上限；summary 上限沿用模型的 200
MAX_CONTENT_LENGTH = 5000
MAX_SUMMARY_LENGTH = 200

#: 远程抓取超时（秒）—— 定时任务不能被一个慢订阅源拖住
FETCH_TIMEOUT = 15


def _strip_html(value):
    """
    把 RSS/Atom 里夹带的 HTML 压成纯文本。

    为什么不用正则"挑出正文"：订阅源给的 `description` 可能整段是 HTML，
    我们只需要纯文本做摘要与再分段；先去掉标签、再反转义实体（&amp; 等），
    最后把连续空白折成单个空格，避免出现一堆空行。

    注意：`<p>` / `<br>` 等**块级标签要先换成换行**再删其它标签 —— 否则
    "<p>a</p><p>b</p>" 会被压成 "a b"，后面再按行拆段就丢掉了段落结构。
    """
    text = re.sub(r'(?i)</?(?:p|div|br|li|h[1-6]|tr|section|article)\b[^>]*>', '\n', value or '')
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'[ \t\u3000]+', ' ', text)
    text = re.sub(r'\s*\n\s*', '\n', text)
    return text.strip()


def _summary_text(plain_text):
    """摘要：纯文本前 200 字（折成单行，避免摘要里带换行）"""
    return re.sub(r'\s+', ' ', plain_text or '').strip()[:MAX_SUMMARY_LENGTH]


def _paragraphs_to_html(plain_text):
    """
    纯文本 → `<p>` 段落 HTML（新闻正文是富文本字段，直接塞纯文本前端不换行）。

    按空行 / 换行切段；每段做 HTML 转义（原文里残留的 < > 不能把结构弄坏）；
    总长到 MAX_CONTENT_LENGTH 就截断 —— 外部源偶尔整篇贴全文，不能无限入库。
    """
    if not plain_text:
        return ''
    paragraphs = [p.strip() for p in re.split(r'\n+', plain_text) if p.strip()]
    parts = []
    length = 0
    for paragraph in paragraphs:
        piece = f'<p>{html.escape(paragraph)}</p>'
        if length + len(piece) > MAX_CONTENT_LENGTH:
            break
        parts.append(piece)
        length += len(piece)
    return ''.join(parts)


def _is_http_url(url):
    """只接收 http/https：javascript: / ftp: / 相对链接都不能作为"原文链接"入库"""
    scheme = urlparse((url or '').strip()).scheme.lower()
    return scheme in ('http', 'https')


def _first_text(element, *tags):
    """按顺序找第一个非空子元素的文本（RSS 与 Atom 的字段名差异用这个兜底）"""
    for tag in tags:
        value = element.findtext(tag)
        if value and value.strip():
            return value.strip()
    return ''


def _atom_link(entry):
    """Atom 的 link 是带 href 属性的空元素；优先 rel='alternate'，否则取第一个 href"""
    candidates = entry.findall(f'{ATOM_NS}link')
    for link in candidates:
        if (link.get('rel') or 'alternate') == 'alternate' and link.get('href'):
            return link.get('href').strip()
    for link in candidates:
        if link.get('href'):
            return link.get('href').strip()
    return ''


def _parse_rss(root):
    """解析 RSS 2.0：返回 (feed_title, [{title, link, summary, content}, ...])"""
    channel = root.find('channel')
    if channel is None:
        raise ValueError('RSS 缺少 channel 节点')
    feed_title = _first_text(channel, 'title')
    items = []
    for item in channel.findall('item'):
        title = _first_text(item, 'title')
        link = _first_text(item, 'link')
        description = _first_text(item, 'description')
        plain = _strip_html(description)
        items.append({
            'title': title,
            'link': link,
            'summary': _summary_text(plain),
            'content': _paragraphs_to_html(plain),
        })
    return feed_title, items


def _parse_atom(root):
    """解析 Atom：返回 (feed_title, [{title, link, summary, content}, ...])"""
    feed_title = _first_text(root, f'{ATOM_NS}title')
    items = []
    for entry in root.findall(f'{ATOM_NS}entry'):
        title = _first_text(entry, f'{ATOM_NS}title')
        link = _atom_link(entry)
        # summary / content 二选一（content 常常是整篇 HTML，先压成纯文本）
        raw_text = _first_text(entry, f'{ATOM_NS}summary') or _first_text(
            entry, f'{ATOM_NS}content',
        )
        plain = _strip_html(raw_text)
        items.append({
            'title': title,
            'link': link,
            'summary': _summary_text(plain),
            'content': _paragraphs_to_html(plain),
        })
    return feed_title, items


def parse_feed(raw_bytes):
    """解析一份 RSS/Atom 字节流，返回 (feed_title, items)。"""
    root = ET.fromstring(raw_bytes)
    # 根节点决定格式：<rss> 或 <feed xmlns=Atom>；两种都认不出来就报错（由调用方计数）
    if root.tag == 'rss' or root.tag.endswith('}rss') or root.find('channel') is not None:
        return _parse_rss(root)
    if root.tag == f'{ATOM_NS}feed':
        return _parse_atom(root)
    raise ValueError(f'无法识别的 Feed 根节点：{root.tag}')


class Command(BaseCommand):
    help = '抓取 RSS 2.0 / Atom 订阅源，把条目以草稿形式写入行业动态（第 404 批）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', action='append', default=[], metavar='PATH',
            help='本地 RSS/Atom XML 文件（可重复；测试与离线用）',
        )
        parser.add_argument(
            '--url', action='append', default=[], metavar='URL',
            help='远程 RSS/Atom 订阅源地址（可重复）',
        )
        parser.add_argument(
            '--category', default='notice',
            help='入库分类（默认 notice，必须是 News.CATEGORY_CHOICES 的合法值）',
        )
        parser.add_argument(
            '--source', default='', metavar='TEXT',
            help='来源名兜底：feed 没有 <title> 时用它；再没有则「外部资讯」',
        )
        parser.add_argument(
            '--limit', type=int, default=DEFAULT_LIMIT,
            help=f'每个 feed 最多处理条数（默认 {DEFAULT_LIMIT}，合法范围 1..{MAX_LIMIT}）',
        )
        parser.add_argument(
            '--dry-run', action='store_true', help='只打印将创建的标题，不写库',
        )

    def handle(self, *args, **options):
        files = options['file'] or []
        urls = options['url'] or []
        if not files and not urls:
            raise CommandError('请至少提供一个 --file 或 --url 订阅源')

        category = (options['category'] or '').strip()
        if category not in dict(News.CATEGORY_CHOICES):
            raise CommandError(
                f'分类不合法：{category!r}，合法取值：'
                f'{" / ".join(value for value, _label in News.CATEGORY_CHOICES)}'
            )

        limit = options['limit'] if options['limit'] is not None else DEFAULT_LIMIT
        if not 1 <= limit <= MAX_LIMIT:
            limit = DEFAULT_LIMIT

        dry_run = options['dry_run']
        source_fallback = (options['source'] or '').strip()

        total_parsed = total_created = total_skipped = total_errors = 0
        # 同一次运行里的内存判重：dry-run 不写库，只靠 DB 查重会把同一 feed 里的
        # 重复条目都打印成"将创建"。
        seen_links = set()
        seen_titles = set()

        targets = [('file', path) for path in files] + [('url', url) for url in urls]
        for kind, target in targets:
            try:
                if kind == 'file':
                    raw_bytes = Path(target).read_bytes()
                else:
                    response = requests.get(target, timeout=FETCH_TIMEOUT)
                    response.raise_for_status()
                    raw_bytes = response.content
                feed_title, items = parse_feed(raw_bytes)
            except Exception as exc:  # 单个源失败不能中断其它源
                total_errors += 1
                self.stderr.write(self.style.ERROR(
                    f'✗ 读取/解析失败：{kind}={target}（{exc}）'
                ))
                logger.warning('抓取订阅源失败 %s=%s: %s', kind, target, exc)
                continue

            # 来源名：feed 的 <title> 最可信；没有才用 --source 兜底，再没有用默认值
            source = feed_title or source_fallback or '外部资讯'
            parsed = created = skipped = 0
            for item in items[:limit]:
                parsed += 1
                title = (item.get('title') or '').strip()
                link = (item.get('link') or '').strip()
                # 标题/链接缺失的条目没法入库、也没法跳转原文 —— 静默跳过（计入 skipped）
                if not title or not link or not _is_http_url(link):
                    skipped += 1
                    continue
                try:
                    duplicated = (
                        link in seen_links
                        or title.lower() in seen_titles
                        or News.objects.filter(external_url=link).exists()
                        or News.objects.filter(title__iexact=title).exists()
                    )
                    if duplicated:
                        skipped += 1
                        continue
                    if dry_run:
                        self.stdout.write(f'[dry-run] 将创建：{title}')
                        created += 1
                        seen_links.add(link)
                        seen_titles.add(title.lower())
                        continue
                    News.objects.create(
                        title=title,
                        content=item.get('content') or '',
                        summary=item.get('summary') or '',
                        source=source,
                        category=category,
                        external_url=link,
                        is_published=False,  # 外部内容一律先落草稿，人工审核后再发布
                        author=None,
                    )
                    created += 1
                    seen_links.add(link)
                    seen_titles.add(title.lower())
                except Exception as exc:  # 单条坏数据不能拖垮整个 feed
                    total_errors += 1
                    logger.warning('抓取条目入库失败（%s）: %s', title[:40], exc)

            total_parsed += parsed
            total_created += created
            total_skipped += skipped
            self.stdout.write(
                f'  · {kind}={target}：解析 {parsed} 条，创建 {created} 条，跳过 {skipped} 条'
            )

        mode = '（dry-run，未写库）' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'✓ 抓取完成{mode}：解析 {total_parsed} 条，创建 {total_created} 条，'
            f'跳过 {total_skipped} 条，错误 {total_errors} 个'
        ))
