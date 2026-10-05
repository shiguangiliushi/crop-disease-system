<template>
  <div class="history-view">
    <header class="history-header text-center mb-4">
      <h1 class="fw-bold text-primary">{{ pageTitle }}</h1>
      <p class="text-muted">
        {{ isAdmin && viewAllUsers
          ? t('history.subtitleAdmin')
          : t('history.subtitleMine') }}
      </p>
      <!-- 第 22 批：原「识别记录管理」页已合并到本页。
           管理员在这里通过开关切换「只看自己 / 全部用户」，列表、统计卡与图表
           会一起切换范围，不再有两个入口看同一批数据的问题。 -->
      <div v-if="isAdmin" class="scope-switch d-inline-flex align-items-center gap-2">
        <el-switch v-model="viewAllUsers" />
        <span class="text-muted small mb-0">
          {{ t('history.viewAllUsers') }}
        </span>
      </div>
    </header>

    <!-- 统计卡片区域 -->
    <div class="stats-cards mb-4">
      <div class="row g-3">
        <div class="col-md-3 col-6">
          <div class="stat-card bg-white rounded-3 p-3 shadow-sm h-100">
            <div class="stat-icon bg-soft-primary rounded-circle d-inline-flex align-items-center justify-content-center mb-2">
              <i class="bi bi-journal-text fs-4 text-primary"></i>
            </div>
            <div class="stat-number fw-bold fs-4">{{ totalRecords || 0 }}</div>
            <div class="stat-label text-muted small">{{ t('history.statTotal') }}</div>
          </div>
        </div>
        <div class="col-md-3 col-6">
          <div class="stat-card bg-white rounded-3 p-3 shadow-sm h-100">
            <div class="stat-icon bg-soft-success rounded-circle d-inline-flex align-items-center justify-content-center mb-2">
              <i class="bi bi-bug fs-4 text-success"></i>
            </div>
            <div class="stat-number fw-bold fs-4">{{ uniquePests.size || 0 }}</div>
            <div class="stat-label text-muted small">{{ t('history.statSpecies') }}</div>
          </div>
        </div>
        <div class="col-md-3 col-6">
          <div class="stat-card bg-white rounded-3 p-3 shadow-sm h-100">
            <div class="stat-icon bg-soft-warning rounded-circle d-inline-flex align-items-center justify-content-center mb-2">
              <i class="bi bi-calendar-check fs-4 text-warning"></i>
            </div>
            <div class="stat-number fw-bold fs-4">{{ todayCount || 0 }}</div>
            <div class="stat-label text-muted small">{{ t('history.statToday') }}</div>
          </div>
        </div>
        <div class="col-md-3 col-6">
          <div class="stat-card bg-white rounded-3 p-3 shadow-sm h-100">
            <div class="stat-icon bg-soft-info rounded-circle d-inline-flex align-items-center justify-content-center mb-2">
              <i class="bi bi-graph-up-arrow fs-4 text-info"></i>
            </div>
            <div class="stat-number fw-bold fs-4 text-truncate" :title="topPestLabel">{{ topPestLabel || t('history.statNone') }}</div>
            <div class="stat-label text-muted small">{{ t('history.statTop') }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 主要内容区域 -->
    <div class="main-content">
    <!-- 统计图表区域 -->
    <div class="chart-section mb-4">
      <div class="card border-0 shadow-sm h-100">
        <div class="card-header bg-white border-0 py-3">
          <h5 class="card-title mb-0 fw-bold">
            <i class="bi bi-bar-chart-line text-primary me-2"></i>
            {{ t('history.chartTitle') }}
          </h5>
        </div>
        <div class="card-body p-3">
          <DiseaseStatistics :all-users="adminAllUsers" />
        </div>
      </div>
    </div>

      <!-- 历史记录区域 -->
      <div class="history-section">
        <div class="card border-0 shadow-sm">
          <div class="card-header bg-white border-0 py-3 d-flex flex-column flex-md-row justify-content-between align-items-md-center">
            <h5 class="card-title mb-3 mb-md-0 fw-bold">
              <i class="bi bi-clock-history text-primary me-2"></i>
              {{ t('history.listTitle') }}
            </h5>
            <div class="filters-bar d-flex align-items-center flex-wrap gap-2">
              <div class="filter-item">
                <label for="filter-keyword" class="form-label small text-muted mb-1">
                  {{ adminAllUsers ? t('history.searchLabelAdmin') : t('history.searchLabel') }}
                </label>
                <input
                  id="filter-keyword"
                  v-model="searchKeyword"
                  class="form-control form-control-sm"
                  :placeholder="adminAllUsers ? t('history.searchAdminPlaceholder') : t('history.searchPlaceholder')"
                  @keyup.enter="applyFilters"
                >
              </div>
              <div class="filter-item">
                <label for="filter-pest" class="form-label small text-muted mb-1">{{ t('history.filterPest') }}</label>
                <select id="filter-pest" v-model="filterPest" @change="applyFilters" class="form-select form-select-sm" style="min-width: 120px;">
                  <option value="">{{ t('history.allPests') }}</option>
                  <option v-for="pest in diseaseTypes" :key="pest" :value="pest">{{ diseaseLabel(pest) }}</option>
                </select>
              </div>
              <div class="filter-item">
                <label for="filter-date" class="form-label small text-muted mb-1">{{ t('history.filterDate') }}</label>
                <!-- 第 78 批：改用 el-date-picker。原来这里是浏览器原生 <input type="date">，
                     它的占位符（"年/月/日"）与日期格式由**浏览器/系统语言**决定，
                     页面切成英文也仍然是中文 —— 前端无法控制。
                     el-date-picker 跟随 el-config-provider 的语言包（App.vue 里已随界面语言切换），
                     切换语言后占位符与面板立即变成英文。 -->
                <el-date-picker
                  id="filter-date"
                  v-model="filterDate"
                  type="date"
                  size="small"
                  value-format="YYYY-MM-DD"
                  :placeholder="t('history.filterDate')"
                  clearable
                  @change="applyFilters"
                  @clear="applyFilters"
                />
              </div>
              <!-- 「清除全部」只清**本人**记录（后端 clear-all 不带 all_users 时即如此），
                   所以在"全部用户"视图下不显示它，避免误以为会清空所有人；
                   该视图下的批量删除请用列表上方的多选。 -->
              <button
                v-if="!adminAllUsers"
                @click="clearAllHistory"
                class="btn btn-outline-danger btn-sm ms-2"
                style="margin-top: 20px;"
              >
                <i class="bi bi-trash"></i> {{ t('history.clearAll') }}
              </button>
            </div>
          </div>

          <!-- 状态显示 -->
          <div v-if="!isInitialized && isLoading" class="status-message">
            <div class="loading-spinner large"></div>
            <p>{{ t('history.initializing') }}</p>
          </div>

          <div v-else-if="error" class="status-message error">
            <i class="fas fa-exclamation-triangle fa-2x"></i>
            <h3>{{ t('history.loadFailed') }}</h3>
            <p>{{ error }}</p>
            <div class="action-buttons">
              <button @click="refreshData" class="btn btn-primary">
                <i class="fas fa-sync-alt"></i> {{ t('history.reload') }}
              </button>
              <button @click="clearFilters" class="btn btn-outline-secondary" v-if="filterPest || filterDate">
                <i class="fas fa-filter-circle-xmark"></i> {{ t('history.clearFilters') }}
              </button>
            </div>
            <p class="text-muted small mt-3">
              {{ t('history.persistentError') }}
            </p>
          </div>

          <div v-else-if="isLoading" class="status-message">
            <div class="loading-spinner"></div>
            <p>{{ t('history.loading') }}</p>
          </div>

          <div v-else-if="history.length === 0" class="status-message">
            <i class="fas fa-box-open fa-3x text-muted mb-3"></i>
            <h3>{{ t('history.emptyTitle') }}</h3>
            <p>{{ t('history.emptyFiltered') }}</p>
            <!-- 第 31 批：空状态原来只有一句话，页面剩下大半屏是空白；补上可点的下一步 -->
            <div class="empty-actions">
              <RouterLink to="/detect" class="empty-action-btn">
                <i class="fas fa-camera"></i> {{ t('history.goDetect') }}
              </RouterLink>
              <RouterLink to="/pests" class="empty-action-btn is-plain">
                <i class="fas fa-book-open"></i> {{ t('history.goWiki') }}
              </RouterLink>
              <button @click="clearFilters" class="btn btn-outline-primary empty-action-btn is-plain" v-if="filterPest || filterDate">
                <i class="fas fa-filter-circle-xmark"></i> {{ t('history.clearFilters') }}
              </button>
            </div>
          </div>

          <!-- 历史记录网格 -->
          <div v-else class="history-content">
            <!-- 导出 / 批量操作条（第 43 批：导出 Excel 对所有登录用户开放） -->
            <div class="batch-bar d-flex align-items-center flex-wrap gap-2 mb-3">
              <button
                class="btn btn-outline-success btn-sm"
                :disabled="exporting || totalRecords === 0"
                @click="exportExcel"
              >
                <i class="fas fa-file-excel"></i>
                {{ exporting ? t('history.exporting') : t('history.exportExcel') }}
              </button>
              <span class="text-muted small">
                {{ t('history.exportHint', { count: totalRecords }) }}{{ isAdmin && viewAllUsers ? t('history.exportHintAll') : '' }}
              </span>

              <template v-if="isAdmin">
                <span class="batch-divider"></span>
                <el-checkbox
                  :model-value="allOnPageSelected"
                  :indeterminate="someOnPageSelected"
                  @change="toggleSelectAllOnPage"
                >
                  {{ t('history.selectAllPage') }}
                </el-checkbox>
                <span class="text-muted small">{{ t('history.selectedCount', { count: selectedIds.length }) }}</span>
                <button
                  class="btn btn-outline-danger btn-sm"
                  :disabled="!selectedIds.length || batchDeleting"
                  @click="handleBatchDelete"
                >
                  <i class="bi bi-trash"></i> {{ batchDeleting ? t('history.deleting') : t('history.batchDelete') }}
                </button>
                <button
                  v-if="selectedIds.length"
                  class="btn btn-outline-secondary btn-sm"
                  @click="selectedIds = []"
                >
                  {{ t('history.deselect') }}
                </button>
              </template>
            </div>

            <div class="history-grid">
              <div v-for="item in history" :key="item.id" class="history-item" :class="{ 'missing-pest-info': !item.pest_info }">
                <!-- 多选（仅管理员） -->
                <div v-if="isAdmin" class="item-select">
                  <el-checkbox
                    :model-value="isSelected(item.id)"
                    @change="toggleSelect(item.id)"
                  />
                </div>
                <div class="history-item-image-wrapper">
                  <img :src="getFullImageUrl(item.image)" :alt="t('history.image')" class="history-image" @click="showDetailModal(item)">
                </div>
                <div class="history-item-info">
                  <template v-if="item.pest_info">
                    <h3 class="pest-name">{{ localizedField(item.pest_info, 'name') }}</h3>
                    <div class="item-meta">
                      <span><i class="fas fa-leaf"></i> {{ localizedField(item.pest_info, 'crop_type') || t('history.noCrop') }}</span>
                      <span><i class="fas fa-percent"></i> {{ item.confidence ? (item.confidence * 100).toFixed(1) + '%' : 'N/A' }}</span>
                    </div>
                  </template>
                  <template v-else>
                    <h3 class="pest-name unknown">
                      <i class="fas fa-exclamation-triangle"></i> {{ t('history.noPestLinked') }}
                      <span class="debug-info" v-if="item.detection_result">({{ t('history.detectionResult') }}: {{ item.detection_result }})</span>
                    </h3>
                    <div class="item-meta">
                      <span class="unknown"><i class="fas fa-question-circle"></i> {{ t('history.noCropLinked') }}</span>
                      <span><i class="fas fa-info-circle"></i> {{ t('history.recordId') }}: {{ item.id }}</span>
                    </div>
                  </template>
                  <!-- 识别者：仅在管理员查看"全部用户"时显示（原第 17 批的功能，
                       第 22 批随两个页面合并回到这里） -->
                  <div
                    v-if="adminAllUsers"
                    class="item-owner"
                    :title="t('history.uploader', { name: item.user?.username || t('forum.unknownUser') })"
                  >
                    <i class="fas fa-user-circle"></i>
                    <span class="item-owner-name">{{ item.user?.username || t('forum.unknownUser') }}</span>
                  </div>
                  <p class="timestamp"><i class="fas fa-clock"></i> {{ formatTimestamp(item.timestamp) }}</p>
                  <div class="history-item-actions">
                    <div class="btn-group w-100" role="group">
                      <button
                        class="btn btn-action btn-view"
                        @click.stop="showDetailModal(item)"
                        :title="t('history.viewDetail')"
                      >
                        <i class="bi bi-eye-fill"></i>
                        <span class="btn-text">{{ t('history.detail') }}</span>
                      </button>
                      <button
                        class="btn btn-action btn-download"
                        @click.stop="downloadReport(item)"
                        :disabled="downloadingReportId === item.id"
                        :title="downloadingReportId === item.id ? t('history.downloading') : t('history.downloadPdf')"
                      >
                        <i class="bi" :class="{'bi-file-earmark-pdf': downloadingReportId !== item.id, 'bi-arrow-repeat': downloadingReportId === item.id, 'fa-spin': downloadingReportId === item.id}"></i>
                        <span class="btn-text">{{ t('history.report') }}</span>
                      </button>
                      <button
                        class="btn btn-action btn-delete"
                        @click.stop="deleteHistoryItem(item.id)"
                        :title="t('history.deleteRecord')"
                      >
                        <i class="bi bi-trash"></i>
                        <span class="btn-text">{{ t('history.delete') }}</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 分页 -->
            <div class="pagination-container" v-if="totalPages > 1">
              <div class="pagination">
                <button @click="handlePageChange(1)" :disabled="currentPage === 1" class="page-btn">{{ t('history.firstPage') }}</button>
                <button @click="handlePageChange(currentPage - 1)" :disabled="currentPage === 1" class="page-btn">{{ t('history.prevPage') }}</button>
                <span class="page-info">{{ t('history.pageInfo', { current: currentPage, total: totalPages }) }}</span>
                <button @click="handlePageChange(currentPage + 1)" :disabled="currentPage === totalPages" class="page-btn">{{ t('history.nextPage') }}</button>
                <button @click="handlePageChange(totalPages)" :disabled="currentPage === totalPages" class="page-btn">{{ t('history.lastPage') }}</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 详情弹窗 -->
      <div v-if="isDetailModalVisible" class="modal-overlay" @click.self="isDetailModalVisible = false">
        <div class="modal-content">
          <button class="modal-close" @click="isDetailModalVisible = false">&times;</button>
          <div class="modal-body" v-if="selectedItem">
            <div class="modal-image">
              <img :src="getFullImageUrl(selectedItem.image)" :alt="t('history.image')">
            </div>
            <div class="modal-details">
              <h2>{{ localizedField(selectedItem.pest_info, 'name') || t('history.unknownPest') }}</h2>
              <div class="detail-section">
                <h3><i class="fas fa-clock"></i> {{ t('history.detectedAt') }}</h3>
                <p>{{ formatTimestamp(selectedItem.timestamp) }}</p>
              </div>
              <div class="detail-section">
                <h3><i class="fas fa-file-medical-alt"></i> {{ t('history.symptomDesc') }}</h3>
                <p>{{ localizedField(selectedItem.pest_info, 'symptoms') || t('history.noSymptomDesc') }}</p>
              </div>
              <div class="detail-section">
                <h3><i class="fas fa-shield-alt"></i> {{ t('history.preventionAdvice') }}</h3>
                <div v-if="selectedItem.pest_info?.prevention_methods && selectedItem.pest_info.prevention_methods.length > 0" class="prevention-methods-list">
                  <div v-for="method in selectedItem.pest_info.prevention_methods" :key="method.measure" class="prevention-method">
                    <strong>【{{ getPreventionCategoryName(method.category) }}】</strong>
                    <p>{{ localizedField(method, 'measure') }}</p>
                  </div>
                </div>
                <p v-else>{{ t('history.noPrevention') }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 第 31 批：列表/图表下面原来直接是页脚，补一块"识别记录能做什么" -->
    <!-- 第 62 批：卡片内容改由脚本 computed 生成，随语言切换 -->
    <PageExtras
      icon="fas fa-clock-rotate-left"
      :title="t('history.guideTitle')"
      :subtitle="t('history.guideSubtitle')"
      :items="guideItems"
    />
  </div>
</template>

<script setup>
// 识别历史（当前用户 / 管理员的全部记录）
// 路由：/history
//
// 页面由四块组成：
//   1) 顶部统计条（总数 / 平均置信度 / 最常见的病害）
//   2) 筛选与搜索（作物、病害、时间范围、只看低置信度）
//   3) 记录表格：单条删除、批量删除、点进详情看原图与标注图
//   4) 底部分页
//
// 改这个文件前值得知道的几件事（都是踩过的）：
//   · 批量删除会**同时删图片文件**，不是只删数据库行 —— 见 handleBatchDelete
//     与后端 DetectionHistoryClearView.delete（那边用 os.remove，绕过 Django storage，
//     换非本地存储时会失效）；
//   · updateTopPest 写回的"最常见病害"依赖当前页数据，所以**换页后这个数字会变**，
//     不是缓存 bug；
//   · 管理端的"全部用户"视图与个人视图**共用本组件**，用 all_users 参数区分，
//     权限校验在后端（前端只负责不显示入口）。
import { ref, onMounted, computed, watch } from 'vue';
import { useI18n } from '@/i18n';  // 第 62 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 69 批：内容数据多语言

const { t, locale } = useI18n();
const { localizedField } = useLocalized();  // 第 69 批：内容数据（病害名/作物名）多语言

// 第 62 批：底部"识别记录能做什么"卡片（原来内联在模板里，无法随语言切换）
const guideItems = computed(() => [
  { icon: 'fas fa-floppy-disk', title: t('history.guideLegacy1'), text: t('history.guideLegacy1Desc') },
  { icon: 'fas fa-filter', title: t('history.guideLegacy2'), text: t('history.guideLegacy2Desc') },
  {
    icon: 'fas fa-shield-halved',
    title: t('history.guideLegacy3'),
    text: t('history.guideLegacy3Desc'),
    more: t('history.guideLegacy3Link'),
    to: '/pests',
  },
  {
    icon: 'fas fa-camera',
    title: t('history.guideLegacy4'),
    text: t('history.guideLegacy4Desc'),
    more: t('history.guideLegacy4Link'),
    to: '/detect',
  },
]);
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox, ElLoading } from 'element-plus'; // 更新 Element Plus 导入，确保包含 ElLoading
// 第 31 批：页面底部"识别记录能做什么"补充信息区
import PageExtras from '@/components/PageExtras.vue';
import apiClient from '@/api';
import axios from 'axios';
import { formatDate, formatTime } from '@/utils/date';
import { getImageUrl } from '@/utils/image';
import { downloadDetectionReportPdf } from '@/utils/pdfReport';
import { toAbsoluteMediaUrl } from '@/api/http';
import { useAuthStore } from '@/stores/auth';
// 批量删除复用识别记录接口模块（第 22 批：原「识别记录管理」页的能力合并到本页）
import { batchDeleteDetectionHistory } from '@/api/detection';
import DiseaseStatistics from '@/components/DiseaseStatistics.vue';
import logoUrl from '@/assets/农作物病害识别1.png';

// 导出组件选项
defineOptions({
  name: 'HistoryView',
  components: {
    DiseaseStatistics
  }
});

// Using ElMessage instead of useToast
const history = ref([]);
const currentPage = ref(1);
const downloadingReportId = ref(null);
const exporting = ref(false);  // 第 43 批：Excel 导出中
const totalPages = ref(1);
const totalRecords = ref(0);
const filterPest = ref('');
const filterDate = ref('');
const isLoading = ref(false);
const error = ref(null);
const isDetailModalVisible = ref(false);
const selectedItem = ref(null);
const uniquePests = ref(new Set());  // 病害种类集合
const diseaseTypes = ref([]);  // 病害类型列表，用于筛选
const isInitialized = ref(false);  // 标记是否已完成初始化加载

/**
 * 第 77 批：病害名中→英对照
 * ------------------------------------------------------------------
 * "按病害筛选"下拉的 `value` **必须**保持中文病害名 —— 后端是按
 * `pest_info__name__icontains` 匹配的（见 fetchHistory 的 pest 参数），换英文就筛不出东西。
 * 但显示的 label 要跟随界面语言，所以这里单独维护一份"中文名 → 英文名"，
 * 从所有已经拿到的记录里顺手攒起来（识别记录接口本来就带 name_en）。
 */
const pestNameEnMap = ref({});
const rememberPestNames = (items) => {
  if (!Array.isArray(items) || !items.length) return;
  const map = { ...pestNameEnMap.value };
  for (const item of items) {
    const zh = item?.pest_info?.name || item?.disease_name;
    const en = item?.pest_info?.name_en;
    if (zh && en && !map[zh]) map[zh] = en;
  }
  pestNameEnMap.value = map;
};
const diseaseLabel = (name) =>
  locale.value === 'en' ? pestNameEnMap.value[name] || name : name;

// ---------- 第 22 批：与原「识别记录管理」页合并 ----------
const authStore = useAuthStore();
const isAdmin = computed(() => Boolean(authStore.isAdmin));

// 管理员是否查看"全部用户"的记录。
// 默认开启：等价于原「识别记录管理」页的视角（管理员进页面就想看全部）。
// 关闭后只看自己 —— 与原「{{ t('history.listTitle') }}」页一致。
const viewAllUsers = ref(Boolean(authStore.isAdmin));

// 列表、统计、病害筛选选项都必须使用**同一个**范围，否则会出现
// "列表只有我的、图表却是所有人"这类自相矛盾。
const adminAllUsers = computed(() => Boolean(isAdmin.value && viewAllUsers.value));

// 传给后端的作用域参数（后端只对管理员认 all_users=true）
const scopeParams = () => (adminAllUsers.value ? { all_users: 'true' } : {});

const pageTitle = computed(() => (adminAllUsers.value ? t('history.titleAdmin') : t('history.titleMine')));

// 关键字搜索：管理员在"全部用户"视图下可搜用户名，也可搜病害名
const searchKeyword = ref('');

// 多选（仅管理员）：批量删除用
const selectedIds = ref([]);
const batchDeleting = ref(false);

const isSelected = (id) => selectedIds.value.includes(id);
const toggleSelect = (id) => {
  if (isSelected(id)) {
    selectedIds.value = selectedIds.value.filter((item) => item !== id);
  } else {
    selectedIds.value = [...selectedIds.value, id];
  }
};
const allOnPageSelected = computed(
  () => history.value.length > 0 && history.value.every((item) => isSelected(item.id)),
);
const someOnPageSelected = computed(
  () => selectedIds.value.length > 0 && !allOnPageSelected.value,
);
const toggleSelectAllOnPage = (checked) => {
  selectedIds.value = checked ? history.value.map((item) => item.id) : [];
};

const handleBatchDelete = async () => {
  if (!selectedIds.value.length) return;
  const count = selectedIds.value.length;
  try {
    await ElMessageBox.confirm(
      t('history.confirmBatchDelete', { count }),
      t('history.batchDelete'),
      { confirmButtonText: t('history.confirmDelete'), cancelButtonText: t('common.cancel'), type: 'warning' },
    );
  } catch {
    return; // 用户取消
  }

  batchDeleting.value = true;
  try {
    await batchDeleteDetectionHistory({ ids: [...selectedIds.value] });
    ElMessage.success(t('history.batchDeleteOk', { count }));
    selectedIds.value = [];
    await fetchHistory(currentPage.value);
  } catch (error) {
    console.error('批量删除失败:', error);
    ElMessage.error(t('history.batchDeleteFailed') + (error.response?.data?.detail || error.message));
  } finally {
    batchDeleting.value = false;
  }
};

// 切换查看范围时：清空选择、回到第一页，并把列表/统计/病害选项全部刷新
watch(viewAllUsers, async () => {
  selectedIds.value = [];
  currentPage.value = 1;
  await Promise.all([fetchHistory(1), fetchStatistics(), loadAllPestTypes()]);
});

// 加载所有病害类型
const loadAllPestTypes = async () => {
  try {
    const { allPests, allPestNames } = await fetchAllPestTypes();
    uniquePests.value = allPests;
    if (allPestNames.length > 0) {
      diseaseTypes.value = allPestNames.sort();
    }
    return allPestNames;
  } catch (error) {
    console.error('加载病害类型失败:', error);
    return [];
  }
};

// 初始化数据（并行加载历史记录与统计数据）
const initializeData = async () => {
  try {
    isLoading.value = true;
    error.value = null;

    await Promise.all([
      fetchHistory(1),
      fetchStatistics()
    ]);

    isInitialized.value = true;
    console.log('Data initialization completed successfully');
  } catch (err) {
    console.error('初始化数据失败:', err);
    error.value = t('history.initFailed');
  } finally {
    isLoading.value = false;
  }
};

// 组件挂载时加载数据（原来这里有两个 onMounted，会导致历史记录与统计接口重复请求两次）
onMounted(async () => {
  console.log('HistoryView component mounted, initializing data...');
  await loadAllPestTypes();
  // initializeData 内部已经并行请求了历史记录与统计数据
  await initializeData();
  console.log('Initial data loaded');
});

// 刷新数据
const refreshData = async () => {
  console.log('Refreshing data...');
  await initializeData();
};

// 清除所有筛选条件
const clearFilters = () => {
  console.log('Clearing all filters');
  filterPest.value = '';
  filterDate.value = '';
  searchKeyword.value = '';
  // 重新加载数据
  fetchHistory(1);
};

// 统计相关状态
const statsLoading = ref(false);
const statsError = ref(null);
const statsLastUpdated = ref(null);
const topPest = ref({ name: '-', count: 0 });
const todayCount = ref(0);  // 今日识别数
const monthlyStats = ref([]);
const diseaseDistribution = ref([]);

// --- 计算属性 ---
const monthCount = computed(() => {
  if (!history.value) return 0;
  const now = new Date();
  return history.value.filter(item => {
    const d = new Date(item.timestamp);
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
  }).length;
});

// 更新 topPest 的函数（第 72 批：同时记下英文名，英文界面下显示英文）
const topPestLabel = computed(() => {
  if (!topPest.value?.name || topPest.value.name === '-') return topPest.value?.name || '-';
  return localizedField(topPest.value, 'name');
});

const updateTopPest = () => {
  if (!history.value || history.value.length === 0) {
    topPest.value = { name: '-', count: 0 };
    return;
  }

  const counts = history.value.reduce((acc, item) => {
    if (item.pest_info?.name) {
      acc[item.pest_info.name] = (acc[item.pest_info.name] || 0) + 1;
    }
    return acc;
  }, {});

  const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
  if (!top) {
    topPest.value = { name: '-', count: 0 };
    return;
  }
  const topItem = history.value.find((item) => item.pest_info?.name === top[0]);
  topPest.value = {
    name: top[0],
    name_en: topItem?.pest_info?.name_en || '',
    count: top[1],
  };
};

// 获取统计数据
const fetchStatistics = async (silent = true) => {
  if (statsLoading.value) return;

  statsLoading.value = true;
  statsError.value = null;

  try {
    // 使用相对路径，因为baseURL已经包含了/api前缀（注意结尾的斜杠，避免 301 重定向）
    const response = await apiClient.get('statistics/', {
      silent,
      // 统计范围跟随页面上的"查看全部用户"开关（普通用户后端只会返回自己的数据）
      params: scopeParams(),
    });

    if (response?.data) {
      const data = response.data;

      // 更新统计信息
      todayCount.value = data.today_detections || 0;
      monthlyStats.value = data.monthly_stats || [];
      diseaseDistribution.value = data.disease_distribution || [];

      // 更新topPest
      if (data.top_pest) {
        topPest.value = data.top_pest;
      } else {
        // 如果没有返回top_pest，则从历史记录中计算
        updateTopPest();
      }

      // 更新最后更新时间
      statsLastUpdated.value = new Date();
    }

    return response?.data;
  } catch (error) {
    console.error('获取统计数据失败:', error);
    statsError.value = error;

    if (!silent) {
      ElMessage.error(t('history.statsFailed', { detail: error.message || t('msg.operationFailedRetry') }));
    }

    return null;
  } finally {
    statsLoading.value = false;
  }
};

// 刷新统计数据
const refreshStatistics = async () => {
  return await fetchStatistics(false);
};

// --- 方法 ---
// 获取完整图片地址
// 说明：原来用 `${VITE_API_BASE_URL}${path}` 拼接，但 VITE_API_BASE_URL 已包含 /api，
// 会得到 ".../api/media/xxx"（媒体文件实际在 /media/ 下）；统一改用 toAbsoluteMediaUrl。
const getFullImageUrl = (imagePath) => toAbsoluteMediaUrl(imagePath);

const getPreventionCategoryName = (categoryKey) => {
  // 第 72 批：防治类别改用 i18n（原来写死中文，英文界面下仍是"农业防治"等）
  const categories = {
    'AGRICULTURAL': 'prevent.agricultural',
    'CHEMICAL': 'prevent.chemical',
    'ECOLOGICAL': 'prevent.ecological',
    'PHYSICAL': 'prevent.physical',
    'MONITORING': 'prevent.monitoring',
  };
  return categories[categoryKey] ? t(categories[categoryKey]) : t('prevent.general');
};

const formatTimestamp = (timestamp) => {
  if (!timestamp) return t('forum.unknownTime');
  return new Date(timestamp).toLocaleString(locale.value === 'en' ? 'en-US' : 'zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
};

// 每页显示的数量
const itemsPerPage = ref(6);

// 本页只展示「我的识别记录」。
// 第 21 批起与「识别记录管理」(/admin/detection-history) 明确分工：
// 管理员要看**全部用户**的记录、要按用户搜索或批量删除，请到那个页面。
// 因此这里不再携带 all_users=true（后端也只有管理员带该参数才会返回全部用户的数据），
// 「识别者」标识与本页已无关系，相关判定一并移除。

// 获取所有病害种类
const fetchAllPestTypes = async () => {
  try {
    // 获取第一页数据
    const firstPageResponse = await apiClient.get('detection-history/', {
      params: {
        page: 1,
        page_size: 1,  // 只需要获取一条记录
        ordering: '-timestamp',
        ...scopeParams(),
      }
    });

    if (!firstPageResponse?.data?.data?.total) {
      return { allPests: new Set(), allPestNames: [] };
    }

    const totalItems = firstPageResponse.data.data.total;
    
    // 一次性获取所有记录
    const allItemsResponse = await apiClient.get('detection-history/', {
      params: {
        page: 1,
        page_size: totalItems,  // 获取所有记录
        ordering: '-timestamp',
        ...scopeParams(),
      }
    });

    if (!allItemsResponse?.data?.data?.items) {
      return { allPests: new Set(), allPestNames: [] };
    }

    // 提取所有病害名称
    const allPests = new Set();
    const allPestNames = [];
    
    allItemsResponse.data.data.items.forEach(item => {
      let pestName = '';
      if (item.pest_info?.name) {
        pestName = item.pest_info.name;
      } else if (item.disease_name) {
        pestName = item.disease_name;
      }
      
      if (pestName && !allPests.has(pestName)) {
        allPests.add(pestName);
        allPestNames.push(pestName);
      }
    });

    // 第 77 批：顺手记下中英对照，供"按病害筛选"下拉显示英文
    rememberPestNames(allItemsResponse.data.data.items);

    return { allPests, allPestNames };
  } catch (error) {
    console.error('获取所有病害种类失败:', error);
    return { allPests: new Set(), allPestNames: [] };
  }
};

// 获取历史记录
const fetchHistory = async (page = 1, extraParams = {}) => {
  try {
    isLoading.value = true;

    // 准备查询参数
    const params = {
      page,
      page_size: itemsPerPage.value,
      ordering: '-timestamp' // 按时间倒序
    };

    // 合并额外参数（包括筛选条件）
    Object.assign(params, extraParams);

    // 作用域：管理员在"全部用户"视图下带 all_users=true —— 与统计卡/图表使用同一开关，
    // 保证"列表有谁的数据，图表就统计谁的数据"
    Object.assign(params, scopeParams());

    // 关键字搜索（用户名 / 病害名）：优先取本次调用传入的，其次取页面搜索框
    const keyword = extraParams.search !== undefined ? extraParams.search : searchKeyword.value;
    if (keyword) {
      params.search = keyword;
    } else {
      delete params.search;
    }

    // 添加筛选条件 - 优先使用 extraParams 中的参数
    if (extraParams.pest) {
      params.pest = extraParams.pest;
    } else if (filterPest.value) {
      params.pest = filterPest.value;
    }
    
    if (extraParams.date) {
      // 确保日期格式正确
      const date = new Date(extraParams.date);
      if (!isNaN(date.getTime())) {
        params.date = extraParams.date;
      }
    } else if (filterDate.value) {
      // 确保日期格式正确
      const date = new Date(filterDate.value);
      if (!isNaN(date.getTime())) {
        params.date = filterDate.value;
      }
    }

    // 移除空参数
    Object.keys(params).forEach(key => (params[key] === '' || params[key] === null) && delete params[key]);

    console.log(`Fetching history page ${page} with params:`, params);

    // 添加请求超时处理
    const requestParams = { ...params };
    
    // 记录请求参数
    console.log('Sending request with params:', requestParams);
    
    const response = await Promise.race([
      apiClient.get('detection-history/', { params: requestParams }),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error(t('msg.requestTimeout'))), 10000)
      )
    ]);

    // 检查响应数据是否存在
    if (!response || !response.data || !response.data.data) {
      throw new Error(t('msg.invalidResponse'));
    }

    const responseData = response.data.data;

    // 记录调试信息
    console.log('History API Response:', {
      status: response.status,
      count: responseData.total,
      total_pages: responseData.total_pages,
      results_count: responseData.items.length,
      first_item: responseData.items[0],
    });

    // 处理数据并更新状态
    const processedItems = responseData.items.map(item => ({
      ...item,
      // 确保每个项目都有pest_info对象
      pest_info: item.pest_info || {
        // 第 77 批：占位文案走 i18n（这两行会直接渲染到卡片上）
        name: item.disease_name || t('history.unknownPest'),
        crop_type: t('history.unknownCrop'),
      }
    }));

    // 更新历史记录
    history.value = processedItems;

    // 更新分页信息
    totalRecords.value = responseData.total;
    totalPages.value = responseData.total_pages;
    currentPage.value = responseData.page;

    // 更新唯一病害类型和统计信息
    const updateDiseaseStats = async () => {
      const pestCounts = {};
      const pests = new Set();

      // 第 77 批：先记下中英对照，供筛选下拉显示英文
      rememberPestNames(processedItems);

      // 统计当前页的病害
      processedItems.forEach(item => {
        const pestName = item.disease_name || (item.pest_info?.name || t('history.unknownPest'));
        pests.add(pestName);
        pestCounts[pestName] = (pestCounts[pestName] || 0) + 1;
      });

      // 在组件挂载时获取所有病害种类
      if (!isInitialized.value) {
        isInitialized.value = true;
        const { allPests, allPestNames } = await fetchAllPestTypes();
        uniquePests.value = allPests;
        // 更新病害类型筛选器
        if (allPestNames.length > 0) {
          diseaseTypes.value = allPestNames.sort();
        }
      }
      
      // 更新最多识别的病害
      if (Object.keys(pestCounts).length > 0) {
        const [topPestName, count] = Object.entries(pestCounts).reduce(
          (max, [name, cnt]) => (cnt > max[1] ? [name, cnt] : max),
          ['', 0]
        );

        if (topPestName) {
          // 第 72 批：把英文名一起取出来
          // 第 77 批修复：这里原来读的是 `statsData.value?.pests`，而本组件**从来没有**
          // 这个变量 —— 只要走到这条分支就抛 ReferenceError。它又是在 async 函数里被
          // 直接调用（没有 await），于是变成"未处理的 Promise 拒绝"：页面看着正常，
          // 控制台一直报 `statsData is not defined`，英文名也永远取不到。
          // 现在只从已加载的记录里找（pest_info 由后端序列化器带上了 name_en）。
          const match = history.value.find(
            (row) => (row.pest_info?.name || row.disease_name) === topPestName,
          );
          topPest.value = {
            name: topPestName,
            name_en: match?.pest_info?.name_en || pestNameEnMap.value[topPestName] || '',
            count,
          };
        }
      }

      // 更新病害类型筛选器（如果是第一页且没有筛选条件）
      if (page === 1 && !filterPest.value && !filterDate.value) {
        diseaseTypes.value = Array.from(pests).sort();
      }
    };

    // 执行统计更新
    updateDiseaseStats();

    // 从所有历史记录中获取病害类型用于筛选器
    try {
      // 获取所有历史记录（不分页）—— 范围与当前视图一致
      const allHistoryResponse = await apiClient.get('/detection-history/', {
        params: {
          page_size: 1000, // 设置一个足够大的数来获取所有记录
          page: 1,
          ...scopeParams(),
        },
        silent: true
      });

      if (allHistoryResponse?.data?.data?.items) {
        const allPestTypes = [];

        // 第 77 批：顺手记下中英对照
        rememberPestNames(allHistoryResponse.data.data.items);

        // 处理所有历史记录
        allHistoryResponse.data.data.items.forEach(item => {
          const pestName = item.disease_name || (item.pest_info?.name || '').trim();
          if (pestName) {
            allPestTypes.push(pestName);
          }
        });

        // 添加当前筛选的病害类型（如果存在且不在列表中）
        if (filterPest.value && !allPestTypes.includes(filterPest.value)) {
          allPestTypes.push(filterPest.value);
        }

        // 更新病害类型筛选器，去重并排序
        if (allPestTypes.length > 0) {
          diseaseTypes.value = [...new Set(allPestTypes)].sort();
        }
      }
    } catch (error) {
      console.warn('获取历史记录病害类型时出错:', error);

      // 如果获取所有记录失败，则回退到只使用当前页的记录
      try {
        const currentPagePests = [];

        rememberPestNames(historyItems.value);

        historyItems.value.forEach(item => {
          const pestName = item.disease_name || (item.pest_info?.name || '').trim();
          if (pestName) {
            currentPagePests.push(pestName);
          }
        });

        if (filterPest.value && !currentPagePests.includes(filterPest.value)) {
          currentPagePests.push(filterPest.value);
        }

        if (currentPagePests.length > 0) {
          diseaseTypes.value = [...new Set(currentPagePests)].sort();
        }
      } catch (fallbackError) {
        console.warn('回退到当前页数据时出错:', fallbackError);
      }
    }

    // 使用后端API获取准确的统计信息
    if (page === 1 && !filterPest.value && !filterDate.value) {
      try {
        const statsResponse = await apiClient.get('statistics/', {
          silent: true,
          params: scopeParams(),
        });

        if (statsResponse?.data) {
          const { pest_distribution } = statsResponse.data;

          if (pest_distribution && pest_distribution.length > 0) {
            // 更新病害类型分布
            const pestTypes = [];
            const pestCounts = {};
            const pestNamesEn = {};

            pest_distribution.forEach(item => {
              const pestName = item.pest_info__name || t('history.unknownPest');
              const count = item.count || 0;

              if (pestName && count > 0) {
                pestTypes.push(pestName);
                pestCounts[pestName] = count;
                // 第 77 批：把英文名一起记下来。此前这条路径只存了中文名，
                // 而它恰恰是"识别最多的病害"卡片的**最后写入者** —— 结果是英文界面下
                // 卡片标题是英文（Most diagnosed disease）、值却是中文病害名。
                if (item.pest_info__name_en) pestNamesEn[pestName] = item.pest_info__name_en;
              }
            });

            // 更新最多识别的病害
            if (Object.keys(pestCounts).length > 0) {
              const [topPestName, count] = Object.entries(pestCounts).reduce(
                (max, [name, cnt]) => (cnt > max[1] ? [name, cnt] : max),
                ['', 0]
              );

              if (topPestName) {
                topPest.value = {
                  name: topPestName,
                  name_en: pestNamesEn[topPestName] || '',
                  count,
                };
              }
            }
          }
        }
      } catch (error) {
        console.warn('获取统计信息失败，使用当前页数据:', error);
        // 如果API调用失败，使用当前页的数据进行统计
        updateDiseaseStats();
      }
    } else {
      // 如果有筛选条件，只使用当前页的数据进行统计
      updateDiseaseStats();
    }

    // 更新加载状态
    isInitialized.value = true;
  } catch (err) {
    console.error('获取历史记录失败:', {
      error: err,
      message: err.message,
      response: err.response?.data,
      status: err.response?.status,
      config: {
        url: err.config?.url,
        method: err.config?.method,
        params: err.config?.params,
        headers: err.config?.headers,
      },
      stack: process.env.NODE_ENV === 'development' ? err.stack : undefined,
    });

    // 更友好的错误信息（第 77 批：全部走 i18n，英文界面不再出现中文报错）
    let errorMessage = t('history.loadRecordFailed');
    if (err.message.includes('timeout')) {
      errorMessage = t('history.timeout');
    } else if (err.response?.status === 401) {
      errorMessage = t('history.sessionExpired');
      router.push('/login');
    } else if (err.response?.status === 403) {
      errorMessage = t('history.forbidden');
    } else if (err.response?.data?.detail) {
      errorMessage = err.response.data.detail;
    }

    error.value = errorMessage;

    // 显示错误提示
    ElMessage.error({
      message: errorMessage,
      showClose: true,
      duration: 3000
    });
  } finally {
    isLoading.value = false;
    console.log('History state after fetch:', {
      historyItems: history.value?.length || 0,
      totalRecords: totalRecords.value,
      totalPages: totalPages.value,
      currentPage: currentPage.value,
      isLoading: isLoading.value,
      error: error.value,
      uniquePests: uniquePests.value?.size || 0,
      diseaseTypes: diseaseTypes.value?.length || 0,
    });
  }
};

