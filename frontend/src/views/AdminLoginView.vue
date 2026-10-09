<script setup>
/**
 * 管理员登录页（第 119 批：**独立页面**，不是农户登录页的变体）
 * ============================================================================
 * 第 116 批先把入口分开了（`/admin/login` 独立成页），但当时是拿农户登录页套了个
 * `variant="admin"`：同一个组件、同一个外壳，只换文案与左栏内容。结果两个界面
 * **结构上还是同一张页面**，改一边要想着另一边。
 *
 * 现在这里是真正独立的一套：
 *   · **自己的模板**：深色整屏 + 居中卡片（不是在农户页那种"左图右表单"的分栏里换内容）；
 *   · **自己的样式**（下面 scoped，不依赖 AuthShell 的 auth- 类）；
 *   · **自己的文案**（`adminAuth.*`），页面上不出现任何拍照识别 / 注册的话术；
 *   · 农户页那边同步把 `variant` 参数删掉了 —— 两张页面互不牵连。
 *
 * 共用的只有**行为**：`composables/useLoginForm.js`（用户名建议、记住登录状态、
 * 冷静期取消注销、被弹回登录页的原因码、带安全检查的登录后落点）。
 * 这份逻辑抄两份必然长歪，所以抽成组合式函数 —— 界面分开，行为一份。
 *
 * 为什么管理员登录不该长成农户那样：
 *   它是一次**低频、目标明确**的操作（进后台管理），用户清楚自己点的是哪个入口；
 *   需要的不是"拍张照片就能识别"的说服，而是"这里是管理入口、请用管理员账号"的确定性。
 *   所以深色、克制、信息量最低。
 */
import { computed } from 'vue';
import { RouterLink } from 'vue-router';
import { useI18n } from '@/i18n';
import { useAuthStore } from '@/stores/auth';
import { useLoginForm } from '@/composables/useLoginForm';
// 第 53 批的约定：认证页没有站点顶栏，语言切换必须自带 —— 否则英文用户第一屏没法切语言
import LanguageSwitcher from '@/components/LanguageSwitcher.vue';

const { t } = useI18n();
const authStore = useAuthStore();

const form = useLoginForm({ adminEntry: true });

const currentYear = new Date().getFullYear();

/** 顶部品牌副标题跟随界面语言（与农户端同一个品牌名） */
const brandName = computed(() => t('auth.brandName'));
</script>

