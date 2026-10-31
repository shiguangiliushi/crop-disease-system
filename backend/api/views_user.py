# 用户相关接口（注册后的资料 / 密码 / 头像 / 注销 / 管理端用户列表）
# ============================================================================
# 按 APIView 分块，主要落点：
#   · `UsernameCheckView` / `RegisterView`   用户名实时校验、注册（见 views.py）
#   · `PasswordResetRequestView` / `PasswordResetConfirmView`  邮箱找回密码
#   · `UserAvatarView`        头像上传（2MB + 白名单，比新闻/论坛的 5MB 更严）
#   · `UserPasswordChangeView` 修改密码（**策略见 `api/password_policy.py`**）
#   · `AccountDeleteView` / `AccountCancelDeletionView`
#                             **注销与取消注销**（第 95/101 批，15 天冷静期）
#   · `AdminUserListView`     管理端用户列表 + 第 100 批的批量删除
#
# 改这个文件前值得知道的几件事：
#   · 密码规则**只有一个来源**：`api/password_policy.py`。
#     第 106 批之前这里有第三套规则（另两套在注册与邮箱重置），已经统一；
#   · `AccountCancelDeletionView` 是**匿名**的（账号已停用、拿不到 Token），
#     靠"用户名+密码"认身份 —— 它挂了 `ScopedRateThrottle`（第 106 批补的），
#     **别把限流删掉**：第 91 批移除 `/api/token-auth/` 的理由正是"能无限撞库"；
#   · 这个文件里"删除用户"有三条不同语义的路径，别混：
#     本人注销（进冷静期）、管理员单删、管理员批量删 ——
#     三条都会走 `_check_delete_allowed`（不能删自己、不能删最后一个超管）。
from rest_framework.views import APIView  # 导入DRF的API视图基类
from rest_framework.response import Response  # 导入DRF的响应类
from rest_framework import status, permissions  # 导入DRF的状态码和权限类
from rest_framework.generics import get_object_or_404  # 导入获取对象或404异常的函数
from rest_framework.pagination import PageNumberPagination  # 导入分页类
from .pagination import CustomPagination  # 第 76 批：认 page_size 的全站统一分页
from rest_framework.parsers import MultiPartParser, FormParser  # 第23批：头像上传需要 multipart 解析
# 第 231 批：改密码/停用时要吊销**所有设备**的凭证（含新的 DeviceToken）；
# 轮换后给当前设备补发一张 —— 不再直接用 DRF 的 Token
from .models_token import DeviceToken, device_of, revoke_all
from django.contrib.auth import get_user_model  # 导入获取用户模型的函数
from .audit import log_admin_action  # 第 146 批：管理操作日志
from django.contrib.auth import logout  # 第 95 批：注销账号时清掉当前会话
from django.db.models import Count  # 导入Django的计数聚合函数
import logging  # 导入日志模块

# 第 124 批：能力口径统一（用户管理 = USER_ADMIN；提权护栏 = is_full_admin）
# 第 128 批：内容模块授权（改角色时同时勾选"内容审核/新闻管理/病害百科/意见反馈"）
from .capabilities import (
    CAP_USER_ADMIN, CONTENT_MODULES, MODULE_LABELS,
    IsUserAdmin, content_modules_of, has_capability, is_full_admin,
)

from .serializers import (
    UserProfileSerializer,
    UserPublicProfileSerializer,
    UserProfileUpdateSerializer,
    UserStatsSerializer,
    PostListSerializer,
    AdminUserSerializer,  # 第 76 批：管理端用户管理
)  # 导入自定义序列化器
from .serializers_forum import UserCommentSerializer  # 第 25 批：用户评论列表（带"发在哪里"的上下文）
from .models_forum import Post, Comment, Like  # 导入论坛相关模型
from .models import EditorModuleGrant  # 第 128 批：编辑员的模块授权（改角色时一起写）
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.generics import ListAPIView
# 第 35 批：账号安全（用户名实时校验 / 找回密码）
import re  # 用户名格式校验
from django.conf import settings  # FRONTEND_BASE_URL / DEFAULT_FROM_EMAIL
from django.contrib.auth.tokens import default_token_generator  # 重置密码 token
from django.core.mail import send_mail  # 发送重置邮件
from django.utils.encoding import force_bytes, force_str  # uid 编解码
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from rest_framework.throttling import ScopedRateThrottle  # 按 scope 限流
# 第 106 批：密码策略的唯一来源（注册 / 重置 / 改密三处共用，避免规则分叉）
from .password_policy import MIN_LENGTH as PASSWORD_MIN_LENGTH, validate_password

logger = logging.getLogger(__name__)
from .i18n import render_for  # 第 276 批：用户可见文案多语言  # 获取日志记录器

User = get_user_model()  # 获取用户模型


# ============================================================================
# 找回密码：链接与邮件（第 35 批，第 120 批抽出成模块级函数）
# ----------------------------------------------------------------------------
# 为什么抽出来：原来这套只在 `PasswordResetRequestView._send_reset_mail` 里，
# 第 120 批的「管理员生成一次性重置链接」要用**完全一样**的签发方式
# （uid + default_token_generator），抄一份必然有一天两边不一致
# （一边改了有效期、另一边没改，就会出现"邮件链接能用、管理员给的链接不能用"）。
# ============================================================================
def build_password_reset_url(user):
    """生成一次性重置链接：{FRONTEND_BASE_URL}/reset-password?uid=..&token=.."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    base = getattr(settings, 'FRONTEND_BASE_URL', 'http://127.0.0.1:5173').rstrip('/')
    return f'{base}/reset-password?uid={uid}&token={token}'


def send_password_reset_mail(user):
    """
    给用户的注册邮箱发重置邮件。返回 True/False（发不出去只记日志，不抛异常 ——
    调用方是匿名接口，500 等于告诉攻击者"这个账号存在"）。
    """
    reset_url = build_password_reset_url(user)
    subject = '【作物病害识别系统】重置你的登录密码'
    body = (
        f'你好 {user.username}：\n\n'
        f'我们收到了重置该账号密码的请求。请在 1 小时内打开下面的链接设置新密码：\n\n'
        f'{reset_url}\n\n'
        f'如果这不是你本人的操作，忽略本邮件即可，你的密码不会被修改。\n'
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
        logger.info('已发送密码重置邮件: user_id=%s', user.id)
        return True
    except Exception:
        logger.exception('发送密码重置邮件失败: user_id=%s', user.id)
        return False


# ============================================================================
# 账号安全相关接口（第 35 批）
# ----------------------------------------------------------------------------
# 用户反馈里"安全性/账号体验"一节的三项：注册用户名实时校验、忘记密码（邮箱重置）、
# 以及配套的限流。原来这三块都没有：注册要等提交后才知道用户名被占用；
# 忘记密码只有一句"请联系管理员重置"。
# ============================================================================

#: 用户名规则：3-20 位，字母/数字/下划线，必须以字母开头
#  （与前端提示保持一致；服务端才是权威校验）
USERNAME_PATTERN = re.compile(r'^[A-Za-z][A-Za-z0-9_]{2,19}$')


def validate_username_format(username):
    """返回 (是否合法, 错误信息)"""
    if not username:
        return False, '请输入用户名'
    if len(username) < 3:
        return False, '用户名至少 3 个字符'
    if len(username) > 20:
        return False, '用户名最多 20 个字符'
    if not USERNAME_PATTERN.match(username):
        return False, '用户名需以字母开头，只能包含字母、数字和下划线'
    if User.objects.filter(username__iexact=username).exists():
        return False, '该用户名已被占用'
    return True, '该用户名可以使用'


class SiteConfigView(APIView):
    """
    站点公开配置（第 38 批）

    GET /api/site-config/  →  { post_require_review: bool }

    用途：发帖页要如实告诉用户"发布后是否需管理员审核"。这个开关由后端 settings 决定，
    前端硬编码就会说谎（管理员一改环境变量，界面提示就与真实行为不符）。
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({
            'post_require_review': bool(getattr(settings, 'POST_REQUIRE_REVIEW', False)),
        })


