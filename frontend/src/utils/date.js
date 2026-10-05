/**
 * 格式化日期
 * @param {Date|string|number} date - 日期对象或时间戳
 * @param {string} format - 格式字符串，默认为 'YYYY-MM-DD'
 * @returns {string} 格式化后的日期字符串
 */
import { t } from '@/i18n';  // 第 83 批：相对时间要跟随语言（t 读的是响应式 locale，函数调用时取值即可）

export function formatDate(date, format = 'YYYY-MM-DD') {
  if (!date) return ''
  
  let d = date
  if (typeof date === 'string' || typeof date === 'number') {
    d = new Date(date)
  }
  
  // 如果转换失败，返回空字符串
  if (isNaN(d.getTime())) return ''
  
  const padStart = (num) => String(num).padStart(2, '0')
  
  const map = {
    'YYYY': d.getFullYear(),
    'MM': padStart(d.getMonth() + 1),
    'DD': padStart(d.getDate()),
    'M': d.getMonth() + 1,
    'D': d.getDate()
  }
  
  return format.replace(/(YYYY|MM|DD|M|D)/g, (match) => map[match])
}

/**
 * 格式化时间
 * @param {Date|string|number} date - 日期对象或时间戳
 * @param {string} format - 格式字符串，默认为 'YYYY-MM-DD HH:mm:ss'
 * @returns {string} 格式化后的时间字符串
 */
export function formatTime(date, format = 'YYYY-MM-DD HH:mm:ss') {
  if (!date) return ''
  
  let d = date
  if (typeof date === 'string' || typeof date === 'number') {
    d = new Date(date)
  }
  
  // 如果转换失败，返回空字符串
  if (isNaN(d.getTime())) return ''
  
  const padStart = (num) => String(num).padStart(2, '0')
  
  const map = {
    'YYYY': d.getFullYear(),
    'MM': padStart(d.getMonth() + 1),
    'DD': padStart(d.getDate()),
    'HH': padStart(d.getHours()),
    'mm': padStart(d.getMinutes()),
    'ss': padStart(d.getSeconds()),
    'M': d.getMonth() + 1,
    'D': d.getDate(),
    'H': d.getHours(),
    'm': d.getMinutes(),
    's': d.getSeconds()
  }
  
  return format.replace(/(YYYY|MM|DD|HH|mm|ss|M|D|H|m|s)/g, (match) => map[match])
}

/**
 * 计算相对时间（如：3分钟前 / 3 minutes ago）
 * @param {Date|string|number} date - 日期对象或时间戳
 * @returns {string} 相对时间字符串
 *
 * 第 83 批：改成跟随语言。此前无论中英文都返回中文（「3分钟前」），
 * 而 formatTime 在帖子、评论、通知、识别记录里到处都在用 —— 是"英文界面下
 * 仍见中文"影响面最大的一处。
 */
export function timeAgo(date) {
  if (!date) return ''

  let d = date
  if (typeof date === 'string' || typeof date === 'number') {
    d = new Date(date)
  }

  if (isNaN(d.getTime())) return ''

  const now = new Date()
  const seconds = Math.floor((now - d) / 1000)

  // 小于1分钟
  if (seconds < 60) return t('time.justNow')

  // 小于1小时
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return t('time.minutesAgo', { count: minutes })

  // 小于24小时
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return t('time.hoursAgo', { count: hours })

  // 小于30天
  const days = Math.floor(hours / 24)
  if (days < 30) return t('time.daysAgo', { count: days })

  // 小于12个月
  const months = Math.floor(days / 30)
  if (months < 12) return t('time.monthsAgo', { count: months })
  
  // 大于1年
  const years = Math.floor(months / 12)
  return t('time.yearsAgo', { count: years })
}

/**
 * 获取两个日期之间的天数差
 * @param {Date} date1 - 第一个日期
 * @param {Date} date2 - 第二个日期
 * @returns {number} 天数差
 */
export function getDaysDiff(date1, date2) {
  const oneDay = 24 * 60 * 60 * 1000 // 一天的毫秒数
  const diffDays = Math.round(Math.abs((date1 - date2) / oneDay))
  return diffDays
}

// 导出所有函数
export default {
  formatDate,
  formatTime,
  timeAgo,
  getDaysDiff
}
