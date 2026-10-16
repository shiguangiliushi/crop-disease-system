"""
业务接口视图（第 106 批补文件级说明）
============================================================================
**这是本项目最大的文件（2600 余行），里面装着大部分对外接口。**
之所以没有拆成多个模块：这些视图是**同一批需求**长出来的（识别、统计、
反馈、报告、上传…），彼此共享同一套响应形状与错误处理习惯；
拆开需要先把这套"隐式约定"显式化，那是另一件事。

改这个文件前先知道三件事
----------------------------------------------------------------------------
1. **文件按"功能块"排布，不是按目录结构。** 主要落点（行号会变，用名字找）：

   | 类 | 作用 |
   |---|---|
   | `RegisterView` | 注册（`AllowAny` + 限流 scope=register） |
   | `LoginView` | 登录：失败锁定 + 限流 + **注销冷静期分支**（见 §2） |
   | `StatisticsView` | 首页统计聚合（6 类聚合，手写而非复用列表接口） |
   | `DetectView` | **识别主入口**：落盘 → 推理 → 匹配病害 → 写历史 |
   | `PreventionDataView` | 防治数据（第 78 批修过 `english_name` 字段 bug） |
   | `FeedbackView` | 意见反馈（含第 100 批的批量改状态） |
      | `DetectionHistoryClearView` | 清空识别历史（**会同时删图片文件**） |
   | `PestTypesView` | 病害名列表（只回名字、没有 id —— 见该类 docstring） |

2. **登录有两个"停用"来源，别只改一处。** `is_active=False` 的账号走不通
   正常认证（Django 的 `ModelBackend.user_can_authenticate` 直接返回 None），
   所以**注销冷静期的判断必须放在 `authenticate()` 之前**、用 `check_password()`
   自己验密码。第 101 批踩过这个坑：放在之后的分支永远不会执行，
   用户拿到的是"用户名或密码错误"，而他的密码其实是对的。

3. **失败响应的形状不统一，这是历史遗留、不是笔误**：

   * 有的返回 `{'error': ..., 'retryable': bool}`（识别相关，给农户看的文案）；
   * 有的返回 `{'status': 'error', 'message': ...}`（早期风格）；
   * DRF 原生的返回 `{'detail': ...}` 或字段名映射。

   所以前端有 `formatApiError()` 专门做兼容（见 `frontend/src/api/http.js`）。
   **改单个接口的失败形状属于破坏性改动** —— 先看前端有没有在读那个 key。

⚠️ 一个反复出现的设计缺陷（第 106 批记录，未全面清理）
----------------------------------------------------------------------------
好几个视图用 `try: ... except Exception as e:` 把**任何**异常收成 500 +
一句笼统文案，真实原因只进日志。后果是：
`PestTypesView` 里那个"字段名写错"的 bug 让接口**一直 500**，
而响应体只写"获取病害类型失败" —— 排查时只能去翻 `logs/debug.log`。
新增接口时请至少把 `logger.exception` 带上 `exc_info`（现有代码大多只
`logger.error(str(e))`，丢了栈信息）。
"""
import base64
import json
import logging
import os
import re
import tempfile
import time
import traceback
import uuid
from datetime import datetime, timedelta
from io import BytesIO

import cv2
import numpy as np
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count, F
from django.db.models.functions import TruncDay, TruncMonth, TruncYear
from django.http import FileResponse, HttpResponse, request
from django.utils import timezone
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image as ReportLabImage
)
from rest_framework import status, viewsets, permissions
from rest_framework.authtoken.models import Token
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.exceptions import ParseError  # 请求体解析失败（应作为 400 而不是 500 处理）
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.throttling import ScopedRateThrottle  # 第 35 批：按 scope 限流（登录/注册/找回密码）
from rest_framework.generics import (
    RetrieveAPIView, RetrieveUpdateDestroyAPIView, ListAPIView,
    CreateAPIView, ListCreateAPIView
)
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
# 第 43 批：零依赖 Excel 导出
from .xlsx import build_workbook

# 配置日志记录器
logger = logging.getLogger(__name__)
from .audit import log_admin_action  # noqa: E402  第 146 批：管理操作日志
from .bulk import parse_ids  # noqa: E402  第 147 批：批量接口的公共校验

from .ai_service import get_ai_service
from .models import (
    CustomUser, DetectionHistory, PestInfo,
    PreventionMethod, Feedback, News
)
from .pagination import CustomPagination
from .permissions import IsAdminOrReadOnly
# 第 124 批：能力口径统一收口（本站原来同一个判定抄了 16 处）
from .capabilities import (
    CAP_USER_ADMIN, IsFeedbackEditor, MODULE_FEEDBACK, capabilities_of, content_modules_of,
    has_content_module,
    has_capability, is_full_admin,
)
from .image_validation import ImageValidationError, validate_image_upload  # 第 91 批：图片上传校验
from .services_content_i18n import pest_en_maps  # 第 77 批：聚合接口的中英对照
from . import serializers
from .serializers import (
    CustomUserSerializer,
    PestInfoDetailSerializer,
    PestInfoListSerializer,
    PestInfoWriteSerializer,
    DetectionHistorySerializer,
    PreventionMethodSerializer,
    NewsSerializer
)

# Default data for initialization
default_data = {
    'diseases': [],
    'prevention_methods': []
}


# 注册中文字体
def register_fonts():
    """
    注册 PDF 报告使用的中文字体

    修复说明：原路径为 os.path.join(BASE_DIR, 'backend', 'static', ...)，
    而 settings.BASE_DIR 本身就是 backend 目录，拼出来是
    backend/backend/static/fonts/simsun.ttc（不存在），因此一直静默回退到
    Helvetica —— 后端生成的 PDF 报告里中文无法正常显示。
    另外兼容字体缺失时回退到系统字体，避免直接抛错。
    """
    candidates = [
        os.path.join(settings.BASE_DIR, 'static', 'fonts', 'simsun.ttc'),
        os.path.join(settings.BASE_DIR, 'static', 'fonts', 'simsun.ttf'),
        os.path.join(settings.BASE_DIR.parent, 'backend', 'static', 'fonts', 'simsun.ttc'),
    ]

    for font_path in candidates:
        if not os.path.exists(font_path):
            continue
        try:
            if 'SimSun' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('SimSun', font_path))
            return 'SimSun'
        except Exception as e:  # noqa: BLE001
            logger.warning('注册中文字体失败(%s): %s', font_path, e)

    logger.warning('未找到可用的中文字体文件，PDF 报告将使用默认字体')
    return 'Helvetica'


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    # 第 35 批：注册限流（防批量注册刷账号）
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'register'

    def post(self, request):
        serializer = CustomUserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            # 注册成功的同时签发 Token，让前端可以「注册即登录」。
            # 响应结构与 LoginView 对齐：{status, message, data:{user, token}}。
            # （此前只返回扁平的用户信息、且不含 token，前端只能注册完再让用户手动登录一次）
            # 第 94 批：与登录一致 —— 直接建新 Token，不复用（避免拿到过期的旧凭证）。
            token = Token.objects.create(user=user)
            return Response({
                'status': 'success',
                'message': '注册成功',
                'data': {
                    'user': CustomUserSerializer(user).data,
                    'token': token.key,
                },
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StatisticsView(APIView):
    """
    提供统计数据的API视图
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # 获取当前用户
        user = request.user
        logger.info(
            f'Getting statistics for user: {user.username}, is_staff: {user.is_staff}, is_superuser: {user.is_staff or user.is_superuser}')

        try:
            # 统计范围与识别记录列表**保持一致**（第 22 批）：
            #   普通用户           → 只看自己
            #   管理员 + all_users=true → 全部用户
            #   管理员不带该参数    → 只看自己
            # 原来这里的判定是 `is_staff or is_superuser`（漏了 role=ADMIN），
            # 且**完全忽略 all_users 参数** —— 结果是管理员无论看哪个页面拿到的都是
            # 全部用户的统计，跟列表范围对不上（"列表只有我的、图表是所有人"）。
            #
            # 第 124 批：改用 `USER_ADMIN` 能力（"能不能看**别人**的数据"），
            # 并且与下面 `feedback_stats` 的第二处判定**必须是同一个口径** ——
            # 否则会出现"识别统计是全站、反馈统计只有我"的错位。
            can_see_all_users = has_capability(user, CAP_USER_ADMIN)
            all_users = request.query_params.get('all_users') == 'true'

            if can_see_all_users and all_users:
                # 管理员查看所有用户数据
                user_filter = {}
                user_count = CustomUser.objects.count()
                logger.info('Admin user detected with all_users=true, showing all records')
            else:
                # 其余情况只看自己
                user_filter = {'user': user}
                user_count = 1
                logger.info(f'Statistics scoped to user {user.id} records')

            # 获取基础查询集
            base_queryset = DetectionHistory.objects.filter(**user_filter)
            logger.info(f'Base queryset count: {base_queryset.count()}')

            # 1. 病害类型分布 - 统计所有记录，按病害类型分组
            pest_distribution = []
            try:
                # 使用聚合查询确保每个记录只被统计一次
                from django.db.models import Count, Case, When, Value, IntegerField

                # 第 77 批：中→英映射（见 services_content_i18n 的说明：不能直接加进
                # values()，否则会改变 GROUP BY 口径、把同一病害拆成两行）
                pest_name_en_map, crop_name_en_map = pest_en_maps()

                # 先统计每种病害的数量
                pest_counts = base_queryset.values('pest_info__name') \
                    .annotate(count=Count('id')) \
                    .order_by('-count')

                # 处理空值并转换为列表
                pest_distribution = []
                total_count = 0

                for item in pest_counts:
                    pest_name = item['pest_info__name'] or '未知病害'
                    count = item['count']
                    pest_distribution.append({
                        'pest_info__name': pest_name,
                        # 第 77 批：英文界面下统计图的柱标签要用英文
                        'pest_info__name_en': pest_name_en_map.get(pest_name, ''),
                        'count': count
                    })
                    total_count += count

                # 记录调试信息
                logger.info(f'Pest distribution query result: {pest_distribution}')
                logger.info(f'Total records in pest distribution: {total_count}')
                logger.info(f'Total records in base_queryset: {base_queryset.count()}')

                # 确保所有记录都被统计
                if total_count != base_queryset.count():
                    logger.warning(
                        f'Record count mismatch: {total_count} in distribution vs {base_queryset.count()} in queryset')

                    # 如果有记录未被统计，添加未知类别
                    if total_count < base_queryset.count():
                        unknown_count = base_queryset.filter(pest_info__isnull=True).count()
                        if unknown_count > 0:
                            pest_distribution.append({
                                'pest_info__name': '未知病害',
                                'pest_info__name_en': '',
                                'count': unknown_count
                            })
                            total_count += unknown_count
                            logger.info(f'Added {unknown_count} unknown records to distribution')

                logger.info(f'Final pest distribution count: {total_count}')
            except Exception as e:
                logger.error(f'查询病害类型分布时出错: {str(e)}', exc_info=True)

            # 2. 时间趋势（按月份）
            monthly_trends = []
            try:
                monthly_trends = list(base_queryset.annotate(
                    month=TruncMonth('timestamp')
                ).values('month').annotate(
                    count=Count('id')
                ).order_by('month'))
                logger.info(f'Monthly trends query result: {monthly_trends}')
            except Exception as e:
                logger.error(f'查询时间趋势时出错: {str(e)}', exc_info=True)

            # 3. 作物病害分布 - 统计所有记录，包括pest_info为空的记录
            crop_distribution = []
            try:
                # 先获取有pest_info和crop_type的记录
                with_crop_type = base_queryset.filter(
                    pest_info__isnull=False,
                    pest_info__crop_type__isnull=False
                ).values(
                    'pest_info__crop_type'
                ).annotate(
                    count=Count('id')
                ).order_by('-count')

                # 获取没有pest_info或crop_type的记录数量
                without_crop_type_count = base_queryset.filter(
                    Q(pest_info__isnull=True) | Q(pest_info__crop_type__isnull=True)
                ).count()

                # 合并结果
                # 第 77 批：作物分布同样带上英文名（英文界面下饼图图例要是英文）
                crop_distribution = [
                    {**row, 'pest_info__crop_type_en': crop_name_en_map.get(row['pest_info__crop_type'], '')}
                    for row in with_crop_type
                ]
                if without_crop_type_count > 0:
                    crop_distribution.append({
                        'pest_info__crop_type': '未知作物',
                        'pest_info__crop_type_en': '',
                        'count': without_crop_type_count
                    })

                logger.info(f'Crop distribution query result: {crop_distribution}')
            except Exception as e:
                logger.error(f'查询作物分布时出错: {str(e)}', exc_info=True)

            # 4. 最近7天检测统计
            today = timezone.localdate()
            last_7_days = []
            for i in range(6, -1, -1):
                day = today - timedelta(days=i)
                count = base_queryset.filter(
                    timestamp__date=day
                ).count()
                last_7_days.append({
                    'date': day.strftime('%Y-%m-%d'),
                    'count': count
                })
            logger.info(f'Last 7 days stats: {last_7_days}')

            # 5. 反馈统计（数据来自独立的 Feedback 模型，is_correct=True 记为正向反馈）
            feedback_queryset = Feedback.objects.all()
            if not can_see_all_users:
                feedback_queryset = feedback_queryset.filter(user=request.user)

            feedback_total = feedback_queryset.count()
            feedback_positive = feedback_queryset.filter(is_correct=True).count()
            feedback_stats = {
                'total': feedback_total,
                'positive': feedback_positive,
                'negative': feedback_total - feedback_positive,
                'neutral': 0,
            }

            # 6. 今日检测数量
            today_detections = base_queryset.filter(
                timestamp__date=today
            ).count()

            # 7. 本月检测数量
            now = timezone.now()
            detections_this_month = base_queryset.filter(
                timestamp__month=now.month,
                timestamp__year=now.year
            ).count()

            # 8. 唯一病害类型数量
            unique_pests = base_queryset.filter(
                pest_info__isnull=False
            ).values('pest_info').distinct().count()

            data = {
                'status': 'success',
                'message': 'Statistics retrieved successfully',
                'pest_distribution': pest_distribution or [],
                'monthly_trends': monthly_trends or [],
                'crop_distribution': crop_distribution or [],
                'last_7_days': last_7_days or [],
                'feedback_stats': feedback_stats or {
                    'total': 0,
                    'positive': 0,
                    'negative': 0,
                    'neutral': 0
                },
                'total_detections': base_queryset.count(),
                'unique_pests': unique_pests,
                'detections_this_month': detections_this_month,
                'today_detections': today_detections,
                'total_users': user_count,
                'is_admin': can_see_all_users
            }

            # 记录详细的调试信息
            logger.info('=' * 50 + ' STATISTICS DATA ' + '=' * 50)
            logger.info(f'Base queryset count: {base_queryset.count()}')
            logger.info(f'Pest distribution count: {len(pest_distribution)}')
            logger.info(f'Monthly trends count: {len(monthly_trends)}')
            logger.info(f'Crop distribution count: {len(crop_distribution)}')
            logger.info(f'Pest distribution sample: {pest_distribution[:3]}')
            logger.info(f'Monthly trends sample: {monthly_trends[:3]}')
            logger.info(f'Crop distribution sample: {crop_distribution[:3]}')
            logger.info('=' * 117)

            return Response(data)

        except Exception as e:
            logger.error(f'获取统计信息时发生错误: {str(e)}', exc_info=True)
            # 返回默认数据而不是500错误
            return Response(default_data, status=status.HTTP_200_OK)
            return Response(default_data, status=status.HTTP_200_OK)


class CheckAuthView(APIView):
    """
    检查用户认证状态
    - 返回当前用户信息（如果已认证）
    - 401未授权（如果未认证）
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            'status': 'success',
            'message': 'User is authenticated',
            'data': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
                'role': getattr(user, 'role', 'USER'),
                # 第 23 批：与登录响应保持一致，带上头像地址
                'avatar': serializers._user_avatar_url(user, request),
                # 第 124 批：能力清单（前端据此显示后台菜单与按钮；
                # 真正的边界始终在后端 —— 前端只负责"别把做不到的东西画出来"）
                'capabilities': capabilities_of(user),
                # 第 128 批：内容模块清单（内容侧**按模块**显示：勾了新闻才给新闻管理）
                'content_modules': content_modules_of(user),
            }
        })


