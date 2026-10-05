<template>
  <div class="auth-page">
    <van-nav-bar
      :title="t('auth.forgotTitle')"
      left-arrow
      @click-left="goBack"
    />

    <div class="auth-hero">
      <h2>{{ t('auth.forgotTitle') }}</h2>
      <p class="muted">{{ t('auth.forgotSubtitle') }}</p>
    </div>

    <!-- 发送成功：不再显示表单，避免用户反复点"发送" -->
    <template v-if="sent">
      <van-cell-group inset>
        <van-cell :title="t('auth.forgotSentTitle')" :label="t('auth.forgotSentBody')" />
      </van-cell-group>
      <p class="hint muted">
        <van-icon name="info-o" /> {{ t('auth.forgotNotReceived') }}
      </p>
      <div class="auth-actions">
        <van-button round block color="#2e7d32" @click="goBack">
          {{ t('auth.backToLogin') }}
        </van-button>
      </div>
      <p class="auth-switch">
        <a href="#" @click.prevent="sent = false">{{ t('auth.tryAnother') }}</a>
      </p>
    </template>

    <van-form v-else @submit="onSubmit">
      <van-cell-group inset>
        <van-field
          v-model="account"
          name="account"
          autocomplete="username"
          :label="t('auth.accountLabel')"
          :placeholder="t('auth.accountPlaceholder')"
          :rules="[{ required: true, message: t('auth.accountRequired') }]"
          clearable
        />
      </van-cell-group>

      <div class="auth-actions">
        <van-button
          round
          block
          type="primary"
          native-type="submit"
          color="#2e7d32"
          :loading="loading"
          :loading-text="t('auth.sending')"
        >
          {{ t('auth.sendReset') }}
        </van-button>
      </div>
    </van-form>

    <p class="auth-switch">
      <router-link to="/login">{{ t('auth.backToLogin') }}</router-link>
    </p>
  </div>
</template>

<script setup>
/**
 * 忘记密码（移动端，第 91 批）
 * ----------------------------------------------------------------------------
 * 改前：移动端**根本没有这个入口** —— 农户忘了密码就等于永久登不进，
 * 只能找管理员在 Django 后台重置。桌面端从第 36 批起就有，这里是补齐。
 *
 * 流程：输入用户名或注册邮箱 → 后端发重置链接到邮箱（1 小时有效）。
 * 安全：后端对"账号不存在"与"已发送"返回同一话术（防账号枚举），
 * 所以页面提示也保持中性 —— 不暗示"这个账号在不在"。
 */
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { showFailToast } from 'vant';
import { requestPasswordReset } from '@/api/auth';
import { formatApiError } from '@/api/http';
import { useI18n } from '@/i18n';

const router = useRouter();
const route = useRoute();
const { t } = useI18n();

const account = ref('');
const loading = ref(false);
const sent = ref(false);

const goBack = () => {
  // 从登录页跳过来的能回退；直接打开这个地址（书签/扫码）时回退会离开站点 → 明确去登录页
  if (window.history.length > 1) router.back();
  else router.replace({ name: 'login', query: route.query });
};

const onSubmit = async () => {
  if (loading.value) return;
  loading.value = true;
  try {
    await requestPasswordReset(account.value.trim());
    sent.value = true;
  } catch (error) {
    showFailToast(formatApiError(error, t('auth.sendFailed')));
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
  padding: 10px 20px 20px;
}

.auth-hero h2 {
  margin: 8px 0 6px;
  font-size: 1.4rem;
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

.hint {
  padding: 10px 24px 0;
  font-size: 0.8rem;
}
</style>
