<template>
  <div class="page result-page">

    <div v-if="loading" class="loading-box">
      <van-loading color="#2e7d32" vertical>{{ t('common.loading') }}</van-loading>
    </div>

    <div v-else-if="!result" class="loading-box">
      <p class="muted">{{ t('common.empty') }}</p>
      <van-button size="small" round color="#2e7d32" @click="router.replace('/detect')">
        {{ t('detect.title') }}
      </van-button>
    </div>

    <div v-else class="page-pad">
      <!-- 结果图：标注图优先（能看到模型框出的病斑），点开可放大 -->
      <div class="card image-card">
        <img
          v-if="displayImage"
          :src="displayImage"
          class="result-img"
          :alt="t('result.annotated')"
          @click="previewImage"
        />
        <p v-if="isHealthy" class="healthy-badge">🌿 {{ t('result.healthy') }}</p>
      </div>

      <div class="card">
        <p class="card-title">{{ isHealthy ? t('result.healthy') : t('result.detected') }}</p>
        <h2 class="disease-name">{{ displayName }}</h2>
        <p v-if="isHealthy" class="muted">{{ t('result.healthyDesc') }}</p>

        <div class="confidence-row">
          <span class="confidence-label">{{ t('result.confidence') }}</span>
          <span class="confidence-value">{{ confidencePercent }}%</span>
          <van-tag :type="confidenceTagType" size="medium">{{ confidenceText }}</van-tag>
        </div>
        <van-progress
          :percentage="confidencePercent"
          :color="confidenceColor"
          :show-pivot="false"
          track-color="#e6ece6"
        />

        <p v-if="result.historyId" class="muted saved-tip">✓ {{ t('result.saved') }}</p>
      </div>

      <div class="card">
        <p class="card-title">{{ t('result.symptoms') }}</p>
        <p class="pre-wrap">{{ symptoms || t('result.noSymptoms') }}</p>
      </div>

      <div class="card">
        <p class="card-title">{{ t('result.prevention') }}</p>
        <p class="pre-wrap">{{ prevention || t('result.noPrevention') }}</p>
      </div>

      <!-- 纠错反馈：一条识别结果只提交一次 -->
      <div class="card">
        <p class="card-title">{{ t('result.feedbackAsk') }}</p>
        <div class="feedback-row">
          <van-button
            size="small"
            round
            :type="feedback === true ? 'primary' : 'default'"
            :color="feedback === true ? '#2e7d32' : undefined"
            :loading="feedbackLoading"
            @click="sendFeedback(true)"
          >
            {{ t('result.feedbackAccurate') }}
          </van-button>
          <van-button
            size="small"
            round
            :type="feedback === false ? 'danger' : 'default'"
            :loading="feedbackLoading"
            @click="onInaccurate"
          >
            {{ t('result.feedbackInaccurate') }}
          </van-button>
        </div>
        <!-- 第 91 批：选了正确病害 → 这条纠错才进得了训练样本池 -->
        <p v-if="feedback === false" class="muted correct-hint">
          {{ correctedName
            ? `${t('result.correctedTo')}：${correctedName}`
            : t('result.feedbackCorrectHint') }}
        </p>
      </div>

      <!--
        第 91 批：纠错时选"正确是哪一种"
        ⚠️ 用**组件**而不是函数式调用：Vant 4 的 action-sheet 没有 `showActionSheet()`
        （只有 dialog / toast / notify / image-preview 有函数式版本），
        写函数调用会在构建期直接报 "showActionSheet is not exported"。
      -->
      <van-action-sheet
        v-model:show="pickerVisible"
        :title="t('result.feedbackCorrectLabel')"
        :actions="pickerActions"
        :cancel-text="t('common.cancel')"
        close-on-click-action
        @select="onPickCorrect"
      />

      <p class="disclaimer muted">{{ t('result.disclaimer') }}</p>

      <div class="result-actions">
        <van-button block round color="#2e7d32" size="large" @click="router.replace('/detect')">
          {{ t('result.retry') }}
        </van-button>
        <van-button block round plain size="large" @click="router.push('/history')">
          {{ t('result.goHistory') }}
        </van-button>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 结果页（移动端）
 * ----------------------------------------------------------------------------
 * 两种进入方式共用同一页面：
 *   · 刚识别完 → 结果在 detect store 里（刷新也能恢复，见 stores/detect.js）
 *   · 从识别记录点进来 → /result/:id，走接口取详情
 * 两条路的数据都被 utils/detectionResult.js 整形过，所以模板只认一种结构。
 */
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { showFailToast, showImagePreview, showSuccessToast } from 'vant';
import { fetchHistoryDetail } from '@/api/history';
import { submitRecognitionFeedback } from '@/api/detection';
import { fetchPestOptions } from '@/api/content';  // 第 91 批：纠错时选"正确病害"
import { formatApiError } from '@/api/http';
import { useDetectStore } from '@/stores/detect';
import { useI18n } from '@/i18n';

const route = useRoute();
const router = useRouter();
const detectStore = useDetectStore();
const { t, locale } = useI18n();

const isDetail = computed(() => Boolean(route.params.id));
const loading = ref(false);
const result = ref(detectStore.result);
const feedback = ref(null);
const feedbackLoading = ref(false);
// 第 91 批：纠错要能选"正确是哪一种"（选了才进训练样本池）
const pestOptions = ref([]);
const correctedName = ref('');
const pickerVisible = ref(false);
const pickerActions = ref([]);

const disease = computed(() => result.value?.disease || {});
const isHealthy = computed(() => Boolean(result.value?.healthy));

