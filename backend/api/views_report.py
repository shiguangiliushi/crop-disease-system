"""
举报接口（第 41 批）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/reports/` | POST | 提交举报（帖子/评论/用户） |
| `/api/reports/` | GET | 举报记录（有 review/forum 模块的人看全部，其余人只看自己提交的） |
| `/api/reports/<id>/handle/` | POST | 处理举报（review/forum 模块或全权管理员） |

规则：
  · 不能举报自己发的内容；
  · 同一个人对同一个目标只能举报一次（`target_key` 唯一约束，重复提交返回 400 并给出友好提示）；
  · 新举报会给**全体管理员**发通知；处理结果会给**举报人**发通知。

第 189 批：举报的权限从"仅全权管理员"改成**三层**（编辑员能管线索，但看不到举报人）——
详见 `_can_handle_reports()` 与 `_can_see_reporter()` 的 docstring。改动原因（用户反馈）：
信息编辑员在「内容管理」里能管帖子与评论，却**完全看不到举报页签**，于是"已经有人在举报"
这件事他永远不知道。
"""
import logging

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q  # 第 124 批：举报通知收件人按完整管理员口径筛
from django.utils import timezone
from rest_framework import permissions, status
# 第 124 批：口径统一收口；第 189 批起举报按**三层**分权（见 _can_handle_reports 的说明）：
#   看自己的举报 = 任何登录用户；看别人的举报并处置 = review/forum 模块；
#   看举报人身份 + 同时下架内容 = 仅全权管理员。
from .capabilities import has_content_module, is_full_admin
from rest_framework.response import Response
from rest_framework.views import APIView

from .models_forum import Comment, Post
from .models_report import Report
from .i18n import render_for  # 第 277 批：举报/反馈文案多语言

logger = logging.getLogger(__name__)
User = get_user_model()


def _can_handle_reports(user):
    """
    能否**看别人的举报并处置**（内容编辑员的 review/forum 模块，或全权管理员）

    第 189 批改口径（此前是 `is_full_admin`，编辑员完全看不到举报）。改的理由：
    编辑员本来就在「内容管理」里管帖子与评论（能驳回/下架），**举报只是"线索入口"** ——
    不给他看，他就只能自己去翻帖子发现问题，而"已经有人在举报这件事"他永远不知道。

    但举报与帖子/评论有两处**实质差别**，所以**只放开一半**：

      · 举报回包带 `reporter.username`（**谁举报的**）与 `target_user_id`（可定位到人）。
        这是"他人数据"，编辑员不需要它也能办事 —— 见 `_can_see_reporter()`：
        **只有全权管理员能看到举报人身份**，编辑员看到的是匿名化后的回包。
      · `hide_content=true`（下架内容）在本模块里是**不可逆**动作，按项目一贯口径
        （见 `capabilities.py`：不可逆动作只给全权管理员）仍然只给全权管理员。

    于是分三层，别把它们混成一条：
      · 看"自己提交的举报"：任何登录用户（第 41 批口径，不变）；
      · 看**别人的**举报 + 处置（handled/rejected）：`review`/`forum` 模块；
      · 看举报人是谁 + 同时下架内容：仅全权管理员。
    """
    if is_full_admin(user):
        return True
    return any(has_content_module(user, module) for module in ('review', 'forum'))


def _can_see_reporter(user):
    """
    能否看到**举报人身份**（`reporter.username`）与被举报人 id

    第 189 批：`_can_handle_reports()` 放开给编辑员之后，这一条守住隐私 ——
    编辑员能处理举报，但**不该知道是谁举报的**（否则举报人可能被针对）。
    另：`handler_name` 照常返回（那是编辑员自己的名字，也是审计信息）。
    """
    return is_full_admin(user)


def _serialize(report, request=None):
    """举报记录（列表与详情共用的小序列化）"""
    user = getattr(request, 'user', None)
    # 未认证/匿名时按"不能看身份"处理（这个接口本身要求登录，这里只是兜底）
    show_reporter = bool(user is not None and getattr(user, 'is_authenticated', False)
                         and _can_see_reporter(user))
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
        # 第 189 批：举报人身份只给全权管理员（编辑员看到的是 None + 标记）
        # 前端据此显示"举报人已隐去"，而不是显示一个空字符串装作有名字
        'reporter': {
            'id': report.reporter_id if show_reporter else None,
            'username': (report.reporter.username if (show_reporter and report.reporter) else None),
        },
        'reporter_hidden': not show_reporter,
        'handler_name': report.handler.username if report.handler_id else None,
        # 便于前端"点进去看看被举报的内容"
        'post_id': report.post_id,
        'comment_id': report.comment_id,
        # 第 189 批：被举报人 id 同样是"定位到人"的信息，只给全权管理员
        'target_user_id': report.target_user_id if show_reporter else None,
    }


