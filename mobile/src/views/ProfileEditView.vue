<template>
  <div class="edit-page">
    <van-cell-group inset>
      <van-field v-model="form.firstName" :label="t('profileEdit.nickname')" maxlength="30" clearable />
      <van-field v-model="form.email" :label="t('profileEdit.email')" type="email" maxlength="60" clearable />
      <van-field v-model="form.bio" :label="t('profileEdit.bio')" type="textarea" rows="3" maxlength="200" show-word-limit />
    </van-cell-group>

    <div class="actions">
      <van-button block round type="primary" :loading="saving" @click="save">
        {{ t('profileEdit.save') }}
      </van-button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue';
import { showFailToast, showSuccessToast } from 'vant';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';
import { formatApiError } from '@/api/http';
import { fetchProfile, updateProfile } from '@/api/profileEdit';

const auth = useAuthStore();
const { t } = useI18n();

const saving = ref(false);
const form = reactive({ firstName: '', email: '', bio: '' });

onMounted(async () => {
  // 登录响应里的 user 不含 first_name/bio，必须单独拉一次资料，
  // 否则"保存成功了、重进页面却是空的"（实测踩过）。
  form.firstName = auth.user?.first_name || '';
  form.email = auth.user?.email || '';
  form.bio = auth.user?.bio || '';

  const userId = auth.user?.id;
  if (!userId) return;
  try {
    const profile = await fetchProfile(userId);
    form.firstName = profile.first_name || '';
    form.email = profile.email || '';
    form.bio = profile.bio || '';
    auth.user = { ...(auth.user || {}), ...profile };
  } catch (error) {
    console.warn('[profile] 加载资料失败', error);
  }
});

async function save() {
  const userId = auth.user?.id;
  if (!userId) {
    showFailToast(t('profileEdit.notLoggedIn'));
    return;
  }
  // 只提交**真正改动过**的字段：把没变的 email 一起发过去，会被后端判成
  // "该邮箱已被其他账号使用"（400）—— 实测踩过。没改动就直接返回。
  const payload = {};
  if (form.firstName.trim() !== (auth.user?.first_name || '')) payload.first_name = form.firstName.trim();
  if (form.email.trim() !== (auth.user?.email || '')) payload.email = form.email.trim();
  if (form.bio.trim() !== (auth.user?.bio || '')) payload.bio = form.bio.trim();

  if (!Object.keys(payload).length) {
    showSuccessToast(t('profileEdit.noChange'));
    return;
  }

  saving.value = true;
  try {
    const updated = await updateProfile(userId, payload);
    auth.user = { ...(auth.user || {}), ...updated };
    showSuccessToast(t('profileEdit.saved'));
  } catch (error) {
    showFailToast(formatApiError(error, t('profileEdit.saveFailed')));
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.edit-page { padding: 12px 0 24px; background: #f6f8f7; min-height: 100vh; }
.actions { padding: 20px 16px 0; }
</style>
