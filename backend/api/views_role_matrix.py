"""
权限矩阵的只读接口（第 179 批）
================================================================================

    GET /api/admin/role-matrix/

给控制台"开通编辑员 / 改角色"的对话框用：勾了哪几个模块，旁边就实时列出
"他能进哪几页、能做哪几件事" —— 授权的人不必凭记忆猜，也不会把"内容审核"
当成"新闻管理"勾错。

数据**不在这里重写**：直接调 `api/role_matrix.matrix_payload()`（与自查命令同一份）。
"""
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .capabilities import CAP_USER_ADMIN, has_capability
from .role_matrix import matrix_payload


class AdminRoleMatrixView(APIView):
    """
    权限矩阵（只读）

    权限用 `USER_ADMIN` —— 与"能给人授权"的那档人**完全一致**：
    能勾模块的人本来就该知道每个模块是干什么的；看不到这一页的人也不需要它。
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not has_capability(request.user, CAP_USER_ADMIN):
            return Response({'detail': '只有用户管理员可以查看权限矩阵'},
                            status=403)
        return Response(matrix_payload())
