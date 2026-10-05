# 数据模型（用户 / 病害 / 防治方法 / 识别记录 / 反馈 / 新闻 / 敏感词…）
# ============================================================================
# 论坛相关模型在 `models_forum.py`（历史原因分开），多语言字段的 mixin 在
# `models_i18n.py`。
#
# 这个文件里最值得先读的是**两条生命周期**（都比字段定义重要）：
#   · **注销冷静期**（第 95 批加入、第 101 批改成 15 天）：
#     `request_deletion()` → `cancel_deletion()` → `soft_delete()`；
#     字段 `deletion_requested_at` / `deletion_scheduled_for` / `deletion_cancelled_at`。
#     语义见 `request_deletion` 的 docstring —— 申请后**立刻停用但保留个人信息**，
#     到期由 `manage.py purge_deletion_requests` 才真正清除；
#   · **敏感词**：改词库要 `cache.delete(...)` 让缓存失效（见模型里的说明）。
#
# ⚠️ 别在这里加"读的时候顺手写库"的逻辑：`serializers.py` 里已经有一处
# （`DetectionHistorySerializer.get_pest_info` 为修历史脏数据而回填），
# 那是例外，不是范式。
import logging  # 第 95 批：注销流程记日志
import uuid  # 第 95 批：注销时把密码置为不可用的随机串

from django.contrib.auth.models import AbstractUser  # 导入Django抽象用户基类
from django.db import models  # 导入Django模型模块
from django.utils import timezone  # 导入时区处理模块
from django.conf import settings  # 导入Django配置模块
from django.core.validators import FileExtensionValidator  # 导入文件扩展名验证器

# 第 85 批：用户内容的英文译文元数据（反馈内容 / 管理员回复），见 models_i18n.py
from .models_i18n import TranslationMetaMixin

logger = logging.getLogger(__name__)


