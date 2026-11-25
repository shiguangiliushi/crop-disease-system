<!--
  系统助手（管理端运维侧）—— 「系统」页的第四个页签
  ============================================================================
  与农户端的 `/assistant`（RAG 知识问答）是**两个东西**：
    · 那边答"病害怎么治"，语料是病害词库；
    · 这边答"系统现在什么状态、该跑什么命令"，数据来自八个**只读**工具（健康 / 快照 /
      审计 / 运行数据 / docs / 白名单命令）；
    · 第 423 批起还能执行三个**可逆**写（样本确认 / 状态流转 / 回复反馈）——
      网关全在后端（`ops/actions.py` 的五道闸门），这里不做任何判断。
  页面本身不含任何业务判断：降级与否、数字是否校验过、调了哪些工具、这次到底改没改成，
  全部由后端返回，这里只负责展示 —— 前端再算一遍必然与后端长歪（本项目反复栽过的坑）。
-->
<template>
  <div class="ops-assistant">
    <header class="ops-head">
      <span class="ops-head-icon"><i class="fas fa-comments"></i></span>
      <div>
        <h2>{{ t('opsAssistant.title') }}</h2>
        <p>{{ t('opsAssistant.subtitle') }}</p>
      </div>
    </header>

    <!-- 权限边界写在页面上，而不是只写在注释里：用的人要知道它**能改什么、不能改什么**。
         第 423 批之前这里写的是"只读"—— 现在它也能执行可逆写（每写一次都留审计），
         文案跟着改；改的是同一个 key（`permissionNote`），别改回 `readonlyNote`。 -->
    <el-alert type="info" :closable="false" show-icon class="ops-note">
      {{ t('opsAssistant.permissionNote') }}
    </el-alert>

    <!--
      观测（E）：`degraded` / `verified` / `tool_calls` 一直落在 OpsAssistantTurn 里，
      但以前没有任何界面在读 —— 问的人在同一个页面就能看到"最近答得好不好"，
      不用再开一个后台页，也不用进 Django admin 一条条翻。
    -->
    <el-collapse v-model="statsOpen" class="ops-stats">
      <el-collapse-item name="stats">
        <template #title>
          <span class="ops-stats-title">
            <i class="fas fa-chart-simple"></i> {{ t('opsAssistant.statsTitle') }}
          </span>
        </template>

        <div class="ops-stats-head">
          <span class="ops-dim">{{ t('opsAssistant.statsRangeHint') }}</span>
          <el-select v-model="statsDays" size="small" style="width: 108px" @change="loadStats">
            <el-option :value="7" :label="t('opsAssistant.statsDays7')" />
            <el-option :value="14" :label="t('opsAssistant.statsDays14')" />
            <el-option :value="30" :label="t('opsAssistant.statsDays30')" />
          </el-select>
        </div>

        <p v-if="statsLoading" class="ops-dim">{{ t('opsAssistant.thinking') }}</p>
        <template v-else>
          <div class="ops-stats-grid">
            <div class="ops-stat">
              <strong>{{ stats.totals.turns ?? 0 }}</strong>
              <span>{{ t('opsAssistant.statsTurns') }}</span>
            </div>
            <div class="ops-stat">
              <strong>{{ pct(stats.totals.degraded_rate) }}</strong>
              <span>{{ t('opsAssistant.statsDegraded') }}</span>
            </div>
            <div class="ops-stat">
              <strong>{{ pct(stats.totals.unverified_rate) }}</strong>
              <span>{{ t('opsAssistant.statsUnverified') }}</span>
            </div>
            <div class="ops-stat">
              <strong>{{ stats.totals.avg_latency_ms ?? 0 }} ms</strong>
              <span>{{ t('opsAssistant.statsLatency') }}</span>
            </div>
            <!-- 第 427 批起接口就有这个数（待确认不算降级），第 428 批才显示出来 -->
            <div class="ops-stat">
              <strong>{{ stats.totals.pending_confirmations ?? 0 }}</strong>
              <span>{{ t('opsAssistant.statsPending') }}</span>
            </div>
          </div>

          <div class="ops-stats-cols">
            <div>
              <h4>{{ t('opsAssistant.statsIntents') }}</h4>
              <ul v-if="stats.by_intent.length">
                <li v-for="row in stats.by_intent" :key="row.intent">
                  <code>{{ row.intent }}</code> {{ row.count }}
                  <span v-if="row.degraded" class="ops-dim">· ⚠ {{ row.degraded }}</span>
                </li>
              </ul>
              <p v-else class="ops-dim">{{ t('opsAssistant.statsEmpty') }}</p>
            </div>
            <div>
              <h4>{{ t('opsAssistant.statsToolFailures') }}</h4>
              <ul v-if="stats.tool_failures.length">
                <li v-for="row in stats.tool_failures" :key="row.tool">
                  <code>{{ row.tool }}</code> × {{ row.count }}
                </li>
              </ul>
              <p v-else class="ops-dim">{{ t('opsAssistant.statsEmpty') }}</p>
            </div>
          </div>

          <div v-if="stats.recent_unverified.length" class="ops-stats-unverified">
            <h4>{{ t('opsAssistant.statsRecentUnverified') }}</h4>
            <ul>
              <li v-for="row in stats.recent_unverified" :key="row.id">
                {{ row.question }}
                <span class="ops-dim">{{ row.degrade_reason || '—' }}</span>
              </li>
            </ul>
          </div>
        </template>
      </el-collapse-item>
    </el-collapse>

    <!--
      待确认队列（第 428 批）
      ------------------------------------------------------------------
      第 426 批的确认按钮只长在"提议它的那条对话"里，而对话在 store 里 —— **刷新就没了**。
      这一块读的是服务端的 `OpsPendingWrite`：刷新后仍能看见"有一条删反馈卡在待确认"，
      并就地确认或取消。只显示自己、未过期的记录（后端负责这两条口径）。
    -->
    <el-collapse v-if="opsStore.openPending.length" v-model="pendingOpen" class="ops-pending">
      <el-collapse-item name="pending">
        <template #title>
          <span class="ops-pending-title">
            <i class="fas fa-hourglass-half"></i>
            {{ t('opsAssistant.pendingTitle') }}（{{ opsStore.openPending.length }}）
          </span>
        </template>

        <ul class="ops-pending-list">
          <li v-for="row in opsStore.openPending" :key="row.token" class="ops-pending-row">
            <div class="ops-pending-facts">
              <strong>{{ row.label || row.action }}</strong>
              <span v-if="row.target">{{ row.target }}</span>
              <span class="ops-dim">{{ t('opsAssistant.pendingLeft', { n: leftMinutes(row) }) }}</span>
            </div>
            <div class="ops-pending-actions">
              <el-button
                type="danger"
                size="small"
                :loading="busyToken === row.token"
                :disabled="Boolean(busyToken)"
                @click="decideRow(row, 'confirm')"
              >
                {{ t('opsAssistant.confirmRun') }}
              </el-button>
              <el-button
                size="small"
                :disabled="Boolean(busyToken)"
                @click="decideRow(row, 'cancel')"
              >
                {{ t('opsAssistant.confirmCancel') }}
              </el-button>
            </div>
            <p v-if="rowResults[row.token]" class="ops-pending-result">
              {{ rowResults[row.token] }}
            </p>
          </li>
        </ul>
        <p class="ops-dim">{{ t('opsAssistant.pendingHint') }}</p>
      </el-collapse-item>
    </el-collapse>

    <div class="ops-thread">
      <el-empty v-if="!opsStore.turns.length" :description="t('opsAssistant.emptyHint')" />

      <article v-for="(turn, index) in opsStore.turns" :key="index" class="ops-turn">
        <p class="ops-question">
          <i class="fas fa-circle-question"></i> {{ turn.question }}
        </p>
        <div class="ops-answer">
          <!-- ⚠️ 与农户侧同一套受控渲染：模型习惯写 `**加粗**`，纯文本渲染会把星号
               原样显示（用户反馈过"回答为什么会出现 `**`"）。这里**只解析加粗一种标记**
               （`utils/assistantText.js`），片段走文本插值、标签名写死在模板里，
               **绝不用 `v-html`** —— 模型输出是不可信输入，没有 HTML 注入面。 -->
          <div v-if="turn.answer" class="ops-text">
            <p v-for="(segments, index) in answerParagraphs(turn.answer)" :key="index">
              <template v-for="(segment, position) in segments" :key="position">
                <strong v-if="segment.bold">{{ segment.text }}</strong>
                <template v-else>{{ segment.text }}</template>
              </template>
            </p>
          </div>
          <p v-else-if="turn.failed" class="ops-text is-failed">{{ t('opsAssistant.failed') }}</p>
          <p v-else class="ops-text is-waiting">{{ t('opsAssistant.thinking') }}</p>

          <!--
            不可逆写的二次确认（第 426 批）
            ------------------------------------------------------------------
            `turn.pending` 非空 = 后端**只落了一条待确认记录，没有执行**；
            真正的执行只发生在下面这个按钮上（`/ops/confirm/`，不经过模型）。
            凭据一次性：一旦有 `pendingResult`（执行/取消/过期/已被处理），
            按钮就不再出现 —— 留着它只会让人重复点、再看到"已经处理过了"。
          -->
          <div v-if="turn.pending" class="ops-confirm">
            <p class="ops-confirm-head">
              <i class="fas fa-triangle-exclamation"></i> {{ t('opsAssistant.confirmTitle') }}
            </p>
            <ul class="ops-confirm-facts">
              <li>
                <span>{{ t('opsAssistant.confirmAction') }}</span>
                {{ turn.pending.label || turn.pending.action || '—' }}
              </li>
              <li v-if="turn.pending.target">
                <span>{{ t('opsAssistant.confirmTarget') }}</span>{{ turn.pending.target }}
              </li>
              <li v-if="(turn.pending.changes || []).length">
                <span>{{ t('opsAssistant.confirmChanges') }}</span>{{ changeText(turn.pending.changes) }}
              </li>
            </ul>
            <p class="ops-confirm-warn">{{ t('opsAssistant.confirmIrreversible') }}</p>

            <div v-if="!turn.pendingResult" class="ops-confirm-actions">
              <el-button
                type="danger"
                size="small"
                :loading="turn.confirming"
                :disabled="turn.confirming"
                @click="decide(turn, 'confirm')"
              >
                {{ t('opsAssistant.confirmRun') }}
              </el-button>
              <el-button size="small" :disabled="turn.confirming" @click="decide(turn, 'cancel')">
                {{ t('opsAssistant.confirmCancel') }}
              </el-button>
            </div>
            <p
              v-else
              class="ops-confirm-result"
              :class="turn.pendingResult.ok ? 'is-ok' : 'is-failed'"
            >
              {{ confirmResultText(turn.pendingResult) }}
            </p>
            <!-- 请求本身失败（网络 / 400 / 403）：不是"后端拒绝了这次确认"，要分开显示 -->
            <p v-if="turn.pendingError" class="ops-confirm-result is-failed">
              {{ formatApiError(turn.pendingError, t('opsAssistant.confirmFailed')) }}
            </p>
          </div>
          <div class="ops-meta">
            <el-tag v-if="turn.intent" size="small" effect="plain">{{ turn.intent }}</el-tag>
            <el-tag
              v-for="tool in turn.tools || []"
              :key="tool.name"
              size="small"
              effect="plain"
              :type="tool.ok ? 'success' : 'danger'"
            >
              {{ tool.name }} · {{ tool.ms }} ms
            </el-tag>
            <!-- `degraded` 标签在"待确认"时**不显示**：那不是降级，是等管理员点确认 -->
            <el-tag v-if="turn.degraded && !turn.pending" size="small" type="warning" effect="plain">
              {{ t('opsAssistant.degradedLabel') }}{{ turn.degrade_reason ? ` · ${turn.degrade_reason}` : '' }}
            </el-tag>
            <el-tag v-if="turn.verified === false" size="small" type="danger" effect="plain">
              {{ t('opsAssistant.unverifiedLabel') }}
            </el-tag>
          </div>

          <el-collapse v-if="(turn.evidence || []).length" class="ops-evidence">
            <el-collapse-item
              :title="`${t('opsAssistant.evidenceLabel')}（${turn.evidence.length}）`"
              :name="index"
            >
              <ul class="ops-evidence-list">
                <li v-for="(item, position) in turn.evidence" :key="position">
                  <p class="ops-evidence-title">
                    {{ item.title }} <code>{{ item.source }}</code>
                  </p>
                  <p
                    v-for="(line, lineIndex) in item.lines || []"
                    :key="lineIndex"
                    class="ops-evidence-line"
                  >
                    {{ line }}
                  </p>
                </li>
              </ul>
            </el-collapse-item>
          </el-collapse>
        </div>
      </article>
    </div>

    <div class="ops-composer">
      <el-input
        v-model="question"
        type="textarea"
        :rows="3"
        maxlength="2000"
        show-word-limit
        :placeholder="t('opsAssistant.placeholder')"
        :disabled="opsStore.loading"
        @keydown.ctrl.enter.prevent="submit"
      />
      <div class="ops-actions">
        <el-button type="primary" :loading="opsStore.loading" @click="submit">
          <i class="fas fa-paper-plane"></i> {{ t('opsAssistant.ask') }}
        </el-button>
        <el-button v-if="opsStore.turns.length" plain :disabled="opsStore.loading" @click="reset">
          {{ t('opsAssistant.clear') }}
        </el-button>
      </div>
      <div class="ops-examples">
        <span class="ops-examples-label">{{ t('opsAssistant.examplesLabel') }}</span>
        <el-button
          v-for="(example, index) in examples"
          :key="index"
          link
          size="small"
          :disabled="opsStore.loading"
          @click="askExample(example)"
        >
          {{ example }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { fetchOpsAssistantStats } from '@/api/opsAssistant';
import { formatApiError } from '@/api/http';
import { useI18n } from '@/i18n';
import { parseAnswerParagraphs } from '@/utils/assistantText';
// 对话状态放 store：这个页签由 Hub 用 `v-if` 挂载，**切页签会被卸载** ——
// 状态留在组件里就会"切走再回来内容没了"（第 414 批用户实测）。
import { useOpsAssistantStore } from '@/stores/opsAssistant';

const { t, locale } = useI18n();
const opsStore = useOpsAssistantStore();

/** 回答分段（与农户侧共用同一个解析器；为什么不用逐行版见模板里那段注释） */
const answerParagraphs = parseAnswerParagraphs;

const question = ref('');
/** 界面语言 → 回答语言（'en' / 'zh'）。切英文后**新问的问题**才是英文，
 *  已经答过的历史保持原样 —— 那是当时的记录，不该被重写。 */
const answerLang = computed(() => (String(locale.value).startsWith('en') ? 'en' : 'zh'));

/* ── 观测（E） ─────────────────────────────────────────────────────── */
const stats = ref({
  totals: {}, by_intent: [], tool_failures: [], recent_unverified: [],
});
const statsDays = ref(7);
const statsOpen = ref([]);
const statsLoading = ref(false);

async function loadStats() {
  statsLoading.value = true;
  try {
    stats.value = await fetchOpsAssistantStats({
      days: statsDays.value, lang: answerLang.value,
    });
  } catch {
    // 看板失败**不打断问答**：它是旁路信息，报错弹窗反而挡着用的人
  } finally {
    statsLoading.value = false;
  }
}

/** 比率 → 百分比；后端在没有数据时给的是 null，这里显示 "—" 而不是 0% */
function pct(value) {
  return typeof value === 'number' ? `${Math.round(value * 1000) / 10}%` : '—';
}

// 进这一页就取好两样东西：看板（一次只读聚合）与待确认队列（刷新后靠它找回凭据）
onMounted(() => {
  loadStats();
  opsStore.loadPending();
});

const examples = computed(() => [
  t('opsAssistant.example1'),
  t('opsAssistant.example2'),
  t('opsAssistant.example3'),
  t('opsAssistant.example4'),
]);

async function submit() {
  const text = question.value.trim();
  if (!text || opsStore.loading) return;

  question.value = '';
  try {
    await opsStore.ask(text, { lang: answerLang.value });
  } catch (error) {
    // 失败（400 / 403 / 429 / 网络）才走这里；`degraded=true` 是 200，不算失败
    ElMessage.error(formatApiError(error, t('opsAssistant.failed')));
    question.value = text;   // 把问题放回去，免得用户重打
  } finally {
    // 刚问完，看板数字该动了；面板没展开就不去打扰后端
    if (statsOpen.value.length) loadStats();
    // 第 428 批：这一轮可能刚提出一条待确认 —— 让它同时出现在上面的队列里
    opsStore.loadPending();
  }
}

function askExample(example) {
  question.value = example;
  submit();
}

/* ── 不可逆写的确认 / 取消（第 426 批） ─────────────────────────────── */

/**
 * 点"确认执行"或"取消"。**这里不发自然语言**，只发 `confirm` / `cancel` ——
 * 后端也只认这两个词（`ops/pending.CONFIRM_WORDS`）。让模型去解析"他说的是确认吗"
 * 正是二次确认要防的那件事（模型可以确认自己刚提的议）。
 */
async function decide(turn, decision) {
  try {
    await opsStore.confirm(turn, decision);
  } catch {
    // 真正的请求失败：错误已经写进 `turn.pendingError`，卡片里就地显示，不再弹一个
  }
}

/**
 * 确认结果 → 一句人读的话。
 *
 * 为什么**按 `status` / `reason` 映射**而不是直接显示后端的 `answer`：
 * 后端失败文案是中文的（`pending.REASON_TEXT`），英文界面下照搬会中英混排。
 * 执行成功时 `answer` 是 lang-aware 的确定性摘要，可以带出来。
 */
function confirmResultText(result) {
  if (!result) return '';
  if (result.ok) {
    const detail = String(result.answer || '').trim();
    return detail
      ? `${t('opsAssistant.confirmExecuted')} · ${detail}`
      : t('opsAssistant.confirmExecuted');
  }
  const reason = String(result.reason || '');
  if (result.status === 'cancelled') return t('opsAssistant.confirmCancelled');
  if (reason === 'expired' || result.status === 'expired') return t('opsAssistant.confirmExpired');
  if (reason === 'consumed') return t('opsAssistant.confirmAlreadyDone');
  if (reason === 'not_found') return t('opsAssistant.confirmNotFound');
  const detail = String(result.answer || '').trim();
  return detail
    ? `${t('opsAssistant.confirmNotRun')}：${detail}`
    : t('opsAssistant.confirmNotRun');
}

/**
 * "会改动哪些字段" → 人读文本。
 *
 * 后端的 `changes` 是**字段名/标记**（`deleted` / `admin_reply` / `status`），
 * 直接把 `deleted` 摆在界面上等于把内部标识符露给管理员。只对已知的几个给中文，
 * 其余原样显示 —— **不翻译未知值**：翻错了比露字段名更糟（比如把"删除"说成"修改"）。
 */
function changeText(changes) {
  const labels = { deleted: t('opsAssistant.confirmChangeDeleted') };
  return (changes || []).map((key) => labels[key] || key).join('、');
}

/* ── 待确认队列（第 428 批） ───────────────────────────────────────── */
const pendingOpen = ref(['pending']);
/** 正在处理的那一行（凭据）；同一时刻只让点一个，避免同一 token 连点两次 */
const busyToken = ref('');
/** token → 结果文本。用整体替换的方式更新，Vue 才能追踪到新键 */
const rowResults = ref({});

/** 剩余时间（分钟，向上取整）：过期与否以后端为准，这里只负责好看 */
function leftMinutes(row) {
  const seconds = Number(row?.seconds_left ?? 0);
  return Math.max(0, Math.ceil(seconds / 60));
}

/**
 * 在"待确认"列表里确认或取消一行。
 *
 * 与对话里那张卡走同一个接口、同一套说法（只发 `confirm` / `cancel`）；
 * 结果写回**这一行**（不是整页），因为失败原因可能只是这一条过期了。
 */
async function decideRow(row, decision) {
  if (busyToken.value) return;
  busyToken.value = row.token;
  try {
    const result = await opsStore.confirmToken(row.token, decision);
    rowResults.value = { ...rowResults.value, [row.token]: confirmResultText(result) };
    if (statsOpen.value.length) loadStats();
  } catch (error) {
    rowResults.value = {
      ...rowResults.value,
      [row.token]: formatApiError(error, t('opsAssistant.confirmFailed')),
    };
  } finally {
    busyToken.value = '';
  }
}

function reset() {
  opsStore.reset();
}
</script>

<style scoped>
.ops-assistant {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px;
}

.ops-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ops-head-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.ops-head h2 {
  margin: 0;
  font-size: 17px;
}

.ops-head p {
  margin: 2px 0 0;
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
}

.ops-note {
  border-radius: 10px;
}

/* ── 观测（E） ───────────────────────────────────────────────────── */
.ops-stats {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 0 12px;
}

.ops-stats-title {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-weight: 600;
}

.ops-stats-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.ops-stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.ops-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  border-radius: 9px;
  background: var(--el-fill-color-lighter);
}

