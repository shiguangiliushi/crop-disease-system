<script setup>
import { ref, computed, watch, onMounted } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { useAuthStore } from '@/stores/auth.js';
import AuthShell from '@/components/AuthShell.vue';
import { checkUsernameAvailability } from '@/api/account';  // 第 35 批：用户名实时校验
import { fetchCaptcha } from '@/api/captcha';  // 第 233 批：注册验证码
import { useI18n } from '@/i18n';  // 第 61 批：多语言

const { t } = useI18n();

const username = ref('');
const password = ref('');
const confirmPassword = ref('');
const email = ref('');
const showPassword = ref(false);
const showConfirmPassword = ref(false);
const errorMessage = ref('');
const isLoading = ref(false);
const authStore = useAuthStore();
const router = useRouter();

// ============================================================================
// 注册验证码（第 233 批）
// ----------------------------------------------------------------------------
// 后端注册接口强制校验验证码（一次性、5 分钟有效）。这里只负责：
//   · 进页面先拿一张；点图片换一张；
//   · 提交时带上 captcha_id + captcha_code；
//   · **提交失败就换一张** —— 旧的那张已经被服务端消费/作废了，不换会一直失败。
// ============================================================================
const captcha = ref({ id: '', image: '' });
const captchaCode = ref('');
const captchaLoading = ref(false);

async function loadCaptcha() {
  if (captchaLoading.value) return;
  captchaLoading.value = true;
  try {
    const data = await fetchCaptcha();
    captcha.value = { id: data.id, image: data.image };
    captchaCode.value = '';
  } catch (error) {
    console.warn('加载验证码失败:', error);
    captcha.value = { id: '', image: '' };
    errorMessage.value = t('auth.captchaLoadFailed');
  } finally {
    captchaLoading.value = false;
  }
}

onMounted(loadCaptcha);

// ============================================================================
// 用户名实时可用性校验（第 35 批）
// ----------------------------------------------------------------------------
// 此前注册要等提交后才知道"用户名已存在"；现在输入停顿 500ms 就先去后端查一次，
// 并在输入框下方直接给出结论（可用 / 被占用 / 格式不合法）。
// 说明：前端只做提示，**服务端仍是权威**（CustomUserSerializer 里也会校验格式与唯一性）。
// ============================================================================
const usernameState = ref({ checking: false, available: null, message: '' });
let usernameTimer = null;

watch(username, (value) => {
  const name = (value || '').trim();
  if (usernameTimer) clearTimeout(usernameTimer);

  if (!name) {
    usernameState.value = { checking: false, available: null, message: '' };
    return;
  }

  usernameState.value = { checking: true, available: null, message: t('auth.checkingUsername') };
  usernameTimer = setTimeout(async () => {
    const result = await checkUsernameAvailability(name);
    // 期间用户可能又改了输入，丢弃过期结果
    if (name !== (username.value || '').trim()) return;
    usernameState.value = {
      checking: false,
      available: result?.available ?? null,
      message: result?.message || '',
    };
  }, 500);
});

// ⚠️ 第 116 批修：这里原来直接返回 `password && confirmPassword && …`，
// 两个框都空时结果是**空字符串**；而 Vue 对 `:disabled=""` 的判定是
// "空字符串也算存在"（includeBooleanAttr），于是**刚打开注册页时「创建账号」是灰的**——
// 用户看到的就是一个按不动的死按钮。用 Boolean() 收敛成真正的布尔值。
const passwordMismatch = computed(() => {
  return Boolean(password.value && confirmPassword.value && password.value !== confirmPassword.value);
});

// 密码强度：综合长度、字母、数字与符号
const passwordStrength = computed(() => {
  const value = password.value || '';
  if (!value) return { level: 0, text: '' };

  let score = 0;
  if (value.length >= 6) score += 1;
  if (value.length >= 10) score += 1;
  if (/[a-zA-Z]/.test(value) && /\d/.test(value)) score += 1;
  if (/[^a-zA-Z0-9]/.test(value)) score += 1;

  if (score <= 1) return { level: 1, text: t('auth.strengthWeak') };
  if (score === 2 || score === 3) return { level: 2, text: t('auth.strengthMedium') };
  return { level: 3, text: t('auth.strengthStrong') };
});

