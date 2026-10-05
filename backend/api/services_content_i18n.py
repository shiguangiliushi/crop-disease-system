"""
内容数据的中英对照（第 77 批）

背景
------------------------------------------------------------------
第 69/72 批把"病害名/作物名"这类**内容数据**的多语言交给后端的 `*_en` 字段，
前端用 `utils/localized.js` 的 `localizedField()` 取值。但那只覆盖了**对象型**
接口（百科列表/详情、识别记录），**聚合型**接口仍然只回中文名：

    /api/statistics/        pest_distribution / crop_distribution
    /api/calendar/          task_groups / my_crops / seasonal_pests / my_history
    /api/admin/dashboard/   pest_distribution / crop_distribution

于是英文界面下会出现"卡片标题是英文、里面的病害名还是中文"的半截翻译
（统计图的柱标签、饼图图例、种植日历的作物分组与右侧榜单都是这样）。
本模块提供映射表，让这几个接口把 `*_en` 一起带上。

为什么不用 `values('...', 'name_en')` 直接加一列
------------------------------------------------------------------
这些查询都是 `GROUP BY 中文名` 聚合出来的。把 `name_en` 塞进 `values()` 会让
分组键多一列：同一病害只要英文名有过改动（或存在空串），就会被拆成两行，
数量统计随之出错。所以这里**单独查一次映射表**，在 Python 侧补字段，
分组口径与改动前完全一致 —— 这是本模块存在的唯一理由。
"""
from .models import PestInfo


def pest_en_maps():
    """返回 `(病害中文名 → 英文名, 作物中文名 → 英文名)` 两个映射。

    同一个中文名出现多行时取第一条非空英文（setdefault 语义，结果稳定）。
    """
    name_map = {}
    crop_map = {}
    for name, name_en, crop_type, crop_type_en in PestInfo.objects.values_list(
        'name', 'name_en', 'crop_type', 'crop_type_en'
    ):
        if name and name_en and name not in name_map:
            name_map[name] = name_en
        if crop_type and crop_type_en and crop_type not in crop_map:
            crop_map[crop_type] = crop_type_en
    return name_map, crop_map


def crop_en(crop_type):
    """单个作物中文名 → 英文名（取不到返回空串，由调用方决定怎么兜底）"""
    if not crop_type:
        return ''
    value = (
        PestInfo.objects.filter(crop_type=crop_type)
        .exclude(crop_type_en='')
        .values_list('crop_type_en', flat=True)
        .first()
    )
    return value or ''
