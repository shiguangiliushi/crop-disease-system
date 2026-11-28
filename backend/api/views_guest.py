"""游客试用接口（第 439 批）：`/api/guest/session/` 与 `/api/guest/quota/`。

只有两个接口，因为"能不能用"的判定不在这里 ——
写权限闸门在 `authentication.GuestTokenAuthentication`，额度扣减在 `guest.consume()`。
这个文件只负责"开一个身份"和"如实报告还剩几次"。
"""
from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import guest, user_payload
from .models_token import device_of

logger = logging.getLogger(__name__)

#: 额度用尽时给用户看的话（按用途分开说，别让人以为是"系统坏了"）
_EXHAUSTED_TEXT = {
    'detect': '今天的试用识别次数已用完，注册后可以继续使用',
    'ask': '今天的试用问答次数已用完，注册后可以继续提问',
}


def charge(kind: str, request):
    """给游客扣一次额度。

    返回 `None` 表示放行；返回 `Response` 表示额度已满（调用方直接 `return` 它）。

    ⚠️ **登录用户不受影响**：这里第一行就判掉，不要把它做成"所有人共享 3 次"。
    """
    if not guest.is_guest(getattr(request, 'user', None)):
        return None
    allowed, _left = guest.consume(kind, request)
    if allowed:
        return None
    return quota_exceeded(kind, request)


def refund(kind: str, request) -> None:
    """把没用上的额度还回去（仅在"请求根本没跑起来"时调用，例如识别服务未初始化）。

    为什么不还"推理失败"：那种情况模型确实跑过、CPU 也确实被占用了；
    全部退还等于给了一个免费压测入口。
    """
    if guest.is_guest(getattr(request, 'user', None)):
        guest.refund(kind, request)


def quota_exceeded(kind: str, request) -> Response:
    """402 + 额度快照。

    为什么是 402 而不是 429：429 的语义是"你太快了，等一会儿"，
    而这里"等一会儿"没用 —— 要等到明天 0 点，或者注册。
    前端据 `code` 弹"注册继续"，据 `reset_at` 说明什么时候重置。
    """
    snap = guest.snapshot(request)
    return Response({
        'status': 'error',
        'code': 'GUEST_QUOTA_EXCEEDED',
        'message': _EXHAUSTED_TEXT.get(kind, '试用次数已用完'),
        'quota': snap,
        'reset_at': snap.get('resets_at'),
    }, status=status.HTTP_402_PAYMENT_REQUIRED)


class GuestSessionView(APIView):
    """开一次游客试用（或把已有身份原样返回）。

    - 匿名调用 → 建一个临时用户 + 签一张 token；
    - **已带游客 token** 再调用 → 返回同一个身份（刷新页面不该多建一个用户，
      否则"开 10 次页面 = 库里多 10 个账号"，而且额度还是按 IP 算，白建）。
    """

    permission_classes = [AllowAny]
    #: 第 439 批：游客重复开试用是合法动作（刷新页面会再调一次），
    #: 不加这一行会被 `GuestTokenAuthentication` 挡成 403。
    guest_allowed = True
    #: 这个接口会**建行**，必须限流。速率在 settings.DEFAULT_THROTTLE_RATES['guest_session']。
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'guest_session'

    @extend_schema(
        summary='开启游客试用',
        responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT},
        description='匿名调用即可。返回 token 与剩余额度；重复调用不会重复建账号。',
    )
    def post(self, request):
        if not guest.config()['enabled']:
            return Response({
                'status': 'error',
                'code': 'GUEST_TRIAL_DISABLED',
                'message': '试用功能当前未开放，请注册后使用',
            }, status=status.HTTP_403_FORBIDDEN)

        user = getattr(request, 'user', None)
        if guest.is_guest(user):
            # 已经有身份了：原样返回（token 就是这次请求用的那张）
            payload = user_payload.build(user, request)
            return Response({
                'status': 'success',
                'message': '试用已开启',
                'data': {
                    'user': payload,
                    'token': getattr(request.auth, 'key', '') or '',
                    'quota': guest.snapshot(request, user=user),
                },
            })

        user, token = guest.create_guest(device=device_of(request))
        logger.info('创建游客试用身份: user_id=%s', user.id)
        return Response({
            'status': 'success',
            'message': '已开启试用',
            'data': {
                'user': user_payload.build(user, request),
                'token': token.key,
                'quota': guest.snapshot(request, user=user),
            },
        }, status=status.HTTP_201_CREATED)


class GuestQuotaView(APIView):
    """查剩余额度。游客与登录用户都能调（登录用户返回 `unlimited: true`）。"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='查询试用额度',
        responses={200: OpenApiTypes.OBJECT},
        description='游客返回剩余次数与重置时间；登录用户返回 unlimited=true。',
    )
    def get(self, request):
        return Response({
            'status': 'success',
            'data': guest.snapshot(request),
        })
