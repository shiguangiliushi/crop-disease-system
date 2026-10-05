<template>
  <div class="feedback-container">
    <div class="container">
      <h2 class="text-center my-4">用户反馈</h2>
      <div class="card shadow-sm">
        <div class="card-body">
          <form @submit.prevent="submitFeedback">
            <div class="mb-3">
              <label for="diseaseName" class="form-label">病害名称</label>
              <input type="text" class="form-control" id="diseaseName" v-model="feedback.disease_name" required>
            </div>
            <div class="mb-3">
              <label for="confidence" class="form-label">置信度</label>
              <input type="number" step="0.01" class="form-control" id="confidence" v-model.number="feedback.confidence">
            </div>
            <div class="mb-3">
              <label class="form-label">识别是否正确？</label>
              <div class="form-check">
                <input class="form-check-input" type="radio" id="correct" :value="true" v-model="feedback.is_correct">
                <label class="form-check-label" for="correct">正确</label>
              </div>
              <div class="form-check">
                <input class="form-check-input" type="radio" id="incorrect" :value="false" v-model="feedback.is_correct">
                <label class="form-check-label" for="incorrect">不正确</label>
              </div>
            </div>
            <div class="mb-3">
              <label for="suggestion" class="form-label">您的建议</label>
              <textarea class="form-control" id="suggestion" rows="4" v-model="feedback.suggestion"></textarea>
            </div>
            <div class="mb-3">
              <label for="image" class="form-label">相关图片 (可选)</label>
              <input type="file" class="form-control" id="image" @change="handleFileChange">
            </div>
            <button type="submit" class="btn btn-primary w-100">提交反馈</button>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import axios from 'axios';
import { useAuthStore } from '@/stores/auth';

const authStore = useAuthStore();
const feedback = ref({
  disease_name: '',
  confidence: null,
  is_correct: true,
  suggestion: ''
});
const feedbackImage = ref(null);

const handleFileChange = (event) => {
  feedbackImage.value = event.target.files[0];
};

const submitFeedback = async () => {
  if (!authStore.token) {
    alert('请先登录！');
    return;
  }

  const formData = new FormData();
  formData.append('disease_name', feedback.value.disease_name);
  // confidence can be null, only append if it has a value
  if (feedback.value.confidence !== null) {
    formData.append('confidence', feedback.value.confidence);
  }
  formData.append('is_correct', feedback.value.is_correct);
  formData.append('suggestion', feedback.value.suggestion);
  if (feedbackImage.value) {
    formData.append('image', feedbackImage.value);
  }

  try {
    await axios.post('/api/feedback/', formData, {
      headers: {
        'Authorization': `Token ${authStore.token}`
        // 'Content-Type': 'multipart/form-data' is set automatically by browser when using FormData
      }
    });
    alert('感谢您的反馈！');
    // Reset form
    feedback.value = {
      disease_name: '',
      confidence: null,
      is_correct: true,
      suggestion: ''
    };
    feedbackImage.value = null;
    // Reset file input
    const fileInput = document.getElementById('image');
    if (fileInput) {
      fileInput.value = '';
    }
  } catch (error) {
    console.error('提交反馈失败:', error);
    alert('提交反馈失败，请稍后再试。');
  }
};
</script>

<style scoped>
.feedback-container {
  padding: 2rem 0;
  background-color: #f8f9fa;
}
.card {
  border: none;
  border-radius: 0.5rem;
}
</style>
