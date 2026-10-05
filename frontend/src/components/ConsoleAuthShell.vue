<script setup>
/**
 * 客服端（坐席工作台）登录 / 注册页面的统一外壳。
 * 左侧：深色品牌与能力说明面板；右侧：表单卡片；顶部：品牌栏与页面切换入口。
 */
import { RouterLink } from 'vue-router';
import { useI18n } from '@/i18n';
// 第 53 批：登录/注册页是 bareLayout（没有顶栏），语言切换器必须也放进来 ——
// 否则"英文用户还没登录就无法切语言"，而登录页恰恰是他们的第一屏。
import LanguageSwitcher from '@/components/LanguageSwitcher.vue';

defineProps({
  // 右侧表单标题
  title: { type: String, default: '' },
  // 右侧表单副标题
  subtitle: { type: String, default: '' },
  // 标题上方的小标签
  eyebrow: { type: String, default: '' },
});

const { t } = useI18n();

// 第 53 批：文案改成 i18n key，渲染时再翻译（原来写死中文）
const highlights = [
  { icon: 'fas fa-headset', titleKey: 'auth.featureQueue', descKey: 'auth.featureQueueDesc' },
  { icon: 'fas fa-clipboard-list', titleKey: 'auth.featureTicket', descKey: 'auth.featureTicketDesc' },
  { icon: 'fas fa-book', titleKey: 'auth.featureKnowledge', descKey: 'auth.featureKnowledgeDesc' },
  { icon: 'fas fa-chart-line', titleKey: 'auth.featureDashboard', descKey: 'auth.featureDashboardDesc' },
];

const currentYear = new Date().getFullYear();
</script>

<template>
  <div class="cs-console">
    <!-- 顶部品牌栏 -->
    <header class="cs-topbar">
      <RouterLink to="/" class="cs-brand">
        <img class="cs-brand-logo" src="@/assets/农作物病害识别1.png" :alt="t('auth.brandName')" />
        <span class="cs-brand-text">
          <span class="cs-brand-name">{{ t('auth.brandName') }}</span>
          <span class="cs-brand-sub">{{ t('auth.brandSub') }}</span>
        </span>
      </RouterLink>

      <div class="cs-topbar-actions">
        <span class="cs-top-hint"><slot name="topbar-actions" /></span>
        <LanguageSwitcher />
        <RouterLink to="/" class="cs-ghost-link">
          <i class="fas fa-home"></i>
          <span>{{ t('auth.backToSite') }}</span>
        </RouterLink>
      </div>
    </header>

    <main class="cs-main">
      <!-- 左侧：客服端能力说明 -->
      <section class="cs-aside">
        <span class="cs-aside-badge"><i class="fas fa-user-tie"></i> {{ t('auth.asideBadge') }}</span>

        <div class="cs-aside-intro">
          <h2>{{ t('auth.asideTitle') }}</h2>
          <p>{{ t('auth.asideDesc') }}</p>
        </div>

        <ul class="cs-aside-features">
          <li v-for="item in highlights" :key="item.titleKey" class="cs-feature">
            <span class="cs-feature-icon"><i :class="item.icon"></i></span>
            <span class="cs-feature-body">
              <strong>{{ t(item.titleKey) }}</strong>
              <em>{{ t(item.descKey) }}</em>
            </span>
          </li>
        </ul>

        <div class="cs-aside-foot">
          <span><i class="fas fa-clock"></i> {{ t('auth.serviceTime') }}</span>
          <span><i class="fas fa-phone-alt"></i> {{ t('auth.internalSupport') }}</span>
        </div>
      </section>

      <!-- 右侧：登录 / 注册表单 -->
      <section class="cs-panel">
        <div class="cs-card">
          <div class="cs-card-head">
            <span class="cs-eyebrow">{{ eyebrow || t('auth.eyebrowDefault') }}</span>
            <h1>{{ title || t('auth.loginTitleDefault') }}</h1>
            <p v-if="subtitle">{{ subtitle }}</p>
          </div>

          <slot />

          <p class="cs-card-foot">
            <i class="fas fa-shield-alt"></i>
            {{ t('auth.accountHint') }}
          </p>
        </div>

        <div class="cs-page-foot">
          <span>© {{ currentYear }} {{ t('auth.brandName') }}</span>
          <span class="cs-dot">·</span>
          <span>{{ t('auth.consoleVersion') }}</span>
        </div>
      </section>
    </main>
  </div>