const handleRegister = async () => {
  if (isLoading.value || passwordMismatch.value) return;

  // 前端校验
  if (!username.value.trim()) {
    errorMessage.value = t('auth.usernameEmpty');
    return;
  }
  // 第 35 批：用户名格式与占用情况先拦一道（服务端仍会再校验一次）
  if (usernameState.value.available === false) {
    errorMessage.value = usernameState.value.message || t('auth.usernameUnavailable');
    return;
  }
  // 第 106 批：6 → 8 位，并补上"不能纯数字"。
  // 原来这里放行 6 位，而「修改密码」要求 8 位 —— 同一套系统两个口径，
  // 用户注册时能过、想改成同样的密码却被拒。真源在
  // backend/api/password_policy.py，后端仍会独立校验（前端只是提前拦）。
  if (password.value.length < 8) {
    errorMessage.value = t('auth.passwordTooShort');
    return;
  }
  if (/^\d+$/.test(password.value)) {
    errorMessage.value = t('auth.passwordTooShort');
    return;
  }
  if (email.value && !/^\S+@\S+\.\S+$/.test(email.value)) {
    errorMessage.value = t('auth.invalidEmail');
    return;
  }
  // 第 233 批：验证码是最便宜的人机校验，前端先拦"没填"
  if (!captchaCode.value.trim()) {
    errorMessage.value = t('auth.captchaRequired');
    return;
  }

  errorMessage.value = '';
  isLoading.value = true;

  try {
    const result = await authStore.register({
      username: username.value,
      password: password.value,
      email: email.value,
      captcha_id: captcha.value.id,
      captcha_code: captchaCode.value.trim(),
    });
    // 后端现在会随注册响应一并签发 token → 已经自动登录
    if (result?.token) {
      ElMessage.success(t('auth.registerOkAuto'));
      router.push('/');
    } else {
      ElMessage.success(t('auth.registerOk'));
      router.push('/login');
    }
  } catch (error) {
    console.error('Register error:', error);
    const data = error.response && error.response.data;
    if (data && data.captcha_code) {
      // 验证码错/过期：换一张再让用户填（旧的那张已经被服务端作废了）
      errorMessage.value = t('auth.captchaWrong');
      loadCaptcha();
    } else if (data) {
      if (data.detail) {
        errorMessage.value = data.detail;
      } else if (typeof data === 'object') {
        errorMessage.value = Object.values(data).join(' ');
      } else {
        errorMessage.value = data;
      }
    } else if (error.message) {
      errorMessage.value = error.message;
    } else {
      errorMessage.value = t('auth.registerFailed');
    }
  } finally {
    isLoading.value = false;
  }
};
</script>

