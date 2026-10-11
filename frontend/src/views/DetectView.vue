<template>
  <div class="detect-page">

    <!-- 1. 初始上传界面 -->
    <div v-if="!isDetecting && !detectionResult">
      <div class="upload-card">
        <header class="upload-head">
          <h2>{{ t('detect.uploadTitle') }}</h2>
          <p>{{ t('detect.uploadHint') }}</p>
        </header>

        <div
          class="drop-zone"
          :class="{ 'is-dragging': isDragging, 'has-preview': !!previewUrl }"
          @click="triggerFileInput"
          @dragover.prevent="onDragOver"
          @dragleave.prevent="onDragLeave"
          @drop.prevent="onDrop"
        >
          <template v-if="!previewUrl">
            <span class="drop-icon"><i class="bi bi-cloud-arrow-up-fill"></i></span>
            <p class="drop-title">{{ t('detect.dropTitle') }}</p>
            <p class="drop-hint">{{ t('detect.dropHint') }}</p>
          </template>
          <img v-else :src="previewUrl" class="drop-preview" :alt="t('detect.previewAlt')" />
        </div>

        <input
          type="file"
          ref="fileInput"
          @change="onFileSelected"
          class="d-none"
          accept="image/*"
        >
        <!-- 第 74 批：手机端"直接拍照"入口。
             capture="environment" 让手机浏览器直接调用后置摄像头，
             而不是先弹"文件浏览 → 再去相册找刚才拍的照片"。 -->
        <input
          type="file"
          ref="cameraInput"
          @change="onFileSelected"
          class="d-none"
          accept="image/*"
          capture="environment"
        >

        <!-- 拍摄 / 相册 双入口：保留原有拖拽框与按钮，只在其上方增加两个大按钮 -->
        <div class="upload-entries">
          <button type="button" class="entry-btn is-primary" @click="openCamera">
            <i class="bi bi-camera-fill"></i>
            <span>{{ t('detect.takePhoto') }}</span>
          </button>
          <button type="button" class="entry-btn" @click="openGallery">
            <i class="bi bi-images"></i>
            <span>{{ t('detect.fromGallery') }}</span>
          </button>
        </div>

        <!-- 第 75 批：页面内取景拍照（拍完直接进下面的预览与识别流程） -->
        <CameraCapture
          v-model:visible="cameraVisible"
          @captured="onCameraCaptured"
          @fallback="onCameraFallback"
        />

        <div class="upload-actions">
          <button
            class="btn btn-primary btn-lg"
            @click="detectDisease"
            :disabled="!selectedFile"
          >
            <i class="bi bi-search me-2"></i>{{ t('detect.start') }}
          </button>
          <button
            class="btn btn-outline-secondary btn-lg"
            @click="resetPreview"
            v-if="selectedFile"
          >
            <i class="bi bi-x-lg me-1"></i>{{ t('detect.clear') }}
          </button>
        </div>
      </div>

      <!-- 第 31 批：上传区下面是整屏空白，这里补一块真正有用的信息 -->
      <!-- 第 58 批：卡片内容改成脚本里的 computed（用 t() 生成），随语言切换 -->
      <PageExtras
        icon="fas fa-camera-retro"
        :title="t('detect.guideTitle')"
        :subtitle="t('detect.guideSubtitle')"
        :items="guideItems"
      />
    </div>

    <!-- 2. 正在识别 -->
    <div v-else-if="isDetecting" class="detecting">
      <div class="detect-progress">
        <div
          class="detect-progress-bar"
          role="progressbar"
          :style="{ width: progress + '%' }"
          :aria-valuenow="progress"
          aria-valuemin="0"
          aria-valuemax="100"
        >
          <span>{{ Math.min(progress, 99) }}%</span>
        </div>
      </div>

      <div class="detecting-status">
        <span class="detecting-spinner" role="status" aria-hidden="true"></span>
        <h4>{{ statusMessage }}</h4>
      </div>
      <p class="detecting-detail">{{ statusDetail }}</p>
    </div>

    <!-- 3. 结果展示 -->
    <div v-else-if="detectionResult && detectionResult.diseases" class="results-container">
      <div class="results-header">
        <h3>{{ t('detect.resultBadge') }}</h3>
        <div class="results-actions">
          <button @click="downloadReport" class="btn btn-success">
            <i class="bi bi-download me-1"></i>{{ t('detect.downloadReport') }}
          </button>
          <button @click="resetDetection" class="btn btn-primary">
            <i class="bi bi-arrow-repeat me-1"></i>{{ t('detect.retry') }}
          </button>
        </div>
      </div>

      <!-- #7 健康叶片：绿色提示条（此前会显示英文 "Healthy Plant"） -->
      <div v-if="detectionResult.healthy" class="healthy-banner">
        <span class="healthy-icon"><i class="bi bi-check-circle-fill"></i></span>
        <div>
          <strong>{{ t('detect.healthyTitle') }}</strong>
          <p>{{ t('detect.healthyDesc') }}</p>
        </div>
      </div>

      <!-- 上部分：图片对比 -->
      <div class="row g-4 mb-4">
        <!-- 左栏：原始图片 -->
        <div class="col-md-6">
          <div class="card h-100 result-media-card">
            <div class="card-header">
              <h5 class="mb-0"><i class="bi bi-image me-2"></i>{{ t('detect.originalImage') }}</h5>
            </div>
            <div class="card-body d-flex flex-column">
              <div v-if="!detectionResult.originalImage" class="alert alert-warning mb-0">
                {{ t('detect.imageLoading') }}
              </div>
              <div v-else class="text-center flex-grow-1 d-flex flex-column">
                <img
                  :src="detectionResult.originalImage"
                  class="img-fluid rounded mb-3 mx-auto"
                  style="max-height: 350px; width: 100%; object-fit: contain;"
                  :alt="t('detect.originalImage')"
                  @error="handleImageError"
                  @load="handleImageLoad"
                >
              </div>
            </div>
          </div>
        </div>

        <!-- 右栏：标注图片 -->
        <div class="col-md-6">
          <div class="card h-100 result-media-card">
            <div class="card-header">
              <h5 class="mb-0"><i class="bi bi-bounding-box me-2"></i>{{ t('detect.detectionResult') }}</h5>
            </div>
            <div class="card-body d-flex flex-column">
              <div v-if="!detectionResult.annotatedImage" class="alert alert-info mb-0">
                {{ t('common.generating', { target: t('detect.detectionResult') }) }}
              </div>
              <div v-else class="text-center flex-grow-1 d-flex flex-column">
                <img
                  :src="detectionResult.annotatedImage || detectionResult.originalImage"
                  class="img-fluid rounded mb-3 mx-auto"
                  style="max-height: 350px; width: 100%; object-fit: contain;"
                  :alt="t('detect.detectionResult')"
                  @error="handleImageError"
                >
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 下部分：病害信息 -->
      <div class="card mb-4 result-detail-card">
        <div class="card-header">
          <h5 class="mb-0"><i class="bi bi-info-circle me-2"></i>{{ t('detect.diseaseDetail') }}</h5>
        </div>
        <div class="card-body">
          <div v-for="disease in filteredDiseases" :key="disease.id">
            <div class="row">
              <div class="col-md-12">
                <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
                  <h4 class="mb-0 detect-disease-name">{{ localizedField(disease, 'name') }}</h4>
                  <!-- #8 置信度说人话：数字徽章之外给出可读判断，并说明仅供参考 -->
                  <span class="confidence-chip" :class="`is-${confidenceLevel(disease.confidence)}`">
                    <i class="bi" :class="confidenceIcon(disease.confidence)"></i>
                    {{ confidenceText(disease.confidence) }}
                    <em>{{ (disease.confidence * 100).toFixed(0) }}%</em>
                  </span>
                </div>

                <p class="confidence-note">
                  <i class="bi bi-info-circle"></i> {{ t('detect.confidenceHint') }}
                </p>

                <div class="mb-4">
                  <h5 class="border-bottom pb-2"><i class="bi bi-exclamation-triangle me-2"></i>{{ t('detect.symptoms') }}</h5>
                  <p class="ms-4">{{ localizedField(disease, 'symptoms') || t('detect.noSymptoms') }}</p>
                </div>

                <div class="mb-4">
                  <h5 class="border-bottom pb-2"><i class="bi bi-shield-check me-2"></i>{{ t('detect.prevention') }}</h5>
                  <div class="ms-4" v-html="formatPreventionText(localizedField(disease, 'prevention') || t('detect.noPrevention'))"></div>
                </div>

                <div class="mt-4 pt-3 border-top">
                  <h6 class="text-muted mb-3">{{ t('detect.feedbackAsk') }}</h6>
                  <div class="d-flex flex-column gap-2">
                    <div class="btn-group" role="group">
                      <button
                        @click="handleFeedback(disease, true)"
                        class="btn btn-outline-success"
                        :class="{ 
                          'active': disease.user_feedback === true,
                          'btn-success text-white': disease.user_feedback === true
                        }"
                        :disabled="disease.feedbackLoading"
                      >
                        <span v-if="disease.feedbackLoading && disease.user_feedback === true" class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                        <i v-else class="bi bi-check-lg me-1"></i>
                        <span>{{ t('detect.feedbackAccurate') }}</span>
                        <span v-if="disease.feedbackSent && disease.user_feedback === true" class="ms-2">
                          <i class="bi bi-check-circle"></i>
                        </span>
                      </button>
                      <button
                        @click="handleFeedback(disease, false)"
                        class="btn btn-outline-danger"
                        :class="{ 
                          'active': disease.user_feedback === false,
                          'btn-danger text-white': disease.user_feedback === false
                        }"
                        :disabled="disease.feedbackLoading"
                      >
                        <span v-if="disease.feedbackLoading && disease.user_feedback === false" class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                        <i v-else class="bi bi-x-lg me-1"></i>
                        <span>{{ t('detect.feedbackInaccurate') }}</span>
                        <span v-if="disease.feedbackSent && disease.user_feedback === false" class="ms-2">
                          <i class="bi bi-check-circle"></i>
                        </span>
                      </button>
                    </div>

                    <!-- 不{{ t('detect.feedbackAccurate') }}时的建议输入框 -->
                    <div v-if="disease.showSuggestionInput" class="mt-2 animate__animated animate__fadeIn">
                      <!-- 第 91 批：先问"正确的病害是哪一种"。
                           这是把纠错变成训练样本的关键一步 —— 只说"错了"而不说"对的是什么"，
                           对模型没有增量信息。可选（不选也能提交），但选了就进样本池。 -->
                      <div class="mb-2">
                        <label class="form-label small text-muted mb-1" :for="`correct-pest-${disease.id ?? ''}`">
                          {{ t('detect.feedbackCorrectLabel') }}
                        </label>
                        <select
                          :id="`correct-pest-${disease.id ?? ''}`"
                          v-model="disease.correctedPestId"
                          class="form-select form-select-sm"
                          :disabled="disease.feedbackLoading || pestOptionsLoading"
                        >
                          <option :value="null">{{ t('detect.feedbackCorrectUnknown') }}</option>
                          <option v-for="pest in pestOptions" :key="pest.id" :value="pest.id">
                            {{ pest.name }}
                          </option>
                        </select>
                        <div class="form-text">{{ t('detect.feedbackCorrectHint') }}</div>
                      </div>
                      <div class="form-floating">
                        <textarea
                          v-model="disease.suggestionText"
                          class="form-control"
                          :placeholder="t('detect.feedbackPlaceholder')"
                          style="height: 100px"
                          :disabled="disease.feedbackLoading"
                        ></textarea>
                        <label>{{ t('detect.feedbackPlaceholder') }}</label>
                      </div>
                      <div class="d-flex justify-content-end gap-2 mt-2">
                        <button
                          @click="disease.showSuggestionInput = false"
                          class="btn btn-sm btn-outline-secondary"
                          :disabled="disease.feedbackLoading"
                        >
                          {{ t('common.cancel') }}
                        </button>
                        <button
                          @click="submitFeedback(disease, false)"
                          class="btn btn-sm btn-primary"
                          :disabled="disease.feedbackLoading"
                        >
                          <span v-if="disease.feedbackLoading" class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>
                          <span>{{ t('detect.submitFeedback') }}</span>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useToast } from 'vue-toast-notification';
