<script setup>
/**
 * 重置密码（第 35 批新增）
 * ------------------------------------------------------------------
 * 入口是重置邮件里的链接：/reset-password?uid=xxx&token=yyy
 * 校验通过后用新密码重置，并提示"其它设备需要重新登录"
 * （后端在重置成功后会删除该用户的全部 token）。
 */
import { computed, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import ConsoleAuthShell from '@/components/ConsoleAuthShell.vue';
import { confirmPasswordReset } from '@/api/account';
import { useI18n } from '@/i18n';  // 第 61 批：多语言

const { t } = useI18n();

const route = useRoute();
const router = useRouter();

const uid = computed(() => String(route.query.uid || ''));
const token = computed(() => String(route.query.token || ''));
const linkValid = computed(() => Boolean(uid.value && token.value));

const password = ref('');
const confirmPassword = ref('');
const showPassword = ref(false);
const isLoading = ref(false);
const done = ref(false);
const errorMessage = ref('');

const mismatch = computed(
  () => password.value && confirmPassword.value && password.value !== confirmPassword.value,
);

const strength = computed(() => {
  const value = password.value || '';
  let level = 0;
  if (value.length >= 6) level += 1;
  if (value.length >= 10) level += 1;
  if (/[A-Za-z]/.test(value) && /\d/.test(value)) level += 1;
  if (/[^A-Za-z0-9]/.test(value)) level += 1;
  const text = [t('auth.strengthTooShort'), t('auth.strengthWeakShort'), t('auth.strengthFair'), t('auth.strengthGood'), t('auth.strengthVeryStrong')][level] || t('auth.strengthTooShort');
  return { level, text };
});

const handleSubmit = async () => {
  if (isLoading.value || mismatch.value) return;
  // 第 106 批：与注册/改密统一为 8 位 + 不能纯数字
  // （原来这里只判 6 位，于是**邮箱重置成了整条链路上最弱的一环**）
  if (password.value.length < 8 || /^\d+$/.test(password.value)) {
    errorMessage.value = t('auth.newPasswordTooShort');
    return;
  }

  errorMessage.value = '';
  isLoading.value = true;
  try {
    await confirmPasswordReset({
      uid: uid.value,
      token: token.value,
      newPassword: password.value,
    });
    done.value = true;
    setTimeout(() => router.push('/login'), 2500);
  } catch (error) {
    errorMessage.value =
      error?.response?.data?.message || error?.message || t('auth.resetFailed');
  } finally {
    isLoading.value = false;
  }
};
</script>

<template>
  <ConsoleAuthShell
    :eyebrow="t('auth.eyebrowDefault')"
    :title="t('auth.resetTitle')"
    :subtitle="t('auth.resetSubtitle')"
  >
    <template #topbar-actions>
      <RouterLink to="/login" class="cs-inline-link">{{ t('auth.backToLogin') }}</RouterLink>
    </template>

    <!-- 链接不完整 -->
    <div v-if="!linkValid" class="cs-alert">
      <i class="fas fa-triangle-exclamation"></i>
      <span>{{ t('auth.resetInvalid') }}</span>
    </div>
    <RouterLink v-if="!linkValid" to="/forgot-password" class="cs-submit cs-submit-link">
      {{ t('auth.requestNewLink') }}
    </RouterLink>

    <!-- 成功 -->
    <div v-else-if="done" class="cs-done">
      <div class="cs-done-icon"><i class="fas fa-circle-check"></i></div>
      <h3>{{ t('auth.resetDoneTitle') }}</h3>
      <p>{{ t('auth.resetDoneBody') }}</p>
      <RouterLink to="/login" class="cs-submit cs-submit-link">{{ t('auth.loginNowButton') }}</RouterLink>
    </div>

    <!-- 设置新密码 -->
    <form v-else class="cs-form" @submit.prevent="handleSubmit">
      <div class="cs-field">
        <label class="cs-label" for="newPassword">{{ t('auth.newPassword') }}</label>
        <div class="cs-input-wrap">
          <i class="fas fa-lock cs-lead-icon"></i>
          <input
            id="newPassword"
            v-model="password"
            class="cs-input has-trailing"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="new-password"
            :placeholder="t('auth.newPasswordPlaceholder')"
            :disabled="isLoading"
            required
          />
          <button
            type="button"
            class="cs-input-trailing"
            :title="showPassword ? t('auth.hidePassword') : t('auth.showPassword')"
            @click="showPassword = !showPassword"
          >
            <i :class="showPassword ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
          </button>
        </div>
        <div v-if="password" class="cs-strength">
          <span class="cs-strength-bar" :class="`level-${strength.level}`"></span>
          <span class="cs-strength-text">{{ strength.text }}</span>
        </div>
      </div>

      <div class="cs-field">
        <label class="cs-label" for="confirmPassword">{{ t('auth.confirmNewPassword') }}</label>
        <div class="cs-input-wrap">
          <i class="fas fa-lock cs-lead-icon"></i>
          <input
            id="confirmPassword"
            v-model="confirmPassword"
            class="cs-input"
            type="password"
            autocomplete="new-password"
            :placeholder="t('auth.confirmNewPasswordPlaceholder')"
            :disabled="isLoading"
            required
          />
        </div>
      </div>

      <div v-if="mismatch" class="cs-alert">
        <i class="fas fa-exclamation-circle"></i>
        <span>{{ t('auth.passwordMismatch') }}</span>
      </div>
      <div v-else-if="errorMessage" class="cs-alert">
        <i class="fas fa-exclamation-circle"></i>
        <span>{{ errorMessage }}</span>
      </div>

      <button type="submit" class="cs-submit" :disabled="isLoading || mismatch">
        <span v-if="isLoading" class="cs-spinner"></span>
        <i v-else class="fas fa-key"></i>
        {{ isLoading ? t('auth.resetting') : t('auth.confirmReset') }}
      </button>
    </form>
  </ConsoleAuthShell>
</template>

<style scoped>
.cs-done {
  text-align: center;
}

.cs-done-icon {
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

.cs-done h3 {
  margin: 0 0 8px;
  font-size: 17px;
  font-weight: 800;
  color: var(--ink-900);
}

.cs-done p {
  margin: 0 0 14px;
  font-size: 13.5px;
  line-height: 1.8;
  color: var(--ink-600);
}

.cs-submit-link {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 12px;
  text-decoration: none;
}

.cs-strength {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.cs-strength-bar {
  flex: 1;
  height: 5px;
  border-radius: 999px;
  background: var(--ink-200);
}

.cs-strength-bar.level-1 { background: #e0574a; }
.cs-strength-bar.level-2 { background: #e0a13a; }
.cs-strength-bar.level-3 { background: #4a9f6b; }
.cs-strength-bar.level-4 { background: var(--brand-600); }

.cs-strength-text {
  font-size: 12px;
  color: var(--ink-500);
}
</style>

