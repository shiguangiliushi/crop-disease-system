<template>
  <div class="health-page tinted-page">
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-heart-pulse"></i></span>
        <div>
          <h1>{{ t('health.title') }}</h1>
          <p>{{ t('health.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-button plain :loading="loading" @click="load">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
      </div>
    </header>

    <!-- 总体状态：一屏先回答"现在有没有事" -->
    <el-alert
      v-if="!loading && data"
      :type="alertType"
      :closable="false"
      show-icon
      class="overall"
    >
      <template #title>
        <b>{{ overallTitle }}</b>
        <span v-if="data.problems.length"> ｜ {{ t('health.problemCount', { count: data.problems.length }) }}</span>
        <span v-if="data.warnings.length"> ｜ {{ t('health.warningCount', { count: data.warnings.length }) }}</span>
      </template>
      <div v-if="data.problems.length || data.warnings.length" class="overall-list">
        <p v-for="(item, index) in data.problems" :key="`p${index}`" class="line line--fail">
          <i class="fas fa-circle-xmark"></i> {{ item }}
        </p>
        <p v-for="(item, index) in data.warnings" :key="`w${index}`" class="line line--warn">
          <i class="fas fa-triangle-exclamation"></i> {{ item }}
        </p>
      </div>
    </el-alert>

    <!-- 数据量概览 -->
    <div v-if="data" class="admin-stats">
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-users"></i></span>
        <div>
          <div class="stat-tile-value">{{ data.counts.users }}</div>
          <div class="stat-tile-label">{{ t('health.statUsers', { active: data.counts.active_users }) }}</div>
        </div>
      </div>
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-comments"></i></span>
        <div>
          <div class="stat-tile-value">{{ data.counts.posts }}</div>
          <div class="stat-tile-label">{{ t('health.statPosts', { comments: data.counts.comments }) }}</div>
        </div>
      </div>
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-camera"></i></span>
        <div>
          <div class="stat-tile-value">{{ data.counts.detections }}</div>
          <div class="stat-tile-label">{{ t('health.statDetections') }}</div>
        </div>
      </div>
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-lightbulb"></i></span>
        <div>
          <div class="stat-tile-value">{{ data.counts.feedback }}</div>
          <div class="stat-tile-label">
            {{ t('health.statFeedback', { pending: data.counts.feedback_pending }) }}
          </div>
        </div>
      </div>
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-hard-drive"></i></span>
        <div>
          <div class="stat-tile-value">{{ data.media.mb }} MB</div>
          <div class="stat-tile-label">{{ t('health.statMedia', { files: data.media.files }) }}</div>
        </div>
      </div>
    </div>

    <!--
      最近 14 天的健康快照（第 158 批）
      ----------------------------------------------------------------
      环境类故障是**安静**的：定时任务挂了、备份没跑成，没人会来报错。
      所以每天记一条快照 —— "最新备份是 3 天前"和"这 14 天一直在跑"
      是两种完全不同的安心程度。缺的那天也会画成灰色（那本身就是信息：任务没跑）。
    -->
    <section v-if="data && data.history" class="panel-card">
      <h3 class="panel-title">
        {{ t('health.trendTitle', { days: data.history.window }) }}
        <span class="panel-count">
          {{ t('health.trendRecorded', { recorded: data.history.recorded_days, days: data.history.window }) }}
        </span>
      </h3>
      <div class="trend">
        <div
          v-for="day in data.history.days"
          :key="day.date"
          class="trend-cell"
          :class="dayClass(day)"
          :title="trendTitle(day)"
        >
          <span class="trend-dot"></span>
          <span class="trend-day">{{ day.date.slice(5) }}</span>
        </div>
      </div>
      <p class="field-hint">{{ t('health.trendHint') }}</p>
    </section>

    <!-- 分节检查结果（就是 check_env 的输出） -->
    <section v-for="section in sections" :key="section.title" class="panel-card">
      <h3 class="panel-title">
        {{ section.title }}
        <span class="panel-count">
          {{ t('health.sectionCount', { ok: countOf(section, 'ok'), total: section.items.length }) }}
        </span>
      </h3>
      <ul class="check-list">
        <li v-for="(item, index) in section.items" :key="index" :class="`check-item check-item--${item.level}`">
          <i :class="iconOf(item.level)"></i>
          <span>{{ item.text }}</span>
        </li>
      </ul>
    </section>

    <!-- 运行时与路径（排查问题时要抄给别人的信息） -->
    <section v-if="data" class="panel-card">
      <h3 class="panel-title">{{ t('health.runtimeTitle') }}</h3>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item :label="t('health.runtimeDebug')">
          <el-tag :type="data.runtime.debug ? 'warning' : 'success'" size="small" effect="light">
            {{ data.runtime.debug ? t('health.debugOn') : t('health.debugOff') }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('health.runtimeVersions')">
          Python {{ data.runtime.python }} · Django {{ data.runtime.django }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('health.runtimeDatabase')">{{ data.runtime.database }}</el-descriptions-item>
        <el-descriptions-item :label="t('health.runtimeCache')">{{ data.runtime.cache }}</el-descriptions-item>
        <el-descriptions-item :label="t('health.runtimeMedia')" :span="2">
          <code>{{ data.runtime.media_root }}</code>
        </el-descriptions-item>
        <el-descriptions-item :label="t('health.runtimeBackup')" :span="2">
          <code>{{ data.runtime.backup_root }}</code>
        </el-descriptions-item>
      </el-descriptions>
      <p class="field-hint">{{ t('health.runtimeHint') }}</p>
    </section>
  </div>
</template>

<script>
/**
 * 管理端「系统健康」（第 157 批）
 *
 * ## 为什么要有这一页
 *
 * 后端早就有 `manage.py check_env`，能查出这些**安静的故障**：
 * 依赖缺了、迁移没跑、模型文件没了、media 不可写、注销到期任务没挂、**备份过期**。
 * 但它只有命令行 —— 也就是说**只有会 SSH 上服务器的人看得见**。
 * 其中"备份挂了没人知道"最要命：等到真出事那天才发现没有可用的备份。
 *
 * 这一页把同一套检查搬到界面上，外加数据量概览与运行时信息。
 *
 * ## 它**不重写**检查
 *
 * 后端 `AdminHealthView` 直接调 `check_env --json`（第 157 批给那个命令加了
 * `--json` 与结构化 `results`）。前端只是把结果画出来 ——
 * 所以**命令行与界面永远说的是同一件事**，不会出现"界面说好、命令行说坏"。
 *
 * ## 权限：仅全权管理员
 *
 * 它会暴露服务器路径、依赖版本、是否开了 HTTPS 等部署细节，
 * 与「操作日志」同档（内容编辑员看不到，直连接口 403）。
 */
import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { fetchSystemHealth } from '@/api/health';
import { formatApiError } from '@/api/http';
import { useI18n } from '@/i18n';

export default {
  name: 'AdminHealthView',
  setup() {
    const { t } = useI18n();
    const loading = ref(false);
    const data = ref(null);

    const load = async () => {
      loading.value = true;
      try {
        data.value = await fetchSystemHealth();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('health.loadFailed')));
      } finally {
        loading.value = false;
      }
    };

    const sections = computed(() => data.value?.sections || []);

    const alertType = computed(() => {
      const level = data.value?.level;
      if (level === 'fail') return 'error';
      if (level === 'warn') return 'warning';
      return 'success';
    });

    const overallTitle = computed(() => {
      const level = data.value?.level;
      if (level === 'fail') return t('health.overallFail');
      if (level === 'warn') return t('health.overallWarn');
      return t('health.overallOk');
    });

    /** 快照格子的状态：没记录 = 灰（说明那天定时任务没跑） */
    const dayClass = (day) => {
      if (!day.recorded) return 'trend-cell--missing';
      if (day.level === 'fail') return 'trend-cell--fail';
      if (day.level === 'warn') return 'trend-cell--warn';
      return 'trend-cell--ok';
    };

    /** 悬停提示：日期 + 等级 + 问题/提示数（有要点就附上） */
    const trendTitle = (day) => {
      if (!day.recorded) return t('health.trendMissing', { date: day.date });
      const base = t('health.trendCell', {
        date: day.date, problems: day.problem_count, warnings: day.warning_count,
      });
      return day.notes ? `${base}\n${day.notes}` : base;
    };

    const iconOf = (level) => ({
      ok: 'fas fa-circle-check',
      warn: 'fas fa-triangle-exclamation',
      fail: 'fas fa-circle-xmark',
    }[level] || 'fas fa-circle-info');

    const countOf = (section, level) => section.items.filter((i) => i.level === level).length;

    onMounted(load);

    return {
      t, loading, data, sections, alertType, overallTitle, iconOf, countOf, load,
      dayClass, trendTitle,
    };
  },
};
</script>

<style scoped>
.overall {
  margin-bottom: 14px;
}

.overall-list {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.line {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
}

.line--fail {
  color: var(--el-color-danger);
}

.line--warn {
  color: var(--el-color-warning);
}

.panel-card {
  margin-bottom: 14px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #fff;
}

.panel-title {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-800);
  display: flex;
  align-items: center;
  gap: 10px;
}

.panel-count {
  font-size: 12px;
  font-weight: 400;
  color: var(--ink-400, #9dada5);
}

.check-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.check-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  line-height: 1.6;
}

.check-item i {
  margin-top: 3px;
}

.check-item--ok i {
  color: var(--el-color-success);
}

.check-item--warn {
  color: var(--el-color-warning);
}

.check-item--fail {
  color: var(--el-color-danger);
}

.trend {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.trend-cell {
  flex: 1 1 46px;
  min-width: 46px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 6px 2px;
  border-radius: 8px;
  background: var(--ink-50);
}

.trend-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--ink-300, #c9d5cd);
}

.trend-day {
  font-size: 11px;
  color: var(--ink-400, #9dada5);
}

.trend-cell--ok .trend-dot { background: var(--el-color-success); }
.trend-cell--warn .trend-dot { background: var(--el-color-warning); }
.trend-cell--fail .trend-dot { background: var(--el-color-danger); }
.trend-cell--missing { background: repeating-linear-gradient(45deg, #f6f8f6, #f6f8f6 4px, #eef2ef 4px, #eef2ef 8px); }

.field-hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--ink-400, #9dada5);
}
</style>
