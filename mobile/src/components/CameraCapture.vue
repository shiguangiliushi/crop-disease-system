<template>
  <div v-if="visible" class="cam" role="dialog" aria-modal="true" :aria-label="t('camera.title')">
    <!-- 取景框：整屏铺满，取景就是最后拍到的画面（所见即所得） -->
    <div class="cam-stage" :class="{ 'is-mirrored': mirrored }">
      <video ref="videoEl" class="cam-video" autoplay playsinline muted></video>

      <div v-if="state === 'live'" class="cam-grid" aria-hidden="true">
        <span></span><span></span><span></span><span></span>
      </div>

      <div v-if="state !== 'live'" class="cam-mask">
        <span v-if="state === 'opening'" class="cam-spinner" aria-hidden="true"></span>
        <i v-else class="cam-warn">!</i>
        <p class="cam-mask-text">{{ state === 'opening' ? t('camera.opening') : errorText }}</p>
        <div class="cam-mask-actions">
          <button v-if="state === 'error' && isSupported" type="button" class="cam-mask-btn" @click="start">
            {{ t('camera.retry') }}
          </button>
          <button v-if="state === 'error'" type="button" class="cam-mask-btn" @click="useSystemCamera">
            {{ t('camera.fallback') }}
          </button>
        </div>
      </div>
    </div>

    <!-- 顶部：关闭 / 切换摄像头 / 补光（都做了 safe-area 适配） -->
    <div class="cam-top">
      <button type="button" class="cam-icon-btn" :aria-label="t('camera.cancel')" @click="close">✕</button>
      <p class="cam-title">{{ t('camera.title') }}</p>
      <div class="cam-top-right">
        <button
          v-if="torchSupported"
          type="button"
          class="cam-icon-btn"
          :class="{ 'is-on': torchOn }"
          :aria-label="t('camera.torchOn')"
          @click="toggleTorch"
        >
          ⚡
        </button>
        <button
          v-if="canSwitch"
          type="button"
          class="cam-icon-btn"
          :aria-label="t('camera.switch')"
          @click="switchCamera"
        >
          ⟳
        </button>
      </div>
    </div>

    <p class="cam-hint">{{ t('camera.hint') }}</p>

    <div class="cam-bottom">
      <button type="button" class="cam-ghost" @click="useSystemCamera">{{ t('camera.fallback') }}</button>
      <button
        type="button"
        class="cam-shutter"
        :disabled="state !== 'live' || capturing"
        :aria-label="t('camera.shoot')"
        @click="shoot"
      >
        <span class="cam-shutter-core"></span>
      </button>
      <span class="cam-ghost cam-ghost--placeholder" aria-hidden="true"></span>
    </div>
  </div>
</template>

