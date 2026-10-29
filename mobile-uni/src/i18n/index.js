/**
 * 极简多语言（uni-app 版，第 237 批）
 * ============================================================================
 * 与现有两个前端保持同一套做法：**点号取值 + 缺翻译回落中文**，只翻译"界面文案"；
 * 病害名/症状/防治等**内容数据**由后端返回（`name` / `name_en`），不在前端翻译。
 *
 * 与 H5 版的三个差别（都是"平台"决定的，不是偏好）：
 *   1. 存储用 `uni.getStorageSync`（小程序没有 localStorage）；
 *   2. 不碰 `document.documentElement.lang`（小程序没有 document）；
 *   3. 语言切换后**当前页面立即生效**靠 `locale` 这个 ref —— 与 H5 一致。
 *
 * 文案文件 `messages.js` 是从 `mobile/src/i18n/messages.js` **复制**过来的
 * （204 个 key，覆盖 auth / detect / result / history / mine / shareCard / offline）。
 * 为什么复制而不是跨工程 import：两端是独立构建，跨工程引用会让 "改一端忘另一端"
 * 变成构建错误或悄悄失效果；复制后 uni-app 可独立演化（未来小程序语言包可以分包下载）。
 */
import { computed, ref } from 'vue'
import { messages } from './messages'

export const DEFAULT_LOCALE = 'zh-CN'
export const LOCALE_STORAGE_KEY = 'uni_locale'
export const SUPPORTED_LOCALES = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'en', label: 'English' },
]

const warned = new Set()

function readStoredLocale() {
  try {
    const stored = uni.getStorageSync(LOCALE_STORAGE_KEY)
    if (stored && messages[stored]) return stored
  } catch (error) {
    /* 隐私模式/存储不可用时用默认中文 */
  }
  return DEFAULT_LOCALE
}

export const locale = ref(readStoredLocale())

export function setLocale(value) {
  if (!messages[value]) return false
  locale.value = value
  try {
    uni.setStorageSync(LOCALE_STORAGE_KEY, value)
  } catch (error) {
    /* 存不了就算了，本次会话仍生效 */
  }
  return true
}

function lookup(target, key) {
  return key.split('.').reduce((node, part) => (node == null ? undefined : node[part]), target)
}

/** 当前语言显示名（"我的"页用） */
export const currentLocaleLabel = computed(
  () => (SUPPORTED_LOCALES.find((item) => item.value === locale.value) || SUPPORTED_LOCALES[0]).label
)

/**
 * 取文案：`t('auth.login')`；带占位符的用 `t('x.y', { n: 3 })` → `{n}` 会被替换。
 * 取不到时回落中文，再取不到返回 key 本身（开发期一眼能看出漏了哪个 key）。
 */
export function t(key, params = {}) {
  const table = messages[locale.value] || messages[DEFAULT_LOCALE]
  let text = lookup(table, key)
  if (text === undefined) {
    text = lookup(messages[DEFAULT_LOCALE], key)
    if (text === undefined) {
      if (!warned.has(key)) {
        warned.add(key)
        console.warn(`[i18n] 缺少文案：${key}`)
      }
      return key
    }
  }
  if (typeof text !== 'string') return key
  return text.replace(/\{(\w+)\}/g, (all, name) =>
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : all
  )
}
