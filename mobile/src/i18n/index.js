/**
 * 移动端极简多语言
 * ----------------------------------------------------------------------------
 * 与桌面客户端（frontend/src/i18n）保持同一套"点号取值 + 缺翻译回落中文"的做法，
 * 但没有直接复用其文件：两端是**独立工程**，跨工程 copy 代码会带来
 * "改一端忘另一端"的隐患，文案也各自不同（移动端只有 5 个页面）。
 *
 * 覆盖范围同样是"界面文案"；病害名/症状/防治等**内容数据**由后端返回，不在这里翻译。
 */
import { computed, ref } from 'vue';
import { messages } from './messages';

export const DEFAULT_LOCALE = 'zh-CN';
export const LOCALE_STORAGE_KEY = 'mobile_locale';
export const SUPPORTED_LOCALES = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'en', label: 'English' },
];

const warned = new Set();

function readStoredLocale() {
  try {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored && messages[stored]) return stored;
  } catch {
    /* 隐私模式可能不可用 */
  }
  return DEFAULT_LOCALE;
}

export const locale = ref(readStoredLocale());

function applyHtmlLang(value) {
  try {
    document.documentElement.setAttribute('lang', value === 'en' ? 'en' : 'zh-CN');
  } catch {
    /* 测试环境没有 document */
  }
}

applyHtmlLang(locale.value);

export function setLocale(value) {
  if (!messages[value]) return false;
  locale.value = value;
  applyHtmlLang(value);
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, value);
  } catch {
    /* 存不了就算了，本次会话仍生效 */
  }
  return true;
}

function lookup(target, key) {
  return key.split('.').reduce((node, part) => (node == null ? undefined : node[part]), target);
}

export function t(key, params = {}) {
  if (!key) return '';
  let value = lookup(messages[locale.value], key);
  if (typeof value !== 'string') {
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

export function useI18n() {
  return {
    t,
    locale,
    setLocale,
    locales: SUPPORTED_LOCALES,
    isEnglish: computed(() => locale.value === 'en'),
  };
}

export default { t, locale, setLocale, useI18n, SUPPORTED_LOCALES, DEFAULT_LOCALE };
