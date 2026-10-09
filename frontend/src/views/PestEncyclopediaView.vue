<template>
  <div class="encyclopedia-page">
    <div class="page-banner">
      <h1>{{ t('wiki.title') }}</h1>
      <p>{{ t('wiki.subtitle') }}</p>
    </div>

    <!--
      第 122 批：这里的**管理员工具条已移走**。
      ------------------------------------------------------------------
      改前：管理员登录后本页顶部会出现「管理员模式：可直接新增、编辑、删除…」
      加两个按钮，卡片上还有编辑/删除 —— 但这一页是**农户读资料**的地方，
      农户打开却先看到"管理员模式"几个字。
      现在维护入口统一在管理后台的「病害百科维护」（`/admin/pests`，侧栏进入），
      本页对所有人都是纯阅读页。
    -->

    <!-- 第 50 批：离线模式提示（显示的是本地缓存资料，图片可能缺失） -->
    <div v-if="offlineMode" class="offline-note">
      <i class="fas fa-plug-circle-xmark"></i>
      {{ t('wiki.offlineNote') }}{{ offlineSavedAt ? `（${new Date(offlineSavedAt).toLocaleString()}）` : '' }}{{ t('wiki.offlineNoteTail') }}
    </div>

    <div class="filter-controls">
      <button
        v-for="crop in cropFilters"
        :key="crop.key"
        @click="selectCrop(crop.key)"
        :class="{ active: selectedCrop === crop.key }"
        class="filter-button"
      >
        {{ crop.name }}
      </button>
    </div>

    <!-- 搜索框 -->
    <div class="search-bar">
      <input v-model="searchKeyword" type="text" :placeholder="t('wiki.searchPlaceholder')" />
      <button @click="searchPests"><i class="fas fa-search"></i> {{ t('wiki.search') }}</button>
    </div>

    <!--
      第 96 批：抓取没抓全时**明说**
      ------------------------------------------------------------------
      改前这里什么都不显示：超过 120 条的部分直接不出现，用户会以为
      "百科里就这么多病害"。宁可显示一条黄色提示，也不要让人误判数据完整性。
    -->
    <el-alert
      v-if="fetchIncomplete"
      type="warning"
      show-icon
      :closable="false"
      class="incomplete-alert"
      :title="t('wiki.incompleteTitle')"
      :description="t('wiki.incompleteDesc', { count: pests.length })"
    />

    <div class="encyclopedia-main">
      <div class="encyclopedia-content">
        <div v-if="isLoading" class="loading-state">
          <p>{{ t('wiki.loading') }}</p>
        </div>
        <div v-else-if="filteredPests.length === 0" class="empty-state">
          <p>{{ t('wiki.empty') }}</p>
        </div>
        <div v-else class="pest-grid">
          <div v-for="pest in filteredPests" :key="pest.id" class="pest-card">
            <div class="card-image-container">
              <img :src="getFullImageUrl(pest.image)" :alt="localizedField(pest, 'name')" class="pest-image">
            </div>
            <div class="card-content">
              <h3>{{ localizedField(pest, 'name') }}</h3>
              <p class="description">{{ localizedField(pest, 'symptoms') }}</p>
              <div class="card-actions">
                <router-link :to="{ name: 'PestDetail', params: { english_identifier: pest.english_identifier } }" class="details-button">
                  {{ t('wiki.details') }} &gt;
                </router-link>
                <!-- 第 122 批：卡片上的编辑/删除按钮已移走（见页面顶部的说明） -->
              </div>
            </div>
          </div>
        </div>

        <!-- 分页控件 -->
        <div class="pagination-container" v-if="totalPages > 1">
          <div class="pagination">
            <button
              class="pagination-btn"
              :disabled="currentPage === 1"
              @click="goToPrevPage"
            >
              &laquo; {{ t('wiki.prevPage') }}
            </button>

            <div class="page-numbers">
              <!-- 第一页 -->
              <button
                v-if="currentPage > 3"
                class="page-number"
                :class="{ active: currentPage === 1 }"
                @click="goToPage(1)"
              >
                1
              </button>

              <!-- 省略号 -->
              <span v-if="currentPage > 3" class="ellipsis">...</span>

              <!-- 当前页前后的页码 -->
              <button
                v-for="page in totalPages"
                :key="page"
                v-show="page >= currentPage - 1 && page <= currentPage + 1 && page > 0 && page <= totalPages"
                class="page-number"
                :class="{ active: currentPage === page }"
                @click="goToPage(page)"
              >
                {{ page }}
              </button>

              <!-- 省略号 -->
              <span v-if="currentPage < totalPages - 2" class="ellipsis">...</span>

              <!-- 最后一页 -->
              <button
                v-if="currentPage < totalPages - 2"
                class="page-number"
                :class="{ active: currentPage === totalPages }"
                @click="goToPage(totalPages)"
              >
                {{ totalPages }}
              </button>
            </div>

            <button
              class="pagination-btn"
              :disabled="currentPage === totalPages"
              @click="goToNextPage"
            >
              {{ t('wiki.nextPage') }} &raquo;
            </button>
          </div>

          <div class="pagination-info">
            Page {{ currentPage }}/{{ totalPages }} · {{ allFilteredPests.length }} entries
          </div>
        </div>
      </div>
      <!-- 右侧热门病害推荐区块 -->
      <div class="encyclopedia-sidebar">
        <div class="hot-pests-section">
          <h3>{{ t('wiki.topPests') }}</h3>
          <ul>
            <li v-for="(hot, idx) in hotPests" :key="idx" @click="goToPestDetail(hot)" class="hot-pest-item">
              <span class="hot-rank">{{ idx + 1 }}</span> {{ hot.label }}
            </li>
          </ul>
        </div>
        <!-- 第 31 批：这里原本是一个**空的** .quick-links-section（只有 CSS、没有内容），
             侧栏下半段因此是一块空白。按原有样式把快捷入口补上。 -->
        <div class="quick-links-section">
          <h3>{{ t('wiki.quickLinks') }}</h3>
          <ul>
            <li><RouterLink to="/detect"><i class="fas fa-camera"></i> {{ t('wiki.quickDetect') }}</RouterLink></li>
            <li><RouterLink to="/forum"><i class="fas fa-comments"></i> {{ t('wiki.quickForum') }}</RouterLink></li>
            <li><RouterLink to="/news"><i class="fas fa-newspaper"></i> {{ t('wiki.quickNews') }}</RouterLink></li>
            <li><RouterLink to="/history"><i class="fas fa-clock-rotate-left"></i> {{ t('wiki.quickHistory') }}</RouterLink></li>
          </ul>
        </div>
      </div>
    </div>

    <!-- 第 31 批：列表下面原本直接就是页脚，补一块"看图识病/防治"的实用说明 -->
    <!-- 第 59 批：卡片内容改由脚本 computed 生成（原来内联在模板里，无法跟着语言切换） -->
    <PageExtras
      icon="fas fa-book-open-reader"
      :title="t('wiki.notSureTitle')"
      :subtitle="t('wiki.notSureSubtitle')"
      :items="notSureItems"
    />

    <!-- 第 122 批：新增/编辑/批量导入三个弹窗已随管理功能一起搬到
         `/admin/pests`（管理后台「病害百科维护」），本页不再挂载它们。 -->
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useToast } from 'vue-toast-notification';
import 'vue-toast-notification/dist/theme-sugar.css';
import apiClient from '@/api';
// 第 31 批：页面底部"看图识病"补充信息区
import PageExtras from '@/components/PageExtras.vue';
// 第 122 批：写接口（deletePest / formatPestError）已随管理功能搬到 AdminPestsView，
// 本页只保留"读"用的东西
import { toAbsoluteMediaUrl } from '@/api/http';
// 第 122 批：作物筛选按钮的来源（别用 pest-types/，那个返回的是病害名称）
import { fetchCalendarCrops } from '@/api/calendar';
// 第 50 批：离线资料包（断网时百科走本地缓存）
import { refreshOfflinePack } from '@/api/offline';
import { readWikiPack } from '@/utils/offlineStorage';
import { useI18n } from '@/i18n';  // 第 59 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 69 批：内容数据多语言

