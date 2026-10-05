<template>
  <div class="prevention-page">
    <div class="header-actions">
      <div class="back-home">
        <el-button type="primary" link @click="goToHome">
          <i class="el-icon-arrow-left"></i> {{ t('preventPage.backHome') }}
        </el-button>
      </div>
      
      <div class="search-filter">
        <el-input
          v-model="searchQuery"
          :placeholder="t('preventPage.searchPlaceholder')"
          clearable
          @clear="handleSearch"
          @keyup.enter="handleSearch"
          style="width: 300px; margin-right: 15px;"
        >
          <template #append>
            <el-button :icon="Search" @click="handleSearch" />
          </template>
        </el-input>
        
        <el-select 
          v-model="selectedCategory" 
          :placeholder="t('preventPage.categoryPlaceholder')" 
          clearable
          @change="handleSearch"
          @clear="handleSearch"
          style="width: 200px; margin-right: 15px;"
        >
          <el-option
            v-for="category in availableCategories"
            :key="category.value"
            :label="category.label"
            :value="category.value"
          />
        </el-select>
      </div>
    </div>
    <div class="page-banner">
      <h1>{{ t('preventPage.title') }}</h1>
      <p>{{ t('preventPage.subtitle') }}</p>
    </div>

    <div v-if="isLoading" class="loading-state">
      <div class="loading-spinner"></div>
      <p>{{ t('preventPage.loading') }}</p>
    </div>
    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-triangle"></i>
      <p>{{ t('preventPage.loadFailed') }}</p>
      <button @click="retryLoad" class="retry-btn">
        <i class="fas fa-redo"></i> {{ t('preventPage.reload') }}
      </button>
    </div>
    <div v-else-if="preventionData.length === 0" class="empty-state">
      <i class="fas fa-info-circle"></i>
      <p>{{ t('preventPage.empty') }}</p>
    </div>

    <div v-else class="prevention-content">
      <!-- 统计信息 -->
      <div class="stats-section">
        <div class="stat-card">
          <div class="stat-icon">
            <i class="fas fa-shield-alt"></i>
          </div>
          <div class="stat-info">
            <span class="stat-number">{{ preventionData && preventionData.categories ? preventionData.categories.length : 0 }}</span>
            <span class="stat-label">{{ t('preventPage.statCategories') }}</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon">
            <i class="fas fa-leaf"></i>
          </div>
          <div class="stat-info">
            <span class="stat-number">{{ totalMeasures }}</span>
            <span class="stat-label">{{ t('preventPage.statMeasures') }}</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon">
            <i class="fas fa-seedling"></i>
          </div>
          <div class="stat-info">
            <span class="stat-number">{{ uniqueDiseases }}</span>
            <span class="stat-label">{{ t('preventPage.statPests') }}</span>
          </div>
        </div>
      </div>
      
      <!-- 病害标签云 -->
      <div class="pest-tags" v-if="uniqueDiseases > 0">
        <div class="section-title">
          <i class="el-icon-collection-tag"></i> {{ t('preventPage.relatedPests') }}
          <span class="tag-count">{{ t('common.totalSpecies', { count: uniqueDiseases }) }}</span>
        </div>
        <div class="tags-container">
          <el-tag
            v-for="pest in getUniquePests()"
            :key="pest.id"
            type="success"
            effect="plain"
            class="pest-tag"
            @click="filterByPest(pest)"
          >
            <i class="el-icon-s-promotion"></i> {{ localizedField(pest, 'name') }}
          </el-tag>
        </div>
      </div>
      
      <!-- 搜索结果信息 -->
      <div v-if="searchQuery || selectedCategory" class="search-results-info">
        <el-tag type="info" size="large">
          <i class="el-icon-search"></i>
          {{ t('preventPage.searchResults', { query: searchQuery, count: totalItems }) }}
          <el-button v-if="searchQuery || selectedCategory" type="text" @click="resetSearch">
            {{ t('preventPage.clearFilters') }}
          </el-button>
        </el-tag>
      </div>

      <!-- 防治方法列表 -->
      <div class="accordion">
        <template v-if="preventionData && preventionData.categories && preventionData.categories.length > 0">
          <div v-for="(category, index) in preventionData.categories" :key="category.category" class="accordion-item">
            <button @click="toggleCategory(index)" class="accordion-header">
              <div class="header-content">
                <span class="header-title">{{ categoryLabel(category.category, category.displayName) }}</span>
                <span class="header-count">
                  {{ t('common.totalMeasures', { count: category.measures ? category.measures.length : 0 }) }}
                </span>
              </div>
              <span class="header-icon">{{ expandedCategories[index] ? '-' : '+' }}</span>
            </button>
            <div v-if="expandedCategories[index] && category.measures && category.measures.length > 0" class="accordion-content">
              <div class="measures-grid">
                <div v-for="(measure, mIndex) in category.measures" :key="mIndex" class="measure-item">
                  <div class="measure-header" @click="toggleMeasure(mIndex)">
                    <h4>{{ getMeasureText(measure) }}</h4>
                    <div class="measure-meta">
                      <el-tag v-if="measure.pest" type="success" size="small" class="pest-tag">
                        <i class="el-icon-s-promotion"></i> {{ localizedField(measure.pest, 'name') }}
                      </el-tag>
                      <i class="el-icon-arrow-down" :class="{ 'rotate-180': expandedMeasures[mIndex] }"></i>
                    </div>
                  </div>
                  <div v-if="expandedMeasures[mIndex]" class="measure-details">
                    <p>{{ localizedField(measure, 'measure') || measure.measure }}</p>
                    <div v-if="measure.pest" class="pest-info">
                      <el-divider content-position="left">{{ t('preventPage.relatedPestsDetail') }}</el-divider>
                      <p><strong>{{ t('preventPage.pestName') }}</strong>{{ localizedField(measure.pest, 'name') }}</p>
                      <!-- 这里可以添加更多病害信息，比如病害描述、图片等 -->
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>
        <div v-else class="no-data">
          {{ t('preventPage.noPrevention') }}
        </div>
      </div>
      
      <!-- 分页 -->
      <div class="pagination-container" v-if="totalItems > 0">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 30, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="totalItems"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
