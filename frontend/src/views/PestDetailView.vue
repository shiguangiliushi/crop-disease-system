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
          <!-- 第 402 批：病害订阅开关（仅登录用户可见；点击即订阅/取消，不跳转） -->
          <button
            v-if="isLoggedIn && pest"
            type="button"
            class="btn-subscribe"
            :class="{ 'is-subscribed': pestSubscribed }"
            :disabled="pestSubscriptionLoading || pestSubscriptionChecking"
            :aria-pressed="pestSubscribed"
            :title="pestSubscribed ? t('pestDetail.unsubscribePest') : t('pestDetail.subscribePest')"
            @click="togglePestSubscription"
          >
            <i
              :class="pestSubscriptionLoading || pestSubscriptionChecking
                ? 'fas fa-spinner fa-spin'
                : pestSubscribed ? 'fas fa-bell' : 'fas fa-bell-plus'"
            ></i>
            {{ pestSubscribed ? t('pestDetail.subscribedPest') : t('pestDetail.subscribePest') }}
          </button>
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

    <!-- 第 401 批：相关行业动态（按 pest=<id> 过滤；无数据 / 接口失败整块不渲染） -->
    <section v-if="relatedNews.length" class="related-news-section">
      <div class="related-news-head">
        <h2>
          <i class="fas fa-newspaper"></i> {{ t('pestDetail.relatedNews') }}
        </h2>
        <router-link class="related-news-more" :to="{ name: 'news' }">
          {{ t('pestDetail.viewAllNews') }} <i class="fas fa-arrow-right"></i>
        </router-link>
      </div>
      <div class="related-news-grid">
        <article
          v-for="item in relatedNews"
          :key="item.id"
          class="related-news-card"
          @click="goToNews(item.id)"
        >
          <span v-if="item.category" class="related-news-cat">{{ getCategoryLabel(item.category) }}</span>
          <h3 class="related-news-title">{{ localizedField(item, 'title') }}</h3>
          <p class="related-news-summary">{{ relatedSummary(item) }}</p>
          <span class="related-news-date">
            <i class="fas fa-clock"></i> {{ formatDate(item.created_at) }}
          </span>
        </article>
      </div>
    </section>

    <!-- 管理员编辑弹窗：登录管理员账号即可在此修改病害百科内容 -->
    <PestEditDialog v-model="editDialogVisible" :pest-id="pestId" @saved="handleSaved" />
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';  // 第 402 批：订阅成功/失败提示
import api from '@/api'; // Using the api object instead of apiClient
import { useAuthStore } from '@/stores/auth';
import PestEditDialog from '@/components/PestEditDialog.vue';
import { toAbsoluteMediaUrl, formatApiError } from '@/api/http';
import { useI18n } from '@/i18n';  // 第 60 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 69 批：内容数据多语言
// 第 401 批：病害详情页底部的「相关行业动态」（按 pest=<id> 过滤）
import { fetchNewsList, getNewsCategoryLabel } from '@/api/news';
import { stripHtmlText } from '@/utils/newsContent';
// 第 402 批：病害订阅（状态查询 / 新建 / 取消）—— 接口未上线时按钮按未订阅降级
import {
  checkNewsSubscription,
  createNewsSubscription,
  deleteNewsSubscription,
} from '@/api/newsSubscription';

const { t, locale } = useI18n();
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

/**
 * 第 402 批：病害订阅
 * ------------------------------------------------------------------
 * 订阅某个病害后，该病害相关的新行业动态会以 type='news' 的站内通知投递。
 * 与列表页的分类订阅同一套约定：
 *   · 仅登录用户可见（`authStore.user` 与 canManage 同源，不另造登录判断）；
 *   · 状态以 check 接口为准，并用**序号**防止慢响应覆盖新目标；
 *   · 未登录 / 接口未上线（404）/ 网络失败 → 静默降级为「未订阅」，不阻断词条浏览；
 *   · 点击失败只弹提示，不动词条内容。
 */
