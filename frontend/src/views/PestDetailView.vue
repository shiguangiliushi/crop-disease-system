<template>
  <div class="pest-detail-container">
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>{{ t('pestDetail.loading') }}</p>
    </div>

    <div v-if="error" class="error-state">
      <h2><i class="icon-error"></i> {{ t('pestDetail.loadFailed') }}</h2>
      <p>{{ error }}</p>
      <button @click="goBack" class="btn btn-secondary">{{ t('pestDetail.backToList') }}</button>
    </div>

    <div v-if="pest" class="pest-detail-card">
      <div class="card-header">
        <h1 class="pest-name">{{ localizedField(pest, 'name') || t('pestDetail.title') }}</h1>
        <div class="header-actions">
          <button v-if="canManage" @click="editDialogVisible = true" class="btn-edit">
            <i class="bi bi-pencil-square"></i> {{ t('pestDetail.editPest') }}
          </button>
          <button @click="goBack" class="btn-back">
            <i class="icon-back"></i> {{ t('pestDetail.backToList') }}
          </button>
        </div>
      </div>
      <div class="pest-content">
        <div class="image-container" v-if="pest.image">
          <img :src="fullImageUrl" :alt="localizedField(pest, 'name')" class="pest-image" />
        </div>
        <div class="details-text">
          <div class="detail-section">
            <h3><i class="icon-symptom"></i> {{ t('pestDetail.symptoms') }}</h3>
            <p>{{ localizedField(pest, 'symptoms') || t('pestDetail.noSymptoms') }}</p>
          </div>
          <div class="detail-section">
            <h3><i class="icon-trigger"></i> {{ t('pestDetail.pattern') }}</h3>
            <p>{{ localizedField(pest, 'trigger') || t('pestDetail.noPattern') }}</p>
          </div>
          <div class="detail-section">
            <h3><i class="icon-prevention"></i> {{ t('pestDetail.treatment') }}</h3>
            <div v-if="parsedPreventionMethods.length">
              <div v-for="(method, idx) in parsedPreventionMethods" :key="idx" class="prevention-group">
                <h4>{{ categoryLabel(method.category) }}</h4>
                <div class="measure-text">{{ localizedField(method, 'measure') }}</div>
              </div>
            </div>
            <p v-else>{{ t('pestDetail.noTreatment') }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 管理员编辑弹窗：登录管理员账号即可在此修改病害百科内容 -->
    <PestEditDialog v-model="editDialogVisible" :pest-id="pestId" @saved="handleSaved" />
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import api from '@/api'; // Using the api object instead of apiClient
import { useAuthStore } from '@/stores/auth';
import PestEditDialog from '@/components/PestEditDialog.vue';
import { toAbsoluteMediaUrl } from '@/api/http';
import { useI18n } from '@/i18n';  // 第 60 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 69 批：内容数据多语言

const { t } = useI18n();
const { localizedField } = useLocalized();

const route = useRoute();
const router = useRouter();

const pest = ref(null);
const loading = ref(true);
const error = ref('');
const editDialogVisible = ref(false);

// 管理员可在此直接编辑病害百科内容
const authStore = useAuthStore();
const canManage = computed(() => {
  const user = authStore.user;
  return !!(user?.is_staff || user?.is_superuser || user?.role === 'ADMIN');
});

// 编辑接口需要数字主键
const pestId = computed(() => pest.value?.id ?? null);

// 防治类别：改用 i18n（第 72 批）—— 原来写死中文，英文界面下仍然显示"农业防治"等
const CATEGORY_KEYS = {
  AGRICULTURAL: 'prevent.agricultural',
  CHEMICAL: 'prevent.chemical',
  ECOLOGICAL: 'prevent.ecological',
  PHYSICAL: 'prevent.physical',
  MONITORING: 'prevent.monitoring',
};

const categoryLabel = (key) => (CATEGORY_KEYS[key] ? t(CATEGORY_KEYS[key]) : t('prevent.general'));

// Computed property to construct the full image URL
const fullImageUrl = computed(() => {
  // 统一由 @/api/http 处理（自动去掉 /api 前缀、兼容绝对地址）
  return toAbsoluteMediaUrl(pest.value?.image);
});

// Computed property to parse the prevention methods JSON string
const parsedPreventionMethods = computed(() => {
  if (pest.value && typeof pest.value.prevention_methods === 'string') {
    try {
      const methods = JSON.parse(pest.value.prevention_methods);
      return Array.isArray(methods) ? methods : [];
    } catch (e) {
      console.error("Failed to parse prevention methods:", e);
      return []; // Return empty array on parsing error
    }
  }
  // Also handle if the data is already an array
  if (Array.isArray(pest.value.prevention_methods)) {
    return pest.value.prevention_methods;
  }
  return [];
});

const loadPest = async () => {
  const identifier = route.params.english_identifier;
  loading.value = true;
  error.value = '';
  try {
    console.log('Fetching pest details for:', identifier);
    // 使用正确的API路径 /pests/{identifier}/
    // 注意：api 实例已经包含了 /api 前缀，所以这里不需要再加 /api
    const response = await api.get(`pests/${identifier}/`);
    pest.value = response.data;
  } catch (err) {
    console.error('Failed to fetch pest details:', err);
    if (err.response) {
      console.error('Response status:', err.response.status);
      console.error('Response data:', err.response.data);
    }
    error.value = t('pestDetail.loadFailedDetail', { detail: err.message });
  } finally {
    loading.value = false;
  }
};

onMounted(loadPest);

/** 编辑保存后：直接使用接口返回的最新数据，若英文标识符变更则同步地址栏 */
const handleSaved = (updated) => {
  if (!updated || typeof updated !== 'object') {
    loadPest();
    return;
  }

  pest.value = updated;

  const newIdentifier = updated.english_identifier;
  if (newIdentifier && newIdentifier !== route.params.english_identifier) {
    router.replace({ name: 'PestDetail', params: { english_identifier: newIdentifier } });
  }
};

const goBack = () => {
  router.push('/pests');
};
</script>

<style scoped>
.pest-detail-container {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.loading-state, .error-state {
  text-align: center;
  padding: 4rem;
  background-color: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.06);
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #2a7f53;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 1rem;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.pest-detail-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.08);
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem 2rem;
  background-color: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
}

.pest-name {
  font-size: 2rem;
  font-weight: 700;
  color: #333;
  margin: 0;
}

.btn-back {
  background: none;
  border: 1px solid #ccc;
  color: #555;
  padding: 0.5rem 1rem;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-back:hover {
  background-color: #e9ecef;
  border-color: #aaa;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.btn-edit {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1.1rem;
  border: 1px solid #2a7f53;
  border-radius: 20px;
  background: #2a7f53;
  color: #fff;
  cursor: pointer;
  transition: all 0.3s;
}

.btn-edit:hover {
  background: #1f6343;
  border-color: #1f6343;
}

.pest-content {
  display: grid;
  grid-template-columns: 1fr;
  gap: 2rem;
  padding: 2rem;
}

@media (min-width: 768px) {
  .pest-content {
    grid-template-columns: 400px 1fr;
  }
}

.image-container {
  text-align: center;
}

.pest-image {
  width: 100%;
  max-width: 400px;
  border-radius: 10px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.1);
  object-fit: cover;
}

.detail-section {
  margin-bottom: 2rem;
}

.detail-section h3 {
  font-size: 1.3rem;
  font-weight: 600;
  color: #2a7f53;
  margin-bottom: 0.8rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid #e0e0e0;
  display: flex;
  align-items: center;
  gap: 0.7rem;
}

.detail-section p, .detail-section pre {
  font-size: 1rem;
  line-height: 1.7;
  color: #495057;
  white-space: pre-wrap; /* Allows text to wrap */
  word-wrap: break-word;
}

.prevention-group {
  margin-bottom: 1.5rem;
}

.prevention-group h4 {
  font-size: 1.1rem;
  font-weight: 600;
  color: #34495e;
  margin-bottom: 0.5rem;
}

.measure-text {
  padding-left: 1rem;
  border-left: 3px solid #76c7c0;
  color: #555;
}

.btn {
  padding: 0.8rem 1.5rem;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  transition: background-color 0.3s;
}

.btn-secondary {
  background-color: #6c757d;
  color: white;
}
.btn-secondary:hover {
  background-color: #5a6268;
}

/* Icons (placeholders) */
[class^="icon-"] {
  display: inline-block;
  width: 1.2em;
  height: 1.2em;
  /* In a real app, you'd use background images or a font icon library */
}
/* ================= 现代化覆写（设计变量见 assets/theme.css） ================= */
.pest-detail-container {
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 24px 48px;
  box-sizing: border-box;
}

.loading-state,
.error-state {
  padding: 60px 24px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.error-state h2 {
  color: var(--danger);
  font-size: 20px;
}

.pest-detail-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background: var(--surface);
  box-shadow: var(--shadow-md);
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  padding: 26px 32px;
  background: var(--gradient-brand-soft);
  border-bottom: 1px solid var(--border);
}

.pest-name {
  font-size: 28px;
  font-weight: 800;
  letter-spacing: 0.5px;
  color: var(--brand-800);
}

.btn-back,
.btn-edit {
  padding: 9px 20px;
  border-radius: var(--radius-pill);
  font-size: 13.5px;
  font-weight: 600;
  transition: all var(--dur) var(--ease);
}

.btn-back {
  border: 1px solid var(--border-strong);
  background: var(--surface);
  color: var(--ink-600);
}

.btn-back:hover {
  border-color: var(--brand-400);
  background: var(--brand-50);
  color: var(--brand-700);
}

.btn-edit {
  border: none;
  background: var(--gradient-brand);
  color: #fff;
  box-shadow: 0 8px 18px rgba(31, 99, 67, 0.22);
}

.btn-edit:hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 24px rgba(31, 99, 67, 0.28);
}