// 防治方法（按病害查"怎么治"）
// 路由：/preventions/:id —— id 是防治方法自身的 id，从病害详情页跳进来。
//
// 页面由三块组成：
//   1) 病害信息头（名称、作物、图片）
//   2) 防治措施列表（按 category 分：用药 / 农事操作 / 注意事项）
//   3) 相关的其它病害（便于横向比较）
//
// 改这个文件前值得知道的几件事：
//   · 数据来自 /api/prevention-data/，那个接口**默认每页 100 条且没有上限钳制**
//     （第 105 批审计记录的隐患），本页靠 page_size 一次取完；
//   · 措施文本是双语字段（measure / measure_en），取用规则见 useLocalized；
//   · english_identifier 是**数据集类别名**（Apple___Apple_scab 这种），
//     不要拿它做展示 —— 展示一律用 name / name_en。
import { ref, computed, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { Search } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import api from '@/api';
import { useI18n } from '@/i18n';  // 第 68 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 78 批：内容数据（病害名/防治措施）多语言

const { t } = useI18n();
const { localizedField } = useLocalized();

/**
 * 第 78 批：防治类别名
 * ------------------------------------------------------------------
 * 后端把分组键从中文类别名改成了语言无关的 code（AGRICULTURAL…），
 * 类别名走 i18n（与病害详情页共用 `prevent.*` 文案）。
 */
const CATEGORY_KEYS = {
  AGRICULTURAL: 'prevent.agricultural',
  CHEMICAL: 'prevent.chemical',
  ECOLOGICAL: 'prevent.ecological',
  PHYSICAL: 'prevent.physical',
  MONITORING: 'prevent.monitoring',
};

/** code → 界面语言下的类别名；认不出的 code 用后端给的名字兜底，不显示空白 */
const categoryLabel = (code, fallback) => {
  const key = CATEGORY_KEYS[String(code || '').toUpperCase()];
  return key ? t(key) : fallback || code || '';
};

// 响应式数据
const preventionData = ref([]);
const isLoading = ref(true);
const error = ref(null);
const activeIndex = ref(null);
const expandedMeasures = ref({});
const expandedCategories = ref({});

// 搜索和筛选
const searchQuery = ref('');
const selectedCategory = ref('');
const selectedPest = ref(null);
// 第 78 批：改成后端真实的类别 code。
// 原来这里写的是 'AG'/'CH'/'PH'/'BI'/'EC' 这类两字母缩写，而后端按
// `category == 'AGRICULTURAL'` 匹配 —— 也就是**筛选一直是坏的**（选中任何类别都查不到）。
const availableCategories = computed(() => [
  { value: 'AGRICULTURAL', label: t('prevent.agricultural') },
  { value: 'CHEMICAL', label: t('prevent.chemical') },
  { value: 'ECOLOGICAL', label: t('prevent.ecological') },
  { value: 'PHYSICAL', label: t('prevent.physical') },
  { value: 'MONITORING', label: t('prevent.monitoring') },
]);

// 分页
const currentPage = ref(1);
const pageSize = ref(10);
const totalItems = ref(0);

// 防抖搜索
let searchTimeout = null;

const totalMeasures = computed(() => {
  if (!preventionData.value || !preventionData.value.categories) return 0;
  return preventionData.value.categories.reduce((total, category) => {
    return total + (category.measures ? category.measures.length : 0);
  }, 0);
});

// 计算所有唯一的病害数量（考虑搜索过滤）
const uniqueDiseases = computed(() => {
  // 如果没有数据，返回0
  if (!preventionData.value || !preventionData.value.categories) return 0;
  
  // 如果有搜索条件或选中的病害，计算当前显示的唯一病害数量
  if (searchQuery.value || selectedPest.value) {
    const pestIds = new Set();
    preventionData.value.categories.forEach(category => {
      // 获取当前分类下显示的防治措施
      const displayedMeasures = getDisplayedMeasures(category);
      
      // 统计唯一病害ID
      displayedMeasures.forEach(measure => {
        if (measure.pest && measure.pest.id) {
          pestIds.add(measure.pest.id);
        }
      });
    });
    return pestIds.size;
  }
  
  // 如果没有搜索条件，直接返回后端计算的总数
  return preventionData.value.displayPestCount || 0;
});

// 获取当前分类下显示的防治措施（考虑搜索条件）
const getDisplayedMeasures = (category) => {
  if (!searchQuery.value && !selectedPest.value) {
    return category.measures;
  }
  
  return category.measures.filter(measure => {
    // 匹配搜索文本
    const matchesSearch = !searchQuery.value || 
      (measure.measure && measure.measure.toLowerCase().includes(searchQuery.value.toLowerCase()));
    
    // 匹配选中的病害
    const matchesPest = !selectedPest.value || 
      (measure.pest && measure.pest.id === selectedPest.value.id);
    
    return matchesSearch && matchesPest;
  });
};

// 重置选中的病害
const resetPestFilter = () => {
  selectedPest.value = null;
};

// 计算每个分类下的唯一病害数量
const getPestCountForCategory = (category) => {
  const pestIds = new Set();
  category.measures.forEach(measure => {
    if (measure.pest && measure.pest.id) {
      pestIds.add(measure.pest.id);
    }
  });
  return pestIds.size;
};

const router = useRouter();
const route = useRoute();

const goToHome = () => {
  router.push('/');
};

// 处理搜索
const handleSearch = () => {
  if (searchTimeout) clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    // 重置选中的病害当搜索条件改变时
    resetPestFilter();
    fetchPreventionData();
  }, 300);
};

