<template>
  <el-drawer
    v-model="visible"
    :title="t('assistant.title')"
    direction="rtl"
    size="520px"
    :destroy-on-close="false"
    class="ask-assistant-drawer"
  >
    <div class="assistant-body">
      <!-- 上下文提示：让用户知道助手已经知道是哪个病害 -->
      <div v-if="diseaseName" class="assistant-context">
        <i class="bi bi-tag" aria-hidden="true"></i>
        <span>{{ t('assistant.contextDisease', { name: diseaseName }) }}</span>
      </div>

      <!-- 对话区 -->
      <div ref="scrollBox" class="assistant-thread">
        <div v-if="!messages.length" class="assistant-empty">
          <p class="assistant-empty-title">{{ t('assistant.emptyTitle') }}</p>
          <p class="assistant-empty-desc">{{ t('assistant.emptyDesc') }}</p>
          <!-- 快捷问题：农户最常问的四类。点一下直接问，省去打字 -->
          <div class="assistant-suggestions">
            <el-button
              v-for="item in suggestions"
              :key="item.key"
              size="small"
              plain
              :disabled="loading"
              @click="submit(item.text)"
            >
              {{ item.label }}
            </el-button>
          </div>
        </div>

        <div v-for="msg in messages" :key="msg.key" :class="['assistant-msg', `is-${msg.role}`]">
          <div class="assistant-bubble">
            <!-- 纯文本渲染而不是 v-html：模型输出是不可信内容，
                 这里绝不能走 v-html（项目已有 sanitize 规范，见 verify-xss 脚本） -->
            <p v-for="(line, index) in linesOf(msg.content)" :key="index" class="assistant-line">{{ line }}</p>
          </div>

          <!-- 降级说明：告诉用户这不是 AI 回答，而是档案原文 -->
          <p v-if="msg.role === 'assistant' && msg.degradeHint" class="assistant-degrade">
            <i class="bi bi-info-circle" aria-hidden="true"></i>
            {{ msg.degradeHint }}
          </p>

          <!-- 来源引用 -->
          <div v-if="msg.citations && msg.citations.length" class="assistant-citations">
            <span class="assistant-citations-label">{{ t('assistant.sources') }}</span>
            <el-tooltip
              v-for="(cite, index) in msg.citations"
              :key="index"
              :content="cite.snippet"
              placement="top"
              :show-after="200"
            >
              <span class="assistant-cite">［{{ index + 1 }}］{{ cite.label }}</span>
            </el-tooltip>
          </div>

          <!-- 用药免责：词条里带药剂时后端要求必须给这句，前端再显式展示一次 -->
          <p v-if="msg.role === 'assistant' && msg.hasPesticide" class="assistant-disclaimer">
            {{ t('assistant.pesticideDisclaimer') }}
          </p>
        </div>

        <div v-if="loading" class="assistant-msg is-assistant">
          <div class="assistant-bubble assistant-typing">
            <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
            {{ t('assistant.thinking') }}
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="assistant-input">
        <el-input
          v-model="draft"
          type="textarea"
          :rows="2"
          resize="none"
          :maxlength="maxLength"
          :placeholder="t('assistant.placeholder')"
          :disabled="loading"
          @keydown.enter.exact.prevent="submit()"
        />
        <div class="assistant-input-actions">
          <span class="assistant-hint">{{ t('assistant.sendHint') }}</span>
          <el-button
            type="primary"
            :loading="loading"
            :disabled="!draft.trim()"
            @click="submit()"
          >
            {{ t('assistant.send') }}
          </el-button>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
/**
 * 「问一下助手」抽屉（第 194 批）
 *
 * 定位：**识别结果页的追问入口**。用户刚看到识别结果，最想追问的是
 * "怎么治""打什么药""会不会传染" —— 所以它带着 `pest_identifier` 进来，
 * 后端据此把该病害直接置顶（见 assistant/retriever.py 的"识别结果直连"）。
 *
 * 三个刻意的实现选择：
 *
 *  1. **不拉历史会话**。抽屉是"一次会话问到完"，刷新即结束。真要做多会话，
 *     该配一个独立问答页，而不是把这个抽屉做重。
 *  2. **模型输出用纯文本渲染，不用 v-html**。内容来自外部模型，属于不可信输入；
 *     项目已有 XSS 规范（`npm run verify:xss`），这里不开口子。
 *  3. **降级不报错**。后端降级时也是 200 + `degraded`，前端把它渲染成
 *     "档案原文 + 说明"，而不是红色错误提示 —— 那对农户没有可操作性。
 */
import { computed, nextTick, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { askAssistant, formatAssistantError } from '@/api/assistant';
import { useI18n } from '@/i18n';

const props = defineProps({
  /** 显式控制显示（配合 v-model:visible） */
  visible: { type: Boolean, default: false },
  /** 当前病害名（仅用于顶部上下文提示） */
  diseaseName: { type: String, default: '' },
  /** 识别结果直连的病害标识，如 tomato___late_blight */
  pestIdentifier: { type: String, default: '' },
});

const emit = defineEmits(['update:visible']);

const { t } = useI18n();

const visible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value),
});

const maxLength = 500; // 与后端 guard.MAX_QUESTION_CHARS 一致
const draft = ref('');
const loading = ref(false);
const messages = ref([]);
const sessionId = ref(null);
const scrollBox = ref(null);
let messageKey = 0;

