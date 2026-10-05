# -*- coding: utf-8 -*-
"""
新闻重复记录处理（默认 dry-run，只预览；加 --apply 才真正执行）

背景（真实的"下架了用户还能看见"）：
    News.title 没有唯一约束，库里出现过 **标题 + 正文逐字节相同** 的两条记录：
        id=25  is_published=False（管理员下架的是这条）
        id=27  is_published=True （用户看到的其实是这条）
    用户在「行业动态」里当然还能看到这条新闻 —— 看起来就像"下架无效"。

处理策略（**只改发布状态，不删数据**）：
    若一组重复记录里已经存在"未发布"的记录（说明管理员已经下架过这条新闻），
    就把同组中仍处于"已发布"的记录一并下架，使前台不再显示；
    若一组重复记录全部处于"已发布"，则只报告、不动手（保留哪条属业务决策）。

    只改一个布尔字段，随时可用 --revert 反向恢复。

用法（在 backend 目录下，用项目环境 crop_env 运行）：
    python ..\\docs\\tools\\fix_duplicate_news.py            # 预览
    python ..\\docs\\tools\\fix_duplicate_news.py --apply     # 执行
    python ..\\docs\\tools\\fix_duplicate_news.py --revert 27 # 把 id=27 重新发布
"""
import argparse
import hashlib
import os
import sys

import django

BACKEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'backend',
)
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')
django.setup()

from api.models import News  # noqa: E402


def fingerprint(news):
    content_md5 = hashlib.md5((news.content or '').encode('utf-8')).hexdigest()
    return (news.title.strip().lower(), content_md5)


def find_groups():
    """返回 [(标题, [(记录, 记录), ...]), ...]，按标题+正文指纹分组"""
    groups = {}
    for news in News.objects.all().order_by('id'):
        groups.setdefault(fingerprint(news), []).append(news)
    return [(key[0], rows) for key, rows in groups.items() if len(rows) > 1]


def collect_targets():
    """需要被下架的记录：同组里存在未发布记录的，其余已发布的记录"""
    targets = []
    for title, rows in find_groups():
        if not any(not row.is_published for row in rows):
            continue
        targets.extend(row for row in rows if row.is_published)
    return targets


def do_revert(news_id):
    news = News.objects.filter(pk=news_id).first()
    if news is None:
        print(f'  id={news_id} 不存在')
        return 1
    news.is_published = True
    news.save(update_fields=['is_published', 'updated_at'])
    print(f'  已恢复发布：id={news.id} {news.title[:30]} -> is_published=True')
    return 0


def main():
    parser = argparse.ArgumentParser(description='新闻重复记录处理（默认只预览）')
    parser.add_argument('--apply', action='store_true', help='真正执行下架')
    parser.add_argument('--revert', type=int, metavar='NEWS_ID', help='把指定新闻恢复为已发布')
    args = parser.parse_args()

    if args.revert:
        return do_revert(args.revert)

    groups = find_groups()
    if not groups:
        print('没有发现重复新闻（标题 + 正文指纹相同）。')
        return 0

    print(f'发现 {len(groups)} 组重复新闻：\n')
    for title, rows in groups:
        print(f'  标题：{rows[0].title[:40]}')
        for row in rows:
            print(f'    id={row.id:<5} is_published={str(row.is_published):<6} '
                  f'created={row.created_at:%Y-%m-%d %H:%M} updated={row.updated_at:%Y-%m-%d %H:%M}')
        print()

    targets = collect_targets()
    if not targets:
        print('所有重复组都处于"已发布"状态，保留哪条属业务决策，脚本不做改动。')
        return 0

    print('计划执行（仅下架，不删除）：')
    for row in targets:
        print(f'    id={row.id} {row.title[:30]} -> is_published=False')

    if not args.apply:
        print('\n以上为预览。确认后加 --apply 执行。')
        return 0

    for row in targets:
        row.is_published = False
        row.save(update_fields=['is_published', 'updated_at'])
    print(f'\n已下架 {len(targets)} 条重复记录。')
    ids = ','.join(str(row.id) for row in targets)
    print(f'如需恢复：python ..\\docs\\tools\\fix_duplicate_news.py --revert <id>   （本批 id: {ids}）')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