class ReportViewSet(APIView):
    """举报的提交与查询（用 APIView 手写，避免再引一个 router）"""
    permission_classes = [permissions.IsAuthenticated]

    # ---------- 列表 ----------
    def get(self, request):
        queryset = Report.objects.select_related('reporter', 'handler', 'post', 'comment', 'target_user')

        if _can_handle_reports(request.user):
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

        pending = queryset.filter(status='pending').count() if _can_handle_reports(request.user) else 0
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
            return Response({'detail': render_for(request, 'report.bad_type')}, status=status.HTTP_400_BAD_REQUEST)
        if reason not in {choice[0] for choice in Report.REASON_CHOICES}:
            reason = 'other'

        # 解析目标
        post = comment = target_user = None
        raw_id = request.data.get('target_id')
        try:
            target_id = int(raw_id)
        except (TypeError, ValueError):
            return Response({'detail': render_for(request, 'report.missing_target')}, status=status.HTTP_400_BAD_REQUEST)

        if target_type == 'post':
            post = Post.objects.filter(pk=target_id).select_related('author').first()
            if not post:
                return Response({'detail': render_for(request, 'report.post_gone')}, status=status.HTTP_404_NOT_FOUND)
            owner = post.author
        elif target_type == 'comment':
            comment = Comment.objects.filter(pk=target_id).select_related('author').first()
            if not comment:
                return Response({'detail': render_for(request, 'report.comment_gone')}, status=status.HTTP_404_NOT_FOUND)
            owner = comment.author
        else:
            target_user = User.objects.filter(pk=target_id).first()
            if not target_user:
                return Response({'detail': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)
            owner = target_user

        # 不能举报自己（自己的帖子/评论/账号都不行）
        if owner and owner.id == request.user.id:
            return Response({'detail': render_for(request, 'report.self')}, status=status.HTTP_400_BAD_REQUEST)

        target_key = f'{target_type}:{target_id}'

        # 先显式查一次重复：直接靠捕获 IntegrityError 是不够的 ——
        # 在事务里（如 TestCase / ATOMIC_REQUESTS）捕获 IntegrityError 之后继续查库会抛
        # TransactionManagementError（"当前事务已损坏"）。所以：
        #   ① 先查一次给出友好提示；② 真并发时用保存点（atomic）兜住唯一约束。
        if Report.objects.filter(reporter=request.user, target_key=target_key).exists():
            return Response({'detail': render_for(request, 'report.duplicate')},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                report = Report.objects.create(
                    reporter=request.user, target_type=target_type, target_key=target_key,
                    post=post, comment=comment, target_user=target_user,
                    reason=reason, detail=detail,
                )
        except IntegrityError:
            return Response({'detail': render_for(request, 'report.duplicate')},
                            status=status.HTTP_400_BAD_REQUEST)

        self._notify_admins(report)
        logger.info('新增举报 id=%s type=%s key=%s by=%s', report.id, target_type, target_key, request.user.id)
        return Response(_serialize(report, request), status=status.HTTP_201_CREATED)

    def _notify_admins(self, report):
        """
        新举报 → 通知**能处理它的人**

        ⚠️ 第 189 批：收件人从"只有全权管理员"扩到"**有 review/forum 模块的编辑员 + 全体管理员**"
        —— 权限开了而通知不开，就会出现"编辑员能处理举报，却永远不知道有举报"
        （这正是第 124 批那次"只给管理员"留下的盲区）。文案里的"管理员"也随之改成中性的说法。
        """
        try:
            from .views_notify import notify
            recipients = User.objects.filter(is_active=True).filter(
                Q(is_staff=True) | Q(is_superuser=True) | Q(role='ADMIN')
                # 编辑员：只勾了 review 或 forum 的才算（其余模块的人不该被举报通知打扰）
                | Q(role='EDITOR', editor_modules__module__in=('review', 'forum'))
            ).distinct()
            for admin in recipients:
                notify(
                    admin,
                    type='system',
                    title=f'收到新的举报：{report.get_reason_display()}',
                    message=f'{report.reporter.username} 举报了 {report.target_label}',
                    # 第 183 批：举报处理搬进了「内容管理」页的**举报页签**
                    url='/admin/content?tab=reports',
                    actor=report.reporter,
                )
        except Exception:
            logger.exception('发送举报通知失败 report=%s', report.id)


class ReportHandleView(APIView):
    """
    处理举报（review/forum 模块或全权管理员）

    POST /api/reports/<id>/handle/  {status: handled|rejected, note: '...', hide_content: true}
    · `hide_content=true` 时，若举报对象是帖子 → 置为 hidden（用户端不再可见）；
      是评论 → 软删除（与评论删除同一套语义）。
    · ⚠️ 第 189 批：`hide_content` **只对全权管理员生效**。编辑员能处置举报（改状态 + 备注），
      但"下架内容"是不可逆动作，按项目口径仍只给全权管理员 —— 编辑员传 true 时**忽略**
      （并在响应里如实说明没隐藏），而不是给 403：他确实有权处理这条举报，
      只是没有"顺手抹掉内容"的那一档权限。
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not _can_handle_reports(request.user):
            return Response({'detail': '只有内容编辑员或管理员可以处理举报'},
                            status=status.HTTP_403_FORBIDDEN)

        report = Report.objects.filter(pk=pk).select_related('reporter', 'post', 'comment').first()
        if not report:
            return Response({'detail': '举报记录不存在'}, status=status.HTTP_404_NOT_FOUND)

        new_status = (request.data.get('status') or '').strip()
        if new_status not in ('handled', 'rejected'):
            return Response({'detail': '处理结果只能是 handled 或 rejected'},
                            status=status.HTTP_400_BAD_REQUEST)

        note = (request.data.get('note') or '').strip()[:300]
        # 第 189 批：下架内容是不可逆动作 → 只认全权管理员
        wants_hide = bool(request.data.get('hide_content'))
        can_hide = is_full_admin(request.user)
        hide_content = wants_hide and can_hide

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
        return Response({
            **_serialize(report, request),
            'hidden_content': bool(hidden_note),
            # 第 189 批：编辑员勾了"同时隐藏内容"但没这一档权限时，如实告诉他"没隐藏"，
            # 否则他会以为内容已经下架（静默忽略 = 更容易出事的那种"友好"）
            'hide_denied': bool(wants_hide and not can_hide),
        })