</template>

<style>
/* 说明：本组件样式为全局（非 scoped），统一定义客服端认证页的视觉规范，
   供登录页与注册页复用；所有类名均以 cs- 前缀命名，避免污染其他页面。 */
.cs-console {
  --cs-green-900: #0b3b2a;
  --cs-green-800: #14503a;
  --cs-green-700: #1a5f3e;
  --cs-green-600: #2a7f53;
  --cs-green-500: #3d9a68;
  --cs-ink: #1f2d3d;
  --cs-ink-soft: #4a5c6a;
  --cs-muted: #7b8c99;
  --cs-border: #e2eae6;
  --cs-bg: #f4f7f5;

  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 100vh;
  width: 100%;
  background: var(--cs-bg);
  color: var(--cs-ink);
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
  font-size: 14px;
  line-height: 1.6;
  box-sizing: border-box;
}

.cs-console *,
.cs-console *::before,
.cs-console *::after {
  box-sizing: border-box;
}

/* ---------- 顶部品牌栏 ---------- */
.cs-topbar {
  flex: 0 0 auto;
  height: 70px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 28px;
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--cs-border);
  position: sticky;
  top: 0;
  z-index: 50;
}

.cs-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
  min-width: 0;
}

.cs-brand-logo {
  height: 42px;
  width: auto;
  object-fit: contain;
}

.cs-brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
  min-width: 0;
}

.cs-brand-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--cs-green-800);
  letter-spacing: 0.2px;
  white-space: nowrap;
}

.cs-brand-sub {
  font-size: 12px;
  color: var(--cs-muted);
  letter-spacing: 0.6px;
}

.cs-topbar-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 13px;
  color: var(--cs-muted);
  white-space: nowrap;
}

.cs-topbar-actions .cs-inline-link {
  color: var(--cs-green-700);
  font-weight: 600;
  margin-left: 4px;
  text-decoration: none;
}

.cs-topbar-actions .cs-inline-link:hover {
  text-decoration: underline;
}

.cs-ghost-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid #dde6e2;
  border-radius: 8px;
  background: #fff;
  color: var(--cs-ink-soft);
  font-size: 13px;
  text-decoration: none;
  transition: all 0.2s ease;
}

.cs-ghost-link:hover {
  color: var(--cs-green-700);
  border-color: #bcd8ca;
  background: #f2f8f4;
}

/* ---------- 主体两栏 ---------- */
.cs-main {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr);
  min-height: 0;
}

/* ---------- 左侧品牌面板 ---------- */
.cs-aside {
  position: relative;
  overflow: hidden;
  padding: 64px 60px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 32px;
  color: #fff;
  background:
    radial-gradient(900px 480px at -10% 8%, rgba(61, 154, 104, 0.5), transparent 62%),
    radial-gradient(700px 420px at 110% 100%, rgba(23, 92, 63, 0.75), transparent 60%),
    linear-gradient(150deg, #0b3b2a 0%, #14503a 48%, #0c3f2d 100%);
}

.cs-aside::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.055) 1px, transparent 1px);
  background-size: 46px 46px;
  mask-image: radial-gradient(720px 520px at 24% 26%, #000 12%, transparent 78%);
  -webkit-mask-image: radial-gradient(720px 520px at 24% 26%, #000 12%, transparent 78%);
  pointer-events: none;
}

.cs-aside > * {
  position: relative;
  z-index: 1;
}

.cs-aside-badge {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.22);
  font-size: 12.5px;
  letter-spacing: 0.4px;
  color: #dff3e7;
}

.cs-aside-intro h2 {
  font-size: 34px;
  line-height: 1.4;
  font-weight: 800;
  letter-spacing: 0.5px;
  margin: 0 0 16px;
  color: #ffffff;
}

.cs-aside-intro p {
  font-size: 15px;
  line-height: 1.95;
  color: rgba(255, 255, 255, 0.76);
  max-width: 560px;
  margin: 0;
}

.cs-aside-features {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  max-width: 620px;
}

.cs-feature {
  display: flex;
  gap: 12px;
  padding: 16px 16px 16px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.12);
  transition: background 0.25s ease, transform 0.25s ease;
}

.cs-feature:hover {
  background: rgba(255, 255, 255, 0.12);
  transform: translateY(-2px);
}