// 重置搜索条件
const resetSearch = () => {
  searchQuery.value = '';
  selectedCategory.value = '';
  currentPage.value = 1;
  fetchPreventionData();
};

// 切换防治措施的展开/收起
const toggleMeasure = (index) => {
  expandedMeasures.value = {
    ...expandedMeasures.value,
    [index]: !expandedMeasures.value[index]
  };
};

// 切换分类的展开/收起
const toggleCategory = (index) => {
  expandedCategories.value = {
    ...expandedCategories.value,
    [index]: !expandedCategories.value[index]
  };
  
  // 确保当前分类的展开状态与activeIndex同步
  if (expandedCategories.value[index]) {
    activeIndex.value = index;
  } else if (activeIndex.value === index) {
    activeIndex.value = null;
  }
};

// 获取所有唯一的病害
const getUniquePests = () => {
  const pestMap = new Map();
  if (!preventionData.value || !preventionData.value.categories) return [];
  
  preventionData.value.categories.forEach(category => {
    if (category.measures && Array.isArray(category.measures)) {
      category.measures.forEach(measure => {
        if (measure.pest && measure.pest.id) {
          pestMap.set(measure.pest.id, measure.pest);
        }
      });
    }
  });
  return Array.from(pestMap.values());
};

// 根据病害筛选措施
const filterByPest = (pest) => {
  // 第 78 批：搜索框里显示当前语言下的病害名；后端同时按中文名与英文名匹配，
  // 所以英文界面下用英文名搜索也能命中（见 PreventionDataView 的 search 分支）。
  searchQuery.value = localizedField(pest, 'name') || pest.name;
  fetchPreventionData();
};