// 处理分页变化
const handlePageChange = async (page) => {
  try {
    isLoading.value = true;
    currentPage.value = page;

    // 保存滚动位置
    const scrollContainer = document.querySelector('.history-container');
    const scrollPosition = scrollContainer ? scrollContainer.scrollTop : 0;

    // 构建筛选参数
    const filterParams = {};
    if (filterPest.value) filterParams.pest = filterPest.value;
    if (filterDate.value) filterParams.date = filterDate.value;

    // 翻页时清空多选：避免"在第 1 页勾选、翻到第 3 页再点批量删除"这种
    // 看不见选中项的误删
    selectedIds.value = [];

    // 传递当前筛选参数
    await fetchHistory(page, filterParams);

    // 恢复滚动位置
    if (scrollContainer) {
      scrollContainer.scrollTop = scrollPosition;
    }

    // 检查当前页是否有选中的病害，如果没有则尝试查找
    if (filterPest.value) {
      const hasSelectedPest = historyItems.value.some(item => {
        const pestName = item.disease_name || (item.pest_info?.name || '').trim();
        return pestName === filterPest.value;
      });

      if (!hasSelectedPest) {
        // 如果当前页没有选中的病害，尝试查找包含该病害的页面
        //
        // 第 16 批修复（此前这段逻辑实际从未生效）：
        //   1. 参数名用了 `disease_name`，后端只认 `pest` → 筛选被忽略，
        //      返回的是"全部记录"的总数；
        //   2. 读取 `data.count`，后端实际结构是 { data: { total, ... } }
        //      → 恒为 undefined，`undefined > 0` 为假，于是永远走到 else 分支
        //      被强制拉回第 1 页（用户看到的现象是"点下一页又跳回第一页"）。
        const searchResponse = await apiClient.get('/detection-history/', {
          params: {
            page: 1,
            page_size: itemsPerPage.value,
            pest: filterPest.value,
            // 范围必须与列表一致，否则算出来的页码会落在错误的记录集上
            ...scopeParams(),
          },
          silent: true
        });

        const matchedTotal = searchResponse?.data?.data?.total || 0;

        if (matchedTotal > 0) {
          // 计算包含该病害的页码（最后一条匹配记录的所在页）
          const itemIndex = matchedTotal - 1;
          const targetPage = Math.floor(itemIndex / itemsPerPage.value) + 1;

          // 如果目标页与当前页不同，则跳转（保留筛选条件，否则跳过去又是空页）
          if (targetPage !== page) {
            currentPage.value = targetPage;
            await fetchHistory(targetPage, filterParams);
          }
        } else if (page > 1) {
          // 如果找不到匹配的记录，且不在第一页，则返回第一页
          currentPage.value = 1;
          await fetchHistory(1, filterParams);
        }
      }
    }
  } catch (error) {
    console.error('分页跳转失败:', error);
    ElMessage.error(t('history.pageFailed', { detail: error.response?.data?.detail || error.message }));
  } finally {
    isLoading.value = false;
  }
};

