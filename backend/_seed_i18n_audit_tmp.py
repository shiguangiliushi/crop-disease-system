"""
临时脚本（i18n 审计专用夹具）：创建/更新审计管理员账号并造检测记录。

⚠️ 这些是**临时的审计夹具**，不是产品数据：
   - 账号 `zz_i18n_audit` / `ZzI18nAudit!2026` 只为本轮「英文界面残留中文」审计服务；
   - 检测记录带 `[i18n-audit]` 前缀，脚本重跑会先删掉自己造的旧记录再重建，
     因此**可重复执行且不会产生重复数据**；
   - 审计结束后可执行：`python _seed_i18n_audit_tmp.py --cleanup` 删除全部夹具。

用法（在 backend 目录下，用项目 conda 解释器）：
    C:\\Users\\zhx\\anaconda3\\envs\\crop_env\\python.exe _seed_i18n_audit_tmp.py
    输出末行为 JSON：{"username": ..., "password": ..., "token": ..., ...}
    加 --out=<file> 可把同一份 JSON 额外写进文件（审计脚本用文件传递，
    因为受限沙箱里 Node 的 child_process 管道 stdio 会 EPERM）。

参数：
    --cleanup   删除审计账号与其造出的检测记录，然后退出。
    --out=PATH  把 JSON 结果同时写入 PATH。
    --role=admin|user  造哪种角色的夹具（默认 admin）。
                 第 80 批新增 user：**普通用户**看到的页面与管理员不同
                 （少掉管理入口、/history 只看得到自己的记录……），
                 只测管理员会漏掉普通用户路径上的未翻译文案。
"""
import os
import sys
import json
import random
from datetime import timedelta

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.utils import timezone  # noqa: E402
from rest_framework.authtoken.models import Token  # noqa: E402

from api.models import DetectionHistory, PestInfo  # noqa: E402

# ── 临时审计夹具常量（勿用于生产） ───────────────────────────────────────────
AUDIT_PASSWORD = 'ZzI18nAudit!2026'
AUDIT_MARKER = '[i18n-audit]'

#: 两种角色的夹具。第 80 批补 user：普通用户路径必须单独验一遍。
FIXTURES = {
    'admin': {
        'username': 'zz_i18n_audit',
        'email': 'zz_i18n_audit@example.invalid',
        'is_staff': True,
        'is_superuser': True,
        'role': 'ADMIN',
    },
    'user': {
        'username': 'zz_i18n_audit_user',
        'email': 'zz_i18n_audit_user@example.invalid',
        'is_staff': False,
        'is_superuser': False,
        'role': 'USER',
    },
}

#: 造数用的病害：必须存在且 name_en 非空，否则英文界面仍会显示中文（那是被测对象，不是造数问题）
PREFERRED_IDENTIFIERS = [
    'apple_scab',
    'apple_black_rot',
    'grape_black_rot',
    'tomato_late_blight',
]
# 一共造 10 条记录，让 /history 的统计卡与图表非空
RECORD_COUNT = 10

User = get_user_model()


def cleanup():
    """删除全部审计夹具账号及其造出的检测记录"""
    usernames = [spec['username'] for spec in FIXTURES.values()]
    deleted_hist, _ = DetectionHistory.objects.filter(
        user__username__in=usernames
    ).delete()
    deleted_user, _ = User.objects.filter(username__in=usernames).delete()
    print(f'[cleanup] 删除检测记录 {deleted_hist} 行，用户对象 {deleted_user} 行')


def ensure_user(spec):
    user, created = User.objects.get_or_create(
        username=spec['username'],
        defaults={
            'email': spec['email'],
            'is_staff': spec['is_staff'],
            'is_superuser': spec['is_superuser'],
            'role': spec['role'],
            'is_active': True,
        },
    )
    # 幂等：无论新建还是复用，都把状态与密码校正到确定值
    user.email = spec['email']
    user.is_staff = spec['is_staff']
    user.is_superuser = spec['is_superuser']
    user.is_active = True
    user.role = spec['role']
    user.failed_login_attempts = 0
    user.locked_until = None
    user.set_password(AUDIT_PASSWORD)
    user.save()
    print(f'[user] {"created" if created else "reused"}: {user.username} '
          f'is_staff={user.is_staff} is_superuser={user.is_superuser} role={user.role}')
    return user