<template>
  <div class="admin-login">
    <!-- 顶部：品牌 + 语言 + 回农户端（这一页没有站点导航，也不该有） -->
    <header class="admin-login-topbar">
      <RouterLink to="/" class="admin-login-brand">
        <span class="admin-login-logo"><i class="fas fa-user-shield"></i></span>
        <span class="admin-login-brand-text">
          <strong>{{ t('adminAuth.badge') }}</strong>
          <em>{{ brandName }}</em>
        </span>
      </RouterLink>

      <div class="admin-login-topbar-actions">
        <LanguageSwitcher />
        <RouterLink to="/login" class="admin-login-ghost">
          <i class="fas fa-arrow-left"></i>
          <span>{{ t('adminAuth.backToUser') }}</span>
        </RouterLink>
      </div>
    </header>

    <!-- 居中卡片 -->
    <main class="admin-login-main">
      <section class="admin-login-card">
        <div class="admin-login-head">
          <span class="admin-login-eyebrow">
            <i class="fas fa-shield-halved"></i> {{ t('adminAuth.eyebrow') }}
          </span>
          <h1>{{ t('adminAuth.title') }}</h1>
          <p>{{ t('adminAuth.subtitle') }}</p>
        </div>

        <form class="admin-login-form" @submit.prevent="form.handleLogin">
          <div class="al-field">
            <label class="al-label" for="username">{{ t('adminAuth.usernameLabel') }}</label>
            <div class="al-input-wrap">
              <i class="fas fa-user al-icon"></i>
              <input
                id="username"
                v-model="form.username"
                class="al-input"
                type="text"
                autocomplete="username"
                :placeholder="t('adminAuth.usernamePlaceholder')"
                :disabled="form.isLoading"
                @input="form.onUsernameChange"
                @focus="form.showUsernameSuggestions"
                @blur="form.hideUsernameSuggestions"
                required
              />
              <!-- 最近登录过的账号（只记账号名，绝不记密码） -->
              <div v-if="form.showSuggestions && form.usernameSuggestions.length > 0" class="al-suggest">
                <div class="al-suggest-tip">
                  <i class="fas fa-history"></i> {{ t('auth.recentAccounts') }}
                </div>
                <div
                  v-for="(item, index) in form.usernameSuggestions"
                  :key="item"
                  class="al-suggest-item"
                  :class="{ 'is-recent': index === 0 }"
                  @mousedown.prevent="form.selectUsername(item)"
                >
                  <i class="fas fa-user"></i> {{ item }}
                </div>
              </div>
            </div>
          </div>

          <div class="al-field">
            <label class="al-label" for="password">{{ t('auth.password') }}</label>
            <div class="al-input-wrap">
              <i class="fas fa-lock al-icon"></i>
              <input
                id="password"
                v-model="form.password"
                class="al-input has-trailing"
                :type="form.showPassword ? 'text' : 'password'"
                autocomplete="current-password"
                :placeholder="t('auth.passwordOnlyPlaceholder')"
                :disabled="form.isLoading"
                required
              />
              <button
                type="button"
                class="al-trailing"
                :title="form.showPassword ? t('auth.hidePassword') : t('auth.showPassword')"
                :aria-label="form.showPassword ? t('auth.hidePassword') : t('auth.showPassword')"
                @click="form.showPassword = !form.showPassword"
              >
                <i :class="form.showPassword ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
              </button>
            </div>
          </div>

          <div class="al-row">
            <label class="al-check" for="rememberMe">
              <input id="rememberMe" v-model="form.rememberMe" type="checkbox" :disabled="form.isLoading" />
              <span>{{ t('auth.rememberLogin') }}</span>
            </label>
            <RouterLink to="/forgot-password" class="al-link">{{ t('auth.forgotPassword') }}</RouterLink>
          </div>

          <!--
            第 120 批：把"这条路对管理员常常走不通"说清楚。
            自助找回密码只在账号**绑了邮箱**时才真的发信；没绑邮箱时后端按防枚举策略
            静默什么都不做，而页面照样显示"已发送" —— 不说清楚，管理员会一直等一封
            永远不会来的邮件。超级管理员那边有「用户管理 → 重置密码」可以签发一次性链接。
          -->
          <p class="al-forgot-hint">
            <i class="fas fa-circle-info"></i>
            {{ t('adminAuth.forgotHint') }}
          </p>

          <div v-if="form.errorMessage" class="al-alert">
            <i class="fas fa-exclamation-circle"></i>
            <span>{{ form.errorMessage }}</span>
          </div>

          <!-- 冷静期：注销中的账号登不上，这里是唯一的自助恢复入口（第 101 批） -->
          <div v-if="form.pendingDeletion" class="al-grace">
            <p class="al-grace-text">
              <i class="fas fa-clock-rotate-left"></i>
              {{ t('auth.pendingDeletionHint', { days: form.pendingDeletion.daysLeft }) }}
            </p>
            <button type="button" class="al-grace-btn" @click="form.openCancelDialog">
              <i class="fas fa-rotate-left"></i> {{ t('auth.cancelDeletion') }}
            </button>
          </div>

          <button type="submit" class="al-submit" :disabled="form.isLoading">
            <span v-if="form.isLoading" class="al-spinner"></span>
            <i v-else class="fas fa-right-to-bracket"></i>
            {{ form.isLoading ? t('auth.signingIn') : t('adminAuth.submit') }}
          </button>
        </form>

        <p class="admin-login-note">
          <i class="fas fa-circle-info"></i>
          {{ t('adminAuth.accountHint') }}
        </p>
      </section>

      <p class="admin-login-foot">
        <span>© {{ currentYear }} {{ brandName }}</span>
        <span class="al-dot">·</span>
        <span>{{ t('adminAuth.footerNote') }}</span>
      </p>
    </main>

    <!-- 取消注销确认（沿用页面自己的对话框：这里要显示错误信息，
         Element Plus 的 MessageBox 关掉就看不到了） -->
    <div v-if="form.cancelDialogVisible" class="al-modal-mask" @click.self="form.cancelDialogVisible = false">
      <div class="al-modal">
        <h3>{{ t('auth.cancelDeletionTitle') }}</h3>
        <p class="al-modal-desc">{{ t('auth.cancelDeletionDesc') }}</p>
        <div v-if="form.cancelError" class="al-alert">
          <i class="fas fa-exclamation-circle"></i>
          <span>{{ form.cancelError }}</span>
        </div>
        <p class="al-modal-account">
          <i class="fas fa-user"></i> {{ form.username || t('auth.cancelNeedsBoth') }}
        </p>
        <div class="al-modal-actions">
          <button type="button" class="al-modal-cancel" @click="form.cancelDialogVisible = false">
            {{ t('common.cancel') }}
          </button>
          <button type="button" class="al-modal-ok" :disabled="form.cancelLoading" @click="form.confirmCancelDeletion">
            <span v-if="form.cancelLoading" class="al-spinner"></span>
            {{ t('auth.cancelDeletionConfirm') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 这一页**不套 AuthShell**：深色整屏 + 居中卡片，与农户端的"左图右表单"完全不同 */
.admin-login {
  position: relative;
  min-height: 100vh;
  width: 100%;
  display: flex;
  flex-direction: column;
  color: #eaf3ee;
  background:
    radial-gradient(900px 520px at 12% 0%, rgba(61, 154, 104, 0.28), transparent 62%),
    radial-gradient(760px 460px at 100% 100%, rgba(23, 92, 63, 0.5), transparent 60%),
    linear-gradient(160deg, #0b3b2a 0%, #103f2d 46%, #0a2f21 100%);
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
}

/* 细网格纹理：只做背景，不抢内容 */
.admin-login::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.045) 1px, transparent 1px);
  background-size: 52px 52px;
  mask-image: radial-gradient(760px 520px at 50% 34%, #000 8%, transparent 76%);
  -webkit-mask-image: radial-gradient(760px 520px at 50% 34%, #000 8%, transparent 76%);
  pointer-events: none;
}

.admin-login > * {
  position: relative;
  z-index: 1;
}

/* ---------- 顶部条 ---------- */
.admin-login-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 26px;
}

.admin-login-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  text-decoration: none;
  min-width: 0;
}