import axios from 'axios';
import api from '@/utils/axios';  // 使用自定义的 axios 实例
import 'vue-toast-notification/dist/theme-sugar.css';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
// 第 31 批：页面底部"识别流程与拍摄建议"补充信息区
import PageExtras from '@/components/PageExtras.vue';
// 第 50 批：离线识别（断网时图片入本地队列，联网后自动补传）
import { enqueueOfflineImage, isBrowserOnline } from '@/utils/offlineSync';
import { getOfflineQueue } from '@/utils/offlineStorage';
import { useI18n } from '@/i18n';  // 第 58 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 72 批：内容数据多语言（病害名/症状/防治）
import { downloadDetectionReportPdf } from '@/utils/pdfReport';  // 第 73 批：#13 报告统一为 PDF
// 第 75 批：应用内拍照（实时取景 + 快门 + 前后摄像头切换）
import CameraCapture from '@/components/CameraCapture.vue';
import { hasInAppCamera } from '@/utils/camera';
// 第 91 批：识别纠错要选"正确是哪一种"，否则反馈成不了训练样本
import { fetchPestOptions } from '@/api/content';

const { t } = useI18n();
const { localizedField } = useLocalized();

// 第 58 批：底部"识别流程与拍摄建议"卡片（原来写死在模板的内联数组里，无法随语言切换）
const guideItems = computed(() => [
  { icon: 'fas fa-camera', title: t('detect.guideStep1'), text: t('detect.guideStep1Desc') },
  { icon: 'fas fa-magnifying-glass-chart', title: t('detect.guideStep2'), text: t('detect.guideStep2Desc') },
  {
    icon: 'fas fa-shield-halved',
    title: t('detect.guideStep3'),
    text: t('detect.guideStep3Desc'),
    more: t('detect.guideStep3Link'),
    to: '/pests',
  },
  {
    icon: 'fas fa-clock-rotate-left',
    title: t('detect.guideStep4'),
    text: t('detect.guideStep4Desc'),
    more: t('detect.guideStep4Link'),
    to: '/history',
  },
]);

