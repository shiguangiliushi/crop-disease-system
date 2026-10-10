"""
批量接口的公共校验（第 147 批）

## 为什么单独一个模块

项目里已经有两条批量接口（反馈的批量改状态/批量删除），第 147 批又加了帖子的批量删除。
"批量接口各自写一套更松的校验"是这类漏洞最常见的形态 —— 单条接口校验很全，
批量接口为了图快自己写一套，于是变成绕过校验的后门。
所以 ids 的解析只有这一份，谁用谁调。

## 校验（每条都对应一种真实事故）

1. **必须是数组**：不然 `for value in 'abc'` 会把字符串逐字符拆成 ['a','b','c']；
2. **逐项转 int，转不了的丢掉**：前端传 `3` 或 `"3"` 都收；
3. **去重**：同一条传两次不该被处理两次（删除/审核都有副作用）；
4. **上限**：一次点几千条会让请求超时；上限让"误点全选"变成一次 400 而不是一次长事务。
"""
from rest_framework import status
from rest_framework.response import Response

#: 单次批量操作的条数上限（各接口一致）
MAX_BULK_ITEMS = 200


def parse_ids(raw_ids, *, label='记录', max_items=MAX_BULK_ITEMS):
    """
    解析批量接口的 `ids`

    :param raw_ids: 请求体里的 ids（任何类型都收，非数组会被拒）
    :param label: 提示语里的名词（"反馈" / "帖子"），让报错读起来自然
    :returns: `(ids, error_response)` —— 成功时 error_response 为 None
    """
    if raw_ids is None:
        raw_ids = []
    if not isinstance(raw_ids, (list, tuple)):
        return None, Response({'ids': ['ids 必须是数组']}, status=status.HTTP_400_BAD_REQUEST)

    ids = []
    for value in raw_ids:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue

    seen = set()
    ids = [i for i in ids if not (i in seen or seen.add(i))]

    if not ids:
        return None, Response({'ids': [f'没有选中任何{label}']},
                              status=status.HTTP_400_BAD_REQUEST)
    if len(ids) > max_items:
        return None, Response({'ids': [f'一次最多处理 {max_items} 条']},
                              status=status.HTTP_400_BAD_REQUEST)
    return ids, None
