/**
 * 极简多语言（第 48 批）
 * ------------------------------------------------------------------
 * 为什么不用 vue-i18n：本项目依赖里没有它，而为一个"导航/按钮/标题"级别的需求
 * 引入整套 i18n 库不划算（还会带来构建体积与版本风险）。这里用 ~80 行实现：
 *
 *   · `t('nav.home')` 点号取值 + `{name}` 参数插值；
 *   · 找不到 key 时**回落到中文**，再找不到就返回 key 本身并 console.warn ——
 *     缺翻译时界面不会变成空白，也不会静默失败；
 *   · 语言存 localStorage(`app_locale`)，并同步 `<html lang>`（对读屏/SEO 有意义）；
 *   · 切换语言会触发响应式更新（locale 是 ref）。
 *
 * 覆盖范围：界面文案。病害名/新闻正文/用户名等**内容数据**由后端提供，不在此翻译。
 */
import { computed, ref } from 'vue';
import { messages } from './messages';

export const DEFAULT_LOCALE = 'zh-CN';
export const LOCALE_STORAGE_KEY = 'app_locale';
export const SUPPORTED_LOCALES = [
  { value: 'zh-CN', labelKey: 'language.zh' },
  { value: 'en', labelKey: 'language.en' },
];

const warned = new Set();

function readStoredLocale() {
  try {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored && messages[stored]) return stored;
  } catch {
    /* 隐私模式下 localStorage 可能不可用，忽略 */
  }
  return DEFAULT_LOCALE;
}

export const locale = ref(readStoredLocale());

function applyHtmlLang(value) {
  try {
    document.documentElement.setAttribute('lang', value === 'en' ? 'en' : 'zh-CN');
  } catch {
    /* SSR / 测试环境没有 document */
  }
}

applyHtmlLang(locale.value);

/** 切换语言（并持久化） */
export function setLocale(value) {
  if (!messages[value]) return false;
  locale.value = value;
  applyHtmlLang(value);
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, value);
  } catch {
    /* 存不了就算了，本次会话仍然生效 */
  }
  return true;
}

function lookup(target, key) {
  return key.split('.').reduce((node, part) => (node == null ? undefined : node[part]), target);
}

/**
 * 翻译
 * @param {string} key 形如 'nav.home'
 * @param {object} params 插值参数，如 { month: 9 }
 */
export function t(key, params = {}) {
  if (!key) return '';
  const current = lookup(messages[locale.value], key);
  let value = current;

  if (typeof value !== 'string') {
    // 回落中文，避免缺翻译时界面空白
    const fallback = lookup(messages[DEFAULT_LOCALE], key);
    value = typeof fallback === 'string' ? fallback : null;
  }

  if (value == null) {
    if (!warned.has(key)) {
      warned.add(key);
      console.warn(`[i18n] 缺少文案：${key}`);
    }
    return key;
  }

  return value.replace(/\{(\w+)\}/g, (match, name) =>
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match,
  );
}

/** 供组件在 setup 里使用 */
export function useI18n() {
  return {
    t,
    tl,
    locale,
    setLocale,
    locales: SUPPORTED_LOCALES,
    currentLocaleLabel: computed(() => t(locale.value === 'en' ? 'language.en' : 'language.zh')),
  };
}

/**
 * 取"列表型"文案（第 53 批）
 *
 * 有些界面文案天然是列表（关于页的技术栈、使用条款的条目），
 * 用 15 个独立 key 去凑很啰嗦。这里允许文案值是**字符串数组**：
 *     tl('about.frontendStack')  →  ['Vue.js 3 - …', 'Vite - …']
 * 找不到时回落中文，仍然找不到返回空数组（模板里 v-for 不会报错）。
 */
export function tl(key) {
  const value = lookup(messages[locale.value], key);
  if (Array.isArray(value)) return value;
  const fallback = lookup(messages[DEFAULT_LOCALE], key);
  if (Array.isArray(fallback)) return fallback;
  if (!warned.has(key)) {
    warned.add(key);
    console.warn(`[i18n] 缺少列表文案：${key}`);
  }
  return [];
}

export default { t, tl, locale, setLocale, useI18n, SUPPORTED_LOCALES, DEFAULT_LOCALE };