class CustomUser(AbstractUser):  # 定义自定义用户模型，继承自AbstractUser
    """
    Custom user model to include user roles and profile information.
    """
    ROLE_CHOICES = (  # 定义角色选择项
        ('ADMIN', 'System Administrator'),  # 系统管理员
        ('EDITOR', 'Information Editor'),  # 信息编辑员
        ('USER', 'Normal User'),  # 普通用户
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='USER', verbose_name="角色")  # 角色字段
    bio = models.TextField(blank=True, null=True, verbose_name="个人简介")  # 个人简介字段
    # 第 23 批新增：真实头像。
    # 此前模型里没有这个字段，而 UserProfileSerializer.get_avatar() 恒返回 None，
    # 前端只能靠 https://ui-avatars.com 这个**外网服务**生成占位图（断网即裂）。
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name="头像")

    # 第 35 批新增：登录失败锁定（防暴力破解）
    # 之前登录接口没有任何失败次数限制 —— 可以无限次猜密码（实测无验证码、无限流）。
    failed_login_attempts = models.PositiveSmallIntegerField('连续登录失败次数', default=0)
    locked_until = models.DateTimeField('锁定截止时间', null=True, blank=True)

    # 第 42 批：等级与积分（等级由 points 推导，见 api/models_points.py）
    points = models.IntegerField('积分', default=0)

    # ========================================================================
    # 第 95 批：账号注销 / 删除（软删除）
    # ------------------------------------------------------------------------
    # 在此之前**没有注销账号的入口**：隐私政策里写着"如需注销账号请通过意见反馈提出申请"
    # （也就是靠人工），而管理端用户管理页明确只做读 —— 用户和管理员都删不了账号。
    #
    # 为什么是软删除而不是 `user.delete()`：
    #   · 帖子的 author 是 SET_NULL，评论/识别记录/积分流水是 CASCADE ——
    #     硬删会把它们一起带走。但这些是**社区共同内容**（别人的回复会变成孤儿），
    #     所以正确做法是"保留内容、清除个人信息"（见 soft_delete 的说明）。
    #   · 用户也可能后悔或需要申诉，留一条可追溯的记录比"查无此人"更负责。
    # ========================================================================
    is_deleted = models.BooleanField('已注销', default=False, db_index=True)
    deleted_at = models.DateTimeField('注销时间', null=True, blank=True)
    deleted_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deleted_users', verbose_name='注销操作人',
    )

    # ------------------------------------------------------------------------
    # 第 101 批：注销**冷静期**（申请 → 15 天内可取消 → 到期才真正删除）
    # ------------------------------------------------------------------------
    # 起因：第 95 批做成了"点一下立刻清空个人信息、不可撤销"。这在合规上没问题，
    # 但对用户不友好 —— 误点、情绪化操作、账号被盗后被恶意注销，都没有回头路。
    # 而且真要恢复只能找管理员手工改库（`username` 已经被改成 `deleted_<id>`，
    # 原用户名也未必还空着）。
    #
    # 现在的语义：
    #   · `deletion_requested_at` 有值、`is_deleted` 仍为 False → **冷静期**
    #     （账号已停用、无法登录，但个人信息完好，凭密码可取消）
    #   · 到期后由 `python manage.py purge_deletion_requests` 执行真正的软删除
    #     （`is_deleted=True` + 清个人信息）
    #
    # `deletion_scheduled_for` 单独存一列而不用"申请时间 + N 天"现算：
    # 冷静期长度将来可能调整，存量申请应当按**当时**的承诺执行，
    # 不能因为改了配置就提前/延后别人的注销日期。
    deletion_requested_at = models.DateTimeField('注销申请时间', null=True, blank=True, db_index=True)
    deletion_scheduled_for = models.DateTimeField('计划注销时间', null=True, blank=True, db_index=True)
    deletion_cancelled_at = models.DateTimeField('最近一次取消注销时间', null=True, blank=True)

    @property
    def is_locked(self):
        """当前是否处于锁定期"""
        return bool(self.locked_until and self.locked_until > timezone.now())

    @property
    def lock_remaining_seconds(self):
        """剩余锁定秒数（未锁定返回 0）"""
        if not self.is_locked:
            return 0
        return max(0, int((self.locked_until - timezone.now()).total_seconds()))

    def register_failed_login(self, max_attempts=5, lock_minutes=15):
        """
        记录一次登录失败；达到阈值就锁定账号。
        返回 (是否刚刚被锁定, 剩余尝试次数)
        """
        self.failed_login_attempts = (self.failed_login_attempts or 0) + 1
        just_locked = False

        if self.failed_login_attempts >= max_attempts:
            self.locked_until = timezone.now() + timezone.timedelta(minutes=lock_minutes)
            self.failed_login_attempts = 0  # 锁定后清零，解锁后重新计数
            just_locked = True

        self.save(update_fields=['failed_login_attempts', 'locked_until'])
        remaining = 0 if just_locked else max(0, max_attempts - self.failed_login_attempts)
        return just_locked, remaining

    def reset_login_failures(self):
        """登录成功后清零失败计数与锁定状态"""
        if self.failed_login_attempts or self.locked_until:
            self.failed_login_attempts = 0
            self.locked_until = None
            self.save(update_fields=['failed_login_attempts', 'locked_until'])

    # ------------------------------------------------------------------
    # 第 95 批：注销 / 删除账号
    # ------------------------------------------------------------------

    #: 注销后对外显示的名字。刻意**不含 id**：带上 id 就等于换个写法继续暴露身份。
    DELETED_DISPLAY_NAME = '已注销用户'
    DELETED_DISPLAY_NAME_EN = 'Deactivated user'

    @property
    def display_name(self):
        """对外展示名（注销后不再泄露原用户名）"""
        return self.DELETED_DISPLAY_NAME if self.is_deleted else self.username

    # ------------------------------------------------------------------
    # 第 101 批：注销冷静期（申请 / 取消 / 到期）
    # ------------------------------------------------------------------
    # 起因：第 95 批做成了"点一下立刻清空个人信息、不可撤销"。合规上没问题，
    # 但对用户不友好 —— 误点、情绪化操作、账号被盗后被恶意注销，都没有回头路；
    # 想恢复只能找管理员手工改库（`username` 已改成 `deleted_<id>`，
    # 原用户名也未必还空着）。
    #
    # 现在的语义：
    #   · `deletion_requested_at` 有值且 `is_deleted=False` → **冷静期**
    #     （账号已停用、无法登录；个人信息完好，凭密码可取消）
    #   · 到期后由 `manage.py purge_deletion_requests` 执行真正的软删除
    #   · 管理员删除走 `request_deletion(immediate=True)` —— 不进冷静期

    @staticmethod
    def deletion_grace_days():
        """冷静期天数（默认 15，可用 DJANGO_ACCOUNT_DELETION_GRACE_DAYS 覆盖）"""
        from django.conf import settings
        try:
            return max(0, int(getattr(settings, 'ACCOUNT_DELETION_GRACE_DAYS', 15)))
        except (TypeError, ValueError):
            return 15

    @property
    def has_pending_deletion(self):
        """是否处于冷静期（已申请注销、未到期、未取消）"""
        return bool(
            not self.is_deleted
            and self.deletion_requested_at
            and self.deletion_scheduled_for
        )

    @property
    def deletion_days_left(self):
        """冷静期还剩几天（向上取整）；没有待处理申请时返回 0"""
        if not self.has_pending_deletion:
            return 0
        remaining = (self.deletion_scheduled_for - timezone.now()).total_seconds()
        if remaining <= 0:
            return 0
        return int(-(-remaining // 86400))  # 向上取整，避免显示"还剩 0 天"

    def request_deletion(self, *, by=None, reason='', immediate=False):
        """
        申请注销。默认进入**冷静期**；`immediate=True` 直接执行（管理员删除用）。

        冷静期内做的事：
          · `is_active=False` —— **立即无法登录**（用户申请注销时最直接的预期）
          · 记录申请时间与计划删除时间（单独存一列，见字段注释的说明）
          · 失效所有 API Token 与已登录会话（否则"注销了但另一台设备还在用"）

        冷静期内**刻意不做**的事：不清个人信息、不改用户名、不改密码 ——
        因为要允许用户凭密码取消。真正清空发生在冷静期结束后的 `soft_delete`。

        返回 `(计划删除时间, 被清理的头像名)`；immediate=True 时第一项为 None。
        """
        if immediate:
            return None, self.soft_delete(by=by, reason=reason)

        now = timezone.now()
        self.is_active = False
        self.deletion_requested_at = now
        self.deletion_scheduled_for = now + timezone.timedelta(days=self.deletion_grace_days())
        self.deletion_cancelled_at = None
        self.failed_login_attempts = 0
        self.locked_until = None
        self.save(update_fields=[
            'is_active', 'deletion_requested_at', 'deletion_scheduled_for',
            'deletion_cancelled_at', 'failed_login_attempts', 'locked_until',
        ])

        # 凭证一起失效：申请注销后不该再有设备能用这张账号
        from rest_framework.authtoken.models import Token
        Token.objects.filter(user=self).delete()
        self._clear_sessions()

        logger.info('账号进入注销冷静期: id=%s 计划删除=%s', self.id, self.deletion_scheduled_for)
        return self.deletion_scheduled_for, ''

    def cancel_deletion(self):
        """取消注销申请（冷静期内有效）：恢复可用并清掉申请标记"""
        if not self.has_pending_deletion:
            return False
        self.is_active = True
        self.deletion_cancelled_at = timezone.now()
        self.deletion_requested_at = None
        self.deletion_scheduled_for = None
        self.save(update_fields=[
            'is_active', 'deletion_cancelled_at',
            'deletion_requested_at', 'deletion_scheduled_for',
        ])
        logger.info('账号取消注销: id=%s', self.id)
        return True

    def _clear_sessions(self):
        """清掉 Django 会话里属于本用户的记录（管理员被删后会话仍可用是实测过的漏洞）"""
        from django.contrib.sessions.models import Session
        try:
            for session in Session.objects.filter(expire_date__gte=timezone.now()):
                try:
                    data = session.get_decoded()
                except Exception:  # noqa: BLE001
                    # 会话数据在缓存里；缓存过期而数据库行还在时 get_decoded() 会抛异常
                    # （Django 自己也会打 "Session data corrupted" 警告）。跳过即可。
                    continue
                if str(data.get('_auth_user_id')) == str(self.id):
                    session.delete()
        except Exception as exc:  # noqa: BLE001
            logger.warning('清理用户 %s 的会话失败: %s', self.id, exc)

    def soft_delete(self, *, by=None, reason=''):
        """
        **软删除账号**：清除个人信息、禁止登录、失效全部凭证，但保留数据行。

        具体做的事：
          1. 清掉个人标识：用户名改成 `deleted_<id>`、邮箱/姓名/简介/头像全部清空；
             （用户名必须让出来并变形，否则"已注销"的用户名还能被人拿去试探身份）
          2. `is_active=False` + `is_deleted=True` + 记时间与操作人；
          3. 删掉 API Token、把密码换成一段不可用的随机串
             （即使有人拿到旧 token 或旧密码也无法再用这张账号）；
          4. 清掉 Django 会话里属于他的记录（否则管理员被删后，**已经登录的 admin 会话
             仍然能用** —— 这是实测过的真实漏洞）。

        第 101 批：这个方法现在承担两个入口 ——
          · 冷静期到期后的**执行**（`purge_deletion_requests` 调用）；
          · 管理员直接删除（`request_deletion(immediate=True)`）。
        两者都要求"这一步之后不可恢复"，所以共用这里。

        刻意**不删**的东西：
          · 帖子（`author` 是 SET_NULL，硬删会连带把别人的评论一起带走）；
          · 评论、识别记录、积分流水的**行**仍在（内容属于社区，见文档说明）。
            展示层用 `display_name` 显示"已注销用户"，不再暴露原身份。

        返回被清理的头像名（调用方可据此删文件），没有则返回空串。
        """
        old_avatar = self.avatar.name if self.avatar else ''

        # 1) 让出用户名并清除个人信息
        self.username = f'deleted_{self.id}'
        self.email = ''
        self.first_name = ''
        self.last_name = ''
        self.bio = ''
        self.avatar = None
        # 2) 标记
        self.is_active = False
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = by
        self.failed_login_attempts = 0
        self.locked_until = None
        # 3) 密码置为不可用（随机串，没人知道；不是空串 —— 空串在某些后端等于"无密码可校验"）
        self.set_password(uuid.uuid4().hex + uuid.uuid4().hex)

        self.save(update_fields=[
            'username', 'email', 'first_name', 'last_name', 'bio', 'avatar',
            'is_active', 'is_deleted', 'deleted_at', 'deleted_by',
            'deletion_requested_at', 'deletion_scheduled_for',
            'failed_login_attempts', 'locked_until', 'password',
        ])

        # 4) 失效 API Token
        from rest_framework.authtoken.models import Token
        Token.objects.filter(user=self).delete()

        # 5) 清会话（关键：不做这一步，已登录的 admin 会话还能继续操作）
        #    第 101 批：这段逻辑与 request_deletion 共用 `_clear_sessions()`
        self._clear_sessions()

        logger.info(
            '账号已注销: id=%s（操作人=%s 原因=%s）',
            self.id, getattr(by, 'id', None) or 'self', reason or '-',
        )
        return old_avatar

    class Meta:  # 定义模型元数据
        verbose_name = "用户"  # 单数名称
        verbose_name_plural = verbose_name  # 复数名称


class SensitiveWord(models.Model):
    """
    敏感词（第 38 批）

    管理员维护；发帖/评论/反馈/新闻都会先过一遍（见 `api/sensitive.py`）。
    放在这里而不是单独模块，是因为 Django 只在 app 的 models 模块里自动发现模型。
    """

    CATEGORY_CHOICES = (
        ('ad', '广告推广'),
        ('abuse', '辱骂攻击'),
        ('politics', '涉政违规'),
        ('other', '其它'),
    )

    word = models.CharField('敏感词', max_length=50, unique=True)
    category = models.CharField('分类', max_length=20, choices=CATEGORY_CHOICES, default='other')
    is_active = models.BooleanField('启用', default=True)
    note = models.CharField('备注', max_length=200, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '敏感词'
        verbose_name_plural = verbose_name
        ordering = ['category', 'word']

    def __str__(self):
        return self.word

    def save(self, *args, **kwargs):
        from django.core.cache import cache
        self.word = (self.word or '').strip()
        super().save(*args, **kwargs)
        cache.delete('sensitive_words:active')  # 词库变了立即失效

    def delete(self, *args, **kwargs):
        from django.core.cache import cache
        result = super().delete(*args, **kwargs)
        cache.delete('sensitive_words:active')
        return result


class CropVariety(models.Model):  # 定义作物品种模型
    """
    Crop variety management.
    """
    name = models.CharField(max_length=100, verbose_name="作物品种名称")  # 品种名称字段
    description = models.TextField(blank=True, null=True, verbose_name="描述")  # 品种描述字段

    def __str__(self):  # 定义对象字符串表示
        return self.name  # 返回品种名称

    class Meta:  # 定义模型元数据
        verbose_name = "作物品种"  # 单数名称
        verbose_name_plural = verbose_name  # 复数名称


class PestInfo(models.Model):  # 定义病害信息模型
    """
    Pest and disease information management.
    """
    name = models.CharField(max_length=255, verbose_name="病害名称")  # 病害名称字段
    # 第 69 批（多语言 C 阶段）：内容数据英文字段。
    # 说明：这些是**数据**（病害名/作物名来自 PlantVillage 数据集），界面文案的翻译不应塞进前端文案表，
    # 所以给数据加 *_en 字段；前端按当前语言选择显示哪个字段，后端管理界面可人工校正。
    name_en = models.CharField(max_length=255, blank=True, default='', verbose_name="病害名称（英文）")
    image = models.ImageField(upload_to='pest_images/', blank=True, null=True, verbose_name="病害图片")  # 病害图片字段
    crop_type = models.CharField(max_length=100, verbose_name="作物类型")  # 作物类型字段
    crop_type_en = models.CharField(max_length=100, blank=True, default='', verbose_name="作物类型（英文）")
    symptoms = models.TextField(verbose_name="症状", default="暂无症状描述")  # 症状描述字段
    # 第 72 批：症状/发病规律也补英文字段 —— 此前只有 name/crop_type 有英文，
    # 于是英文界面下"症状 / 发病规律"整段仍是中文（用户反馈"切换成英语还是没有完全翻译"）。
    symptoms_en = models.TextField(blank=True, default='', verbose_name="症状（英文）")
    english_identifier = models.CharField(max_length=255, unique=True, verbose_name="英文标识符")  # 英文标识符字段

    description = models.TextField(verbose_name="详细描述", default="暂无详细描述")  # 详细描述字段
    description_en = models.TextField(blank=True, default='', verbose_name="详细描述（英文）")

    def __str__(self):  # 定义对象字符串表示
        return f"{self.crop_type} - {self.name}"  # 返回作物类型和病害名称

    class Meta:  # 定义模型元数据
        verbose_name = "病害信息"  # 单数名称
        verbose_name_plural = verbose_name  # 复数名称
        unique_together = ('name', 'crop_type')  # 定义唯一约束


class PreventionMethod(models.Model):  # 定义防治方法模型
    CATEGORY_CHOICES = [  # 定义防治类别选择项
        ('AGRICULTURAL', '农业防治'),  # 农业防治
        ('CHEMICAL', '化学防治'),  # 化学防治
        ('ECOLOGICAL', '生态防治'),  # 生态防治
        ('PHYSICAL', '物理防治'),  # 物理防治
        ('MONITORING', '监测预警'),  # 监测预警
    ]
    pest = models.ForeignKey(PestInfo, related_name='prevention_methods', on_delete=models.CASCADE,
                             verbose_name="关联病害")  # 关联病害外键
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, verbose_name="防治类别")  # 防治类别字段
    measure = models.TextField(verbose_name="具体措施")  # 具体措施字段
    # 第 72 批：防治措施也补英文字段（英文界面下防治建议此前整段是中文）
    measure_en = models.TextField(blank=True, default='', verbose_name="具体措施（英文）")

    def __str__(self):  # 定义对象字符串表示
        return f"{self.pest.name} - {self.get_category_display()}"  # 返回病害名称和防治类别

    class Meta:  # 定义模型元数据
        verbose_name = "防治方法"  # 单数名称
        verbose_name_plural = verbose_name  # 复数名称


class DetectionHistory(models.Model):  # 定义检测历史模型
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name="用户")  # 用户外键
    image = models.ImageField(upload_to='detection_history/', verbose_name="检测图片")  # 检测图片字段
    annotated_image = models.ImageField(upload_to='detection_history/annotated/', blank=True, null=True,
                                        verbose_name="标注图片")  # 标注图片字段
    detection_result = models.CharField(max_length=255, verbose_name="检测结果")  # 检测结果字段
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="检测时间")  # 检测时间字段
    pest_info = models.ForeignKey(PestInfo, on_delete=models.SET_NULL, null=True, blank=True,
                                  verbose_name="关联病害")  # 关联病害外键
    confidence = models.FloatField(null=True, blank=True, verbose_name="置信度")  # 置信度字段

    def __str__(self):  # 定义对象字符串表示
        return f"{self.user.username} - {self.detection_result} at {self.timestamp}"  # 返回用户名、检测结果和检测时间

    class Meta:  # 定义模型元数据
        verbose_name = "识别历史"  # 单数名称
        verbose_name_plural = verbose_name  # 复数名称
        ordering = ['-timestamp']  # 默认按时间倒序排列