.admin-login-logo {
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.16);
  color: #b7e6cb;
  font-size: 15px;
}

.admin-login-brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
  min-width: 0;
}

.admin-login-brand-text strong {
  font-size: 15px;
  font-weight: 800;
  color: #fff;
  letter-spacing: 0.3px;
}

.admin-login-brand-text em {
  font-style: normal;
  font-size: 11.5px;
  color: rgba(255, 255, 255, 0.55);
}

.admin-login-topbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.admin-login-ghost {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  color: rgba(255, 255, 255, 0.85);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.admin-login-ghost:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.36);
  color: #fff;
}

/* ---------- 居中卡片 ---------- */
.admin-login-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
  padding: 24px 20px 40px;
}

.admin-login-card {
  width: 100%;
  max-width: 430px;
  padding: 34px 32px 24px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.97);
  border: 1px solid rgba(255, 255, 255, 0.5);
  box-shadow: 0 26px 60px rgba(4, 22, 15, 0.45);
  color: var(--ink-800, #24352c);
}

.admin-login-head {
  margin-bottom: 24px;
}

.admin-login-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 12px;
  border-radius: 999px;
  background: #eef4f1;
  color: #2c4a3a;
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0.3px;
}

.admin-login-head h1 {
  margin: 14px 0 8px;
  font-size: 24px;
  font-weight: 800;
  color: #16281f;
}