const { t } = useI18n();

// 第 69 批：内容数据（病害名/作物名）按当前语言取值
const { localizedField } = useLocalized();

// 第 122 批：本页的"管理员编辑能力"（canManage / 两个弹窗 / 删除）已整体搬到
// 管理后台的「病害百科维护」`/admin/pests`（views/AdminPestsView.vue）。
// 本页现在对所有人都是**纯阅读页** —— 农户打开不会再看到"管理员模式"。

const pests = ref([]);
const isLoading = ref(true);
// 第 50 批：是否正在用本地缓存的离线资料
const offlineMode = ref(false);
const offlineSavedAt = ref(null);
const route = useRoute();
const router = useRouter();
const selectedCrop = ref('all');
const cropTypes = ref([]); // 动态类型
const searchKeyword = ref('');
/**
 * 热门病害 Top 10（第 59 批起在侧栏展示）
 * ------------------------------------------------------------------
 * 第 77 批：原来这里是一个**写死的中文名数组**，英文界面下右侧整列都是中文，
 * 而且点击时靠"中文名 == 病害名"去找详情，语言一变就找不到。
 * 现在只保留一份语言无关的清单（中文名用于在已加载的百科数据里定位，
 * 英文名仅作离线/未收录时的兜底），显示名走 localizedField。
 */
const HOT_PEST_ENTRIES = [
  { zh: '苹果黑星病', en: 'Apple scab' },
  { zh: '番茄晚疫病', en: 'Late blight' },
  { zh: '苹果黑腐病', en: 'Black rot' },
  { zh: '葡萄黑腐病', en: 'Black rot' },
  { zh: '柑橘黄龙病', en: 'Haunglongbing (Citrus greening)' },
  { zh: '马铃薯早疫病', en: 'Early blight' },
  { zh: '草莓叶焦病', en: 'Leaf scorch' },
  { zh: '番茄早疫病', en: 'Early blight' },
  { zh: '葡萄叶枯病', en: 'Leaf blight (Isariopsis Leaf Spot)' },
  { zh: '玉米普通锈病', en: 'Common rust' },
];

// 分页相关状态
const currentPage = ref(1);
const pageSize = ref(6); // 每页显示6个病害（2行×3列）
const totalPages = computed(() => Math.ceil(allFilteredPests.value.length / pageSize.value) || 1);

// 第 96 批：抓取是否**没抓全**（触到安全上限）。
// 单独用 ref 而不是靠"条数看起来不对"来判断 —— 页面上必须明说，
// 否则用户会以为"百科里就这么多病害"。
const fetchIncomplete = ref(false);

const searchPests = () => {
  // 搜索时重置页码
  currentPage.value = 1;
};

// 作物类型映射，支持中英文双向映射
const cropTypeMap = {
  // 英文小写到中文映射
  'apple': '苹果',
  'tomato': '番茄',
   'grape': '葡萄',
   'corn': '玉米',
   'potato': '马铃薯',
  'cherry': '樱桃',
  'peach': '桃',
  'strawberry': '草莓',
  'squash': '南瓜',
};

// 创建中文到英文的反向映射
const reverseCropTypeMap = Object.entries(cropTypeMap).reduce((acc, [en, zh]) => {
  acc[zh] = en;
  return acc;
}, {});