// 处理分页大小变化
const handleSizeChange = (val) => {
  pageSize.value = val;
  fetchPreventionData();
};

// 处理页码变化
const handleCurrentChange = (val) => {
  currentPage.value = val;
  fetchPreventionData();
};

const fetchPreventionData = async () => {
  console.log('开始获取防治数据...');
  isLoading.value = true;
  error.value = null;
  
  try {
    // 构建查询参数
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
    };
    
    // 添加搜索条件
    if (searchQuery.value) {
      params.search = searchQuery.value;
    }
    
    // 添加分类筛选
    if (selectedCategory.value) {
      params.category = selectedCategory.value;
    }
    
    console.log('请求参数:', params);
    
    // 发送请求
    const response = await api.get('preventions/', { params });
    console.log('收到响应:', response);
    
    if (response && response.data) {
      console.log('响应数据:', response.data);
      
      // 更新总条数
      if (response.data.total) {
        totalItems.value = response.data.total;
      }
      
      // 将响应数据转换为前端需要的格式
      const formattedData = formatPreventionData(response.data);
      // 保存完整的格式化数据，包括 categories 和 displayPestCount
      preventionData.value = formattedData;
      
      // 确保 categories 存在
      if (!preventionData.value.categories) {
        preventionData.value.categories = [];
      }
      
      // 打印接收到的数据格式
      console.log('防治分类数量:', preventionData.value.categories.length);
      console.log('涉及病害数量:', formattedData.displayPestCount);
      preventionData.value.categories.forEach((category, index) => {
        console.log(`分类 ${index + 1}: ${category.category}, 措施数量: ${category.measures ? category.measures.length : 0}, 涉及病害: ${category.displayPestCount}`);
      });
      
      // 初始化展开状态
      if (preventionData.value.categories && preventionData.value.categories.length > 0) {
        // 默认展开第一个分类
        expandedCategories.value = {
          ...expandedCategories.value,
          [0]: true
        };
        activeIndex.value = 0;
        console.log('默认展开第一个分类');
      } else {
        console.warn('未找到防治数据');
      }
    } else {
      console.error('响应数据格式不正确:', response);
      error.value = new Error(t('msg.dataFormatError'));
    }
  } catch (err) {
    console.error('获取防治数据失败:', err);
    if (err.response) {
      // 服务器返回了错误响应
      console.error('错误状态码:', err.response.status);
      console.error('错误响应数据:', err.response.data);
    } else if (err.request) {
      // 请求已发送但未收到响应
      console.error('未收到响应:', err.request);
    } else {
      // 请求设置出错
      console.error('请求设置错误:', err.message);
    }
    error.value = err;
  } finally {
    isLoading.value = false;
    console.log('获取防治数据完成');
  }
};

const retryLoad = () => {
  fetchPreventionData();
};

const toggleAccordion = (index) => {
  if (activeIndex.value === index) {
    activeIndex.value = null; // Close if already open
  } else {
    activeIndex.value = index; // Open the clicked item
  }
};

const getDiseaseName = (measure) => {
  // 如果 measure 是字符串，保持原有逻辑
  if (typeof measure === 'string') {
    const match = measure.match(/^([^：]+)：/);
    return match ? match[1] : '';
  }
  // 如果 measure 是对象，直接返回其 type 或 category 属性
  return measure.type || measure.category || '';
};