const $toast = useToast();
const router = useRouter();
const authStore = useAuthStore();
const fileInput = ref(null);
const cameraInput = ref(null);
const previewUrl = ref('');
const isDragging = ref(false);
const isDetecting = ref(false);
const detectionResult = ref(null);

const selectedFile = ref(null);
const progress = ref(0);
const statusMessage = ref('');
const statusDetail = ref('');

/* ----------------------------------------------------------------------------
 * 第 74 批：识别结果跨刷新保留
 * ----------------------------------------------------------------------------
 * 原实现把结果只放在内存 ref 里。农户的典型动作是：识别完 → 切到相册/微信
 * 对照 → 再切回来。手机浏览器在后台常会回收标签页，回来时页面重新加载、
 * 结果就没了，得重新拍一次。而重新拍的条件（光线、病叶）往往已经变了。
 *
 * 这里把结果存进 sessionStorage（关掉标签页即失效，不会长期占用空间），
 * 页面加载时恢复。图片用服务器返回的地址，不存 base64，避免把存储撑满。
 * -------------------------------------------------------------------------- */
const RESULT_STORAGE_KEY = 'detect_last_result';

const persistResult = (result) => {
  try {
    if (!result) {
      sessionStorage.removeItem(RESULT_STORAGE_KEY);
      return;
    }
    // 只挑必要字段：结果对象里带了 _rawData(含 base64 标注图)，不能整包存
    sessionStorage.setItem(
      RESULT_STORAGE_KEY,
      JSON.stringify({
        diseases: result.diseases,
        originalImage: result.originalImage,
        annotatedImage: result.annotatedImage,
        historyId: result.historyId,
        timestamp: result.timestamp,
        healthy: result.healthy,
        savedAt: Date.now(),
      }),
    );
  } catch (error) {
    // 存储不可用（隐私模式/超配额）不影响识别主流程
    console.warn('[detect] 结果持久化失败:', error?.message || error);
  }
};

const restoreResult = () => {
  try {
    const raw = sessionStorage.getItem(RESULT_STORAGE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    // 超过 2 小时的结果不再恢复：田间情况可能已变，避免用户误当成本次结果
    if (!saved?.diseases?.length || Date.now() - (saved.savedAt || 0) > 2 * 60 * 60 * 1000) {
      sessionStorage.removeItem(RESULT_STORAGE_KEY);
      return;
    }
    detectionResult.value = saved;
    $toast.info(t('detect.resultRestored'), { duration: 4000 });
  } catch (error) {
    console.warn('[detect] 结果恢复失败:', error?.message || error);
  }
};

// 触发文件选择
const triggerFileInput = () => {
  fileInput.value?.click();
};

// 第 74 批：手机端两个入口 —— 直接拍照 / 从相册选
// 第 75 批：「拍照」改为**页面内拍照**（getUserMedia 实时取景 + 快门），
// 只有当前环境拿不到摄像头时（局域网 http / 浏览器不支持 / 权限被拒）
// 才回退到 `<input capture>` 唤起系统相机 —— 回退路径保留，不是可选项：
// 农户用手机访问 http://192.168.x.x:5173 时浏览器根本不暴露 mediaDevices。
const cameraVisible = ref(false);

// ---------------------------------------------------------------------------
// 第 91 批：识别纠错要能选"正确病害"
// ---------------------------------------------------------------------------
// 为什么值得多一个下拉：反馈里只有"对/错"时，负反馈**只能计数**；
// 一旦带上"正确答案是番茄晚疫病"，这条反馈就成了一个可训练样本
// （后端 Feedback.corrected_pest + verify_status，导出见
//   manage.py export_feedback_dataset）。下拉不选也能提交，不阻塞用户。
const pestOptions = ref([]);
const pestOptionsLoading = ref(false);

const loadPestOptions = async () => {
  if (pestOptions.value.length || pestOptionsLoading.value) return;
  pestOptionsLoading.value = true;
  try {
    pestOptions.value = await fetchPestOptions();
  } catch (error) {
    // 拉不到就只是没有下拉可选项，不影响识别与反馈本身
    console.warn('加载病害列表失败（纠错下拉将不可用）:', error);
  } finally {
    pestOptionsLoading.value = false;
  }
};

const openCamera = () => {
  if (hasInAppCamera()) {
    cameraVisible.value = true;
    return;
  }
  $toast.info(t(window.isSecureContext ? 'camera.unsupported' : 'camera.insecure'), { duration: 4000 });
  cameraInput.value?.click();
};

const openGallery = () => fileInput.value?.click();

/** 页面内拍到的照片：复用原有压缩/校验/预览流程 */
const onCameraCaptured = (file) => {
  handleFile(file);
};

/** 组件内点「改用系统相机 / 相册」 */
const onCameraFallback = () => {
  cameraVisible.value = false;
  cameraInput.value?.click();
};

/* ----------------------------------------------------------------------------
 * 第 74 批：上传前压缩
 * ----------------------------------------------------------------------------
 * 农户在田里用手机拍照，一张 3~8MB。弱网下直传原图：上传慢、耗流量，
 * 还经常撞到 5MB 上限被拒（用户只看到"图片大小不能超过5MB"，不知道怎么办）。
 * 这里在本地把长边压到 1600px、JPEG 质量 0.85 再提交 ——
 * 对识别精度没有实际影响（模型输入远小于此），但体积通常降到 1/5 以下。
 * 压缩失败时回落到原文件，绝不让用户因为压缩问题而传不了。
 * -------------------------------------------------------------------------- */
const COMPRESS_MAX_EDGE = 1600;
const COMPRESS_QUALITY = 0.85;
const UPLOAD_LIMIT = 5 * 1024 * 1024;

const compressImage = async (file) => {
  // GIF（可能是动图）与体积本就很小的文件没必要处理
  if (!file.type.startsWith('image/') || file.type === 'image/gif' || file.size < 300 * 1024) {
    return file;
  }

  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, COMPRESS_MAX_EDGE / Math.max(bitmap.width, bitmap.height));
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, width, height);
    bitmap.close?.();

    const blob = await new Promise((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', COMPRESS_QUALITY),
    );

    // 压完反而更大（原图已是高度压缩的 JPEG）→ 用原图
    if (!blob || blob.size >= file.size) return file;

    const name = (file.name || 'photo').replace(/\.[^.]+$/, '') + '.jpg';
    return new File([blob], name, { type: 'image/jpeg', lastModified: Date.now() });
  } catch (error) {
    console.warn('[detect] 图片压缩失败，改用原图:', error?.message || error);
    return file;
  }
};

// 处理文件选择
const onFileSelected = (event) => {
  const file = event.target.files[0];
  if (file) {
    handleFile(file);
  }
};

