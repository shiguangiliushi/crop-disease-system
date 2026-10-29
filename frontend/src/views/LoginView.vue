<script setup>
/**
 * 农户登录页（`/login`）
 * ============================================================================
 * 第 119 批：**这里是农户自己的登录页**，不再兼任管理员入口。
 *   · 管理员登录是另一张完全独立的页面（`views/AdminLoginView.vue`：深色整屏 + 居中卡片，
 *     自己的模板与样式），两页之间只共用行为（`composables/useLoginForm.js`）；
 *   · 因此本页删掉了第 116 批那个 `variant="admin"` 参数 —— 一个页面扮演两个角色，
 *     改一边要想着另一边，最后两边都不像。
 *   · 页脚保留一个不抢眼的「管理员登录」入口：管理端虽然独立成页，
 *     但管理员总得找得到它（另外匿名访问 /admin/** 时守卫也会直接送过去）。
 */
import { RouterLink } from 'vue-router';
import AuthShell from '@/components/AuthShell.vue';
import { useI18n } from '@/i18n';
import { useLoginForm } from '@/composables/useLoginForm';

const { t } = useI18n();
const form = useLoginForm({ adminEntry: false });
</script>

<template>
  <AuthShell
    :eyebrow="t('auth.eyebrowDefault')"
    :title="t('auth.loginTitleDefault')"
    :subtitle="t('auth.loginSubtitle')"
  >
    <form class="auth-form" @submit.prevent="form.handleLogin">
      <div class="auth-field">
        <label class="auth-label" for="username">{{ t('auth.username') }}</label>
        <div class="auth-input-wrap">
          <i class="fas fa-user auth-lead-icon"></i>
          <input
            type="text"
            id="username"
            class="auth-input"
            v-model="form.username"
            @input="form.onUsernameChange"
            @focus="form.showUsernameSuggestions"
            @blur="form.hideUsernameSuggestions"
            :disabled="form.isLoading"
            :placeholder="t('auth.usernamePlaceholder')"
            autocomplete="username"
            required
          />

          <!-- 用户名建议下拉列表（只记账号名，绝不记密码） -->
          <div v-if="form.showSuggestions && form.usernameSuggestions.length > 0" class="auth-suggest">
            <div class="auth-suggest-tip"><i class="fas fa-history"></i> {{ t('auth.recentAccounts') }}</div>
            <div
              v-for="(suggestion, index) in form.usernameSuggestions"
              :key="suggestion"
              class="auth-suggest-item"
              :class="{ 'is-recent': index === 0 }"
              @mousedown.prevent="form.selectUsername(suggestion)"
            >
              <i class="fas fa-user"></i>
              {{ suggestion }}
            </div>
          </div>
        </div>
      </div>

      <div class="auth-field">
        <label class="auth-label" for="password">{{ t('auth.password') }}</label>
        <div class="auth-input-wrap">
          <i class="fas fa-lock auth-lead-icon"></i>
          <input
            :type="form.showPassword ? 'text' : 'password'"
            id="password"
            class="auth-input has-trailing"
            v-model="form.password"
            :disabled="form.isLoading"
            :placeholder="t('auth.passwordOnlyPlaceholder')"
            autocomplete="current-password"
            required
          />
          <button
            type="button"
            class="auth-input-trailing"
            :title="form.showPassword ? t('auth.hidePassword') : t('auth.showPassword')"
            :aria-label="form.showPassword ? t('auth.hidePassword') : t('auth.showPassword')"
            @click="form.showPassword = !form.showPassword"
          >
            <i :class="form.showPassword ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
          </button>
        </div>
      </div>

      <div class="auth-row">
        <label class="auth-check" for="rememberMe">
          <input type="checkbox" id="rememberMe" v-model="form.rememberMe" :disabled="form.isLoading" />
          <span>{{ t('auth.rememberLogin') }}</span>
        </label>
        <!-- 第 35 批：接上自助找回密码（此前这里写的是"请管理员重置"） -->
        <RouterLink to="/forgot-password" class="auth-link">{{ t('auth.forgotPassword') }}</RouterLink>
      </div>

      <div v-if="form.errorMessage" class="auth-alert">
        <i class="fas fa-exclamation-circle"></i>
        <span>{{ form.errorMessage }}</span>
      </div>

      <!--
        第 101 批：注销冷静期的"出路"
        ------------------------------------------------------------------
        冷静期内账号已停用、登录接口会拒，所以**这是用户唯一能自助恢复的地方**。
        只在后端明确回 `can_cancel` 时显示（不猜）。
      -->
      <div v-if="form.pendingDeletion" class="auth-grace">
        <p class="auth-grace-text">
          <i class="fas fa-clock-rotate-left"></i>
          {{ t('auth.pendingDeletionHint', { days: form.pendingDeletion.daysLeft }) }}
        </p>
        <button type="button" class="auth-grace-btn" @click="form.openCancelDialog">
          <i class="fas fa-rotate-left"></i> {{ t('auth.cancelDeletion') }}
        </button>
      </div>

      <!-- 第 246 批：登录验证码（仅后端开关打开时出现） -->
      <div v-if="form.captchaRequired" class="auth-field">
        <label class="auth-label" for="captchaCode">
          <span>{{ t('auth.captchaLabel') }}</span>
          <span class="auth-label-hint">{{ t('auth.captchaHint') }}</span>
        </label>
        <div class="auth-input-wrap">
          <i class="fas fa-shield-halved auth-lead-icon"></i>
          <input
            type="text"
            id="captchaCode"
            class="auth-input has-trailing"
            v-model="form.captchaCode"
            :disabled="form.isLoading"
            :placeholder="t('auth.captchaPlaceholder')"
            autocomplete="off"
            maxlength="4"
          />
          <button type="button" class="auth-captcha-btn" @click="form.loadCaptcha()">
            <img v-if="form.captchaImage" :src="form.captchaImage" alt="" class="auth-captcha-image" />
            <i v-else class="fas fa-rotate-right"></i>
          </button>
        </div>
        <p class="auth-field-feedback muted">
          <i class="fas fa-rotate-right"></i>
          {{ t('auth.captchaRefresh') }}
        </p>
      </div>

      <button type="submit" :disabled="form.isLoading" class="auth-submit">
        <span v-if="form.isLoading" class="auth-spinner"></span>
        <i v-else class="fas fa-right-to-bracket"></i>
        {{ form.isLoading ? t('auth.signingIn') : t('auth.loginButton') }}
      </button>
    </form>

    <!-- 农户侧：注册入口放在表单下方（手机上离拇指最近的位置），不放顶栏 -->
    <template #card-actions>
      {{ t('auth.noAccount') }}
      <RouterLink to="/register" class="auth-inline-link">{{ t('auth.registerNow') }}</RouterLink>
    </template>

    <!-- 农户侧的页脚：给管理员留一个不抢眼的入口（管理端是另一张独立页面） -->
    <template #page-foot>
      <RouterLink to="/admin/login">{{ t('adminAuth.entryLink') }}</RouterLink>
    </template>

    <!-- 取消注销确认（沿用页面自己的对话框，不引 Element Plus 的 MessageBox：
         这里需要显示错误信息，MessageBox 关掉就看不到了） -->
    <div v-if="form.cancelDialogVisible" class="auth-modal-mask" @click.self="form.cancelDialogVisible = false">
      <div class="auth-modal">
        <h3>{{ t('auth.cancelDeletionTitle') }}</h3>
        <p class="auth-modal-desc">{{ t('auth.cancelDeletionDesc') }}</p>
        <div v-if="form.cancelError" class="auth-alert">
          <i class="fas fa-exclamation-circle"></i>
          <span>{{ form.cancelError }}</span>
        </div>
        <p class="auth-modal-account">
          <i class="fas fa-user"></i> {{ form.username || t('auth.cancelNeedsBoth') }}
        </p>
        <div class="auth-modal-actions">
          <button type="button" class="auth-modal-cancel" @click="form.cancelDialogVisible = false">
            {{ t('common.cancel') }}
          </button>
          <button type="button" class="auth-modal-ok" :disabled="form.cancelLoading" @click="form.confirmCancelDeletion">
            <span v-if="form.cancelLoading" class="auth-spinner"></span>
            {{ t('auth.cancelDeletionConfirm') }}
          </button>
        </div>
      </div>
    </div>
  </AuthShell>