// 获取所有中文作物类型
const chineseCropTypes = Object.values(cropTypeMap);

// 预设的作物类型顺序
const presetCropOrder = [...chineseCropTypes];

// 获取所有可能的作物类型（中文）
const getAllCropTypes = () => {
  try {
    // 确保 apiCrops 是数组
    const apiCrops = Array.isArray(cropTypes.value) ? cropTypes.value : [];
    // 合并并去重
    const allCrops = [...new Set([...apiCrops, ...chineseCropTypes])];
    return allCrops;
  } catch (error) {
    console.error('获取作物类型时出错:', error);
    return [...chineseCropTypes]; // 返回预设的作物类型
  }
};

const cropFilters = computed(() => {
  // 获取所有可用的作物类型
  const allCrops = getAllCropTypes();

  // 中文作物名 → 英文作物名（第 69 批：从已加载的病害数据里取 crop_type_en）
  const cropEnMap = computed(() => {
    const map = {};
    for (const pest of pests.value) {
      if (pest?.crop_type && pest?.crop_type_en) map[pest.crop_type] = pest.crop_type_en;
    }
    return map;
  });

  // 创建筛选器选项（第 69 批：英文界面用作物英文名，来自后端 crop_type_en）
  const cropOptions = allCrops.map(crop => {
    // 如果是中文作物名，尝试获取对应的英文key，否则直接使用中文
    const key = reverseCropTypeMap[crop] || crop;
    return {
      key: key,
      name: localizedField({ crop_type: crop, crop_type_en: cropEnMap.value[crop] }, 'crop_type'),
    };
  });

  // 添加'全部'选项
  return [{ key: 'all', name: t('wiki.allCrops') }, ...cropOptions];
});

// 第 59 批：底部"看图识病"卡片（原来内联在模板里，无法随语言切换）
const notSureItems = computed(() => [
  {
    icon: 'fas fa-camera',
    title: t('wiki.notSure1'),
    text: t('wiki.notSure1Desc'),
    more: t('wiki.notSure1Link'),
    to: '/detect',
  },
  { icon: 'fas fa-magnifying-glass', title: t('wiki.notSure2'), text: t('wiki.notSure2Desc') },
  { icon: 'fas fa-shield-halved', title: t('wiki.notSure3'), text: t('wiki.notSure3Desc') },
  {
    icon: 'fas fa-comments',
    title: t('wiki.notSure4'),
    text: t('wiki.notSure4Desc'),
    more: t('wiki.notSure4Link'),
    to: '/forum',
  },
]);

