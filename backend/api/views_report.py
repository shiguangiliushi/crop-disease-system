"""
举报接口（第 41 批）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/reports/` | POST | 提交举报（帖子/评论/用户） |
| `/api/reports/` | GET | 我的举报记录（管理员默认看全部，`?status=pending` 筛选） |
| `/api/reports/<id>/handle/` | POST | 处理举报（仅管理员）：`status` + `note` + 可选 `hide_content` |

规则：
  · 不能举报自己发的内容；
  · 同一个人对同一个目标只能举报一次（`target_key` 唯一约束，重复提交返回 400 并给出友好提示）；
  · 新举报会给**全体管理员**发通知；处理结果会给**举报人**发通知。
"""
import logging

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models_forum import Comment, Post
from .models_report import Report

logger = logging.getLogger(__name__)
User = get_user_model()


def _is_admin(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_staff or user.is_superuser or getattr(user, 'role', None) == 'ADMIN')
    )


def _serialize(report, request=None):
    """举报记录（列表与详情共用的小序列化）"""
    return {
        'id': report.id,
        'target_type': report.target_type,
        'target_type_display': report.get_target_type_display(),
        'target_key': report.target_key,
        'target_label': report.target_label,
        'reason': report.reason,
        'reason_display': report.get_reason_display(),
        'detail': report.detail,
        'status': report.status,
        'status_display': report.get_status_display(),
        'handle_note': report.handle_note,
        'handled_at': report.handled_at,
        'created_at': report.created_at,
        'reporter': {
            'id': report.reporter_id,
            'username': report.reporter.username if report.reporter else '未知',
        },
        'handler_name': report.handler.username if report.handler_id else None,
        # 便于前端"点进去看看被举报的内容"
        'post_id': report.post_id,
        'comment_id': report.comment_id,
        'target_user_id': report.target_user_id,
    }


