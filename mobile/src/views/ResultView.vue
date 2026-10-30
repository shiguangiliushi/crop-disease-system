<template>
  <div class="page result-page">

    <div v-if="loading" class="loading-box">
      <van-loading color="var(--brand)" vertical>{{ t('common.loading') }}</van-loading>
    </div>

    <div v-else-if="!result" class="loading-box">
      <p class="muted">{{ t('common.empty') }}</p>
      <van-button size="small" round type="primary" @click="router.replace('/detect')">
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

      <!--
        第 176 批：一键求助
        ------------------------------------------------------------------
        农户识别出病害之后，最常见的下一步是**拿去问人**（微信群、农资店、农技员）。
        但"打开论坛写帖子"在手机上是件重活，而移动端本来就没有论坛
        （设计约定：论坛留给桌面端，见 router/index.js 的说明）。

        所以这里做的是**复制一段现成的求助文案**：病名、把握多大、主要症状、
        系统给的防治建议、识别图片的链接 —— 粘到微信群里就能问，
        对方看得懂，农户也不用打字。
      -->
      <div class="card">
        <p class="card-title">{{ t('askHelp.title') }}</p>
        <p class="muted ask-hint">{{ t('askHelp.hint') }}</p>
        <van-button
          block
          round
          type="primary"
          icon="records-o"
          :loading="askingHelp"
          @click="askForHelp"
        >
          {{ t('askHelp.copy') }}
        </van-button>
        <!--
          第 177 批：生成**图片卡片**。
          文字链接在群里经常没人点，而农户之间本来就是"发图说话"：
          照片 + 病名 + 处理办法一张图说完，农资店老板扫一眼就能答。
        -->
        <van-button
          block
          round
          plain
          type="primary"
          icon="photo-o"
          class="share-card-btn"
          :loading="sharingCard"
          @click="openShareCard"
        >
          {{ t('shareCard.make') }}
        </van-button>
      </div>

      <!-- 分享图预览：手机上保存图片靠"长按"，所以这里必须把图**显示出来** -->
      <van-dialog
        v-model:show="shareCardVisible"
        :title="t('shareCard.previewTitle')"
        :show-confirm-button="false"
        close-on-click-overlay
      >
        <div class="share-card-body">
          <img v-if="shareCardUrl" :src="shareCardUrl" class="share-card-img" :alt="t('shareCard.previewTitle')" />
          <p class="muted share-card-hint">{{ t('shareCard.hint') }}</p>
          <van-button
            v-if="canShareFiles"
            block
            round
            type="primary"
            class="share-card-action"
            @click="shareTheCard"
          >
            {{ t('shareCard.share') }}
          </van-button>
        </div>
      </van-dialog>

      <!-- 纠错反馈：一条识别结果只提交一次 -->
      <div class="card">
        <p class="card-title">{{ t('result.feedbackAsk') }}</p>
        <div class="feedback-row">
          <van-button
            size="small"
            round
            :type="feedback === true ? 'primary' : 'default'"
            :color="feedback === true ? 'var(--brand)' : undefined"
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

      <!-- 第 253 批：识别后追问助手（Vant 弹层，非流式） -->
      <div class="card ask-card">
        <p class="card-title">{{ t('assistantAsk.title') }}</p>
        <p class="muted ask-hint">{{ t('assistantAsk.hint') }}</p>
        <van-button block round type="primary" size="large" @click="openAsk">
          {{ t('assistantAsk.open') }}
        </van-button>
      </div>

      <van-popup
        v-model:show="askVisible"
        position="bottom"
        round
        :style="{ maxHeight: '80vh' }"
        teleport="body"
      >
        <div class="ask-sheet">
          <div class="ask-sheet-head">
            <span>{{ t('assistantAsk.sheetTitle') }}</span>
            <van-icon name="cross" @click="askVisible = false" />
          </div>

          <div class="ask-sheet-body">
            <div v-if="askedQuestion" class="ask-bubble ask-bubble--user">{{ askedQuestion }}</div>
            <div v-if="askLoading" class="ask-loading">
              <van-loading size="18" /> {{ t('assistantAsk.asking') }}
            </div>
            <div v-else-if="askAnswer" class="ask-bubble ask-bubble--bot">
              <p class="pre-wrap">{{ askAnswer }}</p>
              <p v-if="askCitations.length" class="ask-sources">
                {{ t('assistantAsk.sources') }}：{{ askCitations.map((c) => c.pest_name || c.name || '词条').join('、') }}
              </p>
            </div>
          </div>

          <div class="ask-sheet-input">
            <van-field
              v-model="askDraft"
              rows="1"
              autosize
              type="textarea"
              maxlength="200"
              show-word-limit
              :placeholder="t('assistantAsk.placeholder')"
              @keyup.enter.stop="submitAsk"
            />
            <van-button
              size="small"
              type="primary"
              round
              :loading="askLoading"
              :disabled="!askDraft.trim()"
              @click="submitAsk"
            >{{ t('assistantAsk.send') }}</van-button>
          </div>
        </div>
      </van-popup>

      <div class="result-actions">
        <van-button block round type="primary" size="large" @click="router.replace('/detect')">
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
import { askAssistant } from '@/api/assistant';  // 第 253 批：识别后追问
import { copyText } from '@/utils/clipboard';
import { dataUrlToFile, renderResultCard } from '@/utils/shareCard';  // 第 177 批：生成分享图  // 第 176 批：复制求助文案（含 HTTP 回退）
import { submitRecognitionFeedback } from '@/api/detection';
import { fetchPestOptions } from '@/api/content';
import { showDialog, showToast } from 'vant';  // 第 176 批：复制成功/失败提示  // 第 91 批：纠错时选"正确病害"
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

