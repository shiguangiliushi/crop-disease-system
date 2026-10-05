"""
"用户生成内容"的英文译文元数据（第 85 批）

============================================================================
为什么单独一个模块
----------------------------------------------------------------------------
第 85 批要给**用户写的内容**（论坛帖子/评论、意见反馈）补英文译文。这些内容
分散在 `models_forum.py` 与 `models.py` 两个模块里，如果把公共字段和方法写在
其中一边，另一边就得跨模块 import 模型文件 —— 容易出现"谁先加载"的隐式依赖。
所以把两个抽象基类放在这里，两边都只依赖本模块：

    TranslationMetaMixin        只有译文元数据（指纹 / 来源 / 时间）+ 判断方法
    TranslatableContentMixin    在上面基础上多一个 `content_en`（帖子/评论用）

反馈（Feedback）用的是 Meta 版：它的英文是**两个**字段（反馈内容 + 管理员回复），
语义比单一的 `content` 复杂，所以在模型里显式声明 `suggestion_en` /
`admin_reply_en`，只复用元数据部分。

三条不变式（与 services_translate.py 的"人工优先"配套）
----------------------------------------------------------------------------
① `translation_hash` 记录**翻译时原文的指纹**；原文后来被改过 → 指纹不匹配 →
   接口返回 `translation_stale=True`，界面提示"译文可能过期"；
② `translation_source == 'manual'` 的内容不会被自动翻译覆盖（除非显式 force）；
③ 没有译文 ≠ 译文过期：没译文时 `translation_stale` 恒为 False，界面文案不同。
============================================================================
"""
import hashlib

from django.db import models
from django.utils import timezone


class TranslationMetaMixin(models.Model):
    """"用户生成内容"的译文元数据（不含具体译文字段）"""

    SOURCE_NONE = ''
    SOURCE_AUTO = 'auto'
    SOURCE_MANUAL = 'manual'
    SOURCE_CHOICES = (
        (SOURCE_NONE, '无译文'),
        (SOURCE_AUTO, '机器翻译'),
        (SOURCE_MANUAL, '人工翻译'),
    )

    translation_hash = models.CharField('译文对应的原文指纹', max_length=40, blank=True, default='')
    translation_source = models.CharField(
        '译文来源', max_length=10, choices=SOURCE_CHOICES, blank=True, default=SOURCE_NONE,
    )
    translated_at = models.DateTimeField('翻译时间', null=True, blank=True)

    class Meta:
        abstract = True

    # ── 子类需要实现 ────────────────────────────────────────────────────────
    def translation_source_texts(self):
        """参与"原文指纹"计算的原文片段（顺序必须稳定）"""
        raise NotImplementedError

    def has_any_translation(self):
        """是否存在**任何**译文（子类按自己的字段实现；默认看 `content_en`）"""
        return bool((getattr(self, 'content_en', '') or '').strip())

    # ── 通用实现 ────────────────────────────────────────────────────────────
    def source_fingerprint(self):
        """当前原文的指纹；原文为空时返回空串（空串表示"不值得翻译"）"""
        parts = [str(part or '').strip() for part in self.translation_source_texts()]
        if not any(parts):
            return ''
        return hashlib.sha1('\x1f'.join(parts).encode('utf-8')).hexdigest()[:40]

    @property
    def has_translation(self):
        """是否存在**任何**译文（人工或机器）"""
        return self.has_any_translation()

    @property
    def translation_stale(self):
        """译文是否已过期：译文存在、但原文在翻译之后又被改过

        没有译文（从未翻译）不算"过期" —— 那是"未翻译"，界面提示语不同。
        """
        if not self.has_translation or not self.translation_hash:
            return False
        return self.translation_hash != self.source_fingerprint()

    def mark_translated(self, source, when=None):
        """记录译文来源与指纹（调用方负责先把译文字段填好）"""
        self.translation_hash = self.source_fingerprint()
        self.translation_source = source
        self.translated_at = when or timezone.now()


class TranslatableContentMixin(TranslationMetaMixin):
    """单一正文的译文（论坛帖子额外有 `title_en`，在各模型里单独声明）"""

    content_en = models.TextField('内容（英文）', blank=True, default='')

    class Meta:
        abstract = True