// 处理拖放
const onDragOver = () => {
  isDragging.value = true;
};

const onDragLeave = () => {
  isDragging.value = false;
};

const onDrop = (event) => {
  isDragging.value = false;
  const file = event.dataTransfer.files[0];
  if (file) {
    handleFile(file);
  }
};

// 处理文件（第 74 批：先本地压缩再使用；提示语走 i18n）
const handleFile = async (file) => {
  if (!file) return;

  // 检查文件类型
  if (!file.type.match('image.*')) {
    $toast.error(t('msg.imageOnly'));
    return;
  }

  // 超大原图先压缩；压缩后仍超限才拒绝
  const compressed = await compressImage(file);
  if (compressed.size > UPLOAD_LIMIT) {
    $toast.error(t('msg.imageTooLarge5'));
    return;
  }

  selectedFile.value = compressed;

  // 创建预览
  const reader = new FileReader();
  reader.onload = (e) => {
    previewUrl.value = e.target.result;
  };
  reader.readAsDataURL(compressed);
};

// 重置预览
const resetPreview = () => {
  previewUrl.value = '';
  selectedFile.value = null;
  if (fileInput.value) {
    fileInput.value.value = '';
  }
  if (cameraInput.value) {
    cameraInput.value.value = '';
  }
};

// 图片加载处理
const handleImageError = (event) => {
  console.error('图片加载失败:', event);
  $toast.error(t('detect.imageLoadFailed'));
};

// 图片加载成功
const handleImageLoad = (event) => {
  console.log('图片加载成功:', event);
};

// 识别结果列表（第 73 批：删除了此前的"作物类型筛选"死代码 ——
// 它依赖一个界面上不存在的作物选择器，且后端结果里也没有作物字段，
// 所以原来的 filter 条件恒为 true，属于永不生效的逻辑）
const filteredDiseases = computed(() => detectionResult.value?.diseases || []);

/* ---- #8 置信度"说人话"：数字之外给出可读判断 ---- */
const CONFIDENCE_KEYS = {
  high: 'detect.confidenceHigh',
  medium: 'detect.confidenceMedium',
  low: 'detect.confidenceLow',
};

const CONFIDENCE_ICONS = {
  high: 'bi-check-circle-fill',
  medium: 'bi-question-circle-fill',
  low: 'bi-exclamation-triangle-fill',
};

const confidenceLevel = (value) => {
  const pct = (value || 0) * 100;
  if (pct >= 70) return 'high';
  if (pct >= 40) return 'medium';
  return 'low';
};

const confidenceText = (value) => t(CONFIDENCE_KEYS[confidenceLevel(value)]);
const confidenceIcon = (value) => CONFIDENCE_ICONS[confidenceLevel(value)];

// 更新进度和状态
const updateProgress = (value, message, detail = '') => {
  progress.value = value;
  statusMessage.value = message;
  if (detail) statusDetail.value = detail;
};

// 进度上限：上传阶段展示真实的已上传字节占比（映射到 0~90%），
// 上传完成后进入服务端识别阶段，用定时器平滑推进到 99%。
// 说明：原代码写的是 `const progressInterval = simulateProgress()`，
// 但 simulateProgress 只是自增一次并返回 undefined，既没有动画，
// clearInterval(undefined) 也清不掉任何东西，相关提示文案从未出现过。
const UPLOAD_PROGRESS_MAX = 90;
const ANALYSIS_PROGRESS_MAX = 99;

// 识别请求的超时（第 159 批）：
// 服务端要跑一次模型推理，CPU 上实测 9~45 秒 —— 旧实例默认 30 秒不够，
// 于是"服务端算完了、前端已经放弃"，用户还被告知是网络问题。
// 这里给到 3 分钟（真正断网时不会等这么久：浏览器会立刻报错）。
const DETECT_TIMEOUT_MS = 180000;
let progressTimer = null;

const stopProgressTimer = () => {
  if (progressTimer) {
    clearInterval(progressTimer);
    progressTimer = null;
  }
};

// 服务端识别阶段的进度动画（识别耗时无法预估，最多推进到 99%）
const startProgressTimer = () => {
  stopProgressTimer();

  progressTimer = setInterval(() => {
    if (progress.value >= ANALYSIS_PROGRESS_MAX) return;

    let increment;
    if (progress.value < 40) {
      increment = Math.random() * 6 + 3;
    } else if (progress.value < 80) {
      increment = Math.random() * 3 + 1.5;
    } else {
      increment = Math.random() * 1 + 0.5;
    }

    progress.value = Math.min(progress.value + increment, ANALYSIS_PROGRESS_MAX);

    if (progress.value < 50) {
      statusMessage.value = t('detect.matching');
      statusDetail.value = t('detect.matchingDetail');
    } else {
      statusMessage.value = t('detect.generating');
      statusDetail.value = t('detect.generatingDetail');
    }
  }, 350);
};

/**
 * 第 50 批：把当前选中的图片存入离线队列
 * 场景：断网、或联网时请求因网络原因失败（服务端 500 之类的业务错误不该进队列）。
 */
const queueForOffline = async () => {
  isDetecting.value = false;
  stopProgressTimer();
  try {
    const item = await enqueueOfflineImage(selectedFile.value);
    const counts = await getOfflineQueue().count();
    window.dispatchEvent(new Event('offline-queue-changed'));
    $toast.success(t('detect.queuedOffline', { count: counts.pending }));
    console.log('[offline] 已入队:', item.id);
  } catch (error) {
    console.error('[offline] 入队失败:', error);
    $toast.error(t('detect.offlineSaveFailed'));
  }
};