<template>
  <AuthShell
    :eyebrow="t('auth.eyebrowDefault')"
    :title="t('auth.registerTitle')"
    :subtitle="t('auth.registerSubtitle')"
  >

    <form class="auth-form" @submit.prevent="handleRegister">
      <div class="auth-field">
        <label class="auth-label" for="username">
          <span>{{ t('auth.usernameLabel') }}</span>
          <span class="auth-label-hint">{{ t('auth.usernameRequired') }}</span>
        </label>
        <div class="auth-input-wrap">
          <i class="fas fa-user auth-lead-icon"></i>
          <input
            type="text"
            id="username"
            class="auth-input"
            v-model="username"
            :disabled="isLoading"
            :placeholder="t('auth.regUsernamePlaceholder')"
            autocomplete="username"
            required
          />
        </div>
        <!-- 第 35 批：实时反馈用户名是否可用 -->
        <p
          v-if="usernameState.message"
          class="auth-field-feedback"
          :class="{
            'is-ok': usernameState.available === true,
            'is-bad': usernameState.available === false,
          }"
        >
          <i
            :class="
              usernameState.checking
                ? 'fas fa-spinner fa-spin'
                : usernameState.available
                  ? 'fas fa-circle-check'
                  : 'fas fa-circle-xmark'
            "
          ></i>
          {{ usernameState.message }}
        </p>
      </div>

      <div class="auth-field">
        <label class="auth-label" for="email">
          <span>{{ t('auth.emailLabel') }}</span>
          <span class="auth-label-hint">{{ t('auth.emailOptional') }}</span>
        </label>
        <div class="auth-input-wrap">
          <i class="fas fa-envelope auth-lead-icon"></i>
          <input
            type="email"
            id="email"
            class="auth-input"
            v-model="email"
            :disabled="isLoading"
            :placeholder="t('auth.emailPlaceholder')"
            autocomplete="email"
          />
        </div>
      </div>

      <div class="auth-field">
        <label class="auth-label" for="password">
          <span>{{ t('auth.passwordLabel') }}</span>
          <span class="auth-label-hint">{{ t('auth.passwordAtLeast8') }}</span>
        </label>
        <div class="auth-input-wrap">
          <i class="fas fa-lock auth-lead-icon"></i>
          <input
            :type="showPassword ? 'text' : 'password'"
            id="password"
            class="auth-input has-trailing"
            v-model="password"
            :disabled="isLoading"
            :placeholder="t('auth.regPasswordPlaceholder')"
            autocomplete="new-password"
            required
          />
          <button
            type="button"
            class="auth-input-trailing"
            :title="showPassword ? t('auth.hidePassword') : t('auth.showPassword')"
            :aria-label="showPassword ? t('auth.hidePassword') : t('auth.showPassword')"
            @click="showPassword = !showPassword"
          >
            <i :class="showPassword ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
          </button>
        </div>
        <div v-if="passwordStrength.level > 0" class="auth-strength">
          <span class="auth-strength-bars">
            <span
              v-for="bar in 3"
              :key="bar"
              class="auth-strength-bar"
              :class="[{ 'is-on': bar <= passwordStrength.level }, `level-${passwordStrength.level}`]"
            ></span>
          </span>
          <span class="auth-strength-text">{{ passwordStrength.text }}</span>
        </div>
      </div>

      <div class="auth-field">
        <label class="auth-label" for="confirmPassword">
          <span>{{ t('auth.confirmPasswordLabel') }}</span>
          <span class="auth-label-hint">{{ t('auth.confirmPasswordHint') }}</span>
        </label>
        <div class="auth-input-wrap">
          <i class="fas fa-lock auth-lead-icon"></i>
          <input
            :type="showConfirmPassword ? 'text' : 'password'"
            id="confirmPassword"
            class="auth-input has-trailing"
            v-model="confirmPassword"
            :disabled="isLoading"
            :placeholder="t('auth.confirmPasswordPlaceholder')"
            autocomplete="new-password"
            required
          />
          <button
            type="button"
            class="auth-input-trailing"
            :title="showConfirmPassword ? t('auth.hidePassword') : t('auth.showPassword')"
            :aria-label="showConfirmPassword ? t('auth.hidePassword') : t('auth.showPassword')"
            @click="showConfirmPassword = !showConfirmPassword"
          >
            <i :class="showConfirmPassword ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
          </button>
        </div>
        <div v-if="passwordMismatch" class="auth-alert" style="margin: 10px 0 0">
          <i class="fas fa-exclamation-circle"></i>
          <span>{{ t('auth.passwordMismatch') }}</span>
        </div>
      </div>

      <!-- 第 233 批：注册验证码（后端强制校验；点图片换一张） -->
      <div class="auth-field">
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
            v-model="captchaCode"
            :disabled="isLoading"
            :placeholder="t('auth.captchaPlaceholder')"
            autocomplete="off"
            maxlength="4"
            required
          />
          <button
            type="button"
            class="auth-captcha-btn"
            :disabled="captchaLoading || isLoading"
            :title="t('auth.captchaRefresh')"
            :aria-label="t('auth.captchaRefresh')"
            @click="loadCaptcha()"
          >
            <img v-if="captcha.image" :src="captcha.image" alt="" class="auth-captcha-image" />
            <i v-else :class="captchaLoading ? 'fas fa-spinner fa-spin' : 'fas fa-rotate-right'"></i>
          </button>
        </div>
        <p class="auth-field-feedback muted">
          <i class="fas fa-rotate-right"></i>
          {{ t('auth.captchaRefresh') }}
        </p>
      </div>

      <div v-if="errorMessage" class="auth-alert">
        <i class="fas fa-exclamation-circle"></i>
        <span>{{ errorMessage }}</span>
      </div>

      <button type="submit" :disabled="isLoading || passwordMismatch" class="auth-submit">
        <span v-if="isLoading" class="auth-spinner"></span>
        <i v-else class="fas fa-user-plus"></i>
        {{ isLoading ? t('auth.registering') : t('auth.registerTitle') }}
      </button>

      <p class="auth-form-note">
        <i class="fas fa-info-circle"></i>
        <!-- 第 26 批：《用户协议》《隐私政策》原来只是纯文本，现在可点开查看 -->
        {{ t('auth.agreePrefix') }}
        <RouterLink to="/terms" target="_blank">{{ t('auth.terms') }}</RouterLink>
        {{ t('auth.and') }}
        <RouterLink to="/privacy" target="_blank">{{ t('auth.privacy') }}</RouterLink>{{ t('auth.agreeSuffix') }}
      </p>
    </form>

    <!-- 第 116 批：「已有账号？立即登录」从顶栏挪到表单下方（手机上离拇指最近的位置） -->
    <template #card-actions>
      {{ t('auth.hasAccount') }}
      <RouterLink to="/login" class="auth-inline-link">{{ t('auth.loginNow') }}</RouterLink>
    </template>
  </AuthShell>
</template>

<style scoped>
/* 第 233 批：验证码图片（点击换一张） */
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

.auth-captcha-btn:disabled {
  cursor: progress;
  opacity: 0.7;
}

.auth-captcha-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

/* 第 233 批：验证码输入框要给右侧的图片留出宽度（默认 has-trailing 只有 44px） */
#captchaCode.has-trailing {
  padding-right: 112px;
}

.auth-form :deep(.auth-form-note i) {
  margin-right: 6px;
  color: #b3c4cc;
}

/* 用户名实时校验反馈（第 35 批） */
.auth-field-feedback {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 8px 0 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--ink-500, #78897f);
}

.auth-field-feedback.is-ok {
  color: var(--brand-700, #1f6343);
}

.auth-field-feedback.is-bad {
  color: #cf4436;
}
</style>



