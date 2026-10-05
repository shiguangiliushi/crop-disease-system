"""
密码策略（第 106 批新增）
============================================================================
**为什么要有这个文件**：改前"密码最少几位"这件事在项目里有**三套说法**：

| 位置 | 最短 | 其它规则 |
|---|---|---|
| 注册 `serializers.py` | 6 | 无 |
| 邮箱重置 `views_user.py` | 6 | **一条都没有** |
| 修改密码 `views_user.py` | 8 | 不能纯数字、不能与旧密码相同 |

后果是**自相矛盾的用户体验**：用户可以用邮箱把密码重置成 `123456`，
但打开「修改密码」页却**不能**把它改成 `123456`（也不允许纯数字）。
前端文案也跟着分裂：`frontend/src/i18n/messages.js` 里同时存在
「至少 6 位」与「至少 8 位」两组 key，分别对应两个页面。

更根本的问题是：**没有任何一处写明哪个才是策略**。
所以这里把它定成唯一来源，三处校验全部改成调用它 ——
以后要调策略只改这一个文件，不会再分叉。

策略（取值理由）
----------------------------------------------------------------------------
* **最短 8 位**：取原来三套里**最严**的那一套。这是本项目唯一有安全论证的选项
  （见第 35 批：加入登录失败锁定与限流，就是为了别让弱密码被撞开）。
  向弱的对齐（都改 6）等于**主动放宽**一个已有的安全约束；
  向强的对齐只会影响少数老用户 —— 而且**只在他们下次改密码时**，
  存量账号仍能正常登录（登录不做长度校验，见下）。
* **禁止纯数字**：`12345678` 只有 8 位但搜索空间极小。
  这条规则本来只在"修改密码"里有，现在注册与重置也生效。
* **注册时额外做 Django 内置校验**（`AUTH_PASSWORD_VALIDATORS` 里的
  `CommonPasswordValidator` / `NumericPasswordValidator`）：
  能挡住 `password`、`qwerty123` 这类常见弱口令 —— 这是纯自研规则做不到的。
  存量用户的旧密码不受影响（登录不跑校验器）。

**为什么登录不做长度校验**：一旦登录也校验，所有旧密码短于 8 位的用户
会在升级后**突然登不进来**，而他们没有任何办法自己解决（找回密码又要求 8 位，
等于被锁在门外）。这是"安全加固"最容易造成的自伤，所以刻意不做。
"""
from __future__ import annotations

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError

#: 密码最短长度 —— **全项目唯一来源**，前端文案与后端校验都以此为准
MIN_LENGTH = 8

#: 需要展示给用户的规则说明（i18n 文案与错误消息都从这里取口径）
POLICY_HINT = f'至少 {MIN_LENGTH} 位，且不能是纯数字'

#: 我们实际要跑的 Django 内置校验器 —— **显式实例化，不读 settings**。
#:
#: ⚠️ 为什么不能依赖 `password_validation.validate_password()` 的默认行为：
#:    它遍历的是 `settings.AUTH_PASSWORD_VALIDATORS`，而本项目那段配置
#:    **整段被注释掉了**（`settings.py` 里没有写明原因，见该处第 106 批补的说明）。
#:    于是 `validate_password('password')` 会**通过** —— 实测确认过。
#:    显式列出来，行为就不再受那份（可能被改回来的）配置影响。
#:    注：不用 `UserAttributeSimilarityValidator`，因为"与用户名相似"这条
#:    对农户常用的"姓名+生日"式密码过于苛刻，且我们的用户名本来就不允许中文/空格。
EXPLICIT_VALIDATORS = [
    password_validation.MinimumLengthValidator(min_length=MIN_LENGTH),
    password_validation.CommonPasswordValidator(),
    password_validation.NumericPasswordValidator(),
]


def validate_password(password: str, *, user=None, check_common: bool = True) -> str | None:
    """
    校验密码是否满足策略。**通过返回 None，不通过返回一句可直接展示给用户的中文**。

    为什么返回字符串而不是抛异常：三处调用方的响应形状各不相同
    （DRF 序列化器要 `serializers.ValidationError`、两个 APIView 要
    `Response({'status': 'error', 'message': ...})`），让调用方自己决定怎么包装，
    比在这里抛一个"所有人都得 catch 的异常"更省事，也更不容易漏 catch。

    :param user: 已有用户对象（按主键/用户名做相似度判断时要用）
    :param check_common: 是否顺带跑 Django 内置校验器（挡常见弱口令）。默认开。
    """
    if not password:
        return '请输入密码'
    if len(password) < MIN_LENGTH:
        return f'密码至少 {MIN_LENGTH} 位'
    if password.isdigit():
        return '密码不能是纯数字'

    if check_common:
        for validator in EXPLICIT_VALIDATORS:
            try:
                validator.validate(password, user)
            except ValidationError as exc:
                message = ' '.join(exc.messages)
                # ⚠️ 内置校验器的消息**语言是不固定的**，这里必须同时认中英文：
                #    项目 `LANGUAGE_CODE = 'zh-hans'`，所以 `CommonPasswordValidator`
                #    返回的是「这个密码太常见了。」（中文），
                #    而 `MinimumLengthValidator` 却是英文的
                #    （Django 的 zh-Hans 翻译里恰好缺这条）。实测两种都出现过。
                #    所以先在中文里认关键词、再退回英文，最后原样返回 —— 不再猜测。
                lowered = message.lower()
                if '太常见' in message or 'too common' in lowered:
                    return '这个密码太常见了，请换一个更难猜的'
                if '纯数字' in message or 'entirely numeric' in lowered:
                    return '密码不能是纯数字'
                if '太短' in message or 'too short' in lowered:
                    return f'密码至少 {MIN_LENGTH} 位'
                return f'密码不符合要求：{message}'
    return None


def is_valid_password(password: str, *, user=None) -> bool:
    """只想要布尔值时用这个（例如测试里断言）"""
    return validate_password(password, user=user) is None