# 用户反馈模型
class Feedback(TranslationMetaMixin):  # 定义用户反馈模型
    """
    用户反馈

    第 26 批（用户协议/隐私政策/帮助中心/意见反馈四块一起补）扩展：
    - 原来只能承载"识别结果对不对"这种反馈（`disease_name` / `is_correct` 都是必填），
      没法用来提交一般性的意见与问题；
    - 现把这两个字段改为可选，并补上「反馈类型 / 处理状态 / 管理员回复 / 处理时间」，
      于是既能继续服务识别结果反馈，也能支撑独立的「意见反馈」页面。

    第 85 批：补英文译文字段。
    反馈内容与管理员回复都是**人写的中文**（用户写的意见、管理员写的答复），
    英文界面下原来是中文。这里沿用论坛那套"译文 + 指纹 + 来源"的机制
    （见 models_i18n.py），译文由 `manage.py translate_forum_content --kind=feedback`
    或管理员在 Django admin 里手工填写。
    """
    CATEGORY_CHOICES = (
        ('suggestion', '功能建议'),
        ('bug', '问题反馈'),
        ('recognition', '识别纠错'),  # 由「病害识别」结果页的"识别正确/不正确"产生
        ('other', '其他'),
    )
    STATUS_CHOICES = (
        ('pending', '待处理'),
        ('processing', '处理中'),
        ('resolved', '已处理'),
    )

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name="用户", null=True, blank=True)  # 用户外键
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='suggestion',
                               verbose_name="反馈类型")  # 反馈类型（意见反馈页使用）
    image = models.ImageField(upload_to='feedback_images/', verbose_name="反馈图片", null=True, blank=True)  # 反馈图片字段
    disease_name = models.CharField(max_length=255, blank=True, default='',
                                   verbose_name="病害名称")  # 病害名称字段（识别结果反馈才有）
    confidence = models.FloatField(null=True, blank=True, verbose_name="置信度")  # 置信度字段
    is_correct = models.BooleanField(null=True, blank=True, verbose_name="识别是否正确")  # 识别是否正确字段（识别结果反馈才有）
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="反馈时间")  # 反馈时间字段
    suggestion = models.TextField(blank=True, null=True, verbose_name="反馈内容")  # 反馈内容（原"用户建议"）
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending',
                              verbose_name="处理状态")  # 处理状态（管理员在后台流转）
    admin_reply = models.TextField(blank=True, default='', verbose_name="管理员回复")  # 管理员回复
    handled_at = models.DateTimeField(null=True, blank=True, verbose_name="处理时间")  # 处理时间

    # 第 85 批：英文译文（反馈内容 + 管理员回复各一份）
    suggestion_en = models.TextField(blank=True, default='', verbose_name="反馈内容（英文）")
    admin_reply_en = models.TextField(blank=True, default='', verbose_name="管理员回复（英文）")

    # ========================================================================
    # 第 91 批：把"识别纠错"变成**可用的训练样本**
    # ------------------------------------------------------------------------
    # 改前的断链（很典型）：前端 `DetectView.vue` 提交反馈时**一直在传**
    # `detection_id`（移动端 `api/detection.js` 同样传），但 Feedback 模型与
    # 序列化器都没有这个字段 —— 参数被静默丢弃。结果是：
    #   · 反馈无法回指那条识别记录（管理员在后台复查不了原图与置信度）；
    #   · 纠错只存了"对/错"，没有"正确是哪一种" → 负反馈只能计数，**变不成标签**；
    #   · 没有任何导出入口，人工确认过的样本只能靠手抄。
    # 补上下面四个字段后，链路就闭合了：识别 → 纠错（含正确类别）→ 审核确认 → 导出数据集。
    # ========================================================================
    detection = models.ForeignKey(
        'DetectionHistory', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='feedbacks', verbose_name="关联识别记录",
    )
    corrected_pest = models.ForeignKey(
        PestInfo, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='corrections', verbose_name="纠正为（正确病害）",
    )
    VERIFY_CHOICES = (
        ('pending', '待确认'),    # 用户提交后默认状态：还没人核对
        ('confirmed', '已确认'),  # 管理员核对过，可以进训练集
        ('rejected', '已排除'),   # 明显误报/无效，不进训练集
    )
    verify_status = models.CharField(
        max_length=10, choices=VERIFY_CHOICES, default='pending',
        verbose_name="样本确认状态",
    )
    exported_at = models.DateTimeField(
        null=True, blank=True, verbose_name="上次导出时间",
    )

    def __str__(self):  # 定义对象字符串表示
        return f"{self.disease_name} - {'正确' if self.is_correct else '不正确'}"  # 返回病害名称和识别正确性

    @property
    def is_trainable(self):
        """
        这条反馈能不能当训练样本用

        需要同时满足：分类是识别纠错、用户说"识别错了"、并且给出了正确类别
        （只说"错了"而不说"对的是什么"，对训练没有增量信息）。
        标注本身可以留着 pending —— 训练集导出默认只取 `confirmed`。
        """
        return (
            self.category == 'recognition'
            and self.is_correct is False
            and self.corrected_pest_id is not None
        )

    def translation_source_texts(self):
        """第 85 批：反馈内容与管理员回复都参与指纹（改任意一处都要重译）"""
        return [self.suggestion, self.admin_reply]

    def has_any_translation(self):
        """只要有一份译文就算"有译文"（反馈内容与回复是两条独立的信息）"""
        return bool(
            (self.suggestion_en or '').strip() or (self.admin_reply_en or '').strip()
        )

    class Meta:  # 定义模型元数据
        verbose_name = "用户反馈"  # 单数名称
        verbose_name_plural = verbose_name  # 复数名称
        ordering = ['-timestamp']  # 默认按时间倒序排列


