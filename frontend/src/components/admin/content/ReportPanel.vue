<script setup>
/**
 * 「内容管理」— 举报页签（第 183 批）
 * ============================================================================
 * 本组件 = 原 `/admin/review`「内容审核」页**右栏的举报处理**（第 41/74/96 批），
 * 原样搬成一个独立页签：列表、分页、处理/驳回、`hide_content` 勾选、提示文案一行未改。
 *
 * ## 为什么它单独一个页签（而不是跟着帖子走）
 * 举报的权限口径与帖子/评论**不同**，见下 —— 放在同一个页签里就没法只按模块隐藏。
 *
 * ## 权限：**仅全权管理员**（与后端 `views_report._can_handle_reports()` 同一口径）
 *   · `_can_handle_reports(user)` = `is_full_admin(user)`
 *     （`capabilities.py` 的 `is_staff or is_superuser or role=='ADMIN'`）；
 *   · 举报回包里带 `reporter.username` / `handler_name` / `target_user_id`，
 *     能直接定位到人（属"他人数据"），且"下架内容"不可逆 ——
 *     第 124 批起**没有**列入信息编辑员的能力矩阵；
 *   · `api.tests.ForumOnlyEditorTests` 把这条钉死了：
 *     只勾「论坛交流」的编辑员看别人的举报 → 空列表，处理举报 → **403**。
 * 因此本页签只在 `authStore.isAdmin` 时出现（Hub 负责判断），本组件也不再自己判一遍。
 */
import { ref } from 'vue';
import { ElMessage } from 'element-plus';
import { formatTime } from '@/utils/date';
import { fetchReports, handleReport as apiHandleReport } from '@/api/report';  // 第 41 批：举报处理
import { useI18n } from '@/i18n';

defineOptions({ name: 'ContentReportPanel' });

const { t } = useI18n();

/* 第 74 批：举报原因 → 后端常量是 ad/abuse/politics/irrelevant/other，
   直接展示后端的 reason_display 在英文界面下会显示中文，这里用 i18n 覆盖。 */
const REASON_KEYS = {
  spam: 'review.catAd',
  ad: 'review.catAd',
  abuse: 'review.catAbuse',
  politics: 'review.catPolitics',
  irrelevant: 'report.reasonIrrelevant',
  other: 'review.catOther',
};

const reportReasonLabel = (reason) =>
  REASON_KEYS[reason] ? t(REASON_KEYS[reason]) : (reason || t('review.catOther'));

// 第 41 批：待处理举报
const reports = ref([]);
const reportsLoading = ref(false);
const reportActing = ref(null);
const hideContent = ref({});
// 第 96 批：举报同样是硬截断（原来固定取 20 条，页头却显示当前条数，
// 看起来"只有 20 条"）。补上真分页 + 真实总数。
const reportsPage = ref(1);
const reportsPageSize = ref(5);
const reportsTotal = ref(0);

/** 第 41 批：加载待处理举报（第 96 批改为真分页） */
const loadReports = async () => {
  reportsLoading.value = true;
  try {
    const data = await fetchReports({
      status: 'pending',
      page: reportsPage.value,
      page_size: reportsPageSize.value,
    });
    reports.value = data?.results || [];
    reportsTotal.value = data?.count || 0;
  } catch (error) {
    console.warn('加载举报失败:', error);
    reports.value = [];
  } finally {
    reportsLoading.value = false;
  }
};

/** 第 96 批：举报分页 —— 改每页条数时回到第 1 页 */
const handleReportsSizeChange = () => {
  reportsPage.value = 1;
  loadReports();
};

/** 处理 / 驳回一条举报（可同时隐藏被举报内容） */
const handleReport = async (report, status) => {
  reportActing.value = report.id;
  try {
    const data = await apiHandleReport(report.id, {
      status,
      note: status === 'handled' ? t('review.noteHandled') : t('review.noteRejected'),
      hide_content: Boolean(hideContent.value[report.id]),
    });
    ElMessage.success(
      status === 'handled'
        ? (data?.hidden_content ? t('review.handledHiddenNotified') : t('review.handledNotified'))
        : t('review.rejectedNotified'),
    );
    // 第 96 批：处理的是本页最后一条且不在第 1 页时退回上一页，
    // 否则会停在一个空白页上（第 89 批在反馈管理页踩过同样的坑）
    if (reports.value.length === 1 && reportsPage.value > 1) {
      reportsPage.value -= 1;
    }
    // 第 183 批说明：原页面这里还要顺带刷新"已发布"统计（下架内容后数字要变）——
    // 那个统计属于**帖子页签**，而两个页签是切换挂载的（切换时会重新加载），
    // 所以这里只刷新举报列表即可，切回帖子页签时统计自然是新的。
    await loadReports();
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || t('msg.operationFailed'));
  } finally {
    reportActing.value = null;
  }
};

