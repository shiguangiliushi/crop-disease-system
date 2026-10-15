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
            <!-- ⚠️ 仍然是**纯文本渲染，绝不用 `v-html`**：模型输出属于不可信输入，
                 项目已有 sanitize 规范（`npm run verify:xss`），这里不开口子。
                 但模型习惯写 `**加粗**`，纯文本渲染会把星号原样显示出来（用户反馈过
                 "回答为什么会出现 `**` 和【数字】"）。所以**只解析加粗一种标记**：
                 拆成文本片段 + `<strong>`，其余一律当纯文本 ——
                 这样既有可读性，又不引入任何 HTML 注入面（标签名是我们写死的）。
                 解析逻辑在 `utils/assistantText.js`（与独立问答页共用，含单测）。 -->
            <p
              v-for="(segments, index) in answerLines(msg.content)"
              :key="index"
              class="assistant-line"
            >
              <template v-for="(seg, si) in segments" :key="si">
                <strong v-if="seg.bold">{{ seg.text }}</strong>
                <template v-else>{{ seg.text }}</template>
              </template>
            </p>
          </div>

          <!-- 降级说明：告诉用户这不是 AI 回答，而是档案原文 -->
          <p v-if="msg.role === 'assistant' && msg.degradeHint" class="assistant-degrade">
            <i class="bi bi-info-circle" aria-hidden="true"></i>
            {{ msg.degradeHint }}
          </p>

          <!-- 回答被长度上限截断（第 204 批）。
               ⚠️ 与"降级"是**两件事**：降级=没调用模型，截断=模型没说完。
               两者都会让用户觉得"答案有问题"，但成因完全不同，提示也要分开。 -->
          <p v-if="msg.role === 'assistant' && msg.truncated" class="assistant-truncated">
            <i class="bi bi-exclamation-triangle" aria-hidden="true"></i>
            {{ t('assistant.hintTruncatedAnswer') }}
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

          <!-- 反馈闭环（第 196 批）：只对**已经答完**的助手消息显示。
               流式进行中不显示 —— 答案还没完，评价没有意义。 -->
          <div v-if="msg.role === 'assistant' && msg.messageId && !isStreaming(msg)" class="assistant-feedback">
            <template v-if="msg.verdict">
              <span class="assistant-feedback-done">
                <i class="bi bi-check-circle" aria-hidden="true"></i>
                {{ t('assistant.feedbackThanks') }}
                <em v-if="msg.verdict === 'useless'">{{ t('assistant.feedbackUseless') }}</em>
              </span>
              <el-button link size="small" @click="openFeedback(msg)">
                {{ t('assistant.feedbackSubmit') }}
              </el-button>
            </template>
            <template v-else>
              <el-button size="small" plain :disabled="feedbackBusy" @click="rate(msg, 'helpful')">
                <i class="bi bi-hand-thumbs-up me-1"></i>{{ t('assistant.feedbackHelpful') }}
              </el-button>
              <el-button size="small" plain :disabled="feedbackBusy" @click="openFeedback(msg)">
                <i class="bi bi-hand-thumbs-down me-1"></i>{{ t('assistant.feedbackUseless') }}
              </el-button>
            </template>

            <!-- 转人工：单独一条（它不是"评价"，而是"换个人来答"）。
                 已转过就显示"已转人工"而不是再给按钮 —— 后端虽然幂等，
                 但让用户重复点是设计上的浪费。 -->
            <span class="assistant-escalate">
              <el-tooltip :content="t('assistant.escalateHint')" placement="top" :show-after="300">
                <el-button
                  v-if="!escalatedQuestionId"
                  link
                  size="small"
                  :loading="escalating"
                  @click="escalate(msg)"
                >
                  <i class="bi bi-person-plus me-1"></i>{{ t('assistant.escalate') }}
                </el-button>
                <span v-else class="assistant-escalate-done">
                  <i class="bi bi-check-circle me-1" aria-hidden="true"></i>{{ t('assistant.escalateDone') }}
                </span>
              </el-tooltip>
            </span>
          </div>

          <!-- "没用"的补充说明：**这是最有价值的信号**（只统计次数无法知道该补什么） -->
          <div v-if="msg.showNoteInput" class="assistant-note">
            <p class="assistant-note-label">{{ t('assistant.feedbackReasonLabel') }}</p>
            <el-input
              v-model="msg.noteDraft"
              type="textarea"
              :rows="2"
              resize="none"
              maxlength="500"
              :placeholder="t('assistant.feedbackReasonPlaceholder')"
            />
            <div class="assistant-note-actions">
              <el-button size="small" text @click="msg.showNoteInput = false">
                {{ t('assistant.feedbackCancel') }}
              </el-button>
              <el-button size="small" type="primary" :loading="feedbackBusy" @click="rate(msg, 'useless')">
                {{ t('assistant.feedbackSubmit') }}
              </el-button>
            </div>
          </div>
        </div>

        <!-- 第 195 批：改为 SSE 流式后**不再有"思考中"骨架** —— 正文自己逐字出现。
             只在"请求已发出但还没收到第一个字"时给一个轻提示，避免这段空窗被当成卡死。 -->
        <div v-if="loading && !streamingStarted" class="assistant-msg is-assistant">
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
import { askAssistantStream, escalateSession, formatAssistantError, sendAssistantFeedback } from '@/api/assistant';
import { useI18n } from '@/i18n';
import { parseAnswerLines } from '@/utils/assistantText';

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
/** 是否已经收到第一个正文字（用于决定要不要显示"正在查找词条…"） */
const streamingStarted = ref(false);
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
/**
 * 把回答按行拆成片段，供模板渲染（解析逻辑见 `utils/assistantText.js`，含单测）。
 *
 * ⚠️ 这里**刻意不自己写正则**：抽屉与独立问答页都要这段解析，
 *    抄两份迟早只改一处（第 210 批就是这么抽出来的）。
 */