/** 快捷问题：覆盖"怎么治/什么药/怎么认/怎么防"四类真实需求 */
const suggestions = computed(() => [
  { key: 'treat', label: t('assistant.qTreat'), text: t('assistant.qTreatText') },
  { key: 'chemical', label: t('assistant.qChemical'), text: t('assistant.qChemicalText') },
  { key: 'identify', label: t('assistant.qIdentify'), text: t('assistant.qIdentifyText') },
  { key: 'prevent', label: t('assistant.qPrevent'), text: t('assistant.qPreventText') },
]);

/** 按行拆开，逐行 <p> —— 模型输出里的编号与空行因此能保住版式 */
const linesOf = (content) => String(content || '').split('\n').filter((line) => line.trim() !== '');

/** 降级原因 → 给用户的一句人话（不是错误码） */
const degradeHintOf = (reason) => {
  if (!reason) return '';
  if (['llm_disabled', 'llm_error', 'no_citation'].includes(reason)) {
    return t('assistant.hintArchiveOnly');
  }
  if (reason === 'no_source') return t('assistant.hintNoSource');
  if (reason === 'rate_limited') return t('assistant.hintRateLimited');
  if (reason === 'sensitive') return t('assistant.hintSensitive');
  if (reason === 'too_long') return t('assistant.hintTooLong');
  return '';
};

/** 回答里是否出现药剂（用于补免责声明）。保守匹配：常见剂型/百分比浓度/稀释倍数 */
const hasPesticideText = (text) => /(\d+%|倍液|稀释|可湿性粉剂|悬浮剂|水分散粒剂|间隔期)/.test(String(text || ''));

const scrollToBottom = async () => {
  await nextTick();
  const box = scrollBox.value;
  if (box) box.scrollTop = box.scrollHeight;
};

const submit = async (presetText) => {
  const question = String(presetText ?? draft.value).trim();
  if (!question || loading.value) return;

  messages.value.push({ key: ++messageKey, role: 'user', content: question, citations: [] });
  draft.value = '';
  loading.value = true;
  scrollToBottom();

  try {
    const data = await askAssistant({
      question,
      session_id: sessionId.value || undefined,
      pest_identifier: props.pestIdentifier || undefined,
    });
    if (data?.session_id) sessionId.value = data.session_id;

    messages.value.push({
      key: ++messageKey,
      role: 'assistant',
      content: data?.answer || '',
      citations: Array.isArray(data?.citations) ? data.citations : [],
      degradeHint: data?.degraded ? degradeHintOf(data.degrade_reason) : '',
      hasPesticide: hasPesticideText(data?.answer),
    });
  } catch (error) {
    // 只有真正的失败才走到这里（降级是 200）。用 toast 而不是塞进对话流：
    // 对话流里出现一条"系统错误"会让人以为助手答不了话。
    ElMessage.error(formatAssistantError(error));
  } finally {
    loading.value = false;
    scrollToBottom();
  }
};

// 每次打开都滚到底部（用户可能上次看到一半关掉）
watch(visible, (opened) => {
  if (opened) scrollToBottom();
});

defineExpose({ submit });
</script>

<style scoped>
.assistant-body {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.assistant-context {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 0.75rem;
  margin-bottom: 0.75rem;
  font-size: 0.85rem;
  color: #2f6b4f;
  background: #eef7f1;
  border-radius: 6px;
}

.assistant-thread {
  flex: 1;
  overflow-y: auto;
  padding-right: 0.25rem;
}

.assistant-empty {
  text-align: center;
  color: #6b7280;
  padding: 1.5rem 0.5rem;
}

.assistant-empty-title {
  font-weight: 600;
  color: #374151;
  margin-bottom: 0.35rem;
}

.assistant-empty-desc {
  font-size: 0.85rem;
  margin-bottom: 1rem;
}

.assistant-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: center;
}

.assistant-msg {
  margin-bottom: 1rem;
}

.assistant-msg.is-user {
  display: flex;
  justify-content: flex-end;
}

.assistant-bubble {
  display: inline-block;
  max-width: 100%;
  padding: 0.6rem 0.8rem;
  border-radius: 10px;
  background: #f3f4f6;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

.assistant-msg.is-user .assistant-bubble {
  background: #2f6b4f;
  color: #fff;
}

.assistant-line {
  margin: 0 0 0.35rem;
}

.assistant-line:last-child {
  margin-bottom: 0;
}

.assistant-typing {
  color: #6b7280;
}

.assistant-degrade,
.assistant-disclaimer {
  font-size: 0.78rem;
  color: #8a6d3b;
  margin: 0.35rem 0 0;
}

.assistant-disclaimer {
  color: #6b7280;
}

.assistant-citations {
  margin-top: 0.4rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
}

.assistant-citations-label {
  font-size: 0.78rem;
  color: #6b7280;
}

.assistant-cite {
  font-size: 0.75rem;
  color: #2f6b4f;
  background: #eef7f1;
  border-radius: 4px;
  padding: 0.1rem 0.35rem;
  cursor: help;
}

.assistant-input {
  border-top: 1px solid #e5e7eb;
  padding-top: 0.75rem;
  margin-top: 0.5rem;
}

.assistant-input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.5rem;
}

.assistant-hint {
  font-size: 0.75rem;
  color: #9ca3af;
}
</style>
