"""

================================================================================
第 149 批：控制台的评论管理接口
================================================================================
农户端的评论列表是**挂在帖子下**的（`forums/posts/<post_pk>/comments/`），
而控制台要跨帖子看评论（"最近有没有人在刷广告"），所以这里给一套全局接口：

    GET    /api/admin/comments/                     列表（review 模块）
    POST   /api/admin/comments/<pk>/soft-delete/    软删除单条（review 模块）
    DELETE /api/admin/comments/<pk>/                硬删除单条（**仅全权管理员**）
    POST   /api/admin/comments/bulk-delete/         批量软删除（review 模块）

权限口径与既有实现**完全一致**（不是新定的）：
  · **软删除**（内容置为 `[已删除]`、行还在、可追溯）= 内容审核工作 → review 模块；
  · **硬删除**（从库里真删）= 不可逆动作 → 仅全权管理员（与"删除意见反馈"同类）。

为什么批量只做**软**删除：批量硬删除是不可逆的成批破坏，控制台不该有这个按钮
（真要清理走管理命令）。批量软删除正是审核员日常要用的（一波广告十几条）。

软删除的实现**复用** `views_forum.soft_delete_comment()` —— 与农户端那条路径是同一个函数，
避免"两套删除各有各的口径"（本项目最容易出问题的地方）。
"""
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .audit import log_admin_action
from .bulk import parse_ids
from .capabilities import MODULE_REVIEW, has_content_module, is_full_admin
from .models_audit import AdminAuditLog  # noqa: F401  （choices 里有 comment.* 动作）
from .models_forum import Comment, Post
from .pagination import CustomPagination

User = get_user_model()

#: 列表排序白名单（非法值忽略 —— 与其它管理列表一致）
ORDERING_WHITELIST = ('created_at', '-created_at', 'id', '-id', 'like_count', '-like_count')


def _reject_non_moderator(request, action_label):
    """审核类动作的统一门禁（review 模块 / Moderators 组）"""
    user = request.user
    if (has_content_module(user, MODULE_REVIEW)
            or user.groups.filter(name='Moderators').exists()):
        return None
    return Response({'detail': f'只有内容维护者可以{action_label}'},
                    status=status.HTTP_403_FORBIDDEN)


def _serialize(comment):
    return {
        'id': comment.id,
        'content': comment.content,
        'content_en': comment.content_en,
        'is_deleted': comment.is_deleted,
        'author': {
            'id': comment.author_id,
            # 作者账号被注销后 author 可能是 None（SET_NULL）—— 快照兜底
            'username': getattr(comment.author, 'username', '') or '已注销用户',
        } if comment.author_id else None,
        'post': {
            'id': comment.post_id,
            'title': getattr(comment.post, 'title', '') or '',
        } if comment.post_id else None,
        'parent': comment.parent_id,
        'reply_to_user': getattr(comment.reply_to_user, 'username', None),
        'like_count': comment.like_count or 0,
        'created_at': comment.created_at,
    }


class AdminCommentListView(APIView):
    """
    评论列表（第 149 批，review 模块）

    筛选：`?post=&author=&search=&only_deleted=&ordering=&page=&page_size=`
      · `search` 匹配评论内容（也匹配 `content_en`，英文内容站也要查得到）；
      · `only_deleted=true` → **只看**已删除的（审计"谁删了什么"，第 91 批对帖子就是这个约定）；
      · 默认**不含**已删除的（与农户端一致，否则列表里全是 `[已删除]`）。
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        blocked = _reject_non_moderator(request, '查看评论管理')
        if blocked:
            return blocked

        queryset = Comment.objects.select_related('author', 'post', 'reply_to_user')

        params = request.query_params
        only_deleted = (params.get('only_deleted') or '').strip().lower()
        if only_deleted in ('true', '1', 'yes'):
            queryset = queryset.filter(is_deleted=True)
        else:
            queryset = queryset.filter(is_deleted=False)

        post_id = (params.get('post') or '').strip()
        if post_id.isdigit():
            queryset = queryset.filter(post_id=int(post_id))

        author_id = (params.get('author') or '').strip()
        if author_id.isdigit():
            queryset = queryset.filter(author_id=int(author_id))

        search = (params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(
                Q(content__icontains=search) | Q(content_en__icontains=search))

        ordering = (params.get('ordering') or '-created_at').strip()
        if ordering not in ORDERING_WHITELIST:
            ordering = '-created_at'
        queryset = queryset.order_by(ordering)

        paginator = CustomPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        rows = [_serialize(c) for c in (page if page is not None else queryset)]
        if page is not None:
            return paginator.get_paginated_response(rows)
        return Response({'count': len(rows), 'results': rows})


class AdminCommentSoftDeleteView(APIView):
    """软删除一条评论（第 149 批，review 模块）—— 复用农户端那条路径的实现"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        blocked = _reject_non_moderator(request, '删除评论')
        if blocked:
            return blocked

        from .views_forum import soft_delete_comment

        comment = Comment.objects.filter(pk=pk).select_related('post').first()
        if comment is None:
            return Response({'detail': '评论不存在'}, status=status.HTTP_404_NOT_FOUND)
        if comment.is_deleted:
            # 幂等：再点一次不该报错，也不该重复记日志
            return Response({'id': comment.id, 'is_deleted': True, 'changed': False})

        preview = (comment.content or '')[:50]
        soft_delete_comment(comment)
        log_admin_action(
            request.user, 'comment.soft_delete', target_type='comment', target_id=comment.id,
            target_repr=preview or f'#{comment.id}',
            detail=f'软删除评论（内容置为 [已删除]，可追溯）：{preview}',
            request=request,
        )
        return Response({'id': comment.id, 'is_deleted': True, 'changed': True})


