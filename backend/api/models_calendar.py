"""
种植日历模型（第 47 批）

背景：清单里"种植日历"此前完全没有。

**内容来源说明（很重要）**：本系统没有农技站的本地化农时数据，
所以日历由两部分组成，且明确区分：
  ① **通用农事模板**（`source='通用模板'`）—— 常见的、公开的农事时间节点
     （育苗/定植/水肥/防病/采收/越冬），由管理员维护，可改成适合本地的版本；
  ② **站内真实统计** —— 该作物在**这个月份**历史上检出过哪些病害、检出多少次，
     完全来自本站识别记录（这部分不做任何编造）。

模型只存①；② 由 `services_calendar.py` 实时统计。
"""
from django.conf import settings
from django.db import models


class CalendarTask(models.Model):
    """某作物在某个月的农事任务"""

    TASK_TYPES = (
        ('nursery', '育苗'),
        ('sowing', '整地播种'),
        ('planting', '定植'),
        ('fertilizer', '水肥管理'),
        ('pruning', '修剪整枝'),
        ('pest_control', '病害防治'),
        ('harvest', '采收'),
        ('winter', '越冬管理'),
        ('other', '其它'),
    )

    crop_type = models.CharField('作物', max_length=100, db_index=True)
    #: 1~12；用 SmallIntegerField 便于按月份范围查询
    month = models.PositiveSmallIntegerField('月份', db_index=True)
    task_type = models.CharField('农事类型', max_length=20, choices=TASK_TYPES, default='other')
    title = models.CharField('任务标题', max_length=120)
    detail = models.TextField('要点说明', blank=True, default='')
    # 第 72 批：农事任务也是"内容数据"，英文界面下需要英文标题与要点
    title_en = models.CharField('任务标题（英文）', max_length=120, blank=True, default='')
    detail_en = models.TextField('要点说明（英文）', blank=True, default='')
    #: 内容来源：通用模板 / 管理员录入（对外展示时会标明，避免把模板当成专家建议）
    source = models.CharField('来源', max_length=40, default='通用模板')
    is_active = models.BooleanField('启用', default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='calendar_tasks', verbose_name='创建人',
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '种植日历任务'
        verbose_name_plural = verbose_name
        ordering = ['crop_type', 'month', 'task_type']
        unique_together = ('crop_type', 'month', 'title')
        indexes = [models.Index(fields=['month', 'crop_type'])]

    def __str__(self):
        return f'{self.crop_type} {self.month}月 · {self.title}'
