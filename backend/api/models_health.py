"""
系统健康快照（第 158 批）

## 为什么要有它

第 157 批把 `check_env` 的检查搬到了管理端「系统健康」页。但那一页是**当下**的状态 ——
它回答"现在有没有事"，回答不了**"这周备份跑了没有"**。

而环境类故障的共性是**安静**：定时任务挂了、磁盘快满了、注销到期任务没执行，
都不会有人来报错；等到真出事那天，回头看只有一片空白。
所以每天记一条快照，页面就能画出趋势 —— **"最新备份是 3 天前"和"这 14 天备份一直在跑"
是两种完全不同的安心程度**。

## 设计取舍

1. **只存摘要，不存全量结果**：每天一条，字段是"总体等级 + 问题数 + 提示数 + 数据量 JSON"。
   全量 `results`（29 条文本）每天都存一份，一年就是一万多条重复文本，收益却为零 ——
   要细节随时能在页面上现跑一次。
2. **一天一条**：`snapshot_date` 唯一，重复执行只更新当天那条（定时任务重复跑不会堆垃圾）。
3. **保留期由命令的 `--days` 控制**（默认 180 天），过期自动清理。
"""
from django.db import models


class HealthSnapshot(models.Model):
    """某一天的系统健康摘要"""

    LEVEL_CHOICES = (
        ('ok', '正常'),
        ('warn', '有提示'),
        ('fail', '有问题'),
    )

    #: 快照日期（唯一：一天只留一条，重复执行更新当天）
    snapshot_date = models.DateField('日期', unique=True, db_index=True)
    level = models.CharField('总体等级', max_length=8, choices=LEVEL_CHOICES, default='ok')
    problem_count = models.PositiveIntegerField('问题数', default=0)
    warning_count = models.PositiveIntegerField('提示数', default=0)
    #: 数据量概览（users/posts/comments/detections/feedback/media_mb…）
    counts = models.JSONField('数据量', default=dict, blank=True)
    #: 问题与提示的**前几条**（够画 tooltip / 事后回忆即可，不存全量）
    notes = models.TextField('要点', blank=True, default='')
    created_at = models.DateTimeField('记录时间', auto_now_add=True)

    class Meta:
        verbose_name = '系统健康快照'
        verbose_name_plural = verbose_name
        ordering = ['-snapshot_date']

    def __str__(self):
        return f'{self.snapshot_date} {self.get_level_display()}'