const getMeasureType = (measure) => {
  // 如果 measure 是字符串，保持原有逻辑
  if (typeof measure === 'string') {
    const match = measure.match(/：([^:]+):/);
    return match ? match[1] : '';
  }
  // 如果 measure 是对象，直接返回其 type 属性
  return measure.type || '';
};

const getMeasureText = (measure) => {
  // 如果 measure 是字符串，保持原有逻辑
  if (typeof measure === 'string') {
    const match = measure.match(/^[^：]+：[^:]+:\s*(.+)$/);
    return match ? match[1] : measure;
  }
  // 如果 measure 是对象，返回跟随语言的措施正文（第 78 批）
  return localizedField(measure, 'measure') || measure.text || measure.measure || '';
};

// 格式化防治数据
const formatPreventionData = (data) => {
  if (!data || !data.data) return { categories: [], pests: [] };
  
  // 首先收集所有病害信息
  const pestMap = new Map();
  const allMeasures = [];
  
  // 遍历所有分类和措施，收集病害信息
  for (const [categoryName, measures] of Object.entries(data.data)) {
    if (Array.isArray(measures)) {
      measures.forEach(item => {
        if (item.pest_id && item.pest_name) {
          // 使用病害ID作为键，确保唯一性
          pestMap.set(item.pest_id, item.pest_name);
        }
        // 收集所有措施，用于后续统计
        allMeasures.push({
          ...item,
          category: categoryName
        });
      });
    }
  }
  
  // 将病害信息转换为数组
  const pests = Array.from(pestMap.entries()).map(([id, name]) => ({
    id,
    name
  }));
  
  // 构建分类数据
  const categories = [];
  
  for (const [categoryCode, measures] of Object.entries(data.data)) {
    if (Array.isArray(measures) && measures.length > 0) {
      // 为每个措施添加病害信息
      const categoryMeasures = measures.map(item => ({
        ...item,
        type: categoryCode,
        text: item.measure || '',
        // 确保 pest 对象包含必要的字段（第 78 批：带上英文名）
        pest: item.pest_id ? {
          id: item.pest_id,
          name: item.pest_name || '未知病害',
          name_en: item.pest_name_en || ''
        } : null
      }));
      
      // 计算该分类下的唯一病害数量
      const pestIds = measures
        .filter(m => m.pest_id)
        .map(m => m.pest_id);
      const uniquePestCount = new Set(pestIds).size;
      
      categories.push({
        category: categoryCode,
        // 后端下发的类别名（中/英），i18n 认不出 code 时兜底
        displayName: measures[0]?.category_display || '',
        displayNameEn: measures[0]?.category_display_en || '',
        measures: categoryMeasures,
        pestCount: uniquePestCount,
        // 添加一个辅助属性，用于前端显示
        displayPestCount: uniquePestCount
      });
    }
  }
  
  // 按分类下的病害数量排序，病害多的排在前面
  categories.sort((a, b) => b.pestCount - a.pestCount);
  
  // 计算总病害数量（去重）
  const totalUniquePests = pestMap.size;
  
  const result = {
    categories,
    pests,
    totalPests: totalUniquePests,
    totalMeasures: allMeasures.length,
    // 添加一个辅助属性，用于前端显示
    displayPestCount: totalUniquePests
  };
  
  console.log('格式化后的防治数据:', result);
  return result;
};

onMounted(fetchPreventionData);
</script>

<style scoped>
/* 病害标签样式 */
.pest-tags {
  margin: 25px 0;
  padding: 15px;
  background-color: #f8f9fa;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
}

.section-title {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  color: #606266;
  font-size: 15px;
  font-weight: 500;
}

.section-title i {
  margin-right: 8px;
  color: #67c23a;
}

.tag-count {
  margin-left: 10px;
  color: #909399;
  font-size: 13px;
}

.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.pest-tag {
  margin: 0;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.3s;
  border-radius: 16px;
  padding: 0 12px;
  height: 32px;
  line-height: 30px;
  font-size: 13px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.pest-tag:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px 0 rgba(103, 194, 58, 0.2);
}

