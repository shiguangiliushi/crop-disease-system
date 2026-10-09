<script setup>
/**
 * 认证页外壳（农户侧：登录 / 注册 / 找回密码 / 重置密码 共用）
 * ============================================================================
 * 第 116 批重做。改这一件事的原因写在最前面，免得后来的人又把两套气质混回去：
 *
 *   **这个项目是给农户用的 C 端产品，不是客服后台。**
 *   改前它叫 `ConsoleAuthShell`，左侧一栏写着「客服坐席专用入口 / 工单全流程 /
 *   服务数据看板 / 服务时间 周一至周五 09:00-18:00 / 内部支持 400-123-4567」——
 *   农户打开第一屏看到的是"某个内部管理系统"，不是"拍张照片看病虫害"。
 *   而代码里**根本没有客服角色**（权限只有 is_staff / is_superuser / role=ADMIN），
 *   那套文案纯粹是装饰，所以直接换掉。
 *
 * 第 119 批：**管理端登录页已从这里拆出去**（`views/AdminLoginView.vue`，
 * 深色整屏 + 居中卡片，自己的模板与样式）。本外壳现在只服务农户侧四个页面，
 * 因此不再有 `variant` 参数 —— 一个外壳扮演两种气质，最后两边都不像。
 *
 * 样式是**全局的**（非 scoped，四个页面共用一套表单控件规范），类名统一 `auth-` 前缀。
 * 说明：`auth-` 是第 116 批从 `cs-`（console shell）改过来的 —— 名字得跟用途一致。
 */
import { RouterLink } from 'vue-router';
import { useI18n } from '@/i18n';
// 第 53 批：登录/注册页是 bareLayout（没有顶栏），语言切换器必须也放进来 ——
// 否则"英文用户还没登录就无法切语言"，而登录页恰恰是他们的第一屏。
import LanguageSwitcher from '@/components/LanguageSwitcher.vue';
// 首屏图：从项目自带的《农作物病害识别2》里裁掉了烤进图里的标题字，再转 webp
// （1.42MB PNG → 57KB）—— 登录页是第一屏，不该为一张背景图拖慢农户的流量。
import heroImage from '@/assets/auth-hero.webp';

defineProps({
  // 右侧表单标题
  title: { type: String, default: '' },
  // 右侧表单副标题
  subtitle: { type: String, default: '' },
  // 标题上方的小标签
  eyebrow: { type: String, default: '' },
});

const { t } = useI18n();

/** 左侧那四条（图标 + i18n key），顺序就是"打开 App 会先做什么" */
const highlights = [
  { icon: 'fas fa-camera', titleKey: 'auth.featureQueue', descKey: 'auth.featureQueueDesc' },
  { icon: 'fas fa-notes-medical', titleKey: 'auth.featureTicket', descKey: 'auth.featureTicketDesc' },
  { icon: 'fas fa-book-open', titleKey: 'auth.featureKnowledge', descKey: 'auth.featureKnowledgeDesc' },
  { icon: 'fas fa-clock-rotate-left', titleKey: 'auth.featureDashboard', descKey: 'auth.featureDashboardDesc' },
];

const currentYear = new Date().getFullYear();
</script>