<script setup>
/**
 * 移动端应用内拍照（第 75 批）
 * ----------------------------------------------------------------------------
 * 与桌面端组件同源，但按手机场景重做：
 *   · 整屏取景（横屏照片在小弹窗里看不清，农户没法确认病斑拍进去没有）
 *   · 控件贴底 + safe-area（iPhone 底部 Home 条不遮挡快门）
 *   · 长边压到 1280：田间 4G 弱网下上传更快，对识别精度无影响
 *
 * ⚠️ 「不支持」是常态而不是异常：商户/农户用 http://<电脑IP>:5174 访问时
 * 浏览器不暴露 mediaDevices，此时必须能一键退回系统相机（`<input capture>`）。
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { useI18n } from '@/i18n';
import { captureFrameFromVideo, describeCameraError, hasInAppCamera } from '@/utils/camera';

const props = defineProps({
  visible: { type: Boolean, default: false },
  facing: { type: String, default: 'environment' },
  maxEdge: { type: Number, default: 1280 },
  quality: { type: Number, default: 0.9 },
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
  if (videoEl.value) videoEl.value.srcObject = null;
  torchSupported.value = false;
  torchOn.value = false;
};

const refreshDeviceInfo = async () => {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    canSwitch.value = devices.filter((d) => d.kind === 'videoinput').length > 1;
  } catch {
    canSwitch.value = false;
  }
};

/**
 * 打开摄像头并开始取景（第 107 批补说明）
 *
 * 流程：能力探测 → 关掉上一路流 → getUserMedia → 挂到 `<video>` → play → 探测补光灯。
 *
 * 逐处说明（这些在桌面端同款组件里都有注释，移动端此前是空的）：
 *
 * · **L164 `videoEl.value.play().catch(() => {})`**：这个空 catch 不是偷懒 ——
 *   **iOS Safari 必须显式 play()，否则画面停在第一帧**（黑屏或一张静止图），
 *   而 `play()` 在某些时机返回的 Promise 会被浏览器以 `AbortError` 拒绝
 *   （例如立刻又调用了 `stopStream`）。这种拒绝**不影响取景**，
 *   所以刻意吞掉；真出问题会表现在"画面不动"，而不是这里报错。
 *
 * · **L158 用 `1280 / 960` 而不是 `maxEdge`**：这是**取景分辨率**，
 *   与"最终上传尺寸"是两件事（见 `utils/image.js` 顶部的三处配置对照表）。
 *   1280 在"清晰度够用"与"中低端机不卡、内存不炸"之间取平衡；
 *   抓帧之后还会再走一次 `compressImage`（长边 1600，不会放大）。
 *
 * · **L176 对任何失败都 `emit('unsupported')`** ——
 *   ⚠️ **这里与桌面端是有意不同的，写下来免得有人"统一"掉**：
 *   桌面端（`frontend/src/components/CameraCapture.vue`）只在
 *   `camera.denied / camera.notFound / camera.insecure` 三种情况下才升级为"不支持"，
 *   其余（`camera.busy`、`camera.overconstrained`、`camera.failed`）留在应用内让用户重试；
 *   移动端则一律交还给**系统相机**。
 *   理由：手机上"应用内取景失败"的兜底体验（系统相机）比"让农户对着一个错误提示重试"更好，
 *   而田间弱网/低端机正是 `overconstrained` 与 `busy` 高发的环境。
 *   代价：一次**偶发**失败也会把用户推到系统相机 —— 可以接受，因为这个组件本来就是"锦上添花"，
 *   系统相机始终是可靠路径。
 */
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
      // ideal 而非 exact：设备不支持这个尺寸时会退到最接近的，而不是直接失败
      video: { facingMode: { ideal: facingMode.value }, width: { ideal: 1280 }, height: { ideal: 960 } },
    });

    await nextTick();
    if (!videoEl.value) throw new Error('video_element_missing');
    videoEl.value.srcObject = stream;
    // iOS Safari 需要显式 play()，否则画面停在第一帧；AbortError 可安全忽略
    await videoEl.value.play().catch(() => {});

    state.value = 'live';
    await refreshDeviceInfo();

    // 补光灯能力要问 track：设备声称支持但可能实际调不动（见 toggleTorch 的兜底）
    const track = stream.getVideoTracks()[0];
    torchSupported.value = Boolean(track?.getCapabilities?.().torch);
  } catch (error) {
    stopStream();
    state.value = 'error';
    errorKey.value = describeCameraError(error);
    errorDetail.value = error?.message || '';
    // 移动端策略：任何失败都交还系统相机（与桌面端不同，理由见上方说明）
    emit('unsupported', errorKey.value);
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
    state.value = 'error';
    errorKey.value = 'camera.shootFailed';
    errorDetail.value = error?.message || '';
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
    torchSupported.value = false;
    console.warn('[camera] 补光灯切换失败:', error?.message || error);
  }
};

const useSystemCamera = () => {
  close();
  emit('fallback', errorKey.value || 'camera.unsupported');
};

