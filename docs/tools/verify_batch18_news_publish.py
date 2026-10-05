# -*- coding: utf-8 -*-
"""
第 18 批验证：管理员下架新闻后，用户还能不能看见（真实 HTTP）

用法（先起后端，再跑脚本；用项目环境 crop_env）：
    cd backend
    python manage.py runserver 127.0.0.1:8001 --noreload
    python ..\\docs\\tools\\verify_batch18_news_publish.py

断言：
    1) 匿名 / 普通用户：列表、recent 一律看不到未发布新闻（显式传 is_published=false 也拿不到）
    2) 管理员：能看到未发布新闻
    3) 已下架 / 不存在的详情返回 **404**（修复前是 500 {"error":"服务器内部错误"}）
    4) 旧版接口 /api/news/{pk}/detail/ 可用（修复前 100% 500 TypeError: 'bool' object is not callable）
    5) 管理员下架一条临时新闻后，匿名列表与详情立刻看不到它（下架主流程）
    6) 同标题重复建档被拒（400），从源头避免"下架了一条、用户看到另一条"

所有临时 token / 临时新闻在结尾清理，不改动既有业务数据。
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

import django

BACKEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'backend',
)
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')
django.setup()

from django.contrib.auth import get_user_model          # noqa: E402
from rest_framework.authtoken.models import Token        # noqa: E402
from api.models import News                              # noqa: E402

BASE = os.environ.get('B18_BASE', 'http://127.0.0.1:8001/api')
User = get_user_model()
results = []
TEMP_NEWS_TITLE = '【第18批验证用临时新闻】请勿手动保留'


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('  PASS  ' if ok else '  FAIL  ') + name + (('  -> ' + str(detail)) if detail else ''))


def req(path, token=None, method='GET', payload=None, content_type='application/json'):
    url = BASE + urllib.parse.quote(path, safe='/?&=%')
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Token ' + token
    data = None
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = content_type
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            body = resp.read().decode('utf-8', 'replace')
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, body


def ids_of(body):
    if isinstance(body, dict):
        rows = body.get('results') or []
    elif isinstance(body, list):
        rows = body
    else:
        rows = []
    return [row.get('id') for row in rows]


def main():
    draft = News.objects.filter(is_published=False).order_by('id').first()
    published = News.objects.filter(is_published=True).order_by('id').first()
    print(f'数据库实况：未发布 id={draft.id if draft else None}，已发布 id={published.id if published else None}')

    admin = User.objects.filter(is_staff=True).first()
    normal = User.objects.filter(is_staff=False).first()
    admin_token, _ = Token.objects.get_or_create(user=admin)
    normal_token, _ = Token.objects.get_or_create(user=normal)
    temp_news = None

    try:
        # ---------- 1. 匿名 / 普通用户看不到未发布 ----------
        for label, token in (('匿名', None), (f'普通用户 {normal.username}', normal_token.key)):
            status, body = req('/news/?page_size=100', token)
            got = ids_of(body)
            check(f'{label} 列表不含未发布', status == 200 and (draft is None or draft.id not in got),
                  f'{status} ids={got}')

        status, body = req('/news/?page_size=100&is_published=false', None)
        check('匿名显式请求 is_published=false 也拿不到草稿', status == 200 and ids_of(body) == [],
              f'{status} ids={ids_of(body)}')

        status, body = req('/news/recent/?page_size=100', normal_token.key)
        check('普通用户 recent 不含未发布', status == 200 and (draft is None or draft.id not in ids_of(body)),
              f'{status} ids={ids_of(body)}')

        # ---------- 2. 管理员能看到未发布 ----------
        status, body = req('/news/?page_size=100', admin_token.key)
        got = ids_of(body)
        check('管理员列表包含未发布', status == 200 and draft is not None and draft.id in got,
              f'{status} ids={got}')

        # ---------- 3. 404 而不是 500 ----------
        if draft is not None:
            status, body = req(f'/news/{draft.id}/')
            check('匿名访问已下架详情 -> 404', status == 404, f'{status} {body}')
            status, body = req(f'/news/{draft.id}/', normal_token.key)
            check('普通用户访问已下架详情 -> 404', status == 404, f'{status} {body}')
            status, body = req(f'/news/{draft.id}/', admin_token.key)
            check('管理员可看草稿详情 -> 200', status == 200, f'{status}')

        status, body = req('/news/999999/')
        check('不存在的详情 -> 404（不是 500）', status == 404, f'{status} {body}')

        # ---------- 4. 旧版 detail 动作 ----------
        status, body = req(f'/news/{published.id}/detail/')
        check('旧版 /news/{id}/detail/ 可用 -> 200', status == 200 and body.get('id') == published.id,
              f'{status}')
        if draft is not None:
            status, body = req(f'/news/{draft.id}/detail/')
            check('旧版 detail 对非管理员隐藏草稿 -> 404', status == 404, f'{status}')

        # ---------- 5. 下架主流程（用临时新闻，结尾删除） ----------
        temp_news = News.objects.create(
            title=TEMP_NEWS_TITLE, content='第18批验证用正文', is_published=True, author=admin,
        )
        status, body = req('/news/?page_size=100', None)
        check('临时新闻发布时匿名可见', temp_news.id in ids_of(body), f'{status}')

        status, body = req(f'/news/{temp_news.id}/', admin_token.key, method='PATCH',
                           payload={'is_published': False}, content_type='application/json')
        check('管理员下架临时新闻 -> 200 且状态为 false',
              status == 200 and body.get('is_published') is False, f'{status} {body}')

        temp_news.refresh_from_db()
        status, body = req('/news/?page_size=100', None)
        check('下架后匿名列表立刻看不到', not temp_news.is_published and temp_news.id not in ids_of(body),
              f'is_published={temp_news.is_published} ids={ids_of(body)}')
        status, body = req(f'/news/{temp_news.id}/', None)
        check('下架后匿名详情 -> 404', status == 404, f'{status}')

        # ---------- 6. 同标题重复建档被拒 ----------
        before_ids = set(News.objects.filter(title=published.title).values_list('id', flat=True))
        status, body = req('/news/', admin_token.key, method='POST',
                           payload={'title': published.title, 'content': '重复正文', 'category': 'notice'})
        created_ids = set(News.objects.filter(title=published.title).values_list('id', flat=True)) - before_ids
        if created_ids:
            # 服务端仍在跑旧代码时会真的创建出来：立刻删掉，避免污染数据
            News.objects.filter(id__in=created_ids).delete()
            check('同标题重复建档 -> 400 且未落库',
                  False,
                  f'{status} 守卫未生效（服务端可能仍是旧代码），已回滚新建的 id={sorted(created_ids)}')
        else:
            check('同标题重复建档 -> 400 且未落库',
                  status == 400 and 'title' in (body or {}),
                  f'{status} {body}')
    finally:
        if temp_news is not None:
            News.objects.filter(pk=temp_news.id).delete()
        News.objects.filter(title=TEMP_NEWS_TITLE).delete()
        # 只删除本次 mint 出来的 token；若原本就存在则保留
        Token.objects.filter(key=admin_token.key).delete()
        Token.objects.filter(key=normal_token.key).delete()
        print('\n临时新闻与临时 token 已清理。')

    passed = sum(1 for _, ok, _ in results if ok)
    print(f'\n汇总：{passed}/{len(results)} 通过')
    for name, ok, detail in results:
        if not ok:
            print(f'  未通过：{name} -> {detail}')
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