// 筛选历史记录
const applyFilters = async () => {
  try {
    isLoading.value = true;

    // 保存当前筛选条件
    const currentPest = filterPest.value;
    const currentDate = filterDate.value;

    // 准备查询参数
    const params = {};
    if (currentPest) {
      params.pest = currentPest;
    }
    if (currentDate) {
      params.date = currentDate;
    }

    // 总是加载所有病害类型，确保筛选器列表完整
    await loadAllPestTypes();

    // 重置分页到第一页
    currentPage.value = 1;
    
    // 发起请求，强制刷新数据
    await fetchHistory(1, params);

    // 检查是否有匹配的记录
    if (history.value.length === 0) {
      totalRecords.value = 0;
      totalPages.value = 1;
      if (currentPest) {
        ElMessage.info(t('history.noRecordForPest', { name: currentPest }));
      } else if (currentDate) {
        ElMessage.info(t('history.noRecordForDate', { date: currentDate }));
      }
    }
  } catch (error) {
    console.error('应用筛选时出错:', error);
    ElMessage.error(t('history.filterFailed', { detail: error.response?.data?.detail || error.message }));
  } finally {
    isLoading.value = false;
  }
};

const showDetailModal = (item) => {
  selectedItem.value = item;
  isDetailModalVisible.value = true;
};

