<template>
  <div class="feedback-page">
    <div class="card">
      <p class="label">{{ t('feedbackForm.category') }}</p>
      <div class="chips">
        <span
          v-for="option in categories"
          :key="option.value"
          class="chip"
          :class="{ active: form.category === option.value }"
          @click="form.category = option.value"
        >{{ option.label }}</span>
      </div>

      <p class="label">{{ t('feedbackForm.content') }}</p>
      <van-field
        v-model="form.suggestion"
        type="textarea"
        rows="4"
        maxlength="500"
        show-word-limit
        :placeholder="t('feedbackForm.contentPlaceholder')"
        class="textarea"
      />

      <p class="label">{{ t('feedbackForm.contact') }}</p>
      <van-field
        v-model="form.contact"
        maxlength="50"
        :placeholder="t('feedbackForm.contactPlaceholder')"
      />

      <p class="label">{{ t('feedbackForm.image') }}</p>
      <van-uploader v-model="fileList" :max-count="1" :after-read="onAfterRead" @delete="onDelete" />
    </div>

    <van-button block round type="primary" :loading="submitting" @click="submit">
      {{ t('feedbackForm.submit') }}
    </van-button>
  </div>
</template>

<script setup>
/** 意见反馈（第 266 批）—— 建议 / 问题 / 其他，可附图与联系方式 */
import { computed, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { showFailToast, showSuccessToast } from 'vant';
import { submitFeedback } from '@/api/feedback';
import { useI18n } from '@/i18n';
import { formatApiError } from '@/api/http';

const router = useRouter();
const { t } = useI18n();

const submitting = ref(false);
const fileList = ref([]);
const pickedFile = ref(null);
const form = reactive({ category: 'suggestion', suggestion: '', contact: '' });

const categories = computed(() => [
  { value: 'suggestion', label: t('feedbackForm.typeSuggestion') },
  { value: 'bug', label: t('feedbackForm.typeBug') },
  { value: 'other', label: t('feedbackForm.typeOther') },
]);

function onAfterRead(file) {
  pickedFile.value = file.file || null;
}

function onDelete() {
  pickedFile.value = null;
}

async function submit() {
  const text = form.suggestion.trim();
  if (!text) {
    showFailToast(t('feedbackForm.empty'));
    return;
  }
  submitting.value = true;
  try {
    await submitFeedback({
      category: form.category,
      suggestion: text,
      contact: form.contact.trim(),
      imageFile: pickedFile.value,
    });
    showSuccessToast(t('feedbackForm.submitted'));
    router.back();
  } catch (error) {
    showFailToast(formatApiError(error, t('feedbackForm.failed')));
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.feedback-page {
  padding: 12px;
  background: #f6f8f7;
  min-height: 100vh;
}

.card {
  background: #fff;
  border-radius: 14px;
  padding: 14px 16px;
  margin-bottom: 16px;
}

.label {
  margin: 4px 0 8px;
  font-size: 13px;
  color: #566b60;
}

.chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.chip {
  padding: 6px 14px;
  border-radius: 999px;
  background: #f2f6f3;
  color: #566b60;
  font-size: 13px;
}

.chip.active {
  background: #2f855a;
  color: #fff;
}

.textarea {
  background: #f7faf8;
  border-radius: 10px;
  margin-bottom: 10px;
}
</style>