def ensure_pests():
    """挑出 name_en 非空的病害；优先使用 PREFERRED_IDENTIFIERS"""
    pests = list(
        PestInfo.objects.exclude(name_en='').exclude(name_en__isnull=True).order_by('id')
    )
    by_ident = {p.english_identifier: p for p in pests}
    picked = [by_ident[i] for i in PREFERRED_IDENTIFIERS if i in by_ident]
    if not picked:
        print('[pests] 警告：首选病害都缺失，回退到任意 name_en 非空的病害', file=sys.stderr)
        picked = pests[:4]
    print('[pests] ' + ', '.join(f'{p.id}:{p.english_identifier}({p.name_en})' for p in picked))
    return picked


def seed_history(user, pests):
    """重建审计检测记录（先删后建 → 幂等）"""
    removed, _ = DetectionHistory.objects.filter(
        user=user, detection_result__startswith=AUDIT_MARKER
    ).delete()
    if removed:
        print(f'[history] 清理上次造的记录 {removed} 行')

    rng = random.Random(20260214)  # 固定种子：重跑得到完全一样的数据
    now = timezone.now()
    rows = []
    for idx in range(RECORD_COUNT):
        pest = pests[idx % len(pests)]
        # 分布在最近 12 天内，让「今日/物种/趋势」三个统计维度都有数据
        captured = now - timedelta(days=idx % 6, hours=idx, minutes=rng.randint(0, 59))
        rows.append(
            DetectionHistory(
                user=user,
                # 只存相对路径字符串：这里的图片是**占位引用**，不写实际文件
                image=f'detection_history/{AUDIT_MARKER.strip("[]")}_placeholder_{idx}.jpg',
                detection_result=f'{AUDIT_MARKER} {pest.name_en or pest.name}',
                pest_info=pest,
                confidence=round(rng.uniform(0.72, 0.98), 4),
            )
        )
    DetectionHistory.objects.bulk_create(rows)

    # timestamp 是 auto_now_add，必须再 update 一次才能改成"过去的时间"
    saved = list(
        DetectionHistory.objects.filter(user=user, detection_result__startswith=AUDIT_MARKER)
        .order_by('id')
    )
    for row, offset_idx in zip(saved, range(len(saved))):
        row.timestamp = now - timedelta(days=offset_idx % 6, hours=offset_idx)
    DetectionHistory.objects.bulk_update(saved, ['timestamp'])

    total = DetectionHistory.objects.filter(user=user).count()
    print(f'[history] 审计账号现有检测记录 {total} 行（本次重建 {len(saved)} 行）')
    return total


def main():
    if '--cleanup' in sys.argv:
        cleanup()
        return 0

    role = 'admin'
    for arg in sys.argv[1:]:
        if arg.startswith('--role='):
            role = arg[len('--role='):].strip()
    if role not in FIXTURES:
        print(f'[error] 未知角色 {role!r}；可选：{", ".join(FIXTURES)}', file=sys.stderr)
        return 2

    spec = FIXTURES[role]
    user = ensure_user(spec)
    pests = ensure_pests()
    total = seed_history(user, pests)

    # 令牌：让浏览器端可以直接种登录态，也便于脚本自检
    token, _ = Token.objects.get_or_create(user=user)

    payload = {
        'username': spec['username'],
        'password': AUDIT_PASSWORD,
        'token': token.key,
        'user_id': user.id,
        'role': user.role,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'acting_as': role,
        'detection_history_count': total,
        'temporary_fixture': True,
    }
    print('===SEED-JSON===')
    print(json.dumps(payload, ensure_ascii=False))
    print('===END-SEED-JSON===')

    # 受限沙箱里 Node 无法用管道读子进程 stdout（spawn EPERM），
    # 因此审计脚本用 --out 让本脚本把同一份 JSON 落到文件里再读。
    for arg in sys.argv[1:]:
        if arg.startswith('--out='):
            out_path = arg[len('--out='):]
            with open(out_path, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            print(f'[out] JSON 已写入 {out_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