//病害识别
const detectDisease = async () => {
  if (!selectedFile.value) {
    $toast.error(t('detect.selectFirst'));
    return;
  }

  // 第 50 批：离线时不做无意义的请求，直接进本地队列
  if (!isBrowserOnline()) {
    await queueForOffline();
    return;
  }

  isDetecting.value = true;
  progress.value = 0;
  statusMessage.value = t('detect.uploading');
  statusDetail.value = t('detect.uploadingDetail');
  stopProgressTimer();

  const formData = new FormData();
  formData.append('image', selectedFile.value);

  try {
    // 检查是否已登录
    if (!authStore.isAuthenticated) {
      $toast.error(t('msg.loginRequired'));
      await router.push('/login');
      return;
    }

    // 发送识别请求
    //
    // ⚠️ 第 159 批：这里必须**单独放宽超时**。
    // `@/utils/axios`（本页仍在用的旧实例）默认 30 秒，而识别要在服务端跑模型：
    // 在 CPU 上实测 9~45 秒不等（取决于机器与那台服务器加载的权重）——
    // 一旦超过 30 秒，前端会先放弃，用户看到的是"网络错误/已存入离线队列"，
    // 而**服务端其实算完了**（白白浪费一次推理，用户还得再点一次）。
    const response = await api({
      method: 'post',
      url: '/detect/',
      data: formData,
      timeout: DETECT_TIMEOUT_MS,
      headers: {
        'Content-Type': 'multipart/form-data',
        'X-CSRFToken': getCookie('csrftoken')
      },
      withCredentials: true,
      onUploadProgress: (progressEvent) => {
        const total = progressEvent.total || 0;
        const percentCompleted = total ? Math.round((progressEvent.loaded * 100) / total) : 0;

        // 上传阶段占 0~90%，展示真实上传进度
        const scaled = Math.min(UPLOAD_PROGRESS_MAX, Math.round((percentCompleted / 100) * UPLOAD_PROGRESS_MAX));
        if (scaled > progress.value) {
          updateProgress(scaled, t('detect.uploadingPhoto'), t('detect.uploadingPhotoDesc'));
        }

        // 上传完成 → 进入服务端识别阶段
        if (percentCompleted >= 100) {
          updateProgress(UPLOAD_PROGRESS_MAX, t('detect.matching'), t('detect.matchingDetail'));
          startProgressTimer();
        }
      }
    });

    console.log('后端响应数据:', response.data);

    console.log('后端响应数据:', response.data);

    // 检查响应格式 - 现在支持两种格式：
    // 1. 直接返回检测数据: { detection: {...}, history_id: 123 }
    // 2. 包装在 status/data 中: { status: 'success', data: { detection: {...}, history_id: 123 } }

    let responseData = response.data;

    // 如果响应是包装格式，提取data
    if (responseData.status === 'success' && responseData.data) {
      responseData = responseData.data;
    }

    // 确保有检测数据
    if (!responseData.detection) {
      console.error('返回的数据中缺少检测结果:', responseData);
      throw new Error(t('msg.invalidResponse'));
    }

    const detectionData = responseData.detection;

    // 处理图片URL
    const getFullUrl = (url) => {
      if (!url) return '';
      if (url.startsWith('http')) return url;

      // 规范化路径分隔符，将反斜杠替换为正斜杠
      const normalizedUrl = url.replace(/\\/g, '/');

      // 添加基础URL
      const baseUrl = import.meta.env.VITE_API_BASE_URL || `${window.location.protocol}//${window.location.hostname}:8000`;

      // 确保URL格式正确
      const base = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
      const path = normalizedUrl.startsWith('/') ? normalizedUrl : `/${normalizedUrl}`;

      return `${base}${path}`;
    };

    // 构建结果对象（第 72 批：同时带上英文内容，英文界面下不再回落到中文）
    detectionResult.value = {
      diseases: [{
        name: detectionData.disease || t('detect.unknownDisease'),
        name_en: detectionData.disease_en || '',
        confidence: detectionData.confidence || 0,
        // 使用后端返回的症状和防治建议，如果没有则显示默认值
        symptoms: detectionData.symptoms || detectionData.description || '',
        symptoms_en: detectionData.symptoms_en || detectionData.description_en || '',
        prevention: detectionData.prevention || detectionData.suggestions || '',
        prevention_en: detectionData.prevention_en || '',
        // 保留原始数据，方便调试
        _rawData: detectionData
      }],
      originalImage: getFullUrl(detectionData.original_image || detectionData.image_url || ''),
      annotatedImage: getFullUrl(detectionData.annotated_image || detectionData.annotated_image_url || ''),
      historyId: responseData.history_id,
      // 报告里的"检测时间"要用识别发生的时刻，不能用导出时刻
      timestamp: detectionData.timestamp || responseData.timestamp || new Date().toISOString(),
      // #7 健康叶片：后端无检出时返回 identifier='healthy_plant'，
      // 此前会走到"查库失败"分支、界面显示英文 "Healthy Plant"。
      // 这里单独标记出来，由模板渲染绿色"叶片大概率健康"提示。
      healthy:
        detectionData.status === 'healthy' ||
        detectionData.identifier === 'healthy_plant' ||
        /healthy/i.test(detectionData.identifier || ''),
    };

    // 第 74 批：结果落库到 sessionStorage，刷新/后台回收后可恢复
    persistResult(detectionResult.value);

    // 调试信息
    console.log('原始检测数据:', detectionData);
    console.log('原始图片URL:', detectionData.original_image || detectionData.image_url);
    console.log('标注图片URL:', detectionData.annotated_image || detectionData.annotated_image_url);
    console.log('处理后的原始图片URL:', detectionResult.value.originalImage);
    console.log('处理后的标注图片URL:', detectionResult.value.annotatedImage);

    // 打印调试信息
    console.log('检测结果详情:', {
      disease: detectionData.disease,
      symptoms: detectionData.symptoms,
      prevention: detectionData.prevention,
      originalImage: detectionResult.value.originalImage,
      annotatedImage: detectionResult.value.annotatedImage
    });

    console.log('处理后的检测结果:', detectionResult.value);

    // 为每个病害添加反馈状态
    detectionResult.value.diseases = detectionResult.value.diseases.map(disease => ({
      ...disease,
      showSuggestionInput: false,
      feedbackSent: false,
      suggestion: '',
      // 第 91 批：识别不正确时，用户选择的"正确病害"（决定这条反馈能不能当训练样本）
      correctedPestId: null,
    }));

    $toast.success(t('detect.done'));

  } catch (error) {
    console.error('识别失败:', error);

    // 第 159 批：**超时**要单独拎出来。
    // axios 的超时（`ECONNABORTED`）没有 `response`，于是原来落进了下面的"网络类失败"分支 →
    // 图片被悄悄塞进离线队列，用户看到"已存到离线队列，联网后自动识别"——
    // 可他明明连着网，只是服务端还在跑模型。这里改成明确提示，并且**不入队**。
    if (error?.code === 'ECONNABORTED') {
      console.warn('[detect] 识别请求超时（服务端仍在计算，结果不会返回给本次请求）');
      $toast.error(t('detect.timeout'));
      return;
    }

    // 第 50 批：网络类失败（拿不到 response，或明确是断网）→ 进离线队列，
    // 而不是让用户"白拍一张"。业务错误（400/413/500 等有 response 的）仍按普通错误提示。
    const isNetworkError = !error?.response || error?.code === 'ERR_NETWORK' || !isBrowserOnline();
    if (isNetworkError && selectedFile.value) {
      await queueForOffline();
      return;
    }

    // #11 错误提示人话化：后端 4xx 的 detail 是面向用户的短句（如"未检测到图片文件"），
    // 直接展示；503 用本地化文案（"识别服务暂时不可用"）；
    // 其余 5xx / 无响应属于服务端故障，技术细节留在控制台，
    // 界面只给农户能行动的那句话（重拍一张），不要把 Python 异常抛给用户。
    const status = error?.response?.status;
    const serverDetail = error?.response?.data?.detail || error?.response?.data?.error;
    const isUserFacing = status && status >= 400 && status < 500 && serverDetail;

    if (!isUserFacing) {
      console.error('[detect] 识别失败（已对用户隐藏技术细节）:', {
        status,
        detail: serverDetail,
        message: error?.message,
      });
    }

    if (status === 503) {
      $toast.error(t('detect.serviceUnavailable'));
    } else {
      $toast.error(isUserFacing ? serverDetail : t('detect.detectFailed'));
    }

    // 如果未授权，跳转到登录页
    if (error.response?.status === 401) {
      await router.push('/login');
    }
  } finally {
    isDetecting.value = false;
    stopProgressTimer();
    progress.value = 0;
  }
};