// 下载 PDF 报告
const downloadReport = async (item) => {
  if (!item) return;

  // 显示加载中
  const loadingInstance = ElLoading.service({
    lock: true,
    text: t('history.generatingReport'),
    background: 'rgba(0, 0, 0, 0.7)',
  });

  downloadingReportId.value = item.id;

  try {
    const fileName = await downloadDetectionReportPdf(item, {
      imageUrl: getFullImageUrl(item.image),
      annotatedImageUrl: item.annotated_image_url ? getFullImageUrl(item.annotated_image_url) : '',
      logoUrl,
    });
    ElMessage.success(t('history.reportGenerated', { name: fileName }));
  } catch (error) {
    console.error('生成 PDF 报告失败:', error);
    ElMessage.error(t('history.reportFailed', { detail: error?.message || t('msg.operationFailedRetry') }));
  } finally {
    if (loadingInstance) {
      loadingInstance.close();
    }
    downloadingReportId.value = null;
  }
};

/**
 * 导出 Excel（第 43 批）
 * 带上当前筛选条件（病害 / 日期 / 用户 / 全部用户），导出的就是"你现在看到的结果"。
 * 接口需要 Token，所以用 blob 方式下载而不是直接 window.open。
 */
const exportExcel = async () => {
  if (exporting.value) return;
  exporting.value = true;
  try {
    const params = {
      pest: filterPest.value || undefined,
      date: filterDate.value || undefined,
      search: searchKeyword.value || undefined,
      // 第 72 批：把界面语言带过去，导出文件的表头/工作表名跟着走
      lang: locale.value === 'en' ? 'en' : 'zh',
      ...scopeParams(),
    };

    const response = await apiClient.get('detection-history/export-excel/', {
      params,
      responseType: 'blob',
    });

    const blob = new Blob([response.data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
    link.href = url;
    link.download = `${t('history.exportFileName')}-${stamp}.xlsx`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);

    ElMessage.success(t('history.excelDownloading'));
  } catch (error) {
    console.error('导出 Excel 失败:', error);
    // 出错时后端返回的是 JSON（blob 里），尽量把提示读出来
    let message = t('history.exportFailed');
    try {
      const text = await error?.response?.data?.text?.();
      if (text) {
        const parsed = JSON.parse(text);
        message = parsed.message || parsed.detail || message;
      }
    } catch { /* 忽略解析失败 */ }
    ElMessage.error(message);
  } finally {
    exporting.value = false;
  }
};

const deleteHistoryItem = async (id) => {
  if (confirm(t('history.confirmDeleteOne'))) {
    try {
      await apiClient.delete(`detection-history/${id}/`);  // 添加了末尾的斜杠
      // 同步清理选中态，避免批量删除时带上已删除的 id
      selectedIds.value = selectedIds.value.filter((item) => item !== id);
      await fetchHistory(currentPage.value);
      ElMessage.success(t('history.recordDeleted'));
    } catch (error) {
      console.error('删除记录失败:', error);
      ElMessage.error(t('history.deleteRecordFailed', { detail: error.response?.data?.detail || error.message }));
    }
  }
};

const clearAllHistory = async () => {
  // 注意：本页只展示本人记录，这里的"清除全部"也只会删除**你自己**的记录
  // （后端 clear-all 只在管理员显式带 all_users=true 时才清空所有人，
  //   而本页已不再携带该参数）。
  if (window.confirm(t('history.clearAllConfirm'))) {
    try {
      await apiClient.delete('/detection-history/clear-all/');
      selectedIds.value = [];
      ElMessage.success(t('history.clearedAll'));
      await fetchHistory(1); // Refresh the view to show it's empty
    } catch (err) {
      console.error('Failed to clear history:', err);
      ElMessage.error(t('history.clearFailed'));
    }
  }
};

// 删除重复的 onMounted 钩子
</script>

<style scoped>
/* 基础样式重置 */
.history-view {
  padding: 1.5rem 0;
  max-width: 1400px;
  margin: 0 auto;
}

/* 统计卡片样式 */
.stats-cards .stat-card {
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  border: 1px solid rgba(0,0,0,0.05);
}

.stats-cards .stat-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 0.5rem 1rem rgba(0,0,0,0.1) !important;
}

