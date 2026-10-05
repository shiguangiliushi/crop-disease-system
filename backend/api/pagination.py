from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from urllib.parse import urlencode


class CustomPagination(PageNumberPagination):
    """
    项目统一分页器（第 106 批补说明）

    **这个类为什么存在**（别把它"简化"回 `PageNumberPagination`）
    ------------------------------------------------------------------
    DRF 自带的 `get_next_link()` / `get_previous_link()` 会**从当前 request 重新拼 URL**，
    而它只带 `page` 一个参数 —— 于是**筛选条件全丢**：
    在第 2 页点"下一页"，`?status=pending&page=3` 会变成 `?page=3`，
    用户看到的是"筛选莫名失效、列表突然变多"。这就是本类唯一的理由：
    把原始请求里的筛选参数重新附回 next/prev 链接（见 `_add_filter_params`）。
    把它换回 `PageNumberPagination` 会**静默重现**这个 bug。

    另外补了两个前端要用的字段：`current_page` / `total_pages`
    （前端分页器不想自己从 count + page_size 反算）。

    ⚠️ 关于"默认每页几条"——项目里有三个数字，别改错地方
    ------------------------------------------------------------------
    | 位置 | 值 | 是否生效 |
    |---|---|---|
    | 本类 `page_size = 6` | **6** | ✅ **这才是真实默认值** |
    | `settings.REST_FRAMEWORK['PAGE_SIZE']` | 5 | ❌ 不生效（DRF 只在使用自带分页器时读它） |
    | `news_views.StandardResultsSetPagination` | 10 | ✅ 但只作用于新闻接口 |

    所以要调"默认每页几条"，改这里；改 settings 里的 5 不会有任何效果。
    前端各页大多显式传 `page_size`，实际影响面有限。
    """

    page_size = 6  # 默认每页 6 条（见类说明：这是真正的默认值）
    page_size_query_param = 'page_size'
    # 上限 100：防止 `?page_size=999999` 一次性把整库拖出来（列表接口都靠它兜底）
    max_page_size = 100

    def get_paginated_response(self, data):
        # 获取基础分页响应
        response_data = {
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'current_page': self.page.number,
            'total_pages': self.page.paginator.num_pages,
            'results': data
        }

        # 添加分页信息
        return Response(response_data)

    def get_next_link(self):
        if not self.page.has_next():
            return None
        url = super().get_next_link()
        return self._add_filter_params(url) if url else None

    def get_previous_link(self):
        if not self.page.has_previous():
            return None
        url = super().get_previous_link()
        return self._add_filter_params(url) if url else None

    def _add_filter_params(self, url):
        """
        把原始请求里的**筛选参数**附回分页链接（本类存在的理由，见类说明）。

        步骤：取当前请求的全部 query params → 去掉 `page` / `page_size`
        （它们已经在新链接里了，重复会拼出 `?page=2&page=3`）→ 用 `urlencode(doseq=True)`
        追加（`doseq` 是为了让 `?tag=a&tag=b` 这种多值参数不至于被拍平成一个）。
        """
        # 获取原始请求参数
        request = self.request
        params = request.query_params.copy()

        # 移除分页相关参数，避免重复
        if 'page' in params:
            del params['page']
        if 'page_size' in params:
            del params['page_size']

        # 如果没有其他参数，直接返回原始URL
        # （这个分支是为了避免拼出一个孤零零的 `?`）
        if not params:
            return url

        # 将参数添加到URL中
        if '?' in url:
            return f"{url}&{urlencode(params, doseq=True)}"
        else:
            return f"{url}?{urlencode(params, doseq=True)}"
