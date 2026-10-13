<template>
  <div class="forum-admin tinted-page">
    <!-- 页头（沿用全站 .admin-hero） -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-comments"></i></span>
        <div>
          <h1>{{ t('forumAdmin.title') }}</h1>
          <p>{{ t('forumAdmin.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <!-- 版块管理是 BROADCAST 的页面，只有能管版块的人看得到这个跳转 -->
        <el-button v-if="canManageBoards" class="btn-on-brand" @click="goBoards">
          <i class="fas fa-table-columns"></i> {{ t('manage.boards') }}
        </el-button>
        <el-button plain :loading="loading" @click="loadList">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
      </div>
    </header>

    <!-- 概览小卡（各用一次 page_size=1 拿 count，与反馈页同一做法） -->
    <div class="admin-stats">
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-comments"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.total }}</div>
          <div class="stat-tile-label">{{ t('forumAdmin.statTotal') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--pending">
        <span class="stat-tile-icon"><i class="fas fa-hourglass-half"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.pending }}</div>
          <div class="stat-tile-label">{{ t('forumAdmin.statusPending') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--ok">
        <span class="stat-tile-icon"><i class="fas fa-circle-check"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.published }}</div>
          <div class="stat-tile-label">{{ t('forumAdmin.statusPublished') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--processing">
        <span class="stat-tile-icon"><i class="fas fa-eye-slash"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.hidden }}</div>
          <div class="stat-tile-label">{{ t('forumAdmin.statusHidden') }}</div>
        </div>
      </div>
    </div>

    <!-- 筛选 -->
    <div class="filter-bar">
      <el-select v-model="filters.board" :placeholder="t('forumAdmin.boardFilter')" clearable
                 style="width: 170px" @change="applyFilter" @clear="applyFilter">
        <el-option v-for="board in boards" :key="board.id"
                   :label="localizedField(board, 'name')" :value="String(board.id)" />
      </el-select>
      <el-select v-model="filters.status" :placeholder="t('forumAdmin.statusFilter')" clearable
                 style="width: 150px" @change="applyFilter" @clear="applyFilter">
        <!-- 第 166 批：显式传 all —— 公开论坛列表默认不含草稿，控制台「全部」要能看到全部状态 -->
          <el-option :label="t('forumAdmin.statusAll')" value="all" />
        <el-option :label="t('forumAdmin.statusPending')" value="pending" />
        <el-option :label="t('forumAdmin.statusPublished')" value="published" />
        <el-option :label="t('forumAdmin.statusDraft')" value="draft" />
        <el-option :label="t('forumAdmin.statusHidden')" value="hidden" />
      </el-select>
      <el-select v-model="filters.mark" :placeholder="t('forumAdmin.markFilter')" clearable
                 style="width: 140px" @change="applyFilter" @clear="applyFilter">
        <el-option :label="t('forumAdmin.markPinned')" value="pinned" />
        <el-option :label="t('forumAdmin.markEssence')" value="essence" />
      </el-select>
      <el-input v-model="filters.search" :placeholder="t('forumAdmin.searchPlaceholder')"
                clearable style="width: 240px" @clear="applyFilter" @keyup.enter="applyFilter">
        <template #prefix><i class="fas fa-search"></i></template>
        <template #append>
          <el-button @click="applyFilter"><i class="fas fa-search"></i></el-button>
        </template>
      </el-input>
      <el-button plain :disabled="!hasFilter" @click="resetFilters">
        <i class="fas fa-rotate-left"></i> {{ t('forumAdmin.resetFilters') }}
      </el-button>
      <span class="total-hint">{{ t('forumAdmin.totalHint', { count: total }) }}</span>
    </div>

    <!-- 批量操作条：只有能操作帖子的人才看得到 -->
    <div v-if="canModerate" class="bulk-bar">
      <span v-if="selectedIds.length" class="bulk-count">
        {{ t('forumAdmin.selectedCount', { count: selectedIds.length }) }}
      </span>
      <span v-else class="bulk-count muted">{{ t('forumAdmin.selectHint') }}</span>
      <div class="bulk-actions">
        <el-button size="small" type="primary" :disabled="!selectedIds.length || bulkActing"
                   @click="bulkAct('approve')">
          <i class="fas fa-check"></i> {{ t('review.bulkApprove') }}
        </el-button>
        <el-button size="small" type="danger" plain :disabled="!selectedIds.length || bulkActing"
                   @click="openBulkReject">
          <i class="fas fa-xmark"></i> {{ t('review.bulkReject') }}
        </el-button>
        <!-- 批量删帖是不可逆的破坏性操作：只给全权管理员（后端也是 403） -->
        <el-button v-if="canDelete" size="small" type="danger" :disabled="!selectedIds.length"
                   :loading="bulkDeleting" @click="bulkRemove">
          <i class="fas fa-trash"></i> {{ t('forumAdmin.bulkDelete') }}
        </el-button>
        <el-button v-if="selectedIds.length" size="small" text @click="clearSelection">
          {{ t('review.clearSelection') }}
        </el-button>
      </div>
    </div>

    <!-- 列表 -->
    <el-table
      v-loading="loading"
      :data="items"
      row-key="id"
      class="admin-table"
      @selection-change="onSelectionChange"
    >
      <el-table-column v-if="canModerate" type="selection" width="46" reserve-selection />

      <el-table-column :label="t('forumAdmin.colTitle')" min-width="320">
        <template #default="{ row }">
          <div class="post-title-cell">
            <el-tag v-if="row.is_pinned" size="small" type="danger" effect="dark">{{ t('forum.tagPinned') }}</el-tag>
            <el-tag v-if="row.is_essence" size="small" type="warning" effect="dark">{{ t('forum.tagEssence') }}</el-tag>
            <span class="post-title-text">{{ localizedField(row, 'title') || t('forum.untitled') }}</span>
          </div>
          <div class="post-sub">
            <span><i class="fas fa-user"></i> {{ row.author?.username || t('forum.unknownUser') }}</span>
            <span v-if="row.board"><i class="fas fa-layer-group"></i> {{ localizedField(row.board, 'name') }}</span>
            <span><i class="fas fa-clock"></i> {{ formatTime(row.created_at, 'YYYY-MM-DD HH:mm') }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column :label="t('forumAdmin.colStatus')" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="statusTagType(row.status)" effect="light">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('forumAdmin.colStats')" width="150">
        <template #default="{ row }">
          <span class="muted">
            {{ t('forumAdmin.statCell', { views: row.view_count || 0, comments: row.comment_count || 0 }) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column :label="t('forumAdmin.colActions')" width="330" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text @click="preview(row)">
            {{ t('review.view') }}
          </el-button>
          <el-button v-if="row.status === 'pending'" size="small" type="primary" link
                     :loading="acting === row.id" @click="approve(row)">
            {{ t('review.approve') }}
          </el-button>
          <el-button v-if="row.status === 'pending'" size="small" type="danger" link
                     @click="openReject(row)">
            {{ t('review.reject') }}
          </el-button>
          <!--
            第 182 批：**已发布**的帖子给一个「下架」入口。
            原先界面上没有任何办法撤回已发布的内容：单条驳回只对待审显示、
            批量驳回（后端）只处理 pending —— 用户反馈"点批量驳回没用"就是这个。
            后端第 182 批已允许驳回处理 published（语义=下架，可再次通过恢复），
            这里补上对应入口，走同一个驳回对话框（要填理由，进审核轨迹）。
          -->
          <el-button v-if="row.status === 'published' && canModerate" size="small"
                     type="warning" link @click="openReject(row)">
            {{ t('review.unpublish') }}
          </el-button>
          <el-button v-if="canModerate" size="small" link
                     :type="row.is_pinned ? 'danger' : 'default'"
                     :loading="acting === `pin-${row.id}`" @click="togglePin(row)">
            {{ row.is_pinned ? t('forum.unpinAction') : t('forum.pinAction') }}
          </el-button>
          <el-button v-if="canModerate" size="small" link
                     :type="row.is_essence ? 'warning' : 'default'"
                     :loading="acting === `essence-${row.id}`" @click="toggleEssence(row)">
            {{ row.is_essence ? t('forum.unessenceAction') : t('forum.essenceAction') }}
          </el-button>
          <!-- 第 181 批：删帖只给全权管理员（后端 CanDeletePost 的既定口径）—— 原先这个按钮**没有任何 v-if**，编辑员看得到、点了必然 403 -->
          <el-button v-if="canDelete" size="small" type="danger" link title="仅全权管理员可删除帖子；编辑员请用【驳回】或软删评论处置" @click="removeOne(row)">
            {{ t('feedbackAdmin.delete') }}
          </el-button>
        </template>
      </el-table-column>

      <template #empty>
        <el-empty :description="t('forumAdmin.empty')" :image-size="80" />
      </template>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[10, 20, 50]"
      layout="total, sizes, prev, pager, next"
      class="admin-pagination"
      @current-change="loadList"
      @size-change="handleSizeChange"
    />

    <!-- 帖子预览（内容较长，放弹窗里看，避免列表被撑开） -->
    <el-dialog v-model="previewVisible" :title="previewPost_?.title || t('forumAdmin.previewTitle')"
               width="720px">
      <div v-if="previewPost_" class="preview-body">
        <p class="preview-meta">
          <span><i class="fas fa-user"></i> {{ previewPost_.author?.username || t('forum.unknownUser') }}</span>
          <span><i class="fas fa-layer-group"></i> {{ previewPost_.board?.name || '' }}</span>
          <span><i class="fas fa-clock"></i> {{ formatTime(previewPost_.created_at, 'YYYY-MM-DD HH:mm') }}</span>
        </p>
        <div class="preview-content" v-html="previewPost_.content || t('forumAdmin.noContent')"></div>
      </div>
      <template #footer>
        <el-button @click="previewVisible = false">{{ t('common.close') }}</el-button>
        <el-button type="primary" @click="openInSite">
          {{ t('forumAdmin.openInSite') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 驳回原因（批量与单条共用同一个弹窗） -->
    <el-dialog v-model="rejectVisible" :title="t('review.rejectDialogTitle')" width="460px"
               :close-on-click-modal="false">
      <el-input v-model="rejectReason" type="textarea" :rows="3" maxlength="200" show-word-limit
                :placeholder="t('review.rejectReasonPlaceholder')" />
      <p class="field-hint">{{ t('review.rejectDialogHint') }}</p>
      <template #footer>
        <el-button @click="rejectVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="danger" :loading="rejecting" :disabled="!rejectReason.trim()"
                   @click="confirmReject">
          {{ t('review.confirmReject') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
/**
 * 管理端「论坛管理」（第 147 批）
 *
 * ## 为什么要有这一页
 *
 * 在此之前控制台里只能管理**待审核**的帖子（内容审核页），而论坛的内容远不止待审：
 * 已经发布的帖子里有广告、有吵架、有需要置顶加精的好帖 —— 但控制台**看不到它们**：
 *   · 想看已发布的帖子，只能回到农户端的论坛列表（那是给农户看的页面）；
 *   · 想删一条已发布的帖子，控制台没有入口；
 *   · 置顶/加精虽然第 145 批在论坛列表上给了开关，但那是"浏览时顺手点"，
 *     不能按版块/状态/关键字去**找**该处理的帖子。
 *
 * 这一页把论坛帖子当成一类**可管理的内容**：按版块/状态/置顶精华/关键字筛选，
 * 行内通过·驳回·置顶·加精，批量通过/驳回/删除。
 * ⚠️ 第 181 批：行内【删除】只给全权管理员 —— 后端 CanDeletePost 明确不给信息编辑员
 *   （帖子删除不在编辑员能力矩阵里；编辑员用驳回 + 软删评论处置内容）。
 *   此处原按 canModerate 显示，编辑员点了必然 403 —— 按钮在、权限没有。
 *
 * ## 权限（三层口径一致）
 *
 * · **看与审**：`review` 内容模块（信息编辑员即可）—— 与后端
 *   `is_moderator()`、以及内容审核页同一口径；
 * · **批量驳回**：待审与**已发布**都能处理（后者语义是撤回发布=下架，可再次通过恢复）；
 *   已驳回的不重复处理，且会在结果里**说明原因**（第 182 批前是静默跳过）。
 * · **批量删除**：仅全权管理员（不可逆的破坏性操作，后端 `bulk_delete` 也是 403）；
 * · **版块管理**：BROADCAST，只有能管版块的人才看到那个跳转按钮。
 *
 * ## 几个刻意的取舍
 *
 * 1. **不做"假批量"**：批量通过/驳回走后端现成的 `bulk-review`（逐条成败、
 *    只处理待审、上限 200），批量删除走后端新加的 `bulk-delete` —— 不在前端循环发 N 个请求，
 *    那样既慢又没法给出"哪几条失败了"的一致结果。
 * 2. **删除是软删除**：评论、点赞、收藏都留在库里（后端 `post.soft_delete()`），
 *    真正的清理走管理命令。所以确认框里写的是"从论坛移除"而不是"彻底删除"。
 * 3. **预览用弹窗**：列表里放正文会把行撑得很高；弹窗里另给一个"在站内打开"的出口。
 */
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getForumBoards, getPosts, setPostEssence, setPostPinned } from '@/api/forum';
import { approvePost, bulkReviewPosts, rejectPost } from '@/api/content';
import { bulkDeletePosts } from '@/api/forum';
import { formatApiError } from '@/api/http';
import { formatTime } from '@/utils/date';
import { useI18n } from '@/i18n';
import { useLocalized } from '@/utils/localized';
import { useAuthStore } from '@/stores/auth';
import { useQueryState } from '@/composables/useQueryState';

export default {
  name: 'AdminForumView',
  setup() {
    const { t } = useI18n();
    const { localizedField } = useLocalized();
    const router = useRouter();
    const authStore = useAuthStore();

    const items = ref([]);
    const total = ref(0);
    const loading = ref(false);
    const page = ref(1);
    const pageSize = ref(10);
    const boards = ref([]);
    // 第 166 批：默认就是 'all'（不是空串）—— 公开论坛列表默认不含草稿，
      // 而控制台一进来就该看到全部状态（第 147 批的设计），所以默认显式要 all。
      const filters = ref({ board: '', status: 'all', mark: '', search: '' });
    const stats = ref({ total: 0, pending: 0, published: 0, hidden: 0 });

    const acting = ref('');
    const bulkActing = ref(false);
    const bulkDeleting = ref(false);
    const selectedIds = ref([]);
    const selectedRows = ref([]);

    const previewVisible = ref(false);
    const previewPost_ = ref(null);
    const rejectVisible = ref(false);
    const rejecting = ref(false);
    const rejectReason = ref('');
    const rejectTarget = ref(null);      // null = 批量驳回
    const bulkRejectMode = ref(false);

    // -- 权限 ---------------------------------------------------------------
    /**
     * 能审核 / 置顶 / 加精 / 删除：与后端 `is_moderator()` 对齐
     *
     * 第 151 批：`forum`（论坛交流）也算 —— 只勾这一个模块的编辑员就是"论坛管理员"，
     * 不给他按钮等于这个模块名不副实（E2E 就是这么发现漏改的：后端放行、页面上一个按钮都没有）。
     * 前端仍判不了 Moderators 组（组信息没下发），那种用户看不到按钮但后端放行 —— 见第 145 批说明。
     */
    const canModerate = computed(() => Boolean(
      authStore.hasContentModule?.('review')
      || authStore.hasContentModule?.('forum')
      || authStore.user?.is_staff
      || authStore.user?.is_superuser,
    ));
    /** 能批量删除：仅全权管理员 */
    const canDelete = computed(() => Boolean(authStore.isAdmin));
    const canManageBoards = computed(() => Boolean(
      authStore.hasCapability?.(authStore.CAP_BROADCAST) || authStore.user?.is_superuser,
    ));

    // -- 状态标签 -----------------------------------------------------------
    const statusLabel = (status) => ({
      pending: t('forumAdmin.statusPending'),
      published: t('forumAdmin.statusPublished'),
      draft: t('forumAdmin.statusDraft'),
      hidden: t('forumAdmin.statusHidden'),
    }[status] || status);

    const statusTagType = (status) => ({
      pending: 'warning',
      published: 'success',
      draft: 'info',
      hidden: 'danger',
    }[status] || 'info');

    // -- 数据 ---------------------------------------------------------------
    const buildParams = () => {
      const params = { page: page.value, page_size: pageSize.value };
      if (filters.value.board) params.board = filters.value.board;
      if (filters.value.status) params.status = filters.value.status;
      if (filters.value.mark === 'pinned') params.ordering = 'pinned';
      if (filters.value.mark === 'essence') params.is_essence = 'true';
      if (filters.value.search.trim()) params.search = filters.value.search.trim();
      return params;
    };

    const loadList = async () => {
      loading.value = true;
      try {
        const data = await getPosts(buildParams());
        items.value = data.results || data || [];
        total.value = data.count ?? items.value.length;
      } catch (error) {
        ElMessage.error(formatApiError(error, t('forumAdmin.loadFailed')));
      } finally {
        loading.value = false;
      }
    };

    /** 概览：各状态各查一次 count（page_size=1 只为拿 count，与反馈页一致） */
    const loadStats = async () => {
      try {
        const [all, pending, published, hidden] = await Promise.all([
          getPosts({ page: 1, page_size: 1 }),
          getPosts({ page: 1, page_size: 1, status: 'pending' }),
          getPosts({ page: 1, page_size: 1, status: 'published' }),
          getPosts({ page: 1, page_size: 1, status: 'hidden' }),
        ]);
        stats.value = {
          total: all?.count || 0,
          pending: pending?.count || 0,
          published: published?.count || 0,
          hidden: hidden?.count || 0,
        };
      } catch (error) {
        console.warn('论坛统计加载失败:', error);
      }
    };

    const loadBoards = async () => {
      try {
        const data = await getForumBoards();
        boards.value = Array.isArray(data) ? data : (data?.results || []);
      } catch (error) {
        console.warn('版块列表加载失败:', error);
      }
    };

    const reload = () => Promise.all([loadList(), loadStats()]);

    const applyFilter = () => { page.value = 1; loadList(); };
    const handleSizeChange = () => { page.value = 1; loadList(); };
    const hasFilter = computed(() => Boolean(
      filters.value.board || filters.value.status || filters.value.mark || filters.value.search.trim(),
    ));
    const resetFilters = () => {
      // 第 166 批：重置回 'all'（= 不过滤状态，含草稿）而不是空串 ——
      // 空串会让控制台落到"默认排除草稿"的公开列表口径上，与「全部状态」的语义不符。
      filters.value = { board: '', status: 'all', mark: '', search: '' };
      applyFilter();
    };

    // 第 98 批的约定：筛选与分页进 URL（刷新/分享不丢）
    const { isReady: queryReady } = useQueryState({
      fields: {
        page: { ref: page, type: 'int', default: 1 },
        page_size: { ref: pageSize, type: 'int', default: 10 },
        board: { ref: { get value() { return filters.value.board; },
                       set value(v) { filters.value.board = v ?? ''; } }, type: 'string', default: '' },
        status: { ref: { get value() { return filters.value.status; },
                        // 第 166 批：URL 里没有 status 时，恢复成 'all'（= 不做状态过滤）而不是空串。
                        // 空串在公开列表口径里意味着"默认排除草稿"，而控制台的「全部」
                        // 是要看全部状态（第 147 批的设计，有测试盯着）。
                        set value(v) { filters.value.status = v ?? 'all'; } }, type: 'string', default: 'all' },
        mark: { ref: { get value() { return filters.value.mark; },
                      set value(v) { filters.value.mark = v ?? ''; } }, type: 'string', default: '' },
        search: { ref: { get value() { return filters.value.search; },
                        set value(v) { filters.value.search = v ?? ''; } }, type: 'string', default: '' },
      },
      onExternalChange: () => reload(),
    });

    // -- 选择 ---------------------------------------------------------------
    const onSelectionChange = (rows) => {
      selectedRows.value = rows;
      selectedIds.value = rows.map((row) => row.id);
    };
    const clearSelection = () => {
      selectedIds.value = [];
      selectedRows.value = [];
    };

    // -- 行内动作 -----------------------------------------------------------
    const approve = async (row) => {
      acting.value = row.id;
      try {
        await approvePost(row.id);
        row.status = 'published';   // 就地更新，先给个即时反馈
        ElMessage.success(t('review.approvedOk'));
        // ⚠️ 必须重新拉列表：在"按状态筛选"的视图里（比如只看待审核），
        //    刚刚通过的帖子已经不属于这个筛选结果了 —— 不刷新它会赖在列表里，
        //    管理员以为没生效、再点一次（第二版才发现的问题）。
        await reload();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('forumAdmin.approveFailed')));
      } finally {
        acting.value = '';
      }
    };

    const openReject = (row) => {
      rejectTarget.value = row;
      bulkRejectMode.value = false;
      rejectReason.value = '';
      rejectVisible.value = true;
    };

    const openBulkReject = () => {
      rejectTarget.value = null;
      bulkRejectMode.value = true;
      rejectReason.value = '';
      rejectVisible.value = true;
    };

    const confirmReject = async () => {
      const reason = rejectReason.value.trim();
      if (!reason) {
        ElMessage.warning(t('forumAdmin.rejectReasonRequired'));
        return;
      }
      rejecting.value = true;
      try {
        if (bulkRejectMode.value) {
          const data = await bulkReviewPosts(selectedIds.value, 'reject', reason);
          reportBulk(data, 'review.bulkRejectOk', 'review.bulkPartial');
          clearSelection();
        } else {
          await rejectPost(rejectTarget.value.id, reason);
          rejectTarget.value.status = 'hidden';
          ElMessage.success(t('review.rejectedOk'));
        }
        rejectVisible.value = false;
        await reload();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('forumAdmin.rejectFailed')));
      } finally {
        rejecting.value = false;
      }
    };

    const bulkAct = async (action) => {
      if (action === 'reject') {
        openBulkReject();
        return;
      }
      bulkActing.value = true;
      try {
        const data = await bulkReviewPosts(selectedIds.value, 'approve');
        reportBulk(data, 'review.bulkApproveOk', 'review.bulkPartial');
        clearSelection();
        await reload();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('forumAdmin.bulkApproveFailed')));
      } finally {
        bulkActing.value = false;
      }
    };

    /** 逐条成败的结果提示（批量接口不整体失败） */
    const reportBulk = (data, okKey, partialKey) => {
      if (!data || data.failed === 0) {
        ElMessage.success(t(okKey, { count: data?.succeeded ?? 0 }));
        return;
      }
      ElMessage.warning(t(partialKey, { ok: data.succeeded, failed: data.failed }));
    };

    const togglePin = async (row) => {
      acting.value = `pin-${row.id}`;
      try {
        const data = await setPostPinned(row.id, !row.is_pinned);
        row.is_pinned = data?.is_pinned ?? !row.is_pinned;
        ElMessage.success(row.is_pinned ? t('forum.pinOk') : t('forum.unpinOk'));
      } catch (error) {
        ElMessage.error(formatApiError(error, t('forum.pinFailed')));
      } finally {
        acting.value = '';
      }
    };

    const toggleEssence = async (row) => {
      acting.value = `essence-${row.id}`;
      try {
        const data = await setPostEssence(row.id, !row.is_essence);
        row.is_essence = data?.is_essence ?? !row.is_essence;
        ElMessage.success(row.is_essence ? t('forum.essenceOk') : t('forum.unessenceOk'));
      } catch (error) {
        ElMessage.error(formatApiError(error, t('forum.essenceFailed')));
      } finally {
        acting.value = '';
      }
    };

    const removeOne = async (row) => {
      try {
        await ElMessageBox.confirm(
          t('forumAdmin.deleteConfirm', { title: localizedField(row, 'title') }),
          t('forumAdmin.deleteAction'),
          { type: 'warning', confirmButtonText: t('forumAdmin.deleteAction'),
            cancelButtonText: t('common.cancel') },
        );
      } catch {
        return;
      }
      try {
        await bulkDeletePosts([row.id]);
        ElMessage.success(t('forumAdmin.deleteOk'));
        await reload();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('forumAdmin.deleteFailed')));
      }
    };

    const bulkRemove = async () => {
      const count = selectedIds.value.length;
      try {
        await ElMessageBox.confirm(
          t('forumAdmin.bulkDeleteConfirm', { count }),
          t('forumAdmin.bulkDelete'),
          { type: 'warning', confirmButtonText: t('forumAdmin.bulkDelete'),
            cancelButtonText: t('common.cancel') },
        );
      } catch {
        return;
      }
      bulkDeleting.value = true;
      try {
        const data = await bulkDeletePosts(selectedIds.value);
        reportBulk(data, 'forumAdmin.bulkDeleteOk', 'forumAdmin.bulkDeletePartial');
        clearSelection();
        await reload();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('forumAdmin.bulkDeleteFailed')));
      } finally {
        bulkDeleting.value = false;
      }
    };

    // -- 预览 / 跳转 ---------------------------------------------------------
    const preview = (row) => {
      previewPost_.value = row;
      previewVisible.value = true;
    };
    const openInSite = () => {
      const id = previewPost_.value?.id;
      if (!id) return;
      window.open(router.resolve({ name: 'post-detail', params: { id } }).href, '_blank');
    };
    const goBoards = () => router.push('/admin/boards');

    onMounted(() => {
      loadBoards();
    });
    // 第 98 批的约定：**等 URL 参数应用完**再查，避免"带参数打开链接"时先按默认值查一次
    // （上面那版我误写成 `router.afterEach` —— 那是给全局导航挂钩子，跟这里没关系）
    watch(queryReady, (ready) => {
      if (ready) reload();
    }, { immediate: true });

    return {
      t,
      items, total, loading, page, pageSize, boards, filters, stats,
      selectedIds, acting, bulkActing, bulkDeleting,
      canModerate, canDelete, canManageBoards,
      statusLabel, statusTagType, localizedField, formatTime,
      loadList, applyFilter, handleSizeChange, resetFilters, hasFilter,
      onSelectionChange, clearSelection,
      approve, openReject, openBulkReject, confirmReject, bulkAct,
      togglePin, toggleEssence, removeOne, bulkRemove,
      previewVisible, previewPost_, preview, openInSite, goBoards,
      rejectVisible, rejecting, rejectReason,
    };
  },
};
</script>

<style scoped>
.post-title-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: var(--ink-800);
}

.post-title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.post-sub {
  margin-top: 4px;
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--ink-400, #9dada5);
}

.bulk-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--ink-50);
}

.bulk-count {
  font-size: 13px;
  font-weight: 600;
  color: var(--brand-700, #1c6b4b);
}

.bulk-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.preview-meta {
  display: flex;
  gap: 14px;
  font-size: 12.5px;
  color: var(--ink-400, #9dada5);
  margin: 0 0 10px;
}

.preview-content {
  max-height: 420px;
  overflow-y: auto;
  line-height: 1.7;
}

.admin-pagination {
  margin-top: 14px;
  justify-content: flex-end;
}
</style>