.pest-tag i {
  margin-right: 4px;
  font-size: 12px;
}

.measure-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.measure-pest-info {
  margin-top: 15px;
  padding: 10px;
  background-color: #f8f9fa;
  border-radius: 4px;
  border-left: 3px solid #67c23a;
}

.measure-pest-info p {
  margin: 5px 0;
  color: #606266;
}

.measure-pest-info strong {
  color: #303133;
}
/* 顶部操作栏 */
.header-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 0 20px;
}

.search-filter {
  display: flex;
  gap: 10px;
  align-items: center;
}

/* 搜索结果信息 */
.search-results-info {
  margin: 15px 0;
  padding: 0 20px;
}

.search-results-info .el-tag {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.search-results-info .el-button {
  margin-left: 10px;
  padding: 0 5px;
}

/* 分页 */
.pagination-container {
  margin-top: 20px;
  padding: 20px 0;
  display: flex;
  justify-content: center;
  background-color: #fff;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
}

/* 响应式调整 */
@media (max-width: 768px) {
  .header-actions {
    flex-direction: column;
    align-items: stretch;
    gap: 15px;
  }
  
  .search-filter {
    flex-direction: column;
  }
  
  .search-filter .el-input,
  .search-filter .el-select {
    width: 100% !important;
    margin-right: 0 !important;
    margin-bottom: 10px;
  }
}

.back-home {
  margin: 20px 0 0 20px;
}

.back-home .el-button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--el-color-primary);
  font-size: 14px;
  transition: color 0.3s;
}

.back-home .el-button:hover {
  color: var(--el-color-primary-light-3);
}

.back-home .el-icon-arrow-left {
  font-size: 12px;
}
.prevention-page {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.page-banner {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 12px;
  padding: 2.5rem;
  text-align: center;
  margin-bottom: 3rem;
  box-shadow: 0 8px 25px rgba(102, 126, 234, 0.2);
}

.page-banner h1 {
  font-size: 2.5rem;
  font-weight: 700;
  margin-bottom: 0.75rem;
}

.page-banner p {
  font-size: 1.1rem;
  opacity: 0.9;
  line-height: 1.6;
  max-width: 800px;
  margin: 0 auto;
}

.loading-state, .error-state, .empty-state {
  text-align: center;
  padding: 5rem;
  color: #6c757d;
  font-size: 1.25rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.error-state {
  color: #dc3545;
}

.retry-btn {
  background: #667eea;
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: background 0.3s;
}

.retry-btn:hover {
  background: #5a6fd8;
}

.prevention-content {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.stats-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: white;
  padding: 1.5rem;
  border-radius: 12px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
  display: flex;
  align-items: center;
  gap: 1rem;
  transition: transform 0.3s ease;
}

.stat-card:hover {
  transform: translateY(-5px);
}

.stat-icon {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-number {
  font-size: 1.8rem;
  font-weight: 700;
  color: #2c3e50;
}

.stat-label {
  font-size: 0.9rem;
  color: #7f8c8d;
}

.accordion {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.08);
}

.accordion-item {
  border-bottom: 1px solid #e9ecef;
}

.accordion-item:last-child {
  border-bottom: none;
}

.accordion-header {
  width: 100%;
  padding: 1.5rem 2rem;
  background-color: #fff;
  border: none;
  text-align: left;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  transition: all 0.3s ease;
}

.accordion-header:hover {
  background-color: #f8f9fa;
}

.header-content {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.25rem;
}

.header-title {
  font-size: 1.2rem;
  font-weight: 600;
  color: #2a7f53;
}

.header-count {
  font-size: 0.85rem;
  color: #6c757d;
  background: #e9ecef;
  padding: 0.25rem 0.5rem;
  border-radius: 12px;
}

.header-icon {
  font-size: 1.5rem;
  font-weight: 300;
  color: #6c757d;
  transition: transform 0.3s ease;
}

.accordion-header:hover .header-icon {
  transform: scale(1.1);
}

.accordion-content {
  padding: 1.5rem 2rem;
  background-color: #fdfdff;
  border-top: 1px solid #e9ecef;
}

.measures-grid {
  display: grid;
  gap: 1rem;
}

.measure-item {
  background: white;
  border-radius: 8px;
  padding: 1rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  transition: transform 0.3s ease;
}

.measure-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.measure-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.disease-name {
  font-weight: 600;
  color: #e74c3c;
  font-size: 1rem;
}

.measure-type {
  background: #667eea;
  color: white;
  padding: 0.25rem 0.5rem;
  border-radius: 12px;
  font-size: 0.8rem;
  font-weight: 500;
}

.measure-text {
  color: #495057;
  line-height: 1.6;
  margin: 0;
  font-size: 0.95rem;
}

@media (max-width: 768px) {
  .prevention-page {
    padding: 1rem;
  }
  
  .page-banner {
    padding: 2rem;
  }
  
  .page-banner h1 {
    font-size: 2rem;
  }
  
  .stats-section {
    grid-template-columns: 1fr;
  }
  
  .measure-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }
}

/* ================= 现代化覆写（设计变量见 assets/theme.css） ================= */
.prevention-page {
  width: 100%;
  max-width: 1320px;
  margin: 0 auto;
  padding: 8px 24px 48px;
  box-sizing: border-box;
}

/* 顶部横幅 */
.page-banner {
  position: relative;
  overflow: hidden;
  padding: 48px 34px;
  margin-bottom: 24px;
  text-align: center;
  border: none;
  border-radius: var(--radius-xl);
  background: var(--gradient-hero);
  box-shadow: var(--shadow-lg);
}

.page-banner h1,
.page-banner h2 {
  margin: 0 0 12px;
  font-size: 30px;
  font-weight: 800;
  letter-spacing: 1px;
  color: #fff;
}

.page-banner p {
  max-width: 720px;
  margin: 0 auto;
  font-size: 14.5px;
  line-height: 1.9;
  color: rgba(255, 255, 255, 0.85);
}

/* 统计 */
.stats-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 18px;
  margin-bottom: 24px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-md);
}