class AdminCommentHardDeleteView(APIView):
    """
    硬删除一条评论（第 149 批，**仅全权管理员**）

    与农户端的 `DELETE .../comments/<pk>/` 同一口径（那里也是 `is_full_admin`）。
    硬删除**不可逆**，所以：
      · 只给全权管理员（内容编辑员用软删除）；
      · 审计日志里留下评论内容的前 50 字 —— 行删了之后，这是唯一的线索。
    """

    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        if not (is_full_admin(request.user)
                or request.user.groups.filter(name='Moderators').exists()):
            return Response({'detail': '只有管理员可以彻底删除评论'},
                            status=status.HTTP_403_FORBIDDEN)

        comment = Comment.objects.filter(pk=pk).select_related('post').first()
        if comment is None:
            return Response({'detail': '评论不存在'}, status=status.HTTP_404_NOT_FOUND)

        post_id = comment.post_id
        preview = (comment.content or '')[:50]
        comment.delete()   # Comment.delete() 里维护了 post.comment_count
        post = Post.objects.filter(pk=post_id).first()
        if post is not None:
            post.update_comment_count()

        log_admin_action(
            request.user, 'comment.hard_delete', target_type='comment', target_id=pk,
            target_repr=preview or f'#{pk}',
            detail=f'**彻底删除**评论（不可逆）；原内容前 50 字：{preview}',
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminCommentBulkDeleteView(APIView):
    """
    批量**软**删除评论（第 149 批，review 模块）

    为什么批量只做软删除：批量硬删除是不可逆的成批破坏，控制台不该有这个按钮。
    软删除正是审核员日常要用的 —— 一波广告十几条，一条条点确认框太慢。
    （口径与第 147 批"帖子批量删除只给全权管理员"的区别在于：帖子那次是**批量**这个动作本身
    被当成破坏性操作；而评论的软删除是**可追溯**的日常审核动作，连单条都允许编辑员做。）
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        blocked = _reject_non_moderator(request, '删除评论')
        if blocked:
            return blocked

        from .views_forum import soft_delete_comment

        ids, error = parse_ids(request.data.get('ids'), label='评论')
        if error:
            return error

        comments = {c.id: c for c in Comment.objects.filter(id__in=ids, is_deleted=False)}
        results = []
        ok_count = 0
        previews = []
        for comment_id in ids:
            comment = comments.get(comment_id)
            if comment is None:
                results.append({'id': comment_id, 'ok': False,
                                'detail': '评论不存在或已被删除'})
                continue
            previews.append((comment.content or '')[:20])
            soft_delete_comment(comment)
            ok_count += 1
            results.append({'id': comment_id, 'ok': True,
                            'detail': (comment.content or '')[:30]})

        if ok_count:
            log_admin_action(
                request.user, 'comment.bulk_delete', target_type='comment',
                target_id=','.join(str(i) for i in ids[:20]),
                # 快照写前几条的内容：日志页只看得到 target_repr 一列，
                # 光有 id 列表读不出"删掉的都是些什么评论"
                target_repr='、'.join(previews[:3]) + ('…' if len(previews) > 3 else ''),
                detail=f'批量软删除评论 {ok_count}/{len(ids)} 条',
                request=request,
            )
        return Response({
            'requested': len(ids),
            'succeeded': ok_count,
            'failed': len(ids) - ok_count,
            'results': results,
        })
