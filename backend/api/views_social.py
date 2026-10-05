"""
关注 / 粉丝接口（第 40 批）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/users/<id>/follow/` | POST | 关注 / 取消关注（toggle，返回最新状态与粉丝数） |
| `/api/users/<id>/followers/` | GET | 该用户的粉丝列表（公开，分页） |
| `/api/users/<id>/following/` | GET | 该用户关注的人（公开，分页） |
| `/api/users/me/following/` | GET | 我关注的人（登录，便于"关注流"扩展） |

被关注的人会收到一条站内通知（`notify()` 内部跳过自己关注自己）。
"""
import logging

from django.contrib.auth import get_user_model
from django.db.models import Count
from rest_framework import permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models_social import Follow

logger = logging.getLogger(__name__)
User = get_user_model()


def _user_brief(user, request=None):
    """列表里展示的最小用户信息"""
    avatar = None
    if getattr(user, 'avatar', None):
        try:
            avatar = user.avatar.url
        except Exception:  # pragma: no cover - 文件缺失时不该 500
            avatar = None
        if avatar and request is not None:
            avatar = request.build_absolute_uri(avatar)
    return {
        'id': user.id,
        'username': user.username,
        'bio': user.bio or '',
        'avatar': avatar,
        'role': getattr(user, 'role', 'USER'),
    }


class FollowListView(APIView):
    """粉丝 / 关注列表（公开，分页）"""

    permission_classes = [permissions.AllowAny]

    def get(self, request, user_id=None, direction='followers'):
        # `/api/users/me/following/` 只传 direction（没有 user_id）→ 用当前登录用户
        if user_id is None:
            if not request.user.is_authenticated:
                return Response({'detail': '请先登录'}, status=status.HTTP_401_UNAUTHORIZED)
            user = request.user
        else:
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                return Response({'detail': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)

        if direction == 'followers':
            queryset = (
                Follow.objects.filter(following=user)
                .select_related('follower')
                .order_by('-created_at')
            )
            users = [row.follower for row in queryset]
        else:
            queryset = (
                Follow.objects.filter(follower=user)
                .select_related('following')
                .order_by('-created_at')
            )
            users = [row.following for row in queryset]

        # 当前登录用户与列表中每个人的关系（用于按钮状态），一次查完避免 N+1
        following_ids = set()
        if request.user.is_authenticated:
            following_ids = set(
                Follow.objects.filter(follower=request.user)
                .values_list('following_id', flat=True)
            )

        # 手动分页（列表是内存里的对象，不是 queryset）
        paginator = PageNumberPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(users, request, view=self)
        data = [
            {**_user_brief(item, request), 'is_following': item.id in following_ids,
             'is_self': item.id == getattr(request.user, 'id', None)}
            for item in (page if page is not None else users)
        ]
        if page is not None:
            return paginator.get_paginated_response(data)
        return Response({'count': len(data), 'results': data})


class FollowToggleView(APIView):
    """关注 / 取消关注（toggle）"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, user_id):
        try:
            target = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({'detail': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)

        if target.id == request.user.id:
            return Response({'detail': '不能关注自己'}, status=status.HTTP_400_BAD_REQUEST)

        relation = Follow.objects.filter(follower=request.user, following=target).first()
        if relation:
            relation.delete()
            is_following = False
            logger.debug('取消关注: %s → %s', request.user.id, target.id)
        else:
            Follow.objects.create(follower=request.user, following=target)
            is_following = True
            logger.debug('新增关注: %s → %s', request.user.id, target.id)
            self._notify(target, request.user)

        follower_count = Follow.objects.filter(following=target).count()
        return Response({
            'is_following': is_following,
            'follower_count': follower_count,
            'following_count': Follow.objects.filter(follower=request.user).count(),
        })

    def _notify(self, target, actor):
        """关注也发一条通知（复用第 37 批的通知体系）"""
        try:
            from .views_notify import notify
            notify(
                target,
                type='follow',
                title=f'{actor.username} 关注了你',
                title_en=f'{actor.username} started following you',
                message='去 TA 的主页看看吧',
                url=f'/user/profile/{actor.id}',
                actor=actor,
            )
        except Exception:
            logger.exception('发送关注通知失败 target=%s', target.id)

        # 第 42 批：被关注 +1 积分
        try:
            from .services_points import award_points
            award_points(target, 'follow_received', ref_type='user', ref_id=actor.id)
        except Exception:
            logger.exception('关注积分失败 target=%s', target.id)


class MyFollowingStatsView(APIView):
    """
    我自己的社交数据（关注数 / 粉丝数）—— 个人资料页用

    说明：`/api/users/{id}/` 已返回他人的关注/粉丝数（见 UserPublicProfileSerializer），
    这里额外提供"当前登录用户"的口径，避免前端为了自己还要多请求一次 profile。
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        following = Follow.objects.filter(follower=request.user).count()
        followers = Follow.objects.filter(following=request.user).count()
        return Response({'following_count': following, 'follower_count': followers})


class FollowSuggestionView(APIView):
    """
    推荐关注：最近活跃、且我还没关注的用户（Top 5）

    用途：用户资料页/首页给一个"可以关注谁"的入口 —— 否则新用户面对空主页无从下手。
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        queryset = User.objects.filter(is_active=True)
        if request.user.is_authenticated:
            followed = Follow.objects.filter(follower=request.user).values_list('following_id', flat=True)
            queryset = queryset.exclude(id__in=list(followed)).exclude(id=request.user.id)

        users = (
            queryset.annotate(followers=Count('follower_relations'))
            .order_by('-followers', '-last_login')[:5]
        )
        return Response({'results': [_user_brief(user, request) for user in users]})
