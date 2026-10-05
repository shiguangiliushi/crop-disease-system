<template>
  <div class="review-page">
    <!-- 返回入口（第 87 批：本页只能从顶栏「管理」下拉进来，此前没有返回按钮；
         页头右侧那个「去论坛」是去**审核对象**所在的页面，不等于返回） -->
    <BackButton />

    <!-- 页头 -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-clipboard-check"></i></span>
        <div>
          <h1>{{ t('review.title') }}</h1>
          <p>{{ t('review.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-button plain :loading="loading" @click="loadAll">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
        <el-button plain @click="goForum">
          <i class="fas fa-comments"></i> {{ t('review.goForum') }}
        </el-button>
      </div>
    </header>

    <!-- 审核策略提示 -->
    <div class="policy-bar" :class="{ 'is-on': siteConfig.post_require_review }">
      <i :class="siteConfig.post_require_review ? 'fas fa-shield-halved' : 'fas fa-circle-info'"></i>
      <span v-if="siteConfig.post_require_review">
        {{ t('review.policyPrefix') }}<strong>{{ t('review.policyOn') }}</strong>{{ t('review.policyOnTail') }}
      </span>
      <span v-else>
        {{ t('review.policyPrefix') }}<strong>{{ t('review.policyOff') }}</strong>{{ t('review.policyOffTail') }} <code>POST_REQUIRE_REVIEW</code> {{ t('review.policyOffSetTo') }} <code>true</code>.
      </span>
    </div>

    <!-- 统计 -->
    <div class="admin-stats">
      <div class="stat-tile stat-tile--pending">
        <span class="stat-tile-icon"><i class="fas fa-hourglass-half"></i></span>
        <div>
          <div class="stat-tile-value">{{ pendingTotal }}</div>
          <div class="stat-tile-label">{{ t('review.statPendingPosts') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--ok">
        <span class="stat-tile-icon"><i class="fas fa-check"></i></span>
        <div>
          <div class="stat-tile-value">{{ publishedTotal }}</div>
          <div class="stat-tile-label">{{ t('review.statPublished') }}</div>
        </div>
      </div>
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-filter"></i></span>
        <div>
          <div class="stat-tile-value">{{ words.length }}</div>
          <div class="stat-tile-label">{{ t('review.statWords') }}</div>
        </div>
      </div>
    </div>

    <div class="review-layout">
      <!-- 待审核列表 -->
      <section class="panel-card">
        <div class="panel-head">
          <span class="panel-icon"><i class="fas fa-list-check"></i></span>
          <h2 class="panel-title">{{ t('review.pendingTitle') }}</h2>
          <span class="panel-count">{{ t('review.totalCount', { count: pendingTotal }) }}</span>
          <!--
            第 100 批：批量审核
            ------------------------------------------------------------------
            为什么需要：待审多起来后只能一条一条点"通过"，每条一次点击 + 一次网络往返；
            更麻烦的是**漏审** —— 列表一分页就很容易看漏中间某条。
            这里给"全选本页 + 批量通过/驳回"。
          -->
          <div class="panel-head-right">
            <template v-if="selectedIds.length">
              <span class="selection-hint">{{ t('review.selectedCount', { count: selectedIds.length }) }}</span>
              <el-button size="small" type="primary" :loading="bulkActing" @click="bulkApprove">
                <i class="fas fa-check-double"></i> {{ t('review.bulkApprove') }}
              </el-button>
              <el-button size="small" type="danger" plain :disabled="bulkActing" @click="bulkRejectVisible = true">
                <i class="fas fa-xmark"></i> {{ t('review.bulkReject') }}
              </el-button>
              <el-button size="small" text @click="selectedIds = []">{{ t('review.clearSelection') }}</el-button>
            </template>
          </div>
        </div>

        <div class="panel-body">
          <el-skeleton v-if="loading" :rows="4" animated />

          <el-empty
            v-else-if="pendingPosts.length === 0"
            :description="t('review.emptyPending')"
          />

          <template v-else>
            <div class="bulk-bar">
              <el-checkbox
                :model-value="allPageSelected"
                :indeterminate="somePageSelected"
                @change="toggleSelectAllPage"
              >
                {{ t('review.selectAllPage') }}
              </el-checkbox>
            </div>

            <ul class="review-list">
              <li v-for="post in pendingPosts" :key="post.id" class="review-item">
                <el-checkbox
                  class="review-check"
                  :model-value="selectedIds.includes(post.id)"
                  @change="(checked) => toggleSelect(post.id, checked)"
                />
                <div class="review-main">
                  <h3 class="review-title">
                    <el-tag size="small" type="warning" effect="dark">{{ t('review.tagPendingReview') }}</el-tag>
                    {{ post.title }}
                  </h3>
                  <p class="review-excerpt">{{ excerptOf(post) }}</p>
                  <div class="review-meta">
                    <span><i class="fas fa-user"></i> {{ post.author?.username || t('review.unknownAuthor') }}</span>
                    <span><i class="fas fa-layer-group"></i> {{ post.board?.name || t('review.unknownBoard') }}</span>
                    <span><i class="fas fa-clock"></i> {{ formatTime(post.created_at) }}</span>
                  </div>
                </div>

                <div class="review-actions">
                  <el-button size="small" type="primary" :loading="acting === post.id" @click="approve(post)">
                    <i class="fas fa-check"></i> {{ t('review.approve') }}
                  </el-button>
                  <el-button size="small" type="danger" plain @click="openReject(post)">
                    <i class="fas fa-xmark"></i> {{ t('review.reject') }}
                  </el-button>
                  <el-button size="small" text @click="previewPost(post)">
                    <i class="fas fa-eye"></i> {{ t('review.view') }}
                  </el-button>
                </div>
              </li>
            </ul>
          </template>

          <!--
            第 96 批：待审列表分页
            ------------------------------------------------------------------
            改前一次性只取 20 条，而页头显示的是**真实总数** —— 有 25 条待审时
            页头写"25 条"，列表里只有 20 条，剩下 5 条没有任何入口能看到。
            审核员会以为"都处理完了"。现在有真分页，页头总数与列表条数一致可核对。
          -->
          <div v-if="pendingTotal > 0" class="pagination-wrap">
            <el-pagination
              v-model:current-page="pendingPage"
              v-model:page-size="pendingPageSize"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next"
              :total="pendingTotal"
              background
              @size-change="handlePendingSizeChange"
              @current-change="loadPending"
            />
          </div>
        </div>
      </section>

      <!-- 敏感词词库 -->
      <aside class="review-side">
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

        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-filter"></i></span>
            <h3 class="panel-title">{{ t('review.wordsTitle') }}</h3>
            <span class="panel-count">{{ t('review.totalCount', { count: words.length }) }}</span>
          </div>
          <div class="panel-body">
            <div class="word-add">
              <el-input
                v-model="newWord"
                size="small"
                maxlength="50"
                :placeholder="t('review.wordPlaceholder')"
                @keyup.enter="addWord"
              />
              <el-select v-model="newWordCategory" size="small" class="word-category">
                <el-option v-for="item in categories" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <el-button size="small" type="primary" :loading="addingWord" @click="addWord">
                <i class="fas fa-plus"></i>
              </el-button>
            </div>
            <p class="field-hint">
              {{ t('review.wordsHint') }}
            </p>

            <ul v-if="words.length" class="word-list">
              <li v-for="item in words" :key="item.id" class="word-item">
                <span class="word-text">{{ item.word }}</span>
                <span class="word-cat">{{ categoryLabel(item.category) }}</span>
                <span v-if="!item.is_active" class="word-off">{{ t('review.disabled') }}</span>
                <button type="button" class="word-del" :title="t('review.delete')" @click="removeWord(item)">
                  <i class="fas fa-trash"></i>
                </button>
              </li>
            </ul>
            <el-empty v-else :description="t('review.wordsEmpty')" :image-size="60" />
          </div>
        </section>
      </aside>
    </div>

    <!-- 驳回原因 -->
    <el-dialog v-model="rejectDialog" width="520px" class="form-dialog" :close-on-click-modal="false">
      <template #header>
        <div class="form-dialog-head">
          <span class="form-dialog-head-icon"><i class="fas fa-xmark"></i></span>
          <div>
            <h3>{{ t('review.rejectDialogTitle') }}</h3>
            <p>{{ t('review.rejectDialogHint') }}</p>
          </div>
        </div>
      </template>

      <div class="form-dialog-body">
        <p class="reject-post-title">{{ rejectingPost?.title }}</p>
        <el-input
          v-model="rejectReason"
          type="textarea"
          :rows="4"
          resize="none"
          maxlength="200"
          show-word-limit
          :placeholder="t('review.rejectReasonPlaceholder')"
        />
      </div>

      <template #footer>
        <div class="form-dialog-footer">
          <span class="footer-hint"><i class="fas fa-bell"></i> {{ t('review.authorWillBeNotified') }}</span>
          <span>
            <el-button @click="rejectDialog = false">{{ t('review.cancel') }}</el-button>
            <el-button type="danger" :loading="acting === rejectingPost?.id" @click="confirmReject">
              {{ t('review.confirmReject') }}
            </el-button>
          </span>
        </div>
      </template>
    </el-dialog>

    <!-- 批量驳回（第 100 批）：与单条驳回共用同一个原因输入，逐条通知作者 -->
    <el-dialog v-model="bulkRejectVisible" width="520px" class="form-dialog" :close-on-click-modal="false">
      <template #header>
        <div class="form-dialog-head">
          <span class="form-dialog-head-icon"><i class="fas fa-xmark"></i></span>
          <div>
            <h3>{{ t('review.bulkRejectTitle', { count: selectedIds.length }) }}</h3>
            <p>{{ t('review.rejectDialogHint') }}</p>
          </div>
        </div>
      </template>

      <div class="form-dialog-body">
        <el-input
          v-model="bulkRejectReason"
          type="textarea"
          :rows="4"
          resize="none"
          maxlength="200"
          show-word-limit
          :placeholder="t('review.rejectReasonPlaceholder')"
        />
      </div>

      <template #footer>
        <div class="form-dialog-footer">
          <span class="footer-hint"><i class="fas fa-bell"></i> {{ t('review.authorWillBeNotified') }}</span>
          <span>
            <el-button @click="bulkRejectVisible = false">{{ t('review.cancel') }}</el-button>
            <el-button type="danger" :loading="bulkActing" @click="bulkReject">
              {{ t('review.bulkRejectConfirm', { count: selectedIds.length }) }}
            </el-button>
          </span>
        </div>
      </template>
    </el-dialog>

    <!-- 帖子预览 -->
    <el-dialog v-model="previewDialog" width="720px" top="6vh" class="form-dialog">
      <template #header>
        <div class="form-dialog-head">
          <span class="form-dialog-head-icon"><i class="fas fa-eye"></i></span>
          <div>
            <h3>{{ localizedField(previewingPost, 'title') }}</h3>
            <p>{{ previewingPost?.author?.username }} · {{ localizedField(previewingPost?.board, 'name') }}</p>
          </div>
        </div>
      </template>
      <div class="form-dialog-body">
        <!-- 第 91 批（安全）：预览的是**待审帖子正文**（用户写的内容），必须净化后再进 v-html -->
        <div class="post-preview" v-html="sanitizeRichText(localizedField(previewingPost, 'content'))"></div>
      </div>
    </el-dialog>
  </div>
</template>

<script>
/**
 * 内容审核（第 38 批新增，仅管理员）
 * ------------------------------------------------------------------
 * 左侧：待审核帖子（通过 / 驳回 / 预览）；驳回会带原因通知作者
 * 右侧：敏感词词库维护（增删）
 * 顶部：如实显示当前审核策略（来自 /api/site-config/，不硬编码）
 */
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { formatTime } from '@/utils/date';
import {
  approvePost,
  bulkReviewPosts,  // 第 100 批：批量审核
  createSensitiveWord,
  deleteSensitiveWord,
  fetchPostsByStatus,
  fetchSensitiveWords,
  fetchSiteConfig,
  rejectPost,
} from '@/api/content';
import { fetchReports, handleReport as apiHandleReport } from '@/api/report';  // 第 41 批：举报处理
import { useI18n } from '@/i18n';  // 第 65 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 85 批：帖子预览用英文译文
import BackButton from '@/components/BackButton.vue';  // 第 87 批：返回按钮
import { sanitizeRichText } from '@/utils/richText';  // 第 91 批：预览正文净化（存储型 XSS）

// 敏感词分类标签（文案走 i18n，value 保持后端约定的英文标识）
const CATEGORY_KEYS = [
  { value: 'ad', labelKey: 'review.catAd' },
  { value: 'abuse', labelKey: 'review.catAbuse' },
  { value: 'politics', labelKey: 'review.catPolitics' },
  { value: 'other', labelKey: 'review.catOther' },
];

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

export default {
  name: 'ContentReviewView',
  components: { BackButton },  // 第 87 批：返回按钮
  setup() {
    const { t } = useI18n();  // 必须在 setup 内取，模板才能拿到
    const { localizedField } = useLocalized();  // 第 85 批：审核预览也显示英文译文
    const categories = computed(() => CATEGORY_KEYS.map((item) => ({ value: item.value, label: t(item.labelKey) })));
    const reportReasonLabel = (reason) =>
      REASON_KEYS[reason] ? t(REASON_KEYS[reason]) : (reason || t('review.catOther'));

    // 词条上显示的分类名：后端返回的是中文 category_display，这里用前端映射覆盖，
    // 这样切英文时分类名也能跟着变（词条内容本身仍是数据，不翻译）。
    const categoryLabel = (value) => categories.value.find((item) => item.value === value)?.label || value;
    const router = useRouter();

    const loading = ref(false);
    const pendingPosts = ref([]);
    const pendingTotal = ref(0);
    const publishedTotal = ref(0);
    const acting = ref(null);

    // ======================================================================
    // 第 96 批：待审列表真分页
    // ----------------------------------------------------------------------
    // 改前是 `fetchPostsByStatus('pending', { page_size: 20 })` 一次性取 20 条，
    // 而页头显示的是后端返回的**真实总数**（`pendingTotal`）。
    // 后果：有 25 条待审时页头写"25 条待审核"，列表里只有 20 条 —— 剩下 5 条
    // 既看不到、也没有任何提示、更没有翻页入口。审核员会以为处理完了。
    // ======================================================================
    const pendingPage = ref(1);
    const pendingPageSize = ref(10);

    const words = ref([]);
    const newWord = ref('');
    const newWordCategory = ref('ad');
    const addingWord = ref(false);

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

    const siteConfig = ref({ post_require_review: false });

    const rejectDialog = ref(false);
    const rejectReason = ref('');
    const rejectingPost = ref(null);
    const previewDialog = ref(false);
    const previewingPost = ref(null);

    const excerptOf = (post) => {
      // 第 85 批：英文界面下待审列表的摘要用 content_en（否则只有摘要栏是中文）
      const text = String(localizedField(post, 'content') || '')
        .replace(/<[^>]+>/g, ' ')
        .replace(/&nbsp;/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      return text.length > 100 ? `${text.slice(0, 100)}…` : text || t('review.noContent');
    };

    const loadPending = async () => {
      const data = await fetchPostsByStatus('pending', {
        page: pendingPage.value,
        page_size: pendingPageSize.value,
      });
      pendingPosts.value = data?.results || [];
      pendingTotal.value = data?.count || 0;
    };

    /** 第 96 批：待审分页 —— 改每页条数时回到第 1 页（否则可能落在空页上） */
    const handlePendingSizeChange = () => {
      pendingPage.value = 1;
      loadPending();
    };

    const loadPublishedCount = async () => {
      try {
        const data = await fetchPostsByStatus('published', { page_size: 1 });
        publishedTotal.value = data?.count || 0;
      } catch (error) {
        console.warn('统计已发布数量失败:', error);
      }
    };

    const loadWords = async () => {
      try {
        const data = await fetchSensitiveWords();
        words.value = Array.isArray(data) ? data : data?.results || [];
      } catch (error) {
        console.warn('加载敏感词失败:', error);
        words.value = [];
      }
    };

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
        await Promise.all([loadReports(), loadPublishedCount()]);
      } catch (error) {
        ElMessage.error(error?.response?.data?.detail || t('msg.operationFailed'));
      } finally {
        reportActing.value = null;
      }
    };

    /**
     * 表头排序 → 交给后端（`sortable="custom"`）
     */
    // ======================================================================
    // 第 100 批：批量审核
    // ======================================================================
    const selectedIds = ref([]);
    const bulkActing = ref(false);
    const bulkRejectVisible = ref(false);
    const bulkRejectReason = ref('');

    const toggleSelect = (id, checked) => {
      if (checked) {
        if (!selectedIds.value.includes(id)) selectedIds.value = [...selectedIds.value, id];
      } else {
        selectedIds.value = selectedIds.value.filter((item) => item !== id);
      }
    };

    const allPageSelected = computed(() =>
      pendingPosts.value.length > 0
      && pendingPosts.value.every((post) => selectedIds.value.includes(post.id)),
    );
    const somePageSelected = computed(() =>
      !allPageSelected.value
      && pendingPosts.value.some((post) => selectedIds.value.includes(post.id)),
    );

    const toggleSelectAllPage = (checked) => {
      const pageIds = pendingPosts.value.map((post) => post.id);
      if (checked) {
        selectedIds.value = [...new Set([...selectedIds.value, ...pageIds])];
      } else {
        selectedIds.value = selectedIds.value.filter((id) => !pageIds.includes(id));
      }
    };

    /**
     * 批量审核结果的统一提示
     *
     * ⚠️ 必须**如实报告被跳过的那几条**：批量接口逐条执行、不整体失败，
     * 如果只弹一句"完成"，管理员会以为全都通过了 —— 而实际上"已发布的帖子"
     * 这类会被跳过。所以有失败时把原因列出来。
     */
    const reportBulkResult = (result, successKey) => {
      const succeeded = result?.succeeded ?? 0;
      const failed = result?.failed ?? 0;
      if (failed > 0) {
        const reasons = (result?.results || [])
          .filter((item) => !item.ok)
          .map((item) => `#${item.id}：${item.detail}`)
          .join('；');
        ElMessage.warning(t('review.bulkPartial', { ok: succeeded, failed }) + reasons);
      } else {
        ElMessage.success(t(successKey, { count: succeeded }));
      }
    };

    const bulkApprove = async () => {
      if (!selectedIds.value.length) return;
      bulkActing.value = true;
      try {
        const result = await bulkReviewPosts(selectedIds.value, 'approve');
        reportBulkResult(result, 'review.bulkApproveOk');
        selectedIds.value = [];
        // 本页可能被清空 → 回到第 1 页（否则停在空白页）
        pendingPage.value = 1;
        await Promise.all([loadPending(), loadPublishedCount()]);
      } catch (error) {
        ElMessage.error(error?.response?.data?.detail || t('msg.operationFailed'));
      } finally {
        bulkActing.value = false;
      }
    };

    const bulkReject = async () => {
      if (!selectedIds.value.length) return;
      bulkActing.value = true;
      try {
        const result = await bulkReviewPosts(
          selectedIds.value, 'reject', bulkRejectReason.value.trim(),
        );
        reportBulkResult(result, 'review.bulkRejectOk');
        bulkRejectVisible.value = false;
        bulkRejectReason.value = '';
        selectedIds.value = [];
        pendingPage.value = 1;
        await loadPending();
      } catch (error) {
        ElMessage.error(error?.response?.data?.detail || t('msg.operationFailed'));
      } finally {
        bulkActing.value = false;
      }
    };

    const loadAll = async () => {
      loading.value = true;
      try {
        const [config] = await Promise.all([
          fetchSiteConfig().catch(() => ({ post_require_review: false })),
          loadPending(),
          loadPublishedCount(),
          loadWords(),
          loadReports(),
        ]);
        siteConfig.value = config || { post_require_review: false };
      } catch (error) {
        console.error('加载审核数据失败:', error);
        ElMessage.error(t('msg.loadFailed'));
      } finally {
        loading.value = false;
      }
    };

    const approve = async (post) => {
      acting.value = post.id;
      try {
        await approvePost(post.id);
        ElMessage.success(t('review.approvedOk'));
        // 第 96 批：批掉本页最后一条且不在第 1 页时退回上一页（避免停在空页）
        if (pendingPosts.value.length === 1 && pendingPage.value > 1) {
          pendingPage.value -= 1;
        }
        await Promise.all([loadPending(), loadPublishedCount()]);
      } catch (error) {
        ElMessage.error(error?.response?.data?.detail || t('msg.operationFailed'));
      } finally {
        acting.value = null;
      }
    };

    const openReject = (post) => {
      rejectingPost.value = post;
      rejectReason.value = '';
      rejectDialog.value = true;
    };

    const confirmReject = async () => {
      if (!rejectingPost.value) return;
      acting.value = rejectingPost.value.id;
      try {
        await rejectPost(rejectingPost.value.id, rejectReason.value.trim());
        ElMessage.success(t('review.rejectedOk'));
        rejectDialog.value = false;
        // 第 96 批：同上，拒绝掉本页最后一条时退回上一页
        if (pendingPosts.value.length === 1 && pendingPage.value > 1) {
          pendingPage.value -= 1;
        }
        await loadPending();
      } catch (error) {
        ElMessage.error(error?.response?.data?.detail || t('msg.operationFailed'));
      } finally {
        acting.value = null;
      }
    };

    const previewPost = (post) => {
      previewingPost.value = post;
      previewDialog.value = true;
    };

    const addWord = async () => {
      const word = newWord.value.trim();
      if (!word) {
        ElMessage.warning(t('review.wordRequired'));
        return;
      }
      addingWord.value = true;
      try {
        await createSensitiveWord({ word, category: newWordCategory.value });
        ElMessage.success(t('msg.addingWord', { word }));
        newWord.value = '';
        await loadWords();
      } catch (error) {
        const data = error?.response?.data;
        ElMessage.error(data?.word?.[0] || data?.detail || t('review.addWordFailed'));
      } finally {
        addingWord.value = false;
      }
    };

    const removeWord = async (item) => {
      try {
        await ElMessageBox.confirm(t('review.deleteWordConfirm', { word: item.word }), t('msg.confirmDelete'), {
          confirmButtonText: t('msg.delete'),
          cancelButtonText: t('msg.cancel'),
          type: 'warning',
        });
      } catch {
        return;
      }
      try {
        await deleteSensitiveWord(item.id);
        ElMessage.success(t('msg.deleteOk'));
        await loadWords();
      } catch (error) {
        ElMessage.error(t('msg.deleteFailed'));
      }
    };

    const goForum = () => router.push({ name: 'forum' });

    onMounted(loadAll);

    return {
      loading,
      pendingPosts,
      pendingTotal,
      publishedTotal,
      acting,
      // 第 96 批：待审列表分页
      pendingPage,
      pendingPageSize,
      handlePendingSizeChange,
      // ⚠️ `loadPending` 必须 return：分页器的 `@current-change="loadPending"` 用它，
      //    漏掉的话翻页会变成"页码变了、数据不刷新"（Vue 只在控制台打一条 warning：
      //    Property "loadPending" was accessed during render but is not defined on instance）。
      //    这一条是实测抓出来的 —— 页头写 23 条、翻页却只请求过一次。
      loadPending,
      reportReasonLabel,
      words,
      newWord,
      newWordCategory,
      addingWord,
      // 第 41 批：举报处理
      reports,
      reportsLoading,
      reportActing,
      hideContent,
      handleReport,
      // 第 96 批：举报分页
      reportsPage,
      reportsPageSize,
      reportsTotal,
      handleReportsSizeChange,
      loadReports,
      // 第 100 批：批量审核
      selectedIds, bulkActing, bulkRejectVisible, bulkRejectReason,
      toggleSelect, toggleSelectAllPage, allPageSelected, somePageSelected,
      bulkApprove, bulkReject,
      siteConfig,
      rejectDialog,
      rejectReason,
      rejectingPost,
      previewDialog,
      previewingPost,
      categories,
      categoryLabel,
      t,
      localizedField,  // 第 85 批：预览弹窗的英文标题/正文
      excerptOf,
      formatTime,
      loadAll,
      approve,
      openReject,
      confirmReject,
      previewPost,
      sanitizeRichText,  // 第 91 批：模板里要用（Options API 不 return 就是 undefined）
      addWord,
      removeWord,
      goForum,
    };
  },
};
</script>

<style scoped>
.review-page {
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 24px 20px 40px;
}

/* 第 87 批：返回按钮紧贴左边缘，和下面的深绿页头留出间距 */
.review-page > .back-button {
  margin-bottom: 12px;
}

.policy-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 15px;
  padding: 11px 15px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--ink-50);
  font-size: 13px;
  color: var(--ink-600);
}

.policy-bar.is-on {
  border-color: var(--brand-200);
  background: var(--brand-50);
  color: var(--brand-800);
}

.policy-bar code {
  padding: 1px 5px;
  border-radius: 5px;
  background: #fff;
  border: 1px solid var(--border);
  font-size: 12px;
}

.review-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 18px;
  align-items: start;
}

.review-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.review-item {
  display: flex;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid var(--brand-100);
  border-radius: var(--radius);
  background: linear-gradient(160deg, #fffdf7, #ffffff);
}

.review-main {
  flex: 1;
  min-width: 0;
}

.review-title {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 700;
  color: var(--ink-900);
}

.review-excerpt {
  margin: 0 0 8px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-500);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.review-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--ink-400);
}

