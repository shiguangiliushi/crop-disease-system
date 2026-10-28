<template>
  <div class="assistant-admin tinted-page">
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-robot"></i></span>
        <div>
          <h1>{{ t('assistantAdmin.title') }}</h1>
          <p>{{ t('assistantAdmin.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-select v-model="days" style="width: 140px" :disabled="loading" @change="load">
          <el-option :value="7" :label="t('assistantAdmin.range7')" />
          <el-option :value="14" :label="t('assistantAdmin.range14')" />
          <el-option :value="30" :label="t('assistantAdmin.range30')" />
        </el-select>
        <el-button plain :loading="loading" @click="load">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
      </div>
    </header>

    <!-- 只读声明：写在页面上，而不是只写在代码注释里 -->
    <el-alert type="info" :closable="false" show-icon class="readonly-note">
      {{ t('assistantAdmin.readonlyNote') }}
    </el-alert>

    <p v-if="errorMessage" class="load-error">
      <i class="fas fa-triangle-exclamation"></i> {{ errorMessage }}
    </p>

    <!-- 一、四个关键数字（一屏先回答"现在好不好"） -->
    <div class="stat-grid">
      <div class="stat-card">
        <span class="stat-label">{{ t('assistantAdmin.statQuestions') }}</span>
        <strong class="stat-value">{{ totals.questions }}</strong>
        <span class="stat-sub">{{ t('assistantAdmin.statAnswers') }} {{ totals.answers }}</span>
      </div>
      <div class="stat-card" :class="{ 'is-warn': totals.degraded_rate > 0.3 }">
        <span class="stat-label">{{ t('assistantAdmin.statDegraded') }}</span>
        <strong class="stat-value">{{ percent(totals.degraded_rate) }}</strong>
        <span class="stat-sub">
          {{ t('assistantAdmin.degradedHint', { count: totals.degraded }) }}
        </span>
      </div>
      <div class="stat-card">
        <span class="stat-label">{{ t('assistantAdmin.statNoSource') }}</span>
        <strong class="stat-value">{{ totals.no_source }}</strong>
        <span class="stat-sub">
          {{ t('assistantAdmin.statLimited', { rate: totals.rate_limited, full: totals.session_full }) }}
        </span>
      </div>
      <div class="stat-card">
        <span class="stat-label">{{ t('assistantAdmin.statUseful') }}</span>
        <strong class="stat-value">{{ percent(totals.useless_rate) }}</strong>
        <span class="stat-sub">
          {{ t('assistantAdmin.usefulHint', { helpful: totals.helpful, useless: totals.useless }) }}
        </span>
      </div>
      <div class="stat-card">
        <span class="stat-label">{{ t('assistantAdmin.statLatency') }}</span>
        <strong class="stat-value">{{ totals.avg_latency_ms }}</strong>
        <span class="stat-sub">{{ t('assistantAdmin.latencyUnit') }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">{{ t('assistantAdmin.statTokens') }}</span>
        <strong class="stat-value">{{ tokenTotal }}</strong>
        <span class="stat-sub">
          {{ t('assistantAdmin.tokenHint', {
            prompt: totals.tokens.prompt, completion: totals.tokens.completion,
          }) }}
        </span>
      </div>
    </div>

    <!-- 二、趋势：纯 CSS 柱状（不引图表库，管理端这页不需要交互） -->
    <!-- 回答语言分布：原来挂在「被引用最多的词条」标题右边，读起来像是在说引用，
         现在单独一行并标清是"哪种界面语言下的回答有多少条"。 -->
    <div v-if="langRows.length" class="lang-line">
      <span class="lang-label">{{ t('assistantAdmin.langTitle') }}</span>
      <el-tag v-for="row in langRows" :key="row.key" size="small" effect="plain">
        {{ row.label }} {{ row.count }}
      </el-tag>
    </div>

    <section class="panel">
      <header class="panel-head">
        <h2>{{ t('assistantAdmin.trendTitle') }}</h2>
        <div class="legend">
          <span class="legend-item"><i class="dot dot--q"></i>{{ t('assistantAdmin.legendQuestions') }}</span>
          <span class="legend-item"><i class="dot dot--d"></i>{{ t('assistantAdmin.legendDegraded') }}</span>
          <span class="legend-item"><i class="dot dot--n"></i>{{ t('assistantAdmin.legendNoSource') }}</span>
        </div>
      </header>
      <div class="trend">
        <div v-for="item in trend" :key="item.date" class="trend-col" :title="item.date">
          <div class="bar bar--q" :style="{ height: barHeight(item.questions) }"></div>
          <div class="bar bar--d" :style="{ height: barHeight(item.degraded) }"></div>
          <div class="bar bar--n" :style="{ height: barHeight(item.no_source) }"></div>
          <span class="trend-date">{{ shortDate(item.date) }}</span>
        </div>
      </div>
    </section>

    <!-- 三、知识库缺口：no_source 的问题 Top 榜 —— 补语料的清单 -->
    <section class="panel">
      <header class="panel-head">
        <h2>{{ t('assistantAdmin.gapTitle') }}</h2>
      </header>
      <!-- 第 229 批补：原因码不进标题（中文界面里冒出 `no_source` 像是没翻译完），
           这里用人话解释"这一栏是什么"，标识符只留给代码与日志。 -->
      <p class="panel-hint">{{ t('assistantAdmin.gapHint') }}</p>
      <el-table v-if="gaps.length" :data="gaps" row-key="question" class="admin-table">
        <el-table-column prop="question" :label="t('assistantAdmin.gapColQuestion')" min-width="320" />
        <el-table-column :label="t('assistantAdmin.gapColCount')" width="110">
          <template #default="{ row }">
            <el-tag type="warning" effect="light" size="small">{{ row.count }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('assistantAdmin.gapColLast')" width="180">
          <template #default="{ row }">{{ formatTime(row.last_at, 'YYYY-MM-DD HH:mm') }}</template>
        </el-table-column>
      </el-table>
      <p v-else class="empty-line">{{ t('assistantAdmin.gapEmpty') }}</p>
    </section>

    <!-- 四、用户说"没用"：note 是最有价值的信号 -->
    <section class="panel">
      <header class="panel-head">
        <h2>{{ t('assistantAdmin.uselessTitle') }}</h2>
      </header>
      <el-table v-if="useless.length" :data="useless" row-key="message_id" class="admin-table">
        <el-table-column prop="question" :label="t('assistantAdmin.uselessColQuestion')" min-width="220" />
        <el-table-column :label="t('assistantAdmin.uselessColNote')" min-width="200">
          <template #default="{ row }">
            <span :class="{ muted: !row.note }">{{ row.note || t('assistantAdmin.noteEmpty') }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('assistantAdmin.uselessColAnswer')" min-width="260">
          <template #default="{ row }">
            <span class="answer-preview">{{ row.answer_preview }}</span>
            <el-tag v-if="row.degraded" type="info" size="small" effect="plain" class="degraded-tag">
              {{ reasonLabel(row.degrade_reason) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('assistantAdmin.uselessColTime')" width="170">
          <template #default="{ row }">{{ formatTime(row.feedback_at, 'YYYY-MM-DD HH:mm') }}</template>
        </el-table-column>
      </el-table>
      <p v-else class="empty-line">{{ t('assistantAdmin.uselessEmpty') }}</p>
    </section>

    <!-- 五、被引用最多的词条：哪几条语料在撑回答 -->
    <section class="panel">
      <header class="panel-head">
        <h2>{{ t('assistantAdmin.sourcesTitle') }}</h2>
      </header>
      <ul v-if="sources.length" class="source-list">
        <li v-for="item in sources" :key="item.pest_id">
          <span class="source-name">{{ pestLabel(item) }}</span>
          <span class="source-count">{{ t('assistantAdmin.sourcesCount', { count: item.count }) }}</span>
        </li>
      </ul>
      <p v-else class="empty-line">{{ t('assistantAdmin.sourcesEmpty') }}</p>
    </section>
  </div>
</template>

<script setup>
/**
 * 助手质量看板（第 228 批，`/admin/assistant`）
 * ----------------------------------------------------------------------------
 * 为什么加这一页：`degraded` / `degrade_reason` / `latency_ms` / `usage` /
 * `verdict` / `feedback_note` 这些字段从第 193 批就在落库，但**没有任何界面在读** ——
 * "助手最近答得不好"只能进 Django admin 一条条翻。
 *
 * 三个刻意的实现选择：
 *   · **比率全部由后端算**：前端只格式化。两处各算一遍必然会漂（本项目吃过
 *     "同一套逻辑两个口径"的亏，见第 106/124 批）；
 *   · 趋势用**纯 CSS 柱**而不是图表库：这页要的是"有没有异常"，不是交互分析，
 *     没必要为它加载 180KB 的 echarts chunk；
 *   · 空白日也画（后端补齐）：缺日会让折线/柱状把两个有数据的日子连成一条假趋势。
 */
import { computed, onMounted, ref } from 'vue';
import { fetchAssistantStats } from '@/api/assistantAdmin';
import { formatApiError } from '@/api/http';
import { formatTime } from '@/utils/date';
import { useI18n } from '@/i18n';

const { t, locale } = useI18n();

const days = ref(14);
const loading = ref(false);
const errorMessage = ref('');
const data = ref(null);

const totals = computed(() => data.value?.totals ?? {
  questions: 0, answers: 0, degraded: 0, degraded_rate: 0, no_source: 0,
  rate_limited: 0, session_full: 0, llm_error: 0, llm_disabled: 0,
  helpful: 0, useless: 0, useless_rate: 0, avg_latency_ms: 0,
  tokens: { prompt: 0, completion: 0 },
});
const trend = computed(() => data.value?.trend ?? []);
const gaps = computed(() => data.value?.gaps?.no_source_questions ?? []);
const useless = computed(() => data.value?.gaps?.useless ?? []);
const sources = computed(() => data.value?.top_sources ?? []);
const tokenTotal = computed(() => totals.value.tokens.prompt + totals.value.tokens.completion);

/** 回答语言分布：把后端给的 `{zh: 43, en: 4}` 变成"中文 43 / English 4" */
const langRows = computed(() => {
  const languages = data.value?.languages ?? {};
  const labelOf = (key) => {
    if (key === 'zh') return t('assistantAdmin.langZh');
    if (key === 'en') return t('assistantAdmin.langEn');
    return key;
  };
  return Object.entries(languages)
    .map(([key, count]) => ({ key, count, label: labelOf(key) }))
    .sort((a, b) => b.count - a.count);
});

/** 降级原因 → 人话。认不出来的码原样显示（新原因码没配文案时至少不至于是空白） */
const REASON_KEYS = [
  'no_source', 'llm_disabled', 'llm_error', 'llm_error_partial',
  'rate_limited', 'session_full', 'vision_unreadable', 'too_long', 'sensitive', 'empty',
];
const reasonLabel = (code) => (
  REASON_KEYS.includes(code) ? t(`assistantAdmin.reason.${code}`) : (code || '')
);

/**
 * 词条名按当前界面语言选（第 229 批补）
 *
 * 数据级双语在本项目一律是"后端回中英两个字段、前端按语言挑"（同 `result_en` /
 * `crop_type_en`）—— 后端不猜语言，否则缓存与 Accept-Language 的差异会变成
 * "同一个接口两种结果"。`name_en` 允许为空（老词条没填），空则回落中文。
 */
const pestLabel = (item) => {
  const isEn = String(locale.value || '').toLowerCase().startsWith('en');
  if (isEn) return item.name_en || item.name;
  return item.name || item.name_en;
};

/** 趋势柱子的最大值（至少 1，避免全 0 时除零） */
const trendMax = computed(() => Math.max(1, ...trend.value.map((item) => item.questions)));
const barHeight = (value) => `${Math.round((value / trendMax.value) * 100)}%`;
const shortDate = (date) => (date || '').slice(5);   // MM-DD

const percent = (value) => `${((Number(value) || 0) * 100).toFixed(1)}%`;

const load = async () => {
  loading.value = true;
  errorMessage.value = '';
  try {
    data.value = await fetchAssistantStats(days.value);
  } catch (error) {
    errorMessage.value = formatApiError(error, t('assistantAdmin.loadFailed'));
  } finally {
    loading.value = false;
  }
};

onMounted(load);
</script>

<style scoped>
.assistant-admin {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.readonly-note {
  border-radius: 10px;
}

.load-error {
  margin: 0;
  padding: 10px 14px;
  border-radius: 10px;
  background: #fef4f4;
  border: 1px solid #f7d9d9;
  color: #c0392b;
  font-size: 13px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  border-radius: 14px;
  background: #fff;
  border: 1px solid rgba(31, 99, 67, 0.1);
  box-shadow: 0 1px 2px rgba(16, 32, 24, 0.04);
}

.stat-card.is-warn {
  border-color: #f0c7a8;
  background: #fffaf5;
}

.stat-label {
  font-size: 12px;
  color: #6b7d72;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #1f6343;
  line-height: 1.2;
}

.stat-sub {
  font-size: 12px;
  color: #8b9a91;
}

.panel {
  padding: 16px 18px;
  border-radius: 14px;
  background: #fff;
  border: 1px solid rgba(31, 99, 67, 0.1);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.panel-head h2 {
  margin: 0;
  font-size: 15px;
  color: #20402f;
}

.legend {
  display: flex;
  gap: 14px;
  font-size: 12px;
  color: #6b7d72;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

/* 第 229 批补：面板说明行 + 语言分布行 */
.panel-hint {
  margin: -4px 0 12px;
  font-size: 12.5px;
  line-height: 1.7;
  color: #6b7d72;
}

.lang-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 12px;
  background: #f4f9f6;
  border: 1px solid rgba(31, 99, 67, 0.1);
  font-size: 12.5px;
  color: #4a5f53;
}

.lang-label {
  font-weight: 600;
  color: #20402f;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.dot--q { background: #2f855a; }
.dot--d { background: #d98324; }
.dot--n { background: #c0392b; }

.trend {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 150px;
  padding-top: 8px;
}

.trend-col {
  flex: 1;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 2px;
  height: 100%;
  position: relative;
  padding-bottom: 18px;
}

.trend-col .bar {
  width: 26%;
  min-height: 2px;
  border-radius: 3px 3px 0 0;
  transition: height 0.2s ease;
}

.bar--q { background: #2f855a; }
.bar--d { background: #d98324; }
.bar--n { background: #c0392b; }

.trend-date {
  position: absolute;
  bottom: 0;
  font-size: 10px;
  color: #8b9a91;
  white-space: nowrap;
}

.empty-line {
  margin: 0;
  padding: 18px 0;
  text-align: center;
  font-size: 13px;
  color: #8b9a91;
}

.answer-preview {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}

.degraded-tag {
  margin-left: 6px;
}

.muted {
  color: #9aa8a0;
}

.source-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.source-list li {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 999px;
  background: #f2f8f4;
  border: 1px solid rgba(31, 99, 67, 0.12);
  font-size: 13px;
}

.source-name {
  color: #20402f;
  font-weight: 600;
}

.source-count {
  color: #6b7d72;
}
</style>