// 处理用户反馈点击
const handleFeedback = (disease, isCorrect) => {
  // 如果正在加载中，不处理点击
  if (disease.feedbackLoading) return;
  
  // 如果点击的是当前已选中的按钮，不处理
  if (disease.user_feedback === isCorrect) return;
  
  // 更新反馈状态
  disease.user_feedback = isCorrect;
  disease.feedbackSent = false;
  
  // 如果选择"准确"，直接提交反馈
  if (isCorrect) {
    submitFeedback(disease, isCorrect);
  } else {
    // 如果选择"不准确"，显示建议输入框
    disease.showSuggestionInput = true;
    // 初始化建议文本
    if (disease.suggestionText === undefined) {
      disease.suggestionText = '';
    }
  }
};

// 提交反馈到后端
const submitFeedback = async (disease, isCorrect = false) => {
  if (!detectionResult.value) {
    $toast.error(t('detect.nothingToSubmit'));
    return;
  }

  // 设置加载状态
  disease.feedbackLoading = true;
  disease.showSuggestionInput = false;

  try {
    // 获取CSRF token
    const csrftoken = getCookie('csrftoken');
    if (!csrftoken) {
      console.warn('未找到CSRF token，请求可能被拒绝');
    }

    // 创建FormData对象
    const formData = new FormData();

    // 获取病害名称
    // 第 79 批：这里的文案会作为**反馈数据**存进库（feedback.disease_name / suggestion），
    // 所以必须按当前界面语言写入，否则英文用户提交的反馈在后台仍是中文。
    const diseaseName =
      detectionResult.value.diseases?.[0]?.name
      || detectionResult.value.disease_name
      || t('detect.unknownDisease');

    // 添加表单字段
    // 第 26 批：标明这是"识别纠错"类反馈，避免在「意见反馈」页/后台里被当成功能建议
    formData.append('category', 'recognition');
    formData.append('disease_name', diseaseName);
    formData.append('is_correct', isCorrect);
    
    // 添加建议文本
    const suggestionText = isCorrect
      ? t('detect.feedbackCorrect')
      : (disease.suggestionText || t('detect.feedbackIncorrect'));
    formData.append('suggestion', suggestionText);

    // 添加检测记录ID
    if (detectionResult.value?.id) {
      formData.append('detection_id', detectionResult.value.id);
    }

    // 第 91 批：用户选了"正确病害"就带上 —— 后端据此把这条反馈标记成可训练样本
    // （Feedback.corrected_pest）。不选也不影响提交，只是进不了数据集。
    if (!isCorrect && disease.correctedPestId) {
      formData.append('corrected_pest_id', disease.correctedPestId);
    }

    // 添加图片文件（如果有）
    if (selectedFile.value) {
      formData.append('image', selectedFile.value);
    }

    console.log('提交反馈数据:', {
      disease_name: diseaseName,
      is_correct: isCorrect,
      suggestion: suggestionText,
      corrected_pest_id: disease.correctedPestId || null,
      has_image: !!selectedFile.value
    });

    // 发送multipart/form-data请求
    // 使用axios实例，确保已经配置了baseURL
    const response = await axios.post('/feedback/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
        'X-CSRFToken': csrftoken || ''
      },
      withCredentials: true
    });

    $toast.success(t('detect.feedbackThanks'));
    console.log('反馈提交成功:', response.data);

    // 更新UI状态
    disease.feedbackSent = true;
    disease.showSuggestionInput = false;
    
    // 更新disease对象的状态
    disease.user_feedback = isCorrect;
    if (!isCorrect) {
      disease.suggestionText = disease.suggestionText || t('detect.feedbackIncorrect');
    }

    // 更新detectionResult中的反馈状态
    if (detectionResult.value && detectionResult.value.diseases) {
      const updatedDiseases = detectionResult.value.diseases.map(d => {
        if (d.name === disease?.name) {
          return { ...d, feedbackSent: true, showSuggestionInput: false };
        }
        return d;
      });
      detectionResult.value = { ...detectionResult.value, diseases: updatedDiseases };
    }
    if (detectionResult.value) {
      detectionResult.value.hasFeedback = true;
    }

  } catch (error) {
    console.error('提交反馈失败:', error);
    
    // 恢复状态
    disease.feedbackSent = false;
    
    let errorMessage = t('msg.operationFailedRetry');
    
    if (error.response) {
      // 请求已发出，但服务器响应的状态码不在 2xx 范围内
      console.error('错误响应数据:', error.response.data);
      console.error('错误状态码:', error.response.status);
      console.error('错误头部:', error.response.headers);
      
      errorMessage = error.response.data?.detail || error.response.statusText || errorMessage;
      
      // 如果是因为未授权，可能需要重新登录
      if (error.response.status === 401) {
        await router.push('/login');
      }
    } else if (error.request) {
      // 请求已发出但没有收到响应
      console.error('请求已发出但没有响应:', error.request);
      errorMessage = t('msg.cannotConnect');
    } else {
      // 其他错误
      console.error('请求配置错误:', error.message);
      errorMessage = error.message || errorMessage;
    }
    
    $toast.error(errorMessage);
    
    // 如果是"不准确"的反馈，重新显示输入框
    if (!isCorrect) {
      disease.showSuggestionInput = true;
    }
  }
};

// 辅助函数：获取CSRF token
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// 重置识别
const resetDetection = () => {
  detectionResult.value = null;
  isDetecting.value = false;
  progress.value = 0;
  statusMessage.value = t('detect.preparing');
  statusDetail.value = t('detect.initializing');
  persistResult(null);
  resetPreview();
};

// 下载报告
// #13 报告统一为 PDF：原来这里自己拼一段 HTML 再下载 .html 文件，
// 而历史记录页早已有 PDF 导出（utils/pdfReport.js），同一系统两种格式。
// 现在改为复用同一套 PDF 实现，并把防治方法转成结构化列表，
// 让 PDF 里按「农业防治 / 化学防治 / …」分类展示，而不是一坨文本。
const buildMethodsFromText = (text) => {  if (!text) return [];
  const CATEGORY_MATCHERS = [
    { re: /^(农业防治|栽培防治|Cultural[^\u4e00-\u9fff:：]*)/i, category: 'AGRICULTURAL' },
    { re: /^(化学防治|药剂防治|Chemical[^\u4e00-\u9fff:：]*)/i, category: 'CHEMICAL' },
    { re: /^(生态防治|Ecological[^\u4e00-\u9fff:：]*)/i, category: 'ECOLOGICAL' },
    { re: /^(物理防治|Physical[^\u4e00-\u9fff:：]*)/i, category: 'PHYSICAL' },
    { re: /^(监测预警|Monitoring[^\u4e00-\u9fff:：]*)/i, category: 'MONITORING' },
  ];

  return String(text)
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      for (const { re, category } of CATEGORY_MATCHERS) {
        if (re.test(line)) {
          const measure = line.replace(re, '').replace(/^[\s:：、.]+/, '').trim();
          return { category, measure: measure || line };
        }
      }
      return { category: 'AGRICULTURAL', measure: line };
    })
    .filter((m) => m.measure);
};