// 本地生成的占位图（原来是 https://via.placeholder.com，离线或断网时无法显示）
// 第 84 批：图内"暂无图片"原来硬编码中文 —— 英文界面下图片内容仍是中文，改为随语言切换。
const placeholderImage = computed(() =>
  'data:image/svg+xml;charset=utf-8,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">
      <rect width="400" height="300" fill="#f2f8f4"/>
      <path d="M200 78c-34 0-60 26-60 60 0 25 15 47 38 56-4-21 4-38 21-51-13 21-13 38-4 55h9c9-21 7-42-4-59 17 10 27 30 25 51 21-10 34-32 34-55 0-34-26-60-59-60z" fill="#bcd8ca"/>
      <text x="200" y="232" font-family="Microsoft YaHei,PingFang SC,sans-serif" font-size="16" fill="#8aa79a" text-anchor="middle">${t('news.noImage')}</text>
    </svg>`,
  ),
);

const getFullImageUrl = (imagePath) => {
  // 无图时使用内置占位图；有图时交给统一的地址构造器处理
  if (!imagePath) return placeholderImage.value;
  return toAbsoluteMediaUrl(imagePath) || placeholderImage.value;
};

const fetchPests = async () => {
    isLoading.value = true;
    fetchIncomplete.value = false;
    try {
        let allPests = [];
        let nextUrl = 'pests/';
        let page = 1;

        // ==================================================================
        // 循环取完所有分页数据（第 96 批修复：原来会**静默丢数据**）
        // ------------------------------------------------------------------
        // 改前：默认请求 `pests/`（后端 page_size=6），并在 `page >= 20` 时直接 break。
        // 也就是**最多只显示 120 条**，超出部分既不报错也不提示 —— 管理员在后台
        // 新增到第 121 条病害后，百科页面上它永远不会出现，而且没有任何迹象。
        //
        // 现在两处都改：
        //   1. 每次请求带 `page_size=100`（后端 CustomPagination 的 max_page_size=100），
        //      请求数从 N/6 降到 N/100；
        //   2. 安全上限提高（防后端 `next` 不前进导致死循环），并且**一旦真的触到上限
        //      就把 `fetchIncomplete` 置真**，页面上出提示条 —— 宁可明说"没取全"，
        //      也不要让人以为看到了全部。
        // ==================================================================
        const PAGE_SIZE = 100;     // 后端上限
        // 安全阀：默认 200 × 100 = 20000 条，防后端 `next` 不前进导致死循环。
        // 允许用环境变量调小 —— **这一条是为了能被验证**：正常数据量下永远不会触到
        // 上限，"触到上限时提示条真的会出现"这件事就没法在浏览器里证明。
        // 有了它，验证脚本可以把上限压到 1 页，确认提示条确实显示。
        const MAX_PAGES = Math.max(1, Number(import.meta.env.VITE_WIKI_MAX_PAGES) || 200);
        while (nextUrl) {
            const response = await apiClient.get(nextUrl, {
                params: page === 1 ? { page_size: PAGE_SIZE } : undefined,
            });

            let pagePests = [];

            // 处理分页格式的响应
            if (response.data && Array.isArray(response.data.results)) {
                pagePests = response.data.results;
                // 检查是否有下一页
                nextUrl = response.data.next;
            }
            // 直接返回数组的情况（非分页）
            else if (Array.isArray(response.data)) {
                pagePests = response.data;
                nextUrl = null; // 没有分页，获取一次即可
            }
            // 其他格式
            else if (response.data && typeof response.data === 'object') {
                pagePests = Object.values(response.data);
                nextUrl = null; // 没有分页，获取一次即可
            } else {
                console.warn('无法识别的数据格式:', response.data);
                nextUrl = null;
            }

            if (pagePests && pagePests.length > 0) {
                allPests = [...allPests, ...pagePests];
            }

            if (!nextUrl) break;

            // 触到安全上限：说明还有下一页但不再继续取 —— 明确告知，不静默截断
            if (page >= MAX_PAGES) {
                fetchIncomplete.value = true;
                console.warn(
                    `[wiki] 已达单次抓取上限（${MAX_PAGES} 页 × ${PAGE_SIZE} 条），`
                    + `当前 ${allPests.length} 条，可能还有更多未显示`,
                );
                break;
            }

            page++;
        }

        // 更新数据
        pests.value = allPests;

        if (allPests.length === 0) {
            console.warn('没有获取到病害数据');
        }
    } catch (error) {
        console.error('Failed to fetch pest data:', error);
        // 第 50 批：网络失败时用本地离线资料包兜底，断网也能查百科
        const cached = readWikiPack();
        if (cached?.items?.length) {
            pests.value = cached.items;
            offlineMode.value = true;
            offlineSavedAt.value = cached.savedAt || null;
            console.warn(`[offline] 使用本地缓存的 ${cached.items.length} 条病害资料`);
        } else {
            pests.value = [];
        }
    } finally {
        isLoading.value = false;
    }
};

/**
 * 第 50 批：联网时把百科资料包缓存到本地（供断网查阅）
 * 内容没变时后端只回 `unchanged`，几乎不耗流量。
 */
const refreshOfflineCache = async () => {
    try {
        const pack = await refreshOfflinePack();
        if (pack?.items?.length) {
            console.log(`[offline] 资料包已就绪：${pack.count} 条（${pack.fromCache ? '来自缓存' : '已更新'}）`);
        }
    } catch (error) {
        console.warn('[offline] 资料包更新失败（不影响页面）:', error?.message || error);
    }
};

/**
 * 作物筛选按钮的来源
 * ----------------------------------------------------------------------------
 * ⚠️ 第 122 批修：这里原来打的是 `pest-types/`，而**那个接口返回的是病害名称**
 * （`PestInfo.name`，38 条，还包含"健康大豆"这类占位条目）。于是**登录用户**的
 * 筛选条里会多出一堆「健康大豆 / 南瓜白粉病」这样的按钮；
 * 匿名用户因为该接口要登录（401）而走下面的兜底分支，反而看不出问题 ——
 * 这就是它一直没被发现的原因。
 * 正确的来源是 `/api/calendar/crops/`（取自百科里真实存在的作物）。
 */
const fetchCropTypes = async () => {
  try {
    const data = await fetchCalendarCrops();
    const crops = Array.isArray(data?.crops) ? data.crops : [];
    cropTypes.value = crops.length ? crops : [...presetCropOrder];
  } catch (error) {
    console.error('Failed to fetch crop types:', error);
    // 接口不可用（未登录 / 断网）时用预设作物兜底，筛选条不至于空掉
    cropTypes.value = [...presetCropOrder];
  }
};

// 第 122 批：管理相关的函数（adminCropTypeOptions / openCreateDialog / openEditDialog /
// handlePestSaved / importDialogVisible / handleImported / handleDeletePest）
// 已随管理功能一起搬到 `views/AdminPestsView.vue`。

const toast = useToast();
const selectCrop = async (cropKey) => {
  try {
    console.log('Selected crop key:', cropKey);

    // 更新选中状态
    selectedCrop.value = cropKey;
    currentPage.value = 1;

    // 更新URL，保持与首页跳转一致
    const query = { ...route.query };

    if (cropKey === 'all') {
      // 如果选择'全部'，则移除crop参数
      delete query.crop;
    } else {
      // 否则设置crop参数
      query.crop = cropKey;
    }

    // 使用replace而不是push，避免浏览器历史记录过多
    await router.replace({
      path: '/pests',
      query: query
    });

    // 强制重新加载数据
    await fetchPests();

    // 滚动到顶部
    window.scrollTo(0, 0);
  } catch (error) {
    console.error('Error selecting crop:', error);
    toast.error(t('forum.switchCropFailed'));
  }
};

// 所有过滤后的病害（未分页）
const allFilteredPests = computed(() => {
  console.log('=== allFilteredPests 开始计算 ===');
  console.log('当前选中的作物:', selectedCrop.value);
  console.log('当前搜索关键词:', searchKeyword.value);
  console.log('当前 pests 数据:', JSON.parse(JSON.stringify(pests.value)));

  // 过滤掉健康植物条目
  let diseasePests = pests.value.filter(pest => {
    if (!pest || !pest.name) return false;
    return !pest.name.startsWith('健康');
  });

  console.log('过滤后的病害数据:', diseasePests);
  console.log('过滤健康状态后数量:', diseasePests.length);

  // 处理搜索关键词
  const keyword = searchKeyword.value?.trim().toLowerCase();
  if (keyword) {
    diseasePests = diseasePests.filter(pest => {
      // 在病害名称、症状、防治方法中搜索（第 72 批：中英文字段都参与，
      // 否则英文界面下用英文关键字搜不到东西）
      const haystack = [
        pest.name, pest.name_en,
        pest.symptoms, pest.symptoms_en,
        pest.crop_type, pest.crop_type_en,
        pest.prevention, pest.prevention_en,
      ];
      return haystack.some((value) => value && String(value).toLowerCase().includes(keyword));
    });
    console.log('搜索后数量:', diseasePests.length);
  }

  // 如果没有选择特定作物，返回所有病害
  if (!selectedCrop.value || selectedCrop.value === 'all') {
    console.log('返回所有非健康病害，数量:', diseasePests.length);
    return diseasePests;
  }

  console.log('按作物类型筛选:', selectedCrop.value, '原始值:', selectedCrop.value);

  // 获取当前选中的作物类型（支持中英文）
  let targetCrop = selectedCrop.value;

  // 如果是英文且存在于映射中，获取中文名
  const chineseCropName = cropTypeMap[targetCrop.toLowerCase()];

  // 如果是中文且存在于反向映射中，获取英文名
  const englishCropName = reverseCropTypeMap[targetCrop];

  // 根据选中的作物类型进行筛选（精确匹配）
  const filteredByCrop = diseasePests.filter(pest => {
    if (!pest.crop_type) return false;

    const cropTypeLower = pest.crop_type.toLowerCase();

    // 检查是否精确匹配
    const matchChinese = chineseCropName && cropTypeLower === chineseCropName.toLowerCase();
    const matchEnglish = englishCropName && cropTypeLower === englishCropName.toLowerCase();
    const matchDirect = cropTypeLower === targetCrop.toLowerCase();

    // 如果是中文作物名，还要检查是否在作物类型列表中
    const isExactMatch = matchChinese || matchEnglish || matchDirect;

    // 如果是中文作物名，还要检查是否在作物类型列表中
    const isInCropList = cropTypeLower.split(/[、,，]/).some(crop => {
      const trimmedCrop = crop.trim().toLowerCase();
      return trimmedCrop === (chineseCropName?.toLowerCase() || '') ||
             trimmedCrop === (englishCropName?.toLowerCase() || '') ||
             trimmedCrop === targetCrop.toLowerCase();
    });

    const isMatch = isExactMatch || isInCropList;

    console.log(`病害: ${pest.name}, 作物类型: ${pest.crop_type}, 是否匹配: ${isMatch}`);

    return isMatch;
  });

  console.log('按作物类型筛选后数量:', filteredByCrop.length);
  return filteredByCrop;
});

// 当前页显示的病害
const filteredPests = computed(() => {
  console.log('计算 filteredPests, 总数量:', allFilteredPests.value.length);
  const start = (currentPage.value - 1) * pageSize.value;
  const end = start + pageSize.value;
  const result = allFilteredPests.value.slice(start, end);
  console.log('分页结果:', result);
  return result;
});

// 监听过滤后的数据变化，确保当前页码有效
watch(allFilteredPests, (newVal) => {
  // 如果当前页码超出范围，重置为第一页
  if (currentPage.value > Math.ceil(newVal.length / pageSize.value)) {
    currentPage.value = 1;
  }
}, { immediate: true });

// 总页数计算已经在上面定义为计算属性

// 页码导航方法
const goToPage = (page) => {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page;
    // 滚动到页面顶部
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
};

const goToPrevPage = () => {
  if (currentPage.value > 1) {
    goToPage(currentPage.value - 1);
}
};

const goToNextPage = () => {
if (currentPage.value < totalPages.value) {
    currentPage.value++;
}
};

// 跳转到病害详情页
// 第 77 批：入参从"中文病害名"改成热门条目对象 —— 榜单在英文界面显示英文名，
// 再按显示名反查就找不到了；这里用已加载的百科数据（含离线缓存）定位 english_identifier。
const goToPestDetail = (hot) => {
  const entry = typeof hot === 'string' ? { zh: hot, en: hot } : hot;
  const pest = pests.value.find(
    (p) => p.english_identifier && (p.name === entry.zh || (entry.en && p.name_en === entry.en)),
  );
  if (pest?.english_identifier) {
    router.push({
      name: 'PestDetail',
      params: { english_identifier: pest.english_identifier },
    });
  } else {
    console.warn('未找到病害详情:', entry.zh);
    // 如果找不到对应的病害，可以跳转到搜索页面或显示提示
  }
};

// 第 77 批：榜单显示名跟随语言。已经收录的病害用库里的名字；
// 没收录时用静态的中/英兜底（localizedField 按当前语言挑一个，不会出现空白）。
const hotPests = computed(() =>
  HOT_PEST_ENTRIES.map((entry) => {
    const found = pests.value.find((p) => p.name === entry.zh);
    return {
      zh: entry.zh,
      en: entry.en,
      label: localizedField(found || { name: entry.zh, name_en: entry.en }, 'name'),
    };
  }),
);

// 组件属性定义
const props = defineProps({
  query: {
    type: Object,
    default: () => ({})
  }
});

// 监听路由查询参数变化
watch(() => props.query, async (newQuery) => {
  console.log('Query props changed:', newQuery);

  try {
    // 重置到第一页
    currentPage.value = 1;

    if (newQuery?.crop) {
      const cropValue = newQuery.crop.toLowerCase();
      console.log('Processing crop from URL:', cropValue);

      // 1. 检查是否是英文作物名称（在cropTypeMap的key中）
      if (cropTypeMap[cropValue]) {
        selectedCrop.value = cropValue;
        console.log('Using English crop name:', cropValue);
      }
      // 2. 检查是否是中文作物名称（在reverseCropTypeMap的key中）
      else if (reverseCropTypeMap[cropValue]) {
        selectedCrop.value = reverseCropTypeMap[cropValue];
        console.log('Mapped Chinese crop to English:', cropValue, '->', selectedCrop.value);
      }
      // 3. 检查是否是中文作物名称（在cropTypeMap的value中）
      else if (Object.values(cropTypeMap).includes(cropValue)) {
        // 找到对应的英文key
        const enKey = Object.entries(cropTypeMap).find(([_, zh]) => zh === cropValue)?.[0];
        if (enKey) {
          selectedCrop.value = enKey;
          console.log('Mapped Chinese crop name to English key:', cropValue, '->', enKey);
        } else {
          selectedCrop.value = 'all';
          console.log('No matching crop found, showing all');
        }
      }
      // 4. 其他情况，显示所有
      else {
        selectedCrop.value = 'all';
        console.log('No matching crop found, showing all');
      }
    } else {
      // 如果crop参数是all或者不存在，显示所有作物
      selectedCrop.value = 'all';
      console.log('No crop specified, showing all');
    }

    // 重新加载数据
    await fetchPests();

    // 滚动到顶部
    window.scrollTo(0, 0);
  } catch (error) {
    console.error('Error handling route change:', error);
    toast.error(t('forum.loadFailed'));
  }
}, { immediate: true, deep: true });

// 组件挂载时获取数据
onMounted(async () => {
  const route = useRoute();

  // 初始化时检查URL参数
  if (route.query.crop) {
    selectedCrop.value = route.query.crop;
    console.log('Initial crop from URL:', route.query.crop);
  } else {
    selectedCrop.value = 'all';
  }

  // 获取数据
  await Promise.all([fetchPests(), fetchCropTypes()]);

  // 第 50 批：顺手更新离线资料包（失败不影响页面）
  refreshOfflineCache();

  console.log('Component mounted with crop:', selectedCrop.value);
});

</script>

<style scoped>
.encyclopedia-page {
padding: 2rem;
max-width: 1400px;
margin: 0 auto;
}

.page-banner {
background-color: #f8f9fa;
border-radius: 12px;
padding: 2.5rem;
text-align: center;
margin-bottom: 2.5rem;
border: 1px solid #e9ecef;
}

.page-banner h1 {
font-size: 2.5rem;
font-weight: 700;
color: #343a40;
margin-bottom: 0.75rem;
}

.page-banner p {
font-size: 1.1rem;
color: #6c757d;
max-width: 800px;
margin: 0 auto;
line-height: 1.6;
}

.filter-controls {
display: flex;
justify-content: center;
gap: 1rem;
margin-bottom: 3rem;
flex-wrap: wrap;
}

.filter-button {
padding: 0.7rem 1.5rem;
border-radius: 25px;
border: 1px solid #dee2e6;
background-color: #fff;
cursor: pointer;
transition: all 0.3s ease;
font-size: 0.95rem;
font-weight: 500;
color: #495057;
}

.filter-button:hover {
background-color: #e9ecef;
border-color: #adb5bd;
}

.filter-button.active {
background-color: #2a7f53;
color: #fff;
border-color: #2a7f53;
box-shadow: 0 4px 10px rgba(42, 127, 83, 0.2);
transform: translateY(-2px);
}

.loading-state, .empty-state {
text-align: center;
padding: 5rem;
color: #6c757d;
font-size: 1.25rem;
}

.pest-grid {
display: grid;
grid-template-columns: repeat(3, 1fr);
gap: 2.5rem;
margin-bottom: 2rem;
}

.pest-card {
background: white;
border-radius: 12px;
box-shadow: 0 6px 25px rgba(0,0,0,0.07);
overflow: hidden;
transition: transform 0.3s, box-shadow 0.3s;
display: flex;
flex-direction: column;
}

.pest-card:hover {
transform: translateY(-10px);
box-shadow: 0 10px 30px rgba(0,0,0,0.1);
}

.card-image-container {
width: 100%;
padding-top: 75%; /* 4:3 Aspect Ratio */
position: relative;
overflow: hidden;
}

.pest-image {
position: absolute;
top: 0;
left: 0;
width: 100%;
height: 100%;
object-fit: cover;
transition: transform 0.4s ease;
}

.pest-card:hover .pest-image {
transform: scale(1.05);
}

.card-content {
padding: 1.5rem;
flex-grow: 1;
display: flex;
flex-direction: column;
}

.card-content h3 {
margin: 0 0 0.75rem;
font-size: 1.3rem;
color: #212529;
}

.card-content .description {
font-size: 0.95rem;
color: #6c757d;
line-height: 1.6;
flex-grow: 1;
display: -webkit-box;
-webkit-box-orient: vertical;
-webkit-line-clamp: 3;
overflow: hidden;
text-overflow: ellipsis;
margin-bottom: 1.5rem;
}

.details-button {
text-decoration: none;
display: inline-block;
margin-top: auto; /* Push button to the bottom */
padding: 0.6rem 1.2rem;
border: 1px solid #ced4da;
background-color: transparent;
color: #007bff;
border-radius: 20px;
cursor: pointer;
transition: all 0.3s;
align-self: flex-start;
font-weight: 500;
}

.details-button:hover {
background-color: #007bff;
color: #fff;
border-color: #007bff;
}

/* ===== 管理员操作区 =====
   第 122 批：`.admin-toolbar` / `.admin-add-btn` / `.admin-import-btn` 以及卡片上的
   `.card-admin-actions` / `.admin-action-btn` 样式**已随管理功能一起删除** ——
   它们现在由管理后台的「病害百科维护」页负责（用 Element Plus 的表格与按钮）。 */

/* 第 50 批：离线模式提示条 */
.offline-note {
display: flex;
align-items: center;
gap: 8px;
flex-wrap: wrap;
margin: 0 0 14px;
padding: 10px 14px;
border: 1px solid #f0d9b0;
border-radius: 12px;
background: linear-gradient(120deg, #fdf6ea, #fffdf8);
color: #8a5a12;
font-size: 13px;
line-height: 1.7;
}

.offline-note i {
color: #b8761b;
}

.card-actions {
display: flex;
align-items: center;
justify-content: space-between;
gap: 0.75rem;
flex-wrap: wrap;
margin-top: auto;
}

.card-actions .details-button {
margin-top: 0;
}

/* 搜索栏样式统一在下方 .search-bar 处定义（第 74 批：此处原有一整套
   被后方同名规则完全覆盖的死代码，其中还残留 hover 变蓝(#409eff) 的旧配色，
   一并删除，避免"改了这里却不生效"以及三套主色并存）。 */

/* 主内容与右侧并排布局 */
.encyclopedia-main {
display: flex;
gap: 2.5rem;
align-items: flex-start;
}
.encyclopedia-content {
flex: 1;
}
.encyclopedia-sidebar {
width: 320px;
min-width: 260px;
background: #f8f9fa;
border-radius: 12px;
box-shadow: 0 2px 8px rgba(0,0,0,0.06);
padding: 2rem 1.5rem;
}
.hot-pests-section h3, .quick-links-section h3 {
font-size: 1.15rem;
color: #764ba2;
margin-bottom: 1rem;
}
.hot-pests-section ul {
list-style: none;
padding: 0;
margin: 0 0 1.5rem 0;
display: grid;
grid-template-columns: repeat(2, 1fr);
gap: 1rem;
}

.quick-links-section ul {
list-style: none;
padding: 0;
margin: 0 0 1.5rem 0;
}
.hot-pests-section li {
  margin-bottom: 8px;
  color: #555;
  font-size: 14px;
  display: flex;
  align-items: center;
  white-space: nowrap; /* 防止文字换行 */
  overflow: hidden; /* 隐藏溢出内容 */
  text-overflow: ellipsis; /* 超出部分显示省略号 */
  cursor: pointer;
  transition: all 0.3s ease;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid transparent;
  background-color: #f8f9fa;
  max-width: 100%; /* 确保不会超出容器 */
}

.hot-pests-section li:hover {
  background-color: #e9f5f0;
  color: #2a7f53;
  transform: translateX(6px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-color: #2a7f53;
}

.hot-pests-section li:active {
  transform: translateX(6px) scale(0.98);
}
.hot-rank {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.8em;
  height: 1.8em;
  background: #2a7f53;
  color: #fff;
  border-radius: 50%;
  font-weight: bold;
  margin-right: 0.7em;
  flex-shrink: 0;
}
.quick-links-section ul li {
  margin-bottom: 0.7rem;
}
.quick-links-section ul li a {
  color: #2a7f53;
  text-decoration: underline;
  font-size: 1rem;
  transition: color 0.2s;
}
.quick-links-section ul li a:hover {
  color: var(--brand-700, #1f6343);
}

/* 分页控件样式 */
.pagination-container {
  margin-top: 3rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.pagination {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.pagination-btn {
  padding: 0.6rem 1.2rem;
  border-radius: 25px;
  border: 1px solid #dee2e6;
  background-color: #fff;
  cursor: pointer;
  transition: all 0.3s ease;
  font-size: 0.95rem;
  color: #495057;
}

.pagination-btn:hover:not(:disabled) {
  background-color: #2a7f53;
  color: #fff;
  border-color: #2a7f53;
}

.pagination-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-numbers {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.page-number {
  width: 2.5rem;
  height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 1px solid #dee2e6;
  background-color: #fff;
  cursor: pointer;
  transition: all 0.3s ease;
  font-size: 0.95rem;
  color: #495057;
}

.page-number:hover {
  background-color: #e9ecef;
}

.page-number.active {
  background-color: #2a7f53;
  color: #fff;
  border-color: #2a7f53;
  box-shadow: 0 2px 5px rgba(42, 127, 83, 0.3);
}

.ellipsis {
  padding: 0 0.5rem;
  color: #6c757d;
}

.pagination-info {
  font-size: 0.9rem;
  color: #6c757d;
}
/* ================= 现代化覆写（设计变量见 assets/theme.css） ================= */
.encyclopedia-page {
  width: 100%;
  max-width: 1520px;
  margin: 0 auto;
  padding: 0 24px 48px;
  box-sizing: border-box;
}

/* 顶部横幅：改为渐变大卡片 */
.page-banner {
  position: relative;
  overflow: hidden;
  padding: 54px 40px;
  margin-bottom: 24px;
  text-align: center;
  border: none;
  border-radius: var(--radius-xl);
  background: var(--gradient-hero);
  box-shadow: var(--shadow-lg);
}

.page-banner::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.06) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(600px 320px at 78% 20%, #000 10%, transparent 75%);
  -webkit-mask-image: radial-gradient(600px 320px at 78% 20%, #000 10%, transparent 75%);
  pointer-events: none;
}

.page-banner h1,
.page-banner p {
  position: relative;
  z-index: 1;
}

.page-banner h1 {
  margin-bottom: 12px;
  font-size: 34px;
  font-weight: 800;
  letter-spacing: 1px;
  color: #fff;
}

.page-banner p {
  max-width: 760px;
  margin: 0 auto;
  font-size: 15px;
  line-height: 1.9;
  color: rgba(255, 255, 255, 0.85);
}

/* 作物筛选：胶囊按钮 */
.filter-controls {
  gap: 10px;
  margin-bottom: 18px;
}

.filter-button {
  padding: 9px 20px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border);
  background: var(--surface);
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-600);
  transition: all var(--dur) var(--ease);
}

.filter-button:hover {
  background: var(--brand-50);
  border-color: var(--brand-300);
  color: var(--brand-700);
}

.filter-button.active {
  background: var(--gradient-brand);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 8px 18px rgba(31, 99, 67, 0.22);
  transform: none;
}

/* 搜索栏 */
.search-bar {
  gap: 12px;
  margin-bottom: 26px;
}

/* 第 96 批：抓取未完成时的提示条（紧跟在搜索栏下方） */
.incomplete-alert {
  margin-bottom: 18px;
}

.search-bar input {
  width: 420px;
  max-width: 70vw;
  padding: 12px 22px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-strong);
  background: var(--surface);
  font-size: 14.5px;
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.search-bar input:focus {
  outline: none;
  border-color: var(--brand-500);
  box-shadow: var(--shadow-focus);
}

.search-bar button {
  /* 第 74 批修复："搜索"两个字曾竖排成上下两行。
     原因是按钮宽度被 flex 压缩（输入框 420px + 按钮在同一条 flex 行里），
     中文两字没有 nowrap 保护就会被逐字换行。这里给出最小宽度并禁止换行，
     同时与输入框等高，视觉成一组。 */
  flex: none;
  min-width: 96px;
  min-height: 46px;
  padding: 12px 26px;
  white-space: nowrap;
  border-radius: var(--radius-pill);
  background: var(--gradient-brand);
  font-size: 15px;
  font-weight: 600;
  box-shadow: 0 8px 18px rgba(31, 99, 67, 0.2);
}

.search-bar button:hover {
  background: var(--gradient-brand);
  transform: translateY(-1px);
}

/* 卡片网格：**固定 3 列**（每页 6 条 = 3 列 × 2 行）
   ------------------------------------------------------------------
   第 115 批：这里原来是 `repeat(auto-fill, minmax(260px, 1fr))`，列数跟着容器宽度变。
   内容区宽 1132px 时能塞下 4 列（4×260 + 3×22 = 1106 ≤ 1132），所以
   **1920 / 1600 这类宽屏上 6 条病害排成"4 + 2"**（实测：4 列 266px），
   第二行右侧空出一大块，与 `pageSize = 6`（2 行 × 3 列）的设定对不上。
   现在写死 3 列：宽屏每行 3 条、正好 2 行；窄屏在文件末尾的断点里降到 2 列 / 1 列。
   用 `minmax(0, 1fr)` 而不是 `1fr`：卡片里的长病害名/长描述撑开时不会顶破网格。 */
.pest-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 22px;
}

.pest-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.pest-card:hover {
  transform: translateY(-6px);
  box-shadow: var(--shadow-lg);
}

.card-content {
  padding: 20px;
}

.card-content h3 {
  font-size: 17px;
  font-weight: 700;
  color: var(--ink-800);
}

.card-content .description {
  font-size: 13.5px;
  line-height: 1.75;
  color: var(--ink-500);
}

.details-button {
  padding: 8px 18px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--brand-300);
  color: var(--brand-700);
  font-size: 13.5px;
  font-weight: 600;
}

.details-button:hover {
  background: var(--gradient-brand);
  border-color: transparent;
  color: #fff;
}

/* 侧边栏 */
.encyclopedia-sidebar {
  width: 300px;
  min-width: 260px;
  padding: 22px 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.hot-pests-section h3,
.quick-links-section h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 15.5px;
  font-weight: 700;
  color: var(--ink-800);
}

.hot-pests-section h3::before,
.quick-links-section h3::before {
  content: '';
  width: 4px;
  height: 15px;
  border-radius: var(--radius-pill);
  background: var(--brand-500);
}

.hot-pests-section ul {
  grid-template-columns: 1fr;
  gap: 8px;
}

.hot-pests-section li {
  padding: 8px 12px;
  margin-bottom: 0;
  border-radius: var(--radius-sm);
  background: var(--ink-50);
  font-size: 13.5px;
  color: var(--ink-700);
  cursor: pointer;
  transition: all var(--dur) var(--ease);
}

.hot-pests-section li:hover {
  background: var(--brand-50);
  color: var(--brand-700);
  transform: translateX(4px);
}

.hot-rank {
  display: inline-grid;
  place-items: center;
  width: 20px;
  height: 20px;
  margin-right: 8px;
  border-radius: 50%;
  background: var(--brand-100);
  color: var(--brand-700);
  font-size: 11.5px;
  font-weight: 700;
}

/* 分页 */
.pagination-btn,
.page-number {
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--ink-600);
  font-weight: 600;
  transition: all var(--dur) var(--ease);
}

.pagination-btn:hover:not(:disabled),
.page-number:hover {
  border-color: var(--brand-400);
  background: var(--brand-50);
  color: var(--brand-700);
}

.page-number.active {
  background: var(--gradient-brand);
  border-color: transparent;
  color: #fff;
}

.pagination-info {
  color: var(--ink-500);
  font-size: 13.5px;
}

.loading-state,
.empty-state {
  padding: 60px 20px;
  border-radius: var(--radius-lg);
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--ink-500);
  font-size: 15px;
}

@media (max-width: 1200px) {
  .encyclopedia-sidebar {
    display: none;
  }
}

/* 第 115 批：固定 3 列之后的窄屏降级 —— 与改造前 `auto-fill` 的实际表现一致
   （768px 左右本来就是 2 列，390px 左右本来就是 1 列），宽屏才是这次真正改的地方。 */
@media (max-width: 900px) {
  .pest-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .pest-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 768px) {
  .encyclopedia-page {
    padding: 0 16px 32px;
  }

  .page-banner {
    padding: 36px 22px;
  }

  .page-banner h1 {
    font-size: 26px;
  }

  .search-bar input {
    width: 100%;
    max-width: none;
  }
}
</style>

