/**
 * 内容数据的多语言取值（第 69 批 · C 阶段）
 * ------------------------------------------------------------------
 * 为什么单独做这个：病害名、作物名这类**内容数据**存在数据库里，
 * 前端文案表（i18n/messages.js）管不到它们。后端为这些字段提供了 `*_en` 版本，
 * 这里按当前语言挑一个显示，缺失时回落到原字段，保证永远不会出现空白。
 *
 * 用法：
 *   localizedField(pest, 'name')      // 中文界面 → pest.name；英文界面 → pest.name_en || pest.name
 *   localizedField(pest, 'crop_type')
 */
import { computed } from 'vue';
import { locale } from '@/i18n';

export function localizedField(source, base) {
  if (!source) return '';
  const english = source[`${base}_en`];
  const original = source[base] || '';
  // 第 85 批：`*_en` 只有空白字符时按"没有译文"处理。
  // 原来的判断是 `if (... && english)`，`'   '` 这种值会通过 → 英文界面渲染出一片
  // 空白（内容"消失"了），与本文件 hasTranslation() 的判定也不一致。
  if (locale.value === 'en' && english && String(english).trim()) return english;
  return original;
}

/** 传入 ref/computed 的对象，返回跟随语言变化的 computed */
export function useLocalizedField(sourceRef, base) {
  return computed(() => localizedField(sourceRef?.value, base));
}

// ============================================================================
// 第 85 批：用户生成内容（论坛帖子/评论）的译文状态
// ----------------------------------------------------------------------------
// 帖子/评论的 `*_en` 不是"标准答案"，而是机器或人工翻译出来的，可能：
//   · 还不存在（新帖还没翻、翻译接口挂了）→ 界面要标注"显示的是原文"；
//   · 存在但原文后来被编辑过（后端 translation_stale=true）→ 界面要提示
//     "原文已更新，译文可能过期"，而不是拿一段过时的英文当作正文。
// 下面三个 helper 给模板用，判断逻辑与后端 models_forum.TranslatableContentMixin
// 保持一致：有译文才谈得上过期；没译文是"未翻译"。
// ============================================================================

/** 当前语言下，这条内容是否有对应译文可用 */
export function hasTranslation(source, base) {
  if (!source) return false;
  const english = source[`${base}_en`];
  return Boolean(english && String(english).trim());
}

/** 是否正在显示"原文兜底"（英文界面 + 没有译文）
 *
 *  source 为空时返回 false —— 那是"数据还没加载"，页面上什么都没有，
 *  谈不上"正在显示原文"（否则首屏会给空列表挂一排"未翻译"角标）。
 */
export function isShowingOriginal(source, base) {
  if (!source) return false;
  return locale.value === 'en' && !hasTranslation(source, base);
}

/** 译文是否已过期（原文改过） */
export function isTranslationStale(source) {
  return Boolean(source && source.translation_stale);
}

/** 译文是人工写的还是机器翻的（用于界面角标文案） */
export function translationSource(source) {
  return (source && source.translation_source) || '';
}

/** 组件里一次性拿到 helper（模板中直接可用） */
export function useLocalized() {
  return {
    localizedField,
    useLocalizedField,
    hasTranslation,
    isShowingOriginal,
    isTranslationStale,
    translationSource,
  };
}

export default {
  localizedField,
  useLocalizedField,
  useLocalized,
  hasTranslation,
  isShowingOriginal,
  isTranslationStale,
  translationSource,
};