const downloadReport = async () => {
  if (!detectionResult.value) return;

  $toast.info(t('detect.downloading'));
  try {
    const disease = filteredDiseases.value[0] || {};

    // 组装成 pdfReport 认识的记录形状（与历史记录页同一套字段）
    const record = {
      id: detectionResult.value.historyId,
      confidence: disease.confidence,
      timestamp: detectionResult.value.timestamp,
      pest_info: {
        name: disease.name,
        name_en: disease.name_en,
        crop_type: disease.cropType || disease.crop_type,
        crop_type_en: disease.crop_type_en,
        english_identifier: disease.english_identifier || disease.identifier,
        symptoms: disease.symptoms,
        symptoms_en: disease.symptoms_en,
        prevention_methods: buildMethodsFromText(disease.prevention),
      },
      // PDF 在防治方法为空时回落到这段纯文本
      prevention: localizedField(disease, 'prevention'),
    };

    const fileName = await downloadDetectionReportPdf(record, {
      imageUrl: detectionResult.value.originalImage,
      annotatedImageUrl: detectionResult.value.annotatedImage,
    });

    $toast.success(t('detect.reportOk', { name: fileName }));
  } catch (error) {
    console.error('生成报告时出错:', error);
    $toast.error(t('detect.reportFailed'));
  }
};

// 格式化防治建议文本，处理换行符
const formatPreventionText = (text) => {
  if (!text) return t('detect.noPrevention');

  // 首先将文本按换行符分割成数组
  const lines = text.split('\n').filter(line => line.trim() !== '');

  // 如果只有一行，直接返回
  if (lines.length === 1) return text;

  // 多行文本，添加有序列表
  return lines.map((line, index) => {
    const trimmed = line.trim();
    // 如果行以数字加句点开头，保持原样
    if (/^\d+\./.test(trimmed)) {
      return trimmed;
    }
    // 否则添加项目符号
    return `• ${trimmed}`;
  }).join('<br>');
};

/* 第 74 批：进入页面时恢复上次的识别结果（刷新 / 后台标签被回收后的兜底）。
   注意组件被 <keep-alive include="DetectView"> 缓存，onMounted 只在首次挂载触发，
   因此这里不会在站内来回切换时重复弹提示。 */
onMounted(() => {
  restoreResult();
  // 第 91 批：纠错下拉的候选列表（只在需要时才用，提前拉好避免用户点开等）
  loadPestOptions();
});
</script>

<style scoped>
.disease-result {
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.section-title {
  color: #333;
  margin-bottom: 0.75rem;
  font-size: 1.1rem;
}

.symptoms-content, .solutions-content {
  background-color: #f8f9fa;
  border-left: 4px solid #0d6efd;
  padding: 1rem;
  margin-bottom: 1.5rem;
}

.solutions-content {
  border-left-color: #198754;
}

.card {
  box-shadow: 0 0.5rem 1rem rgba(0, 0, 0, 0.1);
  border: none;
  border-radius: 0.5rem;
}

.card-body {
  padding: 1.5rem;
}

.btn-outline-success, .btn-outline-danger {
  min-width: 80px;
}

.badge {
  font-weight: 500;
  padding: 0.5em 0.8em;
  border-radius: 0.5rem;
}

textarea.form-control {
  border-radius: 0.375rem;
  border: 1px solid #dee2e6;
  resize: vertical;
  min-height: 100px;
}

.img-fluid {
  max-width: 100%;
  height: auto;
  border-radius: 0.375rem;
}

.disease-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #eee;
}

.disease-name {
  color: #2c3e50;
  font-weight: 600;
  margin: 0;
}

.confidence-badge .badge {
  font-size: 0.85rem;
  font-weight: 500;
  padding: 0.35em 0.65em;
}

.section-title {
  color: #495057;
  font-weight: 600;
  margin-bottom: 0.75rem;
  display: flex;
  align-items: center;
}

.symptoms-content {
  background-color: #f8f9fa;
  border-left: 4px solid #ffc107;
  font-size: 0.95rem;
  line-height: 1.6;
}

.solutions-list {
  background-color: #f8f9fa;
  border-radius: 0.5rem;
  padding: 1rem;
}

.solution-item {
  padding: 0.5rem 0;
  display: flex;
  align-items: flex-start;
  border-bottom: 1px dashed #dee2e6;
}

.solution-item:last-child {
  border-bottom: none;
}

.solution-item i {
  margin-top: 0.2rem;
  flex-shrink: 0;
}

.solution-text {
  flex-grow: 1;
  line-height: 1.5;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .disease-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .confidence-badge {
    width: 100%;
  }
}

/* ================= 现代化覆写（设计变量见 assets/theme.css） ================= */
.detect-page {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px 48px;
  box-sizing: border-box;
}

/* ---------------- 上传卡片 ---------------- */
.upload-card {
  padding: 40px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background: var(--surface);
  box-shadow: var(--shadow-md);
}

.upload-head {
  margin-bottom: 26px;
  text-align: center;
}

.upload-head h2 {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 800;
  color: var(--ink-900);
}

.upload-head p {
  margin: 0;
  font-size: 13.5px;
  color: var(--ink-500);
}

.drop-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 260px;
  padding: 40px 24px;
  border: 2px dashed var(--border-strong);
  border-radius: var(--radius-lg);
  background: var(--surface-muted);
  cursor: pointer;
  transition: border-color var(--dur) var(--ease), background-color var(--dur) var(--ease),
    box-shadow var(--dur) var(--ease);
}

.drop-zone:hover {
  border-color: var(--brand-400);
  background: var(--brand-50);
}

.drop-zone.is-dragging {
  border-color: var(--brand-500);
  background: var(--brand-50);
  box-shadow: var(--shadow-focus);
}

.drop-zone.has-preview {
  padding: 12px;
  border-style: solid;
  background: var(--surface);
}

.drop-icon {
  margin-bottom: 16px;
  font-size: 54px;
  line-height: 1;
  color: var(--brand-400);
}

.drop-title {
  margin: 0 0 6px;
  font-size: 15.5px;
  font-weight: 600;
  color: var(--ink-700);
}

.drop-hint {
  margin: 0;
  font-size: 13px;
  color: var(--ink-400);
}

.drop-preview {
  display: block;
  max-width: 100%;
  max-height: 320px;
  border-radius: var(--radius);
}

.upload-actions {
  display: flex;
  justify-content: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 26px;
}

/* ---------------- 识别中 ---------------- */
.detecting {
  padding: 56px 32px;
  text-align: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.detect-progress {
  height: 12px;
  margin-bottom: 26px;
  border-radius: var(--radius-pill);
  background: var(--ink-100);
  overflow: hidden;
}

.detect-progress-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
  padding-right: 10px;
  border-radius: var(--radius-pill);
  background: var(--gradient-brand);
  color: #fff;
  font-size: 11.5px;
  font-weight: 700;
  transition: width 0.35s var(--ease);
}