/* 内容数据（病害名/症状/防治）由后端提供，中英各一套；英文缺失回落中文 */
const pick = (zh, en) => (locale.value === 'en' ? en || zh : zh);

const displayName = computed(() =>
  pick(disease.value.name || t('result.detected'), disease.value.nameEn),
);
const symptoms = computed(() => pick(disease.value.symptoms, disease.value.symptomsEn));
const prevention = computed(() => pick(disease.value.prevention, disease.value.preventionEn));

const displayImage = computed(() => result.value?.annotatedImage || result.value?.originalImage || '');

const confidencePercent = computed(() => {
  const value = disease.value.confidence || 0;
  const percent = value <= 1 ? value * 100 : value;
  return Math.max(0, Math.min(100, Math.round(percent)));
});

const confidenceText = computed(() => {
  if (confidencePercent.value >= 70) return t('result.high');
  if (confidencePercent.value >= 40) return t('result.medium');
  return t('result.low');
});

const confidenceTagType = computed(() => {
  if (confidencePercent.value >= 70) return 'success';
  if (confidencePercent.value >= 40) return 'warning';
  return 'danger';
});

const confidenceColor = computed(() => {
  if (confidencePercent.value >= 70) return '#2e7d32';
  if (confidencePercent.value >= 40) return '#f0a020';
  return '#d9534f';
});

const previewImage = () => {
  if (displayImage.value) showImagePreview([displayImage.value]);
};

const goBack = () => {
  if (window.history.length > 1) router.back();
  else router.replace('/detect');
};

const sendFeedback = async (isCorrect, correctedPestId = null) => {
  if (feedbackLoading.value) return;
  // 点"准确"时若已经提交过，不重复请求；点"不准确"时会先弹选择框，所以这里不做去重
  if (isCorrect && feedback.value === true) return;
  feedbackLoading.value = true;
  try {
    await submitRecognitionFeedback({
      diseaseName: disease.value.name,
      isCorrect,
      confidence: disease.value.confidence,
      historyId: result.value?.historyId,
      imageFile: detectStore.chosenFile || undefined,
      correctedPestId,
    });
    feedback.value = isCorrect;
    if (!isCorrect && correctedPestId) {
      correctedName.value = pestOptions.value.find((item) => item.id === correctedPestId)?.text || '';
    }
    showSuccessToast(t('result.feedbackThanks'));
  } catch (error) {
    showFailToast(formatApiError(error, t('result.feedbackFailed')));
  } finally {
    feedbackLoading.value = false;
  }
};

/**
 * 点「不准确」：第 91 批先问"正确是哪一种"，再提交。
 *
 * 为什么不直接提交"错了"就算了：只存"对/错"的负反馈**对模型没有增量信息**，
 * 只能计数；带上正确类别（`corrected_pest_id`）之后它就是一条可训练样本。
 * 手机上不适合作下拉，用 action sheet 让农户点一下就行；
 * 第一个选项是"不确定 / 跳过" —— 不强迫作答，避免为了省事乱选。
 */
const onInaccurate = async () => {
  if (feedbackLoading.value) return;

  if (!pestOptions.value.length) {
    try {
      pestOptions.value = await fetchPestOptions();
    } catch (error) {
      console.warn('[feedback] 病害列表加载失败，直接提交"不准确":', error);
    }
  }

  if (!pestOptions.value.length) {
    await sendFeedback(false);
    return;
  }

  pickerActions.value = [
    { name: t('result.feedbackCorrectSkip'), value: null },
    ...pestOptions.value.map((item) => ({ name: item.text, value: item.id })),
  ];
  pickerVisible.value = true;
};

/** action sheet 选中一项（`close-on-click-action` 会自动收起面板） */
const onPickCorrect = (action) => {
  sendFeedback(false, action?.value ?? null);
};

onMounted(async () => {
  if (!isDetail.value) return;
  // 详情模式：即使 store 里有"上一次的结果"也必须按 id 重新取，否则会张冠李戴
  loading.value = true;
  try {
    result.value = await fetchHistoryDetail(route.params.id);
  } catch (error) {
    showFailToast(formatApiError(error, t('common.requestFailed')));
    result.value = null;
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.result-page {
  min-height: 100vh;
  padding-bottom: calc(env(safe-area-inset-bottom, 0px) + 20px);
}

.loading-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 60px 20px;
}

.image-card {
  padding: 8px;
  position: relative;
}

.result-img {
  width: 100%;
  border-radius: 12px;
  display: block;
  background: #f1f4f1;
}

.healthy-badge {
  position: absolute;
  left: 18px;
  bottom: 18px;
  margin: 0;
  background: rgba(46, 125, 50, 0.92);
  color: #fff;
  font-size: 0.8rem;
  padding: 5px 10px;
  border-radius: 999px;
}

.disease-name {
  margin: 0 0 8px;
  font-size: 1.3rem;
  color: #1f2a1f;
}

.confidence-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0 10px;
}

.confidence-label {
  font-size: 0.85rem;
  color: #6f806f;
}

.confidence-value {
  font-size: 1.05rem;
  font-weight: 700;
  color: #2e7d32;
}

.saved-tip {
  margin: 10px 0 0;
  color: #2e7d32;
}

.feedback-row {
  display: flex;
  gap: 12px;
}

/* 第 91 批：纠错下方的提示（"已记为 XX" / "选对病害能帮我们…"） */
.correct-hint {
  margin: 10px 0 0;
  font-size: 0.78rem;
  line-height: 1.6;
}

.disclaimer {
  padding: 0 4px 12px;
  line-height: 1.7;
}

.result-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
