<template>
  <div class="admin-page">
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-clock-rotate-left"></i></span>
        <div>
          <h1>{{ t('detections.title') }}</h1>
          <p>{{ t('detections.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-button plain :loading="loading" @click="loadList">
          <i class="fas fa-rotate"></i> {{ t('detections.refresh') }}
        </el-button>
      </div>
    </header>

    <!-- 概览：数字都在**当前筛选条件**下统计，与下面的列表口径一致 -->
    <div class="stat-row">
      <div class="stat-tile">
        <div class="stat-tile-value">{{ stats.total ?? 0 }}</div>
        <div class="stat-tile-label">{{ t('detections.statTotal') }}</div>
      </div>
      <div class="stat-tile">
        <div class="stat-tile-value">{{ stats.today ?? 0 }}</div>
        <div class="stat-tile-label">{{ t('detections.statToday') }}</div>
      </div>
      <div class="stat-tile" :class="{ 'is-alert': stats.unmatched > 0 }">
        <div class="stat-tile-value">{{ stats.unmatched ?? 0 }}</div>
        <div class="stat-tile-label">{{ t('detections.statUnmatched') }}</div>
      </div>
      <div class="stat-tile">
        <div class="stat-tile-value">{{ avgPercent }}</div>
        <div class="stat-tile-label">{{ t('detections.statConfidence') }}</div>
      </div>
      <div class="stat-tile">
        <div class="stat-tile-value">{{ stats.users ?? 0 }}</div>
        <div class="stat-tile-label">{{ t('detections.statUsers') }}</div>
      </div>
    </div>

    <!-- 筛选 -->
    <div class="filter-bar">
      <el-input
        v-model="filters.search"
        :placeholder="t('detections.searchPlaceholder')"
        clearable
        class="filter-search"
        @keyup.enter="applyFilter"
        @clear="applyFilter"
      >
        <template #prefix><i class="fas fa-magnifying-glass"></i></template>
      </el-input>

      <!-- ⚠️ Element Plus 会把 value="" 的选项当成"未选中"，显示默认的「请选择」；
       所以这里显式给 placeholder，默认状态一样能读懂。 -->
      <el-select
        v-model="filters.matched"
        class="filter-select"
        :placeholder="t('detections.matchAll')"
        @change="applyFilter"
      >
        <el-option :label="t('detections.matchAll')" value="" />
        <el-option :label="t('detections.matchOnly')" value="true" />
        <el-option :label="t('detections.matchNone')" value="false" />
      </el-select>

      <el-select
        v-model="filters.confidenceMax"
        class="filter-select"
        :placeholder="t('detections.confidenceAll')"
        @change="applyFilter"
      >
        <el-option :label="t('detections.confidenceAll')" value="" />
        <el-option :label="t('detections.confidenceLow')" value="0.6" />
        <el-option :label="t('detections.confidenceMid')" value="0.8" />
      </el-select>

      <el-date-picker
        v-model="dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        :start-placeholder="t('detections.dateFrom')"
        :end-placeholder="t('detections.dateTo')"
        class="filter-date"
        @change="applyFilter"
      />

      <el-button plain :disabled="!hasFilter" @click="resetFilters">
        <i class="fas fa-rotate-left"></i> {{ t('detections.reset') }}
      </el-button>
    </div>

    <!-- 列表 -->
    <el-table
      v-loading="loading"
      :data="rows"
      class="admin-table"
      :empty-text="t('detections.empty')"
      @row-click="openDetail"
    >
      <el-table-column :label="t('detections.colImage')" width="96">
        <template #default="{ row }">
          <img
            v-if="row.image"
            :src="toAbsoluteMediaUrl(row.image)"
            :alt="row.result"
            class="detect-thumb"
          />
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>

      <el-table-column :label="t('detections.colUser')" width="140">
        <template #default="{ row }">
          <span>{{ row.user ? row.user.username : '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column :label="t('detections.colResult')" min-width="160">
        <template #default="{ row }">
          <span class="detect-result">{{ row.result }}</span>
          <!-- 没匹配到词条的记录最值得看：识别出了名字，但百科里没有对应词条 -->
          <el-tag v-if="!row.matched" size="small" type="warning" class="match-tag">
            {{ t('detections.unmatched') }}
          </el-tag>
          <el-tag v-else size="small" type="info" class="match-tag">
            {{ localizedField(row.pest, 'name') }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('detections.colConfidence')" width="130">
        <template #default="{ row }">
          <span class="confidence-chip" :class="confidenceClass(row.confidence)">
            {{ row.confidence != null ? `${(row.confidence * 100).toFixed(1)}%` : '—' }}
          </span>
        </template>
      </el-table-column>

      <el-table-column :label="t('detections.colTime')" width="170">
        <template #default="{ row }">
          <span class="muted">{{ formatTime(row.timestamp) }}</span>
        </template>
      </el-table-column>

      <el-table-column :label="t('detections.colActions')" width="170" fixed="right">
        <template #default="{ row }">
          <el-button size="small" plain @click.stop="openDetail(row)">
            {{ t('detections.view') }}
          </el-button>
          <!-- 删除是不可逆动作：只给全权管理员画这个按钮（后端也会再拦一次） -->
          <el-button
            v-if="authStore.isAdmin"
            size="small"
            type="danger"
            plain
            @click.stop="removeRow(row)"
          >
            <i class="fas fa-trash"></i>
          </el-button>
        </template>
      </el-table-column>
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

    <!-- 详情：原图 / 标注图对照 -->
    <el-dialog v-model="detailVisible" :title="t('detections.detailTitle')" width="720px">
      <div v-if="current" class="detail-body">
        <div class="detail-images">
          <figure>
            <img :src="toAbsoluteMediaUrl(current.image)" :alt="current.result" />
            <figcaption>{{ t('detections.originalImage') }}</figcaption>
          </figure>
          <figure v-if="current.annotated_image">
            <img :src="toAbsoluteMediaUrl(current.annotated_image)" :alt="current.result" />
            <figcaption>{{ t('detections.annotatedImage') }}</figcaption>
          </figure>
        </div>
        <dl class="detail-fields">
          <div><dt>{{ t('detections.colUser') }}</dt><dd>{{ current.user ? current.user.username : '—' }}</dd></div>
          <div><dt>{{ t('detections.colResult') }}</dt><dd>{{ current.result }}</dd></div>
          <div>
            <dt>{{ t('detections.colConfidence') }}</dt>
            <dd>{{ current.confidence != null ? `${(current.confidence * 100).toFixed(1)}%` : '—' }}</dd>
          </div>
          <div>
            <dt>{{ t('detections.pestEntry') }}</dt>
            <dd>
              <template v-if="current.pest">
                <router-link :to="`/pests/${current.pest.english_identifier}`" target="_blank">
                  {{ localizedField(current.pest, 'name') }}
                </router-link>
              </template>
              <span v-else class="muted">{{ t('detections.noPestEntry') }}</span>
            </dd>
          </div>
          <div><dt>{{ t('detections.colTime') }}</dt><dd>{{ formatTime(current.timestamp) }}</dd></div>
        </dl>
      </div>
    </el-dialog>
  </div>
</template>

<script>
/**
 * 控制台「识别记录」（第 172 批）
 * ============================================================================
 * ## 这一页是干什么的
 *
 * 农户每识别一次就落一条 `DetectionHistory`。在这之前**只有农户自己**能在
 * 「历史记录」看到自己的记录 —— 管理员想知道"识别得准不准、大家在认什么、
 * 有没有明显传错的图"，只能去 Django admin 里翻表。
 *
 * 这一页给的是**跨用户**的全局视图：谁 / 什么时候 / 认出了什么 / 置信度多少 /
 * 有没有匹配到病害词条。
 *
 * ## 两个刻意的设计
 *
 * 1. **统计跟着筛选走**：顶部的数字是"当前筛选条件下的"（后端在同一段代码里算），
 *    而不是"全库总数" —— 否则点开"只看未匹配"后，上面还写着 23 条总数，会让人以为筛选没生效。
 * 2. **"未匹配词条"单独标出来**：识别出名字但百科里没有对应词条的记录，
 *    既是"词条库该补了"的信号，也是人工抽查的最佳样本（机器给的答案没人对过）。
 *
 * ## 历史沿革
 *
 * 第 22 批曾有过管理端 `DetectionHistoryView`，后以"与农户端重复"为由撤掉，
 * 把 `/admin/detection-history` 改成重定向到 `/history`。但农户端只回**自己的**记录，
 * 管理员看不到别人的 —— 所以本批按管理端需求重建（不是把老页面搬回来）。
 */
import { computed, onMounted, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { deleteAdminDetection, fetchAdminDetections } from '@/api/adminDetection';
import { toAbsoluteMediaUrl } from '@/api/http';
import { useI18n } from '@/i18n';
import { useLocalized } from '@/utils/localized';
import { formatTime } from '@/utils/date';
import { useAuthStore } from '@/stores/auth';

export default {
  name: 'AdminDetectionHistoryView',
  setup() {
    const { t } = useI18n();
    const { localizedField } = useLocalized();
    const authStore = useAuthStore();

    const rows = ref([]);
    const stats = ref({});
    const loading = ref(false);
    const page = ref(1);
    const pageSize = ref(20);
    const total = ref(0);
    const detailVisible = ref(false);
    const current = ref(null);

    // 筛选：日期区间单独存（el-date-picker 的 v-model 是数组），其余按参数名一一对应
    const filters = ref({ search: '', matched: '', confidenceMax: '' });
    const dateRange = ref([]);

    const hasFilter = computed(() => Boolean(
      filters.value.search || filters.value.matched || filters.value.confidenceMax
      || (dateRange.value && dateRange.value.length)
    ));

    const avgPercent = computed(() => (
      stats.value.avg_confidence != null
        ? `${(stats.value.avg_confidence * 100).toFixed(1)}%`
        : '—'
    ));

    /** 置信度分档上色（与识别结果页同一套口径：≥0.8 高、≥0.6 中、其余低） */
    const confidenceClass = (value) => {
      if (value == null) return 'is-unknown';
      if (value >= 0.8) return 'is-high';
      if (value >= 0.6) return 'is-mid';
      return 'is-low';
    };

    const buildParams = () => {
      const params = { page: page.value, page_size: pageSize.value };
      if (filters.value.search.trim()) params.search = filters.value.search.trim();
      if (filters.value.matched) params.matched = filters.value.matched;
      if (filters.value.confidenceMax) params.confidence_max = filters.value.confidenceMax;
      if (dateRange.value?.length === 2) {
        params.date_from = dateRange.value[0];
        params.date_to = dateRange.value[1];
      }
      return params;
    };

    const loadList = async () => {
      loading.value = true;
      try {
        const data = await fetchAdminDetections(buildParams());
        rows.value = data.results || [];
        total.value = data.count ?? rows.value.length;
        stats.value = data.stats || {};
      } catch (error) {
        console.error('[detections] 加载识别记录失败:', error);
        ElMessage.error(t('detections.loadFailed'));
      } finally {
        loading.value = false;
      }
    };

    const applyFilter = () => {
      page.value = 1;
      loadList();
    };

    const resetFilters = () => {
      filters.value = { search: '', matched: '', confidenceMax: '' };
      dateRange.value = [];
      applyFilter();
    };

    const handleSizeChange = () => {
      page.value = 1;
      loadList();
    };

    const openDetail = (row) => {
      current.value = row;
      detailVisible.value = true;
    };

    const removeRow = async (row) => {
      try {
        await ElMessageBox.confirm(
          t('detections.deleteConfirm', {
            result: row.result,
            user: row.user ? row.user.username : '—',
          }),
          t('detections.deleteTitle'),
          {
            type: 'warning',
            confirmButtonText: t('detections.delete'),
            cancelButtonText: t('common.cancel'),
          },
        );
      } catch {
        return; // 用户取消
      }
      try {
        await deleteAdminDetection(row.id);
        ElMessage.success(t('detections.deleted'));
        await loadList();
      } catch (error) {
        console.error('[detections] 删除失败:', error);
        ElMessage.error(t('detections.deleteFailed'));
      }
    };

    onMounted(loadList);

    return {
      t, rows, stats, loading, page, pageSize, total, filters, dateRange, hasFilter,
      avgPercent, detailVisible, current, authStore,
      localizedField, toAbsoluteMediaUrl, formatTime, confidenceClass,
      loadList, applyFilter, resetFilters, handleSizeChange, openDetail, removeRow,
    };
  },
};
</script>

<style scoped>
/* 概览磁贴 / 筛选条 / 缩略图 —— 与其它管理页同一套视觉 */
.stat-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
}

.filter-search {
  width: 260px;
}

.filter-select {
  width: 170px;
}

.filter-date {
  width: 260px;
}

.detect-thumb {
  width: 64px;
  height: 48px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--border, #e6ece8);
  cursor: pointer;
}

.detect-result {
  font-weight: 600;
}

.match-tag {
  margin-left: 8px;
}

.confidence-chip {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
}

.confidence-chip.is-high {
  background: #e8f5e9;
  color: #2f7a55;
}

.confidence-chip.is-mid {
  background: #fff8e1;
  color: #a97612;
}

.confidence-chip.is-low {
  background: #fdecea;
  color: #c0392b;
}

.confidence-chip.is-unknown {
  background: #f2f4f3;
  color: #7d8f86;
}

.muted {
  color: var(--ink-400, #9dada5);
  font-size: 13px;
}

.detail-images {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.detail-images figure {
  margin: 0;
  flex: 1 1 280px;
}

.detail-images img {
  width: 100%;
  border-radius: 8px;
  border: 1px solid var(--border, #e6ece8);
}

.detail-images figcaption {
  margin-top: 6px;
  font-size: 12px;
  color: var(--ink-400, #9dada5);
  text-align: center;
}

.detail-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px 18px;
  margin: 0;
}

.detail-fields dt {
  font-size: 12px;
  color: var(--ink-400, #9dada5);
}

.detail-fields dd {
  margin: 2px 0 0;
  font-size: 14px;
}
</style>
