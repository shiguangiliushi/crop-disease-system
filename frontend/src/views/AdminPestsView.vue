<template>
  <div class="pest-admin tinted-page">
    <!-- 页头（沿用全站 .admin-hero：深绿实底 + 白色文字） -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-book-medical"></i></span>
        <div>
          <h1>{{ t('pestAdmin.title') }}</h1>
          <p>{{ t('pestAdmin.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-button class="btn-on-brand" @click="openCreate">
          <i class="fas fa-plus"></i> {{ t('wiki.addPest') }}
        </el-button>
        <el-button class="btn-on-brand" @click="importVisible = true">
          <i class="fas fa-file-import"></i> {{ t('wiki.bulkImport') }}
        </el-button>
        <el-button plain :loading="loading" @click="loadList">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
      </div>
    </header>

    <!-- 概览小卡 -->
    <div class="admin-stats">
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-book"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.total }}</div>
          <div class="stat-tile-label">{{ t('pestAdmin.statTotal') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--processing">
        <span class="stat-tile-icon"><i class="fas fa-seedling"></i></span>
        <div>
          <div class="stat-tile-value">{{ cropOptions.length }}</div>
          <div class="stat-tile-label">{{ t('pestAdmin.statCrops') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--ok">
        <span class="stat-tile-icon"><i class="fas fa-filter"></i></span>
        <div>
          <div class="stat-tile-value">{{ total }}</div>
          <div class="stat-tile-label">{{ t('pestAdmin.statFiltered') }}</div>
        </div>
      </div>
    </div>

    <!-- 筛选：搜索 / 作物 -->
    <div class="filter-bar">
      <el-input
        v-model="filters.search"
        :placeholder="t('pestAdmin.searchPlaceholder')"
        clearable
        style="width: 280px"
        @keyup.enter="handleFilter"
        @clear="handleFilter"
      >
        <template #prefix><i class="fas fa-magnifying-glass"></i></template>
      </el-input>

      <el-select
        v-model="filters.crop_type"
        :placeholder="t('pestAdmin.cropPlaceholder')"
        clearable
        filterable
        style="width: 180px"
        @change="handleFilter"
        @clear="handleFilter"
      >
        <!--
          ⚠️ 第 190 批：`value` 必须是**作物键**（库里 `crop_type` 的原值，中文），
          `label` 才是给人看的显示名。原来 value/label 都直接用 crops 数组里的中文，
          所以中文界面下没问题；但一旦把 label 本地化（英文界面显示 Peach），
          若 value 也跟着变成显示名，后端按 `crop_type` 精确匹配就会**一条都筛不到**。
          这里的写法与农户端百科页一致（那边用 { key, name } 两个字段）。
        -->
        <el-option
          v-for="crop in cropOptions"
          :key="crop.key"
          :label="crop.label"
          :value="crop.key"
        />
      </el-select>

      <el-button type="primary" plain @click="handleFilter">{{ t('pestAdmin.query') }}</el-button>
      <el-button text @click="resetFilters">{{ t('pestAdmin.reset') }}</el-button>

      <span class="filter-hint">
        <i class="fas fa-circle-info"></i> {{ t('pestAdmin.filterHint') }}
      </span>
    </div>

    <!-- 列表 -->
    <el-card class="panel-card" shadow="never">
      <div class="panel-head">
        <div class="panel-head-left">
          <span class="panel-head-icon"><i class="fas fa-list"></i></span>
          <h3>{{ t('pestAdmin.listTitle') }}</h3>
          <span class="panel-count">{{ total }}</span>
        </div>
        <div class="panel-head-right">
          <span class="panel-note">{{ t('pestAdmin.listNote') }}</span>
        </div>
      </div>

      <el-table
        v-loading="loading"
        :data="items"
        stripe
        style="width: 100%"
        :empty-text="t('pestAdmin.empty')"
      >
        <el-table-column :label="t('pestAdmin.colPest')" min-width="240">
          <template #default="{ row }">
            <div class="pest-cell">
              <img
                v-if="row.image"
                :src="toAbsoluteMediaUrl(row.image)"
                :alt="localizedField(row, 'name')"
                class="pest-thumb"
              >
              <span v-else class="pest-thumb pest-thumb--empty"><i class="fas fa-image"></i></span>
              <div class="pest-cell-text">
                <strong>{{ localizedField(row, 'name') }}</strong>
                <em>{{ row.english_identifier }}</em>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column :label="t('pestAdmin.colCrop')" width="140">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ localizedField(row, 'crop_type') }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column :label="t('pestAdmin.colSymptoms')" min-width="260">
          <template #default="{ row }">
            <span class="pest-symptoms">{{ localizedField(row, 'symptoms') || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column :label="t('pestAdmin.colActions')" width="230" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openEdit(row)">
              {{ t('wiki.edit') }}
            </el-button>
            <el-button size="small" link @click="openOnSite(row)">
              {{ t('pestAdmin.viewOnSite') }}
            </el-button>
            <el-button size="small" type="danger" link @click="confirmDelete(row)">
              {{ t('wiki.delete') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          :total="total"
          background
          @size-change="handleSizeChange"
          @current-change="loadList"
        />
      </div>
    </el-card>

    <!-- 新增 / 编辑（复用百科页那两个弹窗：农户端的就地编辑已移到管理后台） -->
    <PestEditDialog
      v-model="editVisible"
      :pest-id="editingId"
      :crop-types="cropOptions"
      @saved="handleSaved"
    />

    <!-- 批量导入（Excel / CSV） -->
    <PestImportDialog v-model="importVisible" @imported="handleSaved" />
  </div>
</template>

<script>
/**
 * 病害百科维护（第 122 批新增，管理后台）
 * ============================================================================
 * 为什么要有这一页：
 *   病害百科的维护入口原来**长在农户端的百科页上**（`/pests` 顶部的
 *   「管理员模式」工具条 + 每张卡片上的编辑/删除按钮）。于是两种人不舒服：
 *     · 农户打开百科，看到的是"管理员模式：可直接新增、编辑、删除…"；
 *     · 管理员想批量管理词条，却只能在"卡片流"里一条条找（那一页每页 6 条、
 *       而且是给农户看的排版）。
 *
 *   第 117 批把管理后台做成独立外壳之后，这就是最后一块"管理员混在农户页面里"的
 *   功能。现在它和新闻管理、用户管理一样，是后台侧栏里的一页：
 *   **服务端搜索 + 作物筛选 + 分页 + 表格 + 新增/编辑/批量导入/删除**。
 *
 * 农户端的 `/pests` 因此变回纯阅读页（工具条与卡片按钮都删掉了）。
 * 详情页 `/pests/:id` 仍保留"编辑本词条"—— 那针对的是"你正在看的这一条"，
 * 属于就地纠错，不是"管理整套资料"。
 *
 * 复用的东西：`PestEditDialog` / `PestImportDialog`（第 44/84 批）与 `api/pest.js`
 * 的写接口都没动，只是换了个更合适的宿主页面。
 */
import { computed, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import PestEditDialog from '@/components/PestEditDialog.vue';
import PestImportDialog from '@/components/PestImportDialog.vue';
import { deletePest, fetchPestList, formatPestError, toAbsoluteMediaUrl } from '@/api/pest';
// 作物选项走日历模块那个"取自百科真实作物"的接口（同一个后端接口只留一处封装）；
// ⚠️ 别改用 `/api/pest-types/` —— 那个返回的是**病害名称**，见 api/pest.js 的说明
import { fetchCalendarCrops } from '@/api/calendar';
import { useI18n } from '@/i18n';
import { useLocalized } from '@/utils/localized';  // 内容数据（病害名/作物名）按语言取值
import { useQueryState } from '@/composables/useQueryState';  // 筛选/分页进 URL

export default {
  name: 'AdminPestsView',
  components: { PestEditDialog, PestImportDialog },
  setup() {
    const { t } = useI18n();
    const { localizedField } = useLocalized();
    const router = useRouter();

    const loading = ref(false);
    const items = ref([]);
    const total = ref(0);
    const page = ref(1);
    const pageSize = ref(10);
    const stats = reactive({ total: 0 });
    const cropOptions = ref([]);

    const filters = reactive({ search: '', crop_type: '' });

    const buildParams = () => {
      const params = { page: page.value, page_size: pageSize.value };
      if (filters.search.trim()) params.search = filters.search.trim();
      if (filters.crop_type) params.crop_type = filters.crop_type;
      return params;
    };

    const loadList = async () => {
      loading.value = true;
      try {
        const data = await fetchPestList(buildParams());
        items.value = Array.isArray(data?.results) ? data.results : Array.isArray(data) ? data : [];
        total.value = data?.count ?? items.value.length;
      } catch (error) {
        console.error('获取病害列表失败:', error);
        items.value = [];
        total.value = 0;
        ElMessage.error(formatPestError(error, t('pestAdmin.loadFailed')));
      } finally {
        loading.value = false;
      }
    };

    /** 词条总数单独取一次（列表带筛选，count 是筛选后的） */
    const loadStats = async () => {
      try {
        const data = await fetchPestList({ page: 1, page_size: 1 });
        stats.total = data?.count ?? 0;
      } catch (error) {
        console.warn('获取病害统计失败:', error);
      }
    };

    /**
     * 作物筛选项：**键**用库里的原值（中文），**显示名**按当前语言取
     *
     * ⚠️ 第 190 批：原来直接把 `/api/calendar/crops/` 返回的中文数组当成 {label, value}，
     * 英文界面下管理员看到的作物筛选是中文（同一个项目里农户端百科页早就用
     * `crop_type_en` 显示了，见 PestEncyclopediaView 的 cropOptions）。
     * 现在补上英文显示名 —— 但**值仍然是中文键**：后端 `?crop_type=` 是按
     * `crop_type` 字段**精确匹配**的，把显示名当值传过去会一条都筛不到。
     * 英文名从病害列表里的 `crop_type_en` 取（与百科页同一个来源）。
     */
    const loadCropOptions = async () => {
      try {
        const data = await fetchCalendarCrops();
        const keys = Array.isArray(data?.crops) ? data.crops : [];

        // 英文显示名：从一份"每作物取一条"的病害列表里拿 crop_type_en
        const enMap = {};
        try {
          const page = await fetchPestList({ page: 1, page_size: 200 });
          for (const row of page?.results || []) {
            if (row?.crop_type && row?.crop_type_en) enMap[row.crop_type] = row.crop_type_en;
          }
        } catch (error) {
          // 拿不到英文名不影响筛选能用，回落成中文显示名
          console.warn('获取作物英文名失败，回落中文显示:', error);
        }

        cropOptions.value = keys.map((key) => ({
          key,
          label: localizedField({ crop_type: key, crop_type_en: enMap[key] || '' }, 'crop_type'),
        }));
      } catch (error) {
        console.warn('获取作物类型失败:', error);
        cropOptions.value = [];
      }
    };

    // 第 98 批的约定：筛选与分页写进 URL（刷新/后退都还在）
    const filterRef = (key) => ({
      get value() { return filters[key]; },
      set value(next) { filters[key] = next ?? ''; },
    });

    const { isReady: queryReady } = useQueryState({
      fields: {
        page: { ref: page, type: 'int', default: 1 },
        page_size: { ref: pageSize, type: 'int', default: 10 },
        search: { ref: filterRef('search'), type: 'string', default: '' },
        crop_type: { ref: filterRef('crop_type'), type: 'string', default: '' },
      },
      onExternalChange: () => loadList(),
    });

    const handleFilter = () => {
      page.value = 1;
      loadList();
    };

    /** 改每页条数回到第 1 页：否则"在第 5 页改成 50 条"会让 page 越界、后端直接 404 */
    const handleSizeChange = () => {
      page.value = 1;
      loadList();
    };

    const resetFilters = () => {
      filters.search = '';
      filters.crop_type = '';
      handleFilter();
    };

    // ---------- 新增 / 编辑 / 删除 ----------
    const editVisible = ref(false);
    const editingId = ref(null);
    const importVisible = ref(false);

    const openCreate = () => {
      editingId.value = null;
      editVisible.value = true;
    };

    const openEdit = (row) => {
      if (!row?.id) return;
      editingId.value = row.id;
      editVisible.value = true;
    };

    /** 保存/导入之后：刷新当前页与统计（保持筛选条件） */
    const handleSaved = async () => {
      await Promise.all([loadList(), loadStats(), loadCropOptions()]);
    };

    /** 到农户端看这一条（新标签页，不打断手头的管理工作） */
    const openOnSite = (row) => {
      if (!row?.english_identifier) return;
      const url = router.resolve({
        name: 'PestDetail',
        params: { english_identifier: row.english_identifier },
      }).href;
      window.open(url, '_blank', 'noopener');
    };

    const confirmDelete = async (row) => {
      const name = localizedField(row, 'name');
      try {
        await ElMessageBox.confirm(
          t('pestAdmin.deleteConfirm', { name }),
          t('wiki.deleteTitle'),
          {
            type: 'warning',
            confirmButtonText: t('msg.confirmDelete'),
            cancelButtonText: t('msg.cancel'),
          },
        );
      } catch {
        return; // 用户取消
      }

      try {
        await deletePest(row.id);
        ElMessage.success(t('pestAdmin.deleted', { name }));
        // 删掉本页最后一条时回退一页，避免停在空白页（与其它管理页同一处理）
        if (items.value.length === 1 && page.value > 1) {
          page.value -= 1;
        }
        await handleSaved();
      } catch (error) {
        console.error('删除病害失败:', error);
        ElMessage.error(formatPestError(error, t('msg.deleteFailedRetry')));
      }
    };

    // 等 URL 参数应用完再加载（否则带参数打开会先用默认值查一次、再查一次）
    watch(queryReady, (ready) => {
      if (ready) {
        loadCropOptions();
        loadStats();
        loadList();
      }
    }, { immediate: true });

    return {
      t,
      localizedField,
      toAbsoluteMediaUrl,
      loading, items, total, page, pageSize, stats, cropOptions, filters,
      loadList, handleFilter, handleSizeChange, resetFilters,
      editVisible, editingId, importVisible,
      openCreate, openEdit, handleSaved, openOnSite, confirmDelete,
    };
  },
};
</script>

<style scoped>
.pest-admin {
  /* 工作区内边距（.tinted-page 已经给了底色与圆角） */
  padding: 22px;
}

.pest-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.pest-thumb {
  width: 44px;
  height: 34px;
  flex: 0 0 auto;
  border-radius: 8px;
  object-fit: cover;
  border: 1px solid var(--border, #e2ebe5);
}

.pest-thumb--empty {
  display: grid;
  place-items: center;
  background: var(--ink-50, #f8fbf9);
  color: var(--ink-300, #c6d2cb);
  font-size: 13px;
}

.pest-cell-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.pest-cell-text strong {
  font-size: 14px;
  color: var(--ink-800, #24352c);
}

.pest-cell-text em {
  font-style: normal;
  font-size: 11.5px;
  color: var(--ink-400, #9dada5);
  word-break: break-all;
}

.pest-symptoms {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  font-size: 13px;
  line-height: 1.7;
  color: var(--ink-600, #566b60);
}

.filter-hint {
  margin-left: auto;
  font-size: 12.5px;
  color: var(--ink-500, #78897f);
}

.filter-hint i {
  margin-right: 5px;
  color: var(--brand-500, #3d9a68);
}

.panel-note {
  font-size: 12.5px;
  color: var(--ink-500, #78897f);
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

@media (max-width: 900px) {
  .filter-hint {
    display: none;
  }
}
</style>