// 第 253 批：识别后追问（弹层）
const askVisible = ref(false);
const askDraft = ref('');
const askedQuestion = ref('');
const askAnswer = ref('');
const askCitations = ref([]);
const askLoading = ref(false);

function openAsk() {
  askVisible.value = true;
  if (!askedQuestion.value && result.value?.disease?.name) {
    // 首次打开用病害名做默认问题，减少"不知道问什么"的犹豫
    askDraft.value = `${result.value.disease.name}该用什么药？`;
  }
}

async function submitAsk() {
  const question = askDraft.value.trim();
  if (!question || askLoading.value) return;
  askedQuestion.value = question;
  askAnswer.value = '';
  askCitations.value = [];
  askLoading.value = true;
  try {
    const data = await askAssistant({
      question,
      pestIdentifier: result.value?.identifier || result.value?.pestIdentifier || '',
    });
    askAnswer.value = data.answer || t('assistantAsk.failed');
    askCitations.value = data.citations || [];
    if (data.degraded) {
      // 降级（如词条未收录）也会给出可读回答，这里只提示一下
      console.info('[assistant] degraded:', data.degradeReason);
    }
  } catch (error) {
    showFailToast(formatApiError(error, t('assistantAsk.failed')));
  } finally {
    askLoading.value = false;
  }
}
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

/**
 * 一键求助（第 176 批）
 * ------------------------------------------------------------------
 * 拼出一段**可以直接粘到微信群里**的文案，然后复制到剪贴板。
 * 文案里带：病名、把握多大、主要症状、系统给的防治建议、识别图片链接。
 *
 * 为什么是"复制"而不是"去论坛发帖"：移动端没有论坛（设计上留给桌面端），
 * 而农户真实的提问场景就是微信群 —— 复制一段现成的话，比让他打字现实得多。
 *
 * 复制失败时（HTTP 局域网下 Clipboard API 不可用、execCommand 也被拦）
 * **把文案显示出来**让用户长按复制 —— 宁可多一步，也不能"点了没反应"。
 */
const askingHelp = ref(false);

const buildHelpText = () => {
  const name = disease.value?.name || result.value?.disease_name || '';
  const percent = confidencePercent.value;
  const symptom = disease.value?.symptoms || result.value?.symptoms || '';
  const prevent = prevention.value || '';
  const rawImage = result.value?.annotatedImage || result.value?.originalImage || '';
  // ⚠️ 后端在 Windows 上给出的图片地址可能带反斜杠（编码后是 %5C），
  // 而且这里是**相对路径** —— 粘到微信里别人根本点不开。统一成绝对地址 + 正斜杠。
  const image = rawImage
    ? new URL(String(rawImage).replace(/\\/g, '/').replace('%5C', '/'), window.location.origin).href
    : '';

  const lines = [
    t('askHelp.heading', { disease: name }),
    t('askHelp.lineConfidence', { disease: name, percent }),
  ];
  if (symptom) lines.push(t('askHelp.lineSymptom', { symptom: String(symptom).slice(0, 200) }));
  if (prevent) lines.push(t('askHelp.linePrevention', { prevention: String(prevent).slice(0, 200) }));
  if (image) lines.push(t('askHelp.lineImage', { url: image }));
  lines.push(t('askHelp.lineQuestion'));
  return lines.join('\n');
};

/**
 * 生成"可分享的识别结果卡片"（第 177 批）
 * ------------------------------------------------------------------
 * 画一张 750×1000 的图（App 名 / 识别图 / 病名 / 置信度 / 处理办法摘要），
 * 然后**显示出来**让用户长按保存或转发 —— 手机浏览器（尤其微信内置）里
 * "下载图片"基本靠长按，给一个下载按钮反而没人会用。
 *
 * 支持 Web Share API Level 2 的机型（安卓 Chrome、iOS 16.4+ Safari）
 * 额外给一个"分享"按钮，直接调系统分享面板。
 */
