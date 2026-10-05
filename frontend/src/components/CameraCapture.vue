<template>
  <Teleport to="body">
    <div v-if="visible" class="camera-overlay" role="dialog" aria-modal="true" :aria-label="t('camera.title')">
      <div class="camera-card">
        <header class="camera-head">
          <h3 class="camera-title"><i class="bi bi-camera-fill"></i> {{ t('camera.title') }}</h3>
          <button type="button" class="camera-close" :aria-label="t('camera.cancel')" @click="close">
            <i class="bi bi-x-lg"></i>
          </button>
        </header>

        <!-- 取景框 -->
        <div class="camera-stage" :class="{ 'is-mirrored': mirrored }">
          <video
            ref="videoEl"
            class="camera-video"
            autoplay
            playsinline
            muted
          ></video>

          <!-- 三分线辅助构图 -->
          <div v-if="state === 'live'" class="camera-grid" aria-hidden="true">
            <span></span><span></span><span></span><span></span>
          </div>

          <div v-if="state !== 'live'" class="camera-mask">
            <span v-if="state === 'opening'" class="camera-spinner" aria-hidden="true"></span>
            <i v-else class="bi bi-exclamation-triangle-fill"></i>
            <p class="camera-mask-text">
              {{ state === 'opening' ? t('camera.opening') : errorText }}
            </p>
            <button
              v-if="state === 'error' && isSupported"
              type="button"
              class="camera-retry"
              @click="start"
            >
              <i class="bi bi-arrow-clockwise"></i> {{ t('camera.retry') }}
            </button>
          </div>
        </div>

        <p class="camera-hint">{{ t('camera.hint') }}</p>

        <footer class="camera-actions">
          <button type="button" class="camera-btn camera-btn--ghost" @click="close">
            {{ t('camera.cancel') }}
          </button>

          <button
            type="button"
            class="camera-shutter"
            :disabled="state !== 'live' || capturing"
            :aria-label="t('camera.shoot')"
            @click="shoot"
          >
            <span class="camera-shutter-ring"></span>
          </button>

          <div class="camera-side">
            <button
              v-if="canSwitch"
              type="button"
              class="camera-btn camera-btn--icon"
              :title="t('camera.switch')"
              :aria-label="t('camera.switch')"
              @click="switchCamera"
            >
              <i class="bi bi-arrow-repeat"></i>
            </button>
            <button
              v-if="torchSupported"
              type="button"
              class="camera-btn camera-btn--icon"
              :class="{ 'is-on': torchOn }"
              :title="torchOn ? t('camera.torchOff') : t('camera.torchOn')"
              :aria-label="torchOn ? t('camera.torchOff') : t('camera.torchOn')"
              @click="toggleTorch"
            >
              <i class="bi bi-lightning-charge-fill"></i>
            </button>
          </div>
        </footer>

        <!-- 拿不到摄像头时，保留一条"用系统相机/相册"的退路 -->
        <button v-if="state === 'error'" type="button" class="camera-fallback" @click="useSystemCamera">
          <i class="bi bi-images"></i> {{ t('camera.fallback') }}
        </button>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
/**
 * 应用内拍照组件（第 75 批）
 * ----------------------------------------------------------------------------
 * 用 getUserMedia 在页面里实时取景 + 快门拍照，拍完直接把 File 交给父组件，
 * 父组件当作"用户选好的图片"继续走原有上传/识别流程（无需改后端）。
 *
 * 设计要点：
 *   · 打开才申请权限、关闭一定释放：`stopStream()` 在 close / 关闭组件 / 切后台时
 *     都会 stop 所有 track —— 否则手机上摄像头指示灯会一直亮着（用户会以为被偷拍）。
 *   · **能力探测失败绝不硬撑**：不支持（http 局域网访问）或权限被拒时，
 *     通过 `unsupported` 事件让父组件回退到 `<input capture>` 的老方案，
 *     保证"拍不了照"至少还能"用系统相机拍"。
 *   · 预览镜像只影响显示（自拍时看着自然），**抓帧不镜像**，交给模型的仍是真实画面。
 */
import { computed, onBeforeUnmount, ref, watch, nextTick } from 'vue';
import { useI18n } from '@/i18n';
import { captureFrameFromVideo, describeCameraError, hasInAppCamera } from '@/utils/camera';

const props = defineProps({
  /** 是否显示（配合 v-model:visible 使用） */
  visible: { type: Boolean, default: false },
  /** 首选摄像头：environment=后置/主摄，user=前置 */
  facing: { type: String, default: 'environment' },
  /** 拍出来的图片长边上限 */
  maxEdge: { type: Number, default: 1600 },
  /** JPEG 质量 */
  quality: { type: Number, default: 0.92 },
});