</template>

<style scoped>
/* 第 246 批：登录验证码（与注册页同一套观感） */
.auth-captcha-btn {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 96px;
  height: 34px;
  padding: 0;
  border: 1px solid rgba(47, 133, 90, 0.18);
  border-radius: 8px;
  background: #f4f8f5;
  cursor: pointer;
  overflow: hidden;
}

.auth-captcha-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

#captchaCode.has-trailing {
  padding-right: 112px;
}

/* 页面结构样式统一定义在 AuthShell.vue 中（auth- 前缀），此处仅保留页面级微调 */

/* ============================================================================
   第 101 批：冷静期提示与"取消注销"对话框
   （auth- 前缀的通用样式在 AuthShell 里，这里是本页独有的三块）
   ============================================================================ */
.auth-grace {
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid #d8ead9;
  border-radius: 12px;
  background: #f3faf4;
}

.auth-grace-text {
  margin: 0 0 10px;
  font-size: 13.5px;
  line-height: 1.7;
  color: #2c4a35;
}

.auth-grace-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 999px;
  background: var(--gradient-brand, linear-gradient(135deg, #2f855a, #1f6343));
  color: #fff;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
}

.auth-modal-mask {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(16, 32, 24, 0.45);
  padding: 20px;
}

.auth-modal {
  width: 100%;
  max-width: 420px;
  padding: 24px 24px 18px;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 18px 40px rgba(16, 32, 24, 0.24);
}

.auth-modal h3 {
  margin: 0 0 10px;
  font-size: 17px;
  color: #1f3a2a;
}

.auth-modal-desc {
  margin: 0 0 12px;
  font-size: 13.5px;
  line-height: 1.8;
  color: #4a5f52;
}

.auth-modal-account {
  margin: 0 0 16px;
  font-size: 13.5px;
  color: #2c4a35;
  font-weight: 600;
}

.auth-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.auth-modal-cancel,
.auth-modal-ok {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  border-radius: 999px;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
}

.auth-modal-cancel {
  border: 1px solid #d7e2da;
  background: #fff;
  color: #4a5f52;
}

.auth-modal-ok {
  border: none;
  background: var(--gradient-brand, linear-gradient(135deg, #2f855a, #1f6343));
  color: #fff;
}

.auth-modal-ok:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