const answerLines = parseAnswerLines;

/** 降级原因 → 给用户的一句人话（不是错误码） */
const degradeHintOf = (reason) => {
  if (!reason) return '';
  // ⚠️ `llm_error_partial` 必须单独处理（第 198 批修）：它表示"AI 已经答了一部分，
  //    中途断了"，界面上是**被截断的 AI 回答**。若也套用"以上为档案原文"，
  //    用户会以为这段是词条原文 —— 那是**说错了内容的来源**。
  if (reason === 'llm_error_partial') return t('assistant.hintTruncated');
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

// ── 反馈闭环（第 196 批）───────────────────────────────────────────────
const feedbackBusy = ref(false);
const escalating = ref(false);
/** 已转人工的工单 id（非空即视为"这次会话已转过"） */
const escalatedQuestionId = ref(null);

/** 流式进行中的那条还没有 messageId，不该显示评价按钮 */
const isStreaming = (msg) => loading.value && !msg.messageId;

const openFeedback = (msg) => {
  // 展开输入框时把已有说明带出来，便于用户在原话上修改
  msg.noteDraft = msg.feedbackNote || '';
  msg.showNoteInput = true;
};

const rate = async (msg, verdict) => {
  if (feedbackBusy.value || !msg.messageId) return;
  feedbackBusy.value = true;
  try {
    const data = await sendAssistantFeedback(msg.messageId, verdict, msg.noteDraft || '');
    msg.verdict = data?.verdict || verdict;
    msg.feedbackNote = data?.note || '';
    msg.showNoteInput = false;
    ElMessage.success(t('assistant.feedbackThanks'));
  } catch (error) {
    ElMessage.error(formatAssistantError(error) || t('assistant.feedbackSubmitFailed'));
  } finally {
    feedbackBusy.value = false;
  }
};

/**
 * 转人工。**只在拿到 sessionId 后才可能** —— 第一次提问的响应里才有会话 id；
 * 若用户还没问过任何问题，"转人工"没有内容可转（后端也会以 404 拒绝）。
 */
const escalate = async (msg) => {
  if (escalating.value) return;
  const target = sessionId.value;
  if (!target) {
    ElMessage.warning(t('assistant.escalateHint'));
    return;
  }
  escalating.value = true;
  try {
    const data = await escalateSession(target, msg.feedbackNote || '');
    escalatedQuestionId.value = data?.consult_question_id || 'sent';
    ElMessage.success(data?.created === false
      ? t('assistant.escalateAlready')
      : t('assistant.escalateDone'));
  } catch (error) {
    ElMessage.error(formatAssistantError(error) || t('assistant.escalateFailed'));
  } finally {
    escalating.value = false;
  }
};

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
  streamingStarted.value = false;
  scrollToBottom();

  // 先占一条**空**的助手气泡，正文随 SSE 的 delta 逐段追加。
  // 这样用户第一眼就看到"回答区已就位"，而不是盯着"思考中" —— 实测首个正文
  // 0.7s 到达（同步版要等 3.1s 才整段出现）。
  // `messageId` 先留空：它对评价按钮的显示条件有用（流式期间不该出现评价）。
  const placeholder = {
    key: ++messageKey,
    role: 'assistant',
    content: '',
    citations: [],
    degradeHint: '',
    truncated: false,
    hasPesticide: false,
    messageId: null,
    verdict: '',
    feedbackNote: '',
    noteDraft: '',
    showNoteInput: false,
  };
  messages.value.push(placeholder);
  const target = messages.value[messages.value.length - 1];
  let received = false;

  try {
    await askAssistantStream(
      {
        question,
        session_id: sessionId.value || undefined,
        pest_identifier: props.pestIdentifier || undefined,
      },
      {
        onDelta: (text) => {
          received = true;
          streamingStarted.value = true;
          target.content += text;
          // 跟随滚动：让最新一行始终可见（否则长回答时用户要手动往下拉）
          scrollToBottom();
        },
      },
    ).then((data) => {
      if (data?.session_id) sessionId.value = data.session_id;
      // 兜底：若某个事件丢了，用最终 answer 校正，保证界面与库里一致
      if (data?.answer && data.answer !== target.content) target.content = data.answer;
      target.citations = Array.isArray(data?.citations) ? data.citations : [];
      target.degradeHint = data?.degraded ? degradeHintOf(data.degrade_reason) : '';
      target.hasPesticide = hasPesticideText(target.content);
      // 第 204 批：被长度上限截断时提示（否则用户看到"半句话 + 好像答完了"）
      target.truncated = Boolean(data?.truncated);
      // 拿到 message_id 之后评价按钮才会出现（见 isStreaming）
      target.messageId = data?.message_id || null;
    });
  } catch (error) {
    // 只有真正的失败才走到这里（业务降级是 200 + degraded）。
    // 把占位气泡**撤掉**，否则界面会留下一个空回答，看起来像"答了但什么都没说"。
    const index = messages.value.indexOf(target);
    if (index >= 0) messages.value.splice(index, 1);
    ElMessage.error(formatAssistantError(error));
  } finally {
    if (!received && target.content) target.content = target.content.trim();
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
  /* ⚠️ 第 203 批：**固定宽度**，不再由内容决定。
     原来是 `display: inline-block; max-width: 100%` —— 收缩到内容宽度，
     于是同一次对话里短回答占不到半行、长回答撑满整行（实测 46% vs 73%），
     每条消息宽度都不同，看着参差不齐；流式出字时宽度还会**边写边长**。
     现在固定 88%，靠左右对齐区分提问与回答。
     抽屉比页面窄（默认 30% 视口），所以这里用百分比而非像素。 */
  width: 88%;
  box-sizing: border-box;
  display: block;
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

/* 被长度上限截断的提示：用琥珀色与"降级"的棕黄区分开 */
.assistant-truncated {
  font-size: 0.75rem;
  color: #b45309;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 6px;
  padding: 0.3rem 0.5rem;
  margin: 0.35rem 0 0;
  width: 88%;
  box-sizing: border-box;
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

/* 第 196 批：反馈闭环（评价 / 转人工 / 补充说明） */
.assistant-feedback {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  margin-top: 0.45rem;
}

.assistant-feedback-done {
  font-size: 0.78rem;
  color: #2f6b4f;
}

.assistant-feedback-done em {
  font-style: normal;
  color: #8a6d3b;
}

.assistant-escalate {
  margin-left: auto;   /* 推到右侧：它与其他按钮不同类（不是"评价"） */
}

.assistant-escalate-done {
  font-size: 0.75rem;
  color: #6b7280;
}

.assistant-note {
  margin-top: 0.5rem;
  padding: 0.6rem 0.7rem;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.assistant-note-label {
  font-size: 0.78rem;
  color: #4b5563;
  margin-bottom: 0.35rem;
}

.assistant-note-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.4rem;
  margin-top: 0.45rem;
}
</style>