const emit = defineEmits(['update:visible', 'captured', 'unsupported', 'fallback']);

const { t } = useI18n();

const videoEl = ref(null);
const facingMode = ref(props.facing);
const state = ref('idle'); // idle | opening | live | error
const errorKey = ref('');
const errorDetail = ref('');
const capturing = ref(false);
const canSwitch = ref(false);
const torchSupported = ref(false);
const torchOn = ref(false);

let stream = null;

const isSupported = computed(() => hasInAppCamera());
const mirrored = computed(() => facingMode.value === 'user');
const errorText = computed(() => {
  const text = t(errorKey.value || 'camera.failed');
  return errorDetail.value ? `${text}（${errorDetail.value}）` : text;
});

const stopStream = () => {
  if (stream) {
    stream.getTracks().forEach((track) => {
      try {
        track.stop();
      } catch {
        /* 已结束的 track 再 stop 会抛，忽略 */
      }
    });
    stream = null;
  }
  if (videoEl.value) {
    videoEl.value.srcObject = null;
  }
  torchSupported.value = false;
  torchOn.value = false;
};

/** 摄像头数量 > 1 时才显示"切换"按钮（单摄电脑上显示它只会让人误点） */
const refreshDeviceInfo = async () => {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cams = devices.filter((d) => d.kind === 'videoinput');
    canSwitch.value = cams.length > 1;
  } catch {
    canSwitch.value = false;
  }
};

const start = async () => {
  if (!isSupported.value) {
    state.value = 'error';
    errorKey.value = window.isSecureContext ? 'camera.unsupported' : 'camera.insecure';
    emit('unsupported', errorKey.value);
    return;
  }

  stopStream();
  state.value = 'opening';
  errorKey.value = '';
  errorDetail.value = '';

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: { ideal: facingMode.value },
        width: { ideal: 1920 },
        height: { ideal: 1080 },
      },
    });

    await nextTick();
    if (!videoEl.value) throw new Error('video_element_missing');
    videoEl.value.srcObject = stream;
    // iOS Safari 需要显式 play()，否则画面停在第一帧
    await videoEl.value.play().catch(() => {});

    state.value = 'live';
    await refreshDeviceInfo();

    const track = stream.getVideoTracks()[0];
    torchSupported.value = Boolean(track?.getCapabilities?.().torch);
  } catch (error) {
    stopStream();
    state.value = 'error';
    errorKey.value = describeCameraError(error);
    errorDetail.value = error?.message || '';
    // 打开就失败（权限被拒 / 没有设备）→ 让父组件知道可以走系统相机
    //
    // ⚠️ 第 107 批注：**这里只对三种失败升级，是有意的**。
    //    其余失败（`camera.busy` 设备被占用、`camera.overconstrained` 分辨率不支持、
    //    `camera.failed` 其它）留在应用内让用户重试 —— 这些多为**瞬时**问题，
    //    桌面端直接交还给"系统相机"反而更绕。
    //
    //    移动端同款组件（`mobile/src/components/CameraCapture.vue`）**对任何失败都升级**：
    //    手机上"应用内取景失败"的兜底体验（系统相机）比让农户对着错误提示重试更好，
    //    而田间弱网/低端机正是 busy 与 overconstrained 高发的环境。
    //    两边行为不同是刻意取舍 —— 想"统一"之前请先读那段说明。
    if (['camera.denied', 'camera.notFound', 'camera.insecure'].includes(errorKey.value)) {
      emit('unsupported', errorKey.value);
    }
  }
};

const shoot = async () => {
  if (state.value !== 'live' || capturing.value) return;
  capturing.value = true;
  try {
    const file = await captureFrameFromVideo(videoEl.value, {
      maxEdge: props.maxEdge,
      quality: props.quality,
    });
    emit('captured', file);
    close();
  } catch (error) {
    errorKey.value = 'camera.shootFailed';
    errorDetail.value = error?.message || '';
    state.value = 'error';
  } finally {
    capturing.value = false;
  }
};

const switchCamera = async () => {
  facingMode.value = facingMode.value === 'environment' ? 'user' : 'environment';
  await start();
};

const toggleTorch = async () => {
  const track = stream?.getVideoTracks?.()[0];
  if (!track) return;
  const next = !torchOn.value;
  try {
    await track.applyConstraints({ advanced: [{ torch: next }] });
    torchOn.value = next;
  } catch (error) {
    // 设备声称支持但实际拒绝：直接隐藏按钮，别让用户反复点
    torchSupported.value = false;
    console.warn('[camera] 补光灯切换失败:', error?.message || error);
  }
};

