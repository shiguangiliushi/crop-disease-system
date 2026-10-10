<template>
  <div class="comment-admin tinted-page">
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-comment-dots"></i></span>
        <div>
          <h1>{{ t('commentAdmin.title') }}</h1>
          <p>{{ t('commentAdmin.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-button plain :loading="loading" @click="loadList">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
      </div>
    </header>

    <div class="filter-bar">
      <el-select v-model="filters.scope" :placeholder="t('commentAdmin.scopeFilter')"
                 style="width: 160px" @change="applyFilter">
        <el-option :label="t('commentAdmin.scopeNormal')" value="" />
        <el-option :label="t('commentAdmin.scopeDeleted')" value="deleted" />
      </el-select>
      <el-input v-model="filters.search" :placeholder="t('commentAdmin.searchPlaceholder')"
                clearable style="width: 260px" @clear="applyFilter" @keyup.enter="applyFilter">
        <template #prefix><i class="fas fa-search"></i></template>
        <template #append>
          <el-button @click="applyFilter"><i class="fas fa-search"></i></el-button>
        </template>
      </el-input>
      <el-button plain :disabled="!hasFilter" @click="resetFilters">
        <i class="fas fa-rotate-left"></i> {{ t('commentAdmin.resetFilters') }}
      </el-button>
      <span class="total-hint">{{ t('commentAdmin.totalHint', { count: total }) }}</span>
    </div>

    <!-- 批量条：只有"能审核"的人看得到（软删除=审核工作） -->
    <div v-if="canModerate" class="bulk-bar">
      <span v-if="selectedIds.length" class="bulk-count">
        {{ t('commentAdmin.selectedCount', { count: selectedIds.length }) }}
      </span>
      <span v-else class="bulk-count muted">{{ t('commentAdmin.selectHint') }}</span>
      <div class="bulk-actions">
        <el-button size="small" type="danger" plain :disabled="!selectedIds.length"
                   :loading="bulkActing" @click="bulkRemove">
          <i class="fas fa-trash"></i> {{ t('commentAdmin.bulkDelete') }}
        </el-button>
        <el-button v-if="selectedIds.length" size="small" text @click="clearSelection">
          {{ t('review.clearSelection') }}
        </el-button>
      </div>
    </div>

    <el-table
      v-loading="loading"
      :data="items"
      row-key="id"
      class="admin-table"
      @selection-change="onSelectionChange"
    >
      <el-table-column v-if="canModerate" type="selection" width="46"
                       :selectable="(row) => !row.is_deleted" reserve-selection />

      <el-table-column :label="t('commentAdmin.colContent')" min-width="330">
        <template #default="{ row }">
          <div class="comment-text" :class="{ 'is-deleted': row.is_deleted }">
            {{ row.content || t('commentAdmin.emptyContent') }}
          </div>
          <div class="comment-sub">
            <span><i class="fas fa-user"></i> {{ row.author?.username || t('forum.unknownUser') }}</span>
            <span><i class="fas fa-clock"></i> {{ formatTime(row.created_at, 'YYYY-MM-DD HH:mm') }}</span>
            <span v-if="row.parent"><i class="fas fa-reply"></i> {{ t('commentAdmin.isReply') }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column :label="t('commentAdmin.colPost')" min-width="200">
        <template #default="{ row }">
          <el-button v-if="row.post" link type="primary" @click="openPost(row.post.id)">
            {{ row.post.title || `#${row.post.id}` }}
          </el-button>
          <span v-else class="muted">{{ t('commentAdmin.postGone') }}</span>
        </template>
      </el-table-column>

      <el-table-column :label="t('commentAdmin.colStatus')" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="row.is_deleted ? 'info' : 'success'" effect="light">
            {{ row.is_deleted ? t('commentAdmin.statusDeleted') : t('commentAdmin.statusNormal') }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('commentAdmin.colActions')" width="210" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!row.is_deleted" size="small" type="danger" link @click="softRemove(row)">
            {{ t('commentAdmin.softDelete') }}
          </el-button>
          <!-- 硬删除不可逆：只给全权管理员画这个按钮（后端也是 403） -->
          <el-button v-if="canHardDelete" size="small" type="danger" link @click="hardRemove(row)">
            {{ t('commentAdmin.hardDelete') }}
          </el-button>
          <span v-if="row.is_deleted && !canHardDelete" class="muted">—</span>
        </template>
      </el-table-column>

      <template #empty>
        <el-empty :description="t('commentAdmin.empty')" :image-size="80" />
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
  </div>
</template>

<script>
/**
 * 管理端「评论管理」（第 149 批）
 *
 * ## 为什么要有这一页
 *
 * 论坛的帖子有「论坛管理」页，但**评论一直没有控制台入口**：
 * 一波广告往往刷在十几条帖子的评论区里，管理员只能一条条帖子点进去删。
 * 农户端的评论列表还是**挂在帖子下**的（`forums/posts/<id>/comments/`），
 * 根本没有"跨帖子看最近评论"的地方 —— 所以这一批后端补了一套全局接口
 * （`/api/admin/comments/`），页面才有东西可接。
 *
 * ## 权限（两层，与后端一致）
 *
 * · **看 + 软删除 + 批量软删除**：`review` 内容模块（信息编辑员即可）——
 *   软删除是内容审核的日常工作（内容置为 `[已删除]`、行还在、可追溯）；
 * · **硬删除**（从库里真删、不可逆）：**仅全权管理员** —— 按钮只给这类人画，
 *   后端 `AdminCommentHardDeleteView` 同样 403。批量**不提供**硬删除：
 *   批量不可逆的成批破坏，控制台不该有那个按钮。
 */
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  bulkSoftDeleteComments, fetchAdminComments, hardDeleteComment, softDeleteComment,
} from '@/api/adminComment';
import { formatApiError } from '@/api/http';
import { formatTime } from '@/utils/date';
import { useI18n } from '@/i18n';
import { useAuthStore } from '@/stores/auth';
import { useQueryState } from '@/composables/useQueryState';

export default {
  name: 'AdminCommentsView',
  setup() {
    const { t } = useI18n();
    const router = useRouter();
    const authStore = useAuthStore();

    const items = ref([]);
    const total = ref(0);
    const loading = ref(false);
    const page = ref(1);
    const pageSize = ref(10);
    const filters = ref({ search: '', scope: '' });
    const selectedIds = ref([]);
    const bulkActing = ref(false);

    /** 能审核 = 能看评论管理、能软删（与后端 review 模块判定对齐） */
    const canModerate = computed(() => Boolean(
      authStore.hasContentModule?.('review')
      || authStore.user?.is_staff
      || authStore.user?.is_superuser,
    ));
    /** 能彻底删除：仅全权管理员 */
    const canHardDelete = computed(() => Boolean(authStore.isAdmin));

    const buildParams = () => {
      const params = { page: page.value, page_size: pageSize.value };
      if (filters.value.search.trim()) params.search = filters.value.search.trim();
      if (filters.value.scope === 'deleted') params.only_deleted = 'true';
      return params;
    };

    const loadList = async () => {
      loading.value = true;
      try {
        const data = await fetchAdminComments(buildParams());
        items.value = data.results || [];
        total.value = data.count ?? items.value.length;
      } catch (error) {
        ElMessage.error(formatApiError(error, t('commentAdmin.loadFailed')));
      } finally {
        loading.value = false;
      }
    };

    const applyFilter = () => { page.value = 1; loadList(); };
    const handleSizeChange = () => { page.value = 1; loadList(); };
    const hasFilter = computed(() => Boolean(filters.value.search.trim() || filters.value.scope));
    const resetFilters = () => {
      filters.value = { search: '', scope: '' };
      applyFilter();
    };

    const onSelectionChange = (rows) => { selectedIds.value = rows.map((row) => row.id); };
    const clearSelection = () => { selectedIds.value = []; };

    const softRemove = async (row) => {
      try {
        await ElMessageBox.confirm(
          t('commentAdmin.softDeleteConfirm'),
          t('commentAdmin.softDelete'),
          { type: 'warning', confirmButtonText: t('commentAdmin.softDelete'),
            cancelButtonText: t('common.cancel') },
        );
      } catch {
        return;
      }
      try {
        await softDeleteComment(row.id);
        ElMessage.success(t('commentAdmin.softDeleteOk'));
        await loadList();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('commentAdmin.softDeleteFailed')));
      }
    };

    const hardRemove = async (row) => {
      try {
        await ElMessageBox.confirm(
          t('commentAdmin.hardDeleteConfirm'),
          t('commentAdmin.hardDelete'),
          { type: 'error', confirmButtonText: t('commentAdmin.hardDelete'),
            cancelButtonText: t('common.cancel') },
        );
      } catch {
        return;
      }
      try {
        await hardDeleteComment(row.id);
        ElMessage.success(t('commentAdmin.hardDeleteOk'));
        await loadList();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('commentAdmin.hardDeleteFailed')));
      }
    };

    const bulkRemove = async () => {
      const count = selectedIds.value.length;
      try {
        await ElMessageBox.confirm(
          t('commentAdmin.bulkDeleteConfirm', { count }),
          t('commentAdmin.bulkDelete'),
          { type: 'warning', confirmButtonText: t('commentAdmin.bulkDelete'),
            cancelButtonText: t('common.cancel') },
        );
      } catch {
        return;
      }
      bulkActing.value = true;
      try {
        const data = await bulkSoftDeleteComments(selectedIds.value);
        if (!data || data.failed === 0) {
          ElMessage.success(t('commentAdmin.bulkDeleteOk', { count: data?.succeeded ?? 0 }));
        } else {
          ElMessage.warning(t('review.bulkPartial', { ok: data.succeeded, failed: data.failed }));
        }
        clearSelection();
        await loadList();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('commentAdmin.bulkDeleteFailed')));
      } finally {
        bulkActing.value = false;
      }
    };

    const openPost = (postId) => {
      window.open(router.resolve({ name: 'post-detail', params: { id: postId } }).href, '_blank');
    };

    // 筛选与分页进 URL（第 98 批约定）
    const filterRef = (key) => ({
      get value() { return filters.value[key]; },
      set value(next) { filters.value[key] = next ?? ''; },
    });
    const { isReady: queryReady } = useQueryState({
      fields: {
        page: { ref: page, type: 'int', default: 1 },
        page_size: { ref: pageSize, type: 'int', default: 10 },
        search: { ref: filterRef('search'), type: 'string', default: '' },
        scope: { ref: filterRef('scope'), type: 'string', default: '' },
      },
      onExternalChange: () => loadList(),
    });

    watch(queryReady, (ready) => {
      if (ready) loadList();
    }, { immediate: true });

    return {
      t,
      items, total, loading, page, pageSize, filters, selectedIds, bulkActing,
      canModerate, canHardDelete,
      loadList, applyFilter, handleSizeChange, resetFilters, hasFilter,
      onSelectionChange, clearSelection,
      softRemove, hardRemove, bulkRemove, openPost, formatTime,
    };
  },
};
</script>

<style scoped>
.comment-text {
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--ink-800);
  word-break: break-word;
}

.comment-text.is-deleted {
  color: var(--ink-400, #9dada5);
  font-style: italic;
}

.comment-sub {
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

.admin-pagination {
  margin-top: 14px;
  justify-content: flex-end;
}
</style>
