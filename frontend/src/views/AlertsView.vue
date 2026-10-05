<template>
  <div class="alerts-page">
    <!-- 页头 -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-triangle-exclamation"></i></span>
        <div>
          <h1>{{ t('alerts.title') }}</h1>
          <p>{{ t('alerts.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-select v-model="days" size="default" class="range-select" @change="load">
          <el-option :value="7" :label="t('alerts.range7')" />
          <el-option :value="14" :label="t('alerts.range14')" />
          <el-option :value="30" :label="t('alerts.range30')" />
        </el-select>
        <el-button plain :loading="loading" @click="load">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
        <el-button v-if="isAdmin" type="primary" :loading="pushing" @click="push">
          <i class="fas fa-paper-plane"></i> {{ t('alerts.push') }}
        </el-button>
      </div>
    </header>

    <!-- 汇总条 -->
    <div v-if="!loading" class="alert-summary" :class="`is-${topLevel}`">
      <span class="summary-icon">
        <i :class="topLevel === 'high' ? 'fas fa-bolt' : topLevel === 'medium' ? 'fas fa-circle-exclamation' : 'fas fa-circle-check'"></i>
      </span>
      <div class="summary-text">
        <strong>{{ headline }}</strong>
        <span class="summary-meta">
          {{ t('alerts.summaryRange', { days }) }} · {{ t('alerts.summaryHigh') }} {{ summary.counts.high || 0 }} ·
          {{ t('alerts.summaryMedium') }} {{ summary.counts.medium || 0 }} · {{ t('alerts.summaryLow') }} {{ summary.counts.low || 0 }}
        </span>
      </div>
    </div>

    <el-skeleton v-if="loading" :rows="6" animated />

    <template v-else>
      <div v-if="alerts.length" class="alert-list">
        <article v-for="alert in alerts" :key="alert.pest.id" class="alert-card" :class="`is-${alert.level}`">
          <header class="alert-head">
            <span class="alert-level">{{ levelText(alert.level) }}</span>
            <h2 class="alert-title">{{ localizedField(alert, 'title') }}</h2>
            <span v-if="alert.is_personal" class="alert-mine">
              <i class="fas fa-user-check"></i> {{ t('alerts.relatedToMe') }}
            </span>
          </header>

          <p class="alert-message">{{ localizedField(alert, 'message') }}</p>

          <div class="alert-facts">
            <span class="fact"><b>{{ alert.recent_count }}</b> {{ t('alerts.factsDetections') }}</span>
            <span class="fact">
              {{ t('alerts.factsBaseline') }} <b>{{ alert.baseline_weekly_avg }}</b>
              <!-- 第 79 批：括号/乘号原来写死成全角（（{ratio}×）），英文界面下很不自然，
                   改成 i18n（中文仍用全角，英文用半角括号 + "×"） -->
              <template v-if="alert.ratio">{{ t('alerts.factsRatio', { ratio: alert.ratio }) }}</template>
            </span>
            <span class="fact"><b>{{ alert.distinct_users }}</b> {{ t('alerts.factsUsers') }}</span>
            <span class="fact">{{ t('alerts.factsCrop') }}: {{ localizedField(alert.pest, 'crop_type') }}</span>
          </div>

          <div class="alert-signals">
            <span v-for="signal in alert.signals" :key="signal" class="signal-chip" :class="`is-${signal}`">
              {{ signalText(signal) }}
            </span>
          </div>

          <div v-if="alert.advice.length" class="alert-advice">
            <span class="advice-title"><i class="fas fa-notes-medical"></i> {{ t('alerts.adviceTitle') }}</span>
            <ul>
              <li v-for="(item, index) in alert.advice" :key="index">
                <span class="advice-cat">{{ adviceCategory(item.category) }}</span>
                {{ localizedField(item, 'measure') }}
              </li>
            </ul>
          </div>
          <p v-else class="alert-advice-empty">{{ t('alerts.noAdvice') }}</p>

          <footer class="alert-foot">
            <RouterLink :to="alert.url" class="alert-link">
              {{ t('alerts.viewDetail') }} <i class="fas fa-arrow-right"></i>
            </RouterLink>
            <span v-if="alert.alerted_before" class="alert-history">
              {{ t('alerts.myHistory', { count: alert.my_count }) }}
            </span>
          </footer>
        </article>
      </div>

      <div v-else class="alert-empty">
        <i class="fas fa-shield-heart"></i>
        <h3>{{ t('alerts.emptyTitle') }}</h3>
        <p>{{ t('alerts.emptyDesc') }}</p>

        <!-- 第 76 批：空状态必须说清"为什么没有"，否则用户会以为功能坏了。
             数据来自后端 diagnostics（仅在无预警时返回）。 -->
        <div v-if="diagnostics" class="empty-why">
          <p v-if="diagnostics.recent_detections === 0" class="why-line">
            <i class="fas fa-circle-info"></i>
            {{ t('alerts.emptyNoData', { days: diagnostics.window_days }) }}
          </p>
          <template v-else>
            <p class="why-line">
              <i class="fas fa-circle-info"></i>
              {{ t('alerts.emptyWhy', {
                days: diagnostics.window_days,
                count: diagnostics.recent_detections,
                diseases: diagnostics.diseases_in_window,
                threshold: diagnostics.threshold,
              }) }}
            </p>
            <p v-if="diagnostics.closest" class="why-line is-close">
              <i class="fas fa-bullseye"></i>
              <!-- 第 79 批：这里此前直接用后端的裸字段。`name`/`crop_type` 是中文内容数据
                   （后端已随第 77 批给出 *_en），无预警时才渲染，所以之前几轮审计没扫到。 -->
              {{ t('alerts.emptyClosest', {
                name: localizedField(diagnostics.closest, 'name'),
                count: diagnostics.closest.count,
                needed: diagnostics.closest.needed,
              }) }}
            </p>
          </template>

          <div v-if="widerRanges.length" class="why-actions">
            <span class="why-actions-label">{{ t('alerts.emptyWiden') }}</span>
            <el-button
              v-for="option in widerRanges"
              :key="option"
              size="small"
              plain
              @click="switchRange(option)"
            >
              {{ t('alerts.summaryRange', { days: option }) }}
            </el-button>
          </div>
        </div>

        <RouterLink to="/detect" class="empty-action">{{ t('alerts.goDetect') }}</RouterLink>
      </div>

      <p class="alert-source">
        <i class="fas fa-circle-info"></i> {{ localizedField(source, 'source') }}
      </p>
    </template>
  </div>
</template>

<script>
/**
 * 病害预警页（第 46 批）
 * ------------------------------------------------------------------
 * 数据来自 `/api/alerts/`（后端 services_alert 计算）。
 * 诚实说明：本系统没有接气象/植保站数据，预警完全基于站内识别记录，
 * 页面底部会把这句话原样显示出来（`source` 字段），不做过度包装。
 */
import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { fetchAlerts, pushAlerts } from '@/api/alert';
import { formatApiError } from '@/api/http';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';  // 第 48 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 72 批：预警文案/防治措施的英文内容

/** 防治类别 → i18n key（后端 category_display 是中文，英文界面下不能用） */
const ADVICE_CATEGORY_KEYS = {
  AGRICULTURAL: 'prevent.agricultural',
  CHEMICAL: 'prevent.chemical',
  ECOLOGICAL: 'prevent.ecological',
  PHYSICAL: 'prevent.physical',
  MONITORING: 'prevent.monitoring',
};

// 第 48 批：信号与级别改成 i18n key，渲染时再翻译（原来写死中文）
const SIGNAL_KEY = {
  trend: 'alerts.signalTrend',
  community: 'alerts.signalCommunity',
  seasonal: 'alerts.signalSeasonal',
};

const LEVEL_KEY = { high: 'alerts.levelHigh', medium: 'alerts.levelMedium', low: 'alerts.levelLow' };

export default {
  name: 'AlertsView',
  setup() {
    const authStore = useAuthStore();
    const { t } = useI18n();
    const { localizedField } = useLocalized();
    const loading = ref(false);
    const pushing = ref(false);
    const days = ref(7);
    const alerts = ref([]);
    const summary = ref({ counts: {}, total: 0, headline: '' });
    const source = ref({ source: '', source_en: '' });
    // 第 76 批：无预警时后端附带的"为什么没有"说明
    const diagnostics = ref(null);

    //: 页面支持的观察窗口（与上方 el-select 一致）
    const RANGE_OPTIONS = [7, 14, 30];
    /** 比当前窗口更宽的候选窗口 —— 数据少时给用户一个"放宽看看"的出口 */
    const widerRanges = computed(() => RANGE_OPTIONS.filter((option) => option > days.value));

    const switchRange = (value) => {
      days.value = value;
      load();
    };

    const isAdmin = computed(() => Boolean(authStore.isAdmin));
    const topLevel = computed(() => {
      if (summary.value.counts?.high) return 'high';
      if (summary.value.counts?.medium) return 'medium';
      if (summary.value.counts?.low) return 'low';
      return 'none';
    });

    const levelText = (level) => (LEVEL_KEY[level] ? t(LEVEL_KEY[level]) : level);
    const signalText = (signal) => (SIGNAL_KEY[signal] ? t(SIGNAL_KEY[signal]) : signal);
    const adviceCategory = (category) =>
      ADVICE_CATEGORY_KEYS[category] ? t(ADVICE_CATEGORY_KEYS[category]) : t('prevent.general');

    // 汇总标题由前端的级别文案 + 数量拼出来（后端返回的中文 headline 只作兜底），
    // 这样切换语言时顶部这句话也会跟着变。
    const headline = computed(() => {
      const counts = summary.value.counts || {};
      if (counts.high) return `${counts.high} × ${t('alerts.levelHigh')}`;
      if (counts.medium) return `${counts.medium} × ${t('alerts.levelMedium')}`;
      if (counts.low) return `${counts.low} × ${t('alerts.levelLow')}`;
      return t('alerts.emptyTitle');
    });

    const load = async () => {
      loading.value = true;
      try {
        const data = await fetchAlerts({ days: days.value });
        alerts.value = data.alerts || [];
        summary.value = data.summary || { counts: {}, total: 0, headline: '' };
        // 第 79 批：来源声明是内容数据，中英各一份（原来只回中文）
        source.value = { source: data.source || '', source_en: data.source_en || '' };
        diagnostics.value = data.diagnostics || null;
      } catch (error) {
        ElMessage.error(formatApiError(error, t('alerts.loadFailed')));
      } finally {
        loading.value = false;
      }
    };

    const push = async () => {
      pushing.value = true;
      try {
        const data = await pushAlerts();
        ElMessage.success(data.message || t('alerts.pushOk'));
      } catch (error) {
        ElMessage.error(formatApiError(error, t('alerts.pushFailed')));
      } finally {
        pushing.value = false;
      }
    };

    onMounted(load);

    return {
      loading, pushing, days, alerts, summary, source, isAdmin, topLevel,
      diagnostics, widerRanges, switchRange,
      levelText, signalText, adviceCategory, headline, t, localizedField, load, push,
    };
  },
};
</script>

<style scoped>
.alerts-page {
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
  padding: 24px 20px 40px;
}

.range-select {
  width: 130px;
}

/* 汇总条 */
.alert-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 14px 16px;
  border-radius: var(--radius);
  border: 1px solid var(--brand-200);
  background: linear-gradient(120deg, #f3fbf7, #ffffff);
}

.alert-summary.is-high {
  border-color: #f3c9c3;
  background: linear-gradient(120deg, #fdecea, #fffdfd);
}

.alert-summary.is-medium {
  border-color: #f0d9b0;
  background: linear-gradient(120deg, #fdf6ea, #fffdf8);
}

.summary-icon {
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 13px;
  font-size: 18px;
  color: #fff;
  background: var(--gradient-brand);
}

.is-high .summary-icon { background: linear-gradient(135deg, #d9503f, #a32f22); }
.is-medium .summary-icon { background: linear-gradient(135deg, #e0a03c, #b8761b); }

.summary-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.summary-text strong {
  font-size: 15px;
  color: var(--ink-900);
}

.summary-meta {
  font-size: 12.5px;
  color: var(--ink-500);
}

/* 预警卡 */
.alert-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.alert-card {
  padding: 16px 18px;
  border: 1px solid var(--brand-150, #d8ece1);
  border-left: 4px solid var(--brand-500);
  border-radius: var(--radius);
  background: #fff;
  box-shadow: var(--shadow-xs);
}

.alert-card.is-high { border-left-color: #cf4436; }
.alert-card.is-medium { border-left-color: #d9922f; }
.alert-card.is-low { border-left-color: #3d7ea6; }

.alert-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.alert-level {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: var(--brand-600);
}

.is-high .alert-level { background: #cf4436; }
.is-medium .alert-level { background: #d9922f; }
.is-low .alert-level { background: #3d7ea6; }

.alert-title {
  margin: 0;
  font-size: 16px;
  font-weight: 800;
  color: var(--ink-900);
}

.alert-mine {
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--brand-800, #1a5238);
  background: var(--brand-100);
}

.alert-message {
  margin: 0 0 10px;
  font-size: 13.5px;
  line-height: 1.75;
  color: var(--ink-700);
}

.alert-facts {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 10px;
  font-size: 12.5px;
  color: var(--ink-500);
}

.fact b {
  color: var(--ink-800);
  font-size: 13.5px;
}

.alert-signals {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.signal-chip {
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11.5px;
  background: var(--ink-50);
  border: 1px solid var(--border);
  color: var(--ink-600);
}

.signal-chip.is-trend { background: #fdf3e3; border-color: #f0d9b0; color: #8a5a12; }
.signal-chip.is-community { background: #e9f1fd; border-color: #cbdcf6; color: #2a6fdb; }
.signal-chip.is-seasonal { background: #f1ecfb; border-color: #ddd2f5; color: #6b46c1; }

.alert-advice {
  padding: 11px 13px;
  border-radius: 10px;
  background: linear-gradient(160deg, #f6fdf9, #ffffff);
  border: 1px solid var(--brand-100);
}

.advice-title {
  display: block;
  margin-bottom: 6px;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--brand-800, #1a5238);
}

.advice-title i {
  margin-right: 5px;
}

.alert-advice ul {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.alert-advice li {
  font-size: 13px;
  line-height: 1.7;
  color: var(--ink-700);
}

.advice-cat {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 7px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--brand-700);
  background: var(--brand-100);
}

.alert-advice-empty {
  margin: 0;
  font-size: 12.5px;
  color: var(--ink-400);
}

.alert-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.alert-link {
  font-size: 13px;
  font-weight: 700;
  color: var(--brand-700);
  text-decoration: none;
}

.alert-link:hover {
  text-decoration: underline;
}

.alert-history {
  font-size: 12px;
  color: var(--ink-400);
}

/* 空状态 */
.alert-empty {
  padding: 46px 20px;
  text-align: center;
  border: 1px dashed var(--brand-200);
  border-radius: var(--radius);
  background: linear-gradient(160deg, #f8fcfa, #ffffff);
}

.alert-empty i {
  font-size: 38px;
  color: var(--brand-300);
}

.alert-empty h3 {
  margin: 12px 0 8px;
  font-size: 17px;
  color: var(--ink-800);
}

.alert-empty p {
  margin: 0 auto 16px;
  max-width: 520px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--ink-500);
}

.empty-action {
  display: inline-block;
  padding: 9px 20px;
  border-radius: var(--radius-pill);
  background: var(--gradient-brand);
  color: #fff;
  font-size: 13.5px;
  font-weight: 700;
  text-decoration: none;
}

/* 第 76 批：空状态的"为什么没有"说明块 */
.empty-why {
  max-width: 620px;
  margin: 0 auto 18px;
  padding: 13px 16px;
  border: 1px solid var(--brand-100);
  border-radius: var(--radius);
  background: #fff;
  text-align: left;
}

.why-line {
  margin: 0 0 7px;
  font-size: 12.8px;
  line-height: 1.75;
  color: var(--ink-600);
}

.why-line:last-of-type {
  margin-bottom: 0;
}

.why-line i {
  margin-right: 6px;
  color: var(--brand-500);
}

.why-line.is-close {
  color: #8a5a12;
}

.why-line.is-close i {
  color: #d9922f;
}

.why-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 11px;
  padding-top: 10px;
  border-top: 1px dashed var(--border);
}

.why-actions-label {
  font-size: 12.5px;
  color: var(--ink-500);
}

.alert-source {
  margin: 18px 0 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--ink-400);
  text-align: center;
}

.alert-source i {
  margin-right: 4px;
}
</style>
