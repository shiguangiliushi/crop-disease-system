<template>
  <div class="auth-page">

    <div class="auth-hero">
      <p class="muted">{{ t('auth.registerSubtitle') }}</p>
    </div>

    <van-form @submit="onSubmit">
      <van-cell-group inset>
        <van-field
          v-model="form.username"
          name="username"
          :label="t('auth.username')"
          :placeholder="t('auth.usernamePlaceholder')"
          :rules="[{ required: true, message: t('auth.usernameRequired') }]"
          clearable
        />
        <van-field
          v-model="form.password"
          type="password"
          name="password"
          :label="t('auth.password')"
          :placeholder="t('auth.passwordPlaceholder')"
          :rules="[
            { required: true, message: t('auth.passwordRequired') },
            { validator: (value) => (value || '').length >= 8, message: t('auth.passwordTooShort') },
          ]"
          clearable
        />
        <van-field
          v-model="form.confirmPassword"
          type="password"
          name="confirmPassword"
          :label="t('auth.confirmPassword')"
          :placeholder="t('auth.confirmPasswordPlaceholder')"
          :rules="[{ validator: samePassword, message: t('auth.passwordMismatch') }]"
          clearable
        />
        <van-field
          v-model="form.email"
          type="email"
          name="email"
          :label="t('auth.email')"
          :placeholder="t('auth.emailPlaceholder')"
          clearable
        />
      </van-cell-group>

      <div class="auth-actions">
        <van-button
          round
          block type="primary"
          native-type="submit"
          :loading="loading"
          :loading-text="t('auth.registering')"
        >
          {{ t('auth.register') }}
        </van-button>
      </div>
    </van-form>

    <p class="auth-switch">
      {{ t('auth.haveAccount') }}
      <router-link to="/login">{{ t('auth.backToLogin') }}</router-link>
    </p>
  </div>
</template>

<script setup>
/**
 * 注册页（移动端）
 *
 * 后端 CustomUserSerializer 只接受 username / password / email(+姓名)；
 * 且注册成功**直接签发 token**（可"注册即登录"），所以这里注册成功就直接进识别页，
 * 少一步"请重新登录"。
 */
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { showFailToast, showSuccessToast } from 'vant';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';
import { formatApiError } from '@/api/http';

const router = useRouter();
const auth = useAuthStore();
const { t } = useI18n();

const form = reactive({ username: '', password: '', confirmPassword: '', email: '' });
const loading = ref(false);

const samePassword = (value) => value === form.password;

const onSubmit = async () => {
  // 第 106 批：密码规则与后端对齐（至少 8 位、不能纯数字）。
  // 真源是 backend/api/password_policy.py —— 前端只做"提前拦一下"，
  // 让用户不必提交一次才看到错误；**后端仍会独立校验**（前端校验永远不算数）。
  const password = form.password || '';
  if (password.length < 8) {
    showFailToast(t('auth.passwordTooShort'));
    return;
  }
  if (/^\d+$/.test(password)) {
    showFailToast(t('auth.passwordTooShort'));
    return;
  }

  loading.value = true;
  try {
    const payload = { username: form.username.trim(), password: form.password };
    if (form.email.trim()) payload.email = form.email.trim();

    const result = await auth.register(payload);

    if (result?.token && result?.user) {
      showSuccessToast(t('auth.loginSuccess'));
      router.replace('/detect');
    } else {
      showSuccessToast(t('auth.registerSuccess'));
      router.replace('/login');
    }
  } catch (error) {
    showFailToast(formatApiError(error, error?.message || t('common.requestFailed')));
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  background: #fff;
  padding-bottom: calc(env(safe-area-inset-bottom, 0px) + 24px);
}

.auth-hero {
  padding: 14px 20px 12px;
}

.auth-actions {
  padding: 22px 16px 6px;
}

.auth-switch {
  text-align: center;
  font-size: 0.9rem;
  color: #55665a;
}

.auth-switch a {
  color: var(--brand);
  font-weight: 600;
  text-decoration: none;
}
</style>