const sharingCard = ref(false);
const shareCardVisible = ref(false);
const shareCardUrl = ref('');
const shareCardFile = ref(null);

/** 机型是否支持"分享文件"（不支持就只给长按提示） */
const canShareFiles = computed(() => {
  if (!shareCardFile.value || typeof navigator.canShare !== 'function') return false;
  try { return navigator.canShare({ files: [shareCardFile.value] }); } catch { return false; }
});

const openShareCard = async () => {
  sharingCard.value = true;
  try {
    const raw = result.value?.annotatedImage || result.value?.originalImage || '';
    // 与求助文案同一套处理：绝对地址 + 正斜杠（后端在 Windows 上给的是反斜杠路径）
    const imageUrl = raw
      ? new URL(String(raw).replace(/\\/g, '/').replace('%5C', '/'), window.location.origin).href
      : '';
    const advice = prevention.value || disease.value?.symptoms || '';
    shareCardUrl.value = await renderResultCard({
      imageUrl,
      diseaseName: disease.value?.name || result.value?.disease_name || '',
      confidenceText: t('shareCard.confidence', { percent: `${confidencePercent.value}%` }),
      advice: String(advice).slice(0, 220),
      appName: t('common.appName'),
      footer: t('shareCard.footer'),
    });
    shareCardFile.value = dataUrlToFile(shareCardUrl.value);
    shareCardVisible.value = true;
  } catch (error) {
    console.error('[shareCard] 生成失败:', error);
    showToast(t('shareCard.failed'));
  } finally {
    sharingCard.value = false;
  }
};

const shareTheCard = async () => {
  if (!shareCardFile.value) return;
  try {
    await navigator.share({
      files: [shareCardFile.value],
      title: t('shareCard.previewTitle'),
      text: disease.value?.name || '',
    });
  } catch (error) {
    // 用户取消分享不算错误，不打扰他
    if (error?.name !== 'AbortError') console.warn('[shareCard] 分享失败:', error?.message || error);
  }
};

const askForHelp = async () => {
  askingHelp.value = true;
  try {
    const text = buildHelpText();
    const ok = await copyText(text);
    if (ok) {
      showToast(t('askHelp.copied'));
      return;
    }
    // 兜底：把文案显示出来，让用户长按复制
    showDialog({
      title: t('askHelp.copyFailedTitle'),
      message: text,
      messageAlign: 'left',
      confirmButtonText: t('common.confirm'),
    });
  } finally {
    askingHelp.value = false;
  }
};

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
  if (confidencePercent.value >= 70) return 'var(--brand)';
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
/* 第 253 批：追问弹层 */
.ask-card .ask-hint {
  margin: 0 0 12px;
  font-size: 12.5px;
  line-height: 1.6;
}

.ask-sheet {
  padding: 14px 16px calc(18px + env(safe-area-inset-bottom, 0px));
}

.ask-sheet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 10px;
}

.ask-sheet-body {
  max-height: 42vh;
  overflow-y: auto;
  margin-bottom: 12px;
}

.ask-bubble {
  padding: 10px 12px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.7;
  margin-bottom: 10px;
}

.ask-bubble--user {
  background: #e8f5ee;
  color: #1f2d26;
}

.ask-bubble--bot {
  background: #f6f8f7;
  color: #24352c;
}

.ask-sources {
  margin: 8px 0 0;
  font-size: 12px;
  color: #8b9a91;
}

.ask-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #8b9a91;
  font-size: 13px;
  padding: 8px 0;
}

.ask-sheet-input {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

.ask-sheet-input :deep(.van-field) {
  flex: 1;
  background: #f6f8f7;
  border-radius: 10px;
}

/* 第 177 批：分享图按钮与预览 */
.share-card-btn {
  margin-top: 10px;
}

.share-card-body {
  padding: 4px 16px 16px;
  text-align: center;
}

.share-card-img {
  width: 100%;
  border-radius: 10px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.12);
}

.share-card-hint {
  margin: 12px 0 0;
  font-size: 0.8rem;
  line-height: 1.6;
}

.share-card-action {
  margin-top: 12px;
}

/* 第 176 批：求助卡片的说明小字 */
.ask-hint {
  margin: 0 0 10px;
  font-size: 0.8rem;
  line-height: 1.6;
}

.result-page {
  /* 第 241 批：结果页入场淡入（纯 CSS；降低动效偏好时关闭） */
  animation: result-fade-up 0.32s cubic-bezier(0.22, 0.8, 0.3, 1) both;
}

@keyframes result-fade-up {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (prefers-reduced-motion: reduce) {
  .result-page { animation: none !important; }
}

@media (prefers-reduced-motion: reduce) {
  .result-page { animation: none; }
}

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
  color: var(--brand);
}

.saved-tip {
  margin: 10px 0 0;
  color: var(--brand);
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
