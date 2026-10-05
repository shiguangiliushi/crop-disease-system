# -*- coding: utf-8 -*-
"""
第 17 批验证：历史记录页「识别者」可见性（管理员 vs 普通用户 vs role=ADMIN）

用法（在 backend 目录下，用项目环境 crop_env 运行）：
    1) python manage.py runserver 127.0.0.1:8001 --noreload
    2) python -c "import os,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','crop_disease_backend.settings');django.setup();exec(open(r'..\\docs\\tools\\verify_batch17_admin_owner.py',encoding='utf-8').read())"

断言（真实 HTTP）：
  - 管理员 + all_users=true：能看到**全部用户**的记录，且每条都带 user.username（可看出是谁识别的）
  - 管理员不带 all_users：只看得到自己的记录
  - 普通用户 + all_users=true：只看得到自己的记录（不越权）
  - role=ADMIN 但 is_staff=False 的账号：后端同样按管理员对待（前端 isAdmin 判定需与之一致）
所有临时 token / 临时用户 / 临时记录在结尾清理。
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get('B17_BASE', 'http://127.0.0.1:8001/api')
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('  PASS  ' if ok else '  FAIL  ') + name + (('  -> ' + str(detail)) if detail else ''))


def req(path, token):
    r = urllib.request.Request(
        BASE + urllib.parse.quote(path, safe='/?&=%'),
        headers={'Accept': 'application/json', 'Authorization': 'Token ' + token},
    )
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def req_login(username, password):
    """真实走 POST /api/login/（不带 token）"""
    payload = json.dumps({'username': username, 'password': password}).encode('utf-8')
    r = urllib.request.Request(
        BASE + '/login/', data=payload,
        headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


from django.contrib.auth import get_user_model                      # noqa: E402
from rest_framework.authtoken.models import Token                   # noqa: E402
from api.models import DetectionHistory                             # noqa: E402

User = get_user_model()
total_records = DetectionHistory.objects.count()
owners = set(DetectionHistory.objects.values_list('user__username', flat=True))
print('数据库中识别记录:', total_records, '条，归属用户:', sorted(owners))

admin = User.objects.get(username='admin')
normal = User.objects.get(username='123456')
normal_id = normal.id

temp_admin, _ = User.objects.get_or_create(
    username='_batch17_roleadmin',
    defaults={'email': 'ra@example.com', 'role': 'ADMIN', 'is_staff': False},
)
temp_admin.role = 'ADMIN'
temp_admin.is_staff = False
temp_admin.save(update_fields=['role', 'is_staff'])

admin_tok, _ = Token.objects.get_or_create(user=admin)
normal_tok, _ = Token.objects.get_or_create(user=normal)
temp_tok, _ = Token.objects.get_or_create(user=temp_admin)

print('\n--- 管理员视角 ---')
st, body = req('/detection-history/?all_users=true&page_size=100', admin_tok.key)
items = (body.get('data') or {}).get('items', []) if isinstance(body, dict) else []
seen = sorted({(i.get('user') or {}).get('username') for i in items})
check('管理员带 all_users=true 返回 200', st == 200, st)
check('管理员能看到全部用户的记录', len(items) == total_records, '返回 %s / 库中 %s' % (len(items), total_records))
check('每条记录都带 user.username（可看出是谁识别的）',
      all((i.get('user') or {}).get('username') for i in items), seen)
check('返回结果横跨多个用户', len([s for s in seen if s]) >= 2, seen)

st, body = req('/detection-history/?page_size=100', admin_tok.key)
own_items = (body.get('data') or {}).get('items', []) if isinstance(body, dict) else []
check('管理员不带 all_users 时只看得到自己的记录',
      all((i.get('user') or {}).get('username') == 'admin' for i in own_items), len(own_items))

print('\n--- 普通用户视角（不越权）---')
st, body = req('/detection-history/?all_users=true&page_size=100', normal_tok.key)
n_items = (body.get('data') or {}).get('items', []) if isinstance(body, dict) else []
n_owners = sorted({(i.get('user') or {}).get('username') for i in n_items})
expected = DetectionHistory.objects.filter(user_id=normal_id).count()
check('普通用户带 all_users=true 仍只看得到自己', len(n_items) == expected, '返回 %s / 自己的 %s' % (len(n_items), expected))
check('普通用户结果里只有自己', n_owners == ['123456'], n_owners)

print('\n--- role=ADMIN 但 is_staff=False（前端 isAdmin 判定必须与之对齐）---')
st, body = req('/detection-history/?all_users=true&page_size=100', temp_tok.key)
ra_items = (body.get('data') or {}).get('items', []) if isinstance(body, dict) else []
check('后端把 role=ADMIN 当管理员（能看到全部记录）', len(ra_items) == total_records,
      '返回 %s / 库中 %s' % (len(ra_items), total_records))

print('\n--- 登录响应必须带 role（否则前端所有 role 判定都是死代码）---')
temp_admin.set_password('Role#Admin123')
temp_admin.save()
st, body = req_login('_batch17_roleadmin', 'Role#Admin123')
login_user = ((body or {}).get('data') or {}).get('user') or {} if isinstance(body, dict) else {}
check('登录返回 200', st == 200, st)
check('登录响应包含 role', 'role' in login_user, sorted(login_user.keys()))
check('role 值为 ADMIN', login_user.get('role') == 'ADMIN', login_user.get('role'))
check('该账号 is_staff 仍为 False（确属"仅角色管理员"场景）', login_user.get('is_staff') is False,
      login_user.get('is_staff'))
check('登录返回的 token 可用', bool(((body or {}).get('data') or {}).get('token')))

# ---------------------------------------------------------------------------
# 清理
# ---------------------------------------------------------------------------
for t in (admin_tok, normal_tok, temp_tok):
    t.delete()
temp_admin.delete()
print('\n已清理临时 token 与临时用户；识别记录未做任何改动（仍为 %s 条）' % DetectionHistory.objects.count())

failed = [r for r in results if not r[1]]
print('\n================ 汇总 ================')
print('通过 %d / %d' % (len(results) - len(failed), len(results)))
for name, _, detail in failed:
    print('  FAIL: %s -> %s' % (name, detail))
sys.exit(1 if failed else 0)
