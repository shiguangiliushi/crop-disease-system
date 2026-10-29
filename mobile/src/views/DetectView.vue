<template>
  <div class="page detect-page">
    <div class="brand-bar">
      <span class="brand-logo">叶</span>
      <!--
        第 173 批：这里原来有一个 `<h1>{{ t('detect.title') }}</h1>`。
        顶栏收进外壳后，页面标题由 App.vue 统一渲染 —— 留着就变成
        **同一屏里两个"病害识别"** ✗（把顶栏加出来之后一眼就看出来了），所以整块去掉。
        品牌标记（叶）与语言切换保留：前者是识别页的身份，后者是手机上切语言的入口。
      -->
      <button type="button" class="lang-switch" @click="toggleLocale">
        {{ locale === 'en' ? '中文' : 'EN' }}
      </button>
    </div>

    <div class="page-pad">
      <!-- 未选图：两个大入口（拍照是主路径，做成整块可点，田里戴手套也点得中） -->
      <div v-if="!previewUrl" class="card">
        <button type="button" class="entry entry--primary" @click="openCamera">
          <span class="entry-icon">📷</span>
          <span class="entry-text">
            <strong>{{ t('detect.takePhoto') }}</strong>
            <em>{{ t('detect.takePhotoHint') }}</em>
          </span>
          <span class="entry-arrow">›</span>
        </button>

        <button type="button" class="entry" @click="openGallery">
          <span class="entry-icon">🖼️</span>
          <span class="entry-text">
            <strong>{{ t('detect.fromGallery') }}</strong>
            <em>{{ t('detect.galleryHint') }}</em>
          </span>
          <span class="entry-arrow">›</span>
        </button>
      </div>

      <!-- 已选图：预览 + 开始识别 -->
      <div v-else class="card">
        <p class="card-title">{{ t('detect.preview') }}</p>
        <!-- 第 241 批：识别中扫描线（纯 CSS；只在 detecting 渲染，不改识别逻辑） -->
        <div class="scan-stage">
          <img :src="previewUrl" class="preview-img" :alt="t('detect.preview')" />
          <template v-if="detecting">
            <div class="scan-tint" aria-hidden="true"></div>
            <div class="scan-line" aria-hidden="true"></div>
            <div class="scan-caption">
              <span class="scan-dot" aria-hidden="true"></span>{{ progressText }}
            </div>
          </template>
        </div>

        <!-- 第 241 批：进度条放在照片下方，遮罩只负责挡误触 -->
        <div v-if="detecting" class="scan-progress">
          <van-progress :percentage="progress" color="var(--brand)" :show-pivot="false" />
          <p class="progress-detail">{{ progressDetail }}</p>
        </div>

        <div class="preview-actions">
          <van-button
            block
            round
            type="primary"
            size="large"
            :loading="detecting"
            :loading-text="t('detect.uploading')"
            @click="startDetect"
          >
            {{ t('detect.start') }}
          </van-button>
          <van-button block round plain size="large" @click="resetSelection">
            {{ t('detect.clear') }}
          </van-button>
        </div>
      </div>

      <div class="card">
        <p class="card-title">{{ t('detect.tipTitle') }}</p>
        <ul class="tips">
          <li v-for="tip in tips" :key="tip">{{ tip }}</li>
        </ul>
      </div>
    </div>

    <!-- 上传/识别进度：两段式（真实上传进度 → 服务端分析） -->
    <van-overlay :show="detecting" z-index="2500" :lock-scroll="true" class="detect-overlay" />

    <!-- 第 75 批：页面内拍照（不支持时自动退回系统相机，见 openCamera） -->
    <CameraCapture
      v-model:visible="cameraVisible"
      @captured="onCaptured"
      @fallback="onCameraFallback"
    />

    <!-- 两个隐藏输入：相册选择 + capture 降级（唤起系统相机） -->
    <input ref="galleryInput" type="file" accept="image/*" class="hidden-input" @change="onFileChange" />
    <input
      ref="cameraInput"
      type="file"
      accept="image/*"
      capture="environment"
      class="hidden-input"
      @change="onFileChange"
    />
  </div>
</template>

<script setup>
/**
 * 识别页（移动端）
 * ----------------------------------------------------------------------------
 * 这是农户每天真正会用的页面，所以：
 *   · 「拍照」优先用**页面内取景**（有取景框、有快门，拍完立刻看到预览）；
 *   · 拿不到摄像头（局域网 http / 权限被拒）时自动退回系统相机 —— 不能"点不动"；
 *   · 上传前本地压缩到 1600px，弱网下省流量、少撞 5MB 上限；
 *   · 识别完成后把结果交给 detect store 再跳结果页（见 stores/detect.js 的说明）。
 */