.stat-icon {
  width: 40px;
  height: 40px;
  background-color: #f8f9fa;
}

/* 历史记录网格布局 */
.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem;
  padding: 1rem;
}

.history-item {
  background: white;
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  display: flex;
  flex-direction: column;
  /* 第 22 批：卡片左上角的多选框（.item-select）需要以卡片为定位基准 */
  position: relative;
}

.history-item:hover {
  transform: translateY(-5px);
  box-shadow: 0 10px 20px rgba(0,0,0,0.1);
}

/* 图片容器 */
.history-item-image-wrapper {
  position: relative;
  width: 100%;
  padding-top: 75%; /* 4:3 宽高比 */
  background: #f8f9fa;
  overflow: hidden;
}

.history-image {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s ease;
}

.history-item:hover .history-image {
  transform: scale(1.05);
}

/* 信息区域 */
.history-item-info {
  padding: 1.25rem;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.pest-name {
  font-size: 1.1rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: #2c3e50;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-meta {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.75rem;
  font-size: 0.85rem;
  color: #6c757d;
}

.timestamp {
  font-size: 0.8rem;
  color: #868e96;
  margin-bottom: 1rem;
}

/* 操作按钮 */
.history-item-actions {
  margin-top: auto;
}

.btn-group {
  display: flex;
  gap: 0.5rem;
}

.btn-action {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.4rem 0.75rem;
  font-size: 0.85rem;
  border-radius: 6px;
  transition: all 0.2s;
}

.btn-view {
  background-color: #e8f4fd;
  color: #0d6efd;
  border: 1px solid #cfe2ff;
}

.btn-view:hover {
  background-color: #d0e3ff;
  border-color: #9ec5fe;
}

.btn-download {
  background-color: #e8f5e9;
  color: #198754;
  border: 1px solid #d1e7dd;
}

.btn-download:hover {
  background-color: #d1e7dd;
  border-color: #a3cfbb;
}

.btn-delete {
  background-color: #fef2f2;
  color: #dc3545;
  border: 1px solid #f5c2c7;
}

.btn-delete:hover {
  background-color: #f8d7da;
  border-color: #ea868f;
}

/* 分页样式 */
.pagination-container {
  margin-top: 2rem;
  padding: 0 1rem 1.5rem;
}

.pagination {
  display: flex;
  justify-content: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.page-btn {
  padding: 0.375rem 0.75rem;
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.page-btn:not(:disabled):hover {
  background: #f8f9fa;
  border-color: #dee2e6;
}

.page-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.page-info {
  display: flex;
  align-items: center;
  padding: 0.375rem 0.75rem;
  color: #6c757d;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .history-grid {
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    padding: 0.5rem;
    gap: 1rem;
  }

  .history-item-info {
    padding: 1rem;
  }

  .btn-action .btn-text {
    display: none;
  }

  .btn-action {
    padding: 0.4rem;
  }
}

/* 加载状态 */
.status-message {
  padding: 3rem 1rem;
  text-align: center;
  color: #6c757d;
}

/* 第 31 批：空状态的下一步按钮（原来只有一句话，剩下一大片空白） */
.empty-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.empty-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 16px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  color: #fff;
  background: linear-gradient(135deg, #2a7f53, #1f6343);
  border: 1px solid #1f6343;
  box-shadow: 0 8px 16px rgba(25, 79, 55, 0.18);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.empty-action-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 22px rgba(25, 79, 55, 0.24);
}

.empty-action-btn.is-plain {
  color: #245c3d;
  background: #fff;
  border-color: #bfe3cd;
  box-shadow: none;
}

.empty-action-btn.is-plain:hover {
  background: #f1f9f4;
}

.loading-spinner {
  width: 3rem;
  height: 3rem;
  margin: 0 auto 1rem;
  border: 0.3rem solid #f3f3f3;
  border-top: 0.3rem solid #3498db;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* 错误状态 */
.error {
  color: #dc3545;
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 3rem 1rem;
  color: #6c757d;
}

.empty-state i {
  font-size: 3rem;
  margin-bottom: 1rem;
  opacity: 0.6;
}

/* 筛选区域 */
.filters-bar {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  margin-top: 1rem;
}

.filter-item {
  min-width: 150px;
}

/* 卡片标题 */
.card-header {
  background-color: #f8f9fa;
  border-bottom: 1px solid rgba(0,0,0,0.05);
}

.card-title {
  color: #2c3e50;
  font-weight: 600;
}

/* 响应式调整 */
@media (max-width: 576px) {
  .stats-cards .col-6 {
    margin-bottom: 1rem;
  }

  .filters-bar {
    flex-direction: column;
    gap: 0.5rem;
  }

  .filter-item {
    width: 100%;
  }
}
/* 修复网格布局 */
.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem;
  padding: 1rem 0;
}

.history-item {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.history-item:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

/* 未知病害的样式 */
.history-item.missing-pest-info {
  border-left: 4px solid #ff9800;
  background-color: #fff8e1;
}

.history-item-image-wrapper {
  width: 100%;
  height: 200px;
  overflow: hidden;
}

.history-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  cursor: pointer;
  transition: transform 0.3s ease;
}

.history-item:hover .history-image {
  transform: scale(1.03);
}

.history-item-info {
  padding: 1rem;
  flex-grow: 1;
  display: flex;
  flex-direction: column;
}

.pest-name {
  margin: 0 0 0.5rem 0;
  font-size: 1.1rem;
  color: #333;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.pest-name.unknown {
  color: #ff5722;
}

.item-meta {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
  color: #666;
}

.timestamp {
  margin: 0.5rem 0 0 0;
  font-size: 0.85rem;
  color: #888;
}

.debug-info {
  font-size: 0.75rem;
  color: #888;
  background: #f5f5f5;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  margin-left: 0.5rem;
  font-family: monospace;
}

.history-item-actions {
  margin-top: 12px;
  width: 100%;
}

.btn-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.btn-action {
  flex: 1;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  transition: all 0.2s ease;
}

.details-btn {
  background-color: #4caf50;
  color: white;
}

.details-btn:hover {
  background-color: #43a047;
}

.delete-btn {
  background-color: #f44336;
  color: white;
}

.delete-btn:hover {
  background-color: #e53935;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .history-grid {
    grid-template-columns: 1fr;
  }
}
.history-view {
  padding: 1.5rem 0;
  max-width: 1400px;
  margin: 0 auto;
}

/* 标题区域 */
.history-header {
  margin-bottom: 1.5rem;
  text-align: center;
}

.history-header h1 {
  font-size: 2rem;
  color: #2c3e50;
  margin-bottom: 0.5rem;
  font-weight: 700;
}

.history-header p {
  color: #6c757d;
  font-size: 1.1rem;
  margin-bottom: 0;
}

/* 统计卡片 */
.stats-cards {
  margin-bottom: 1.5rem;
  flex-direction: column;
  gap: 2rem;
}

.history-stats {
  display: flex;
  justify-content: space-around;
  gap: 1rem;
  flex-wrap: wrap;
}

.stat-item {
  text-align: center;
  padding: 1rem;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.05);
  flex-grow: 1;
  min-width: 150px;
}

