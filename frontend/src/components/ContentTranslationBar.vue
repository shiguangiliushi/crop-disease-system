<template>
  <!--
    第 85 批：用户生成内容的"译文状态"说明条
    ========================================================================
    帖子/评论是用户自己写的中文，英文界面下靠**机器翻译或人工译文**显示英文。
    译文可能缺失（刚发出来、翻译接口挂了、额度用完），也可能过期（原文后来被改过）。
    没有这一条，读者只会看到一段中文而不知道发生了什么；有了它，界面能明确说清：

      · 有译文      → 显示「译文由机器翻译提供」+「查看原文」开关；
      · 译文过期    → 额外提示「原文已更新，译文可能过期」；
      · 没有译文    → 「暂无英文译文，当前显示原文」+「立即翻译」按钮（登录用户）。

    组件本身不请求接口：翻译由父组件处理（需要刷新列表/局部替换数据）。
  -->
  <div
    v-if="visible"
    class="translation-bar"
    :class="[`is-${state}`, { 'is-compact': compact }]"
  >
    <i class="fas" :class="iconClass"></i>
    <span class="translation-text">{{ message }}</span>

    <button
      v-if="canToggle"
      type="button"
      class="translation-action"
      @click="$emit('toggle-original')"
    >
      {{ showOriginal ? t('trans.showTranslation') : t('trans.showOriginal') }}
    </button>

    <button
      v-if="canTranslate"
      type="button"
      class="translation-action"
      :disabled="busy"
      @click="$emit('translate')"
    >
      <span v-if="busy" class="translation-spinner"></span>
      {{ busy ? t('trans.translating') : t('trans.translateNow') }}
    </button>
  </div>
</template>

<script setup>
/**
 * 译文状态条（第 85 批）
 *
 * 只负责"显示状态 + 抛出意图"，不碰数据：翻译动作由父组件执行
 * （父组件知道自己是帖子还是评论、要刷新哪一份数据）。
 */
import { computed } from 'vue';
import { useI18n } from '@/i18n';
import { hasTranslation, isTranslationStale, translationSource } from '@/utils/localized';

const props = defineProps({
  /** 带有 `*_en` / translation_stale / translation_source 的对象 */
  source: { type: Object, default: () => ({}) },
  /** 字段基名：帖子/评论正文都是 'content'，标题是 'title' */
  base: { type: String, default: 'content' },
  /** 是否正处于"显示原文"状态（父组件持有，便于整页统一控制） */
  showOriginal: { type: Boolean, default: false },
  /** 翻译请求进行中 */
  busy: { type: Boolean, default: false },
  /** 紧凑样式（评论区用） */
  compact: { type: Boolean, default: false },
});

defineEmits(['toggle-original', 'translate']);

const { t, locale } = useI18n();

const translated = computed(() => hasTranslation(props.source, props.base));
const stale = computed(() => isTranslationStale(props.source));
const manual = computed(() => translationSource(props.source) === 'manual');

/** 中文界面下这条说明条没有意义（本来就是原文），直接不渲染 */
const visible = computed(() => locale.value === 'en');

const state = computed(() => {
  if (!translated.value) return 'missing';
  return stale.value ? 'stale' : 'ok';
});

const iconClass = computed(() => ({
  missing: 'fa-language',
  stale: 'fa-triangle-exclamation',
  ok: 'fa-robot',
}[state.value]));

const message = computed(() => {
  if (!translated.value) return t('trans.notTranslated');
  if (stale.value) return t('trans.stale');
  return manual.value ? t('trans.manual') : t('trans.auto');
});

const canToggle = computed(() => translated.value);
const canTranslate = computed(() => !translated.value || stale.value);
</script>

<style scoped>
.translation-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 8px 0;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
  background: #f4f7f5;
  color: #5c7266;
  border: 1px solid #e2ebe6;
}

.translation-bar.is-compact {
  margin: 4px 0 0;
  padding: 3px 8px;
  font-size: 11.5px;
}

.translation-bar.is-missing {
  background: #fff8e6;
  border-color: #f4e0b0;
  color: #8a6d1f;
}

.translation-bar.is-stale {
  background: #fdf2f2;
  border-color: #f3d0d0;
  color: #9b5252;
}

.translation-text {
  flex: 1 1 auto;
  min-width: 0;
}

.translation-action {
  flex: 0 0 auto;
  border: none;
  background: transparent;
  color: #2f7d5d;
  font-size: inherit;
  cursor: pointer;
  padding: 0 2px;
  text-decoration: underline;
}

.translation-action:disabled {
  color: #9bb0a6;
  cursor: not-allowed;
  text-decoration: none;
}

.translation-spinner {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 4px;
  border: 2px solid #cfded7;
  border-top-color: #2f7d5d;
  border-radius: 50%;
  animation: translation-spin 0.8s linear infinite;
}

@keyframes translation-spin {
  to { transform: rotate(360deg); }
}
</style>
