<!--
  智能问答（独立页面，第 198 批）

  ## 为什么需要一个独立页面

  在此之前助手只能从**识别结果页**打开抽屉 —— 也就是说：
  - 手上没有识别结果时（比如刚听说某个病、想先查明白），**根本没法提问**；
  - 问过的问答记录**看不到**，关掉抽屉就找不回来了。

  这个页面补上这两点：左侧问答历史（可搜索、可删除、可点回去接着问），
  中间是完整对话，顶部可以随时开新提问。

  ## 与抽屉的分工（_刻意保留两套渲染_）

  抽屉是"识别完之后就地追问一句"，空间窄、只显示当前这一轮；
  本页是"专门来查资料的"，空间宽、要显示历史与全部往来。
  两者的布局与交互差别很大，**共用一套消息组件反而会互相牵制**
  （抽屉要紧凑、页面要舒展），所以这里自己渲染一次。
  但**反馈闭环的行为是共享的**（走同一套 `api/assistant.js` 接口），
  不存在"页面上能打分、抽屉里不能"这种不一致。
-->
<template>
  <div class="assistant-page">
    <!-- 左：问答历史 -->
    <aside class="assistant-side" :class="{ 'is-hidden-mobile': mobileView === 'chat' }">
      <div class="assistant-side-head">
        <el-button type="primary" class="w-100" @click="startNewChat">
          <i class="bi bi-plus-lg me-1"></i>{{ t('assistant.newChat') }}
        </el-button>
      </div>

      <div class="assistant-side-search">
        <el-input
          v-model="keyword"
          size="small"
          clearable
          :placeholder="t('assistant.searchHistory')"
          :prefix-icon="Search"
        />
      </div>

      <div class="assistant-side-list" v-loading="listLoading">
        <p v-if="!filteredSessions.length && !listLoading" class="assistant-side-empty">
          {{ keyword ? t('assistant.noSessions') : t('assistant.historyEmpty') }}
        </p>
        <div
          v-for="item in filteredSessions"
          :key="item.id"
          class="assistant-side-item"
          :class="{ 'is-active': item.id === currentSessionId }"
          @click="openSession(item)"
        >
          <div class="assistant-side-title">
            <span class="assistant-side-name">{{ item.title || t('assistant.newChat') }}</span>
            <!-- 降级标记：让用户扫一眼就知道"这次没真的答上来"。
                 ⚠️ 这里**不写"降级"** —— 那是内部术语，用户看不懂；
                 改用已有的"未用 AI 生成"说明短语。 -->
            <el-tag v-if="item.degraded" size="small" type="warning" effect="plain">
              {{ t('assistant.hintArchiveOnly') }}
            </el-tag>
          </div>
          <div class="assistant-side-meta">
            <span v-if="item.pest_name">{{ item.pest_name }} · </span>
            <span>{{ formatTime(item.updated_at) }}</span>
          </div>
          <div class="assistant-side-preview">{{ item.preview }}</div>
          <el-button
            class="assistant-side-del"
            link
            size="small"
            :title="t('assistant.deleteSession')"
            @click.stop="removeSession(item)"
          >
            <i class="bi bi-trash"></i>
          </el-button>
        </div>
        <div v-if="hasMore" class="assistant-side-more">
          <el-button link size="small" :loading="listLoading" @click="loadSessions(false)">
            {{ t('assistant.loadMore') }}
          </el-button>
        </div>
      </div>
    </aside>

    <!-- 右：对话 -->
    <section class="assistant-main" :class="{ 'is-hidden-mobile': mobileView === 'list' }">
      <header class="assistant-main-head">
        <el-button class="assistant-back" link @click="mobileView = 'list'">
          <i class="bi bi-arrow-left"></i>
        </el-button>
        <div class="assistant-main-title">
          <h1>{{ t('assistant.pageTitle') }}</h1>
          <p>{{ t('assistant.pageSubtitle') }}</p>
        </div>
        <span v-if="currentPestName" class="assistant-context">
          {{ t('assistant.contextDisease', { name: currentPestName }) }}
        </span>
      </header>

      <div ref="scrollBox" class="assistant-thread">
        <!-- 空态 -->
        <div v-if="!messages.length" class="assistant-welcome">
          <i class="bi bi-chat-square-text assistant-welcome-icon"></i>
          <h2>{{ t('assistant.welcomeTitle') }}</h2>
          <p>{{ t('assistant.welcomeHint') }}</p>
          <div class="assistant-presets">
            <el-button
              v-for="preset in presets"
              :key="preset"
              size="small"
              plain
              :disabled="loading"
              @click="submit(preset)"
            >
              {{ preset }}
            </el-button>
          </div>
        </div>

        <!-- 消息 -->
        <div
          v-for="msg in messages"
          :key="msg.key"
          class="assistant-msg"
          :class="msg.role === 'user' ? 'is-user' : 'is-assistant'"
        >
          <div class="assistant-bubble">
            <!-- 纯文本渲染，**不用 v-html**：模型输出直接当 HTML 插入是 XSS 入口 -->
            <p v-for="(para, i) in paragraphs(msg.content)" :key="i">{{ para }}</p>
            <p v-if="msg.role === 'assistant' && msg.hasPesticide" class="assistant-disclaimer">
              {{ t('assistant.pesticideDisclaimer') }}
            </p>
          </div>

          <!-- 引用来源 -->
          <div v-if="msg.citations?.length" class="assistant-cites">
            <span class="assistant-cites-label">{{ t('assistant.citations') }}</span>
            <el-tooltip
              v-for="(cite, i) in msg.citations"
              :key="i"
              :content="cite.snippet || cite.label"
              placement="top"
              :show-after="200"
            >
              <router-link
                v-if="cite.pest_id"
                :to="`/pests/${cite.pest_id}`"
                class="assistant-cite"
              >【{{ i + 1 }}】{{ cite.label }}</router-link>
              <span v-else class="assistant-cite">【{{ i + 1 }}】{{ cite.label }}</span>
            </el-tooltip>
          </div>

          <p v-if="msg.degradeHint" class="assistant-degrade-hint">
            <i class="bi bi-info-circle me-1"></i>{{ msg.degradeHint }}
          </p>

          <!-- 回答被长度上限截断（与"降级"是两件事：降级=没调用模型，截断=模型没说完） -->
          <p v-if="msg.truncated" class="assistant-truncated">
            <i class="bi bi-exclamation-triangle me-1"></i>{{ t('assistant.hintTruncatedAnswer') }}
          </p>

          <!-- 反馈闭环（与抽屉走同一套接口） -->
          <div v-if="msg.role === 'assistant' && msg.messageId && !isStreaming(msg)" class="assistant-feedback">
            <template v-if="msg.verdict">
              <span class="assistant-feedback-done">
                <i class="bi bi-check-circle" aria-hidden="true"></i>
                {{ t('assistant.feedbackThanks') }}
                <em v-if="msg.verdict === 'useless'">{{ t('assistant.feedbackUseless') }}</em>
              </span>
            </template>
            <template v-else>
              <el-button size="small" plain :disabled="feedbackBusy" @click="promptNote(msg)">
                <i class="bi bi-hand-thumbs-up me-1"></i>{{ t('assistant.feedbackHelpful') }}
              </el-button>
              <el-button size="small" plain :disabled="feedbackBusy" @click="openNote(msg)">
                <i class="bi bi-hand-thumbs-down me-1"></i>{{ t('assistant.feedbackUseless') }}
              </el-button>
            </template>
            <span class="assistant-escalate">
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
            </span>
          </div>

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

        <!-- 等待首个字符：流式下这段空窗很短，但不能什么都不显示 -->
        <div v-if="loading && !streamingStarted" class="assistant-msg is-assistant">
          <div class="assistant-bubble assistant-typing">
            <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
            {{ t('assistant.thinking') }}
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <footer class="assistant-composer">
        <el-input
          v-model="draft"
          type="textarea"
          :rows="2"
          resize="none"
          maxlength="500"
          show-word-limit
          :placeholder="t('assistant.inputPlaceholder')"
          @keydown.enter.exact.prevent="submit()"
        />
        <el-button
          type="primary"
          class="assistant-send"
          :loading="loading"
          :disabled="!draft.trim()"
          @click="submit()"
        >
          {{ t('assistant.send') }}
        </el-button>
      </footer>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Search } from '@element-plus/icons-vue';