.ops-stat strong {
  font-size: 18px;
}

.ops-stat span {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.ops-stats-cols {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 12px;
}

.ops-stats-cols h4,
.ops-stats-unverified h4 {
  margin: 0 0 6px;
  font-size: 12.5px;
  color: var(--el-text-color-regular);
}

.ops-stats-cols ul,
.ops-stats-unverified ul {
  margin: 0;
  padding-left: 18px;
  font-size: 12.5px;
  line-height: 1.7;
}

.ops-stats-unverified {
  margin-top: 12px;
}

.ops-dim {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

@media (max-width: 720px) {
  .ops-stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .ops-stats-cols {
    grid-template-columns: 1fr;
  }
}

/* 待确认队列（第 428 批）：比对话更"待办"，所以用 warning 色系且不折叠进对话里 */
.ops-pending {
  margin-top: 12px;
}

.ops-pending-title {
  font-weight: 600;
  color: var(--el-color-warning);
}

.ops-pending-title i {
  margin-right: 6px;
}

.ops-pending-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}

.ops-pending-row {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 9px;
  padding: 8px 10px;
  background: var(--el-bg-color);
}

.ops-pending-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
  font-size: 13px;
}

.ops-pending-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.ops-pending-result {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
}

.ops-thread {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 120px;
}

