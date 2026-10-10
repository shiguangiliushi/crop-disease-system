"""
管理操作日志的写入助手（第 146 批）

用法（在管理端的写操作里各加一行）：

    from .audit import log_admin_action
    log_admin_action(request.user, 'user.suspend', target=target,
                     detail='停用账号并作废其登录凭证', request=request)

三条刻意的设计：

1. **绝不抛异常**：写日志是"附带动作"，不该因为它失败而让停用/删除这类操作整体失败
   （磁盘满、表锁、字段超长都可能）。内部兜住所有异常并降级到 `logger.exception`。
2. **绝不记录凭证**：`detail` 由调用方自己写，但这里会做一次**保险过滤** ——
   清掉形如 `token=...` 的片段；重置链接之类的动作请只写"已签发"，不要拼整条链接。
3. **快照优于外键**：把操作人与目标的名字一起存下来（目标后来改名/被删也能读懂）。
"""
import logging
import re

logger = logging.getLogger(__name__)

#: 目标快照里最多留多少字符（超长标题不该把日志表撑爆）
MAX_REPR = 200
MAX_DETAIL = 2000
#: 保险丝：detail 里若出现 `token=xxx` / `password=xxx` 一律抹掉
SENSITIVE_PATTERN = re.compile(r'(token|password|secret|key)=[^\s&]+', re.IGNORECASE)
#: 模型类名 → 日志里更好读的目标类型（`CustomUser` 直接落到日志里会写成 "customuser"）
TARGET_TYPE_ALIASES = {
    'customuser': 'user',
    'sensitiveword': 'word',
    'forumboard': 'board',
}


def _repr_of(target):
    """目标的展示名快照（用户名 / 标题 / 名称 …）"""
    if target is None:
        return ''
    for attr in ('username', 'title', 'name', 'word'):
        value = getattr(target, attr, None)
        if value:
            return str(value)[:MAX_REPR]
    return str(target)[:MAX_REPR]


def _client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR') if hasattr(request, 'META') else None
    if forwarded:
        return forwarded.split(',')[0].strip()[:39]
    return (request.META.get('REMOTE_ADDR') or None) if hasattr(request, 'META') else None


def sanitize_detail(detail):
    """抹掉 detail 里可能出现的凭证片段（保险丝，见模块 docstring 第 2 条）"""
    text = str(detail or '')
    return SENSITIVE_PATTERN.sub(r'\1=***', text)[:MAX_DETAIL]


def log_admin_action(actor, action, target=None, detail='', request=None,
                     target_type=None, target_id=None, target_repr=None):
    """
    写一条管理操作日志

    :param actor: 操作人（可以是 None —— 系统动作）
    :param action: 形如 `user.suspend`，取值见 `AdminAuditLog.ACTION_CHOICES`
    :param target: 目标对象（会自动取 `username`/`title`/`name`/`word` 做快照）
    :param detail: 补充说明（**不要放凭证**）
    :param request: 用来取 IP；也可以直接传 target_type/target_id
    :param target_repr: **显式指定目标快照**。删除类操作用得上：
        软删除会把用户名改成 `deleted_<id>`，若在删除**之后**才写日志，
        快照抓到的就是这个改名后的值 —— "谁删了谁"当场变成了看不懂的记录。
        所以删除类动作要么在删除前写日志，要么把原用户名显式传进来。
    :returns: 写入的日志对象，失败时返回 None（**不会抛异常**）
    """
    try:
        from .models_audit import AdminAuditLog

        if target_type:
            kind = target_type
        elif target is None:
            kind = ''
        else:
            class_name = target.__class__.__name__.lower()
            kind = TARGET_TYPE_ALIASES.get(class_name, class_name)

        return AdminAuditLog.objects.create(
            actor=actor if getattr(actor, 'is_authenticated', False) else None,
            actor_repr=(getattr(actor, 'username', '') or '')[:150],
            action=action,
            target_type=kind,
            target_id=str(target_id if target_id is not None
                          else (getattr(target, 'pk', '') or '')),
            target_repr=(target_repr if target_repr is not None else _repr_of(target)),
            detail=sanitize_detail(detail),
            ip=_client_ip(request),
        )
    except Exception:  # noqa: BLE001 —— 写日志失败绝不能影响主操作
        logger.exception('写管理操作日志失败 action=%s actor=%s',
                         action, getattr(actor, 'username', '?'))
        return None
