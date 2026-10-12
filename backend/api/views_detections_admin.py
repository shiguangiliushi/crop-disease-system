"""
================================================================================
第 172 批：控制台的「识别记录」接口
================================================================================
农户在识别页拍的每一张叶子都会落一条 `DetectionHistory`（图片 + 结果 + 置信度 + 关联词条）。
在这之前**只有农户自己**能在「历史记录」页看到自己的记录 —— 管理员想看"这台机器识别得准不准、
大家在拿它认什么、有没有人传了一堆废图"，只能去 Django admin 里翻表。

历史沿革（值得记一笔）：第 22 批曾有过一个管理端 `DetectionHistoryView`，
后来以"与农户端 HistoryView 重复"为由撤掉，把 `/admin/detection-history`
改成重定向到 `/history`。但两者定位其实不同：

  · 农户端 HistoryView：**只看自己的**记录（删自己的、批量清空）；
  · 控制台这一页：**跨用户**的全局视图 —— 谁在什么时候认出了什么、有没有匹配到词条、
    置信度分布如何、能不能一眼看出"某张图明显传错了"。

所以本批按管理端的需要重建这一页，**不是**把老页面搬回来。

    GET    /api/admin/detections/            列表 + 统计（**USER_ADMIN 能力**）
    DELETE /api/admin/detections/<pk>/       删除单条（**仅全权管理员**，不可逆，连图片一起删）

## 权限口径（与既有实现一致，不是新定的）

识别记录里带**用户身份与用户上传的图片** → 与「用户管理」同档：`CAP_USER_ADMIN`。
"删除"是**不可逆**动作（行没了、图片文件也删）→ 与"删除意见反馈 / 硬删除评论"同类，
**仅全权管理员**。

## 为什么不做批量删除

与评论管理同一个理由（第 149 批的结论）：成批的不可逆删除不该出现在控制台按钮上
（真要清库走管理命令）。农户端自己那套"批量清空"是另一回事 —— 那是用户删自己的东西。

## 列表为什么要"轻"

农户端序列化器会把**标注图的 base64** 塞进响应（识别结果页要用它直接渲染）。
列表页绝不能这么干：一页 20 条就是几十 MB。这里只回**图片地址**，
缩略图由浏览器按 URL 取。
"""
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .audit import log_admin_action
from .capabilities import CAP_USER_ADMIN, has_capability, is_full_admin
from .models import DetectionHistory
from .pagination import CustomPagination

User = get_user_model()

#: 排序白名单（非法值忽略 —— 与其它管理列表一致）
ORDERING_WHITELIST = (
    'timestamp', '-timestamp', 'confidence', '-confidence', 'id', '-id',
)


def _reject_non_user_admin(request, action_label):
    """识别记录含用户身份，门禁与「用户管理」同档（USER_ADMIN）"""
    if has_capability(request.user, CAP_USER_ADMIN):
        return None
    return Response({'detail': f'只有用户管理员可以{action_label}'},
                    status=status.HTTP_403_FORBIDDEN)


def _media_url(field):
    """
    图片地址：回**相对路径**（`/media/...`）

    前端有 `getFullUrl()` 统一补域名（与其它管理页一致）。
    这里不用 `request.build_absolute_uri`：本地开发时后端在 8000、
    前端在 5173，绝对地址会把图片指到后端端口，反而要额外配 CORS。
    """
    if not field:
        return ''
    try:
        url = field.url
    except ValueError:
        # 文件字段有值但文件不在（手工删过 media）→ 不要让整个列表 500
        return ''
    return url if url.startswith('/') else f'/{url}'


def serialize_detection(row):
    """一条识别记录（列表与详情共用）"""
    pest = None
    if row.pest_info_id:
        pest = {
            'id': row.pest_info_id,
            'name': row.pest_info.name,
            'name_en': row.pest_info.name_en or '',
            'english_identifier': row.pest_info.english_identifier,
        }
    return {
        'id': row.id,
        'user': {
            'id': row.user_id,
            # 账号注销后 user 可能是 None（SET_NULL 之外的删除路径）—— 给个兜底名
            'username': getattr(row.user, 'username', '') or '已注销用户',
        } if row.user_id else None,
        'result': row.detection_result,
        'confidence': row.confidence,
        # 是否匹配到了病害词条：没匹配上的记录最值得看（识别出了名字，但库里没有对应词条）
        'matched': bool(row.pest_info_id),
        'pest': pest,
        'image': _media_url(row.image),
        'annotated_image': _media_url(row.annotated_image),
        'timestamp': row.timestamp.isoformat() if row.timestamp else None,
    }