.ops-turn {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 12px 14px;
  background: var(--el-bg-color);
}

.ops-question {
  margin: 0 0 8px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.ops-question i {
  color: var(--el-color-primary);
  margin-right: 6px;
}

.ops-text {
  margin: 0;
  padding: 10px 12px;
  border-radius: 9px;
  background: var(--el-fill-color-lighter);
  font-size: 13px;
  line-height: 1.7;
  /* 段落之间的空行由 <p> 表现；段内单换行靠 pre-wrap 显示（与农户侧同一套语义） */
  white-space: pre-wrap;
  word-break: break-word;
}

.ops-text p {
  margin: 0 0 8px;
}

.ops-text p:last-child {
  margin-bottom: 0;
}

.ops-text.is-failed {
  color: var(--el-color-danger);
}

.ops-text.is-waiting {
  color: var(--el-text-color-secondary);
  font-style: italic;
}

.ops-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

/* 不可逆写的二次确认卡（第 426 批）—— 用 danger 色系，和"降级提示"区分开：
   降级是"答案可能不可信"，这里是"马上要删东西了"，两者的分量不一样。 */
.ops-confirm {
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid var(--el-color-danger-light-5);
  border-radius: 9px;
  background: var(--el-color-danger-light-9);
}

.ops-confirm-head {
  margin: 0 0 6px;
  font-weight: 600;
  color: var(--el-color-danger);
}

.ops-confirm-head i {
  margin-right: 6px;
}

.ops-confirm-facts {
  margin: 0;
  padding-left: 0;
  list-style: none;
  font-size: 13px;
  line-height: 1.8;
}

.ops-confirm-facts span {
  display: inline-block;
  min-width: 4em;
  margin-right: 8px;
  color: var(--el-text-color-secondary);
}

.ops-confirm-warn {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--el-color-danger);
}

.ops-confirm-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.ops-confirm-result {
  margin: 8px 0 0;
  font-size: 13px;
  white-space: pre-wrap;
}

.ops-confirm-result.is-ok {
  color: var(--el-color-success);
}

.ops-confirm-result.is-failed {
  color: var(--el-color-danger);
}

.ops-evidence {
  margin-top: 10px;
}

.ops-evidence-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12.5px;
  line-height: 1.7;
}

.ops-evidence-title {
  margin: 0 0 2px;
  font-weight: 600;
}

.ops-evidence-title code {
  font-weight: 400;
  color: var(--el-text-color-secondary);
}

.ops-evidence-line {
  margin: 0 0 4px;
  color: var(--el-text-color-regular);
  word-break: break-all;
}

.ops-composer {
  position: sticky;
  bottom: 0;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-bg-color-page);
}

.ops-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.ops-examples {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  margin-top: 8px;
}

.ops-examples-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