const isLoggedIn = computed(() => Boolean(authStore.user));
const pestSubscribed = ref(false);
const pestSubscriptionId = ref(null);
const pestSubscriptionLoading = ref(false);
const pestSubscriptionChecking = ref(false);
let pestSubscriptionSeq = 0;

const resetPestSubscription = () => {
  pestSubscribed.value = false;
  pestSubscriptionId.value = null;
};

/** 重查该词条的订阅状态；用 seq 丢弃过期响应 —— 连续切词条时旧的 check 返回会盖掉新的 */
const refreshPestSubscription = async () => {
  const id = pest.value?.id;
  const seq = ++pestSubscriptionSeq;

  if (!isLoggedIn.value || !id) {
    resetPestSubscription();
    pestSubscriptionChecking.value = false;
    return;
  }

  resetPestSubscription();
  pestSubscriptionChecking.value = true;
  try {
    const data = await checkNewsSubscription({ target_type: 'pest', pest: id });
    if (seq !== pestSubscriptionSeq) return;
    pestSubscribed.value = data.subscribed;
    pestSubscriptionId.value = data.id;
  } catch (error) {
    if (seq !== pestSubscriptionSeq) return;
    console.warn('获取病害订阅状态失败（按未订阅处理）:', error);
    resetPestSubscription();
  } finally {
    if (seq === pestSubscriptionSeq) pestSubscriptionChecking.value = false;
  }
};

/** 订阅/退订：已订阅却拿不到订阅 id 时先重查一次，否则会拿 undefined 去调删除接口 */
const togglePestSubscription = async () => {
  const id = pest.value?.id;
  if (!isLoggedIn.value || !id || pestSubscriptionLoading.value) return;

  if (pestSubscribed.value && !pestSubscriptionId.value) {
    await refreshPestSubscription();
    return;
  }

  pestSubscriptionLoading.value = true;
  try {
    if (pestSubscribed.value) {
      await deleteNewsSubscription(pestSubscriptionId.value);
      ElMessage.success(t('pestDetail.unsubscribePestOk'));
    } else {
      await createNewsSubscription({ target_type: 'pest', pest: id });
      ElMessage.success(t('pestDetail.subscribePestOk'));
    }
    await refreshPestSubscription();
  } catch (error) {
    console.error('切换病害订阅失败:', error);
    ElMessage.error(formatApiError(error, t('pestDetail.subscribeFailed')));
  } finally {
    pestSubscriptionLoading.value = false;
  }
};

/**
 * 第 401 批：底部「相关行业动态」
 * ------------------------------------------------------------------
 * 反向入口：相关新闻的卡片上能点进病害百科，这里也让"先查病害"的用户
 * 看到与该病害相关的行业动态。用后端列表接口的 `pest=<id>` 过滤（第 401 批新增），
 * 只取 3 条；接口未上线 / 请求失败都按"没有相关动态"处理，整块不渲染、不弹错误。
 */
const relatedNews = ref([]);
const loadRelatedNews = async () => {
  const id = pest.value?.id;
  if (!id) {
    relatedNews.value = [];
    return;
  }
  try {
    const data = await fetchNewsList({ pest: id, page_size: 3, ordering: 'recent' });
    const results = Array.isArray(data?.results) ? data.results : [];
    relatedNews.value = results.slice(0, 3);
  } catch (error) {
    console.warn('获取相关行业动态失败（不渲染该区块）:', error);
    relatedNews.value = [];
  }
};

/** 分类角标文案（与新闻列表共用同一份分类表，英文界面不露中文） */
const getCategoryLabel = (value) => getNewsCategoryLabel(value, t);

/** 摘要截断：去掉富文本标签后取前 80 字（社区卡片的高度才稳定） */
const relatedSummary = (item) => {
  const text = stripHtmlText(localizedField(item, 'summary') || localizedField(item, 'content'));
  return text.length > 80 ? `${text.slice(0, 80)}...` : text;
};