<template>
  <div class="auth-shell auth-shell--user">
    <!-- 顶部品牌栏 -->
    <header class="auth-topbar">
      <RouterLink to="/" class="auth-brand">
        <img class="auth-brand-logo" src="@/assets/农作物病害识别1.png" :alt="t('auth.brandName')" />
        <span class="auth-brand-text">
          <span class="auth-brand-name">{{ t('auth.brandName') }}</span>
          <span class="auth-brand-sub">{{ t('auth.brandSub') }}</span>
        </span>
      </RouterLink>

      <div class="auth-topbar-actions">
        <span class="auth-top-hint"><slot name="topbar-actions" /></span>
        <LanguageSwitcher />
        <RouterLink to="/" class="auth-ghost-link">
          <i class="fas fa-house"></i>
          <span>{{ t('auth.backToSite') }}</span>
        </RouterLink>
      </div>
    </header>

    <main class="auth-main">
      <!-- 左栏：实拍图 + 农户视角的四条能力 -->
      <section class="auth-hero" :style="{ backgroundImage: `url(${heroImage})` }">
        <span class="auth-hero-badge">
          <i class="fas fa-leaf"></i> {{ t('auth.asideBadge') }}
        </span>

        <div class="auth-hero-intro">
          <h2>{{ t('auth.asideTitle') }}</h2>
          <p>{{ t('auth.asideDesc') }}</p>
        </div>

        <ul class="auth-chips">
          <li v-for="item in highlights" :key="item.titleKey" class="auth-chip">
            <span class="auth-chip-icon"><i :class="item.icon"></i></span>
            <span class="auth-chip-body">
              <strong>{{ t(item.titleKey) }}</strong>
              <em>{{ t(item.descKey) }}</em>
            </span>
          </li>
        </ul>

        <div class="auth-hero-foot">
          <span><i class="fas fa-bolt"></i> {{ t('auth.serviceTime') }}</span>
          <span><i class="fas fa-seedling"></i> {{ t('auth.internalSupport') }}</span>
        </div>
      </section>

      <!-- 右栏：表单 -->
      <section class="auth-panel">
        <div class="auth-card">
          <div class="auth-card-head">
            <span class="auth-eyebrow">{{ eyebrow || t('auth.eyebrowDefault') }}</span>
            <h1>{{ title || t('auth.loginTitleDefault') }}</h1>
            <p v-if="subtitle">{{ subtitle }}</p>
          </div>

          <slot />

          <!-- 表单下方的次要动作（"还没有账号？立即注册"这类），由各页自己填 -->
          <div v-if="$slots['card-actions']" class="auth-card-actions">
            <slot name="card-actions" />
          </div>

          <p class="auth-card-foot">
            <i class="fas fa-shield-halved"></i>
            {{ t('auth.accountHint') }}
          </p>
        </div>

        <div class="auth-page-foot">
          <span>© {{ currentYear }} {{ t('auth.brandName') }}</span>
          <span class="auth-dot">·</span>
          <span>{{ t('auth.footerNote') }}</span>
        </div>

        <!-- 页脚下方的极小补充位（农户登录页用它放「管理员登录」这个入口：
             管理端有独立页面，但管理员也要能找到它，所以留一个不抢眼的位置） -->
        <div v-if="$slots['page-foot']" class="auth-page-extra">
          <slot name="page-foot" />
        </div>
      </section>
    </main>
  </div>
</template>

<style>
/* 说明：本组件样式为全局（非 scoped），统一定义认证页的视觉规范，五个页面复用；
   所有类名均以 auth- 前缀命名，避免污染其他页面。 */
.auth-shell {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 100vh;
  width: 100%;
  background: var(--ink-50, #f8fbf9);
  color: var(--ink-800, #24352c);
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
  font-size: 14px;
  line-height: 1.6;
  box-sizing: border-box;
}

.auth-shell *,
.auth-shell *::before,
.auth-shell *::after {
  box-sizing: border-box;
}

/* ---------- 顶部品牌栏 ---------- */
.auth-topbar {
  flex: 0 0 auto;
  height: 68px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 28px;
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border, #e2ebe5);
  position: sticky;
  top: 0;
  z-index: 50;
}

.auth-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
  min-width: 0;
}

.auth-brand-logo {
  height: 40px;
  width: auto;
  border-radius: 10px;
  object-fit: contain;
}

.auth-brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
  min-width: 0;
}

.auth-brand-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--brand-800, #194f37);
  letter-spacing: 0.2px;
  white-space: nowrap;
}