class News(models.Model):  # 定义新闻模型
    """
    Industry news and updates.
    """
    # 新闻分类选项
    CATEGORY_CHOICES = (
        ('policy', '政策解读'),
        ('tech', '农业技术'),
        ('market', '市场动态'),
        ('report', '行业报告'),
        ('notice', '通知公告'),
    )
    
    title = models.CharField(max_length=200, verbose_name="新闻标题")  # 新闻标题字段
    content = models.TextField(verbose_name="新闻内容")  # 新闻内容字段
    # 第 72 批：新闻是管理员维护的内容数据，英文界面下需要英文标题与正文
    title_en = models.CharField(max_length=200, blank=True, default='', verbose_name="新闻标题（英文）")
    content_en = models.TextField(blank=True, default='', verbose_name="新闻内容（英文）")
    image = models.ImageField(upload_to='news_images/', blank=True, null=True, verbose_name="新闻图片")  # 新闻图片字段
    source = models.CharField(max_length=100, blank=True, null=True, verbose_name="来源")  # 来源字段
    # 第 72 批：来源是机构名（如"中国气象局"），英文界面下需要英文写法
    source_en = models.CharField(max_length=100, blank=True, default='', verbose_name="来源（英文）")
    author = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
                               verbose_name="发布人")  # 发布人外键
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='notice', 
                               verbose_name="新闻分类")  # 新闻分类字段
    tags = models.CharField(max_length=255, blank=True, null=True, verbose_name="标签")  # 标签字段，多个标签用逗号分隔
    is_published = models.BooleanField(default=True, verbose_name="是否发布")  # 是否发布字段
    # 第 38 批：定时发布。为空=立即生效；设为未来时间则到点才对外可见（管理员始终可见）。
    published_at = models.DateTimeField(
        null=True, blank=True, verbose_name="定时发布时间",
        help_text="留空表示立即发布；填未来时间则到点才对外可见",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")  # 创建时间字段
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")  # 更新时间字段

    def __str__(self):  # 定义对象字符串表示
        return self.title  # 返回新闻标题

    @property
    def is_pending_schedule(self):
        """是否还在等待定时时间（到点前对用户不可见）"""
        return bool(self.published_at and self.published_at > timezone.now())

    @property
    def is_visible_to_public(self):
        """对普通用户是否可见：已发布 且 未处于"等待定时"状态"""
        return bool(self.is_published and not self.is_pending_schedule)

    class Meta:  # 定义模型元数据
        verbose_name = "行业新闻"  # 单数名称
        verbose_name_plural = verbose_name  # 复数名称
        ordering = ['-created_at']  # 默认按创建时间倒序排列


# ============================================================================
# 第 43 批修复：把"卫星模型模块"在这里统一导入一次
# ----------------------------------------------------------------------------
# Django 只会自动导入每个应用的 `models` 模块；放在别的文件里的模型
# （models_forum / models_notify / models_social / models_report /
#   models_message / models_points）必须有人 import 它们才会被注册。
#
# 之前它们只在"加载了 urls.py"的进程里被间接导入（urls → views → models_xxx），
# 于是出现一个很隐蔽的事故：在**只 import 了 api.models 的进程**里（例如
# `manage.py shell` 里直接删用户），Django 的删除收集器根本不知道 `PointLog`
# 这些表的存在，删用户时**不会级联**，最终在 COMMIT 时抛
# `IntegrityError: FOREIGN KEY constraint failed` —— 用户根本删不掉。
#
# 放在文件**末尾**导入：此时 CustomUser / Post 等都已定义好，不存在循环导入问题。
# 这样任何 import 了 `api.models` 的进程都能拿到全部模型。
# ============================================================================
from . import models_calendar  # noqa: E402,F401
from . import models_expert  # noqa: E402,F401
from . import models_forum  # noqa: E402,F401
from . import models_message  # noqa: E402,F401
from . import models_notify  # noqa: E402,F401
from . import models_points  # noqa: E402,F401
from . import models_report  # noqa: E402,F401
from . import models_social  # noqa: E402,F401
