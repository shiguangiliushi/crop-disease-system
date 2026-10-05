/**
 * 用户内容译文取值测试（第 85 批）
 * ----------------------------------------------------------------------------
 * 背景：论坛帖子/评论是用户写的中文，英文界面下靠后端翻译（人工或机器）显示英文。
 * 这里把"显示译文还是原文""要不要提示未翻译/已过期"的判定钉死 —— 这几条规则
 * 分散在帖子详情、评论、列表页里，一旦写错，用户会看到：
 *   · 英文界面里突兀的一段中文（该用译文却用了原文）；
 *   · 或者把中文原文当成"已翻译"而不给任何提示（用户以为系统翻译错了）。
 */
import { describe, expect, it, beforeEach } from 'vitest';
import {
  hasTranslation,
  isShowingOriginal,
  isTranslationStale,
  localizedField,
  translationSource,
} from '@/utils/localized';
import { locale } from '@/i18n';

const translated = {
  title: '番茄晚疫病',
  title_en: 'Tomato late blight',
  content: '正文',
  content_en: 'Body',
  translation_stale: false,
  translation_source: 'auto',
};

const untranslated = { title: '番茄晚疫病', title_en: '', content: '正文', content_en: '' };

const staleManual = {
  title: '标题',
  title_en: 'Title',
  translation_stale: true,
  translation_source: 'manual',
};

describe('用户内容译文取值', () => {
  beforeEach(() => {
    locale.value = 'zh-CN';
  });

  it('中文界面永远显示原文，即使译文存在', () => {
    locale.value = 'zh-CN';
    expect(localizedField(translated, 'title')).toBe('番茄晚疫病');
    expect(isShowingOriginal(translated, 'title')).toBe(false);
  });

  it('英文界面有译文时显示译文', () => {
    locale.value = 'en';
    expect(localizedField(translated, 'title')).toBe('Tomato late blight');
    expect(hasTranslation(translated, 'title')).toBe(true);
    expect(isShowingOriginal(translated, 'title')).toBe(false);
  });

  it('英文界面没有译文时回落原文，并标记为"正在显示原文"', () => {
    locale.value = 'en';
    expect(localizedField(untranslated, 'title')).toBe('番茄晚疫病');
    expect(hasTranslation(untranslated, 'title')).toBe(false);
    expect(isShowingOriginal(untranslated, 'title')).toBe(true);
  });

  it('只有空白的译文按"没有译文"处理', () => {
    locale.value = 'en';
    const blank = { title: '标题', title_en: '   ' };
    expect(hasTranslation(blank, 'title')).toBe(false);
    expect(localizedField(blank, 'title')).toBe('标题');
  });

  it('译文过期与译文来源由后端字段直接反映', () => {
    expect(isTranslationStale(translated)).toBe(false);
    expect(isTranslationStale(staleManual)).toBe(true);
    expect(translationSource(staleManual)).toBe('manual');
    expect(translationSource(translated)).toBe('auto');
    expect(translationSource({})).toBe('');
  });

  it('空对象/undefined 不会抛异常（列表首屏数据还没回来时的常态）', () => {
    expect(localizedField(null, 'title')).toBe('');
    expect(hasTranslation(undefined, 'title')).toBe(false);
    expect(isTranslationStale(null)).toBe(false);
    locale.value = 'en';
    expect(isShowingOriginal(null, 'title')).toBe(false);
  });
});