import { computed, onBeforeUnmount, ref } from 'vue';
import { useRouter } from 'vue-router';
import { showDialog, showFailToast, showToast } from 'vant';
import CameraCapture from '@/components/CameraCapture.vue';
import { detectDisease } from '@/api/detection';
import { formatApiError } from '@/api/http';
import { compressImage, fileToDataUrl, UPLOAD_LIMIT } from '@/utils/image';
import { hasInAppCamera } from '@/utils/camera';
// 第 91 批：断网时把照片存进本地队列，联网后自动补传识别（见 utils/offlineSync.js）
import { enqueueOfflineImage } from '@/utils/offlineSync';
import { useDetectStore } from '@/stores/detect';
import { useI18n } from '@/i18n';

const router = useRouter();
const detectStore = useDetectStore();
const { t, locale, setLocale } = useI18n();

const galleryInput = ref(null);
const cameraInput = ref(null);
const cameraVisible = ref(false);
const previewUrl = ref('');
const selectedFile = ref(null);
const detecting = ref(false);
const progress = ref(0);
// 第 241 批：让扫描线至少扫一遍（本地识别 0.3~0.8s，否则动效一闪而过）
let detectStartedAt = 0;
const MIN_SCAN_VISIBLE_MS = 1100;
const progressText = ref('');
const progressDetail = ref('');

let progressTimer = null;

const tips = computed(() => [t('detect.tip1'), t('detect.tip2'), t('detect.tip3')]);

const toggleLocale = () => setLocale(locale.value === 'en' ? 'zh-CN' : 'en');

/* ---------------------------------------------------------------------------
 * 第 75 批：拍照入口
 * 有摄像头 → 打开页面内取景；没有（http 局域网 / 老浏览器）→ 明确告知原因并
 * 唤起系统相机。**不要静默失败**：农户只会以为"按钮坏了"。
 * ------------------------------------------------------------------------- */
const openCamera = () => {
  if (hasInAppCamera()) {
    cameraVisible.value = true;
    return;
  }
  showToast({
    message: t(window.isSecureContext ? 'camera.unsupported' : 'camera.insecure'),
    duration: 3500,
  });
  cameraInput.value?.click();
};

const openGallery = () => galleryInput.value?.click();

const onCameraFallback = () => {
  cameraVisible.value = false;
  cameraInput.value?.click();
};

const onCaptured = (file) => {
  handleFile(file);
};

const onFileChange = (event) => {
  const file = event.target?.files?.[0];
  // 清空 input 的值：否则"拍同一张/选同一个文件"不会再触发 change
  event.target.value = '';
  if (file) handleFile(file);
};

const handleFile = async (file) => {
  if (!file) return;
  if (!file.type?.startsWith('image/')) {
    showFailToast(t('detect.imageOnly'));
    return;
  }

  const compressed = await compressImage(file);
  if (compressed.size > UPLOAD_LIMIT) {
    showFailToast(t('detect.imageTooLarge'));
    return;
  }

  selectedFile.value = compressed;
  previewUrl.value = await fileToDataUrl(compressed);
};

const resetSelection = () => {
  selectedFile.value = null;
  previewUrl.value = '';
  if (galleryInput.value) galleryInput.value.value = '';
  if (cameraInput.value) cameraInput.value.value = '';
};

const stopProgressTimer = () => {
  if (progressTimer) {
    clearInterval(progressTimer);
    progressTimer = null;
  }
};

/** 上传完成后进入"服务端分析"阶段：真实进度已到头，用缓动动画顶到 99% */
const startProgressTimer = () => {
  stopProgressTimer();
  progressTimer = setInterval(() => {
    if (progress.value >= 99) return;
    progress.value = Math.min(99, progress.value + (progress.value < 60 ? 3 : 1));
  }, 400);
};

const startDetect = async () => {
  if (!selectedFile.value) {
    showFailToast(t('detect.selectFirst'));
    return;
  }

  // 第 91 批：**断网不再让农户白拍一张**。
  // 改前这里只弹一句"当前处于离线状态，请联网后再识别"就把人打发了；
  // 现在把照片存进本地队列（IndexedDB），回到有信号的地方自动补传识别。
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    await queueForOffline();
    return;
  }

  detecting.value = true;
  detectStartedAt = Date.now();
  progress.value = 0;
  progressText.value = t('detect.uploading');
  progressDetail.value = '';

  try {
    const result = await detectDisease(selectedFile.value, (event) => {
      const total = event.total || 0;
      const percent = total ? Math.round((event.loaded * 100) / total) : 0;
      // 上传阶段映射到 0~90%，剩下的留给服务端识别
      progress.value = Math.min(90, Math.round((percent / 100) * 90));
      if (percent >= 100) {
        progressText.value = t('detect.analyzing');
        progressDetail.value = t('detect.analyzingDetail');
        startProgressTimer();
      }
    });

    stopProgressTimer();
    progress.value = 100;
    detectStore.setResult(result);
    detectStore.setChosenFile(selectedFile.value);
    // 第 241 批：扫描线至少可见 1.1 秒（只影响等待动效，不影响结果）
    const elapsed = Date.now() - detectStartedAt;
    if (elapsed < MIN_SCAN_VISIBLE_MS) {
      await new Promise((resolve) => setTimeout(resolve, MIN_SCAN_VISIBLE_MS - elapsed));
    }
    router.push('/result');
  } catch (error) {
    stopProgressTimer();

    // 第 91 批：**网络类失败也进离线队列**（而不是让用户看着"识别失败"重拍）。
    // 判据与桌面端一致：没有 response（压根没连上）或明确是 ERR_NETWORK
    // —— 业务错误（400/413/503 等有 response 的）仍按普通错误提示。
    const isNetworkError = !error?.response || error?.code === 'ERR_NETWORK';
    if (isNetworkError) {
      await queueForOffline();
      return;
    }

    const retryable = error?.response?.status === 503;
    showFailToast(
      retryable
        ? t('detect.serviceUnavailable')
        : formatApiError(error, t('detect.failed')),
    );
  } finally {
    detecting.value = false;
  }
};