const close = () => {
  stopStream();
  state.value = 'idle';
  emit('update:visible', false);
};

const onVisibilityChange = () => {
  if (!props.visible) return;
  if (document.hidden) {
    // 切到后台先释放摄像头：否则手机上指示灯一直亮着
    stopStream();
    state.value = 'idle';
  } else if (state.value === 'idle') {
    start();
  }
};

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      facingMode.value = props.facing;
      document.body.style.overflow = 'hidden';
      document.addEventListener('visibilitychange', onVisibilityChange);
      start();
    } else {
      document.body.style.overflow = '';
      document.removeEventListener('visibilitychange', onVisibilityChange);
      stopStream();
    }
  },
);

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange);
  document.body.style.overflow = '';
  stopStream();
});
</script>

<style scoped>
.cam {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background: #000;
  color: #fff;
  display: flex;
  flex-direction: column;
}

.cam-stage {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.cam-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.cam-stage.is-mirrored .cam-video {
  transform: scaleX(-1);
}

.cam-grid {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: repeat(3, 1fr);
  pointer-events: none;
}

.cam-grid span {
  border: 1px solid rgba(255, 255, 255, 0.16);
}

.cam-grid span:nth-child(4) {
  border: 0;
}

.cam-mask {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 32px 24px;
  text-align: center;
  background: rgba(0, 0, 0, 0.78);
}

.cam-warn {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: 2px solid #ffc857;
  color: #ffc857;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 1.4rem;
  font-weight: 700;
}

.cam-mask-text {
  margin: 0;
  line-height: 1.7;
  font-size: 0.95rem;
}

.cam-mask-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(280px, 80%);
}

.cam-mask-btn {
  border: 1px solid rgba(255, 255, 255, 0.45);
  background: transparent;
  color: inherit;
  border-radius: 12px;
  padding: 12px 16px;
  font-size: 0.95rem;
}

.cam-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid rgba(255, 255, 255, 0.25);
  border-top-color: #7ec87e;
  border-radius: 50%;
  animation: cam-spin 0.9s linear infinite;
}

@keyframes cam-spin {
  to {
    transform: rotate(360deg);
  }
}

.cam-top {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: calc(env(safe-area-inset-top, 0px) + 10px) 12px 6px;
  background: linear-gradient(180deg, rgba(0, 0, 0, 0.55), transparent);
}

.cam-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.cam-top-right {
  display: flex;
  gap: 8px;
}

.cam-icon-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 0;
  background: rgba(0, 0, 0, 0.42);
  color: #fff;
  font-size: 1.05rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.cam-icon-btn.is-on {
  background: #f5c451;
  color: #2b2200;
}

.cam-hint {
  position: relative;
  z-index: 2;
  margin: 0;
  margin-top: auto;
  padding: 8px 20px;
  text-align: center;
  font-size: 0.82rem;
  color: rgba(255, 255, 255, 0.82);
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
}

.cam-bottom {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 20px calc(env(safe-area-inset-bottom, 0px) + 18px);
  background: linear-gradient(0deg, rgba(0, 0, 0, 0.6), transparent);
}

.cam-ghost {
  flex: 1;
  border: 1px solid rgba(255, 255, 255, 0.4);
  background: rgba(0, 0, 0, 0.3);
  color: #fff;
  border-radius: 10px;
  padding: 10px 8px;
  font-size: 0.8rem;
  line-height: 1.3;
}

.cam-ghost--placeholder {
  visibility: hidden;
  border-color: transparent;
  background: transparent;
}

.cam-shutter {
  width: 74px;
  height: 74px;
  border-radius: 50%;
  border: 4px solid rgba(255, 255, 255, 0.9);
  background: transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}

.cam-shutter:disabled {
  opacity: 0.45;
}

.cam-shutter-core {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #fff;
}

.cam-shutter:not(:disabled):active .cam-shutter-core {
  transform: scale(0.9);
}
</style>