.cs-feature-icon {
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.14);
  color: #b7e6cb;
  font-size: 15px;
}

.cs-feature-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.cs-feature-body strong {
  font-size: 14px;
  font-weight: 700;
  color: #ffffff;
}

.cs-feature-body em {
  font-style: normal;
  font-size: 12.5px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.6);
}

.cs-aside-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 28px;
  padding-top: 22px;
  border-top: 1px solid rgba(255, 255, 255, 0.16);
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.66);
}

.cs-aside-foot i {
  margin-right: 6px;
  color: #8fd3ac;
}

/* ---------- 右侧表单区 ---------- */
.cs-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  padding: 48px 32px;
  background: linear-gradient(180deg, #ffffff 0%, #f7faf8 100%);
}

.cs-card {
  width: 100%;
  max-width: 428px;
  background: #ffffff;
  border: 1px solid var(--cs-border);
  border-radius: 18px;
  padding: 36px 34px 28px;
  box-shadow: 0 20px 48px rgba(15, 61, 42, 0.09);
}

.cs-card-head {
  margin-bottom: 26px;
}

.cs-eyebrow {
  display: inline-block;
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 1.4px;
  text-transform: uppercase;
  color: var(--cs-green-600);
}

.cs-card-head h1 {
  margin: 10px 0 8px;
  font-size: 24px;
  font-weight: 700;
  color: #16281f;
  letter-spacing: 0.3px;
}

.cs-card-head p {
  margin: 0;
  font-size: 13px;
  color: var(--cs-muted);
  line-height: 1.7;
}

.cs-card-foot {
  margin: 22px 0 0;
  padding-top: 16px;
  border-top: 1px dashed #e4ebe7;
  font-size: 12px;
  color: #93a2ad;
  line-height: 1.7;
}

.cs-card-foot i {
  margin-right: 6px;
  color: #b3c4cc;
}

.cs-page-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #9aa9b3;
}

.cs-dot {
  color: #ccd6db;
}

/* ---------- 表单控件 ---------- */
.cs-form {
  display: block;
}

.cs-field {
  margin-bottom: 18px;
}

.cs-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #33475b;
}

.cs-label-hint {
  font-size: 12px;
  font-weight: 400;
  color: #9aa9b3;
}

.cs-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.cs-input-wrap > i.cs-lead-icon {
  position: absolute;
  left: 14px;
  font-size: 13.5px;
  color: #93a5b1;
  pointer-events: none;
  transition: color 0.2s ease;
}

.cs-input-wrap:focus-within > i.cs-lead-icon {
  color: var(--cs-green-600);
}

.cs-input {
  width: 100%;
  height: 46px;
  padding: 0 14px 0 40px;
  border: 1px solid #dde5e2;
  border-radius: 10px;
  background: #f8faf9;
  font-size: 14px;
  color: var(--cs-ink);
  line-height: normal;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.cs-input::placeholder {
  color: #a9b6bf;
}

.cs-input:hover:not(:disabled) {
  border-color: #c9d8d2;
}

.cs-input:focus {
  outline: none;
  border-color: var(--cs-green-600);
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(42, 127, 83, 0.13);
}

.cs-input:disabled {
  background: #f1f4f3;
  color: #9aa9b3;
  cursor: not-allowed;
}

.cs-input.has-trailing {
  padding-right: 44px;
}

.cs-input-trailing {
  position: absolute;
  right: 6px;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: #93a5b1;
  font-size: 13.5px;
  cursor: pointer;
  border-radius: 8px;
  transition: color 0.2s ease, background 0.2s ease;
}

.cs-input-trailing:hover {
  color: var(--cs-green-700);
  background: #eef4f0;
}

/* 用户名建议下拉 */
.cs-suggest {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  z-index: 60;
  background: #ffffff;
  border: 1px solid var(--cs-border);
  border-radius: 10px;
  box-shadow: 0 12px 28px rgba(15, 61, 42, 0.14);
  padding: 6px;
  max-height: 208px;
  overflow-y: auto;
}

.cs-suggest-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 8px;
  font-size: 13.5px;
  color: var(--cs-ink-soft);
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}

.cs-suggest-item i {
  font-size: 12.5px;
  color: #9aa9b3;
}

.cs-suggest-item:hover {
  background: #eef7f2;
  color: var(--cs-green-700);
}