/**
 * 把当前选中的照片存进离线队列（第 91 批）
 *
 * 存完把页面上的预览清掉并提示"已存到手机里" —— 否则用户会以为
 * "图片还在、再点一次识别就好了"，反复点同一次没网的操作。
 */
const queueForOffline = async () => {
  if (!selectedFile.value) return;
  try {
    await enqueueOfflineImage(selectedFile.value);
    resetSelection();
    showDialog({
      title: t('offline.queuedTitle'),
      message: t('offline.queued'),
      confirmButtonText: t('common.confirm'),
    });
  } catch (error) {
    console.error('[offline] 入队失败:', error);
    showFailToast(t('detect.offline'));
  }
};

onBeforeUnmount(stopProgressTimer);
</script>

<style scoped>
.detect-page {
  min-height: 100vh;
}

.entry {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 12px;
  border: 0;
  border-radius: 12px;
  background: #f7faf7;
  text-align: left;
  margin-bottom: 10px;
}

.entry:last-child {
  margin-bottom: 0;
}

.entry--primary {
  background: var(--brand-soft);
}

.entry-icon {
  font-size: 1.5rem;
  width: 34px;
  text-align: center;
}

.entry-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.entry-text strong {
  font-size: 1.02rem;
  color: #1f2a1f;
}

.entry-text em {
  font-style: normal;
  font-size: 0.8rem;
  color: #6f806f;
}

.entry-arrow {
  color: #9fb29f;
  font-size: 1.3rem;
}

.preview-img {
  width: 100%;
  border-radius: 12px;
  display: block;
  margin-bottom: 12px;
  max-height: 46vh;
  object-fit: contain;
  background: #f1f4f1;
}

.preview-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tips {
  margin: 0;
  padding-left: 18px;
  color: #4a5a4a;
  font-size: 0.87rem;
  line-height: 1.9;
}

/* ============================================================================
   第 241 批：识别中动效（纯 CSS，零功能改动）
   · 手机屏小：线 2px、1.8s；标题胶囊字号 12px；
   · 只动 transform/opacity；系统开了"减少动态效果"就全部关掉。
   ========================================================================== */
.scan-stage {
  position: relative;
  border-radius: 14px;
  overflow: hidden;
  background: #0f1f17;
}

.scan-tint {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(15, 31, 23, 0.32), rgba(15, 31, 23, 0.08));
  animation: scan-breathe 2.4s ease-in-out infinite;
  pointer-events: none;
}

.scan-line {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, #7ee2b8 20%, #b9f4d8 50%, #7ee2b8 80%, transparent);
  box-shadow: 0 0 12px rgba(126, 226, 184, 0.85);
  animation: scan-sweep 1.8s cubic-bezier(0.5, 0, 0.5, 1) infinite;
  pointer-events: none;
}

.scan-caption {
  position: absolute;
  left: 50%;
  bottom: 10px;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(15, 31, 23, 0.72);
  color: #e9f7ef;
  font-size: 12px;
  white-space: nowrap;
}

.scan-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #7ee2b8;
  animation: scan-pulse 1.2s ease-in-out infinite;
}

@keyframes scan-sweep {
  0% { top: 0; opacity: 0; }
  12% { opacity: 1; }
  88% { opacity: 1; }
  100% { top: 100%; opacity: 0; }
}

@keyframes scan-breathe {
  0%, 100% { opacity: 0.55; }
  50% { opacity: 0.25; }
}

@keyframes scan-pulse {
  0%, 100% { transform: scale(1); opacity: 0.7; }
  50% { transform: scale(1.5); opacity: 1; }
}

/* 整屏遮罩只做"挡住误触"：调成半透明，露出下面的照片和扫描线 */
.detect-overlay {
  background: rgba(15, 31, 23, 0.22) !important;
}

@media (prefers-reduced-motion: reduce) {
  .scan-tint,
  .scan-line,
  .scan-dot {
    animation: none !important;
  }
}

.scan-progress {
  padding: 14px 2px 0;
}

.progress-wrap {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: min(300px, 78vw);
  display: flex;
  flex-direction: column;
  gap: 14px;
  align-items: center;
}

.progress-detail {
  margin: 0;
  text-align: center;
  font-size: 0.82rem;
  color: rgba(255, 255, 255, 0.78);
}

.hidden-input {
  display: none;
}
</style>