/** 回退：交给父组件用系统相机/相册（`<input capture>` 老路径） */
const useSystemCamera = () => {
  close();
  emit('fallback', errorKey.value || 'camera.unsupported');
};

const close = () => {
  stopStream();
  state.value = 'idle';
  emit('update:visible', false);
};

const onKeydown = (event) => {
  if (event.key === 'Escape') close();
};

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      facingMode.value = props.facing;
      document.addEventListener('keydown', onKeydown);
      document.body.style.overflow = 'hidden';
      start();
    } else {
      document.removeEventListener('keydown', onKeydown);
      document.body.style.overflow = '';
      stopStream();
    }
  },
);

// 切到后台（接电话、切 App）时先释放摄像头，回来再重启，避免"指示灯常亮"
const onVisibilityChange = () => {
  if (!props.visible) return;
  if (document.hidden) {
    stopStream();
    state.value = 'idle';
  } else if (state.value === 'idle') {
    start();
  }
};
document.addEventListener('visibilitychange', onVisibilityChange);

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown);
  document.removeEventListener('visibilitychange', onVisibilityChange);
  document.body.style.overflow = '';
  stopStream();
});
</script>

<style scoped>
.camera-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(12, 20, 12, 0.82);
  padding: 16px;
}

.camera-card {
  width: min(720px, 100%);
  max-height: 96vh;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #16211a;
  border-radius: 18px;
  padding: 14px 16px 16px;
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.45);
  color: #f2f6f2;
}

.camera-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.camera-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.camera-close {
  border: 0;
  background: transparent;
  color: inherit;
  font-size: 1.1rem;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 10px;
}

.camera-close:hover {
  background: rgba(255, 255, 255, 0.12);
}

.camera-stage {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  max-height: 64vh;
  background: #000;
  border-radius: 14px;
  overflow: hidden;
}

.camera-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.camera-stage.is-mirrored .camera-video {
  transform: scaleX(-1);
}

.camera-grid {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: repeat(3, 1fr);
  pointer-events: none;
}

.camera-grid span {
  border: 1px solid rgba(255, 255, 255, 0.18);
}

.camera-grid span:nth-child(4) {
  border: 0;
}

.camera-mask {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  text-align: center;
  background: rgba(8, 12, 8, 0.72);
  color: #eaf3ea;
  font-size: 0.95rem;
}

.camera-mask i {
  font-size: 2rem;
  color: #ffc857;
}

.camera-mask-text {
  margin: 0;
  line-height: 1.6;
}

.camera-spinner {
  width: 34px;
  height: 34px;
  border: 3px solid rgba(255, 255, 255, 0.25);
  border-top-color: #7ec87e;
  border-radius: 50%;
  animation: camera-spin 0.9s linear infinite;
}

@keyframes camera-spin {
  to {
    transform: rotate(360deg);
  }
}

.camera-retry {
  border: 1px solid rgba(255, 255, 255, 0.4);
  background: transparent;
  color: inherit;
  border-radius: 10px;
  padding: 8px 14px;
  cursor: pointer;
}

.camera-hint {
  margin: 0;
  font-size: 0.85rem;
  color: #b8c9b8;
  text-align: center;
}

.camera-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.camera-btn {
  border: 0;
  background: rgba(255, 255, 255, 0.12);
  color: inherit;
  border-radius: 12px;
  padding: 10px 16px;
  font-size: 0.95rem;
  cursor: pointer;
  min-width: 72px;
}

.camera-btn--icon {
  min-width: 44px;
  padding: 10px 12px;
}

.camera-btn.is-on {
  background: #f5c451;
  color: #2b2200;
}

.camera-side {
  display: flex;
  gap: 8px;
  min-width: 72px;
  justify-content: flex-end;
}

.camera-shutter {
  position: relative;
  width: 72px;
  height: 72px;
  border-radius: 50%;
  border: 4px solid rgba(255, 255, 255, 0.85);
  background: transparent;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.camera-shutter:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.camera-shutter-ring {
  width: 54px;
  height: 54px;
  border-radius: 50%;
  background: #f2f6f2;
  transition: transform 0.12s ease;
}

.camera-shutter:not(:disabled):active .camera-shutter-ring {
  transform: scale(0.88);
}

.camera-fallback {
  border: 1px dashed rgba(255, 255, 255, 0.4);
  background: transparent;
  color: inherit;
  border-radius: 12px;
  padding: 10px;
  cursor: pointer;
  font-size: 0.9rem;
}

@media (max-width: 480px) {
  .camera-card {
    border-radius: 14px;
    padding: 12px;
  }

  .camera-shutter {
    width: 64px;
    height: 64px;
  }

  .camera-shutter-ring {
    width: 46px;
    height: 46px;
  }
}
</style>