class ReportViewSet(APIView):
    """举报的提交与查询（用 APIView 手写，避免再引一个 router）"""
    permission_classes = [permissions.IsAuthenticated]

    # ---------- 列表 ----------
    def get(self, request):
        queryset = Report.objects.select_related('reporter', 'handler', 'post', 'comment', 'target_user')

        if _is_admin(request.user):
            status_param = (request.query_params.get('status') or '').strip()
            if status_param in {choice[0] for choice in Report.STATUS_CHOICES}:
                queryset = queryset.filter(status=status_param)
        else:
            # 普通用户只能看到自己提交的举报
            queryset = queryset.filter(reporter=request.user)

        total = queryset.count()
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = min(50, max(1, int(request.query_params.get('page_size', 20))))
        except (TypeError, ValueError):
            page_size = 20

        start = (page - 1) * page_size
        rows = queryset[start:start + page_size]

        pending = queryset.filter(status='pending').count() if _is_admin(request.user) else 0
        return Response({
            'count': total,
            'pending': pending,
            'page': page,
            'page_size': page_size,
            'results': [_serialize(row, request) for row in rows],
        })

    # ---------- 提交 ----------
    def post(self, request):
        target_type = (request.data.get('target_type') or '').strip()
        reason = (request.data.get('reason') or 'other').strip()
        detail = (request.data.get('detail') or '').strip()[:500]

        if target_type not in {choice[0] for choice in Report.TARGET_CHOICES}:
            return Response({'detail': '举报对象类型不合法'}, status=status.HTTP_400_BAD_REQUEST)
        if reason not in {choice[0] for choice in Report.REASON_CHOICES}:
            reason = 'other'

        # 解析目标
        post = comment = target_user = None
        raw_id = request.data.get('target_id')
        try:
            target_id = int(raw_id)
        except (TypeError, ValueError):
            return Response({'detail': '缺少有效的举报对象'}, status=status.HTTP_400_BAD_REQUEST)

        if target_type == 'post':
            post = Post.objects.filter(pk=target_id).select_related('author').first()
            if not post:
                return Response({'detail': '帖子不存在或已被删除'}, status=status.HTTP_404_NOT_FOUND)
            owner = post.author
        elif target_type == 'comment':
            comment = Comment.objects.filter(pk=target_id).select_related('author').first()
            if not comment:
                return Response({'detail': '评论不存在或已被删除'}, status=status.HTTP_404_NOT_FOUND)
            owner = comment.author
        else:
            target_user = User.objects.filter(pk=target_id).first()
            if not target_user:
                return Response({'detail': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)
            owner = target_user

        # 不能举报自己（自己的帖子/评论/账号都不行）
        if owner and owner.id == request.user.id:
            return Response({'detail': '不能举报自己的内容'}, status=status.HTTP_400_BAD_REQUEST)

        target_key = f'{target_type}:{target_id}'

        # 先显式查一次重复：直接靠捕获 IntegrityError 是不够的 ——
        # 在事务里（如 TestCase / ATOMIC_REQUESTS）捕获 IntegrityError 之后继续查库会抛
        # TransactionManagementError（"当前事务已损坏"）。所以：
        #   ① 先查一次给出友好提示；② 真并发时用保存点（atomic）兜住唯一约束。
        if Report.objects.filter(reporter=request.user, target_key=target_key).exists():
            return Response({'detail': '你已经举报过这条内容了，管理员会尽快处理'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                report = Report.objects.create(
                    reporter=request.user, target_type=target_type, target_key=target_key,
                    post=post, comment=comment, target_user=target_user,
                    reason=reason, detail=detail,
                )
        except IntegrityError:
            return Response({'detail': '你已经举报过这条内容了，管理员会尽快处理'},
                            status=status.HTTP_400_BAD_REQUEST)

        self._notify_admins(report)
        logger.info('新增举报 id=%s type=%s key=%s by=%s', report.id, target_type, target_key, request.user.id)
        return Response(_serialize(report, request), status=status.HTTP_201_CREATED)

    def _notify_admins(self, report):
        try:
            from .views_notify import notify
            for admin in User.objects.filter(is_staff=True, is_active=True):
                notify(
                    admin,
                    type='system',
                    title=f'收到新的举报：{report.get_reason_display()}',
                    message=f'{report.reporter.username} 举报了 {report.target_label}',
                    url='/admin/review',
                    actor=report.reporter,
                )
        except Exception:
            logger.exception('发送举报通知失败 report=%s', report.id)


class ReportHandleView(APIView):
    """
    处理举报（仅管理员）

    POST /api/reports/<id>/handle/  {status: handled|rejected, note: '...', hide_content: true}
    · `hide_content=true` 时，若举报对象是帖子 → 置为 hidden（用户端不再可见）；
      是评论 → 软删除（与评论删除同一套语义）。
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not _is_admin(request.user):
            return Response({'detail': '只有管理员可以处理举报'}, status=status.HTTP_403_FORBIDDEN)

        report = Report.objects.filter(pk=pk).select_related('reporter', 'post', 'comment').first()
        if not report:
            return Response({'detail': '举报记录不存在'}, status=status.HTTP_404_NOT_FOUND)

        new_status = (request.data.get('status') or '').strip()
        if new_status not in ('handled', 'rejected'):
            return Response({'detail': '处理结果只能是 handled 或 rejected'},
                            status=status.HTTP_400_BAD_REQUEST)

        note = (request.data.get('note') or '').strip()[:300]
        hide_content = bool(request.data.get('hide_content'))

        report.status = new_status
        report.handle_note = note
        report.handler = request.user
        report.handled_at = timezone.now()
        report.save(update_fields=['status', 'handle_note', 'handler', 'handled_at'])

        hidden_note = ''
        if hide_content:
            if report.post_id and report.post:
                report.post.status = 'hidden'
                report.post.save(update_fields=['status'])
                hidden_note = '，相关内容已隐藏'
            elif report.comment_id and report.comment:
                report.comment.content = '[已被管理员隐藏]'
                report.comment.is_deleted = True
                report.comment.save(update_fields=['content', 'is_deleted', 'updated_at'])
                report.comment.post.update_comment_count()
                hidden_note = '，相关评论已隐藏'

        # 结果通知举报人（举报"有回音"才有人愿意继续举报）
        try:
            from .views_notify import notify
            verb = '已处理' if new_status == 'handled' else '已驳回'
            verb_en = 'handled' if new_status == 'handled' else 'rejected'
            notify(
                report.reporter,
                type='system',
                title=f'你的举报{verb}',
                title_en=f'Your report was {verb_en}',
                message=(note or f'关于「{report.target_label}」的举报{verb}') + hidden_note,
                url='/notifications',
                actor=request.user,
            )
        except Exception:
            logger.exception('发送举报处理通知失败 report=%s', report.id)

        logger.info('举报已处理 id=%s status=%s by=%s hide=%s', report.id, new_status, request.user.id, hide_content)
        return Response({**_serialize(report, request), 'hidden_content': bool(hidden_note)})