.auth-brand-sub {
  font-size: 12px;
  color: var(--ink-500, #78897f);
  letter-spacing: 0.6px;
}

.auth-topbar-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 13px;
  color: var(--ink-500, #78897f);
  white-space: nowrap;
}

.auth-topbar-actions .auth-inline-link {
  color: var(--brand-700, #1f6343);
  font-weight: 600;
  margin-left: 4px;
  text-decoration: none;
}

.auth-topbar-actions .auth-inline-link:hover {
  text-decoration: underline;
}

.auth-ghost-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid var(--border, #e2ebe5);
  border-radius: var(--radius-pill, 999px);
  background: #fff;
  color: var(--ink-600, #566b60);
  font-size: 13px;
  text-decoration: none;
  transition: all 0.2s ease;
}

.auth-ghost-link:hover {
  color: var(--brand-700, #1f6343);
  border-color: var(--brand-300, #93cdad);
  background: var(--brand-50, #f1f9f4);
}

/* ---------- 主体两栏 ---------- */
.auth-main {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.02fr) minmax(0, 0.98fr);
  min-height: 0;
}

/* ---------- 左栏（农户侧：实拍图） ---------- */
.auth-hero {
  position: sticky;
  /* 顶栏高度：粘在顶栏下面，右栏（注册页表单更长）滚动时照片不动 */
  top: 68px;
  align-self: start;
  min-height: calc(100vh - 68px);
  overflow: hidden;
  padding: 56px 54px 48px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 26px;
  color: #fff;
  background-color: var(--brand-900, #123a29);
  background-size: cover;
  /* 图的构图：太阳与麦田在中上部，人物在右 —— 取中偏下，标题文字压在留白上最好读 */
  background-position: center 62%;
}

/* 图片上压一层深绿，保证白字可读（也让实拍图和全站绿色调统一）。
   透明度取"能看清是张照片、白字又不费力"的中间值 —— 压得太实会变成一块纯色板。 */
.auth-hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    158deg,
    rgba(9, 46, 32, 0.9) 0%,
    rgba(13, 66, 45, 0.76) 48%,
    rgba(23, 94, 63, 0.5) 100%
  );
  pointer-events: none;
}

.auth-hero > * {
  position: relative;
  z-index: 1;
}

/* 管理端登录已拆成独立页面（views/AdminLoginView.vue），这里不再有 admin 分支 */

.auth-hero-badge {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 14px;
  border-radius: var(--radius-pill, 999px);
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.22);
  font-size: 12.5px;
  letter-spacing: 0.4px;
  color: #dff3e7;
}

.auth-hero-intro h2 {
  margin: 0 0 14px;
  font-size: 32px;
  line-height: 1.42;
  font-weight: 800;
  letter-spacing: 0.5px;
  color: #ffffff;
  /* 图片透出来之后文字底不一定干净，给一点点阴影兜底 */
  text-shadow: 0 1px 14px rgba(6, 32, 22, 0.4);
}

.auth-hero-intro p {
  margin: 0;
  max-width: 560px;
  font-size: 14.5px;
  line-height: 1.9;
  color: rgba(255, 255, 255, 0.82);
  text-shadow: 0 1px 10px rgba(6, 32, 22, 0.3);
}

/* 能力胶囊：比"边框卡片"轻，读起来像产品介绍而不是功能清单 */
.auth-chips {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
  max-width: 560px;
}

.auth-chip {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 13px 16px;
  border-radius: var(--radius, 14px);
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.14);
  transition: background 0.25s ease, transform 0.25s ease;
}

.auth-chip:hover {
  background: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
}

.auth-chip-icon {
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.16);
  color: #b7e6cb;
  font-size: 14px;
}

.auth-chip-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.auth-chip-body strong {
  font-size: 14px;
  font-weight: 700;
  color: #ffffff;
}

.auth-chip-body em {
  font-style: normal;
  font-size: 12.5px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.66);
}

.auth-hero-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 26px;
  padding-top: 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.16);
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.68);
}

.auth-hero-foot i {
  margin-right: 6px;
  color: #8fd3ac;
}

/* ---------- 右栏（表单区） ---------- */
.auth-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
  padding: 44px 32px;
  background: linear-gradient(180deg, #ffffff 0%, var(--ink-50, #f8fbf9) 100%);
}

