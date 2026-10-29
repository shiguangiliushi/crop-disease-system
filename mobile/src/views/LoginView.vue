<template>
  <div class="auth-page">
    <div class="brand-bar">
      <span class="brand-logo">叶</span>
      <h1>{{ t('common.appName') }}</h1>
      <button type="button" class="lang-switch" @click="toggleLocale">
        {{ locale === 'en' ? '中文' : 'EN' }}
      </button>
    </div>

    <div class="auth-hero">
      <!--
        第 173 批：这里原来的 `<h2>{{ t('auth.loginTitle') }}</h2>` 与外壳顶栏重复
        （顶栏标题用的就是同一个 key），去掉标题、保留副标题。
      -->
      <p class="muted">{{ t('auth.loginSubtitle') }}</p>
    </div>

    <van-form @submit="onSubmit">
      <!-- 第 91 批：被 401 踢回来时说明原因，而不是让用户对着"请求失败"发呆 -->
      <van-notice-bar
        v-if="sessionExpired"
        left-icon="info-o"
        color="#8a5a12"
        background="#fdf6ea"
        :text="t('auth.sessionExpired')"
        wrapable
        class="auth-notice"
      />
      <van-cell-group inset>
        <van-field
          v-model="form.username"
          name="username"
          autocomplete="username"
          :label="t('auth.username')"
          :placeholder="t('auth.usernamePlaceholder')"
          :rules="[{ required: true, message: t('auth.usernameRequired') }]"
          clearable
        />
        <van-field
          v-model="form.password"
          type="password"
          name="password"
          autocomplete="current-password"
          :label="t('auth.password')"
          :placeholder="t('auth.passwordPlaceholder')"
          :rules="[{ required: true, message: t('auth.passwordRequired') }]"
          clearable
        />
        <!-- 第 247 批：登录验证码（仅在服务端开关打开时出现） -->
        <van-field
          v-if="captchaRequired"
          v-model="captchaCode"
          name="captchaCode"
          :label="t('auth.captcha')"
          :placeholder="t('auth.captchaPlaceholder')"
          maxlength="4"
          autocomplete="off"
          clearable
        >
          <template #button>
            <div class="captcha-box" @click="loadCaptcha">
              <img v-if="captchaImage" :src="captchaImage" alt="" class="captcha-image" />
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
          :loading-text="t('auth.loggingIn')"
        >
          {{ t('auth.login') }}
        </van-button>
      </div>
    </van-form>

    <!-- 第 91 批：忘记密码入口（此前移动端没有，忘了密码 = 永久登不进） -->
    <p class="auth-forgot">
      <router-link to="/forgot-password">{{ t('auth.forgot') }}</router-link>
    </p>

    <p class="auth-switch">
      {{ t('auth.noAccount') }}
      <router-link to="/register">{{ t('auth.registerNow') }}</router-link>
    </p>

    <!--
      法务链接（第 91 批修正）
      ----------------------------------
      原来这里是 `<a href="/terms" target="_blank">`，而**移动端没有这两个路由**，
      会落到兜底 redirect（`/:pathMatch(.*)*` → `/detect`）—— 用户点"用户协议"
      新开一个标签页，看到的是识别页。合规入口形同虚设。
      现在改为指向**桌面端已实现的法务页**（地址来自 VITE_LEGAL_BASE_URL）；
      没配置就整段不显示 —— 宁可没有入口，也不要"点开不是那个页面"。
    -->
    <p v-if="legalBase" class="auth-terms muted">
      {{ t('auth.agreePrefix') }}
      <a :href="legalUrl('terms')" target="_blank" rel="noopener">{{ t('auth.terms') }}</a>
      {{ t('auth.and') }}
      <a :href="legalUrl('privacy')" target="_blank" rel="noopener">{{ t('auth.privacy') }}</a>
    </p>
  </div>
</template>

<script setup>
/**
 * 登录页（移动端）
 * 表单校验交给 van-form 的 rules（回车即提交、错误提示贴近输入框），
 * 错误文案统一走统一 API 客户端抛出的可读消息。
 */
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { showFailToast, showSuccessToast } from 'vant';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';
import { consumeAuthExpiredFlag, formatApiError } from '@/api/http';
import { fetchCaptcha, loginCaptchaRequired } from '@/api/auth';  // 第 247 批：登录验证码

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const { t, locale, setLocale } = useI18n();

const form = reactive({ username: '', password: '' });

// 第 247 批：登录验证码（默认关闭，后端开关打开时才显示）
const captchaRequired = ref(false);
const captchaId = ref('');
const captchaImage = ref('');
const captchaCode = ref('');

async function loadCaptcha() {
  try {
    captchaRequired.value = await loginCaptchaRequired();
    if (!captchaRequired.value) return;
    const data = await fetchCaptcha();
    captchaId.value = data.id;
    captchaImage.value = data.image;
    captchaCode.value = '';
  } catch (error) {
    console.warn('[login] 加载验证码失败，按"不需要验证码"处理', error);
    captchaRequired.value = false;
  }
}

onMounted(loadCaptcha);
const loading = ref(false);

// 第 91 批：两个入口条件
//   · `?reason=expired`（401 自愈跳过来的）或 sessionStorage 里的标记 → 提示"登录已过期"
//   · 配了 VITE_LEGAL_BASE_URL 才显示法务链接（见模板里的说明）
const sessionExpired = computed(
  () => route.query.reason === 'expired' || consumeAuthExpiredFlag(),
);

const legalBase = (import.meta.env.VITE_LEGAL_BASE_URL || '').replace(/\/+$/, '');
const legalUrl = (path) => `${legalBase}/${path}`;

const toggleLocale = () => setLocale(locale.value === 'en' ? 'zh-CN' : 'en');

const onSubmit = async () => {
  loading.value = true;
  try {
    await auth.login({
      username: form.username.trim(),
      password: form.password,
      captchaId: captchaRequired.value ? captchaId.value : '',
      captchaCode: captchaRequired.value ? captchaCode.value.trim() : '',
    });
    showSuccessToast(t('auth.loginSuccess'));
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/detect';
    router.replace(redirect);
  } catch (error) {
    if (error?.response?.data?.captcha_required) {
      // 第 247 批：验证码错/过期 —— 换一张再填
      await loadCaptcha();
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
/* 第 247 批：登录验证码图片（与注册页同一套观感） */
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

.auth-page {
  min-height: 100vh;
  background: #fff;
  padding-bottom: calc(env(safe-area-inset-bottom, 0px) + 24px);
}

.auth-hero {
  padding: 10px 20px 20px;
}

.auth-hero h2 {
  margin: 8px 0 6px;
  font-size: 1.5rem;
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

.auth-terms {
  text-align: center;
  padding: 0 24px;
  font-size: 0.78rem;
}

.auth-terms a {
  color: var(--brand);
}

/* 第 91 批：忘记密码入口（放在登录按钮下方，右对齐更贴近"辅助操作"的位置） */
.auth-forgot {
  margin: 4px 20px 0;
  text-align: right;
  font-size: 0.86rem;
}

.auth-forgot a {
  color: var(--brand);
  font-weight: 600;
  text-decoration: none;
}

/* 第 91 批：登录过期提示条（贴着表单顶部，不要挤掉输入框） */
.auth-notice {
  margin: 0 16px 12px;
  border-radius: 10px;
}
</style>
