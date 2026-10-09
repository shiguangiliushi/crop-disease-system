<script setup>
/**
 * 忘记密码（第 35 批新增）
 * ------------------------------------------------------------------
 * 此前登录页只有一句"忘记密码请联系系统管理员重置"，用户没有任何自助途径。
 * 现在：输入用户名或邮箱 → 后端给注册邮箱发一封带链接的邮件（1 小时有效）。
 * 安全说明：无论账号是否存在，页面提示都一致 —— 避免被用来枚举系统里有哪些账号。
 */
import { ref } from 'vue';
import { RouterLink } from 'vue-router';
import AuthShell from '@/components/AuthShell.vue';
import { requestPasswordReset } from '@/api/account';
import { useI18n } from '@/i18n';  // 第 61 批：多语言

const { t } = useI18n();

const account = ref('');
const isLoading = ref(false);
const sent = ref(false);
const errorMessage = ref('');
const devHint = ref('');

const handleSubmit = async () => {
  if (isLoading.value) return;
  const value = account.value.trim();
  if (!value) {
    errorMessage.value = t('auth.usernameOrEmailPlaceholder');
    return;
  }

  errorMessage.value = '';
  isLoading.value = true;
  try {
    const data = await requestPasswordReset(value);
    sent.value = true;
    devHint.value = data?.message || '';
  } catch (error) {
    errorMessage.value =
      error?.response?.data?.message || error?.message || t('auth.sendFailed');
  } finally {
    isLoading.value = false;
  }
};
</script>

<template>
  <AuthShell
    :eyebrow="t('auth.eyebrowDefault')"
    :title="t('auth.forgotTitle')"
    :subtitle="t('auth.forgotSubtitle')"
  >
    <template #topbar-actions>
      {{ t('auth.rememberIt') }}<RouterLink to="/login" class="auth-inline-link">{{ t('auth.backToLogin') }}</RouterLink>
    </template>

    <!-- 发送成功 -->
    <div v-if="sent" class="auth-done">
      <div class="auth-done-icon"><i class="fas fa-envelope-circle-check"></i></div>
      <h3>{{ t('auth.forgotSentTitle') }}</h3>
      <p>
        {{ t('auth.forgotSentBody') }}
        <strong>{{ t('auth.oneHour') }}</strong>{{ t('auth.forgotSentTail') }}
      </p>
      <p class="auth-done-tip">
        <i class="fas fa-circle-info"></i>
        {{ t('auth.forgotNotReceived') }}
      </p>
      <RouterLink to="/login" class="auth-submit auth-submit-link">{{ t('auth.backToLogin') }}</RouterLink>
      <button type="button" class="auth-link-btn" @click="sent = false">
        {{ t('auth.tryAnother') }}
      </button>
    </div>

    <!-- 输入账号 -->
    <form v-else class="auth-form" @submit.prevent="handleSubmit">
      <div class="auth-field">
        <label class="auth-label" for="account">
          <span>{{ t('auth.usernameOrEmail') }}</span>
          <span class="auth-label-hint">{{ t('auth.eitherOne') }}</span>
        </label>
        <div class="auth-input-wrap">
          <i class="fas fa-user auth-lead-icon"></i>
          <input
            id="account"
            v-model="account"
            class="auth-input"
            type="text"
            autocomplete="username"
            :placeholder="t('auth.usernameOrEmailPlaceholder')"
            :disabled="isLoading"
            required
          />
        </div>
      </div>

      <div v-if="errorMessage" class="auth-alert">
        <i class="fas fa-exclamation-circle"></i>
        <span>{{ errorMessage }}</span>
      </div>

      <button type="submit" class="auth-submit" :disabled="isLoading">
        <span v-if="isLoading" class="auth-spinner"></span>
        <i v-else class="fas fa-paper-plane"></i>
        {{ isLoading ? t('auth.sending') : t('auth.sendResetLink') }}
      </button>
    </form>
  </AuthShell>
</template>

<style scoped>
.auth-done {
  text-align: center;
}

.auth-done-icon {
  width: 56px;
  height: 56px;
  margin: 4px auto 14px;
  display: grid;
  place-items: center;
  border-radius: 18px;
  font-size: 24px;
  color: #fff;
  background: linear-gradient(135deg, var(--brand-500), var(--brand-700));
  box-shadow: 0 10px 22px rgba(25, 79, 55, 0.24);
}

.auth-done h3 {
  margin: 0 0 8px;
  font-size: 17px;
  font-weight: 800;
  color: var(--ink-900);
}

.auth-done p {
  margin: 0 0 10px;
  font-size: 13.5px;
  line-height: 1.8;
  color: var(--ink-600);
}

.auth-done-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--ink-500);
}

.auth-submit-link {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 14px;
  text-decoration: none;
}

.auth-link-btn {
  margin-top: 10px;
  border: none;
  background: none;
  color: var(--brand-700);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
}
</style>