.review-meta i {
  margin-right: 4px;
}

.review-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-shrink: 0;
}

.review-actions .el-button + .el-button {
  margin-left: 0;
}

/* 敏感词 */
.word-add {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.word-category {
  width: 108px;
}

.word-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 320px;
  overflow-y: auto;
}

/* 举报条目（第 41 批） */
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

.word-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--ink-50);
  font-size: 13px;
}

.word-text {
  font-weight: 600;
  color: var(--ink-800);
}

.word-cat {
  padding: 1px 7px;
  border-radius: 999px;
  background: #fff;
  border: 1px solid var(--border);
  font-size: 11px;
  color: var(--ink-500);
}

.word-off {
  font-size: 11px;
  color: #cf4436;
}

.word-del {
  margin-left: auto;
  border: none;
  background: none;
  color: var(--ink-400);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 6px;
}

.word-del:hover {
  background: #fdecea;
  color: #cf4436;
}

.reject-post-title {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 700;
  color: var(--ink-900);
}

.post-preview {
  font-size: 14px;
  line-height: 1.85;
  color: var(--ink-700);
}

.post-preview :deep(img) {
  max-width: 100%;
  border-radius: 10px;
}

@media (max-width: 1080px) {
  .review-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}

/* ============================================================================
   第 96 批：分页条
   ----------------------------------------------------------------------------
   待审列表在宽面板里右对齐；举报列表在窄侧栏里，用紧凑版并允许换行 ——
   默认的 el-pagination 在窄栏里会溢出（侧栏宽度只有 ~320px）。
   ============================================================================ */
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

/* ============================================================================
   第 100 批：批量审核
   ----------------------------------------------------------------------------
   勾选框放在每条左侧（`review-item` 原本是 flex 行），所以这里改成让勾选框与内容
   并排、操作按钮仍在右侧。全选条压在列表上方，不占额外高度太多。
   ============================================================================ */
.panel-head-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.selection-hint {
  font-size: 13px;
  font-weight: 700;
  color: var(--brand-700, #1f6343);
}

.bulk-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 2px 10px;
  border-bottom: 1px dashed var(--border, #e2ebe5);
  margin-bottom: 10px;
}

.review-check {
  margin-right: 10px;
  flex: 0 0 auto;
}
</style>

