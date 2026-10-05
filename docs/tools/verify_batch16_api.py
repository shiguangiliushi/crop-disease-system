# -*- coding: utf-8 -*-
"""
第 16 批接口回归脚本（评论/回复/点赞/评论编辑/检测历史筛选）

用法（在 backend 目录下，用项目环境 crop_env 运行）：
    1) 先起一个**独立端口**的验证服务，避免影响开发中的 8000：
         python manage.py runserver 127.0.0.1:8001 --noreload
    2) 再跑本脚本：
         python -c "import os,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','crop_disease_backend.settings');django.setup();exec(open(r'..\\docs\\tools\\verify_batch16_api.py',encoding='utf-8').read())"

它做三件事：
  1. 用 ORM 造最小测试数据（两个临时用户 / 帖子评论与回复 / 检测历史）；
  2. 用真实 HTTP 请求打 127.0.0.1:8001，逐条断言期望行为（33 项）；
  3. 打印 PASS/FAIL 汇总（退出码非 0 表示有失败）。
测试评论与检测历史在结尾自动清理；两个临时用户（_batch16_tmp / _batch16_tmp2）
保留以便复跑，确认不再需要时可用 manage.py shell 删除。
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get('B16_BASE', 'http://127.0.0.1:8001/api')
TOKEN = os.environ.get('B16_TOKEN', '')
POST_ID = int(os.environ.get('B16_POST_ID', '101'))   # 一个已存在的帖子
PEST_NAME = '苹果黑星病'

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('  PASS  ' if ok else '  FAIL  ') + name + (('  -> ' + str(detail)) if detail else ''))


def req(method, path, data=None, token=None, timeout=30):
    url = BASE + urllib.parse.quote(path, safe='/?&=%')
    body = None
    headers = {'Accept': 'application/json'}
    if data is not None:
        body = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    tk = token if token is not None else TOKEN
    if tk:
        headers['Authorization'] = 'Token ' + tk
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


# --------------------------------------------------------------------------
# 1. 造数据
# --------------------------------------------------------------------------
from django.contrib.auth import get_user_model                      # noqa: E402
from rest_framework.authtoken.models import Token                   # noqa: E402
from api.models import DetectionHistory, PestInfo                   # noqa: E402
from api.models_forum import Comment, Post                          # noqa: E402

User = get_user_model()
u, _ = User.objects.get_or_create(
    username='_batch16_tmp',
    defaults={'email': 'tmp@example.com', 'role': 'USER'},
)
u.set_password('Tmp#123456')
u.save()
tok, _ = Token.objects.get_or_create(user=u)
TOKEN = tok.key
print('临时用户 token:', TOKEN)

post = Post.objects.get(id=POST_ID)
# 清掉上一次运行留下的数据
Comment.objects.filter(post=post, author=u).delete()
DetectionHistory.objects.filter(user=u).delete()

other_comments = Comment.objects.filter(post=post, is_deleted=False).count()
print('帖子 %s 当前未删除评论数: %s' % (POST_ID, other_comments))

pest = PestInfo.objects.filter(name__icontains='苹果').first()
for i in range(2):
    DetectionHistory.objects.create(
        user=u, image='detection_history/_batch16_tmp.jpg',
        detection_result=PEST_NAME if i == 0 else '苹果黑星病(测试)',
        confidence=0.9, pest_info=pest,
    )
DetectionHistory.objects.create(
    user=u, image='detection_history/_batch16_tmp.jpg',
    detection_result='番茄晚疫病', confidence=0.8, pest_info=None,
)
print('临时检测历史:', DetectionHistory.objects.filter(user=u).count(), '条（其中含“苹果黑星病”2 条）')

# --------------------------------------------------------------------------
# 2. HTTP 断言
# --------------------------------------------------------------------------
print('\n--- 2.1 评论/回复创建响应契约 ---')
st, body = req('POST', '/forums/posts/%s/comments/' % POST_ID, {'content': '第16批验证-顶级评论'})
check('创建顶级评论返回 201', st == 201, st)
comment_id = body.get('id') if isinstance(body, dict) else None
top_obj = Comment.objects.filter(post=post, author=u, content='第16批验证-顶级评论').first()
check('创建评论响应包含 id', isinstance(comment_id, int), body)
check('顶级评论已写入数据库', top_obj is not None, getattr(top_obj, 'id', None))
real_comment_id = top_obj.id if top_obj else None

st2, body2 = req('POST', '/forums/posts/%s/comments/' % POST_ID, {'content': '第16批验证-回复', 'parent': real_comment_id})
check('创建回复返回 201', st2 == 201, st2)
reply_id = body2.get('id') if isinstance(body2, dict) else None
reply_obj = Comment.objects.filter(post=post, author=u, content='第16批验证-回复').first()
check('创建回复响应包含 id', isinstance(reply_id, int), body2)
check('创建回复响应 parent 指向父评论', isinstance(body2, dict) and body2.get('parent') == real_comment_id, body2)
check('回复已写入数据库且 parent 正确', reply_obj is not None and reply_obj.parent_id == real_comment_id,
      getattr(reply_obj, 'parent_id', None))
real_reply_id = reply_obj.id if reply_obj else None

print('\n--- 2.2 评论列表只返回顶级评论（parent__isnull）---')
st, body = req('GET', '/forums/posts/%s/comments/?parent__isnull=true&page_size=100' % POST_ID)
check('评论列表返回 200', st == 200, st)
if st == 200 and isinstance(body, dict):
    ids = [c.get('id') for c in body.get('results', [])]
    check('顶级评论列表中不含刚创建的回复', real_reply_id not in ids, 'reply_id=%s ids=%s' % (real_reply_id, ids))
    check('顶级评论列表中包含刚创建的顶级评论', real_comment_id in ids, ids)
    check('count 只统计顶级评论', body.get('count') == len(ids), 'count=%s len=%s' % (body.get('count'), len(ids)))

print('\n--- 2.3 评论序列化包含 reply_count / reply_to ---')
st, body = req('GET', '/forums/posts/%s/comments/?parent__isnull=true&page_size=100' % POST_ID)
target = None
if st == 200 and isinstance(body, dict):
    target = next((c for c in body.get('results', []) if c.get('id') == real_comment_id), None)
check('顶级评论对象存在', target is not None, target)
if target:
    check('评论含 reply_count 字段', 'reply_count' in target, sorted(target.keys()))
    check('reply_count 统计到 1 条回复', target.get('reply_count') == 1, target.get('reply_count'))

print('\n--- 2.4 回复列表接口 ---')
st, body = req('GET', '/forums/posts/%s/comments/%s/replies/' % (POST_ID, real_comment_id))
check('回复列表返回 200', st == 200, st)
if st == 200:
    rs = body.get('results') if isinstance(body, dict) else body
    check('回复列表包含刚创建的回复', any(r.get('id') == real_reply_id for r in (rs or [])), rs)
    first = (rs or [None])[0] if rs else None
    if first:
        check('回复对象含 reply_to 信息', 'reply_to' in first, sorted(first.keys()))

print('\n--- 2.5 评论点赞返回状态 ---')
st, body = req('POST', '/forums/posts/%s/comments/%s/like/' % (POST_ID, real_comment_id))
check('评论点赞返回 200/201', st in (200, 201), st)
check('点赞响应含 is_liked/like_count', isinstance(body, dict) and 'is_liked' in body and 'like_count' in body, body)
st, body = req('POST', '/forums/posts/%s/comments/%s/like/' % (POST_ID, real_comment_id))
check('再次调用为取消点赞且状态翻转', isinstance(body, dict) and body.get('is_liked') is False, body)

print('\n--- 2.5b 跨用户给他人评论点赞（此前被对象权限误拦）---')
u2, _ = User.objects.get_or_create(
    username='_batch16_tmp2',
    defaults={'email': 'tmp2@example.com', 'role': 'USER'},
)
u2.set_password('Tmp#123456')
u2.save()
tok2, _ = Token.objects.get_or_create(user=u2)
st, body = req('POST', '/forums/posts/%s/comments/%s/like/' % (POST_ID, real_comment_id), token=tok2.key)
check('他人可以给该评论点赞（非 403）', st in (200, 201), 'status=%s body=%s' % (st, body))
check('他人点赞后 like_count = 1', isinstance(body, dict) and body.get('like_count') == 1, body)
st, body = req('GET', '/forums/posts/%s/comments/?parent__isnull=true&page_size=100' % POST_ID, token=tok2.key)
mine = next((c for c in (body.get('results') or []) if c.get('id') == real_comment_id), None) if isinstance(body, dict) else None
check('列表 is_liked 反映他人点赞', bool(mine) and mine.get('is_liked') is True, mine and mine.get('is_liked'))
st, body = req('POST', '/forums/posts/%s/comments/%s/like/' % (POST_ID, real_comment_id), token=tok2.key)
check('他人取消点赞后 like_count = 0', isinstance(body, dict) and body.get('like_count') == 0, body)

print('\n--- 2.6 检测历史：按病害筛选（前端跳页依赖的字段）---')
st, body = req('GET', '/detection-history/?pest=%s&page=1&page_size=1' % PEST_NAME)
total_pest = None
if st == 200 and isinstance(body, dict):
    total_pest = (body.get('data') or {}).get('total')
check('?pest= 生效（total 应为 2）', total_pest == 2, 'status=%s body=%s' % (st, body))
st, body = req('GET', '/detection-history/?disease_name=%s&page=1&page_size=1' % PEST_NAME)
total_dn = (body.get('data') or {}).get('total') if isinstance(body, dict) else None
check('?disease_name= 不被后端识别（total 仍为 3）', total_dn == 3, total_dn)
check('旧前端读的 data.count 字段不存在', isinstance(body, dict) and 'count' not in (body.get('data') or {}), sorted((body.get('data') or {}).keys()) if isinstance(body, dict) else body)

print('\n--- 2.7 错误不再被当成成功（后端 4xx 语义）---')
st, body = req('POST', '/forums/posts/%s/comments/' % POST_ID, {'content': ''})
check('空内容评论被拒绝（4xx）', 400 <= st < 500, st)

print('\n--- 2.8 评论编辑（作者本人可改，他人不可）---')
st, body = req('PATCH', '/forums/posts/%s/comments/%s/' % (POST_ID, real_comment_id),
               {'content': '第16批验证-顶级评论（已编辑）'})
check('作者 PATCH 评论返回 200', st == 200, st)
check('响应含编辑后的内容', isinstance(body, dict) and body.get('content') == '第16批验证-顶级评论（已编辑）', body)
check('响应含 id 与 updated_at', isinstance(body, dict) and 'id' in body and 'updated_at' in body, body)
check('数据库已更新', Comment.objects.get(id=real_comment_id).content == '第16批验证-顶级评论（已编辑）')
st, body = req('PATCH', '/forums/posts/%s/comments/%s/' % (POST_ID, real_comment_id),
               {'content': '他人篡改'}, token=tok2.key)
check('他人编辑该评论被拒绝（403）', st == 403, 'status=%s body=%s' % (st, body))

print('\n--- 2.9 删除评论后，帖子上的「评论数」必须同步（第 17 批修复）---')
post.refresh_from_db()
before_count = post.comment_count
st, _ = req('POST', '/forums/posts/%s/comments/%s/delete/' % (POST_ID, real_reply_id))
check('软删除回复返回 204', st == 204, st)
post.refresh_from_db()
check('删除回复后 post.comment_count 减 1',
      post.comment_count == before_count - 1,
      'before=%s after=%s' % (before_count, post.comment_count))
st, _ = req('POST', '/forums/posts/%s/comments/%s/delete/' % (POST_ID, real_comment_id))
check('软删除顶级评论返回 204', st == 204, st)
post.refresh_from_db()
check('删除顶级评论后再减 1',
      post.comment_count == before_count - 2,
      'before=%s after=%s' % (before_count, post.comment_count))
check('库中计数与实际未删除评论数一致',
      post.comment_count == post.comments.filter(is_deleted=False).count(),
      '%s vs %s' % (post.comment_count, post.comments.filter(is_deleted=False).count()))

# --------------------------------------------------------------------------
# 3. 清理
# --------------------------------------------------------------------------
Comment.objects.filter(post=post, author=u).delete()
# 注意：QuerySet.delete() 是批量删除，不会调用 Comment.delete()，
# 所以这里必须显式重算帖子评论数，否则脚本自己会留下脏数据。
post.update_comment_count()
DetectionHistory.objects.filter(user=u).delete()
print('\n已清理测试数据（并已重算帖子 %s 的评论数）；临时用户保留（便于复跑），如需删除见脚注。' % POST_ID)

failed = [r for r in results if not r[1]]
print('\n================ 汇总 ================')
print('通过 %d / %d' % (len(results) - len(failed), len(results)))
for name, _, detail in failed:
    print('  FAIL: %s -> %s' % (name, detail))
sys.exit(1 if failed else 0)
