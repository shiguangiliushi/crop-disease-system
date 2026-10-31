"""
敏感词过滤（第 38 批）

背景：`views_forum.py` 的文档字符串一直写着"防刷限制和敏感词过滤"，
但**敏感词部分零实现**（第 35 批核实清单时发现）。本模块把它补成真的：

  · `SensitiveWord` 模型（定义在 models.py，Django 需要在那里发现它）：管理员可维护词库；
  · `find_sensitive_words()`：扫描一段文本命中了哪些词；
  · `check_text()`：给序列化器/视图用 —— 命中就抛 400，并把命中的词告诉用户，
    这样用户能自己改（比"内容不合规"这种不可操作的提示友好）；
  · 带 60 秒缓存的词表读取，避免每条评论都全表查询。

命中策略是**拒绝并提示**而不是静默替换：静默替换会让用户以为发成功了，
而管理员在后台看到的又是 `***`，两边都困惑。
"""
import logging
import re

from django.core.cache import cache

from .models import SensitiveWord

logger = logging.getLogger(__name__)

CACHE_KEY = 'sensitive_words:active'
CACHE_TTL = 60


def get_active_words():
    """启用中的敏感词列表（带缓存）"""
    words = cache.get(CACHE_KEY)
    if words is None:
        words = list(
            SensitiveWord.objects.filter(is_active=True).values_list('word', flat=True)
        )
        cache.set(CACHE_KEY, words, CACHE_TTL)
    return words


def find_sensitive_words(*texts):
    """
    返回文本中命中的敏感词（去重、保持出现顺序）

    支持传多段文本（如标题 + 正文），一起检查。
    """
    words = get_active_words()
    if not words:
        return []

    haystack = '\n'.join(str(t or '') for t in texts)
    if not haystack.strip():
        return []

    lowered = haystack.lower()
    hits = []
    for word in words:
        if not word:
            continue
        if word.lower() in lowered and word not in hits:
            hits.append(word)
    return hits


def check_text(*texts, field_label='内容', lang='zh'):
    """
    命中敏感词就抛 ValidationError（DRF 会转成 400）

    用法：
        from .sensitive import check_text
        check_text(title, content, field_label='帖子')
    """
    from rest_framework import serializers

    hits = find_sensitive_words(*texts)
    if hits:
        joined = '、'.join(hits[:5])
        more = '等' if len(hits) > 5 else ''
        # 第 281 批：文案按请求语言渲染（lang 由调用方从 request 取，不传回中文）
        from .i18n import msg as _render

        raise serializers.ValidationError({
            'detail': _render('forum.sensitive_hit', lang,
                              label=field_label, words=f'{joined}{more}'),
            'code': 'sensitive_word',
            'words': hits,
        })


def mask_text(text, mask='*'):
    """把敏感词替换成掩码（用于日志/展示，可选）"""
    result = str(text or '')
    for word in get_active_words():
        if word:
            result = re.sub(re.escape(word), mask * len(word), result, flags=re.IGNORECASE)
    return result