.cs-suggest-item:hover i {
  color: var(--cs-green-600);
}

.cs-suggest-item.is-recent {
  font-weight: 600;
  color: var(--cs-green-700);
}

.cs-suggest-tip {
  padding: 7px 10px 5px;
  font-size: 11.5px;
  color: #a9b6bf;
  border-bottom: 1px solid #f0f4f2;
  margin-bottom: 4px;
}

/* 行内布局：记住密码 / 忘记密码 */
.cs-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 2px 0 22px;
}

.cs-check {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--cs-ink-soft);
  cursor: pointer;
  user-select: none;
  margin: 0;
}

.cs-check input[type='checkbox'] {
  width: 16px;
  height: 16px;
  margin: 0;
  accent-color: var(--cs-green-600);
  cursor: pointer;
}

.cs-link {
  font-size: 13px;
  color: var(--cs-green-700);
  font-weight: 600;
  text-decoration: none;
}

.cs-link:hover {
  text-decoration: underline;
}

/* 提交按钮 */
.cs-submit {
  width: 100%;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #2a7f53 0%, #1a5f3e 100%);
  color: #ffffff;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.5px;
  cursor: pointer;
  box-shadow: 0 10px 22px rgba(26, 95, 62, 0.22);
  transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;
}

.cs-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 14px 26px rgba(26, 95, 62, 0.3);
}

.cs-submit:disabled {
  opacity: 0.65;
  cursor: not-allowed;
  box-shadow: none;
  transform: none;
}

.cs-spinner {
  width: 15px;
  height: 15px;
  border: 2px solid rgba(255, 255, 255, 0.45);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: cs-spin 0.8s linear infinite;
}

@keyframes cs-spin {
  to {
    transform: rotate(360deg);
  }
}

/* 提示信息 */
.cs-alert {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0 0 16px;
  padding: 11px 13px;
  border-radius: 10px;
  background: #fef4f4;
  border: 1px solid #f7d9d9;
  color: #c0392b;
  font-size: 12.5px;
  line-height: 1.65;
}

.cs-alert i {
  margin-top: 2px;
}

.cs-alert.is-success {
  background: #f1faf4;
  border-color: #cbe9d7;
  color: #1e7a4c;
}

.cs-alert.is-info {
  background: #f2f8fb;
  border-color: #d5e7ef;
  color: #2b6c8a;
}

/* 表单补充说明 */
.cs-form-note {
  margin: 14px 0 0;
  font-size: 12px;
  color: #93a2ad;
  line-height: 1.7;
}

/* 密码强度 */
.cs-strength {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 9px;
}

.cs-strength-bars {
  display: flex;
  gap: 5px;
  flex: 0 0 auto;
}

.cs-strength-bar {
  width: 34px;
  height: 5px;
  border-radius: 999px;
  background: #e6ecea;
  transition: background 0.25s ease;
}

.cs-strength-bar.is-on.level-1 {
  background: #e07a5f;
}

.cs-strength-bar.is-on.level-2 {
  background: #e0b34f;
}

.cs-strength-bar.is-on.level-3 {
  background: #2a7f53;
}

.cs-strength-text {
  font-size: 12px;
  color: #93a2ad;
}

/* 页面切换 */
.cs-switch {
  margin: 20px 0 0;
  text-align: center;
  font-size: 13px;
  color: var(--cs-muted);
}

/* ---------- 响应式 ---------- */
@media (max-width: 1180px) {
  .cs-aside {
    padding: 48px 40px;
  }

  .cs-aside-intro h2 {
    font-size: 29px;
  }

  .cs-aside-features {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 960px) {
  .cs-main {
    grid-template-columns: minmax(0, 1fr);
  }

  .cs-aside {
    display: none;
  }

  .cs-panel {
    padding: 36px 20px;
  }
}

@media (max-width: 640px) {
  .cs-topbar {
    height: auto;
    padding: 12px 16px;
    flex-wrap: wrap;
  }

  .cs-brand-name {
    font-size: 13.5px;
    white-space: normal;
  }

  .cs-brand-sub {
    display: none;
  }

  .cs-topbar-actions {
    width: 100%;
    justify-content: space-between;
    font-size: 12.5px;
  }

  .cs-card {
    padding: 26px 20px 22px;
    border-radius: 14px;
  }
}
</style>