loadReports();
</script>

<template>
  <div class="content-report-panel">
    <header class="hub-block-head">
      <span class="hub-block-icon"><i class="fas fa-flag"></i></span>
      <div class="hub-block-text">
        <h2>{{ t('review.reportsTitle') }}</h2>
        <p>{{ t('contentHub.reportsSubtitle') }}</p>
      </div>
      <div class="hub-block-actions">
        <el-button plain :loading="reportsLoading" @click="loadReports">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
      </div>
    </header>

    <section class="panel-card">
      <div class="panel-head">
        <span class="panel-icon"><i class="fas fa-flag"></i></span>
        <h3 class="panel-title">{{ t('review.reportsTitle') }}</h3>
        <!-- 第 96 批：改成**真实总数**（原来显示的是当前页条数，20 条以上时会少报） -->
        <span class="panel-count">{{ t('review.reportsPendingCount', { count: reportsTotal }) }}</span>
      </div>
      <div class="panel-body">
        <el-skeleton v-if="reportsLoading" :rows="3" animated />
        <template v-else-if="reports.length">
          <article v-for="report in reports" :key="report.id" class="report-item">
            <header class="report-head">
              <!-- 第 74 批：举报原因原来直接渲染后端的 reason_display（中文常量
                   "广告推广" 等），英文界面下会露中文。改用前端 i18n 映射。 -->
              <span class="report-reason">{{ reportReasonLabel(report.reason) }}</span>
              <span class="report-target">{{ report.target_label }}</span>
            </header>
            <p v-if="report.detail" class="report-detail">“{{ report.detail }}”</p>
            <div class="report-meta">
              <span><i class="fas fa-user"></i> {{ report.reporter?.username }}</span>
              <span><i class="fas fa-clock"></i> {{ formatTime(report.created_at) }}</span>
            </div>
            <div class="report-actions">
              <el-button size="small" type="primary" :loading="reportActing === report.id" @click="handleReport(report, 'handled')">
                {{ t('review.handle') }}
              </el-button>
              <el-button size="small" plain @click="handleReport(report, 'rejected')">{{ t('review.reject') }}</el-button>
              <el-checkbox v-model="hideContent[report.id]" size="small">{{ t('review.hideContent') }}</el-checkbox>
            </div>
          </article>
        </template>
        <el-empty v-else :description="t('review.emptyReports')" :image-size="60" />

        <!-- 第 96 批：举报分页（原来固定取 20 条，多出来的看不到） -->
        <div v-if="reportsTotal > reportsPageSize" class="pagination-wrap pagination-wrap--compact">
          <el-pagination
            v-model:current-page="reportsPage"
            v-model:page-size="reportsPageSize"
            :page-sizes="[5, 10, 20]"
            layout="total, sizes, prev, pager, next"
            :total="reportsTotal"
            :pager-count="5"
            small
            background
            @size-change="handleReportsSizeChange"
            @current-change="loadReports"
          />
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* 页签内的区块头（与 PostPanel / CommentPanel 里的同名类一致 —— 三个面板各自 scoped） */
.hub-block-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.hub-block-icon {
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: var(--brand-50, #f1f9f4);
  color: var(--brand-700, #1f6343);
  font-size: 16px;
}

.hub-block-text {
  min-width: 0;
}

.hub-block-text h2 {
  margin: 0 0 3px;
  font-size: 17px;
  font-weight: 800;
  color: var(--ink-900, #1b2b23);
}

.hub-block-text p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--ink-500, #78897f);
}

.hub-block-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* ---------- 原 ContentReviewView 右栏的样式 ---------- */
.report-item {
  padding: 11px 12px;
  border: 1px solid #f0d9b0;
  border-radius: var(--radius);
  background: linear-gradient(160deg, #fffdf8, #ffffff);
}

.report-item + .report-item {
  margin-top: 10px;
}

.report-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.report-reason {
  padding: 2px 8px;
  border-radius: 999px;
  background: #fdf3e3;
  color: #8a5a12;
  font-size: 11.5px;
  font-weight: 700;
}

.report-target {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-800);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.report-detail {
  margin: 0 0 8px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-600);
}

.report-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 11.5px;
  color: var(--ink-400);
}

.report-meta i {
  margin-right: 4px;
}

.report-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 9px;
}

/* 第 96 批：举报列表的紧凑分页（它原来在窄侧栏里；现在整页宽了，仍保留紧凑左对齐） */
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.pagination-wrap--compact {
  justify-content: flex-start;
}

.pagination-wrap--compact :deep(.el-pagination) {
  flex-wrap: wrap;
  row-gap: 6px;
  justify-content: flex-start;
}
</style>
