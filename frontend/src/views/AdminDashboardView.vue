<template>
  <div class="dashboard-page">
    <!-- 返回入口（第 87 批：本页只能从顶栏「管理」下拉进来，此前没有返回按钮） -->
    <BackButton />

    <!-- 页头 -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-chart-line"></i></span>
        <div>
          <h1>{{ t('dashboard.title') }}</h1>
          <p>{{ t('dashboard.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-select v-model="days" size="default" class="range-select" @change="load">
          <el-option :value="7" :label="t('dashboard.range7')" />
          <el-option :value="14" :label="t('dashboard.range14')" />
          <el-option :value="30" :label="t('dashboard.range30')" />
          <el-option :value="90" :label="t('dashboard.range90')" />
        </el-select>
        <el-button plain :loading="loading" @click="load">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
      </div>
    </header>

    <!-- 待办提醒 -->
    <div v-if="todoCount > 0" class="todo-bar">
      <i class="fas fa-bell"></i>
      <span>{{ t('dashboard.todoLabel', { count: todoCount }) }}</span>
      <RouterLink v-if="totals.pending_posts" to="/admin/review">
        {{ t('dashboard.pendingPosts') }} {{ totals.pending_posts }}
      </RouterLink>
      <RouterLink v-if="totals.feedback_pending" to="/admin/feedback">
        {{ t('dashboard.pendingFeedback') }} {{ totals.feedback_pending }}
      </RouterLink>
      <RouterLink v-if="totals.reports_pending" to="/admin/review">
        {{ t('dashboard.pendingReports') }} {{ totals.reports_pending }}
      </RouterLink>
    </div>

    <el-skeleton v-if="loading && !loaded" :rows="8" animated />

    <template v-else>
      <!-- 核心指标 -->
      <div class="kpi-grid">
        <div class="kpi" v-for="item in kpis" :key="item.label" :class="item.tone">
          <span class="kpi-icon"><i :class="item.icon"></i></span>
          <div class="kpi-body">
            <div class="kpi-value">{{ item.value }}</div>
            <div class="kpi-label">{{ item.label }}</div>
            <div v-if="item.hint" class="kpi-hint">{{ item.hint }}</div>
          </div>
        </div>
      </div>

      <!-- 图表区 -->
      <div class="chart-grid">
        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-chart-area"></i></span>
            <h2 class="panel-title">{{ t('dashboard.trendDetections') }}</h2>
            <span class="panel-count">{{ t('alerts.summaryRange', { days }) }}</span>
          </div>
          <div class="panel-body chart-body">
            <Line :data="detectionChart" :options="lineOptions" />
          </div>
        </section>

        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-chart-pie"></i></span>
            <h2 class="panel-title">{{ t('dashboard.pestTop') }}</h2>
          </div>
          <div class="panel-body chart-body">
            <Doughnut v-if="pestChart.labels.length" :data="pestChart" :options="doughnutOptions" />
            <el-empty v-else :description="t('dashboard.noDetections')" :image-size="70" />
          </div>
        </section>
      </div>

      <div class="chart-grid">
        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-user-plus"></i></span>
            <h2 class="panel-title">{{ t('dashboard.trendUsers') }}</h2>
            <span class="panel-count">{{ t('alerts.summaryRange', { days }) }}</span>
          </div>
          <div class="panel-body chart-body">
            <Line :data="userChart" :options="lineOptions" />
          </div>
        </section>

        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-seedling"></i></span>
            <h2 class="panel-title">{{ t('dashboard.cropTop') }}</h2>
          </div>
          <div class="panel-body chart-body">
            <Bar v-if="cropChart.labels.length" :data="cropChart" :options="barOptions" />
            <el-empty v-else :description="t('dashboard.noDetections')" :image-size="70" />
          </div>
        </section>
      </div>

      <!-- 内容与用户 -->
      <div class="split-grid">
        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-layer-group"></i></span>
            <h2 class="panel-title">{{ t('dashboard.contentOverview') }}</h2>
          </div>
          <div class="panel-body">
            <div class="status-row">
              <span class="status-label">{{ t('dashboard.postsByStatus') }}</span>
              <span v-for="(count, key) in statusKeys.posts" :key="key" class="status-chip" :class="`is-${key}`">
                {{ statusText('posts', key) }} {{ postsByStatus[key] || 0 }}
              </span>
            </div>
            <div class="status-row">
              <span class="status-label">{{ t('dashboard.feedbackByStatus') }}</span>
              <span v-for="(count, key) in statusKeys.feedback" :key="key" class="status-chip" :class="`is-${key}`">
                {{ statusText('feedback', key) }} {{ feedbackByStatus[key] || 0 }}
              </span>
            </div>

            <ul class="mini-stats">
              <li><span>{{ t('dashboard.totalPosts') }}</span><b>{{ totals.posts }}</b></li>
              <li><span>{{ t('dashboard.totalComments') }}</span><b>{{ totals.comments }}</b></li>
              <li><span>{{ t('dashboard.totalNews') }}</span><b>{{ totals.news }}</b></li>
              <li><span>{{ t('dashboard.scheduledNews') }}</span><b>{{ totals.news_scheduled }}</b></li>
              <li><span>{{ t('dashboard.wikiEntries') }}</span><b>{{ totals.pest_species }}</b></li>
              <li><span>{{ t('dashboard.totalFeedback') }}</span><b>{{ totals.feedback }}</b></li>
            </ul>
          </div>
        </section>

        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-trophy"></i></span>
            <h2 class="panel-title">{{ t('dashboard.topContributors') }}</h2>
          </div>
          <div class="panel-body">
            <ol v-if="topContributors.length" class="rank-list">
              <li v-for="(user, index) in topContributors" :key="user.username">
                <span class="rank" :class="`is-${index + 1}`">{{ index + 1 }}</span>
                <span class="rank-name">{{ user.username }}</span>
                <span class="rank-meta">
                  {{ t('forum.postsCount', { count: user.post_count }) }} ·
                  {{ t('forum.commentsCount', { count: user.comment_count }) }}
                </span>
              </li>
            </ol>
            <el-empty v-else :description="t('dashboard.noContributors')" :image-size="70" />
          </div>
        </section>
      </div>

      <section class="panel-card">
        <div class="panel-head">
          <span class="panel-icon"><i class="fas fa-users"></i></span>
          <h2 class="panel-title">{{ t('dashboard.recentUsers') }}</h2>
        </div>
        <div class="panel-body">
          <table class="dash-table">
            <thead>
              <tr>
                <th>{{ t('dashboard.colUsername') }}</th>
                <th>{{ t('dashboard.colRole') }}</th>
                <th>{{ t('dashboard.colJoined') }}</th>
                <th>{{ t('dashboard.colLastLogin') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="user in recentUsers" :key="user.username">
                <td>
                  <RouterLink :to="`/user/profile/${user.id || ''}`" class="user-link">
                    {{ user.username }}
                  </RouterLink>
                </td>
                <td>{{ user.role || 'USER' }}</td>
                <td>{{ formatTime(user.date_joined) }}</td>
                <td>{{ user.last_login ? formatTime(user.last_login) : t('dashboard.neverLoggedIn') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <p class="generated-at">
        <i class="fas fa-clock"></i> {{ t('dashboard.dataGeneratedAt') }} {{ formatTime(data.generated_at) }}
      </p>
    </template>
  </div>
</template>

<script>
/**
 * 管理员数据看板（第 39 批）
 * ------------------------------------------------------------------
 * 数据来自一次聚合请求 `/api/admin/dashboard/`（识别量/用户/内容/待办都在里面），
 * 图表用项目已有的 chart.js + vue-chartjs。
 */
import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { Bar, Doughnut, Line } from 'vue-chartjs';
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  DoughnutController,
  Filler,
  Legend,
  LineController,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
  ArcElement,
} from 'chart.js';
import { fetchDashboard } from '@/api/dashboard';
import { formatTime } from '@/utils/date';
import { useI18n } from '@/i18n';  // 第 54 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 77 批：分布图的内容数据（病害名/作物名）
import BackButton from '@/components/BackButton.vue';  // 第 87 批：返回按钮

ChartJS.register(
  BarController, BarElement, LineController, LineElement, PointElement,
  DoughnutController, ArcElement, CategoryScale, LinearScale,
  Filler, Legend, Tooltip,
);

const BRAND = '#3d9a68';
const BRAND_SOFT = 'rgba(61, 154, 104, 0.16)';
const PALETTE = ['#3d9a68', '#5fb088', '#93cdad', '#2a7f53', '#d9922f', '#3d7ea6', '#cf4436', '#9dada5'];

export default {
  name: 'AdminDashboardView',
  components: { Line, Bar, Doughnut, BackButton },  // 第 87 批：加返回按钮
  setup() {
    const { t, locale } = useI18n();  // 第 54 批：多语言（第 77 批起也要 locale）
    const { localizedField } = useLocalized();  // 第 77 批：分布图的内容数据
    const loading = ref(false);
    const loaded = ref(false);
    const days = ref(14);
    const data = ref({ totals: {}, detection_trend: [], user_trend: [], post_trend: [], pest_distribution: [], crop_distribution: [], posts_by_status: {}, feedback_by_status: {}, top_contributors: [], recent_users: [] });

    /**
     * 第 77 批：看板两张分布图的标签
     * ----------------------------------------------------------------
     * 原来直接用 `item.name`（后端只回中文名），英文界面下饼图/柱图的图例全是中文。
     * 后端已随本批补上 `name_en`；"未知 / 未知作物"这两条是后端对没有匹配到病害的
     * 记录兜出来的占位行，没有英文名，只在英文界面下换成界面文案 ——
     * 中文界面保持原样（'未知' 与 stats.unknownPest 的 '未知病害' 是两处不同的既有文案）。
     */
    const UNKNOWN_LABELS = { '未知': 'stats.unknownPest', '未知作物': 'stats.unknownCrop' };
    const chartLabel = (row) => {
      const placeholderKey = locale.value === 'en' ? UNKNOWN_LABELS[row?.name] : '';
      if (placeholderKey) return t(placeholderKey);
      return localizedField(row, 'name');
    };

    // 第 54 批：状态文案改成 i18n key（原来写死中文）
    const statusKeys = {
      posts: { draft: 'status.draft', pending: 'status.pendingReview', published: 'status.published', hidden: 'status.hidden' },
      feedback: { pending: 'status.feedbackPending', processing: 'status.feedbackProcessing', resolved: 'status.feedbackResolved' },
    };

    const totals = computed(() => data.value.totals || {});
    const postsByStatus = computed(() => data.value.posts_by_status || {});
    const feedbackByStatus = computed(() => data.value.feedback_by_status || {});
    const topContributors = computed(() => data.value.top_contributors || []);
    const recentUsers = computed(() => data.value.recent_users || []);

    const todoCount = computed(
      () =>
        (totals.value.pending_posts || 0) +
        (totals.value.feedback_pending || 0) +
        (totals.value.reports_pending || 0),
    );

    const statusText = (group, key) => {
      const i18nKey = statusKeys[group]?.[key];
      return i18nKey ? t(i18nKey) : key;
    };

    const kpis = computed(() => [
      { label: t('dashboard.kpiUsers'), value: totals.value.users ?? '—', icon: 'fas fa-users', tone: '',
        hint: t('dashboard.kpiUsersHint', { count: totals.value.new_users_7d ?? 0 }) },
      { label: t('dashboard.kpiDetectionsToday'), value: totals.value.detections_today ?? '—', icon: 'fas fa-camera', tone: 'is-ok',
        hint: t('dashboard.kpiDetections7d', { count: totals.value.detections_7d ?? 0 }) },
      { label: t('dashboard.kpiDetectionsTotal'), value: totals.value.detections ?? '—', icon: 'fas fa-chart-simple', tone: 'is-info',
        hint: t('dashboard.kpiPestSpecies', { count: totals.value.pest_species ?? 0 }) },
      { label: t('dashboard.kpiActiveUsers'), value: totals.value.active_users_7d ?? '—', icon: 'fas fa-user-check', tone: 'is-info',
        hint: t('dashboard.kpiActiveHint') },
      { label: t('dashboard.kpiPendingPosts'), value: totals.value.pending_posts ?? '—', icon: 'fas fa-clipboard-check', tone: 'is-warn',
        hint: t('dashboard.kpiPendingPostsHint') },
      { label: t('dashboard.kpiPendingFeedback'), value: totals.value.feedback_pending ?? '—', icon: 'fas fa-comment-dots', tone: 'is-warn',
        hint: t('dashboard.kpiPendingFeedbackHint') },
    ]);

    const detectionChart = computed(() => ({
      labels: (data.value.detection_trend || []).map((item) => item.date),
      datasets: [{
        label: t('dashboard.chartDetections'),
        data: (data.value.detection_trend || []).map((item) => item.count),
        borderColor: BRAND,
        backgroundColor: BRAND_SOFT,
        fill: true,
        tension: 0.35,
        pointRadius: 3,
        pointBackgroundColor: BRAND,
      }],
    }));

    const userChart = computed(() => ({
      labels: (data.value.user_trend || []).map((item) => item.date),
      datasets: [{
        label: t('dashboard.chartNewUsers'),
        data: (data.value.user_trend || []).map((item) => item.count),
        borderColor: '#3d7ea6',
        backgroundColor: 'rgba(61, 126, 166, 0.16)',
        fill: true,
        tension: 0.35,
        pointRadius: 3,
        pointBackgroundColor: '#3d7ea6',
      }],
    }));

    const pestChart = computed(() => ({
      labels: (data.value.pest_distribution || []).map((item) => chartLabel(item)),
      datasets: [{
        data: (data.value.pest_distribution || []).map((item) => item.count),
        backgroundColor: PALETTE,
        borderWidth: 0,
      }],
    }));

    const cropChart = computed(() => ({
      labels: (data.value.crop_distribution || []).map((item) => chartLabel(item)),
      datasets: [{
        label: t('dashboard.chartDetections'),
        data: (data.value.crop_distribution || []).map((item) => item.count),
        backgroundColor: BRAND_SOFT,
        borderColor: BRAND,
        borderWidth: 1.5,
        borderRadius: 6,
      }],
    }));

    const lineOptions = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#78897f', font: { size: 11 } } },
        y: { beginAtZero: true, grid: { color: '#eef5f1' }, ticks: { color: '#78897f', precision: 0 } },
      },
    };

    const barOptions = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#78897f', font: { size: 11 } } },
        y: { beginAtZero: true, grid: { color: '#eef5f1' }, ticks: { color: '#78897f', precision: 0 } },
      },
    };

    const doughnutOptions = {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '58%',
      plugins: {
        legend: { position: 'right', labels: { boxWidth: 10, color: '#566b60', font: { size: 11 } } },
      },
    };

    const load = async () => {
      loading.value = true;
      try {
        data.value = await fetchDashboard(days.value);
        loaded.value = true;
      } catch (error) {
        console.error('加载看板数据失败:', error);
        ElMessage.error(error?.response?.data?.detail || t('msg.loadFailed'));
      } finally {
        loading.value = false;
      }
    };

    onMounted(load);

    return {
      loading,
      loaded,
      days,
      data,
      totals,
      postsByStatus,
      feedbackByStatus,
      topContributors,
      recentUsers,
      todoCount,
      kpis,
      detectionChart,
      userChart,
      pestChart,
      cropChart,
      lineOptions,
      barOptions,
      doughnutOptions,
      statusKeys,
      t,
      statusText,
      formatTime,
      load,
    };
  },
};
</script>

<style scoped>
.dashboard-page {
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px 20px 40px;
}

/* 第 87 批：返回按钮紧贴左边缘，和下面的深绿页头留出间距 */
.dashboard-page > .back-button {
  margin-bottom: 12px;
}

.range-select {
  width: 130px;
}

/* 待办条 */
.todo-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 15px;
  padding: 11px 15px;
  border: 1px solid #f0d9b0;
  border-radius: var(--radius);
  background: linear-gradient(120deg, #fdf6ea, #fffdf8);
  font-size: 13px;
  color: #8a5a12;
}

.todo-bar a {
  padding: 3px 10px;
  border-radius: 999px;
  background: #fff;
  border: 1px solid #f0d9b0;
  color: #8a5a12;
  font-weight: 700;
  text-decoration: none;
}

.todo-bar a:hover {
  background: #fdf3e3;
}

/* KPI */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.kpi {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid var(--brand-100);
  border-left: 3px solid var(--brand-400);
  border-radius: var(--radius);
  background: linear-gradient(150deg, #ffffff, #eef9f3);
  box-shadow: var(--shadow-xs);
}

.kpi.is-ok { border-left-color: #1f8a5c; }
.kpi.is-info { border-left-color: #3d7ea6; }
.kpi.is-warn { border-left-color: #d9922f; }

.kpi-icon {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 12px;
  font-size: 17px;
  color: var(--brand-700);
  background: var(--brand-100);
}

.kpi.is-info .kpi-icon { color: #2a6fdb; background: #e9f1fd; }
.kpi.is-warn .kpi-icon { color: #b8761b; background: #fdf3e3; }

.kpi-value {
  font-size: 22px;
  font-weight: 800;
  line-height: 1.1;
  color: var(--ink-900);
}

.kpi-label {
  font-size: 12.5px;
  color: var(--ink-600);
}

.kpi-hint {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--ink-400);
}

/* 图表 */
.chart-grid,
.split-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.chart-body {
  height: 260px;
  position: relative;
}

/* 内容概览 */
.status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.status-label {
  font-size: 12.5px;
  color: var(--ink-500);
  min-width: 62px;
}

.status-chip {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  background: var(--ink-50);
  border: 1px solid var(--border);
  color: var(--ink-600);
}

.status-chip.is-pending,
.status-chip.is-processing { background: #fdf3e3; border-color: #f0d9b0; color: #8a5a12; }
.status-chip.is-published,
.status-chip.is-resolved { background: #e7f6ee; border-color: #bfe3cd; color: #1f6343; }
.status-chip.is-hidden { background: #fdecea; border-color: #f3c9c3; color: #a32f22; }

.mini-stats {
  list-style: none;
  margin: 14px 0 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
}

.mini-stats li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 10px;
  background: var(--ink-50);
  font-size: 12.5px;
  color: var(--ink-500);
}

.mini-stats b {
  font-size: 14px;
  color: var(--ink-800);
}

/* 贡献榜 */
.rank-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rank-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--ink-50);
}

.rank {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 800;
  color: #fff;
  background: var(--ink-300);
}

.rank.is-1 { background: linear-gradient(135deg, #f0a94a, #d9822b); }
.rank.is-2 { background: linear-gradient(135deg, #9fb4c7, #7b8fa3); }
.rank.is-3 { background: linear-gradient(135deg, #cd9a72, #a9764c); }

.rank-name {
  font-weight: 700;
  color: var(--ink-800);
  font-size: 13.5px;
}

.rank-meta {
  margin-left: auto;
  font-size: 12px;
  color: var(--ink-500);
}

/* 最近用户表 */
.dash-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.dash-table th {
  text-align: left;
  padding: 9px 10px;
  background: linear-gradient(180deg, var(--brand-100), var(--brand-50));
  color: var(--brand-900);
  font-weight: 700;
  font-size: 12.5px;
}

.dash-table th:first-child { border-radius: 10px 0 0 10px; }
.dash-table th:last-child { border-radius: 0 10px 10px 0; }

.dash-table td {
  padding: 9px 10px;
  border-bottom: 1px solid #eef5f1;
  color: var(--ink-600);
}

.dash-table tbody tr:nth-child(even) td { background: #f8fcfa; }

.user-link {
  color: var(--brand-700);
  font-weight: 600;
  text-decoration: none;
}

.user-link:hover { text-decoration: underline; }

.generated-at {
  margin: 14px 0 0;
  text-align: right;
  font-size: 12px;
  color: var(--ink-400);
}

@media (max-width: 720px) {
  .chart-grid,
  .split-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