const formatDate = (value) => {
  if (!value) return '';
  try {
    return new Date(value).toLocaleDateString(locale.value === 'en' ? 'en-US' : 'zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  } catch {
    return '';
  }
};

const goToNews = (id) => {
  if (!id) return;
  router.push({ name: 'news-detail', params: { id } });
};

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
    // 使用正确的API路径 /pests/{identifier}/
    // 注意：api 实例已经包含了 /api 前缀，所以这里不需要再加 /api
    const response = await api.get(`pests/${identifier}/`);
    pest.value = response.data;
    // 第 401 批：病害加载成功后按它的 id 拉相关行业动态（内部静默兜底）
    loadRelatedNews();
    // 第 402 批：核对当前病害的订阅状态（未登录/接口未上线时静默降级）
    refreshPestSubscription();
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

// 第 402 批：登录态变化时刷新「订阅该病害动态」按钮（与列表页分类订阅同一口径）
watch(() => Boolean(authStore.user), () => {
  refreshPestSubscription();
});

/** 编辑保存后：直接使用接口返回的最新数据，若英文标识符变更则同步地址栏 */
const handleSaved = (updated) => {
  if (!updated || typeof updated !== 'object') {
    loadPest();
    return;
  }

  pest.value = updated;
  // 第 401 批：词条被编辑后作物/名称可能变了，相关动态按当前 id 再拉一次
  loadRelatedNews();
  // 第 402 批：病害 id 若变化，订阅状态跟着重查
  refreshPestSubscription();

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

/* 第 402 批：订阅该病害动态（描边胶囊；已订阅转实心品牌色） */
.btn-subscribe {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 9px 20px;
  border: 1px solid var(--brand-400);
  border-radius: var(--radius-pill);
  background: var(--surface);
  color: var(--brand-700);
  font-family: inherit;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--dur) var(--ease);
}

.btn-subscribe i {
  font-size: 12px;
}

.btn-subscribe:hover {
  border-color: var(--brand-600);
  background: var(--brand-50);
}

.btn-subscribe.is-subscribed {
  border-color: var(--brand-600);
  background: var(--brand-600);
  color: #fff;
}

.btn-subscribe.is-subscribed:hover {
  border-color: var(--brand-700);
  background: var(--brand-700);
}

.btn-subscribe:disabled {
  opacity: 0.65;
  cursor: wait;
  transform: none;
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

/* ================= 第 401 批：相关行业动态 ================= */
.related-news-section {
  margin-top: 26px;
  padding: 24px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.related-news-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.related-news-head h2 {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-size: 19px;
  font-weight: 800;
  color: var(--ink-900);
}

.related-news-head h2 i {
  color: var(--brand-500);
}

.related-news-more {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--brand-700);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  transition: gap var(--dur) var(--ease), color var(--dur) var(--ease);
}

.related-news-more:hover {
  gap: 10px;
  color: var(--brand-500);
}

.related-news-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.related-news-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-muted);
  cursor: pointer;
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease),
    border-color var(--dur) var(--ease);
}

.related-news-card:hover {
  transform: translateY(-3px);
  border-color: var(--brand-200);
  background: var(--surface);
  box-shadow: var(--shadow-md);
}

.related-news-cat {
  align-self: flex-start;
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  background: var(--brand-50);
  color: var(--brand-700);
  font-size: 11.5px;
  font-weight: 600;
}

.related-news-title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin: 0;
  font-size: 14.5px;
  font-weight: 700;
  line-height: 1.5;
  color: var(--ink-800);
}

.related-news-summary {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin: 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-500);
}

.related-news-date {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: auto;
  font-size: 12px;
  color: var(--ink-400);
}

@media (max-width: 992px) {
  .related-news-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .related-news-section {
    padding: 18px;
  }

  .related-news-grid {
    grid-template-columns: 1fr;
  }
}
</style>

