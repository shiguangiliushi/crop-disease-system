<template>
  <button type="button" class="back-button" @click="goBack">
    <i class="fas fa-arrow-left" aria-hidden="true"></i>
    <span>{{ label || t('common.back') }}</span>
  </button>
</template>

<script setup>
/**
 * 页面返回按钮（用户协议 / 隐私政策 / 帮助中心 / 意见反馈 等"二级页面"共用）
 * ------------------------------------------------------------------
 * 背景：这几个页面都只能从页脚进入，进去之后**没有任何返回入口** ——
 * 正文再长也只能靠浏览器后退键，移动端（没有可见的后退键）等于走进死胡同。
 *
 * 行为：
 *   · 有站点内上一页（router 记录里存在 back）→ 退回上一页，保持原有浏览路径；
 *   · 直接打开链接/新标签页进来（没有上一页）→ 回落到 `fallback`，默认首页；
 *   · `window.history.length` 在 SPA 里恒大于 1（当前会话起点也算），
 *     所以用 router.options.history.state.back 判断更准确。
 *
 * 样式：中性胶囊（不要用 el-button type="primary" —— 全局主题会把它涂成
 * 深绿渐变，压在白卡片上过重；第 81 批在新闻详情页已经踩过这个坑）。
 *
 * 第 87 批新增（用户反馈"点进用户协议/隐私政策/帮助中心/意见反馈都没有返回按钮"）。
 */
import { useRouter } from 'vue-router';
import { useI18n } from '@/i18n';

const props = defineProps({
  /** 没有上一页时的回落地址 */
  fallback: { type: String, default: '/' },
  /** 自定义文案，默认用 common.back（「返回」/「Back」） */
  label: { type: String, default: '' },
});

const router = useRouter();
const { t } = useI18n();

const goBack = () => {
  const hasInAppHistory = Boolean(router.options.history.state && router.options.history.state.back);
  if (hasInAppHistory) {
    router.back();
  } else {
    router.push(props.fallback);
  }
};
</script>

<style scoped>
.back-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 8px 16px;
  border: 1px solid var(--border-strong, #d3dfd8);
  border-radius: var(--radius-pill, 999px);
  background: var(--surface, #fff);
  color: var(--ink-700, #3a4d43);
  font-size: 14px;
  font-weight: 600;
  line-height: 1;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.back-button:hover {
  border-color: var(--brand-400, #5fb088);
  background: var(--brand-50, #f1f9f4);
  color: var(--brand-700, #1f6343);
}

.back-button:focus-visible {
  outline: none;
  box-shadow: var(--shadow-focus, 0 0 0 3px rgba(42, 127, 83, 0.15));
}

.back-button i {
  font-size: 12px;
}
</style>