import { useI18n } from '@/i18n';
import {
  askAssistantStream,
  deleteAssistantSession,
  escalateSession,
  formatAssistantError,
  getAssistantSession,
  listAssistantSessions,
  sendAssistantFeedback,
} from '@/api/assistant';

const { t } = useI18n();

const PAGE_SIZE = 20;

const sessions = ref([]);
const listLoading = ref(false);
const hasMore = ref(false);
const page = ref(1);
const keyword = ref('');

const currentSessionId = ref(null);
const currentPestName = ref('');
const messages = ref([]);
const draft = ref('');
const loading = ref(false);
const streamingStarted = ref(false);
const scrollBox = ref(null);
const mobileView = ref('list');

const feedbackBusy = ref(false);
const escalating = ref(false);
const escalatedQuestionId = ref(null);

let messageKey = 0;

// 快捷问题：**不能**复用抽屉的 `qXxxText` —— 那些文案是绑定具体病害的
// （"这个病怎么防治？"），而独立页面**没有病害上下文**，问了只会落进降级。
// 所以这里用带作物名的通用问题，由用户点完再自己改成目标作物。
// 文案必须走 i18n：第一版硬编码了中文，英文界面下会显示中文（i18n 检查也不查模板里的裸文案）。
const presets = computed(() => [
  t('assistant.presetLateBlight'),
  t('assistant.presetAppleScab'),
  t('assistant.presetMetalaxyl'),
  t('assistant.presetHealthyCare'),
]);