.detecting-status {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.detecting-status h4 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--ink-800);
}

.detecting-spinner {
  width: 20px;
  height: 20px;
  border: 3px solid var(--brand-100);
  border-top-color: var(--brand-600);
  border-radius: 50%;
  animation: detect-spin 0.9s linear infinite;
}

@keyframes detect-spin {
  to {
    transform: rotate(360deg);
  }
}

.detecting-detail {
  margin: 0;
  font-size: 13.5px;
  color: var(--ink-500);
}

/* ---------------- 结果区 ---------------- */
.results-container {
  width: 100%;
}

.results-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 22px;
}

.results-header h3 {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  color: var(--ink-900);
}

.results-actions {
  display: flex;
  gap: 10px;
}

.result-media-card .card-header,
.result-detail-card .card-header {
  padding: 14px 20px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.result-media-card .card-header h5,
.result-detail-card .card-header h5 {
  font-size: 15px;
  font-weight: 700;
  color: var(--ink-800);
}

.result-media-card .card-body {
  padding: 18px;
}

.result-media-card img {
  max-height: 340px;
  object-fit: contain;
  border-radius: var(--radius);
}

/* 病害详情排版 */
.result-detail-card .card-body {
  padding: 26px 24px;
}

.result-detail-card h4 {
  font-size: 20px;
  font-weight: 800;
  color: var(--ink-900);
}

.result-detail-card h5 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
  font-size: 15.5px;
  font-weight: 700;
  color: var(--brand-700);
}

.result-detail-card h5 i {
  color: var(--brand-500);
}

.result-detail-card p {
  font-size: 14px;
  line-height: 1.9;
  color: var(--ink-700);
}

.result-detail-card .badge {
  padding: 8px 16px;
  border-radius: var(--radius-pill);
  background: var(--gradient-brand);
  font-size: 13px;
}

/* ---------------- 响应式 ---------------- */
@media (max-width: 768px) {
  .detect-page {
    padding: 0 16px 32px;
  }

  .upload-card {
    padding: 22px 18px;
  }

  .upload-head h2 {
    font-size: 19px;
  }

  .drop-zone {
    min-height: 200px;
    padding: 26px 16px;
  }

  .detecting {
    padding: 36px 20px;
  }
}

/* ============================================================================
 * 第 73 批新增：#7 健康叶片提示条 / #8 置信度可读化 / #23 字号与触控提档
 * ========================================================================== */

/* 健康叶片：绿色肯定式表达，而不是"没查到病害"的失败感 */
.healthy-banner {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 20px;
  padding: 16px 20px;
  border: 1px solid var(--brand-200, #bfe3cd);
  border-left: 5px solid var(--brand-500, #3d9a68);
  border-radius: var(--radius, 14px);
  background: linear-gradient(180deg, #e8f6ee, #fbfefc);
}

.healthy-banner .healthy-icon {
  flex: none;
  font-size: 26px;
  color: var(--brand-600, #2a7f53);
  line-height: 1.2;
}

.healthy-banner strong {
  display: block;
  font-size: var(--font-size-title-sm, 18px);
  color: var(--brand-800, #194f37);
}

.healthy-banner p {
  margin: 4px 0 0;
  font-size: var(--font-size-base, 16px);
  line-height: 1.7;
  color: var(--ink-600, #566b60);
}

/* 病名：田间一眼要看清（#23 关键信息 ≥22px） */
.detect-disease-name {
  font-size: var(--font-size-key, 24px);
  font-weight: 800;
  color: var(--ink-900, #14231c);
}

/* ----------------------------------------------------------------------------
 * 第 74 批：拍摄 / 相册 双入口
 * ----------------------------------------------------------------------------
 * 农户最自然的动作是举手机对着叶子拍。原来只有一个虚线拖拽框（点击后弹
 * "文件浏览"），手机端还得先拍照存相册再翻回来找。这里在不删原拖拽框的
 * 前提下，于其上方加两个大按钮：左"拍照"直接调后置摄像头，右"从相册选"。
 * 触控目标 ≥48px，田间单手可点。
 * -------------------------------------------------------------------------- */
.upload-entries {
  display: flex;
  gap: 12px;
  margin: 18px 0 4px;
}

.entry-btn {
  flex: 1 1 0;
  min-height: 48px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 16px;
  border: 1px solid var(--border-strong, #d3dfd8);
  border-radius: var(--radius-pill, 999px);
  background: var(--surface, #fff);
  color: var(--ink-700, #3a4d43);
  font-size: var(--font-size-base, 16px);
  font-weight: 700;
  cursor: pointer;
  transition: transform var(--dur, 0.24s) var(--ease, ease),
    box-shadow var(--dur, 0.24s) var(--ease, ease),
    border-color var(--dur, 0.24s) var(--ease, ease);
}

.entry-btn i {
  font-size: 19px;
}

.entry-btn:hover {
  transform: translateY(-1px);
  border-color: var(--brand-400, #5fb088);
  color: var(--brand-700, #1f6343);
  background: var(--brand-50, #f1f9f4);
  box-shadow: var(--shadow-sm, 0 2px 8px rgba(19, 58, 41, 0.06));
}

/* 「拍照」是主路径：绿色实底，视觉上引导农户先点这里 */
.entry-btn.is-primary {
  border-color: transparent;
  background: var(--gradient-brand, linear-gradient(135deg, #3d9a68, #1f6343));
  color: #fff;
  box-shadow: 0 6px 16px rgba(31, 99, 67, 0.22);
}

.entry-btn.is-primary:hover {
  color: #fff;
  background: var(--brand-700, #1f6343);
  box-shadow: 0 10px 22px rgba(31, 99, 67, 0.3);
}

/* 窄屏：两个按钮上下排列，各自占满整行，便于单手点 */
@media (max-width: 480px) {
  .upload-entries {
    flex-direction: column;
    gap: 10px;
  }

  .entry-btn {
    min-height: 52px;
    font-size: 17px;
  }
}

/* 置信度：彩色胶囊 + 可读判断 + 百分比 */
.confidence-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: var(--radius-pill, 999px);
  font-size: var(--font-size-sm, 14px);
  font-weight: 700;
  white-space: nowrap;
}

.confidence-chip em {
  font-style: normal;
  font-weight: 600;
  opacity: 0.75;
}

.confidence-chip.is-high {
  color: var(--brand-800, #194f37);
  background: var(--brand-100, #ddf0e5);
}

.confidence-chip.is-medium {
  color: #8a5a12;
  background: #fdf3e2;
}

.confidence-chip.is-low {
  color: #a33227;
  background: #fdecea;
}

.confidence-note {
  margin: -6px 0 16px;
  font-size: var(--font-size-xs, 13px);
  color: var(--ink-500, #78897f);
}

/* #23 触控与字号：田间强光下正文不小于 16px */
.result-detail-card .card-body p,
.result-detail-card .card-body li {
  font-size: var(--font-size-base, 16px);
  line-height: 1.85;
}
</style>