class AdminDetectionListView(APIView):
    """
    识别记录列表 + 概览统计（USER_ADMIN 能力）

    支持参数：
      `search`            用户名 / 识别结果 / 病害名
      `user`              只看某个用户的记录
      `pest`              只看某个病害词条的记录
      `matched`           `true` 只看匹配到词条的；`false` 只看没匹配上的
      `confidence_min`    / `confidence_max`    置信度区间（0~1）
      `date_from`         / `date_to`           `YYYY-MM-DD`
      `ordering`          白名单内，默认 `-timestamp`
      `page` / `page_size`
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        denied = _reject_non_user_admin(request, '查看识别记录')
        if denied:
            return denied

        queryset = DetectionHistory.objects.select_related('user', 'pest_info')

        # -- 关键字：用户名 / 识别结果 / 词条名 --------------------------------
        search = (request.query_params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(
                Q(user__username__icontains=search)
                | Q(detection_result__icontains=search)
                | Q(pest_info__name__icontains=search)
                | Q(pest_info__name_en__icontains=search)
            )

        # -- 按用户 ------------------------------------------------------------
        user_id = (request.query_params.get('user') or '').strip()
        if user_id:
            try:
                queryset = queryset.filter(user_id=int(user_id))
            except (TypeError, ValueError):
                pass  # 非法值忽略（与其它管理列表一致）

        # -- 按病害词条 --------------------------------------------------------
        pest_id = (request.query_params.get('pest') or '').strip()
        if pest_id:
            try:
                queryset = queryset.filter(pest_info_id=int(pest_id))
            except (TypeError, ValueError):
                pass

        # -- 匹配 / 未匹配 -----------------------------------------------------
        matched = (request.query_params.get('matched') or '').strip().lower()
        if matched in ('true', '1', 'yes'):
            queryset = queryset.filter(pest_info__isnull=False)
        elif matched in ('false', '0', 'no'):
            queryset = queryset.filter(pest_info__isnull=True)

        # -- 置信度区间 --------------------------------------------------------
        for param, lookup in (('confidence_min', 'confidence__gte'),
                              ('confidence_max', 'confidence__lte')):
            raw = (request.query_params.get(param) or '').strip()
            if not raw:
                continue
            try:
                queryset = queryset.filter(**{lookup: float(raw)})
            except (TypeError, ValueError):
                pass

        # -- 时间区间（含当天）-------------------------------------------------
        for param, lookup in (('date_from', 'timestamp__date__gte'),
                              ('date_to', 'timestamp__date__lte')):
            raw = (request.query_params.get(param) or '').strip()
            if not raw:
                continue
            try:
                # 只接受 YYYY-MM-DD；非法就忽略（不 500）
                timezone.datetime.strptime(raw, '%Y-%m-%d')
            except ValueError:
                continue
            queryset = queryset.filter(**{lookup: raw})

        # -- 统计（在**过滤后**的集合上算，页面上的数字与列表口径一致）--------
        stats = queryset.aggregate(
            total=Count('id'),
            matched=Count('id', filter=Q(pest_info__isnull=False)),
            unmatched=Count('id', filter=Q(pest_info__isnull=True)),
            avg_confidence=Avg('confidence'),
            users=Count('user', distinct=True),
        )
        today = timezone.localdate()
        stats['today'] = queryset.filter(timestamp__date=today).count()
        stats['avg_confidence'] = (
            round(stats['avg_confidence'], 4) if stats['avg_confidence'] is not None else None
        )

        # -- 排序与分页 --------------------------------------------------------
        ordering = (request.query_params.get('ordering') or '').strip()
        if ordering not in ORDERING_WHITELIST:
            # 没传或非法值 → 默认按时间倒序（与其它管理列表一致：忽略非法值，不报错）
            ordering = '-timestamp'
        queryset = queryset.order_by(ordering, '-id')

        paginator = CustomPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        rows = [serialize_detection(row) for row in page]
        return Response({
            'count': paginator.page.paginator.count,
            'total_pages': paginator.page.paginator.num_pages,
            'current_page': paginator.page.number,
            'results': rows,
            'stats': stats,
        })


class AdminDetectionDeleteView(APIView):
    """
    删除单条识别记录（**仅全权管理员**）

    不可逆：行删掉，**图片文件也一并删除**（只删行会留下孤儿文件，
    media 目录会越滚越大 —— 健康页里"媒体目录体积"那个数字就是这么涨起来的）。
    """

    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        if not is_full_admin(request.user):
            return Response({'detail': '只有管理员可以删除识别记录'},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            row = DetectionHistory.objects.select_related('user').get(pk=pk)
        except DetectionHistory.DoesNotExist:
            return Response({'detail': '识别记录不存在'}, status=status.HTTP_404_NOT_FOUND)

        snapshot = {
            'id': row.id,
            'user': getattr(row.user, 'username', '') or '',
            'result': row.detection_result,
        }
        # 先删文件（数据库删了之后再删文件，一旦出错就找不到路径了）
        for field in (row.image, row.annotated_image):
            if field:
                try:
                    field.delete(save=False)
                except Exception as exc:  # noqa: BLE001 —— 文件删不掉不该挡住删记录
                    import logging
                    logging.getLogger(__name__).warning(
                        '删除识别记录图片失败（继续删记录）: %s', exc)

        row.delete()
        # ⚠️ 审计要在**删除之后**写、但目标快照用删除前抓好的值 ——
        # log_admin_action 的第一个参数是**操作人**，不是 request（这一点容易写错）。
        log_admin_action(
            request.user, 'detection.delete',
            target_type='detection', target_id=snapshot['id'],
            target_repr=f"{snapshot['user']} · {snapshot['result']}",
            detail=(f"删除识别记录 #{snapshot['id']}"
                    f"（{snapshot['user']} · {snapshot['result']}），图片文件一并删除"),
            request=request,
        )
        return Response({'detail': '已删除', 'id': snapshot['id']},
                        status=status.HTTP_200_OK)