// 搜索在**前端内存里过滤**，只过滤已加载的那几页。
// 理由：问答历史是个人数据、量级很小（用户自己问过多少次），
// 为一个侧栏再做一个后端搜索接口不划算。代价是"只能搜到已加载的"，
// 所以下面明确用 loadMore 让用户能继续加载。
const filteredSessions = computed(() => {
  const key = keyword.value.trim().toLowerCase();
  if (!key) return sessions.value;
  return sessions.value.filter((item) => (
    (item.title || '').toLowerCase().includes(key)
    || (item.preview || '').toLowerCase().includes(key)
    || (item.pest_name || '').toLowerCase().includes(key)
  ));
});

const paragraphs = (text) => String(text || '').split('\n').filter((line) => line.trim());
const hasPesticideText = (text) => /(\d+%|倍液|稀释|可湿性粉剂|悬浮剂|水分散粒剂|间隔期)/.test(String(text || ''));
const isStreaming = (msg) => loading.value && !msg.messageId;

const degradeHintOf = (reason) => {
  if (!reason) return '';
  // 复用抽屉里那一套提示键（第 198 批：一开始我给本页另造了 6 个重复键，
  // 同一份文案存两份迟早出现"改了页面忘了抽屉"的不一致，已改成共用）
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

const formatTime = (value) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} `
    + `${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

const scrollToBottom = () => nextTick(() => {
  const box = scrollBox.value;
  if (box) box.scrollTop = box.scrollHeight;
});

const loadSessions = async (reset = true) => {
  if (listLoading.value) return;
  listLoading.value = true;
  try {
    const target = reset ? 1 : page.value + 1;
    const data = await listAssistantSessions({ page: target, page_size: PAGE_SIZE });
    const results = data?.results || [];
    sessions.value = reset ? results : sessions.value.concat(results);
    page.value = target;
    hasMore.value = Boolean(data?.has_more);
  } catch (error) {
    ElMessage.error(formatAssistantError(error) || t('assistant.loadFailed'));
  } finally {
    listLoading.value = false;
  }
};

const resetThread = () => {
  currentSessionId.value = null;
  currentPestName.value = '';
  escalatedQuestionId.value = null;
  messages.value = [];
  draft.value = '';
};

const startNewChat = () => {
  resetThread();
  mobileView.value = 'chat';
};

const applySession = (data) => {
  currentSessionId.value = data.id;
  currentPestName.value = data.pest_name || '';
  escalatedQuestionId.value = data.consult_question_id || null;
  messages.value = (data.messages || []).map((item) => ({
    key: ++messageKey,
    role: item.role,
    content: item.content,
    citations: item.citations || [],
    degradeHint: item.degraded ? degradeHintOf(item.degrade_reason) : '',
    // 历史里的回答也可能当初就被截断过 —— 要一直提示，不能只在刚生成时提示
    truncated: Boolean(item.truncated),
    hasPesticide: item.role === 'assistant' && hasPesticideText(item.content),
    // 只有助手消息能评价；历史里的 id 就是真实消息 id
    messageId: item.role === 'assistant' ? item.id : null,
    verdict: item.verdict || '',
    feedbackNote: item.feedback_note || '',
    noteDraft: '',
    showNoteInput: false,
  }));
  scrollToBottom();
};

const openSession = async (item) => {
  mobileView.value = 'chat';
  if (item.id === currentSessionId.value) return;
  listLoading.value = true;
  try {
    applySession(await getAssistantSession(item.id));
  } catch (error) {
    ElMessage.error(formatAssistantError(error) || t('assistant.loadFailed'));
  } finally {
    listLoading.value = false;
  }
};

const removeSession = async (item) => {
  try {
    await ElMessageBox.confirm(t('assistant.deleteConfirm'), t('assistant.deleteSession'), {
      confirmButtonText: t('assistant.deleteSession'),
      cancelButtonText: t('assistant.feedbackCancel'),
      type: 'warning',
    });
  } catch {
    return;   // 用户取消，不是错误
  }
  try {
    await deleteAssistantSession(item.id);
    sessions.value = sessions.value.filter((s) => s.id !== item.id);
    if (currentSessionId.value === item.id) resetThread();
    ElMessage.success(t('assistant.sessionDeleted'));
  } catch (error) {
    ElMessage.error(formatAssistantError(error) || t('assistant.deleteFailed'));
  }
};

const submit = async (presetText) => {
  const question = String(presetText ?? draft.value).trim();
  if (!question || loading.value) return;

  messages.value.push({ key: ++messageKey, role: 'user', content: question, citations: [] });
  draft.value = '';
  loading.value = true;
  streamingStarted.value = false;
  scrollToBottom();

  // 先占一条空气泡，正文随 SSE 的 delta 逐段追加（与抽屉同一策略）
  const placeholder = {
    key: ++messageKey, role: 'assistant', content: '', citations: [],
    degradeHint: '', hasPesticide: false, messageId: null,
    verdict: '', feedbackNote: '', noteDraft: '', showNoteInput: false,
  };
  messages.value.push(placeholder);
  const target = messages.value[messages.value.length - 1];
  let received = false;

  try {
    const data = await askAssistantStream(
      {
        question,
        session_id: currentSessionId.value || undefined,
        // 独立页面没有识别上下文：由**问题文本自己**去检索（后端按词条名匹配）
      },
      {
        onDelta: (text) => {
          received = true;
          streamingStarted.value = true;
          target.content += text;
          scrollToBottom();
        },
      },
    );
    if (data?.session_id) {
      currentSessionId.value = data.session_id;
      // 新会话第一次提问后，把它加进（或刷新）左侧历史
      loadSessions(true);
    }
    if (data?.answer && data.answer !== target.content) target.content = data.answer;
    target.citations = Array.isArray(data?.citations) ? data.citations : [];
    target.degradeHint = data?.degraded ? degradeHintOf(data.degrade_reason) : '';
    target.hasPesticide = hasPesticideText(target.content);
    target.messageId = data?.message_id || null;
    // 第 204 批：回答被长度上限截断时如实提示（否则用户看到的是"半句话 + 好像答完了"）
    target.truncated = Boolean(data?.truncated);
  } catch (error) {
    const index = messages.value.indexOf(target);
    if (index >= 0) messages.value.splice(index, 1);
    ElMessage.error(formatAssistantError(error));
  } finally {
    if (!received && target.content) target.content = target.content.trim();
    loading.value = false;
    scrollToBottom();
  }
};

// 反馈：与抽屉同一套接口与语义（最后一次评价为准）
const openNote = (msg) => {
  msg.noteDraft = msg.feedbackNote || '';
  msg.showNoteInput = true;
};
const promptNote = (msg) => rate(msg, 'helpful');

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

const escalate = async (msg) => {
  if (escalating.value || !currentSessionId.value) return;
  escalating.value = true;
  try {
    const data = await escalateSession(currentSessionId.value, msg.feedbackNote || '');
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

onMounted(async () => {
  await loadSessions(true);
  // 窄屏默认停在列表；宽屏直接进对话（`mobileView` 只在窄屏生效，见 CSS）
  if (window.matchMedia('(max-width: 768px)').matches) mobileView.value = 'list';
  else mobileView.value = 'chat';
});
</script>

<style scoped>
.assistant-page {
  display: flex;
  gap: 1rem;
  height: calc(100vh - 140px);
  min-height: 520px;
  /* ⚠️ 第 207 批：必须**明确撑满父级**，不能靠 `width: auto`。
     父级 `main.main-content` 是 flex 容器，本元素是它的 flex 项 ——
     `width: auto` 在 flex 项上会被解析成 **fit-content（收缩到内容宽度）**，
     于是整页宽度随"当前这条回答有多宽"起伏。实测：

       生成中 740px → 生成后 1901px（每 50ms 采样，2.6s 内一路长上去）

     表现就是用户看到的"提问框和回答框大小不统一" ——
     其实是**整个页面容器**被内容顶成了不同宽度，两条气泡的固有宽度不同而已。
     `min-width: 0` 是 flex 项的配套写法：允许它在窄屏下正常收缩而不撑破父级。 */
  width: 100%;
  min-width: 0;
}

/* ── 左侧历史 ───────────────────────────────────────────── */
.assistant-side {
  width: 288px;
  flex: 0 0 288px;
  display: flex;
  flex-direction: column;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
}

.assistant-side-head { padding: 0.75rem; border-bottom: 1px solid #f1f3f5; }
.assistant-side-search { padding: 0.6rem 0.75rem; border-bottom: 1px solid #f1f3f5; }
.assistant-side-list { flex: 1; overflow-y: auto; padding: 0.4rem; }
.assistant-side-empty { padding: 1.5rem 0.75rem; text-align: center; color: #9ca3af; font-size: 0.85rem; }
.assistant-side-more { text-align: center; padding: 0.4rem; }

.assistant-side-item {
  position: relative;
  padding: 0.55rem 0.65rem;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}
.assistant-side-item:hover { background: #f8f9fa; }
.assistant-side-item.is-active { background: #eef6f0; }

.assistant-side-title {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.86rem;
  font-weight: 500;
  color: #1f2937;
}
/* ⚠️ 标题必须**自己**是省略号的容器，且给 tag 留出空间。
   第一版把 `text-truncate` 加在 span 上、父级是 flex —— 结果标题被截断后
   日期挤到了同一行，三行信息糊成一片（截图里才看出来）。
   flex 子项要能收缩：`min-width: 0` 是必需的。 */
.assistant-side-name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.assistant-side-title :deep(.el-tag) { flex: 0 0 auto; }
.assistant-side-meta { font-size: 0.72rem; color: #9ca3af; margin-top: 0.15rem; }
.assistant-side-preview {
  font-size: 0.75rem;
  color: #6b7280;
  margin-top: 0.2rem;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.assistant-side-del {
  position: absolute;
  top: 0.4rem;
  right: 0.35rem;
  opacity: 0;
  transition: opacity 0.15s;
}
.assistant-side-item:hover .assistant-side-del { opacity: 1; }

/* ── 右侧对话 ───────────────────────────────────────────── */
.assistant-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
}

.assistant-main-head {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #f1f3f5;
}
.assistant-main-title h1 { font-size: 1.02rem; margin: 0; color: #1f2937; }
.assistant-main-title p { font-size: 0.76rem; margin: 0.1rem 0 0; color: #9ca3af; }
.assistant-context { margin-left: auto; font-size: 0.78rem; color: #2f6b4f; }
.assistant-back { display: none; }

.assistant-thread { flex: 1; overflow-y: auto; padding: 1rem; }

.assistant-welcome { text-align: center; padding: 3rem 1rem; color: #6b7280; }
.assistant-welcome-icon { font-size: 2.4rem; color: #b9d4c4; }
.assistant-welcome h2 { font-size: 1.05rem; margin: 0.6rem 0 0.4rem; color: #374151; }
.assistant-welcome p { font-size: 0.85rem; max-width: 34rem; margin: 0 auto; line-height: 1.7; }
.assistant-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: center;
  margin-top: 1.1rem;
}

.assistant-msg { margin-bottom: 1.1rem; display: flex; flex-direction: column; }
.assistant-msg.is-user { align-items: flex-end; }
.assistant-msg.is-assistant { align-items: flex-start; }

.assistant-bubble {
  /* ⚠️ 第 203 批：**固定宽度**，不再由内容决定。
     原来是 `display: inline-block; max-width: 78%` —— 那是"收缩到内容宽度"，
     于是一条 13 字的回答占 46%、50 字的占 73%（实测，对话区 462px），
     每条消息宽度都不一样，整屏看着参差不齐。
     现在固定 88%，靠**左右对齐**区分提问与回答（12% 的空档在 462px 下有 55px，
     足够看出方向，又不至于像两块通栏色块）。
     `box-sizing: border-box` 是必需的：否则 width 之外还要加上左右 padding，
     实际渲染会超过 88%。 */
  width: 88%;
  box-sizing: border-box;
  max-width: 100%;
  padding: 0.65rem 0.85rem;
  border-radius: 10px;
  font-size: 0.9rem;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}
.assistant-msg.is-user .assistant-bubble { background: #2f6b4f; color: #fff; }
.assistant-msg.is-assistant .assistant-bubble { background: #f5f7f6; color: #1f2937; }
.assistant-bubble p { margin: 0 0 0.5rem; }
.assistant-bubble p:last-child { margin-bottom: 0; }
.assistant-typing { color: #6b7280; font-size: 0.85rem; }

.assistant-disclaimer {
  margin-top: 0.5rem !important;
  font-size: 0.75rem;
  color: #8a6d3b;
  border-top: 1px dashed #e5e7eb;
  padding-top: 0.4rem;
}

.assistant-cites {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.4rem;
  /* 与气泡同宽（第 203 批）：原来 78% 是按"气泡最多 78%"定的，
     气泡改成固定 88% 后，引用会比气泡窄一截、左边缘对不齐。 */
  width: 88%;
  box-sizing: border-box;
}
.assistant-cites-label { font-size: 0.72rem; color: #9ca3af; }
.assistant-cite {
  font-size: 0.75rem;
  color: #2f6b4f;
  background: #eef6f0;
  border-radius: 999px;
  padding: 0.1rem 0.55rem;
  text-decoration: none;
}
.assistant-cite:hover { background: #dcece2; }

.assistant-degrade-hint { font-size: 0.75rem; color: #8a6d3b; margin: 0.35rem 0 0; }
.assistant-truncated {
  font-size: 0.75rem;
  color: #b45309;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 6px;
  padding: 0.3rem 0.5rem;
  margin: 0.35rem 0 0;
  max-width: 88%;
}

.assistant-feedback {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  margin-top: 0.45rem;
}
.assistant-feedback-done { font-size: 0.78rem; color: #2f6b4f; }
.assistant-feedback-done em { font-style: normal; color: #8a6d3b; }
.assistant-escalate { margin-left: auto; }
.assistant-escalate-done { font-size: 0.75rem; color: #6b7280; }

.assistant-note {
  margin-top: 0.5rem;
  padding: 0.6rem 0.7rem;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  width: 88%;
  box-sizing: border-box;
}
.assistant-note-label { font-size: 0.78rem; color: #4b5563; margin-bottom: 0.35rem; }
.assistant-note-actions { display: flex; justify-content: flex-end; gap: 0.4rem; margin-top: 0.45rem; }

.assistant-composer {
  display: flex;
  align-items: flex-end;
  gap: 0.6rem;
  padding: 0.75rem 1rem;
  border-top: 1px solid #f1f3f5;
}
.assistant-send { flex: 0 0 auto; }

/* ── 窄屏：列表与对话二选一（不是并排）─────────────── */
@media (max-width: 768px) {
  .assistant-page { height: calc(100vh - 180px); gap: 0; }
  .assistant-side {
    width: 100%;
    flex: 1 1 100%;
    border-radius: 12px;
  }
  .assistant-side.is-hidden-mobile { display: none; }
  .assistant-main.is-hidden-mobile { display: none; }
  .assistant-back { display: inline-flex; }
  /* ⚠️ 第 203 批：气泡改成固定宽度后，这里必须**改 width 而不是 max-width** ——
     原来写的是 `max-width: 92%`，在固定宽度下等于没生效（宽度还是 88%）。
     窄屏本就该让气泡更宽一些。 */
  .assistant-bubble { width: 92%; }
  .assistant-cites, .assistant-note { width: 92%; }
}
</style>