.admin-login-head p {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.75;
  color: var(--ink-500, #78897f);
}

/* ---------- 表单控件（这一页自己的 al- 前缀，不依赖 AuthShell） ---------- */
.admin-login-form {
  display: block;
}

.al-field {
  margin-bottom: 16px;
}

.al-label {
  display: block;
  margin-bottom: 7px;
  font-size: 13px;
  font-weight: 600;
  color: #33475b;
}

.al-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.al-icon {
  position: absolute;
  left: 13px;
  font-size: 13px;
  color: #9dada5;
  pointer-events: none;
  transition: color 0.2s ease;
}

.al-input-wrap:focus-within .al-icon {
  color: #2a7f53;
}

.al-input {
  width: 100%;
  height: 46px;
  padding: 0 14px 0 38px;
  border: 1px solid #d3dfd8;
  border-radius: 11px;
  background: #f8fbf9;
  font-size: 14px;
  color: var(--ink-800, #24352c);
  line-height: normal;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.al-input::placeholder {
  color: #a9b6bf;
}

.al-input:hover:not(:disabled) {
  border-color: #93cdad;
}

.al-input:focus {
  outline: none;
  border-color: #3d9a68;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(42, 127, 83, 0.15);
}

.al-input:disabled {
  background: #f1f4f3;
  color: #9dada5;
  cursor: not-allowed;
}

.al-input.has-trailing {
  padding-right: 42px;
}

.al-trailing {
  position: absolute;
  right: 6px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: #9dada5;
  font-size: 13px;
  cursor: pointer;
  border-radius: 8px;
  transition: color 0.2s ease, background 0.2s ease;
}

.al-trailing:hover {
  color: #1f6343;
  background: #f1f9f4;
}

/* 最近登录账号下拉 */
.al-suggest {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  z-index: 60;
  padding: 6px;
  border-radius: 11px;
  background: #fff;
  border: 1px solid #e2ebe5;
  box-shadow: 0 12px 28px rgba(15, 61, 42, 0.14);
  max-height: 200px;
  overflow-y: auto;
}

.al-suggest-tip {
  padding: 6px 10px 5px;
  margin-bottom: 4px;
  border-bottom: 1px solid #f1f6f3;
  font-size: 11.5px;
  color: #9dada5;
}

.al-suggest-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 13.5px;
  color: #566b60;
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}

.al-suggest-item:hover {
  background: #f1f9f4;
  color: #1f6343;
}

.al-suggest-item.is-recent {
  font-weight: 600;
  color: #1f6343;
}

.al-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 2px 0 20px;
}

.al-check {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 13px;
  color: #566b60;
  cursor: pointer;
  user-select: none;
}

.al-check input[type='checkbox'] {
  width: 16px;
  height: 16px;
  margin: 0;
  accent-color: #2a7f53;
  cursor: pointer;
}

.al-link {
  font-size: 13px;
  font-weight: 600;
  color: #1f6343;
  text-decoration: none;
}

.al-link:hover {
  text-decoration: underline;
}

/* 找回密码的说明（第 120 批）：写在"忘记密码？"正下方，避免管理员干等一封不会来的邮件 */
.al-forgot-hint {
  margin: -8px 0 18px;
  font-size: 12px;
  line-height: 1.7;
  color: #93a2ad;
}

.al-forgot-hint i {
  margin-right: 6px;
  color: #b3c4cc;
}

.al-alert {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0 0 14px;
  padding: 11px 13px;
  border-radius: 11px;
  background: #fef4f4;
  border: 1px solid #f7d9d9;
  color: #c0392b;
  font-size: 12.5px;
  line-height: 1.65;
}

.al-alert i {
  margin-top: 2px;
}

.al-submit {
  width: 100%;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: none;
  border-radius: 11px;
  background: linear-gradient(135deg, #1f6343 0%, #123a29 100%);
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.5px;
  cursor: pointer;
  box-shadow: 0 10px 22px rgba(12, 45, 31, 0.28);
  transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;
}

.al-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 14px 26px rgba(12, 45, 31, 0.36);
}

.al-submit:disabled {
  opacity: 0.7;
  cursor: not-allowed;
  box-shadow: none;
  transform: none;
}

.al-spinner {
  width: 15px;
  height: 15px;
  border: 2px solid rgba(255, 255, 255, 0.45);
  border-top-color: #fff;
  border-radius: 50%;
  animation: al-spin 0.8s linear infinite;
}

@keyframes al-spin {
  to {
    transform: rotate(360deg);
  }
}

/* 冷静期 */
.al-grace {
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid #d8ead9;
  border-radius: 11px;
  background: #f3faf4;
}

.al-grace-text {
  margin: 0 0 10px;
  font-size: 13.5px;
  line-height: 1.7;
  color: #2c4a35;
}

.al-grace-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 999px;
  background: linear-gradient(135deg, #2f855a, #1f6343);
  color: #fff;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
}

.admin-login-note {
  margin: 20px 0 0;
  padding-top: 16px;
  border-top: 1px dashed #e2ebe5;
  font-size: 12px;
  line-height: 1.7;
  color: #93a2ad;
}

.admin-login-note i {
  margin-right: 6px;
  color: #9dada5;
}

.admin-login-foot {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
  max-width: 460px;
  margin: 0;
  text-align: center;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
}

.al-dot {
  color: rgba(255, 255, 255, 0.3);
}

/* 取消注销对话框 */
.al-modal-mask {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(4, 20, 13, 0.6);
}

.al-modal {
  width: 100%;
  max-width: 420px;
  padding: 24px 24px 18px;
  border-radius: 16px;
  background: #fff;
  color: var(--ink-800, #24352c);
  box-shadow: 0 18px 40px rgba(4, 20, 13, 0.4);
}

.al-modal h3 {
  margin: 0 0 10px;
  font-size: 17px;
  color: #1f3a2a;
}

.al-modal-desc {
  margin: 0 0 12px;
  font-size: 13.5px;
  line-height: 1.8;
  color: #4a5f52;
}

.al-modal-account {
  margin: 0 0 16px;
  font-size: 13.5px;
  font-weight: 600;
  color: #2c4a35;
}

.al-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.al-modal-cancel,
.al-modal-ok {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  border-radius: 999px;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
}

.al-modal-cancel {
  border: 1px solid #d7e2da;
  background: #fff;
  color: #4a5f52;
}

.al-modal-ok {
  border: none;
  background: linear-gradient(135deg, #2f855a, #1f6343);
  color: #fff;
}

.al-modal-ok:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ---------- 窄屏 ---------- */
@media (max-width: 640px) {
  .admin-login-topbar {
    flex-wrap: wrap;
    padding: 14px 16px;
  }

  .admin-login-brand-text em {
    display: none;
  }

  .admin-login-topbar-actions {
    width: 100%;
    justify-content: space-between;
  }

  .admin-login-card {
    padding: 26px 20px 20px;
    border-radius: 16px;
  }

  .admin-login-head h1 {
    font-size: 21px;
  }
}
</style>