class UsernameAvailabilityView(APIView):
    """
    注册时实时校验用户名是否可用（第 35 批）

    GET /api/users/check-username/?username=xxx
    → {available: bool, message: str}
    匿名可访问（注册前还没账号），按 IP 限流防刷。
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'username_check'

    def get(self, request):
        username = (request.query_params.get('username') or '').strip()
        available, message = validate_username_format(username)
        return Response({'available': available, 'message': message, 'username': username})


class PasswordResetRequestView(APIView):
    """
    忘记密码 —— 发送重置邮件（第 35 批）

    POST /api/password-reset/  {username_or_email}
    · 无论账号是否存在，都返回同样的话术（避免"用户名枚举"）；
    · 命中账号时给注册邮箱发一封带重置链接的邮件（开发环境用控制台后端，
      邮件正文会直接打印在后端终端里）；
    · 邮件里的链接形如 {FRONTEND_BASE_URL}/reset-password?uid=xx&token=yy（1 小时内有效）。

    ⚠️ 第 120 批：**"没绑邮箱"的账号在这里是静默失败的** ——
       后端什么都不做，但对外话术完全一致（这是防枚举的代价，见 `post`）。
       管理端账号大多是超管开通的、常常没绑邮箱，于是"管理员忘了密码"这条路是断的。
       现在由 `AdminUserResetLinkView` 补上一条**在系统内**能走通的路。
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    GENERIC_MESSAGE = '如果该账号存在且已绑定邮箱，我们已发送重置链接，请查收邮件（含垃圾箱）。'

    def post(self, request):
        account = (request.data.get('username_or_email') or request.data.get('account') or '').strip()
        if not account:
            return Response({'status': 'error', 'message': render_for(request, 'reset.missing_account')},
                            status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(username__iexact=account).first()
        if user is None:
            user = User.objects.filter(email__iexact=account).first()

        # 只有"账号存在 + 已绑定邮箱 + 未禁用"才真的发信，但对外话术完全一致
        if user is not None and user.email and user.is_active:
            send_password_reset_mail(user)
        else:
            # 第 256 批：**不记账号名**。接口话术已经防枚举，日志却把"命中与否"写清楚，
            # 日志外泄时等于送了一份账号有效性清单。
            logger.info('找回密码请求已受理（未发信）')

        return Response({'status': 'success', 'message': self.GENERIC_MESSAGE})


class PasswordResetConfirmView(APIView):
    """
    忘记密码 —— 用邮件里的 uid + token 设置新密码（第 35 批）

    POST /api/password-reset/confirm/  {uid, token, new_password}
    · 校验 token（含有效期）；
    · 设置新密码后：**清空登录失败锁定**、**删除旧 token**（强制所有端重新登录）。
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request):
        uid = request.data.get('uid') or ''
        token = request.data.get('token') or ''
        new_password = request.data.get('new_password') or ''

        if not uid or not token:
            return Response({'status': 'error', 'message': render_for(request, 'reset.incomplete_link')},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({'status': 'error', 'message': render_for(request, 'reset.invalid_link')},
                            status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, token):
            return Response({'status': 'error', 'message': render_for(request, 'reset.expired_link')},
                            status=status.HTTP_400_BAD_REQUEST)

        # 第 106 批：密码策略改为统一来源（原来这里只判 `len < 6`，
        # 于是**邮箱重置成了整条链路上最弱的一环** —— 用户能把密码重置成
        # `123456`，却在「修改密码」页不允许这么设，前后自相矛盾。
        # 现在注册 / 重置 / 改密三处都走 password_policy，规则不再分叉。
        # 放在取到 user 之后：内置校验器要用它做"与用户名过于相似"的判断。
        problem = validate_password(new_password, user=user)
        if problem:
            return Response({'status': 'error', 'message': problem},
                            status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=['password', 'failed_login_attempts', 'locked_until'])

        # 旧 token 全部作废：密码变了，之前登录过的设备必须重新登录
        # 第 231 批：两种 token 一起吊销（DeviceToken + 老 Token）
        revoke_all(user)

        logger.info('用户通过邮件重置了密码: user_id=%s', user.id)
        return Response({'status': 'success', 'message': render_for(request, 'reset.done')})


class UserProfileView(APIView):  # 定义用户资料视图类
    """
    用户资料API
    GET   /api/users/{user_id}/  - 查看用户资料
        · 本人或管理员：返回完整信息（含邮箱、最后登录时间）
        · 其他人/匿名：仅返回公开信息（不含邮箱等敏感字段）
    PATCH /api/users/{user_id}/  - 修改用户资料（仅本人或管理员）
        可修改字段：first_name / last_name / email / bio
    """
    permission_classes = [permissions.AllowAny]  # 查看资料允许任何人访问

    @staticmethod
    def _is_self_or_admin(request, target):
        """
        本人、或具备 `USER_ADMIN` 能力的账号

        第 124 批：这里管的是"能不能看/改**别人的**资料（含邮箱、最后登录时间）"，
        与用户管理同一口径 = `USER_ADMIN`（**信息编辑员不可**）。
        """
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        return bool(
            user.id == target.id or
            has_capability(user, CAP_USER_ADMIN)
        )

    def get(self, request, user_id):  # 定义GET请求处理方法
        user = get_object_or_404(User, id=user_id)  # 获取用户对象或返回404

        if self._is_self_or_admin(request, user):
            serializer = UserProfileSerializer(user, context={'request': request})
        else:
            serializer = UserPublicProfileSerializer(user, context={'request': request})
        return Response(serializer.data)  # 返回序列化后的数据

    def patch(self, request, user_id):  # 修改资料
        if not request.user or not request.user.is_authenticated:
            return Response({'detail': '请先登录'}, status=status.HTTP_401_UNAUTHORIZED)

        user = get_object_or_404(User, id=user_id)
        if not self._is_self_or_admin(request, user):
            return Response({'detail': '没有权限修改该用户资料'}, status=status.HTTP_403_FORBIDDEN)

        serializer = UserProfileUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(UserProfileSerializer(user, context={'request': request}).data)

    def put(self, request, user_id):  # 与 PATCH 行为一致（前端统一用 PATCH）
        return self.patch(request, user_id)


class UserAvatarView(APIView):
    """
    用户头像（第 23 批新增）

    POST   /api/users/{user_id}/avatar/   上传 / 替换头像（仅本人或管理员）
    DELETE /api/users/{user_id}/avatar/   删除头像（恢复为"无头像"，前端用首字母兜底）

    背景：`CustomUser` 此前**没有** avatar 字段，`UserProfileSerializer.get_avatar()`
    恒返回 None，前端只能用 `https://ui-avatars.com` 这个外网服务生成占位图（断网即裂）。
    现在改为真实图片上传，文件落在 `MEDIA_ROOT/avatars/` 下。
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
    MAX_SIZE = 2 * 1024 * 1024  # 2MB

    @staticmethod
    def _resolve_target(request, user_id):
        """返回 (目标用户, 错误响应)；无权操作时第二个元素非空"""
        target = get_object_or_404(User, id=user_id)
        if not UserProfileView._is_self_or_admin(request, target):
            return target, Response(
                {'detail': '没有权限修改该用户的头像'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return target, None

    def post(self, request, user_id):
        target, denied = self._resolve_target(request, user_id)
        if denied is not None:
            return denied

        upload = request.FILES.get('avatar') or request.FILES.get('image')
        if upload is None:
            return Response({'detail': '未提供头像文件'}, status=status.HTTP_400_BAD_REQUEST)
        if upload.content_type not in self.ALLOWED_TYPES:
            return Response(
                {'detail': '头像仅支持 JPEG / PNG / WebP / GIF 格式'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size > self.MAX_SIZE:
            return Response(
                {'detail': '头像大小不能超过 2MB'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_avatar = target.avatar
        target.avatar = upload
        target.save(update_fields=['avatar'])

        # 替换成功后再删旧文件，避免媒体目录里越堆越多
        if old_avatar:
            try:
                old_avatar.delete(save=False)
            except Exception as e:  # noqa: BLE001  删不掉旧文件不应让上传失败
                logger.warning('删除旧头像失败: %s', e)

        logger.info('用户 %s 更新了头像（目标 id=%s）', request.user.username, target.id)
        return Response(
            UserProfileSerializer(target, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, user_id):
        target, denied = self._resolve_target(request, user_id)
        if denied is not None:
            return denied

        if target.avatar:
            try:
                target.avatar.delete(save=False)
            except Exception as e:  # noqa: BLE001
                logger.warning('删除头像文件失败: %s', e)
            target.avatar = None
            target.save(update_fields=['avatar'])

        return Response(
            UserProfileSerializer(target, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )


class UserPasswordChangeView(APIView):
    """
    修改密码（第 23 批新增）

    POST /api/users/{user_id}/password/   body: {"old_password": "...", "new_password": "..."}

    规则：
    - **仅本人**可改（管理员请用 Django 后台），且必须校验旧密码；
    - 新密码的长度与"不能纯数字"两条**来自统一策略**（`api/password_policy.py`，
      第 106 批起与注册、邮箱重置共用同一套；此前这里单独写着 8 位，
      而注册与重置是 6 位，三处不一致）；
    - 新密码不能与旧密码相同（这一条只在本接口有意义，故留在本地）；
    - 改完**轮换 token** 并把新 token 返回给调用方：
      密码一旦泄露，光改密码并不能踢掉旧设备上已签发的 token，所以这里直接作废旧 token；
      当前标签页拿到新 token 后可无缝继续使用。

    背景：此前「用户资料」里完全没有改密码入口，用户想换密码只能找管理员。
    """
    permission_classes = [permissions.IsAuthenticated]

    # 第 106 批：删掉了本类自己的 `MIN_LENGTH = 8`。
    # 长度与"纯数字"两条规则改由 `api/password_policy.py` 统一提供 ——
    # 之前这里是三套规则里的第三套（另两套在注册与邮箱重置），
    # 保留一个"看起来像配置、实际只影响一个接口"的类属性只会继续误导人。
    # 现在要调策略只改 password_policy.py 一处。
    MIN_LENGTH = PASSWORD_MIN_LENGTH  # 仅为向后兼容保留（有测试/调用方可能读它）

    def post(self, request, user_id):
        target = get_object_or_404(User, id=user_id)
        if request.user.id != target.id:
            return Response(
                {'detail': '只能修改自己的密码'},
                status=status.HTTP_403_FORBIDDEN,
            )

        old_password = request.data.get('old_password') or ''
        new_password = request.data.get('new_password') or ''

        if not old_password or not new_password:
            return Response(
                {'detail': '旧密码与新密码都不能为空'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not target.check_password(old_password):
            return Response(
                {'old_password': ['旧密码不正确']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 第 106 批：长度与"纯数字"两条规则改走统一策略
        # （原来是写在这里的 `MIN_LENGTH = 8` + `isdigit()`，只在改密这一条路径上生效，
        #  而注册与邮箱重置各有一套。现在三处一致，见 api/password_policy.py）。
        problem = validate_password(new_password, user=target)
        if problem:
            return Response(
                {'new_password': [f'新{problem}']},   # 与前端字段名对齐，前缀"新"便于阅读
                status=status.HTTP_400_BAD_REQUEST,
            )
        if new_password == old_password:
            return Response(
                {'new_password': ['新密码不能与旧密码相同']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target.set_password(new_password)
        target.save(update_fields=['password'])

        # 作废该用户的所有旧 token，并签发一个新的给当前调用方
        # 第 231 批：所有**设备**都要重登（安全状态变了），只给当前设备补一张
        revoke_all(target)
        new_token = DeviceToken.issue(target, device_of(request))

        logger.info('用户 %s 修改了密码并轮换了 token', target.username)
        return Response({
            'status': 'success',
            'message': '密码修改成功',
            'token': new_token.key,
        }, status=status.HTTP_200_OK)


class AccountDeleteView(APIView):
    """
    申请注销自己的账号（第 95 批新增，第 101 批改为**冷静期**）

        POST /api/users/me/delete/            body: {"password": "...", "confirm": "DELETE"}
        POST /api/users/me/cancel-deletion/   body: {"username": "...", "password": "..."}  ← 撤回

    在此之前**没有任何注销入口**：隐私政策里写着"如需注销账号请通过意见反馈提出申请"，
    也就是说全靠人工；而管理端用户管理页只做读，用户和管理员都删不掉账号。

    第 101 批的变化（用户提出的需求）：**申请后 15 天内可以取消**。
    改前是"点一下立刻清空个人信息、不可撤销"—— 误点、情绪化操作、账号被盗后被恶意
    注销都没有回头路，想恢复只能找管理员手工改库。

    现在的流程：
        申请（校验密码 + 回传 DELETE）→ 账号**立即无法登录**（用户的直接预期）
        → 15 天冷静期（个人信息完好、凭密码可取消）→ 到期由定时任务真正删除

    设计取舍（每一条都是有意的）：

    1. **必须验密码**：无论"申请"还是"取消"都验 —— 不能让一个被借用/被盗的会话替用户
       做这种决定（取消也验，否则别人能拿盗来的会话"帮他保留账号"，听着无害，
       但那同样是替用户做主）。
    2. **必须显式确认**（`confirm` 字段）而不是只靠前端弹窗：把"我真的要注销"写进请求体，
       避免前端误触发。
    3. **冷静期内不清个人信息**：清了就撤不回来（用户名一改，原名字可能被别人注册）。
       真正清空发生在到期后的 `soft_delete`。
    4. **冷静期内立即停用 + 失效凭证**：否则"注销了但另一台设备还能用"体验更糟。
    5. **不硬删**：帖子的 `author` 是 SET_NULL，硬删会连带把别人的评论一起带走
       （第 92 批刚修过同类问题）；内容属于社区。展示层显示"已注销用户"。
    """
    permission_classes = [permissions.IsAuthenticated]

    #: 前端必须原样回传这个字面量，表示"我确认要注销"
    CONFIRM_WORD = 'DELETE'

    def post(self, request):
        user = request.user
        password = request.data.get('password') or ''
        confirm = (request.data.get('confirm') or '').strip()

        if not password:
            return Response({'password': ['请输入当前密码以确认身份']},
                            status=status.HTTP_400_BAD_REQUEST)
        if not user.check_password(password):
            return Response({'password': ['密码不正确']},
                            status=status.HTTP_400_BAD_REQUEST)
        if confirm != self.CONFIRM_WORD:
            return Response(
                {'confirm': [f'请输入 {self.CONFIRM_WORD} 以确认注销']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        scheduled_for, _ = user.request_deletion(by=user, reason='self')

        # 会话也清掉（request_deletion 里已按 _auth_user_id 清过，这里再 logout 一次兜底）
        try:
            logout(request)
        except Exception:  # noqa: BLE001
            pass

        grace_days = user.deletion_grace_days()
        logger.info('用户 %s 申请注销（冷静期 %s 天，计划 %s 删除）', user.id, grace_days, scheduled_for)
        return Response({
            'status': 'success',
            'message': f'注销申请已提交，{grace_days} 天内可取消',
            # 前端要拿这两个值把"还能反悔到什么时候"写清楚，**不要在前端写死 15 天**
            'grace_days': grace_days,
            'scheduled_for': scheduled_for,
        }, status=status.HTTP_200_OK)


class AccountCancelDeletionView(APIView):
    """
    取消注销申请（第 101 批）

        POST /api/users/me/cancel-deletion/   body: {"username": "...", "password": "..."}

    两种调用场景：

    1. **冷静期内还能发请求时**（另一台设备还留着有效会话）—— 带 Token 也行，但本接口
       不依赖 Token（见下）。
    2. **已经登不上了**（这是主要场景：账号 `is_active=False`，登录接口会拒）——
       前端在登录失败界面引导用户到这里。此时用户没有 Token，所以本接口**允许匿名**，
       靠"用户名 + 密码"自己认身份。

    为什么必须允许匿名：不允许就没有任何自助恢复途径，等于"误点一次就得找管理员"，
    与改前的不可撤销没有本质区别。安全性靠**校验密码**保证；失败时的文案与登录一致
    （用户名或密码不正确），不额外泄露"这个账号是否在冷静期"—— 否则它会变成一个
    账号探测器（拿密码字典反推哪些用户名存在）。

    ⚠️ 第 106 批补上限流（原第 101 批遗漏）
    ------------------------------------------------------------------
    "靠密码保证安全"这句话只有在**不能无限次试**的前提下才成立。
    改前这个类是 `AllowAny` + `authentication_classes = []` + **没有任何限流** ——
    而第 91 批移除 DRF 自带 `/api/token-auth/` 的理由恰恰是：

        "改打这个端点就能无限撞库"（见 urls.py 里那段说明）

    这个接口属于**同一类**风险：给个用户名 + 密码就回答"对不对"，不限速、不计失败次数。
    现在加 `ScopedRateThrottle`（scope=`cancel_deletion`，10/min，与登录接口对齐）。

    为什么不复用登录那套"失败计数 + 锁定"：那套是按**账号**锁的，
    而这里攻击者可以对**同一账号**反复试 —— 按账号锁反而会让攻击者
    通过"故意试错"把真正的主人锁在门外（拒绝服务）。
    按 IP 限流更合适：它拦的是"一个来源大量尝试"，正是撞库的特征。
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    # 第 106 批：匿名密码校验端点必须限流（见类 docstring）
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'cancel_deletion'

    def post(self, request):
        from django.contrib.auth import get_user_model
        UserModel = get_user_model()

        username = (request.data.get('username') or '').strip()
        password = request.data.get('password') or ''

        if not username or not password:
            return Response({'detail': '请填写用户名与密码'},
                            status=status.HTTP_400_BAD_REQUEST)

        user = UserModel.objects.filter(username=username).first()
        if user is None or not user.check_password(password):
            return Response({'detail': '用户名或密码不正确'},
                            status=status.HTTP_400_BAD_REQUEST)

        if user.is_deleted:
            # 第 106 批注：这条分支**实际上到不了**，留着是纵深防御。
            # 原因：`soft_delete()` 会把密码置成随机 UUID 串，所以对已注销账号
            # `check_password()` 永远失败，上一行的 400 会先生效。
            # 万一将来改了 soft_delete 的密码策略（比如不再随机化），
            # 这条判断就能兜住"已注销账号被恢复"。
            return Response(
                {'detail': '该账号已完成注销，无法恢复。如需继续使用请重新注册。'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not user.has_pending_deletion:
            return Response(
                {'detail': '该账号当前没有待处理的注销申请'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.cancel_deletion()

        # 取消成功即视为身份有效：直接签发新 Token，用户不必再登一次
        # 第 231 批：先吊销所有设备，再给当前设备一张（冷静期内账号本来就登不上）
        revoke_all(user)
        token = DeviceToken.issue(user, device_of(request))

        logger.info('用户 %s 取消了注销申请', user.id)
        return Response({
            'status': 'success',
            'message': '已取消注销，账号已恢复，可以继续使用',
            'token': token.key,
            'username': user.username,
        }, status=status.HTTP_200_OK)


class UserStatsView(APIView):  # 定义用户统计信息视图类
    """
    获取用户统计信息API
    GET /api/users/{user_id}/stats/
    """
    permission_classes = [permissions.IsAuthenticated]  # 设置权限类为需要认证用户

    def get(self, request, user_id):  # 定义GET请求处理方法
        user = get_object_or_404(User, id=user_id)  # 获取用户对象或返回404

        # 获取用户发布的帖子数量
        # 第 91 批：改用 Post.active —— 软删除的帖子不该继续算进用户的发帖数
        post_count = Post.active.filter(author=user).count()  # 统计用户发布的帖子数量

        # 获取用户发布的评论数量
        comment_count = Comment.objects.filter(author=user).count()  # 统计用户发布的评论数量

        # 获取用户收到的点赞数量（用户发布的帖子收到的点赞）
        like_count = Like.objects.filter(post__author=user).count()  # 统计用户收到的点赞数量

        # 将统计信息添加到用户对象中
        user.post_count = post_count  # 动态添加帖子数量属性
        user.comment_count = comment_count  # 动态添加评论数量属性
        user.like_count = like_count  # 动态添加点赞数量属性

        # 使用 instance 参数序列化用户对象
        serializer = UserStatsSerializer(instance=user, context={'request': request})  # 使用统计信息序列化器
        return Response(serializer.data)  # 返回序列化后的数据


class UserListView(ListAPIView):
    """
    获取用户列表API
    GET /api/users/
    - 仅管理员可访问
    - 支持按用户名搜索
    """
    permission_classes = [IsUserAdmin]  # 第 124 批：USER_ADMIN 能力（原为 DRF IsAdminUser，只认 is_staff）
    serializer_class = UserProfileSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['username', 'email']
    # 第 76 批：改用 CustomPagination —— 专家咨询页的"授予专家"搜索框会带
    # ?page_size=20，而 DRF 自带的 PageNumberPagination 默认忽略 page_size，
    # 结果只回 5 条，搜不到想授予的那个人。
    pagination_class = CustomPagination
    
    def get_queryset(self):
        return User.objects.all().order_by('username')


# ============================================================================
# 管理端用户管理（第 76 批）
# ----------------------------------------------------------------------------
# 背景：管理后台只有"新闻 / 反馈 / 审核 / 看板"，**没有用户管理** ——
# 想知道"平台上有哪些用户、谁是专家、谁多久没登录过"只能进 Django 自带 /admin/，
# 而那个界面既不在产品导航里，也不受本项目的权限口径约束。
#
# 这里提供**读**接口（列表 + 详情）、专家授予/取消（复用 /api/consult/experts/），
# 以及第 95 批新增的**删除用户**（软删除，四道护栏见 AdminUserDetailView）。
#
# 仍然**刻意不做**的：禁用账号、改角色。
#   · 禁用 vs 删除：删除已经是"不可逆的封禁"，再给一个"可逆封禁"会让管理员在两件事
#     之间纠结（该禁还是该删），而这两者的差别对普通用户几乎没有意义；
#   · 改角色：ADMIN/EDITOR 直接决定后台权限，属于提权操作，与"授予专家"不同 ——
#     后者只影响答疑身份。真需要调整角色，请走 Django admin（那里有操作日志）。
# ============================================================================

#: 用户管理页允许的"角色"筛选值（与 CustomUser.ROLE_CHOICES 一致）
ADMIN_USER_ROLE_CHOICES = ('ADMIN', 'EDITOR', 'USER')
#: 用户管理页允许的"状态"筛选值
ADMIN_USER_STATUS_CHOICES = ('active', 'disabled', 'expert', 'staff')


def _admin_user_queryset():
    """
    用户管理的基查询集：一次带出专家档案 + 帖子/评论/识别记录数。

    为什么用 annotate：列表页一页 20 行，逐行 count() 就是 60 次查询。
    ⚠️ `detectionhistory`（查询名）与 `detectionhistory_set`（访问器名）不同名，
    这里用的是查询名，序列化器回退时才用访问器名。

    第 95 批：**默认排除已注销的账号**（`is_deleted=True`）——
    否则"删掉的用户"会继续留在列表里，管理员会以为没删掉。
    第 101 批：**也排除冷静期中的账号**（`deletion_scheduled_for` 有值）——
    它们已停用、正在等待删除，留在"用户总数/活跃用户"里会让统计失真。
    需要审计时用 `?include_deleted=true` 或 `?pending_deletion=true`。
    """
    return _admin_user_base().filter(is_deleted=False, deletion_scheduled_for__isnull=True)


def _admin_user_base():
    """不带"已注销"过滤的基查询集（`?include_deleted=true` 用它）"""
    return (
        User.objects
        .select_related('expert_profile')
        .annotate(
            post_count=Count('forum_posts', distinct=True),
            comment_count=Count('forum_comments', distinct=True),
            detection_count=Count('detectionhistory', distinct=True),
        )
    )


#: 用户管理页允许的排序字段（第 100 批）
#: 真实字段名 ← 前端用的键。**白名单**而不是直接把参数拼进 order_by：
#: 否则 `?ordering=-is_superuser` 之类会泄露内部字段，更糟的是任意字段排序会
#: 让攻击者用"二分试探"推断出隐藏数据（经典的盲注式信息泄露）。
ADMIN_USER_ORDERING = {
    'username': 'username',
    'date_joined': 'date_joined',
    'last_login': 'last_login',
    'points': 'points',
    'posts': 'post_count',
    'comments': 'comment_count',
    'detections': 'detection_count',
}
ADMIN_USER_ORDERING_DEFAULT = '-date_joined'


def _apply_ordering(queryset, params, allowed, default):
    """
    按 `?ordering=字段` / `?ordering=-字段` 排序（第 100 批）

    为什么所有管理端都用同一个函数：白名单、`-` 前缀、非法值回退这三件事
    每个页面都要处理一遍，写三遍就会有一处漏掉校验。这里统一。
    """
    raw = (params.get('ordering') or '').strip()
    # `-id` 作为**稳定排序**兜底：否则同分/同时间的行在翻页时可能重复或漏掉
    # （SQL 不保证同值行的相对顺序，"第 2 页又出现第 1 页的内容"就是这么来的）
    if not raw:
        return queryset.order_by(default, '-id')

    descending = raw.startswith('-')
    field = allowed.get(raw.lstrip('-'))
    if not field:
        return queryset.order_by(default, '-id')

    return queryset.order_by(f'-{field}' if descending else field, '-id')


def _filter_admin_users(queryset, params):
    """按 role / status 过滤（非法值忽略，不报错 —— 筛选条件不该让页面 500）"""
    # 第 95 批：`?include_deleted=true` → 连已注销账号一起列出来（审计用）
    include_deleted = (params.get('include_deleted') or '').strip().lower()
    if include_deleted in ('true', '1', 'yes'):
        queryset = _admin_user_base()
    else:
        # 第 101 批：`?pending_deletion=true` → 只看**冷静期中**的账号
        #（运营可能想核对"最近有谁申请了注销、什么时候到期"）
        pending = (params.get('pending_deletion') or '').strip().lower()
        if pending in ('true', '1', 'yes'):
            queryset = _admin_user_base().filter(
                is_deleted=False, deletion_scheduled_for__isnull=False,
            )

    role = (params.get('role') or '').strip().upper()
    if role in ADMIN_USER_ROLE_CHOICES:
        queryset = queryset.filter(role=role)

    status_param = (params.get('status') or '').strip().lower()
    if status_param in ADMIN_USER_STATUS_CHOICES:
        if status_param == 'active':
            queryset = queryset.filter(is_active=True)
        elif status_param == 'disabled':
            queryset = queryset.filter(is_active=False)
        elif status_param == 'expert':
            queryset = queryset.filter(expert_profile__is_active=True)
        elif status_param == 'staff':
            queryset = queryset.filter(is_staff=True)

    return queryset


class AdminUserListView(ListAPIView):
    """
    管理端用户列表（第 76 批）

    GET /api/admin/users/?search=&role=&status=&page=&page_size=
      · 仅管理员（IsAdminUser：is_staff=True）
      · search 走 SearchFilter，匹配 用户名 / 邮箱 / 姓名
      · role   ∈ ADMIN | EDITOR | USER
      · status ∈ active | disabled | expert | staff
    """

    permission_classes = [IsUserAdmin]  # 第 124 批：USER_ADMIN 能力（原为 DRF IsAdminUser，只认 is_staff）
    serializer_class = AdminUserSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['username', 'email', 'first_name', 'last_name']
    # 用全站统一的 CustomPagination（它才认 page_size 查询参数）；
    # DRF 自带的 PageNumberPagination 默认**忽略** page_size，前端传了也没用。
    pagination_class = CustomPagination

    def get_queryset(self):
        queryset = _filter_admin_users(_admin_user_queryset(), self.request.query_params)
        return _apply_ordering(
            queryset, self.request.query_params,
            ADMIN_USER_ORDERING, ADMIN_USER_ORDERING_DEFAULT,
        )

    def post(self, request, *args, **kwargs):
        """
        批量删除用户（第 100 批，仅管理员）

            POST /api/admin/users/bulk-delete/   body: {"ids": [1,2,3]}

        **为什么不用 DRF 的 `@action`**：本视图是 `ListAPIView`（不是 ViewSet），
        `@action` 只对 ViewSet 生效，写在上面会直接 `NameError`（实测）。
        两个选择：改成 `ViewSet.as_view({'get':'list','post':'bulk_delete'})`
        （要动 urls.py，还可能影响其它调用），或者在这里按路径分流。
        这里选后者：改动面最小，且路由仍是那一条 `admin/users/`。

        **逐条走与单条删除完全相同的护栏**（`_check_delete_allowed`）——
        批量入口最容易变成"绕过单条校验的后门"，所以刻意不写第二套判断。

        响应逐条给结果：成功几条、跳过几条、各自原因。
        前端把"跳过的"显示出来，避免管理员以为全都删了。
        """
        if 'bulk-delete' not in (request.path_info or ''):
            # 这里是"列表"接口，不接普通 POST —— 返回 405 比 404 更准确
            return Response({'detail': '该接口只支持 GET；批量删除请用 /bulk-delete/'},
                            status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return self._bulk_delete(request)

    def _bulk_delete(self, request):
        raw_ids = request.data.get('ids') or []
        if not isinstance(raw_ids, (list, tuple)):
            return Response({'ids': ['ids 必须是数组']}, status=status.HTTP_400_BAD_REQUEST)

        ids = []
        for value in raw_ids:
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
        seen = set()
        ids = [i for i in ids if not (i in seen or seen.add(i))]
        if not ids:
            return Response({'ids': ['没有选中任何用户']}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > 100:
            return Response({'ids': ['一次最多处理 100 个用户']},
                            status=status.HTTP_400_BAD_REQUEST)

        targets = {u.id: u for u in User.objects.filter(id__in=ids)}
        results = []
        ok_count = 0
        avatars = []

        for user_id in ids:
            target = targets.get(user_id)
            if target is None:
                results.append({'id': user_id, 'ok': False, 'detail': '用户不存在'})
                continue
            blocked = _check_delete_allowed(request.user, target)
            if blocked:
                results.append({'id': user_id, 'ok': False, 'detail': blocked})
                continue

            avatar = target.soft_delete(by=request.user, reason='admin-bulk')
            if avatar:
                avatars.append(avatar)
            ok_count += 1
            results.append({'id': user_id, 'ok': True, 'detail': '已注销'})

        for avatar in avatars:
            try:
                from django.core.files.storage import default_storage
                default_storage.delete(avatar)
            except Exception as exc:  # noqa: BLE001
                logger.warning('批量删除时清理头像失败: %s', exc)

        log_admin_action(
            request.user, 'user.bulk_delete', target_type='user',
            target_id=','.join(str(i) for i in ids[:20]),
            detail=f'批量软删除账号 {ok_count}/{len(ids)} 条',
            request=request,
        )
        logger.info('批量删除用户 by=%s 成功=%s/%s', request.user.id, ok_count, len(ids))
        return Response({
            'requested': len(ids),
            'succeeded': ok_count,
            'failed': len(ids) - ok_count,
            'results': results,
        })


class AdminUserDetailView(APIView):
    """
    单个用户的完整管理视图（第 76 批）
        GET /api/admin/users/{user_id}/   —— 仅管理员

    第 95 批新增删除：
        DELETE /api/admin/users/{user_id}/  —— 仅管理员（权限见下）

    删除同样走**软删除**（见 CustomUser.soft_delete），并且有四道护栏 ——
    每一条都是"不写就会出事"的类型：

      1. **不能删自己**：管理员一怒之下把自己删了，就再没人能进管理端；
      2. **不能删权限不低于自己的人**：只挂 staff 的管理员删不掉其他管理员/超级管理员
         （否则"谁能被删"就取决于谁先动手）；
      3. **超级管理员不能删**：即使操作者也是超级管理员 —— 系统必须永远保留至少一个
         能改配置的最高权限账号，这是运维底线，不该由一次点击破坏；
      4. **需要显式确认**（`confirm` = 对方用户名）：避免点错行。
    """

    permission_classes = [IsUserAdmin]  # 第 124 批：USER_ADMIN 能力（原为 DRF IsAdminUser，只认 is_staff）

    def get(self, request, user_id):
        user = get_object_or_404(_admin_user_queryset(), pk=user_id)
        return Response(AdminUserSerializer(user, context={'request': request}).data)

    def delete(self, request, user_id):
        """删除（软删除）一个用户 —— 三道护栏见 `_check_delete_allowed`（批量删除共用）"""
        target = get_object_or_404(User, pk=user_id)
        actor = request.user

        blocked = _check_delete_allowed(actor, target)
        if blocked:
            # 状态码沿用历史行为：删自己/删超管是"请求本身不合理"（400），
            # 越权删管理员是"权限不足"（403）
            code = (status.HTTP_403_FORBIDDEN if '超级管理员可以删除其他管理员' in blocked
                    else status.HTTP_400_BAD_REQUEST)
            return Response({'detail': blocked}, status=code)
        # 护栏 4：显式确认（回传对方用户名）
        confirm = (request.data.get('confirm') or '').strip()
        if confirm != target.username:
            return Response(
                {'confirm': [f'请输入该用户的用户名（{target.username}）以确认删除']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deleted_name = target.username   # 第 146 批：日志快照用（删除会改名）
        old_avatar = target.soft_delete(by=actor, reason='admin')
        if old_avatar:
            try:
                from django.core.files.storage import default_storage
                default_storage.delete(old_avatar)
            except Exception as exc:  # noqa: BLE001
                logger.warning('删除被注销用户的头像文件失败: %s', exc)

        # ⚠️ 快照要显式传原用户名：`soft_delete()` 已经把 username 改成 `deleted_<id>`，
        #    不传的话日志会变成"管理员删除了 deleted_953" —— 读的人不知道删的是谁。
        log_admin_action(actor, 'user.delete', target=target, target_repr=deleted_name,
                         detail='软删除（用户名已让出、个人信息清空）', request=request)
        logger.info('管理员 %s 删除了用户 %s（软删除）', actor.username, target.id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserStatusView(APIView):
    """
    停用 / 恢复某个账号：
    `POST /api/admin/users/<user_id>/status/`
        body: `{"is_active": false}`   # false = 停用，true = 恢复

    第 137 批。**为什么要有这个接口**：用户管理页早就有「已禁用」这个筛选和状态标签，
    却**没有任何入口能把账号停用** —— 状态只可能来自
      ① 用户自助注销（冷静期内）；
      ② 管理员删除用户（软删除，`is_active=False` + `is_deleted=True`）；
      ③ Django admin 里手动取消 active。
    而 ①② 都被默认列表查询排除（见 `_admin_user_queryset`，只留 `?include_deleted` 审计用），
    所以「已禁用」筛选在控制台里**永远筛不出东西**；更别扭的是「重置密码」的拒绝语写着
    "请先恢复账号再重置密码"，界面上却根本没有"恢复"这个入口。
    这个接口把这条链路补齐：停用 → 列表里就能筛到 → 需要时一键恢复。

    护栏见 `_check_status_allowed`：不能停用自己、非超管不能停用权限不低于自己的账号。
    权限与删除一致（`IsUserAdmin`）—— 见那个函数里"为什么不比删除更严"的说明。

    两个刻意行为（都写在测试里，防止以后被"顺手改掉"）：

      · **停用时顺带作废对方的 token**。DRF 的 `TokenAuthentication` 本来就会拒
        `is_active=False` 的用户（已实测：同一个 token 停用后立刻 401），所以作废 token
        不是为了"挡住现在"，而是为了**恢复之后** —— 否则停用期间对方设备上那个 token
        一直挂着，一恢复就"自己登回来了"。代价是恢复后需要重新登录，这是正确的代价。
      · **恢复不需要对方改密码**（密码全程没被动过）—— 这一点与 `soft_delete` 不同，
        后者会把密码随机化，因此"删除"不可逆、而"停用"可逆。
    """

    permission_classes = [IsUserAdmin]

    def post(self, request, user_id):
        actor = request.user
        # ⚠️ 用 `_admin_user_queryset()` 而不是裸 User：已删除与注销冷静期的账号在这里
        #    直接 404（那两类状态由删除/注销流程管理，不该在用户管理里改）。
        target = get_object_or_404(_admin_user_queryset(), pk=user_id)

        raw = request.data.get('is_active')
        if not isinstance(raw, bool):
            # 不收 "false" 这种字符串：前端传错时宁可 400，也别猜错了把账号停掉
            return Response(
                {'is_active': ['请传布尔值 true（恢复）或 false（停用）']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        blocked = _check_status_allowed(actor, target)
        if blocked:
            # 状态码口径与删除一致：停用自己是"请求本身不合理"（400），
            # 越权动管理员是"权限不足"（403）
            code = (status.HTTP_403_FORBIDDEN if '超级管理员' in blocked
                    else status.HTTP_400_BAD_REQUEST)
            return Response({'detail': blocked}, status=code)

        if target.is_active == raw:
            # 幂等：重复点击不报错，也不写第二条日志（页面刷新后状态可能已经变了）
            return Response({
                'status': 'success',
                'changed': False,
                'user': AdminUserSerializer(target, context={'request': request}).data,
                'message': '该账号已经是这个状态',
            })

        target.is_active = raw
        target.save(update_fields=['is_active'])

        if not raw:
            # 第 231 批：停用要踢掉**所有设备**（含手机那张 DeviceToken）
            revoke_all(target)

        logger.info(
            '管理员 %s %s了用户 %s(%s)%s',
            actor.username, '停用' if not raw else '恢复',
            target.username, target.id,
            '，并作废其登录凭证' if not raw else '，对方可重新登录',
        )
        log_admin_action(
            actor, 'user.suspend' if not raw else 'user.restore', target=target,
            detail=('停用并作废其登录凭证' if not raw else '恢复账号（密码未改动）'),
            request=request,
        )

        return Response({
            'status': 'success',
            'changed': True,
            'user': AdminUserSerializer(target, context={'request': request}).data,
            'message': ('账号已停用：对方会立刻掉线，且无法登录'
                        if not raw else '账号已恢复：对方可以重新登录（需要重新输密码）'),
        })


# ---------------------------------------------------------------------------
# 改角色（第 127 批）
# ---------------------------------------------------------------------------
#: 可以在管理后台里互相切换的角色（**不含 ADMIN**）
#: 升成 ADMIN 仍然只能走 Django admin（那里有操作日志）—— 见 views_user.py 顶部的说明：
#: "改角色：ADMIN/EDITOR 直接决定后台权限，属于提权操作"。
ASSIGNABLE_ROLES = ('EDITOR', 'USER')

#: 角色 → 中文名（错误提示与日志用；前端有自己的 i18n 文案）
ROLE_LABELS = {'ADMIN': '系统管理员', 'EDITOR': '信息编辑员', 'USER': '普通用户'}


def _normalize_modules(raw):
    """
    把前端传来的模块数组整理成合法列表

    返回 `(modules, error)`：`error` 非空表示有非法值（`modules` 此时无意义）。
    单独抽出来是因为"改角色"与"开通编辑员"两个接口要用**同一套校验** ——
    抄两份必然有一天两边不一致（第 120 批把"拼链接/发邮件"抽出来也是这个理由）。
    """
    if not isinstance(raw, (list, tuple)):
        return None, 'modules 必须是数组'
    seen = []
    for item in raw:
        module = str(item).strip().lower()
        if module not in CONTENT_MODULES:
            return None, f'未知模块：{item}（可选：{" / ".join(CONTENT_MODULES)}）'
        if module not in seen:
            seen.append(module)
    # 固定顺序（前端展示与日志都好读）
    return [m for m in CONTENT_MODULES if m in seen], None


def _grant_modules(target, modules, actor):
    """
    把 target 的模块授权设为 `modules`（增删都做，不留"影子授权"）

    为什么用 bulk_create + exclude().delete() 而不是逐条 get_or_create：
    一次请求最多四条记录，批量写更省事，而且"先删多余、再补缺失"的顺序
    保证结果**恰好等于** `modules`。
    """
    EditorModuleGrant.objects.filter(user=target).exclude(module__in=modules).delete()
    existing = set(
        EditorModuleGrant.objects.filter(user=target).values_list('module', flat=True)
    )
    EditorModuleGrant.objects.bulk_create([
        EditorModuleGrant(user=target, module=module, granted_by=actor)
        for module in modules if module not in existing
    ])


class AdminUserCreateEditorView(APIView):
    """
    开通一个**信息编辑员**账号（第 131 批）：
    `POST /api/admin/users/create-editor/`
        body: `{"username": "farm_editor", "email": "a@b.com", "modules": ["news"]}`

    解决什么：第 127/128 批能在后台"把某个已有账号改成编辑员"，但**新建账号**
    仍然只能去 Django admin —— 于是"想让同事来维护新闻"要跨两个界面，
    而且新建出来的账号还得自己想办法设密码。

    这里一次做完三件事：
      1. 建账号，角色直接是 EDITOR，模块按勾选写入 `EditorModuleGrant`；
      2. **不设密码**：用 `set_unusable_password()` —— 没有任何明文密码经手
         （与第 120 批"管理员看不到对方新密码"是同一条原则）；
      3. 返回一条**一次性设置密码链接**（1 小时有效、改密即失效），
         超管线下发给本人，本人在 `/reset-password` 自己设密码。
         账号若填了邮箱，也顺手发一封（`mailed` 如实返回发没发出去）。

    护栏（与改角色同一套，因为"造一个编辑员"与"把别人变成编辑员"是同一类提权）：
      · **只有超级管理员**；
      · 用户名必须符合规则且**未被占用**（大小写不敏感）；
      · 至少给一个内容模块（没有模块的编辑员进后台什么也做不了）；
      · 邮箱可选，但填了就要合法且未被占用（唯一性在两处校验，避免"注册时说能用、
        开通时冲突"这类不一致）。
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        actor = request.user
        if not actor.is_superuser:
            return Response(
                {'detail': '只有超级管理员可以开通编辑员账号'},
                status=status.HTTP_403_FORBIDDEN,
            )

        username = (request.data.get('username') or '').strip()
        email = (request.data.get('email') or '').strip()

        # 用户名：复用注册那套规则（服务端才是权威校验）
        ok, message = validate_username_format(username)
        if not ok:
            return Response({'username': [message]}, status=status.HTTP_400_BAD_REQUEST)

        if email and User.objects.filter(email__iexact=email).exists():
            return Response({'email': ['该邮箱已被其他账号使用']},
                            status=status.HTTP_400_BAD_REQUEST)

        modules, error = _normalize_modules(request.data.get('modules'))
        if error:
            return Response({'modules': [error]}, status=status.HTTP_400_BAD_REQUEST)
        if not modules:
            return Response(
                {'modules': ['至少要给编辑员一个模块（否则他进后台什么也做不了）']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User(username=username, email=email, role='EDITOR')
        user.set_unusable_password()   # 关键：没有任何明文密码经过接口
        try:
            user.save()
        except IntegrityError:
            # 并发下的兜底（上面查过一次，但两个请求同时提交仍可能撞唯一约束）
            return Response({'username': ['该用户名已被占用']},
                            status=status.HTTP_400_BAD_REQUEST)

        _grant_modules(user, modules, actor)

        reset_url = build_password_reset_url(user)
        mailed = bool(email) and send_password_reset_mail(user)

        log_admin_action(
            actor, 'user.create_editor', target=user,
            detail=f'角色=EDITOR，模块={modules}，邮箱={email or "无"}（无可用密码，已签发设置密码链接）',
            request=request,
        )
        logger.info(
            '超级管理员 %s 开通了编辑员账号 %s(%s)：模块=%s，邮箱=%s',
            actor.username, user.username, user.id,
            '、'.join(MODULE_LABELS.get(m, m) for m in modules),
            email or '无',
        )

        return Response({
            'status': 'success',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
                'content_modules': modules,
            },
            'url': reset_url,
            'expires_in_minutes': 60,
            'has_email': bool(email),
            'mailed': mailed,
            'message': '账号已开通，请把设置密码链接发给本人（1 小时内有效、只能用一次）',
        }, status=status.HTTP_201_CREATED)


class AdminUserRoleView(APIView):
    """
    调整某个用户的角色与内容模块：
    `POST /api/admin/users/<user_id>/role/`
        body: `{"role": "EDITOR", "modules": ["news", "feedback"]}`

    第 127 批（产品决策 #4）引入"改角色"；**第 128 批**把内容能力拆成四个模块，
    于是这里同时承担"给编辑员勾选模块"：

        · `role='EDITOR'` + `modules=[...]` → 该账号只在这几个模块里有权限；
        · `role='USER'` → 顺手清掉他的模块授权（降级要干净，否则下次升回来
          "凭记忆恢复"容易多给或少给）。

    以前后台**故意不提供**改角色（第 95 批："改角色属于提权操作，请走 Django admin"）。
    引入编辑员之后这成了日常操作，于是按下面四条护栏在系统内开一个**窄口子**：

      1. **只有超级管理员**能改（`is_superuser`）—— 不是"有 USER_ADMIN 能力就行"：
         否则一个 staff 管理员就能造出编辑员，而编辑员能改全站内容；
      2. **只能改 EDITOR ↔ USER**：`ADMIN` 既不能作为目标、也不能作为结果
         （想把谁升成管理员，请走 Django admin）；
      3. **不能改自己**：避免"把自己降成 USER 之后再没人能改回来"这类锁死；
      4. 目标必须是**普通账号**（不能动 `is_staff` / `is_superuser` 的人）。

    每次变更都写一条 info 日志（谁、把谁、从什么改成什么 + 模块清单）——
    这是本接口的"操作日志"。
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, user_id):
        actor = request.user
        target = get_object_or_404(_admin_user_queryset(), pk=user_id)

        # 护栏 1：只有超级管理员
        if not actor.is_superuser:
            return Response(
                {'detail': '只有超级管理员可以调整角色'},
                status=status.HTTP_403_FORBIDDEN,
            )

        new_role = (request.data.get('role') or '').strip().upper()
        if new_role not in ASSIGNABLE_ROLES:
            return Response(
                {'role': [f'只能改成：{" / ".join(ROLE_LABELS[r] for r in ASSIGNABLE_ROLES)}'
                          f'（升为管理员请走 Django admin）']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 模块清单（第 128 批）：只有编辑员需要；给普通用户传了也忽略（降级要干净）
        raw_modules = request.data.get('modules')
        modules = []
        if new_role == 'EDITOR':
            if raw_modules is None:
                # 没传 modules：保留他**已有**的授权（改角色不该顺手清空模块）
                modules = content_modules_of(target)
            else:
                # 与"开通编辑员"共用同一套模块校验（见 _normalize_modules 的说明）
                modules, error = _normalize_modules(raw_modules)
                if error:
                    return Response({'modules': [error]},
                                    status=status.HTTP_400_BAD_REQUEST)

            if not modules:
                # 一个模块都不勾的编辑员进不了后台（侧栏空），几乎肯定是点漏了
                return Response(
                    {'modules': ['至少要给编辑员一个模块（否则他进后台什么也做不了）']},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # 护栏 3：不能改自己
        if target.id == actor.id:
            return Response(
                {'detail': '不能修改自己的角色'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 护栏 4 + 2：目标本身不能是高权限账号；ADMIN 也不能被改
        if _is_elevated_user(target) or target.role == 'ADMIN':
            return Response(
                {'detail': f'{ROLE_LABELS["ADMIN"]}账号的角色不能在这里调整（请走 Django admin）'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if target.role not in ASSIGNABLE_ROLES:
            return Response(
                {'detail': '该账号的角色不在可调整范围内'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_role = target.role
        old_modules = content_modules_of(target)
        role_changed = old_role != new_role
        modules_changed = new_role == 'EDITOR' and sorted(modules) != sorted(old_modules)

        if not role_changed and not modules_changed:
            # 幂等：什么都没变就直接回当前状态（不写日志，免得日志里全是重复项）
            return Response({
                'id': target.id, 'role': target.role,
                'content_modules': old_modules, 'changed': False,
            })

        if role_changed:
            target.role = new_role
            target.save(update_fields=['role'])

        # 模块授权：编辑员按勾选写表；降级成普通用户则清空（不留"影子权限"）
        if new_role == 'EDITOR':
            _grant_modules(target, modules, actor)
        else:
            EditorModuleGrant.objects.filter(user=target).delete()

        # 第 146 批：改角色是**提权类**操作，必须留痕（谁、把谁、从什么改成什么、模块变化）
        log_admin_action(
            actor, 'user.role_change', target=target,
            detail=(f'角色 {ROLE_LABELS.get(old_role, old_role)} → '
                    f'{ROLE_LABELS.get(new_role, new_role)}；'
                    f'模块 {old_modules or "无"} → {content_modules_of(target) or "无"}'),
            request=request,
        )
        logger.info(
            '超级管理员 %s 调整了用户 %s(%s)：角色 %s → %s；模块 %s → %s',
            actor.username, target.username, target.id,
            ROLE_LABELS.get(old_role, old_role), ROLE_LABELS.get(new_role, new_role),
            old_modules or '无', content_modules_of(target) or '无',
        )

        # 改了角色/模块之后，对方**当前浏览器里的能力清单还是旧的**（能力随登录响应下发，
        # 存在本地存储里）。这里给一条站内通知，提醒他重新登录才会生效 ——
        # 试图热更新别人的会话是做不到的（那是另一个浏览器）。
        try:
            from .views_notify import notify
            if new_role == 'EDITOR':
                module_text = '、'.join(MODULE_LABELS[m] for m in content_modules_of(target))
                message = f'你现在是「信息编辑员」，可以管理：{module_text}。重新登录后生效。'
                message_en = (f'You are now an editor for: {", ".join(content_modules_of(target))}. '
                              f'Sign in again to apply.')
            else:
                message = '你的账号已改回普通用户。重新登录后生效。'
                message_en = 'Your account is a regular user again. Sign in again to apply.'
            notify(
                target, type='system',
                title='你的账号权限已更新',
                title_en='Your permissions have been updated',
                message=message, message_en=message_en,
            )
        except Exception:  # noqa: BLE001 —— 通知失败不该让改角色失败
            logger.exception('角色变更通知发送失败 user=%s', target.id)

        return Response({
            'id': target.id,
            'username': target.username,
            'role': target.role,
            'content_modules': content_modules_of(target),
            'changed': True,
            'detail': '权限已更新，对方重新登录后生效',
        })


def _is_elevated_user(user):
    """
    是否属于"高权限"（管理员 / 超级管理员 / role=ADMIN）

    第 124 批：改为复用 `capabilities.is_full_admin()` —— 它是**提权护栏**用的判定
    （例如"只有超级管理员能给管理员账号签发重置链接"），语义是"这个人本身权限就很高"，
    因此必须用"全权管理员"而不是能力。

    ⚠️ 注意：信息编辑员（EDITOR）**不算**高权限 —— 否则一个编辑员就能去改
    另一个编辑员的密码，而这条护栏的本意是"别让低权限的人动高权限账号"。
    """
    return is_full_admin(user)


class AdminUserResetLinkView(APIView):
    """
    给某个用户生成**一次性密码重置链接**（第 120 批）

        POST /api/admin/users/{user_id}/reset-link/   —— 仅管理员

    ---------------------------------------------------------------------------
    为什么需要它（这是本批要解决的真正问题）
    ---------------------------------------------------------------------------
    自助找回密码（`/api/password-reset/`）只在"账号**绑了邮箱**"时才真的发信；
    没绑邮箱时后端按防枚举策略**静默什么都不做**，而页面照样显示"重置邮件已发送"。
    管理端账号大多是超管在后台开通的、常常没绑邮箱 —— 于是"管理员忘了密码"
    这条路是断的，而且断得**没有声音**。

    这里给一条**在系统内**就能走通的路：管理员生成一条一次性链接，通过
    微信/电话等线下渠道发给本人；本人在 `/reset-password` 自己设新密码
    （复用第 35 批就有的 `PasswordResetConfirmView`，不新建确认流程）。

    安全性（每条都对应一种滥用方式）：
      · 仅管理员（`IsAdminUser`）；
      · 链接复用 Django `default_token_generator`：**1 小时有效、改过密码即失效**、
        与用户当前的密码哈希绑定（换密码后旧链接自动作废）；
      · 接口**不返回也不能设置明文密码** —— 管理员全程看不到对方的密码，
        这与"直接设一个临时密码"有本质区别（后者等于把口令告诉了别人）；
      · **不能给权限不低于自己的人签发**（护栏与删除一致，见 `_check_reset_allowed`）：
        否则一个只有 staff 的管理员就能生成超管的重置链接、把超管顶掉 ——
        这是提权，不是"找回密码"；
      · 已停用/已注销的账号不签发（先恢复账号再说）。
    """

    permission_classes = [IsUserAdmin]  # 第 124 批：USER_ADMIN 能力（原为 DRF IsAdminUser，只认 is_staff）

    def post(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        actor = request.user

        blocked = _check_reset_allowed(actor, target)
        if blocked:
            code = (status.HTTP_403_FORBIDDEN if '权限不低于' in blocked
                    else status.HTTP_400_BAD_REQUEST)
            return Response({'detail': blocked}, status=code)

        url = build_password_reset_url(target)

        # 顺手给绑了邮箱的账号也发一封（能发就发；发不出去不影响返回的链接）
        mailed = bool(target.email) and send_password_reset_mail(target)

        # 第 146 批：落日志 —— ⚠️ detail 里**绝不能放整条链接**：
        # 链接带着一次性 token，写进日志等于把"改别人密码的凭证"抄进数据库。
        log_admin_action(
            actor, 'user.reset_link', target=target,
            detail='签发一次性密码重置链接（1 小时有效、改密即失效）',
            request=request,
        )
        logger.info(
            '管理员 %s 为用户 %s 生成了密码重置链接（mailed=%s）',
            actor.username, target.id, mailed,
        )
        return Response({
            'status': 'success',
            'username': target.username,
            'url': url,
            'expires_in_minutes': 60,
            'has_email': bool(target.email),
            'mailed': mailed,
            'message': '链接 1 小时内有效，且只能用一次（对方设置新密码后即失效）。',
        })


def _check_reset_allowed(actor, target):
    """
    签发密码重置链接的护栏（第 120 批）

    返回空串表示允许，否则返回拒绝原因。

    ⚠️ 为什么必须有"权限不低于自己"这条：重置链接等于**账号控制权**。
       没有这条护栏的话，一个只有 `is_staff` 的管理员可以给超级管理员生成链接、
       打开链接把超管密码改掉 —— 这就是一条从"普通管理员"到"超级管理员"的提权路径。
       删除用户的护栏（`_check_delete_allowed`）早就有这一条，两边口径保持一致。
    """
    if target.id == actor.id:
        return ''   # 自己的账号：随便（本来就登着）
    if not target.is_active:
        return '该账号已停用或已注销，请先恢复账号再重置密码'
    if _is_elevated_user(target) and not actor.is_superuser:
        return '不能为权限不低于你的账号签发重置链接（只有超级管理员可以）'
    return ''


def _check_status_allowed(actor, target):
    """
    停用 / 恢复账号的两道护栏（第 137 批）

    与 `_check_delete_allowed` **同一套口径**，只是动作可逆所以少一条
    （删除才需要"不能删超级管理员"那条底线，停用可以再恢复）：

      1. **不能停用自己** —— 一按就把自己锁在管理端外面，而"谁能救你"取决于
         是否还有另一个管理员在线，这种锁死不该由一次点击造成；
      2. **非超管不能停用权限不低于自己的账号** —— 否则"谁能被停用"就取决于谁先动手。

    ⚠️ 为什么不比删除更严（删除不可逆都允许普通管理员做）：
    如果停用只允许超管，就会出现"**能删却不能停用**"的怪事 —— 口径不一致本身就是 bug。

    已删除（`is_deleted=True`）与注销冷静期的账号走不到这里：
    `_admin_user_queryset()` 已经把这两类排除了（查不到 → 404）。
    它们的状态由删除/注销流程管理，不该在用户管理里改。

    返回空串表示允许，否则返回拒绝原因。
    """
    if target.id == actor.id:
        return '不能停用自己的账号。'
    if _is_elevated_user(target) and not actor.is_superuser:
        return '只有超级管理员可以停用其他管理员账号。'
    return ''


def _check_delete_allowed(actor, target):
    """
    删除用户的三道护栏（第 95 批单条删除 + 第 100 批批量删除**共用**）

    返回一个字符串说明为什么不能删；可以删则返回空串。

    为什么抽成函数而不是各写一遍：批量入口最容易变成"绕过单条校验的后门"。
    这类漏洞的共同形态就是"单条接口校验很全，批量接口为了图快自己写了一套更松的判断"。
    共用一个函数，就不会出现两套规则。

    三道护栏（每一条都是"不写就会出事"的类型）：
      1. **不能删自己** —— 管理员一怒之下把自己删了，就再没人能进管理端；
      2. **不能删超级管理员** —— 系统必须永远保留至少一个能改配置的最高权限账号；
      3. **非超管不能删其他管理员** —— 否则"谁能被删"就取决于谁先动手。
    """
    if target.id == actor.id:
        return '不能删除自己的账号。如需注销，请到「个人资料 → 注销账号」。'
    if target.is_superuser:
        return '系统必须保留至少一个超级管理员，该账号不可删除。'
    if _is_elevated_user(target) and not actor.is_superuser:
        return '只有超级管理员可以删除其他管理员账号。'
    return ''


class UserCommentsView(APIView):
    """
    某个用户发表的评论（第 25 批新增）

    GET /api/users/{user_id}/comments/

    需求：用户资料页要能列出"该用户的评论"，并且每条都能看出**是在哪里发的**
    （所属帖子的标题与版块）—— 由 `UserCommentSerializer` 提供这几个字段。
    仅返回未删除的评论；按时间倒序。
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get(self, request, user_id):
        user = get_object_or_404(User, id=user_id)

        queryset = (
            Comment.objects
            .filter(author=user, is_deleted=False)
            .select_related('author', 'post', 'post__board', 'reply_to_user')
            .order_by('-created_at')
        )

        paginator = PageNumberPagination()
        paginator.page_size = 10
        paginator.page_size_query_param = 'page_size'
        paginator.max_page_size = 100
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = UserCommentSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)

        serializer = UserCommentSerializer(queryset, many=True, context={'request': request})
        return Response({'count': queryset.count(), 'results': serializer.data})


class UserPostsView(APIView):  # 定义用户帖子视图类
    """
    获取用户自己的帖子API
    GET /api/users/me/posts/
    - 用户只能查看自己发布的帖子
    """
    permission_classes = [permissions.IsAuthenticated]  # 需要登录才能访问

    def get(self, request):
        """
        获取当前登录用户的所有帖子
        """
        try:
            # 确保只返回当前登录用户自己的帖子
            # 第 91 批：Post.active —— 自己删掉的帖子不该继续出现在"我的帖子"里
            posts = Post.active.filter(author=request.user).select_related('author', 'board')
            
            # 分页
            page = self.paginate_queryset(posts)
            if page is not None:
                serializer = PostListSerializer(page, many=True, context={'request': request})
                return self.get_paginated_response(serializer.data)
                
            serializer = PostListSerializer(posts, many=True, context={'request': request})
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"获取用户帖子失败: {str(e)}")
            return Response(
                {"detail": "获取帖子列表失败"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @property
    def paginator(self):
        if not hasattr(self, '_paginator'):
            self._paginator = PageNumberPagination()
            self._paginator.page_size = 10  # 每页显示10条
        return self._paginator

    def paginate_queryset(self, queryset):
        return self.paginator.paginate_queryset(queryset, self.request, view=self)

    def get_paginated_response(self, data):
        return self.paginator.get_paginated_response(data)