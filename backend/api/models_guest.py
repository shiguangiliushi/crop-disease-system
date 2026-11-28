"""游客试用（第 439 批）：**日额度**表。

## 为什么额度落库，而不是塞进 cache

本项目的默认生产缓存是 **LocMemCache**（`settings.py` 里写明了：没配
`DJANGO_CACHE_URL` 时回落 LocMem 并给出警告）。LocMem 是**进程内**的 ——
gunicorn 起 4 个 worker，“3 次/天”就会变成 “12 次/天”，而且**没有任何报错**。
所以额度必须落库；DRF 的限流只负责挡“一秒内连点 50 次”这种突发。

## 为什么按 (IP 哈希, 自然日) 而不是按 token

游客身份是可以随手重建的（清 localStorage 再进一次就是新 token）。
**身份与额度必须解耦**：只要额度按 IP 计，换身份不会带来新额度。
反过来，如果额度挂在 token 上，清一下浏览器存储就等于无限次。

## 为什么只存哈希

这张表是"防刷计数器"，不是审计表 —— 没有保留明文 IP 的必要。
明文 IP 已经有它的合法去处（`AdminAuditLog.ip`，运维排障用）。
"""
from __future__ import annotations

from django.db import models


class GuestTrialQuota(models.Model):
    """(IP 哈希, 自然日) 一行，两个计数器：当日已用识别、已用问答。"""

    #: `sha256(f'{SECRET_KEY}:{ip}')` 前 16 位十六进制 —— 不可反推，够做去重键
    ip_hash = models.CharField(max_length=64, verbose_name='IP 哈希')
    day = models.DateField(verbose_name='自然日（服务器时区）')
    detects = models.PositiveSmallIntegerField(default=0, verbose_name='当日已识别次数')
    asks = models.PositiveSmallIntegerField(default=0, verbose_name='当日已问答次数')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='最近一次扣减')

    class Meta:
        verbose_name = '游客试用额度'
        verbose_name_plural = verbose_name
        constraints = [
            # 一天一行：扣减靠 `UPDATE ... WHERE detects < 上限`，靠这条约束保证唯一行
            models.UniqueConstraint(fields=['ip_hash', 'day'], name='guest_quota_uniq'),
        ]
        indexes = [
            # prune/统计按日期清理
            models.Index(fields=['day'], name='guest_quota_day_idx'),
        ]

    def __str__(self):
        return f'{self.ip_hash[:8]} {self.day} detect={self.detects} ask={self.asks}'
