<template>
  <div class="audit-page tinted-page">
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-clipboard-list"></i></span>
        <div>
          <h1>{{ t('auditLog.title') }}</h1>
          <p>{{ t('auditLog.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-button plain :loading="loading" @click="loadList">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
      </div>
    </header>

    <!-- 只读声明：把它写在页面上，而不是只写在代码注释里 -->
    <el-alert type="info" :closable="false" show-icon class="readonly-note">
      {{ t('auditLog.readonlyNote') }}
    </el-alert>

    <div class="filter-bar">
      <el-select v-model="filters.action" :placeholder="t('auditLog.actionFilter')" clearable
                 filterable style="width: 210px" @change="applyFilter" @clear="applyFilter">
        <el-option v-for="item in actions" :key="item.value"
                   :label="item.label" :value="item.value" />
      </el-select>
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        :range-separator="t('auditLog.rangeSeparator')"
        :start-placeholder="t('auditLog.startDate')"
        :end-placeholder="t('auditLog.endDate')"
        style="width: 260px"
        @change="applyFilter"
      />
      <el-input v-model="filters.search" :placeholder="t('auditLog.searchPlaceholder')"
                clearable style="width: 260px" @clear="applyFilter" @keyup.enter="applyFilter">
        <template #prefix><i class="fas fa-search"></i></template>
        <template #append>
          <el-button @click="applyFilter"><i class="fas fa-search"></i></el-button>
        </template>
      </el-input>
      <el-button plain :disabled="!hasFilter" @click="resetFilters">
        <i class="fas fa-rotate-left"></i> {{ t('auditLog.resetFilters') }}
      </el-button>
      <span class="total-hint">{{ t('auditLog.totalHint', { count: total }) }}</span>
    </div>

    <el-table v-loading="loading" :data="items" row-key="id" class="admin-table">
      <el-table-column :label="t('auditLog.colTime')" width="170">
        <template #default="{ row }">
          {{ formatTime(row.created_at, 'YYYY-MM-DD HH:mm:ss') }}
        </template>
      </el-table-column>

      <el-table-column :label="t('auditLog.colActor')" width="150">
        <template #default="{ row }">
          <span :class="{ muted: !row.actor }">{{ row.actor_name || t('auditLog.systemActor') }}</span>
        </template>
      </el-table-column>

      <el-table-column :label="t('auditLog.colAction')" width="170">
        <template #default="{ row }">
          <el-tag size="small" :type="actionTagType(row.action)" effect="light">
            {{ row.action_display || row.action }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('auditLog.colTarget')" width="220">
        <template #default="{ row }">
          <span v-if="row.target_name || row.target_id">
            {{ row.target_name || `#${row.target_id}` }}
            <span class="muted">（{{ targetTypeLabel(row.target_type) }}）</span>
          </span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>

      <el-table-column :label="t('auditLog.colDetail')" min-width="260">
        <template #default="{ row }">
          <!-- 说明是给人读的，长了就折行；不截断（截断会让人以为"就这些"） -->
          <span class="detail-text">{{ row.detail || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column :label="t('auditLog.colIp')" width="130">
        <template #default="{ row }">
          <span class="muted">{{ row.ip || '—' }}</span>
        </template>
      </el-table-column>

      <template #empty>
        <el-empty :description="t('auditLog.empty')" :image-size="80" />
      </template>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[20, 50, 100]"
      layout="total, sizes, prev, pager, next"
      class="admin-pagination"
      @current-change="loadList"
      @size-change="handleSizeChange"
    />
  </div>
</template>

<script>
/**
 * 管理端「操作日志」（第 148 批）
 *
 * ## 为什么要有这一页
 *
 * 第 146 批把管理动作（停用/恢复、改角色、开通编辑员、删账号、批量删反馈、
 * 批量删帖、版块启停与排序…）落进了 `AdminAuditLog` 表，并给了只读接口，
 * 但当时**只能在 Django admin 里看** —— 那是给运维的界面，控制台的管理员
 * 要查"上周谁停用过账号"得另开一个后台，路径也对不上。
 *
 * ## 权限：仅全权管理员
 *
 * 页面显示"谁在什么时候对谁做了什么"，内容编辑员不该看到别的管理员的操作记录。
 * 前端 `meta.fullAdminOnly`（第 148 批给路由守卫加的档位）+ 侧栏过滤 + 后端
 * `is_full_admin` 三处同一口径 —— 只挡前端的页面没有意义，只挡后端则会白开一个页面。
 *
 * ## 只读
 *
 * 没有编辑/删除入口，后端也只有 GET。允许改审计记录，这张表就没有意义了
 * （Django admin 那边同样把 add/change/delete 三个权限禁掉了）。
 */
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { fetchAuditActions, fetchAuditLogs } from '@/api/audit';
import { formatApiError } from '@/api/http';
import { formatTime } from '@/utils/date';
import { useI18n } from '@/i18n';
import { useQueryState } from '@/composables/useQueryState';

export default {
  name: 'AdminAuditLogView',
  setup() {
    const { t } = useI18n();

    const items = ref([]);
    const total = ref(0);
    const loading = ref(false);
    const page = ref(1);
    const pageSize = ref(20);
    const actions = ref([]);
    const filters = ref({ action: '', search: '' });
    /** el-date-picker 的 daterange 绑定 `[start, end]`，空时是 null */
    const dateRange = ref(null);

    const buildParams = () => {
      const params = { page: page.value, page_size: pageSize.value };
      if (filters.value.action) params.action = filters.value.action;
      if (filters.value.search.trim()) params.search = filters.value.search.trim();
      const [start, end] = dateRange.value || [];
      if (start) params.start = start;
      if (end) params.end = end;
      return params;
    };

    const loadList = async () => {
      loading.value = true;
      try {
        const data = await fetchAuditLogs(buildParams());
        items.value = data.results || [];
        total.value = data.count ?? items.value.length;
      } catch (error) {
        ElMessage.error(formatApiError(error, t('auditLog.loadFailed')));
      } finally {
        loading.value = false;
      }
    };

    /** 动作清单来自后端（模型 choices 单一来源），筛选下拉才不会漏掉新加的动作 */
    const loadActions = async () => {
      try {
        const data = await fetchAuditActions();
        actions.value = Array.isArray(data) ? data : (data?.results || []);
      } catch (error) {
        console.warn('动作清单加载失败:', error);
      }
    };

    const applyFilter = () => { page.value = 1; loadList(); };
    const handleSizeChange = () => { page.value = 1; loadList(); };
    const hasFilter = computed(() => Boolean(
      filters.value.action || filters.value.search.trim() || dateRange.value?.length,
    ));
    const resetFilters = () => {
      filters.value = { action: '', search: '' };
      dateRange.value = null;
      applyFilter();
    };

    // 第 98 批的约定：筛选与分页进 URL（刷新/分享不丢）
    const filterRef = (key) => ({
      get value() { return filters.value[key]; },
      set value(next) { filters.value[key] = next ?? ''; },
    });
    const { isReady: queryReady } = useQueryState({
      fields: {
        page: { ref: page, type: 'int', default: 1 },
        page_size: { ref: pageSize, type: 'int', default: 20 },
        action: { ref: filterRef('action'), type: 'string', default: '' },
        search: { ref: filterRef('search'), type: 'string', default: '' },
        start: { ref: { get value() { return dateRange.value?.[0] || ''; },
                       set value(v) {
                         const end = dateRange.value?.[1] || '';
                         dateRange.value = v ? [v, end] : (end ? [end, end] : null);
                       } }, type: 'string', default: '' },
        end: { ref: { get value() { return dateRange.value?.[1] || ''; },
                      set value(v) {
                        const start = dateRange.value?.[0] || '';
                        dateRange.value = v ? [start || v, v] : (start ? [start, start] : null);
                      } }, type: 'string', default: '' },
      },
      onExternalChange: () => loadList(),
    });

    watch(queryReady, (ready) => {
      if (ready) loadList();
    }, { immediate: true });
    loadActions();

    // -- 展示 ---------------------------------------------------------------
    /** 动作分类配色：账号类=红、内容类=蓝、版块/词条类=灰 */
    const actionTagType = (action) => {
      if (action.startsWith('user.')) return 'danger';
      if (action.startsWith('feedback.') || action.startsWith('post.')) return 'primary';
      return 'info';
    };

    const targetTypeLabel = (type) => ({
      user: t('auditLog.targetUser'),
      feedback: t('auditLog.targetFeedback'),
      post: t('auditLog.targetPost'),
      board: t('auditLog.targetBoard'),
      word: t('auditLog.targetWord'),
      announcement: t('auditLog.targetAnnouncement'),
    }[type] || type || '—');

    return {
      t,
      items, total, loading, page, pageSize, actions, filters, dateRange,
      loadList, applyFilter, handleSizeChange, resetFilters, hasFilter,
      actionTagType, targetTypeLabel, formatTime,
    };
  },
};
</script>

<style scoped>
.readonly-note {
  margin-bottom: 14px;
}

.detail-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--ink-700, #46564e);
  word-break: break-word;
}

.admin-pagination {
  margin-top: 14px;
  justify-content: flex-end;
}
</style>