.stat-number {
  font-size: 2rem;
  font-weight: 700;
  color: #667eea;
}

.stat-label {
  font-size: 0.9rem;
  color: #7f8c8d;
}

.filters-bar {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  background-color: #fff;
  padding: 1rem 1.5rem;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.filters-bar label {
  font-weight: 500;
}

.filters-bar select,
.filters-bar input {
  padding: 0.5rem 1rem;
  border-radius: 6px;
  border: 1px solid #ced4da;
  min-width: 180px;
}

.clear-all-btn {
  margin-left: auto; /* 将按钮推到最右边 */
  background-color: #ef4444; /* 红色背景 */
  color: white;
  border: none;
  padding: 0.6rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.3s ease;
}

.clear-all-btn:hover {
  background-color: #dc2626; /* 深红色 */
}

.clear-all-btn i {
  margin-right: 0.5rem;
}

.status-message {
  text-align: center;
  padding: 4rem 0;
  color: #7f8c8d;
  font-size: 1.2rem;
}

.status-message .fas {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.loading-spinner {
  border: 4px solid #f3f3f3;
  border-top: 4px solid #667eea;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  animation: spin 1s linear infinite;
  margin: 0 auto 1rem;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.history-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 2rem;
}

.history-item {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.05);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: transform 0.3s, box-shadow 0.3s;
}

.history-item:hover {
  transform: translateY(-5px);
  box-shadow: 0 8px 20px rgba(0,0,0,0.08);
}

.history-item-image-wrapper {
  width: 100%;
  padding-top: 75%; /* 4:3 aspect ratio */
  position: relative;
  cursor: pointer;
}

.history-image {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
}

.history-item:hover .history-image {
  transform: scale(1.05);
}

.history-item-info {
  padding: 1rem;
  text-align: center;
  display: flex;
  flex-direction: column;
  flex-grow: 1;
}

.pest-name {
  font-size: 1.1rem;
  font-weight: 600;
  color: #333;
  margin: 0 0 0.75rem;
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.item-meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.9rem;
  color: #555;
  margin-bottom: 0.75rem;
  padding: 0 0.5rem;
}

.item-meta span {
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

/* 第 22 批：与「识别记录管理」合并后新增的控件样式 */
.scope-switch {
  padding: 0.4rem 0.9rem;
  background: var(--brand-50, #eef7f1);
  border: 1px solid var(--brand-100, #d8ecdf);
  border-radius: 999px;
}

.batch-bar {
  padding: 0.6rem 0.9rem;
  background: #fff;
  border: 1px solid #eef0f3;
  border-radius: 12px;
}

/* 第 43 批：导出按钮与管理员批量操作之间的分隔 */
.batch-divider {
  width: 1px;
  height: 20px;
  margin: 0 4px;
  background: var(--border, #e2ebe5);
}

/* 卡片左上角的多选框（仅管理员） */
.item-select {
  position: absolute;
  top: 0.5rem;
  left: 0.6rem;
  z-index: 2;
  padding: 0 0.25rem;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 6px;
}

/* 识别者徽标（管理员查看"全部用户"时显示） */
.item-owner {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  align-self: center;
  max-width: 90%;
  padding: 0.18rem 0.7rem;
  margin-bottom: 0.6rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--brand-700, #2f7d4f);
  background: var(--brand-50, #eef7f1);
  border: 1px solid var(--brand-100, #d8ecdf);
  border-radius: 999px;
}

.item-owner .item-owner-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timestamp {
  font-size: 0.85rem;
  color: #7f8c8d;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
}

.card-actions {
  display: flex;
  justify-content: space-around;
  gap: 1rem;
  margin-top: auto;
}

.details-btn, .delete-btn {
  background: none;
  border: 1px solid #ddd;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.3s;
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.details-btn {
  color: #3498db;
  border-color: #3498db;
}

.details-btn:hover {
  background: #3498db;
  color: white;
}

.delete-btn {
  color: #e74c3c;
  border-color: #e74c3c;
}

.delete-btn:hover {
  background: #e74c3c;
  color: white;
}

.pagination-container {
  margin-top: 2rem;
  display: flex;
  justify-content: center;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 0.5rem; /* 调整按钮间距 */
}

.page-btn {
  padding: 0.5rem 1rem;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 6px;
  cursor: pointer;
}

.page-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: #fff;
  padding: 2rem;
  border-radius: 12px;
  width: 90%;
  max-width: 800px;
  position: relative;
}

.modal-close {
  position: absolute;
  top: 1rem;
  right: 1rem;
  font-size: 1.5rem;
  background: none;
  border: none;
  cursor: pointer;
}

.modal-body {
  display: flex;
  gap: 2rem;
}

.modal-image {
  flex: 1;
}

.modal-image img {
  width: 100%;
  border-radius: 8px;
}

.modal-details {
  flex: 1;
}

.detail-section {
  margin-bottom: 1.5rem;
}

.detail-section h3 {
  margin-bottom: 0.5rem;
  font-size: 1.1rem;
  color: #333;
  border-bottom: 2px solid #667eea;
  padding-bottom: 0.3rem;
  display: inline-block;
}

.modal-details h3 {
  font-size: 1.2rem;
  color: #34495e;
  margin-bottom: 0.5rem;
  border-bottom: 2px solid #ecf0f1;
  padding-bottom: 0.3rem;
}

.prevention-methods-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.prevention-method strong {
  color: #667eea;
}

.prevention-method p {
  margin-top: 0.25rem;
  line-height: 1.6;
}

.modal-details p {
  color: #555;
  line-height: 1.7;
}

@media (max-width: 992px) {
  .history-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .history-grid {
    grid-template-columns: 1fr;
  }
  .modal-body {
    flex-direction: column;
  }
}

  /* ================= 现代化覆写（设计变量见 assets/theme.css） ================= */
  .history-view {
    width: 100%;
    max-width: 1500px;
    margin: 0 auto;
    padding: 8px 24px 48px;
    box-sizing: border-box;
  }

  .history-header h1 {
    font-size: 30px;
    font-weight: 800;
    letter-spacing: 0.5px;
    color: var(--ink-900);
  }

  .history-header p {
    font-size: 14.5px;
    color: var(--ink-500);
  }

  /* 统计卡片 */
  .stats-cards .stat-card {
    position: relative;
    padding: 22px 20px;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
    box-shadow: var(--shadow-sm);
    transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
  }

  .stats-cards .stat-card:hover {
    transform: translateY(-4px);
    box-shadow: var(--shadow-md);
  }

  .stat-icon {
    width: 46px;
    height: 46px;
    border-radius: 14px;
    background: var(--brand-50);
  }

  .stat-number {
    font-size: 26px;
    font-weight: 800;
    color: var(--ink-900);
  }

  .stat-label {
    font-size: 13px;
    color: var(--ink-500);
  }

  /* 区块卡片 */
  .chart-section .card,
  .history-section .card {
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
  }

  .chart-section .card-header,
  .history-section .card-header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }

  .card-title {
    font-weight: 700;
    color: var(--ink-800);
  }

  /* 筛选栏 */
  .filters-bar {
    gap: 12px;
  }

  .filter-item label {
    font-size: 12.5px;
    color: var(--ink-500);
  }

  .filters-bar .form-select,
  .filters-bar .form-control {
    border-radius: var(--radius-sm);
    border-color: var(--border-strong);
  }

  /* 记录卡片 */
  .history-grid {
    gap: 20px;
    padding: 20px;
  }

  .history-item {
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
    box-shadow: var(--shadow-sm);
    transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
  }

  .history-item:hover {
    transform: translateY(-5px);
    box-shadow: var(--shadow-lg);
  }

  .history-item-image-wrapper {
    background: var(--ink-50);
  }

  .history-item-info {
    padding: 18px;
    gap: 6px;
  }

  .pest-name {
    font-size: 16.5px;
    font-weight: 700;
    color: var(--ink-800);
  }

  .pest-name.unknown {
    color: var(--warning);
    font-size: 15px;
  }

  .item-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    font-size: 12.5px;
    color: var(--ink-500);
  }

  .item-meta i {
    color: var(--brand-500);
    margin-right: 4px;
  }

  .timestamp {
    font-size: 12.5px;
    color: var(--ink-400);
  }

  .history-item-actions {
    margin-top: auto;
    padding-top: 12px;
  }

  .btn-action {
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--surface);
    font-size: 13px;
    font-weight: 600;
    transition: all var(--dur) var(--ease);
  }

  .btn-action.btn-view {
    color: var(--brand-700);
    border-color: var(--brand-200);
    background: var(--brand-50);
  }

  .btn-action.btn-view:hover {
    background: var(--gradient-brand);
    border-color: transparent;
    color: #fff;
  }

  .btn-action.btn-download {
    color: var(--info);
    border-color: #d3e3ec;
    background: #f3f8fb;
  }

  .btn-action.btn-download:hover {
    background: var(--info);
    border-color: transparent;
    color: #fff;
  }

  .btn-action.btn-delete {
    color: var(--danger);
    border-color: #f0d3cf;
    background: #fdf5f4;
  }

  .btn-action.btn-delete:hover {
    background: var(--danger);
    border-color: transparent;
    color: #fff;
  }

  /* 分页 */
  .pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .page-btn {
    padding: 8px 15px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--surface);
    color: var(--ink-600);
    font-size: 13px;
    font-weight: 600;
    transition: all var(--dur) var(--ease);
  }

  .page-btn:hover:not(:disabled) {
    border-color: var(--brand-400);
    background: var(--brand-50);
    color: var(--brand-700);
  }

  .page-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .page-info {
    font-size: 13px;
    color: var(--ink-500);
  }

  /* 状态提示 */
  .status-message {
    padding: 56px 24px;
    color: var(--ink-500);
    font-size: 15px;
  }

  .status-message.error {
    color: var(--danger);
  }

  .action-buttons {
    display: flex;
    justify-content: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 16px;
  }

  /* 详情弹窗 */
  .modal-overlay {
    background: rgba(19, 58, 41, 0.45);
    backdrop-filter: blur(2px);
  }

  .modal-content {
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-lg);
    padding: 28px;
  }

  .detail-section {
    margin-bottom: 18px;
    padding: 16px 18px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface-muted);
  }

  .detail-section h4 {
    margin-bottom: 10px;
    font-size: 15px;
    font-weight: 700;
    color: var(--brand-700);
  }

  .prevention-method {
    padding: 12px 14px;
    margin-bottom: 10px;
    border-radius: var(--radius-sm);
    background: var(--surface);
    border: 1px solid var(--border);
  }

  @media (max-width: 768px) {
    .history-view {
      padding: 0 16px 32px;
    }

    .history-header h1 {
      font-size: 23px;
    }

    .history-grid {
      grid-template-columns: 1fr;
      padding: 12px;
    }
  }
</style>