class LogoutView(APIView):
    """
    用户登出API视图
    - 登出当前用户
    - 清除认证token
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # 清除用户的认证token
        if hasattr(request.user, 'auth_token'):
            request.user.auth_token.delete()

        # 清除session
        logout(request)

        return Response({
            'status': 'success',
            'message': 'Successfully logged out.'
        }, status=status.HTTP_200_OK)


def _inactive_login_response(user):
    """
    「账号不可用」的登录响应（第 142 批抽成函数：**提前拦**与**兜底**共用一份文案）

    ⚠️ 为什么必须在 `authenticate()` **之前**判：Django 的 `ModelBackend` 对
    `is_active=False` 的用户直接返回 None（`user_can_authenticate`），
    所以登录视图里 `authenticate()` 之后那段 `if not user.is_active` **够不着** ——
    被停用的账号拿到的是 401「密码错误，还可尝试 N 次」，而且**每次都在消耗失败次数**，
    5 次之后账号还会被临时锁定（第 137 批实测：把用户停用后，他用正确密码登录，
    看到的是"密码错误，还可尝试 4 次"）。这条分支留着做兜底，但主路径在下面提前拦。

    两种"不可用"要分开说，因为用户该做的事完全不同：
      · **注销冷静期**（`has_pending_deletion`）→ 告诉他可以点「取消注销」自助恢复；
      · **被管理员停用** → 告诉他没有自助入口，需要联系管理员。
    """
    if user.has_pending_deletion:
        return Response({
            'status': 'error',
            'message': (
                f'该账号已申请注销，正在 {user.deletion_grace_days()} 天冷静期内'
                # ⚠️ `deletion_days_left` 是 **property**，不能加括号 ——
                #    写成 `deletion_days_left()` 会得到
                #    `TypeError: 'int' object is not callable`（实测：登录直接 500，
                #    而视图的 except 把它包成"服务器内部错误"，堆栈只在日志里）
                f'（还剩 {user.deletion_days_left} 天）。'
                '如需继续使用，请点击「取消注销」并输入密码。'
            ),
            'code': 'account_pending_deletion',
            'can_cancel': True,
            'days_left': user.deletion_days_left,
            'scheduled_for': user.deletion_scheduled_for,
        }, status=status.HTTP_403_FORBIDDEN)

    return Response({
        'status': 'error',
        'message': '账户已被停用，请联系管理员',
        'code': 'account_disabled',
    }, status=status.HTTP_403_FORBIDDEN)


class LoginView(APIView):
    """
    用户登录API视图
    - 允许任何用户访问
    - 使用用户名和密码进行认证
    - 返回token和用户信息
    - 第 35 批：加入**登录失败锁定**与**限流**（此前可无限次猜密码）
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.LoginSerializer
    # 第 35 批：按 IP 限流（scope 见 settings.REST_FRAMEWORK.DEFAULT_THROTTLE_RATES）。
    # 注意：以前项目里挂了 UserRateThrottle 但**没配速率**，DRF 会因 rate=None 直接放行，
    # 等于没有防刷；这里连同 settings 一起补上。
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    #: 连续失败多少次后锁定
    MAX_LOGIN_ATTEMPTS = 5
    #: 锁定时长（分钟）
    LOCK_MINUTES = 15

    def post(self, request):
        # 先单独解析请求体。
        # 请求体不是合法 JSON 时 DRF 会抛 ParseError，这属于**客户端错误**。
        # 原来 request.data 直接在下面的 try 里访问，ParseError 被 except Exception 吞掉，
        # 于是畸形 JSON 也返回 500，并把 "JSON parse error ..." 这类内部信息原样回给客户端。
        try:
            data = request.data
        except ParseError:
            return Response({
                'status': 'error',
                'message': '请求体格式错误：应为合法的 JSON',
                'code': 'invalid_payload'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(data, dict):
            return Response({
                'status': 'error',
                'message': '请求体格式错误：应为 JSON 对象',
                'code': 'invalid_payload'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 手动获取用户名和密码
            username = data.get('username')
            password = data.get('password')

            if not username or not password:
                return Response({
                    'status': 'error',
                    'message': '用户名和密码不能为空'
                }, status=status.HTTP_400_BAD_REQUEST)

            # 第 35 批：登录前先看账号是否处于锁定期
            UserModel = get_user_model()
            existing_user = UserModel.objects.filter(username=username).first()

            # 第 95 批：已注销的账号给出明确说明。
            # 注销时用户名被改成 `deleted_<id>` 并清空密码，所以**按原用户名找不到人**，
            # 用户看到的会是"用户名或密码错误"—— 他会以为是自己记错了，反复重试。
            # 这里对"看起来像已注销账号"的情况给一句人话：
            if existing_user and getattr(existing_user, 'is_deleted', False):
                return Response({
                    'status': 'error',
                    'message': '该账号已注销，无法登录。如需继续使用，请重新注册。',
                    'code': 'account_deleted',
                }, status=status.HTTP_403_FORBIDDEN)

            # 第 101 批：**冷静期**内的账号 —— 密码可能仍然正确，但账号已停用。
            # 这里必须给出与"密码错"不同的引导：否则用户会以为是自己密码记错了，
            # 而实际上只要点一下"取消注销"就能恢复。这是冷静期能真正被用上的关键一步。
            # ⚠️ 校验密码**之后**才走这条分支（下面 authenticate 成功但被拒的情形），
            #    顺序见 `if user is not None` 那一段 —— 这里只处理"锁定期"之类的提前返回。
            if existing_user and existing_user.is_locked:
                remaining = existing_user.lock_remaining_seconds
                minutes = max(1, remaining // 60)
                return Response({
                    'status': 'error',
                    'message': f'登录失败次数过多，账号已被锁定，请 {minutes} 分钟后再试',
                    'code': 'account_locked',
                    'retry_after_seconds': remaining,
                }, status=status.HTTP_423_LOCKED)

            # 第 101 批：**注销冷静期**的账号要在这里拦，不能等 authenticate。
            #
            # ⚠️ 实测踩过：Django 的 ModelBackend 对 `is_active=False` 的用户**直接返回 None**
            #    （user_can_authenticate 检查），所以下面 `if not user.is_active` 那段
            #    **永远走不到** —— 冷静期用户拿到的是 401「密码错误」，而他的密码其实是对的。
            #    用户会以为密码记错了，而实际上点一下"取消注销"就能恢复。
            #    所以这里提前判断，并用 `check_password` 自己验密码（验过了才告知，
            #    避免"知道用户名就能探测该账号是否在冷静期"）。
            #
            # 第 142 批：条件从 `has_pending_deletion` **放宽到 `not is_active`** ——
            #    同一个坑还有另一半：**被管理员停用**的账号（没有冷静期）此前也走不到
            #    那条专门的提示，用户看到的是"密码错误，还可尝试 N 次"，还会**白白消耗失败次数**。
            #    现在两种"账号不可用"都在这里拦，并按原因给不同说法（见 _inactive_login_response）。
            if existing_user and not existing_user.is_active:
                if existing_user.check_password(password):
                    return _inactive_login_response(existing_user)
                # 密码不对：与普通失败一视同仁（累加失败次数）
                just_locked, remaining = existing_user.register_failed_login(
                    max_attempts=self.MAX_LOGIN_ATTEMPTS,
                    lock_minutes=self.LOCK_MINUTES,
                )
                if just_locked:
                    return Response({
                        'status': 'error',
                        'message': f'密码错误次数过多，账号已锁定 {self.LOCK_MINUTES} 分钟',
                        'code': 'account_locked',
                        'retry_after_seconds': self.LOCK_MINUTES * 60,
                    }, status=status.HTTP_423_LOCKED)
                return Response({
                    'status': 'error',
                    'message': f'密码错误，还可尝试 {remaining} 次',
                    'code': 'invalid_password',
                    'remaining_attempts': remaining,
                }, status=status.HTTP_401_UNAUTHORIZED)

            # 验证用户凭证
            user = authenticate(request, username=username, password=password)

            if user is None:
                # 第 35 批：失败次数累加；达到阈值直接锁定
                if existing_user is not None:
                    just_locked, remaining = existing_user.register_failed_login(
                        max_attempts=self.MAX_LOGIN_ATTEMPTS,
                        lock_minutes=self.LOCK_MINUTES,
                    )
                    if just_locked:
                        logger.warning('账号因连续登录失败被锁定: username=%s', username)
                        return Response({
                            'status': 'error',
                            'message': f'密码错误次数过多，账号已锁定 {self.LOCK_MINUTES} 分钟',
                            'code': 'account_locked',
                            'retry_after_seconds': self.LOCK_MINUTES * 60,
                        }, status=status.HTTP_423_LOCKED)

                    return Response({
                        'status': 'error',
                        'message': f'密码错误，还可尝试 {remaining} 次',
                        'code': 'invalid_password',
                        'remaining_attempts': remaining,
                    }, status=status.HTTP_401_UNAUTHORIZED)

                # 用户不存在：不累加计数（没有账号可锁），但同样给统一口径的提示
                return Response({
                    'status': 'error',
                    'message': '用户名或密码错误',
                    'code': 'user_not_found'
                }, status=status.HTTP_404_NOT_FOUND)

            if not user.is_active:
                # 第 142 批：这里现在只是**兜底**（主路径已在 authenticate 之前拦下，
                # 见上面那段注释与 `_inactive_login_response`）。留着是因为认证后端将来
                # 若换成"允许停用用户通过认证"的实现，这道判断还能接住。
                return _inactive_login_response(user)

            # 第 35 批：登录成功 → 清零失败计数与锁定状态
            user.reset_login_failures()

            # 第 42 批：每日首次登录 +1 积分
            try:
                from .services_points import award_daily_login
                award_daily_login(user)
            except Exception:
                logger.exception('每日登录积分失败 user=%s', user.id)

            # 登录用户（用于会话认证）
            login(request, user)

            # 第 94 批：**登录一律换一张新 Token**（原来是 get_or_create 复用旧的）。
            #
            # 为什么必须换：Token 现在真的会过期（见 api/middleware.py）。若沿用
            # `get_or_create`，一个"过期但还没被用过"的 Token 会被原样返回 ——
            # 用户刚输对密码，拿到的却是一张已经失效的凭证（实测就是这么复现的）。
            # 顺带两个安全好处：登录即轮换，旧凭证立即失效；多设备不会共用同一张。
            Token.objects.filter(user=user).delete()
            token = Token.objects.create(user=user)

            # 返回用户信息和token
            response_data = {
                'status': 'success',
                'message': '登录成功',
                'data': {
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'is_staff': user.is_staff,
                        'is_superuser': user.is_superuser,
                        # 第 23 批：带上头像地址，否则顶栏要等用户进过一次资料页才有头像
                        'avatar': serializers._user_avatar_url(user, request),
                        # 第 17 批修复：这里原先**不返回 role**，而前端多处管理员判定
                        # （路由守卫 `user.role === 'ADMIN' || user.is_staff`、
                        # HistoryView / DiseaseStatistics 的 all_users 开关、
                        # PestEncyclopediaView / PestDetailView 的新增编辑按钮、
                        # stores/auth.js 的 isAdmin）都依赖 `user.role`；
                        # 而 stores/auth.js 的 checkAuth() 只从 localStorage 读取用户、
                        # **不会调用 /api/check-auth/ 刷新**，所以 role 永远是 undefined
                        # → 这些 role 分支全部是死代码（role=ADMIN 但 is_staff=False 的
                        # 账号会被前端当成普通用户，甚至被路由守卫挡在管理页之外，
                        # 而后端其实是允许的）。
                        # role 本身不是敏感信息（/api/users/{id}/ 与 check-auth 都已公开返回）。
                        'role': getattr(user, 'role', 'USER'),
                        # 第 124 批：能力清单（键名与 /api/check-auth/ 一致）。
                        # 前端 `stores/auth.js` 用它决定"能不能进管理后台、菜单显示哪几项"，
                        # 而不是自己拿 is_staff/role 推 —— 口径只有后端一份（capabilities.py）。
                        'capabilities': capabilities_of(user),
                        # 第 128 批：内容模块（"内容审核/新闻管理/病害百科/意见反馈"里
                        # 这个人被授权了哪几块）
                        'content_modules': content_modules_of(user),
                    },
                    'token': token.key
                }
            }
            # 安全提示：原代码这里是 print('Login response data:', response_data)，
            # 会把**包含 token 的完整登录响应**写进控制台/日志，任何能看日志的人都拿到凭证。
            # 现改为只记录不含敏感信息的用户标识。
            logger.debug("登录成功: user_id=%s, username=%s", user.id, user.username)
            return Response(response_data)

        except Exception:
            # 未预期的错误：记完整堆栈到日志，但**不要把内部错误原文返回给客户端**
            # （原来返回 str(e)，等于把内部实现细节泄露出去）。
            logger.exception("登录接口发生未预期的错误")
            return Response({
                'status': 'error',
                'message': '服务器内部错误，请稍后重试',
                'code': 'server_error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DetectView(APIView):
    """
    病害检测API视图
    - 接收上传的图片进行病害检测
    - 返回检测结果和置信度
    """
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        # 检查是否有文件被上传
        if 'image' not in request.FILES:
            return Response(
                {'error': '未检测到图片文件'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 获取上传的图片
            image_file = request.FILES['image']

            # ⚠️ 第 214 批：**用户选定的作物**（可选）。
            #    识别页新增了一个作物下拉 —— 此前系统完全靠类名自己推断作物
            #    （`pest_lookup._crop_of`），而实测 380 张真实图片有 **2.5% 把作物认错**
            #    （`Potato___Late_blight` → `Tomato___Late_blight` conf=0.998，同科混淆）。
            #    用户先选作物，等于把这条信息从"猜"变成"已知"。
            #
            #    ⚠️ 必须做**白名单校验**，不能把用户字符串直接带进匹配：
            #    一是别让它成为查询注入面，二是避免把"不存在的作物"传下去、
            #    让用户看到一条莫名其妙的"库里没有该作物"。
            crop_hint = (request.data.get('crop_type') or '').strip()
            if crop_hint:
                known_crops = set(
                    PestInfo.objects.exclude(crop_type='')
                    .values_list('crop_type', flat=True).distinct()
                )
                if crop_hint not in known_crops:
                    logger.warning('[detect] 收到未知作物 %r，忽略该约束', crop_hint)
                    crop_hint = ''

            #: ⚠️ 必须在这里初始化：它只在"作物不匹配"分支里被赋值，
            #: 若只在分支内赋值，正常路径走到构建响应时会 `UnboundLocalError`。
            crop_mismatch = None

            # 生成唯一的文件名
            file_ext = os.path.splitext(image_file.name)[1]
            file_name = f"{uuid.uuid4().hex}{file_ext}"

            # 确保上传目录存在
            upload_dir = os.path.join(settings.MEDIA_ROOT, 'detection_uploads')
            os.makedirs(upload_dir, exist_ok=True)

            # 保存上传的图片
            file_path = os.path.join('detection_uploads', file_name)
            full_path = os.path.join(settings.MEDIA_ROOT, file_path)

            # 保存文件
            with open(full_path, 'wb+') as destination:
                for chunk in image_file.chunks():
                    destination.write(chunk)

            # 确保文件保存成功
            if not os.path.exists(full_path):
                raise Exception('文件保存失败')

            # 调用AI服务进行检测
            ai_service = get_ai_service()
            if not ai_service or not ai_service.model:
                # 第 74 批：错误文案面向农户。技术细节（服务未初始化）只进日志，
                # 不返回给用户；同时保留 503 让前端能区分"服务不可用"与"图片问题"。
                logger.error('[detect] AI 服务未初始化，无法识别')
                return Response(
                    {'error': '识别服务暂时不可用，请稍后重试', 'retryable': True},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            try:
                # ⚠️ 第 106 批：删掉了这里的**重复写盘**。
                #
                # 原来第 704-706 行已经把上传内容写到 `full_path` 了，这里又写了一遍
                # 一模一样的内容（同一个路径、同一个迭代器）。两个后果：
                #   1. 每张图片被写两次，白耗一次磁盘 I/O；
                #   2. 更麻烦的是**读的人无法判断哪一遍是必需的** ——
                #      注释写"保存文件到临时位置供AI模型使用"，可上面那句已经做了，
                #      于是谁也不敢删，就这么留了两批。
                #
                # 删它的依据：两个写入点之间只有"AI 服务是否初始化"的判断
                # （不通过就直接 return），没有任何删除/移动文件的操作，
                # 所以到这里时 `full_path` 必定已存在（上面还有显式的 exists 检查）。
                #
                # 使用AI模型进行预测
                with open(full_path, 'rb') as img_file:
                    from django.core.files.uploadedfile import InMemoryUploadedFile
                    from io import BytesIO

                    # 创建一个InMemoryUploadedFile对象
                    img_data = img_file.read()
                    img_io = BytesIO(img_data)
                    img_file = InMemoryUploadedFile(
                        file=img_io,
                        field_name='image',
                        name=file_name,
                        content_type=image_file.content_type,
                        size=len(img_data),
                        charset=None
                    )

                    # 调用AI服务进行预测
                    prediction = ai_service.predict(img_file)

                    if prediction['status'] == 'error':
                        return Response(
                            {'error': f'AI模型预测失败: {prediction.get("message", "未知错误")}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )

                    # 从预测结果中获取病害信息
                    disease_identifier = prediction.get('identifier', '').strip()
                    confidence = prediction.get('confidence', 0)

                    # 添加调试日志
                    logger.info(f'AI模型返回的病害标识符: {disease_identifier}')

                    # 从数据库获取病害详情
                    #
                    # ⚠️ 第 159 批：这里的匹配**以前只有一条"去掉空格后精确相等"**，
                    # 而当前模型给的是 PlantVillage 风格类名（`Apple___Apple_scab`），
                    # 库里存的是 `apple_scab` —— 于是永远匹配不上：
                    # 界面显示英文类名（`Apple   Apple Scab`）、主要症状与防治建议只剩占位文字，
                    # 而**管理后台里明明有内容**（用户就是这样报上来的）。
                    # 现在统一走 `pest_lookup.find_pest_info`（含"包含于类名"等四层规则），
                    # 并且与落库时用的是**同一个**函数。
                    from .pest_lookup import find_pest_info

                    pest_info, match_note = find_pest_info(disease_identifier, crop_hint=crop_hint)
                    if pest_info:
                        logger.info(f'病害词条匹配成功：{pest_info.name}（{match_note}）')
                        disease_name = pest_info.name
                        description = pest_info.symptoms
                        prevention = "\n".join([m.measure for m in pest_info.prevention_methods.all()])
                        # 第 72 批：同时返回英文内容，英文界面下不再回落到中文
                        disease_name_en = pest_info.name_en or ''
                        description_en = pest_info.symptoms_en or ''
                        prevention_en = "\n".join(
                            [m.measure_en or m.measure for m in pest_info.prevention_methods.all()]
                        )
                        logger.info(f'获取到防治方法: {prevention}')
                    else:
                        # 匹配不上时的回落 —— **必须留痕**，否则又是"后台有内容、界面却没有"
                        logger.warning(
                            f'病害词条匹配失败：类名 {disease_identifier!r}（{match_note}）—— '
                            f'界面将显示英文类名与占位建议。'
                            f'请在病害百科里补一条 english_identifier={disease_identifier!r} 的词条'
                            f'（或把它加进 api/pest_lookup.py 的 ALIASES）'
                        )
                        disease_name = disease_identifier.replace('_', ' ').title()
                        description = '暂无详细描述'
                        prevention = '请咨询农业专家获取防治建议'
                        disease_name_en = disease_name
                        #: ⚠️ 英文侧不能留空：界面按 `description_en` 取值，
                        #: 空串会让英文界面下的"症状描述"整块空白（第 213 批补）。
                        description_en = 'No detailed description yet'
                        prevention_en = 'Please consult a local agricultural expert for advice'

                    # ⚠️ 第 213 批：**健康叶片要特判，不能走上面的通用回落**。
                    #    模型零检出时返回 `identifier='healthy_plant'`，而库里没有这个
                    #    `english_identifier` → 走回落 → `'healthy_plant'.title()` = **"Healthy Plant"**。
                    #    于是健康叶页面上同时出现：中文绿条「未检测到病害，叶片大概率健康」
                    #    ＋「病害信息」卡里的英文 "Healthy Plant" ＋ "暂无详细描述"。
                    #    （第 144 行的绿条早就中文化了，卡片这处一直漏着 —— 用户看到的是后者。）
                    #
                    #    英文界面下走 `disease_name_en`，中文界面走 `disease_name`；
                    #    描述与建议也换成人话，不要让它看起来像"词条缺失"。
                    if disease_identifier == 'healthy_plant':
                        disease_name = '未检测到明显病斑，植株看起来健康'
                        disease_name_en = 'No obvious lesions detected — the plant looks healthy'
                        description = '模型未在图片中检出病害特征。可继续观察，注意通风与合理水肥。'
                        description_en = ('The model found no disease features in this image. '
                                          'Keep monitoring; maintain ventilation and balanced irrigation.')
                        prevention = '无需用药。保持合理密植、及时通风降湿，发现异常叶片再复查。'
                        prevention_en = ('No treatment needed. Keep sensible spacing and ventilation; '
                                         're-check if abnormal leaves appear.')

                    # 保存带标注的图片
                    annotated_image_path = None
                    if prediction.get('annotated_image'):
                        try:
                            # 从base64数据中提取图片数据
                            import base64

                            # 移除base64前缀
                            if 'base64,' in prediction['annotated_image']:
                                img_data = prediction['annotated_image'].split('base64,')[1]
                            else:
                                img_data = prediction['annotated_image']

                            # 解码base64数据
                            img_data = base64.b64decode(img_data)

                            # 生成带标注的图片文件名
                            annotated_file_name = f"annotated_{file_name}"
                            annotated_file_path = os.path.join('detection_uploads', annotated_file_name)
                            full_annotated_path = os.path.join(settings.MEDIA_ROOT, annotated_file_path)

                            # 确保目录存在
                            os.makedirs(os.path.dirname(full_annotated_path), exist_ok=True)

                            # 保存带标注的图片
                            with open(full_annotated_path, 'wb') as f:
                                f.write(img_data)

                            annotated_image_path = annotated_file_path

                        except Exception as e:
                            logger.error(f'保存带标注图片失败: {str(e)}')
                            annotated_image_path = file_path  # 如果保存失败，使用原始图片

                    # ⚠️ 第 214 批：**作物不匹配要明确说出来**，不能让它悄悄变成
                    #    "病名是一串英文类名"（实测选"葡萄"、图是苹果病时，
                    #    用户看到的就是 `Apple   Apple Scab`，完全不知道发生了什么）。
                    #    这里保留模型自己的判断 + 回传机器推断的作物，
                    #    前端据此显示"你选的是葡萄，但识别结果指向苹果（苹果黑星病）"，
                    #    用户立刻知道该改哪个 —— 比一个看似合理的跨作物答案安全。
                    if crop_hint and pest_info is None and '没有匹配' in match_note:
                        model_crop = ''
                        try:
                            from .pest_lookup import _crop_of, _crop_set
                            _rows = list(PestInfo.objects.all())
                            model_crop = _crop_of(
                                disease_identifier.replace('___', '_').lower().replace(',', ''),
                                _crop_set(_rows))
                        except Exception:  # noqa: BLE001 —— 推断失败不影响主流程
                            model_crop = ''
                        #: 机器推断的作物 → 中文名（用于提示文案）
                        crop_name_by_prefix = {
                            (p.english_identifier or '').split('_')[0]: p.crop_type
                            for p in PestInfo.objects.exclude(crop_type='')
                        }
                        crop_mismatch = {
                            'selected': crop_hint,
                            'detected_crop': crop_name_by_prefix.get(model_crop, ''),
                        }
                        logger.info(
                            '[detect] 作物约束不匹配：用户选 %r，模型指向 %r（%s）',
                            crop_hint, model_crop, disease_identifier)

                    # 构建返回结果
                    detection_result = {
                        'disease': disease_name,
                        'disease_en': disease_name_en,
                        # 第 194 批：把模型输出的类名标识也带上。
                        # 前端"追问助手"要靠它把该病害在知识库里直接置顶
                        # （`assistant/retriever.py` 的"识别结果直连"）。
                        # 此前响应里没有这个字段，于是用户问"这个病打什么药"时
                        # 检索匹配不到任何词条，助手永远答"词条未收录"。
                        'identifier': disease_identifier,
                        'confidence': confidence,
                        'description': description,
                        'description_en': description_en,
                        'prevention': prevention,
                        'prevention_en': prevention_en,
                        'original_image': request.build_absolute_uri(settings.MEDIA_URL + file_path),
                        'annotated_image': request.build_absolute_uri(
                            settings.MEDIA_URL + (annotated_image_path or file_path)),
                        'bbox': prediction.get('bbox', []),  # 边界框信息
                        # 第 214 批：回传**实际生效的作物约束**。
                        # 前端据此说明"按你选的苹果匹配"，也让"用户选了但被忽略"
                        # （未知作物）这种情况可被发现，而不是静默降级。
                        'crop_hint': crop_hint,
                        'crop_mismatch': crop_mismatch,
                    }

            except Exception as e:
                logger.error(f'AI模型检测失败: {str(e)}', exc_info=True)
                # 第 74 批：原来把 Python 异常原文（e）直接返回给用户，
                # 界面会出现「病害检测失败: 'NoneType' object has no attribute ...」
                # 这类技术报错。技术原因只进日志，用户只看到可行动的那句话。
                return Response(
                    {'error': '图片看不太清，请重新拍一张试试', 'retryable': True},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # 保存检测历史记录
            try:
                # 尝试获取对应的病害信息
                #
                # 第 159 批：这一段原来自己又写了一遍匹配（与上面构建结果的逻辑**不一致**），
                # 现在统一走 `pest_lookup.link_history` —— 同一个函数，不会再打架。
                from .pest_lookup import link_history

                history = DetectionHistory.objects.create(
                    user=request.user,
                    image=file_path,
                    # ⚠️ 第 106 批：**这个字段以前从来没被写入过**。
                    #
                    # `DetectionHistory.annotated_image` 一直在模型里（`detection_history/annotated/`），
                    # 但识别接口只存了 `image` —— 而它在上面又把标注图写到了
                    # `detection_uploads/annotated_<uuid>.JPG`。两个后果：
                    #   1. 标注图**没有任何数据库引用**，于是永远没人清理
                    #      （第 104 批审计发现 media 里 12.9 MB 无引用文件，这是主因之一）；
                    #   2. 前端要拿标注图只能靠接口实时拼 URL（`request.build_absolute_uri`），
                    #      一旦图片路径规则变了，历史记录里的老图就再也显示不出来。
                    #
                    # 现在把落盘路径一并记进库：文件**可追溯**，
                    # `manage.py prune_media` 也能据此判断哪些是垃圾。
                    annotated_image=annotated_image_path,
                    detection_result=detection_result['disease'],
                    confidence=detection_result['confidence'],
                )
                # 第 159 批：关联病害词条改为"落库之后按同一个匹配函数补上"，
                # 这样历史记录与界面显示的结果**必然一致**（以前两处各算一次，可能一个有一个没有）。
                pest_info, match_note = link_history(history, disease_identifier, crop_hint=crop_hint)
                logger.info(
                    f'成功保存检测历史记录 #{history.id}，关联病害：'
                    f'{pest_info.name if pest_info else "无"}（{match_note}）'
                )
            except Exception as e:
                logger.error(f'保存检测历史记录失败: {str(e)}')
                # 即使保存历史记录失败，也继续返回检测结果
                history = None

            # 返回检测结果
            # 注意：保存历史失败时 history 为 None，原代码直接取 history.id → AttributeError，
            # 被外层 except 变成 500 —— 与上面注释里"即使保存失败也继续返回检测结果"的意图相反。
            return Response({
                'status': 'success',
                'data': {
                    'detection': detection_result,
                    'history_id': history.id if history else None
                }
            })

        except Exception as e:
            return Response(
                {'error': f'检测过程中发生错误: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PestDetailView(RetrieveAPIView):
    """
    病害详情视图
    - 根据英文标识符获取病害详情
    - 所有用户可访问
    """
    queryset = PestInfo.objects.all()
    serializer_class = PestInfoDetailSerializer
    lookup_field = 'english_identifier'
    lookup_url_kwarg = 'english_identifier'
    permission_classes = [permissions.AllowAny]


class PreventionDataView(APIView):
    """
    获取病害预防措施数据
    - 支持按病害ID或英文标识符查询
    - 支持搜索和分类筛选
    - 返回病害的预防措施信息
    """
    permission_classes = [permissions.AllowAny]

    #: 防治类别的英文名（第 78 批）。
    #: 中文名来自模型 choices 的 `get_category_display()`，英文名没有对应的字段，
    #: 而它是**固定枚举**（不是用户输入），所以直接在这里给出对照，与前端
    #: `common.prevent.*` 文案保持一致；新增类别时两处一起补。
    CATEGORY_LABELS_EN = {
        'AGRICULTURAL': 'Cultural control',
        'CHEMICAL': 'Chemical control',
        'ECOLOGICAL': 'Ecological control',
        'PHYSICAL': 'Physical control',
        'MONITORING': 'Monitoring',
    }

    def get(self, request, format=None):
        try:
            # 获取查询参数
            pest_id = request.query_params.get('pest_id')
            english_identifier = request.query_params.get('english_identifier')
            search = request.query_params.get('search', '').strip()
            category = request.query_params.get('category', '').strip()
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 100))  # 默认每页100条，确保能获取所有数据

            # 构建基础查询
            query = Q()
            if pest_id:
                query &= Q(pest_id=pest_id)
            elif english_identifier:
                pest = PestInfo.objects.get(english_identifier=english_identifier)
                query &= Q(pest=pest)

            # 添加搜索条件
            if search:
                # 先查找匹配的病害
                # 注意：PestInfo 没有 english_name 字段（只有 name 与 english_identifier），
                # 原来这里写 Q(english_name__icontains=...) 会抛 FieldError，
                # 导致「带 search 参数」的请求必定失败。
                # 第 78 批：英文界面下的搜索词也要能命中英文病害名与英文措施。
                matched_pests = PestInfo.objects.filter(
                    Q(name__icontains=search) |
                    Q(name_en__icontains=search) |
                    Q(english_identifier__icontains=search)
                ).values_list('id', flat=True)

                # 查找匹配的病害ID或措施中包含搜索词的记录
                query &= (
                        Q(measure__icontains=search) |
                        Q(measure_en__icontains=search) |
                        Q(pest__in=matched_pests)
                )

            # 添加类别筛选
            # 第 78 批：接受语言无关的类别 code（AGRICULTURAL…），同时兼容旧前端传中文类别名。
            # 此前前端传的是 'AG'/'CH' 这类两字母缩写，后端直接拿去匹配 code → 永远筛不到东西。
            if category:
                category_choices = dict(PreventionMethod.CATEGORY_CHOICES)
                by_code = {code.lower(): code for code in category_choices}
                by_display = {label: code for code, label in category_choices.items()}
                resolved = by_code.get(category.lower()) or by_display.get(category)
                if resolved:
                    query &= Q(category=resolved)
                else:
                    # 不认识的参数：返回空结果，而不是把整库倒出去（避免"筛选看起来没生效"）
                    query &= Q(category='__none__')

            # 获取所有符合条件的记录（不限制数量）
            prevention_methods = PreventionMethod.objects.filter(query).select_related('pest').order_by('id')

            # 应用分页
            paginator = Paginator(prevention_methods, page_size)
            try:
                page_obj = paginator.page(page)
            except PageNotAnInteger:
                page_obj = paginator.page(1)
            except EmptyPage:
                page_obj = paginator.page(paginator.num_pages)

            # 按类别分组
            # 第 78 批：分组键从**中文类别名**改成语言无关的 `category` code。
            # 原来用中文 display 当键，前端在英文界面下既没法显示英文类别名，
            # 也没法按类别筛选（两字母缩写 'AG' 与中文键对不上，筛选一直是坏的）。
            categories = {}
            for method in page_obj.object_list:
                category_name = method.get_category_display()
                categories.setdefault(method.category, []).append({
                    'id': method.id,
                    'measure': method.measure,
                    'measure_en': method.measure_en or '',
                    'pest_id': method.pest_id,
                    'pest_name': method.pest.name if method.pest else '未知',
                    'pest_name_en': method.pest.name_en if method.pest else '',
                    'category': method.category,
                    'category_display': category_name,
                    'category_display_en': self.CATEGORY_LABELS_EN.get(method.category, category_name),
                })

            return Response({
                'status': 'success',
                'data': categories,
                'pagination': {
                    'total': paginator.count,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': paginator.num_pages,
                    'has_next': page_obj.has_next(),
                    'has_previous': page_obj.has_previous()
                }
            })

        except PestInfo.DoesNotExist:
            return Response(
                {'error': '未找到指定的病害信息'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f'获取预防措施数据失败: {str(e)}')
            return Response(
                {'error': f'获取预防措施数据失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


def _parse_bulk_ids(request):
    """
    解析批量操作里的 `ids`（第 138 批抽出：批量改状态与批量删除**共用**）

    第 147 批：实现挪到了 `api/bulk.py`（帖子那边的批量删除要用**同一套**校验），
    这里保留成薄壳 —— 调用点与既有测试都不用改。
    "批量接口各自写一套更松的校验"是这类漏洞最常见的形态，所以只留一份。

    返回 `(ids, error_response)`：成功时 error_response 为 None；失败时 ids 为 None。
    """
    ids, error = parse_ids(request.data.get('ids'), label='反馈')
    return (None, error) if error else (ids, None)


class FeedbackView(viewsets.ModelViewSet):
    """
    用户反馈API视图（第 26 批扩展为通用「意见反馈」）
    - 用户可以提交反馈、查看**自己**的反馈、撤回（删除）自己的反馈
    - 管理员可以查看所有反馈，并在后台流转处理状态 / 填写回复
    - 支持按类型、处理状态、识别是否正确、病害名称筛选
    """
    serializer_class = serializers.FeedbackSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        """
        反馈列表

        注意：时间字段是 `timestamp`（不是 created_at），排序/筛选必须用真实字段 ——
        历史上这里曾按不存在的字段过滤，导致列表与删除接口 500。
        """
        user = self.request.user
        queryset = Feedback.objects.select_related('user')

        # 普通用户只能看到自己的反馈
        # 第 128 批：反馈列表按 feedback 模块收口（勾了新闻的人不该看到全部反馈）
        if not has_content_module(user, MODULE_FEEDBACK):
            queryset = queryset.filter(user=user)

        # 支持按"识别是否正确"筛选（识别结果反馈用）
        is_correct = self.request.query_params.get('is_correct', None)
        if is_correct not in (None, ''):
            queryset = queryset.filter(is_correct=str(is_correct).lower() in ('true', '1', 'yes'))

        # 支持按病害名称搜索
        disease_name = self.request.query_params.get('disease_name', None)
        if disease_name:
            queryset = queryset.filter(disease_name__icontains=disease_name)

        # 第 26 批：反馈类型 / 处理状态（意见反馈页与后台都用得上）
        category = (self.request.query_params.get('category') or '').strip()
        if category:
            queryset = queryset.filter(category=category)

        status_param = (self.request.query_params.get('status') or '').strip()
        if status_param:
            queryset = queryset.filter(status=status_param)

        # 第 27 批：关键字搜索（管理端"反馈管理"按提交人或内容查）
        search = (self.request.query_params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(
                Q(user__username__icontains=search) |
                Q(suggestion__icontains=search) |
                Q(disease_name__icontains=search) |
                Q(admin_reply__icontains=search)
            )

        # 管理员可按提交人筛选
        user_id = (self.request.query_params.get('user') or '').strip()
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        return queryset.order_by('-timestamp')

    def get_permissions(self):
        """
        设置权限：
        - 普通用户：查看（仅自己的）/ 创建 / 撤回（删除）自己的
        - 内容维护者（CONTENT）：查看全部 / 回复 / 批量流转
        - 删除**别人的**反馈：仅全权管理员（见下面的 destroy 守卫）

        说明：删除不再强制管理员 —— `get_queryset` 对普通用户只返回自己的记录，
        所以 `destroy` 别人 id 时自然 404，允许用户"撤回"自己的反馈是安全的。

        ⚠️ 第 124 批补充（产品决策 #3）：**信息编辑员（EDITOR）可以看、可以回复，
        但不能删除别人的反馈** —— 这是一条**新增**的护栏，因为在此之前
        "能不能删别人的反馈"完全由 `get_queryset` 的范围决定：
        管理员能看到全部反馈，于是顺带就能删任何人的。第 125 批 EDITOR 一旦拿到
        "看全部反馈"，就会连"删任何人的反馈"一起拿到，所以必须在 destroy 上显式收紧。
        """
        if self.action in ['list', 'retrieve', 'create', 'destroy']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [IsFeedbackEditor]  # 第 128 批：feedback 模块（原为笼统的 CONTENT）
        return [permission() for permission in permission_classes]

    def destroy(self, request, *args, **kwargs):
        """
        删除反馈

        · 自己的反馈：随时可撤回（任何人）
        · **别人的**反馈：只有全权管理员（`is_full_admin`）可以删

        为什么单独写一个 destroy：见 `get_permissions` 的说明 —— 原来的约束全靠
        queryset 范围，对"能看到全部反馈的人"等于没有约束。这里把两种情形分开判断，
        让"撤回自己的"和"删别人的"即使都能走到同一个对象，也有不同门槛。
        """
        instance = self.get_object()
        if instance.user_id != request.user.id and not is_full_admin(request.user):
            return Response(
                {'detail': '只有管理员可以删除其他用户的反馈'},
                status=status.HTTP_403_FORBIDDEN,
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_create(self, serializer):
        # 第 38 批：反馈内容也过一遍敏感词（含"识别纠错"里带过来的文本）
        from .sensitive import check_text
        check_text(
            serializer.validated_data.get('suggestion'),
            serializer.validated_data.get('admin_reply'),
            field_label='反馈内容',
        )

        # 第 91 批：关联了识别记录时，把"当时的结论与置信度"顺手补进反馈。
        # 这样即使前端某天忘了传 disease_name / confidence，后台也查得到上下文；
        # 前端**已经传了**的值优先（它可能带了语言相关的展示名）。
        detection = serializer.validated_data.get('detection')
        extra = {}
        if detection is not None:
            if not (serializer.validated_data.get('disease_name') or '').strip():
                extra['disease_name'] = detection.detection_result or ''
            if serializer.validated_data.get('confidence') is None:
                extra['confidence'] = detection.confidence

        # 自动设置当前用户为反馈提交者
        serializer.save(user=self.request.user, **extra)

    @action(detail=False, methods=['post'], url_path='bulk-status',
            permission_classes=[IsFeedbackEditor])
    def bulk_status(self, request):
        """
        批量流转处理状态（第 100 批，仅管理员）

            POST /api/feedback/bulk-status/
            body: {"ids": [1,2,3], "status": "processing" | "resolved" | "pending",
                   "admin_reply": "可选，填了就一起写进去"}

        为什么需要：意见反馈列表按状态筛选后，"这批都是同一类问题、一起标记为已处理"
        是最常见的操作。逐条点开弹窗、选状态、保存 —— 10 条就是 10 轮。

        约束（都是有意的）：
          · **只允许 pending / processing / resolved**（用 Feedback.STATUS_CHOICES 校验），
            避免前端传什么就写什么；
          · 流转到 `resolved` 时**必须**有回复内容（与单条 reply 的规则一致）——
            否则"已处理"会变成一句没有交代的状态变更。批量时要么统一带上回复，
            要么只允许流转到 processing。
          · 逐条处理不整体失败，响应里给每条的成败（同帖子批量审核的理由）。
          · 一次最多 200 条。
        """
        status_value = (request.data.get('status') or '').strip()
        valid_status = {choice[0] for choice in Feedback.STATUS_CHOICES}
        if status_value not in valid_status:
            return Response({'status': [f'状态只能是 {sorted(valid_status)} 之一']},
                            status=status.HTTP_400_BAD_REQUEST)

        admin_reply = request.data.get('admin_reply')
        if status_value == 'resolved' and not (admin_reply or '').strip():
            return Response(
                {'admin_reply': ['批量标记为「已处理」时必须填写回复内容']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ids, error = _parse_bulk_ids(request)
        if error:
            return error

        # 只能操作**自己有权看到**的反馈：管理员的 queryset 是全量，但复用 get_queryset
        # 更安全 —— 万一将来权限口径改了，这里自动跟着变。
        feedbacks = {f.id: f for f in self.get_queryset().filter(id__in=ids)}

        results = []
        ok_count = 0
        for feedback_id in ids:
            feedback = feedbacks.get(feedback_id)
            if feedback is None:
                results.append({'id': feedback_id, 'ok': False, 'detail': '反馈不存在'})
                continue

            feedback.status = status_value
            update_fields = ['status']
            if admin_reply is not None:
                feedback.admin_reply = admin_reply
                update_fields.append('admin_reply')
            if status_value == 'resolved':
                # 与单条 reply 一致：**首次**处理才记时间，重复标记不刷新它
                feedback.handled_at = feedback.handled_at or timezone.now()
                update_fields.append('handled_at')
            else:
                feedback.handled_at = None
                update_fields.append('handled_at')
            feedback.save(update_fields=update_fields)

            ok_count += 1
            results.append({'id': feedback_id, 'ok': True, 'detail': status_value})

        logger.info('批量流转反馈状态 status=%s by=%s 成功=%s/%s',
                    status_value, request.user.id, ok_count, len(ids))
        log_admin_action(
            request.user, 'feedback.bulk_status', target_type='feedback',
            target_id=','.join(str(i) for i in ids[:20]),
            detail=f'批量流转为 {status_value}，{ok_count}/{len(ids)} 条',
            request=request,
        )
        return Response({
            'status': status_value,
            'requested': len(ids),
            'succeeded': ok_count,
            'failed': len(ids) - ok_count,
            'results': results,
        })

    @action(detail=False, methods=['post'], url_path='bulk-delete',
            permission_classes=[IsFeedbackEditor])
    def bulk_delete(self, request):
        """
        批量删除反馈（第 138 批）

            POST /api/feedback/bulk-delete/   {"ids": [1, 2, 3]}

        为什么需要：单条删除每条都要点一次确认框，"这一批都是同一类垃圾反馈"时
        逐条删很折磨。前端列表页加了多选后，这是它的后端。

        权限（**比批量改状态更严**，和单条 destroy 的口径对齐后再收紧一档）：
          · 单条 destroy：自己的随时删、**别人的**仅全权管理员（第 124/126 批的护栏）；
          · 批量 destroy：**只给全权管理员** ——
            理由：批量是不可逆的破坏性操作，"能看全部反馈"（CONTENT 能力）不等于
            "可以一次抹掉一批"。而且列表页里编辑员看到的本就是全部反馈，
            开放给他等于把"删别人的反馈"这条守卫从后门绕过去。

        与批量改状态一致的三处：逐条处理不整体失败（响应里给每条的成败）、
        只能操作自己 queryset 里能看到的记录、一次最多 200 条（`_parse_bulk_ids` 共用）。
        """
        if not is_full_admin(request.user):
            return Response(
                {'detail': '只有管理员可以批量删除反馈'},
                status=status.HTTP_403_FORBIDDEN,
            )

        ids, error = _parse_bulk_ids(request)
        if error:
            return error

        # 复用 get_queryset：将来若权限口径再收紧（例如编辑员只看某几类），这里自动跟着变
        feedbacks = {f.id: f for f in self.get_queryset().filter(id__in=ids)}

        results = []
        ok_count = 0
        for feedback_id in ids:
            feedback = feedbacks.get(feedback_id)
            if feedback is None:
                results.append({'id': feedback_id, 'ok': False, 'detail': '反馈不存在'})
                continue
            # 顺带清掉反馈图：否则 media/feedback_images 会留下孤儿文件
            image_name = feedback.image.name if feedback.image else ''
            feedback.delete()
            if image_name:
                try:
                    from django.core.files.storage import default_storage
                    default_storage.delete(image_name)
                except Exception as exc:  # noqa: BLE001 —— 文件删不掉不该让接口失败
                    logger.warning('批量删除反馈时清理图片失败: %s', exc)
            ok_count += 1
            results.append({'id': feedback_id, 'ok': True, 'detail': 'deleted'})

        logger.info('批量删除反馈 by=%s 成功=%s/%s', request.user.id, ok_count, len(ids))
        log_admin_action(
            request.user, 'feedback.bulk_delete', target_type='feedback',
            target_id=','.join(str(i) for i in ids[:20]),
            detail=f'批量删除反馈 {ok_count}/{len(ids)} 条（失败 {len(ids) - ok_count} 条）',
            request=request,
        )
        return Response({
            'requested': len(ids),
            'succeeded': ok_count,
            'failed': len(ids) - ok_count,
            'results': results,
        })

    @action(detail=True, methods=['post'], permission_classes=[IsFeedbackEditor])
    def reply(self, request, pk=None):
        """
        管理员回复 / 流转处理状态（第 27 批新增）

        `status` 与 `admin_reply` 在序列化器里是**只读**的（普通用户不能自评"已处理"），
        所以管理员不能直接 PATCH 这两个字段 —— 这里给管理端一个专门的动作：
            POST /api/feedback/{id}/reply/  {"status": "resolved", "admin_reply": "..."}
        """
        feedback = self.get_object()

        status_value = (request.data.get('status') or '').strip()
        valid_status = {choice[0] for choice in Feedback.STATUS_CHOICES}
        if status_value and status_value not in valid_status:
            return Response({'status': ['无效的处理状态']}, status=status.HTTP_400_BAD_REQUEST)

        if status_value:
            feedback.status = status_value
        if request.data.get('admin_reply') is not None:
            feedback.admin_reply = request.data.get('admin_reply')

        # 只有"已处理"才记录处理时间；从已处理退回其它状态则清空
        if feedback.status == 'resolved':
            feedback.handled_at = feedback.handled_at or timezone.now()
        else:
            feedback.handled_at = None

        feedback.save(update_fields=['status', 'admin_reply', 'handled_at'])

        # 第 85 批：管理员回复是给用户看的中文，英文界面下需要英文版本。
        # 回复内容变了就重译一次（失败只记日志，不影响回复本身）；
        # 管理员若在请求里直接给了 admin_reply_en，则视为人工译文，跳过自动翻译。
        manual_reply_en = (request.data.get('admin_reply_en') or '').strip()
        if manual_reply_en:
            feedback.admin_reply_en = manual_reply_en
            feedback.mark_translated(feedback.SOURCE_MANUAL)
            feedback.save(update_fields=['admin_reply_en', 'translation_hash',
                                         'translation_source', 'translated_at'])
        elif getattr(settings, 'TRANSLATE_ON_WRITE', True):
            try:
                from .services_translate import safe_translate_instance
                safe_translate_instance(feedback)
            except Exception:  # noqa: BLE001 —— 翻译失败不能影响管理员处理反馈
                logger.exception('反馈回复翻译调度失败 feedback=%s', feedback.id)

        logger.info('管理员 %s 处理了反馈 id=%s -> %s', request.user.username, feedback.id, feedback.status)
        return Response(self.get_serializer(feedback).data)


class PestEncyclopediaViewSet(viewsets.ModelViewSet):
    """
    病害百科API
    - 所有用户可查看病害信息
    - 仅管理员（is_staff / is_superuser / role=ADMIN）可创建、编辑、删除病害信息
    - 支持在同一个请求中提交防治方法列表（prevention_methods）
    """
    permission_classes = [IsAdminOrReadOnly]

    def get_serializer_class(self):
        # 新增 / 修改使用可写序列化器
        if self.action in ('create', 'update', 'partial_update'):
            return PestInfoWriteSerializer
        if self.action == 'retrieve':
            return PestInfoDetailSerializer
        return PestInfoListSerializer

    def get_queryset(self):
        queryset = PestInfo.objects.all()

        # 支持按作物类型筛选
        #
        # ⚠️ 第 190 批：这里原来是 `crop_type__icontains`（**包含**匹配），已改成精确匹配。
        #    "包含"在中文作物名上是错的：作物名之间会互相包含 ——
        #    筛「桃子」会把**樱桃**的病害一起捞出来（`桃子` 里含 `桃`），
        #    筛「樱桃」也会捞出「桃子」那两条。管理员在「病害百科维护」选作物筛选时
        #    看到的就是这个现象（用户反馈："筛选桃，多出了一个樱桃白粉病"）。
        #    作物筛选的值来自 `/api/calendar/crops/`（就是库里 `crop_type` 的原值），
        #    所以精确匹配既正确又不会漏。**要模糊找作物请用 `search=`**（名称/症状/描述）。
        #
        # ⚠️ 契约：这里的值就是 `crop_type` 的**原值**（中文键），不是显示名 ——
        #    英文界面下前端拿 `crop_names_en` 只用来**显示**，回传的仍是这个键
        #    （第 190 批顺手修了管理端下拉把显示名当值传的问题）。所以这里不需要
        #    大小写折叠、也不该接受 `Peach` 这种英文名 —— 那属于另一个字段
        #    （`crop_type_en`）的事，真要支持得先定义清楚冲突时以谁为准。
        crop_type = self.request.query_params.get('crop_type', None)
        if crop_type:
            queryset = queryset.filter(crop_type=crop_type.strip())

        # 支持按病害名称搜索
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(symptoms__icontains=search) |
                Q(description__icontains=search)
            )

        return queryset.order_by('name')

    @action(detail=True, methods=['get'])
    def prevention_methods(self, request, pk=None):
        """获取指定病害的防治方法"""
        pest = self.get_object()
        methods = PreventionMethod.objects.filter(pest=pest)
        serializer = PreventionMethodSerializer(methods, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def recent(self, request):
        """
        最近添加的病害（默认 10 条，最多 50 条）

        说明：路由 `/api/pests/recent/` 原本排在 `pests/<str:english_identifier>/`
        之后，会被当作英文标识符抢走；而且本视图集当时并没有 recent 动作，
        因此这个接口即使被访问也只会得到 404/500，属于未完成接口。
        现已补上动作并把路由顺序调整到标识符路由之前。
        """
        try:
            limit = int(request.query_params.get('limit', 10))
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))

        queryset = self.get_queryset().order_by('-id')[:limit]
        serializer = PestInfoListSerializer(queryset, many=True)
        return Response({
            'status': 'success',
            'count': len(serializer.data),
            'results': serializer.data,
        })


class DetectionHistoryDetailView(RetrieveUpdateDestroyAPIView):
    """
    检测历史详情API视图
    - 用户可查看、更新、删除自己的检测历史记录
    - 管理员可查看、更新、删除任何检测历史记录
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DetectionHistorySerializer
    lookup_field = 'pk'

    def get_queryset(self):
        user = self.request.user
        if has_capability(user, CAP_USER_ADMIN):
            return DetectionHistory.objects.all()
        return DetectionHistory.objects.filter(user=user)

    def perform_destroy(self, instance):
        # 删除相关的标注图片（如果存在）
        if instance.annotated_image:
            try:
                storage, path = instance.annotated_image.storage, instance.annotated_image.path
                if storage.exists(path):
                    storage.delete(path)
            except Exception as e:
                logger.error(f"删除标注图片时出错: {str(e)}")
        instance.delete()


class DetectionHistoryView(APIView):
    """
    检测历史API视图
    - 用户可查看自己的检测历史
    - 管理员可查看所有用户的检测历史
    - 支持按病害名称、日期、用户筛选
    - 支持分页查询
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DetectionHistorySerializer

    def get_queryset(self):
        """
        检测历史查询集

        支持参数：
        - pest：按病害名称筛选（匹配检测结果、病害百科名称、英文标识）
        - user：按识别者用户名筛选（管理端"是谁识别的"）
        - search：综合搜索（用户名 / 检测结果 / 病害百科名称）
        - date：按日期筛选（YYYY-MM-DD，按检测时间 timestamp 的自然日）
        - all_users=true：仅管理员可查看全部用户的记录

        原实现的问题（已修复）：
        1. 引用了 DetectionHistory 上不存在的字段（pest_info__name_zh、
           pest_info__name_en、created_at），会抛 FieldError 又被 except 吞掉，
           导致「按病害筛选」「按日期筛选」永远返回空列表；
        2. all_users 参数对任何登录用户都生效，普通用户可借此查看他人记录；
        3. 每次请求都会把全部请求头写进日志（debug.log 因此膨胀到 90 万行）。
        """
        user = self.request.user

        queryset = DetectionHistory.objects.select_related('pest_info')

        pest_name = (self.request.query_params.get('pest') or '').strip()
        date_str = (self.request.query_params.get('date') or '').strip()
        all_users = self.request.query_params.get('all_users') == 'true'

        is_admin_user = has_capability(user, CAP_USER_ADMIN)

        # 用户权限过滤：普通用户只能看到自己的记录
        if not (is_admin_user and all_users):
            queryset = queryset.filter(user=user)

        # 病害名称筛选
        if pest_name and pest_name.lower() != 'all':
            queryset = queryset.filter(
                Q(detection_result__icontains=pest_name) |
                Q(pest_info__name__icontains=pest_name) |
                Q(pest_info__english_identifier__icontains=pest_name)
            )

        # 按识别者用户名筛选
        # 管理端页面写着"搜索用户或病害名称"，但后端此前只认 pest（病害）参数，
        # 于是"按用户搜索"实际不生效 —— 管理端要查"是谁识别的"就必须有这个参数。
        user_name = (self.request.query_params.get('user') or '').strip()
        if user_name and user_name.lower() != 'all':
            queryset = queryset.filter(user__username__icontains=user_name)

        # 综合搜索：用户名 或 病害名 / 检测结果
        search_kw = (self.request.query_params.get('search') or '').strip()
        if search_kw and search_kw.lower() != 'all':
            queryset = queryset.filter(
                Q(user__username__icontains=search_kw) |
                Q(detection_result__icontains=search_kw) |
                Q(pest_info__name__icontains=search_kw)
            )

        # 日期筛选（按检测时间的自然日）
        if date_str and date_str.lower() != 'all':
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date=date_obj)
            except (ValueError, TypeError):
                logger.warning('[History] 日期参数格式不正确，已忽略: %s', date_str)

        return queryset.order_by('-timestamp').distinct()

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def _get_pagination_params(self, query_params):
        """
        从查询参数中提取分页参数
        """

        def get_param_value(param_name, default_value):
            # 尝试获取标准格式参数
            value = query_params.get(param_name)
            if value is not None:
                if isinstance(value, list):
                    value = value[0] if value else default_value
                try:
                    return int(value) if str(value).strip() else default_value
                except (ValueError, TypeError):
                    return default_value

            # 尝试获取params[param_name]格式的参数
            param_key = f'params[{param_name}]'
            value = query_params.get(param_key)
            if value is not None:
                if isinstance(value, list):
                    value = value[0] if value else default_value
                try:
                    return int(value) if str(value).strip() else default_value
                except (ValueError, TypeError):
                    return default_value

            return default_value

        # 获取并验证分页参数
        page = max(1, get_param_value('page', 1))
        page_size = min(100, max(1, get_param_value('page_size', 6)))

        return page, page_size

    def get(self, request, *args, **kwargs):
        """
        获取检测历史记录 / 导出 Excel

        - 如果 URL 包含 `export-excel`，则导出 Excel（第 43 批）
        - 否则返回分页的检测历史记录

        第 139 批：原来的 `download-report` 分支与 `download_report()`（332 行 ReportLab
        排版代码）已删除 —— 识别报告现在由**前端**用 jsPDF 生成（`utils/pdfReport.js`，
        识别页与历史记录页共用），服务端那两份实现没有任何调用方。
        """

        # 第 43 批：导出 Excel（沿用同一套筛选与权限规则）
        if 'export-excel' in request.path_info:
            return self.export_excel(request, *args, **kwargs)

        # 否则处理正常的列表请求
        try:
            # 记录完整的请求信息
            logger.info(f'[History] 收到请求 - 路径: {request.path}, 方法: {request.method}')
            logger.info(f'[History] 请求参数: {dict(request.query_params)}')

            # 获取分页参数
            page, page_size = self._get_pagination_params(request.query_params)
            logger.info(
                f"[History] 处理检测历史请求 - 用户: {request.user.username}, 页码: {page}, 每页数量: {page_size}")

            # 记录筛选参数
            pest_filter = request.query_params.get('pest')
            if pest_filter:
                logger.info(f'[History] 应用病害筛选: {pest_filter}')

            # 获取查询集并应用筛选条件
            queryset = self.get_queryset()

            # 获取筛选后的总记录数
            total_records = queryset.count()

            # 计算总页数（确保至少1页）
            total_pages = max(1, (total_records + page_size - 1) // page_size) if page_size > 0 else 1

            # 调整请求的页码，确保在有效范围内
            if page < 1:
                page = 1
            elif page > total_pages and total_pages > 0:
                page = total_pages

            # 计算分页
            start_index = (page - 1) * page_size
            end_index = start_index + page_size

            # 应用分页
            paginated_queryset = queryset[start_index:end_index]

            # 记录分页信息
            logger.info(
                f'[History] 分页信息 - 总数: {total_records}, 总页数: {total_pages}, 当前页: {page}, 每页: {page_size}')

            # 记录分页信息
            logger.info(
                f'[History] Pagination - page: {page}, page_size: {page_size}, total_records: {total_records}, total_pages: {total_pages}')

            # 序列化数据
            serializer = self.get_serializer(paginated_queryset, many=True)

            # 记录筛选后的记录数
            logger.info(f'[History] 筛选后记录数: {total_records}, 当前页记录数: {len(serializer.data)}')

            # 记录分页和筛选信息
            logging.info(
                f"分页信息 - 总记录: {total_records}, 总页数: {total_pages}, 当前页: {page}, 每页: {page_size}")

            # 构建符合前端期望的响应数据格式
            response_data = {
                'code': 200,
                'msg': 'success',
                'data': {
                    'items': serializer.data,
                    'total': total_records,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': total_pages,
                    'has_next': page < total_pages,
                    'has_previous': page > 1,
                }
            }

            # 记录最终响应数据
            logger.info(
                f'[History] 返回响应 - 状态: 200, 记录数: {len(serializer.data)}, 总记录: {total_records}, 总页数: {total_pages}')

            # 记录响应数据摘要
            logger.info(
                f'[History] 返回数据 - 记录数: {len(serializer.data)}, 总记录: {total_records}, 总页数: {total_pages}')

            # 记录请求参数和响应数据的摘要
            logger.info(f'[History] 请求参数: {dict(request.query_params)}')
            logger.debug(f'[History] 完整响应数据: {response_data}')

            logging.info(
                f"成功返回检测历史 - 用户: {request.user.username}, 总记录数: {total_records}, 总页数: {total_pages}")

            # 确保返回的数据结构符合前端期望
            response = Response(response_data)
            response.data['data'] = {
                'items': response_data['data']['items'],
                'total': response_data['data']['total'],
                'page': response_data['data']['page'],
                'page_size': response_data['data']['page_size'],
                'total_pages': response_data['data']['total_pages']
            }
            return response

        except Exception as e:
            error_msg = f"获取检测历史失败 - 用户: {request.user.username}, 错误: {str(e)}"
            logging.error(error_msg)
            logging.error(traceback.format_exc())
            return Response(
                {"error": "获取检测历史记录时发生错误", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def export_excel(self, request, *args, **kwargs):
        """
        导出识别记录为 Excel（第 43 批）

        GET /api/detection-history/export-excel/[?pest=&date=&user=&all_users=true]

        · **完全沿用列表那套筛选与权限**（同一个 `get_queryset`）：
          普通用户只导出自己的记录；管理员带 `all_users=true` 才导出全部；
          病害名 / 日期 / 用户名 / 综合搜索都生效 —— 导出的就是"当前筛选结果"。
        · 后端运行环境没有 openpyxl，用 `api/xlsx.py` 这个零依赖的极简 writer 生成。
        """
        try:
            queryset = self.get_queryset().select_related('user', 'pest_info')
            total = queryset.count()

            # 第 72 批：导出语言跟随前端语言（?lang=en），否则英文界面导出的
            # Excel 表头与工作表名全是中文。
            lang = (self.request.query_params.get('lang') or 'zh').lower()
            is_en = lang.startswith('en')

            # 安全上限：避免一次拉爆内存（1 万条以内足够）
            limit = 10000
            rows = []
            for index, item in enumerate(queryset[:limit], start=1):
                pest = item.pest_info
                confidence = item.confidence
                rows.append([
                    index,
                    item.timestamp.strftime('%Y-%m-%d %H:%M:%S') if item.timestamp else '',
                    item.user.username if item.user_id else '',
                    item.detection_result or '',
                    (pest.name_en or pest.name) if (pest and is_en) else (pest.name if pest else ''),
                    (pest.crop_type_en or pest.crop_type) if (pest and is_en) else (pest.crop_type if pest else ''),
                    f'{confidence * 100:.1f}%' if confidence is not None else '',
                    str(item.image) if item.image else '',
                ])

            if is_en:
                headers = ['#', 'Diagnosed at', 'User', 'Result', 'Wiki entry', 'Crop', 'Confidence', 'Image path']
            else:
                headers = ['序号', '识别时间', '识别用户', '识别结果', '病害百科词条', '作物类型', '置信度', '图片路径']

            # 末尾追加一行汇总，方便直接看总数（以及是否被上限截断）
            if total > limit:
                summary = (
                    f'({total} records in total; first {limit} exported)'
                    if is_en
                    else f'（共 {total} 条，本次导出前 {limit} 条）'
                )
            else:
                summary = f'({total} records)' if is_en else f'（共 {total} 条）'
            rows.append([summary, '', '', '', '', '', '', ''])

            content = build_workbook(
                headers, rows,
                sheet_name='Detection records' if is_en else '识别记录',
                column_widths=[6, 20, 14, 22, 22, 12, 10, 34],
            )

            filename = f'detection-history-{timezone.now().strftime("%Y%m%d-%H%M%S")}.xlsx'
            response = HttpResponse(
                content,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            # 文件名同时给 ASCII 与 UTF-8 两种写法，兼容不同浏览器
            response['Content-Disposition'] = (
                f'attachment; filename="{filename}"; filename*=UTF-8\'\'%E8%AF%86%E5%88%AB%E8%AE%B0%E5%BD%95.xlsx'
            )
            logger.info('[History] 导出 Excel: user=%s 条数=%s', request.user.id, len(rows) - 1)
            return response

        except Exception:
            logger.exception('[History] 导出 Excel 失败')
            return Response({
                'status': 'error',
                'message': '导出失败，请稍后重试',
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, *args, **kwargs):
        """
        删除检测记录
        - 用户只能删除自己的记录
        - 管理员可以删除任何记录
        """
        try:
            history_id = kwargs.get('pk')
            if not history_id:
                return Response({
                    'status': 'error',
                    'message': '请提供要删除的记录ID',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                # 获取要删除的记录
                if has_capability(request.user, CAP_USER_ADMIN):
                    history = DetectionHistory.objects.get(id=history_id)
                else:
                    history = DetectionHistory.objects.get(id=history_id, user=request.user)

                # 删除关联的图片文件
                try:
                    # 删除原始图片
                    if history.image and os.path.isfile(history.image.path):
                        os.remove(history.image.path)
                        logger.info(f'[History] 已删除原始图片: {history.image.path}')

                    # 删除标注图片（如果存在）
                    if history.annotated_image and os.path.isfile(history.annotated_image.path):
                        os.remove(history.annotated_image.path)
                        logger.info(f'[History] 已删除标注图片: {history.annotated_image.path}')
                except Exception as e:
                    logger.error(f'[History] 删除图片文件时出错: {str(e)}', exc_info=True)
                    # 继续执行，仍然删除数据库记录

                # 删除数据库记录
                history.delete()
                logger.info(f'[History] 成功删除记录 ID: {history_id}')

                return Response({
                    'status': 'success',
                    'message': '删除成功',
                    'data': None
                }, status=status.HTTP_204_NO_CONTENT)

            except DetectionHistory.DoesNotExist:
                return Response({
                    'status': 'error',
                    'message': '未找到指定的记录',
                    'data': None
                }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error(f'[History] 删除检测记录时出错: {str(e)}', exc_info=True)
            return Response({
                'status': 'error',
                'message': f'删除记录时出错: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ImageUploadView(APIView):
    """
    通用图片上传（论坛发帖/编辑器插图使用）

    说明：前端 forum.js 的 uploadImage 与 EditPostView 一直向 `/api/upload/image/`
    上传图片，但后端从未提供该路由（只有一个新闻专用的 upload_image），
    因此发帖编辑器里插入图片必定失败。这里补上通用实现。

    第 91 批（安全）修掉三处：
      ① 没有大小上限 —— 任何登录用户都能刷爆磁盘；
      ② 只比 `content_type`（客户端可伪造）—— 改成按**文件头**探测真实格式；
      ③ 直接用用户的原始文件名拼路径 —— 改成随机文件名 + 按真实格式定扩展名。
    校验逻辑集中在 `api/image_validation.py`（与新闻图上传共用）。
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        image_file = request.FILES.get('image') or request.FILES.get('file')

        try:
            meta = validate_image_upload(image_file)
        except ImageValidationError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            name = default_storage.save(f'uploads/{meta["filename"]}', image_file)
            image_url = request.build_absolute_uri(f'{settings.MEDIA_URL}{name}')
            return Response(
                {'url': image_url, 'image_url': image_url, 'message': '图片上传成功'},
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:  # noqa: BLE001
            logger.error('图片上传失败: %s', e, exc_info=True)
            return Response({'error': '图片上传失败'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DetectionHistoryClearView(APIView):
    """
    清空检测记录

    DELETE /api/detection-history/clear-all/
    - 普通用户：清空自己的记录
    - 管理员可加 ?all_users=true 清空所有人的记录

    说明：前端「清除全部记录」按钮一直在调用该路由，但后端从未实现，
    点击后必然 404。这里补上，并同步删除关联的图片文件。
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        user = request.user
        is_admin_user = has_capability(user, CAP_USER_ADMIN)
        all_users = request.query_params.get('all_users') == 'true'

        queryset = DetectionHistory.objects.all()
        if not (is_admin_user and all_users):
            queryset = queryset.filter(user=user)

        deleted = 0
        for history in queryset:
            for image_field in ('image', 'annotated_image'):
                try:
                    image = getattr(history, image_field, None)
                    if image and os.path.isfile(image.path):
                        os.remove(image.path)
                except Exception as e:  # noqa: BLE001
                    logger.warning('[History] 清空记录时删除图片失败: %s', e)
            history.delete()
            deleted += 1

        logger.info('[History] 用户 %s 清空了 %s 条检测记录', user.username, deleted)
        return Response({
            'status': 'success',
            'message': f'已删除 {deleted} 条记录',
            'deleted': deleted,
            'data': None,
        })


class PestTypesView(APIView):
    """
    获取所有病害类型（供前端筛选下拉使用）
    - 支持按名称搜索
    - 支持按作物类型筛选
    - 返回格式: {"status": "success", "count": 10, "results": ["病害1", "病害2", ...]}

    ⚠️ 契约提醒（第 106 批补）：返回的是**病害名字符串列表，没有 id**
    ------------------------------------------------------------------
    调用方（前端筛选项、移动端下拉）**只能按名字匹配**，不能按 id。
    这不是笔误，而是早期实现留下的约定：下拉项直接用名字当值。
    如果你想改成返回 `[{id, name}]`，必须先改所有调用方 ——
    前端目前是拿这个字符串去和 `detection_result` 做比较的。

    ⚠️ 另一个坑：整个方法体被一个 `except Exception` 包着，
    任何编程错误（比如字段名写错）都会被改写成
    `500 {'message': '获取病害类型失败'}` —— **真实原因只在日志里**。
    第 106 批那个 `english_name` 的 bug 就是这么躲了几个月的：
    接口一直 500，但响应体看不出为什么。排查时先看 `logs/debug.log`。
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        try:
            # 获取查询参数
            search = request.query_params.get('search', '').strip()
            crop_type = request.query_params.get('crop_type', '').strip()

            # 构建查询条件
            queryset = PestInfo.objects.all()

            # 应用搜索条件
            #
            # ⚠️ 第 106 批修：这里原来写的是 `Q(english_name__icontains=search)`，
            #    而 **PestInfo 没有 `english_name` 字段**（只有 `name` / `name_en` /
            #    `english_identifier`）。`FieldError` 被下面的 `except Exception`
            #    吞掉，于是「带 search 参数的请求」**必定返回 500**，
            #    客户端只能看到一句「获取病害类型失败」。
            #
            #    同一个 bug 在本文件第 945 行的 `PreventionDataView` 里
            #    **早在第 78 批就修好了、还写了注释** —— 但修复没有被传播到这里。
            #    这是"注释只写在一处"的典型代价：解释留在了旁边的方法里，
            #    另一个方法照旧错着。所以这段注释刻意写全字段名，避免再被抄错。
            if search:
                queryset = queryset.filter(
                    Q(name__icontains=search) |
                    Q(name_en__icontains=search) |               # 第 78 批：英文界面下能搜到英文名
                    Q(english_identifier__icontains=search) |    # 数据集标识（Apple___Apple_scab 之类）
                    Q(description__icontains=search)
                )

            # 应用作物类型筛选
            if crop_type:
                queryset = queryset.filter(crop_type__iexact=crop_type)

            # 获取病害名称列表
            pest_names = list(queryset.values_list('name', flat=True).distinct())

            return Response({
                'status': 'success',
                'count': len(pest_names),
                'results': pest_names
            })

        except Exception as e:
            logger.error(f"获取病害类型失败: {str(e)}")
            return Response(
                {'status': 'error', 'message': '获取病害类型失败'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ---------------------------------------------------------------------------
# 第 106 批：删掉了这里一份**重复的 NewsViewSet**（原第 2553-2661 行，约 109 行）
#
# 为什么删：项目里有两份 NewsViewSet，而
#   crop_disease_backend/urls.py 注册的是 api.news_views.NewsViewSet
# —— 也就是说 views.py 里这一份**永远不会被调用**。它还有两个坑：
#   1. 里面留着 def detail(self, request, pk=None)，而 news_views.py 用长注释
#      记录过「这个动作名与 DRF 路由的 detail 冲突 → 必定 500」；
#   2. 它用 CustomPagination（默认 6 条），活的那份用
#      StandardResultsSetPagination（10 条）。
#
# 留着它的代价是真实的：下一个维护者很可能去改错的那一份，
# 或者把死的这份重新注册上去（于是两个坑一起复活）。
# 新闻接口的唯一实现在 api/news_views.py。
# ---------------------------------------------------------------------------