.auth-card {
  width: 100%;
  max-width: 432px;
  background: #ffffff;
  border: 1px solid var(--border, #e2ebe5);
  border-radius: var(--radius-xl, 24px);
  padding: 34px 32px 26px;
  box-shadow: var(--shadow-lg, 0 16px 40px rgba(19, 58, 41, 0.12));
}

.auth-card-head {
  margin-bottom: 24px;
}

/* 小标签改成胶囊：原来是大写 + 字距的"系统标签"长相，C 端不需要那种距离感 */
.auth-eyebrow {
  display: inline-flex;
  align-items: center;
  padding: 5px 12px;
  border-radius: var(--radius-pill, 999px);
  background: var(--brand-50, #f1f9f4);
  color: var(--brand-700, #1f6343);
  font-size: 12.5px;
  font-weight: 700;
}

.auth-card-head h1 {
  margin: 14px 0 8px;
  font-size: 25px;
  font-weight: 800;
  color: var(--ink-900, #14231c);
  letter-spacing: 0.3px;
}

.auth-card-head p {
  margin: 0;
  font-size: 13.5px;
  color: var(--ink-500, #78897f);
  line-height: 1.75;
}

.auth-card-actions {
  margin: 18px 0 0;
  text-align: center;
  font-size: 13.5px;
  color: var(--ink-500, #78897f);
}

.auth-card-actions .auth-inline-link {
  margin-left: 6px;
  color: var(--brand-700, #1f6343);
  font-weight: 700;
  text-decoration: none;
}

.auth-card-actions .auth-inline-link:hover {
  text-decoration: underline;
}

.auth-card-foot {
  margin: 20px 0 0;
  padding-top: 16px;
  border-top: 1px dashed var(--border, #e2ebe5);
  font-size: 12px;
  color: var(--ink-400, #9dada5);
  line-height: 1.7;
}

.auth-card-foot i {
  margin-right: 6px;
  color: var(--brand-400, #5fb088);
}

.auth-page-foot {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
  max-width: 460px;
  text-align: center;
  font-size: 12px;
  color: var(--ink-400, #9dada5);
}

.auth-dot {
  color: var(--ink-300, #c6d2cb);
}

.auth-page-extra {
  font-size: 12px;
  color: var(--ink-400, #9dada5);
}

.auth-page-extra a {
  color: var(--ink-400, #9dada5);
  text-decoration: none;
}

.auth-page-extra a:hover {
  color: var(--brand-700, #1f6343);
  text-decoration: underline;
}

/* ---------- 表单控件 ---------- */
.auth-form {
  display: block;
}

.auth-field {
  margin-bottom: 18px;
}

.auth-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-700, #3a4d43);
}

.auth-label-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--ink-400, #9dada5);
}

.auth-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.auth-input-wrap > i.auth-lead-icon {
  position: absolute;
  left: 14px;
  font-size: 13.5px;
  color: var(--ink-400, #9dada5);
  pointer-events: none;
  transition: color 0.2s ease;
}

.auth-input-wrap:focus-within > i.auth-lead-icon {
  color: var(--brand-600, #2a7f53);
}

.auth-input {
  width: 100%;
  height: 46px;
  padding: 0 14px 0 40px;
  border: 1px solid var(--border-strong, #d3dfd8);
  border-radius: 12px;
  background: var(--ink-50, #f8fbf9);
  font-size: 14px;
  color: var(--ink-800, #24352c);
  line-height: normal;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.auth-input::placeholder {
  color: var(--ink-400, #9dada5);
}

.auth-input:hover:not(:disabled) {
  border-color: var(--brand-300, #93cdad);
}

.auth-input:focus {
  outline: none;
  border-color: var(--brand-500, #3d9a68);
  background: #ffffff;
  box-shadow: var(--shadow-focus, 0 0 0 3px rgba(42, 127, 83, 0.15));
}

.auth-input:disabled {
  background: var(--ink-100, #f1f6f3);
  color: var(--ink-400, #9dada5);
  cursor: not-allowed;
}

.auth-input.has-trailing {
  padding-right: 44px;
}

.auth-input-trailing {
  position: absolute;
  right: 6px;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--ink-400, #9dada5);
  font-size: 13.5px;
  cursor: pointer;
  border-radius: 8px;
  transition: color 0.2s ease, background 0.2s ease;
}

.auth-input-trailing:hover {
  color: var(--brand-700, #1f6343);
  background: var(--brand-50, #f1f9f4);
}

/* 用户名建议下拉 */
.auth-suggest {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  z-index: 60;
  background: #ffffff;
  border: 1px solid var(--border, #e2ebe5);
  border-radius: 12px;
  box-shadow: var(--shadow-md, 0 8px 24px rgba(19, 58, 41, 0.08));
  padding: 6px;
  max-height: 208px;
  overflow-y: auto;
}

.auth-suggest-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 8px;
  font-size: 13.5px;
  color: var(--ink-600, #566b60);
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}

.auth-suggest-item i {
  font-size: 12.5px;
  color: var(--ink-400, #9dada5);
}

.auth-suggest-item:hover {
  background: var(--brand-50, #f1f9f4);
  color: var(--brand-700, #1f6343);
}

.auth-suggest-item:hover i {
  color: var(--brand-600, #2a7f53);
}

.auth-suggest-item.is-recent {
  font-weight: 600;
  color: var(--brand-700, #1f6343);
}

.auth-suggest-tip {
  padding: 7px 10px 5px;
  font-size: 11.5px;
  color: var(--ink-400, #9dada5);
  border-bottom: 1px solid var(--ink-100, #f1f6f3);
  margin-bottom: 4px;
}

/* 行内布局：记住登录状态 / 忘记密码 */
.auth-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 2px 0 22px;
}

.auth-check {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--ink-600, #566b60);
  cursor: pointer;
  user-select: none;
  margin: 0;
}

.auth-check input[type='checkbox'] {
  width: 16px;
  height: 16px;
  margin: 0;
  accent-color: var(--brand-600, #2a7f53);
  cursor: pointer;
}

.auth-link {
  font-size: 13px;
  color: var(--brand-700, #1f6343);
  font-weight: 600;
  text-decoration: none;
}

.auth-link:hover {
  text-decoration: underline;
}

/* 提交按钮：胶囊形，比"系统按钮"更亲和 */
.auth-submit {
  width: 100%;
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: none;
  border-radius: var(--radius-pill, 999px);
  background: var(--gradient-brand, linear-gradient(135deg, #3d9a68 0%, #1f6343 100%));
  color: #ffffff;
  font-size: 15.5px;
  font-weight: 700;
  letter-spacing: 0.5px;
  cursor: pointer;
  box-shadow: 0 10px 22px rgba(26, 95, 62, 0.22);
  transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;
}

.auth-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 14px 26px rgba(26, 95, 62, 0.3);
}

.auth-submit:disabled {
  opacity: 0.65;
  cursor: not-allowed;
  box-shadow: none;
  transform: none;
}

.auth-spinner {
  width: 15px;
  height: 15px;
  border: 2px solid rgba(255, 255, 255, 0.45);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: auth-spin 0.8s linear infinite;
}

@keyframes auth-spin {
  to {
    transform: rotate(360deg);
  }
}

/* 提示信息 */
.auth-alert {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0 0 16px;
  padding: 11px 13px;
  border-radius: 12px;
  background: #fef4f4;
  border: 1px solid #f7d9d9;
  color: #c0392b;
  font-size: 12.5px;
  line-height: 1.65;
}

.auth-alert i {
  margin-top: 2px;
}

.auth-alert.is-success {
  background: #f1faf4;
  border-color: #cbe9d7;
  color: #1e7a4c;
}

.auth-alert.is-info {
  background: #f2f8fb;
  border-color: #d5e7ef;
  color: #2b6c8a;
}

/* 表单补充说明 */
.auth-form-note {
  margin: 14px 0 0;
  font-size: 12px;
  color: var(--ink-400, #9dada5);
  line-height: 1.7;
}

/* 密码强度 */
.auth-strength {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 9px;
}

.auth-strength-bars {
  display: flex;
  gap: 5px;
  flex: 0 0 auto;
}

.auth-strength-bar {
  width: 34px;
  height: 5px;
  border-radius: var(--radius-pill, 999px);
  background: var(--ink-200, #e2ebe5);
  transition: background 0.25s ease;
}

.auth-strength-bar.is-on.level-1 {
  background: #e07a5f;
}

.auth-strength-bar.is-on.level-2 {
  background: #e0b34f;
}

.auth-strength-bar.is-on.level-3 {
  background: var(--brand-600, #2a7f53);
}

.auth-strength-text {
  font-size: 12px;
  color: var(--ink-400, #9dada5);
}

/* 页面切换 */
.auth-switch {
  margin: 20px 0 0;
  text-align: center;
  font-size: 13px;
  color: var(--ink-500, #78897f);
}

/* ---------- 响应式 ---------- */
@media (max-width: 1180px) {
  .auth-hero {
    padding: 44px 40px;
  }

  .auth-hero-intro h2 {
    font-size: 28px;
  }
}

/* 窄屏：两侧并排改成"上方一张窄横幅 + 下方表单" —— 手机上也要一眼看出这是个农作物 App，
   而不是只剩一个孤零零的登录框（改前 <960px 是直接把左栏整块 display:none）。 */
@media (max-width: 960px) {
  .auth-main {
    grid-template-columns: minmax(0, 1fr);
  }

  .auth-hero {
    /* 手机上不粘：否则滚动表单时横幅一直占着上半屏 */
    position: relative;
    top: auto;
    align-self: stretch;
    min-height: 0;
    padding: 26px 22px 24px;
    gap: 14px;
    background-position: center 58%;
  }

  .auth-hero-intro h2 {
    margin-bottom: 8px;
    font-size: 21px;
  }

  .auth-hero-intro p {
    font-size: 13px;
    line-height: 1.75;
    /* 手机上不铺开讲，三行点到为止（详细能力在下面表单区域还有说明） */
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
    overflow: hidden;
  }

  .auth-chips,
  .auth-hero-foot {
    display: none;
  }

  .auth-panel {
    padding: 26px 18px 34px;
  }
}

@media (max-width: 640px) {
  .auth-topbar {
    height: auto;
    padding: 12px 16px;
    flex-wrap: wrap;
  }

  .auth-brand-name {
    font-size: 13.5px;
    white-space: normal;
  }

  .auth-brand-sub {
    display: none;
  }

  .auth-topbar-actions {
    width: 100%;
    justify-content: space-between;
    font-size: 12.5px;
  }

  .auth-card {
    padding: 26px 20px 22px;
    border-radius: var(--radius-lg, 18px);
  }
}
</style>