.pest-content {
  gap: 32px;
  padding: 32px;
}

.image-container {
  position: relative;
}

.pest-image {
  width: 100%;
  max-width: 100%;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  object-fit: cover;
}

.detail-section {
  margin-bottom: 28px;
  padding: 20px 22px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-muted);
}

.detail-section h3 {
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
  font-size: 16px;
  font-weight: 700;
  color: var(--brand-700);
}

.detail-section p,
.detail-section pre {
  font-size: 14.5px;
  line-height: 1.9;
  color: var(--ink-700);
}

.prevention-group {
  padding: 14px 16px;
  margin-bottom: 12px;
  border-radius: var(--radius);
  background: var(--surface);
  border: 1px solid var(--border);
}

.prevention-group h4 {
  display: inline-flex;
  align-items: center;
  margin-bottom: 8px;
  padding: 3px 12px;
  border-radius: var(--radius-pill);
  background: var(--brand-100);
  color: var(--brand-700);
  font-size: 13px;
  font-weight: 700;
}

.measure-text {
  padding-left: 14px;
  border-left: 3px solid var(--brand-300);
  color: var(--ink-700);
  font-size: 14px;
  line-height: 1.85;
}

@media (max-width: 768px) {
  .pest-detail-container {
    padding: 0 16px 32px;
  }

  .card-header {
    padding: 20px;
  }

  .pest-name {
    font-size: 22px;
  }

  .pest-content {
    padding: 20px;
  }
}
</style>