.stat-icon {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: 15px;
  background: var(--brand-50);
  color: var(--brand-600);
  font-size: 20px;
}

.stat-number {
  font-size: 24px;
  font-weight: 800;
  color: var(--ink-900);
}

.stat-label {
  font-size: 12.5px;
  color: var(--ink-500);
}

/* 搜索与标签 */
.search-filter {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  padding: 16px 20px;
  margin-bottom: 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-xs);
}

.search-results-info {
  font-size: 13.5px;
  color: var(--ink-500);
}

.tags-container,
.pest-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pest-tag {
  padding: 5px 14px;
  border-radius: var(--radius-pill);
  background: var(--brand-50);
  color: var(--brand-700);
  font-size: 12.5px;
  font-weight: 600;
}

.tag-count {
  font-size: 12px;
  color: var(--ink-400);
}

/* 内容区 */
.prevention-content {
  display: grid;
  gap: 18px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
  font-size: 17px;
  font-weight: 700;
  color: var(--brand-700);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.back-home,
.retry-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 20px;
  border-radius: var(--radius-pill);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--dur) var(--ease);
}

.back-home {
  border: 1px solid var(--border-strong);
  background: var(--surface);
  color: var(--ink-600);
}

.back-home:hover {
  border-color: var(--brand-400);
  background: var(--brand-50);
  color: var(--brand-700);
}

.retry-btn {
  border: none;
  background: var(--gradient-brand);
  color: #fff;
  box-shadow: 0 8px 18px rgba(31, 99, 67, 0.2);
}

.loading-state,
.empty-state,
.error-state {
  padding: 56px 24px;
  text-align: center;
  color: var(--ink-400);
  font-size: 15px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}

.loading-spinner {
  width: 38px;
  height: 38px;
  margin: 0 auto 14px;
  border: 4px solid var(--ink-100);
  border-top-color: var(--brand-600);
  border-radius: 50%;
  animation: prevent-spin 0.9s linear infinite;
}

@keyframes prevent-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 768px) {
  .prevention-page {
    padding: 0 16px 32px;
  }

  .page-banner {
    padding: 30px 20px;
  }

  .page-banner h1 {
    font-size: 22px;
  }
}
</style> 