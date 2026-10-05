/**
 * 多语言核心逻辑测试（第 48 批）
 * 覆盖：取值、插值、语言切换与持久化、缺 key 时的中文兜底、<html lang> 同步
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_LOCALE, LOCALE_STORAGE_KEY, locale, setLocale, t, tl, useI18n } from '@/i18n';
import { en, zhCN } from '@/i18n/messages';

describe('i18n 核心', () => {
  beforeEach(() => {
    localStorage.clear();
    setLocale(DEFAULT_LOCALE);
  });

  it('按点号路径取值', () => {
    expect(t('nav.home')).toBe('首页');
    setLocale('en');
    expect(t('nav.home')).toBe('Home');
  });

  it('支持 {name} 插值', () => {
    setLocale('en');
    expect(t('alerts.myHistory', { count: 3 })).toBe('You have identified this 3 time(s)');
    expect(t('calendar.deleteConfirm', { title: 'Sowing' })).toBe('Delete “Sowing”?');
  });

  it('未提供的占位符原样保留，不变成 undefined', () => {
    setLocale('en');
    expect(t('alerts.myHistory')).toContain('{count}');
  });

  it('切换语言会持久化到 localStorage', () => {
    setLocale('en');
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en');
    setLocale('zh-CN');
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('zh-CN');
  });

  it('拒绝不支持的语言', () => {
    expect(setLocale('fr')).toBe(false);
    expect(locale.value).toBe('zh-CN');
  });

  it('缺失的 key 回落到中文，再缺就返回 key 并告警（不返回空白）', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    setLocale('en');

    // 英文里没有、中文里有的 key（构造一个：临时挂到 zhCN 上）
    zhCN.__test_only = { greeting: '你好' };
    expect(t('__test_only.greeting')).toBe('你好');

    // 两边都没有 → 返回 key 本身 + 告警
    expect(t('__missing__.nope')).toBe('__missing__.nope');
    expect(warn).toHaveBeenCalled();

    delete zhCN.__test_only;
    warn.mockRestore();
  });

  it('同步 <html lang>', () => {
    setLocale('en');
    expect(document.documentElement.getAttribute('lang')).toBe('en');
    setLocale('zh-CN');
    expect(document.documentElement.getAttribute('lang')).toBe('zh-CN');
  });

  it('两种语言的 key 结构一致（防止只加一半）', () => {
    const flatten = (obj, prefix = '') =>
      Object.entries(obj).flatMap(([key, value]) =>
        value && typeof value === 'object'
          ? flatten(value, `${prefix}${key}.`)
          : [`${prefix}${key}`],
      );
    const zhKeys = flatten(zhCN).sort();
    const enKeys = flatten(en).sort();
    expect(enKeys).toEqual(zhKeys);
  });

  it('useI18n 暴露 t / locale / 语言列表', () => {
    const api = useI18n();
    expect(typeof api.t).toBe('function');
    expect(api.locales.map((item) => item.value)).toEqual(['zh-CN', 'en']);
    setLocale('en');
    expect(api.currentLocaleLabel.value).toBe('English');
  });

  it('useI18n 暴露 t / tl / locale / 语言列表', () => {
    const api = useI18n();
    expect(typeof api.t).toBe('function');
    expect(typeof api.tl).toBe('function');
    expect(api.locales.map((item) => item.value)).toEqual(['zh-CN', 'en']);
    setLocale('en');
    expect(api.currentLocaleLabel.value).toBe('English');
  });

  it('列表文案：tl 取数组、跟随语言、缺失时回落中文并告警', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

    expect(tl('about.stackFrontendItems').length).toBeGreaterThan(0);
    expect(tl('about.stackFrontendItems')[0]).toContain('Vue.js');

    setLocale('en');
    expect(tl('about.stackFrontendItems')[0]).toContain('modern frontend framework');

    // 英文缺、中文有 → 回落中文
    zhCN.__list_only = ['甲', '乙'];
    expect(tl('__list_only')).toEqual(['甲', '乙']);

    // 两边都缺 → 空数组 + 告警（模板里 v-for 不会报错）
    // 注意：告警对同一个 key 只会打一次（避免刷屏），所以这里用一个**没被其它用例碰过**的 key
    expect(tl('__missing_list__.nope')).toEqual([]);
    expect(warn).toHaveBeenCalled();

    // 传字符串 key（非列表）时也返回空数组，而不是抛错
    expect(tl('nav.home')).toEqual([]);

    delete zhCN.__list_only;
    warn.mockRestore();
  });

  it('所有中文文案都非空（避免误留空字符串）', () => {
    const empty = [];
    const walk = (obj, prefix = '') => {
      Object.entries(obj).forEach(([key, value]) => {
        if (value && typeof value === 'object') walk(value, `${prefix}${key}.`);
        else if (!String(value || '').trim()) empty.push(`${prefix}${key}`);
      });
    };
    walk(zhCN);
    walk(en);
    expect(empty).toEqual([]);
  });
});
