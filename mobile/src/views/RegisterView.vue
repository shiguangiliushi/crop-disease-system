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
        <van-field
          v-model="form.captchaCode"
          name="captchaCode"
          :label="t('auth.captcha')"
          :placeholder="t('auth.captchaPlaceholder')"
          maxlength="4"
          autocomplete="off"
          clearable
        >
          <!-- 第 233 批：验证码图片（点击换一张）。Vant 4 的 #button 插槽就放在输入框右侧 -->
          <template #button>
            <div class="captcha-box" :title="t('auth.captchaRefresh')" @click="loadCaptcha">
              <img v-if="captcha.image" :src="captcha.image" alt="" class="captcha-image" />
              <van-loading v-else size="18" />
            </div>
          </template>
        </van-field>
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
import { reactive, ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { showFailToast, showSuccessToast } from 'vant';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';
import { formatApiError } from '@/api/http';
import { fetchCaptcha } from '@/api/auth';

const router = useRouter();
const auth = useAuthStore();
const { t } = useI18n();

const form = reactive({ username: '', password: '', confirmPassword: '', email: '', captchaCode: '' });
const loading = ref(false);

// 第 233 批：验证码（一次性、5 分钟有效；提交失败就换一张）
const captcha = ref({ id: '', image: '' });
const captchaLoading = ref(false);

async function loadCaptcha() {
  if (captchaLoading.value) return;
  captchaLoading.value = true;
  try {
    const data = await fetchCaptcha();
    captcha.value = { id: data.id, image: data.image };
    form.captchaCode = '';
  } catch (error) {
    console.warn('[register] 加载验证码失败', error);
  } finally {
    captchaLoading.value = false;
  }
}

onMounted(loadCaptcha);

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

  // 第 233 批：验证码（后端强制校验；前端先拦"没填"）
  if (!form.captchaCode.trim()) {
    showFailToast(t('auth.captchaRequired'));
    return;
  }

  loading.value = true;
  try {
    const payload = {
      username: form.username.trim(),
      password: form.password,
      captcha_id: captcha.value.id,
      captcha_code: form.captchaCode.trim(),
    };
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
    // 验证码错/过期：换一张（旧的那张已被服务端消费），再提示
    if (error?.response?.data?.captcha_code) {
      loadCaptcha();
      showFailToast(t('auth.captchaWrong'));
    } else {
      showFailToast(formatApiError(error, error?.message || t('common.requestFailed')));
    }
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

/* 第 233 批：验证码图片（输入框右侧，点击换一张） */
.captcha-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 96px;
  height: 34px;
  margin-left: 8px;
  border: 1px solid rgba(47, 133, 90, 0.18);
  border-radius: 6px;
  background: #f4f8f5;
  overflow: hidden;
  cursor: pointer;
}

.captcha-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
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
