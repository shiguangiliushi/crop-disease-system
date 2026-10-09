<template>
  <div class="news-container">
    <!-- 新闻头部 -->
    <div class="news-header">
      <div class="header-content">
        <!-- 第 33 批：原来这里是 `el-icon-news` —— Element Plus 2 已经没有图标字体了，
             这类类名不会渲染出任何字形（实测 ::before content 为 none、宽度 0），
             下面这些图标统一换成 Font Awesome。 -->
        <h1><i class="fas fa-newspaper"></i> {{ t('news.title') }}</h1>
        <p class="header-desc">{{ t('news.subtitle') }}</p>
      </div>
      <div class="header-actions" v-if="isAdmin">
        <el-button
          type="primary"
          @click="goToAddNews"
          class="add-news-btn"
        >
          <i class="fas fa-plus"></i> {{ t('news.addNews') }}
        </el-button>
      </div>
    </div>

    <!-- 分类筛选 -->
    <div class="filter-container">
      <div class="filter-left">
        <el-radio-group v-model="activeCategory" size="default" @change="handleFilterChange">
          <el-radio-button value="">{{ t('news.all') }}</el-radio-button>
          <el-radio-button v-for="category in categories" :key="category.value" :value="category.value">
            {{ category.label }}
          </el-radio-button>
        </el-radio-group>

        <el-select
          v-model="publishStatus"
          :placeholder="t('news.publishStatus')"
          clearable
          style="width: 120px; margin-left: 10px;"
          @change="handleFilterChange"
          @clear="handleFilterChange"
          v-if="isAdmin"
        >
          <el-option :label="t('news.published')" value="published" />
          <el-option :label="t('news.unpublished')" value="unpublished" />
        </el-select>
      </div>

      <div class="search-box">
        <el-input
          v-model="searchQuery"
          :placeholder="t('news.searchPlaceholder')"
          clearable
          style="width: 300px"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #prepend>
            <el-select v-model="searchType" :placeholder="t('news.searchType')" style="width: 110px">
              <el-option :label="t('news.searchByTitle')" value="title" />
              <el-option :label="t('news.searchByContent')" value="content" />
              <el-option :label="t('news.all')" value="all" />
            </el-select>
          </template>
          <template #append>
            <el-button @click="handleSearch"><i class="fas fa-search"></i></el-button>
          </template>
        </el-input>
      </div>
    </div>

    <div v-loading="loading" class="news-list-container">
      <!-- News List -->
      <div class="news-list">
        <div class="news-grid">
          <el-card
            v-for="newsItem in newsList"
            :key="newsItem.id"
            class="news-card"
            shadow="hover"
            @click="goToNewsDetail(newsItem.id)"
          >
            <div class="news-content">
              <div class="news-image">
                <el-image
                  v-if="newsItem.image_url"
                  :src="getFullImageUrl(newsItem.image_url)"
                  :preview-src-list="[getFullImageUrl(newsItem.image_url)]"
                  fit="cover"
                  class="news-image"
                  style="width: 100%; height: 200px; cursor: pointer;"
                  @click="$event.stopPropagation()"
                >
                  <div slot="error" class="image-slot">
                    <i class="fas fa-image"></i>
                  </div>
                </el-image>
                <div v-else class="no-image">
                  <el-icon><Picture /></el-icon>
                  <span>{{ t('news.noImage') }}</span>
                </div>
                <div class="news-category" v-if="newsItem.category">
                  {{ getCategoryLabel(newsItem.category) }}
                </div>
              </div>
              <div class="news-details">
                <h2 class="news-title">{{ localizedField(newsItem, 'title') }}</h2>
                <div class="news-meta">
                  <span class="news-source" v-if="newsItem.source">
                    <i class="fas fa-building-columns"></i> {{ localizedField(newsItem, 'source') }}
                  </span>
                  <span class="news-date">
                    <i class="fas fa-clock"></i> {{ formatDate(newsItem.created_at) }}
                  </span>
                  <span class="news-views" v-if="newsItem.views !== undefined">
                    <i class="fas fa-eye"></i> {{ t('forum.readsShort', { count: newsItem.views }) }}
                  </span>
                </div>
                <div class="news-summary">
                  {{ summaryOf(newsItem) }}
                </div>
                <div class="news-footer">
                  <div class="news-tags">
                    <el-tag
                      v-for="(tag, index) in (Array.isArray(newsItem.tags) ? newsItem.tags : [newsItem.tag].filter(Boolean))"
                      :key="index"
                      size="mini"
                      :type="getTagType(tag)"
                      style="margin-right: 5px; margin-bottom: 5px;"
                    >
                      {{ tag }}
                    </el-tag>
                    <el-tag
                      v-if="!newsItem.is_published"
                      size="mini"
                      type="info"
                      style="margin-left: 5px;"
                    >
                      {{ t('news.unpublished') }}
                    </el-tag>
                  </div>
                  <div class="news-actions">
                    <el-button
                      v-if="isAdmin"
                      type="text"
                      size="small"
                      @click.stop="editNews(newsItem)"
                    >
                      <el-icon><Edit /></el-icon> {{ t('news.edit') }}
                    </el-button>
                    <el-button
                      v-if="isAdmin"
                      type="text"
                      size="small"
                      @click.stop="confirmDelete(newsItem.id)"
                    >
                      <el-icon><Delete /></el-icon> {{ t('news.delete') }}
                    </el-button>
                    <el-button
                      type="text"
                      class="read-more"
                      @click.stop="goToNewsDetail(newsItem.id)"
                    >
                      {{ t('news.readMore') }} <i class="fas fa-arrow-right"></i>
                    </el-button>
                  </div>
                </div>
              </div>
            </div>
          </el-card>
        </div>

        <el-empty v-if="!loading && newsList.length === 0" :description="t('news.noNews')" />

        <div class="pagination" v-if="total > 0">
          <el-pagination
            v-model:currentPage="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[5, 10, 20, 50]"
            layout="total, sizes, prev, pager, next, jumper"
            :total="total"
            :pager-count="5"
            @size-change="handleSizeChange"
            @current-change="handleCurrentChange"
          >
            <template #default>
              <span>{{ t('common.totalItems', { count: total }) }}</span>
            </template>
          </el-pagination>
        </div>
      </div>
    </div>

    <!-- 第 31 批：新闻列表下面原来直接就是页脚，补一块"怎么用好行业动态"的说明 -->
    <!-- 第 63 批：卡片内容改由脚本 computed 生成，随语言切换 -->
    <PageExtras
      icon="fas fa-newspaper"
      :title="t('news.guideTitle')"
      :subtitle="t('news.guideSubtitle')"
      :items="guideItems"
    />

    <!-- Add/Edit News Dialog（第 33 批：改成"深绿头条 + 分段表单 + 底部操作条"） -->
    <el-dialog
      v-model="showAddDialog"
      width="680px"
      top="6vh"
      :close-on-click-modal="false"
      class="form-dialog"
    >
      <template #header>
        <div class="form-dialog-head">
          <span class="form-dialog-head-icon">
            <i :class="editingNews ? 'fas fa-pen-to-square' : 'fas fa-plus'"></i>
          </span>
          <div>
            <h3>{{ editingNews ? t('news.dialogEditTitle') : t('news.dialogCreateTitle') }}</h3>
            <p>
              {{ editingNews
                ? t('news.dialogEditHint')
                : t('news.dialogCreateHint') }}
            </p>
          </div>
        </div>
      </template>

      <div class="form-dialog-body">
        <el-form :model="newsForm" :rules="rules" ref="newsFormRef" label-width="0" label-position="top">
          <!-- 基本信息 -->
          <section class="form-section">
            <div class="form-section-head">
              <i class="fas fa-circle-info"></i>
              <h4>{{ t('news.basicInfo') }}</h4>
              <span class="section-hint">{{ t('news.basicInfoHint') }}</span>
            </div>

            <el-form-item :label="t('news.fieldTitle')" prop="title">
              <el-input
                v-model="newsForm.title"
                maxlength="200"
                show-word-limit
                :placeholder="t('news.fieldTitlePlaceholder')"
              />
            </el-form-item>

            <el-row :gutter="16">
              <el-col :xs="24" :sm="12">
                <el-form-item :label="t('news.fieldCategory')" prop="category">
                  <el-select v-model="newsForm.category" :placeholder="t('news.fieldCategoryPlaceholder')" style="width: 100%">
                    <el-option
                      v-for="item in categories"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item :label="t('news.fieldSource')" prop="source">
                  <el-input v-model="newsForm.source" :placeholder="t('news.fieldSourcePlaceholder')" />
                </el-form-item>
              </el-col>
            </el-row>
          </section>

          <!-- 正文 -->
          <section class="form-section">
            <div class="form-section-head">
              <i class="fas fa-align-left"></i>
              <h4>{{ t('news.bodySection') }}</h4>
              <span class="section-hint">{{ t('news.bodyHint') }}</span>
            </div>

            <el-form-item :label="t('news.searchByContent')" prop="content">
              <el-input
                v-model="newsForm.content"
                type="textarea"
                :rows="7"
                resize="none"
                :placeholder="t('news.bodyPlaceholder')"
              />
            </el-form-item>
          </section>

          <!-- 封面与标签 -->
          <section class="form-section">
            <div class="form-section-head">
              <i class="fas fa-image"></i>
              <h4>{{ t('news.coverSection') }}</h4>
              <span class="section-hint">{{ t('news.coverHint') }}</span>
            </div>

            <el-row :gutter="16">
              <el-col :xs="24" :sm="14">
                <el-form-item :label="t('news.coverLabel')">
                  <el-upload
                    class="tile-uploader"
                    action="#"
                    :show-file-list="false"
                    :before-upload="beforeUpload"
                    :on-change="handleUpload"
                    :auto-upload="false"
                    drag
                  >
                    <div class="upload-tile">
                      <img v-if="newsForm.image_preview" :src="newsForm.image_preview" :alt="t('news.coverPreviewAlt')" />
                      <div v-else class="upload-tile-empty">
                        <i class="fas fa-cloud-arrow-up"></i>
                        <span>{{ t('news.dropOr') }} <em>{{ t('news.clickUpload') }}</em></span>
                        <small>{{ t('news.coverFormats') }}</small>
                      </div>

                      <div v-if="newsForm.image_preview" class="upload-tile-actions">
                        <button type="button" :title="t('news.changeImage')">
                          <i class="fas fa-rotate"></i>
                        </button>
                        <button type="button" :title="t('news.removeImage')" @click.stop="removeImage">
                          <i class="fas fa-trash"></i>
                        </button>
                      </div>
                    </div>
                  </el-upload>
                </el-form-item>
              </el-col>

              <el-col :xs="24" :sm="10">
                <el-form-item :label="t('news.tagLabel')" prop="tags">
                  <el-select
                    v-model="newsForm.tags"
                    multiple
                    filterable
                    allow-create
                    default-first-option
                    :placeholder="t('news.tagPlaceholder')"
                    style="width: 100%"
                  >
                    <el-option
                      v-for="tag in newsForm.tags"
                      :key="tag"
                      :label="tag"
                      :value="tag"
                    />
                  </el-select>
                  <p class="field-hint">{{ t('news.tagHint') }}</p>
                </el-form-item>
              </el-col>
            </el-row>
          </section>

          <!-- 发布设置 -->
          <section class="form-section">
            <div class="form-section-head">
              <i class="fas fa-paper-plane"></i>
              <h4>{{ t('news.publishSection') }}</h4>
            </div>

            <el-form-item :label="t('news.publishStatus')" prop="is_published">
              <el-switch
                v-model="newsForm.is_published"
                :active-text="t('news.published')"
                :inactive-text="t('news.saveUnpublished')"
              />
              <p class="field-hint">
                <i class="fas fa-circle-info"></i>
                {{ t('news.publishHint') }}
              </p>
            </el-form-item>
          </section>
        </el-form>
      </div>

      <template #footer>
        <div class="form-dialog-footer">
          <span class="footer-hint">
            <i class="fas fa-shield-halved"></i> {{ t('news.saveNow') }}
          </span>
          <span>
            <el-button @click="showAddDialog = false">{{ t('common.cancel') }}</el-button>
            <el-button type="primary" @click="submitNews">
              <i class="fas fa-check"></i>
              {{ editingNews ? t('news.saveChanges') : t('news.createNews') }}
            </el-button>
          </span>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
// 第 33 批：Refresh / UploadFilled / Plus 已改用 Font Awesome 图标，不再需要
import { Picture, Delete, Edit } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useAuthStore } from '@/stores/auth';
import axios from 'axios';
import { toAbsoluteMediaUrl } from '@/api/http';
import api from '@/api';
// 与管理端「新闻管理」页共用同一套提交逻辑（字段白名单 + multipart 组装 + 错误文案）
import { createNews, updateNews, formatNewsError } from '@/api/news';
// 身份读写统一走适配器（sessionStorage 优先），避免"本标签页是 A、请求却带 B 的 token"
import { getToken, clearIdentity } from '@/utils/authStorage';
// 第 31 批：页面底部"怎么用好行业动态"补充信息区
import PageExtras from '@/components/PageExtras.vue';
import { useI18n } from '@/i18n';  // 第 63 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 72 批：新闻正文多语言

const { t } = useI18n();
const { localizedField } = useLocalized();

// 列表卡片摘要：英文界面下取英文正文（列表接口不返回 summary 字段，
// 直接截取正文前 160 字，比原来的 100 字更能看出内容）
const summaryOf = (item) => {
  const text = localizedField(item, 'content') || '';
  return text ? text.substring(0, 160) + '...' : '';
};

// 第 63 批：底部"怎么用好行业动态"卡片（原来内联在模板里，无法随语言切换）
const guideItems = computed(() => [
  { icon: 'fas fa-filter', title: t('news.guide1'), text: t('news.guide1Desc') },
  { icon: 'fas fa-magnifying-glass', title: t('news.guide2'), text: t('news.guide2Desc') },
  {
    icon: 'fas fa-camera',
    title: t('news.guide3'),
    text: t('news.guide3Desc'),
    more: t('news.guide3Link'),
    to: '/detect',
  },
  {
    icon: 'fas fa-lightbulb',
    title: t('news.guide4'),
    text: t('news.guide4Desc'),
    more: t('news.guide4Link'),
    to: '/feedback',
  },
]);

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();

// 检查是否是管理员
const isAdmin = computed(() => authStore.isAdmin);

// 第 121 批：`isEditMode` / `isCreateMode` 已删除 —— 那两条历史深链
// （`/news/create`、`/news/:id/edit`）现在重定向进管理后台的新闻管理页，
// 本页只剩下"行业动态列表 + 就地弹窗"这一种身份（新增/编辑都走页面里的按钮）。

// 新闻列表相关
const newsList = ref([]);
const loading = ref(false);
const currentPage = ref(1);
const pageSize = ref(10);
const total = ref(0);
const searchQuery = ref('');
const searchType = ref('title');
const activeCategory = ref('');
const publishStatus = ref('');

// 表单相关
const showAddDialog = ref(false);
const editingNews = ref(null);
const newsFormRef = ref(null);
const newsForm = ref({
  title: '',
  content: '',
  source: '',
  category: '',
  tags: [],
  image: null,
  is_published: true
});

// 表单验证规则（文案走 i18n，第 63 批）
const rules = {
  title: [
    { required: true, message: t('news.validateTitle'), trigger: 'blur' },
    { min: 5, max: 100, message: t('news.validateTitleLength'), trigger: 'blur' }
  ],
  content: [
    { required: true, message: t('news.validateContent'), trigger: 'blur' },
    { min: 10, message: t('news.validateContentMin'), trigger: 'blur' }
  ],
  category: [
    { required: true, message: t('news.validateCategory'), trigger: 'change' }
  ]
};

// 新闻分类（标签走 i18n，第 63 批；value 保持后端约定的英文标识）
const categories = computed(() => [
  { label: t('news.catPolicy'), value: 'policy' },
  { label: t('news.catTech'), value: 'tech' },
  { label: t('news.catMarket'), value: 'market' },
  { label: t('news.catReport'), value: 'report' },
  { label: t('news.catNotice'), value: 'notice' }
]);

// 获取分类标签
const getCategoryLabel = (value) => {
  const category = categories.value.find(item => item.value === value);
  return category ? category.label : value;
};

// 标签类型
const getTagType = (tag) => {
  const types = ['', 'success', 'info', 'warning', 'danger'];
  let hash = 0;
  for (let i = 0; i < tag.length; i++) {
    hash = tag.charCodeAt(i) + ((hash << 5) - hash);
  }
  return types[Math.abs(hash) % types.length];
};

// 重置表单
const resetForm = () => {
  newsForm.value = {
    title: '',
    content: '',
    source: '',
    category: '',
    tags: [],
    image: null,
    is_published: true
  };
  editingNews.value = null;
  if (newsFormRef.value) {
    newsFormRef.value.resetFields();
  }
};

// 显示添加新闻对话框
const goToAddNews = () => {
  // 重置表单
  resetForm();
  // 设置编辑状态
  editingNews.value = null;
  // 显示对话框
  showAddDialog.value = true;
};

// 编辑新闻
const editNews = async (news) => {
  try {
    await loadNewsDetail(news.id);
  } catch (error) {
    console.error('加载新闻详情失败:', error);
    ElMessage.error(t('news.loadDetailFailed'));
  }
};

// 格式化日期
const formatDate = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
};

// 处理搜索
const handleSearch = () => {
  currentPage.value = 1;
  fetchNews();
};

// 处理筛选条件变化
const handleFilterChange = () => {
  currentPage.value = 1;
  fetchNews();
};

// 处理每页条数变化
const handleSizeChange = (val) => {
  pageSize.value = val;
  fetchNews();
};

// 处理当前页码变化
const handleCurrentChange = (val) => {
  currentPage.value = val;
  fetchNews();
};

// 加载新闻详情
const loadNewsDetail = async (id) => {
  try {
    loading.value = true;
    // 注意：vite.config.ts 中已经配置了 /api 代理，所以这里不需要再加 /api
    const url = `/news/${id}/`;
    console.log('正在加载新闻详情，URL:', url);

    const response = await axios.get(url, {
      headers: {
        'Content-Type': 'application/json'
      }
    });

    const data = response.data;
    console.log('新闻详情响应:', data);

    if (!data) {
      throw new Error(t('news.emptyData'));
    }

    // 处理标签数据
    // 后端 tags 是"逗号分隔的字符串"（见 NewsSerializer 的 tags 字段）。
    // 原来只有 Array.isArray 时才赋值，字符串形态会被丢成 []，
    // 保存时再把空数组拼成空字符串发回去 → **已有标签被静默清空**。
    let tags = [];
    if (Array.isArray(data.tags)) {
      tags = data.tags;
    } else if (typeof data.tags === 'string' && data.tags.trim()) {
      tags = data.tags.split(',').map((item) => item.trim()).filter(Boolean);
    } else if (data.tag) {
      tags = [data.tag];
    }

    // 处理图片URL
    let imageUrl = data.image || data.image_url;

    // 更新表单数据
    newsForm.value = {
      ...data,
      id: data.id || null,
      title: data.title || '',
      content: data.content || '',
      source: data.source || '',
      category: data.category || '',
      tags: tags,
      image: null, // 重置为null，避免使用缓存的File对象
      image_url: imageUrl, // 确保image_url被正确设置
      image_preview: imageUrl ? getFullImageUrl(imageUrl) : null,  // 添加图片预览URL
      is_published: data.is_published || false
    };

    console.log('更新后的表单数据:', newsForm.value);
    // 标记"正在编辑哪条新闻"，否则弹窗标题会显示成「添加新闻」
    editingNews.value = data;
    showAddDialog.value = true;
    return data;
  } catch (error) {
    console.error('加载新闻详情失败:', error);
    let errorMessage = t('news.loadDetailFailed');

    if (error.response) {
      // 服务器返回了错误响应
      if (error.response.status === 404) {
        errorMessage = t('news.notFound');
      } else if (error.response.status === 403) {
        errorMessage = t('news.forbidden');
      } else if (error.response.data && error.response.data.detail) {
        errorMessage = error.response.data.detail;
      }
    } else if (error.request) {
      // 请求已发出但没有收到响应
      errorMessage = t('msg.cannotConnect');
    }

    ElMessage.error(errorMessage);
    // 不自动跳转，让用户决定下一步操作
    // router.push({ name: 'news' });
    throw error; // 重新抛出错误，让调用者处理
  } finally {
    loading.value = false;
  }
};

// 获取新闻列表
const fetchNews = async () => {
  try {
    loading.value = true;

    // 构建查询参数
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      search: searchQuery.value,
      search_type: searchType.value,
      category: activeCategory.value,
      is_published: publishStatus.value === 'published' ? 'true' :
                   publishStatus.value === 'unpublished' ? 'false' : ''
    };

    // 移除空参数
    Object.keys(params).forEach(key => {
      if (params[key] === '' || params[key] === null || params[key] === undefined) {
        delete params[key];
      }
    });

    // 构建查询字符串，确保没有多余的斜杠
    const queryString = new URLSearchParams(params).toString();
    // 确保URL格式正确，包含/api前缀
    const baseUrl = '/api/news'.replace(/\/+$/, '');
    // 加时间戳：管理端下架/发布后，浏览器不能继续拿"下架前"的缓存列表，
    // 否则会出现"后台已下架、前台刷新还是旧内容"的假象。
    const cacheBuster = `_t=${Date.now()}`;
    const url = queryString ? `${baseUrl}?${queryString}&${cacheBuster}` : `${baseUrl}?${cacheBuster}`;
    console.log('Final request URL:', url);  // 添加调试日志

    console.log('Request URL:', url);

    // 准备请求头
    const headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    };
    
    // 只有在有token时才添加Authorization头
    const token = getToken();
    if (token) {
      headers['Authorization'] = `Token ${token}`;
    }
    
    console.log('Request headers:', JSON.stringify(headers, null, 2));
    
    // 使用 fetch API 发送请求
    const response = await fetch(url, {
      method: 'GET',
      headers: headers,
      credentials: 'include',  // 确保发送cookies
      cache: 'no-store'        // 发布状态随时可能被管理员改动，禁用协商缓存
    });

    console.log('Response status:', response.status, response.statusText);
    
    if (!response.ok) {
      let errorData;
      try {
        errorData = await response.json();
        console.error('Error response data:', errorData);
      } catch (e) {
        console.error('Failed to parse error response:', e);
        errorData = await response.text();
        console.error('Raw error response:', errorData);
      }
      
      const error = new Error(`HTTP error! status: ${response.status}`);
      error.response = {
        status: response.status,
        statusText: response.statusText,
        data: errorData
      };
      throw error;
    }
    
    const data = await response.json();
    console.log('API Response:', data);

    // 处理响应数据
    if (data.results) {
      newsList.value = data.results;
      total.value = data.count || data.results.length;
    } else {
      newsList.value = Array.isArray(data) ? data : [];
      total.value = Array.isArray(data) ? data.length : 0;
    }
    
    return data;
  } catch (error) {
    console.error('获取新闻列表失败:', error);
    console.error('Error details:', {
      message: error.message,
      response: error.response
    });

    newsList.value = [];
    total.value = 0;

    if (error.response) {
      if (error.response.status === 401) {
        ElMessage.error(t('msg.unauthorized'));
        // 清除认证信息（两个存储一起清）
        clearIdentity();
        router.push('/login');
      } else if (error.response.status === 403) {
        ElMessage.error(t('msg.forbidden'));
      } else if (error.response.status === 404) {
        ElMessage.error(t('msg.notFoundResource'));
      } else if (error.response.status >= 500) {
        ElMessage.error(t('msg.serverError'));
      } else {
        ElMessage.error(t('msg.requestFailedWith', { detail: error.response.statusText || error.message }));
      }
    } else {
      ElMessage.error(t('msg.networkErrorWith', { detail: error.message }));
    }
    
    // 重新抛出错误，以便调用方可以处理
    throw error;
  } finally {
    loading.value = false;
  }
};

// 提交新闻表单
const submitNews = async () => {
  try {
    await newsFormRef.value.validate();
  } catch {
    // 表单校验失败：Element Plus 已在对应表单项上标红，这里不再弹通用错误
    return;
  }

  loading.value = true;
  try {
    // 只提交后端认识的字段，并且复用「新闻管理」页同一套组装逻辑（api/news.js）。
    //
    // 原实现把详情接口返回的字段全塞进 FormData（含 id / created_at_formatted /
    // image_url），又因为 loadNewsDetail 把 image 置成了 null，于是每次保存都会
    // 额外发出 `image=''` —— 后端按"清空封面图"处理；标签数组也会被拼成空字符串。
    // 结果：在行业动态页"编辑成功"却把封面图和标签弄丢了。
    const imageFile = newsForm.value.image instanceof File ? newsForm.value.image : null;
    const payload = {
      title: newsForm.value.title,
      content: newsForm.value.content,
      category: newsForm.value.category,
      source: newsForm.value.source,
      tags: newsForm.value.tags,
      is_published: newsForm.value.is_published,
      // 只有"用户确实移除了封面"（没有新文件、也没有预览）时才要求清空，
      // 否则保持原有封面不动
      clear_image: !imageFile && !newsForm.value.image_preview,
    };

    const newsId = newsForm.value.id || route.params.id;

    if (newsId) {
      await updateNews(newsId, payload, imageFile);
      ElMessage.success(t('news.updatedOk'));
    } else {
      await createNews(payload, imageFile);
      ElMessage.success(t('news.createdOk'));
    }

    // 刷新新闻列表并等待完成
    await fetchNews();

    // 关闭对话框
    showAddDialog.value = false;

    // 重置表单
    resetForm();
  } catch (error) {
    console.error('保存失败:', error);
    // 原来只读 error.response.data.detail，字段级错误（典型："已存在同标题的新闻"）
    // 会退化成没有任何信息量的「保存失败」，管理员只能靠反复试。
    // 这里复用统一文案工具，把后端返回的字段错误展示出来。
    ElMessage.error(formatNewsError(error, t('msg.savingFailedRetry')));
  } finally {
    loading.value = false;
  }
};

// 删除新闻
const confirmDelete = (id) => {
  ElMessageBox.confirm(t('newsDetail.deleteConfirm'), t('msg.notice'), {
    confirmButtonText: t('msg.confirmed'),
    cancelButtonText: t('msg.cancel'),
    type: 'warning'
  }).then(async () => {
    try {
      // 注意：移除了URL开头的/api，因为baseURL已经包含了/api
      await api.delete(`news/${id}/`);
      ElMessage.success(t('msg.deleteOk'));
      fetchNews();
    } catch (error) {
      console.error('删除失败:', error);
      console.error('错误详情:', {
        message: error.message,
        response: error.response?.data,
        status: error.response?.status,
        headers: error.response?.headers
      });
      ElMessage.error(error.response?.data?.detail || t('msg.deleteFailed'));
    }
  }).catch(() => {
    // 用户取消删除
  });
};

// 图片上传前处理
const beforeUpload = (file) => {
  const isImage = file.type.startsWith('image/');
  if (!isImage) {
    ElMessage.error(t('msg.imageOnly'));
    return false;
  }
  const isLt5M = file.size / 1024 / 1024 < 5;
  if (!isLt5M) {
    ElMessage.error(t('msg.imageTooLarge5'));
    return false;
  }
  return true;
};

// 说明：原来这里有一个 getCookie('csrftoken') 辅助函数，只服务于 submitNews 里
// 手写的请求头；改为统一走 @/api/news（内部用 @/api/http，已自动附带
// Token 与 X-CSRFToken）之后它就没有调用点了，故删除。
// 注意：通过统一客户端提交还避免了"手写 multipart 请求体"带来的字段污染问题。

// 处理图片URL，确保是完整路径并添加时间戳防止缓存
const getFullImageUrl = (url) => {
  // 如果URL为空或不是字符串，返回空字符串
  if (!url || typeof url !== 'string') {
    return '';
  }

  // 移除URL中可能存在的多余斜杠
  url = url.replace(/([^:]\/)\/+/g, '$1');

  // 如果URL已经是带时间戳的，直接返回
  if (url.includes('?t=')) {
    return url;
  }

  // 统一由 @/api/http 处理基础地址（自动去掉 /api 前缀，兼容绝对地址）
  const absolute = toAbsoluteMediaUrl(url);
  if (!absolute) return '';

  // 追加时间戳，避免浏览器缓存旧图
  const separator = absolute.includes('?') ? '&' : '?';
  return `${absolute}${separator}t=${Date.now()}`;
};

// 处理图片上传
const handleUpload = (file) => {
  console.log('处理文件上传:', file);

  // 生成预览URL
  const reader = new FileReader();

  // 确保我们有文件对象
  const fileObj = file.raw || file;

  if (!fileObj) {
    console.error('无效的文件对象');
    ElMessage.error(t('news.invalidFile'));
    return false;
  }

  // 检查文件类型
  const isImage = fileObj.type.startsWith('image/');
  if (!isImage) {
    ElMessage.error(t('msg.imageOnly'));
    return false;
  }

  // 检查文件大小（5MB）
  const isLt5M = fileObj.size / 1024 / 1024 < 5;
  if (!isLt5M) {
    ElMessage.error(t('msg.imageTooLarge5'));
    return false;
  }

  // 读取文件内容
  reader.onload = (e) => {
    // 直接使用Data URL作为预览
    newsForm.value.image_preview = e.target.result;

    // 保存文件对象到表单数据
    newsForm.value.image = fileObj;

    console.log('生成预览URL:', newsForm.value.image_preview);
    console.log('文件信息:', fileObj);

    // 如果是编辑模式，清除原始图片URL，以便在提交时更新
    if (newsForm.value.id) {
      newsForm.value.image_url = null;
    }

    // 强制更新DOM
    newsForm.value = { ...newsForm.value };
  };

  reader.onerror = (error) => {
    console.error('文件读取错误:', error);
    ElMessage.error(t('news.imageUploadFailed'));
  };

  // 开始读取文件
  reader.readAsDataURL(fileObj);

  // 返回false阻止自动上传，因为我们会在submitNews中处理上传
  return false;
};

// 删除已上传的图片
const removeImage = (e) => {
  e.stopPropagation();
  newsForm.value.image = null;
  newsForm.value.image_preview = null;
  newsForm.value.image_url = null;
  // 强制更新DOM
  newsForm.value = { ...newsForm.value };
};

// 跳转到新闻详情页
const goToNewsDetail = (id) => {
  router.push({
    name: 'news-detail',
    params: { id }
  });
};

// 初始化
onMounted(() => {
  fetchNews();
});

// 监听路由变化：从任何"新闻相关"的深链回到本页列表时，把弹窗收起来并刷新列表
// （第 121 批：原先这里还要处理"编辑模式/创建模式"，那两条深链现在重定向走了）
watch(() => route.name, (newVal) => {
  if (newVal === 'news') {
    showAddDialog.value = false;
    fetchNews();
  }
});

</script>

<style scoped>
.news-container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
  background-color: #f5f7fa;
  min-height: calc(100vh - 60px);
}

.news-header {
  position: relative;
  text-align: match-parent;
  -webkit-text-align: match-parent;
  padding: 20px;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-content h1 {
  font-size: 2.2rem;
  color: #2c3e50;
  margin: 0 0 10px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 600;
}

.header-desc {
  color: #606266;
  font-size: 1.1rem;
  margin: 10px 0 0;
  line-height: 1.6;
}

.add-news-btn {
  margin-top: 20px;
  padding: 10px 24px;
  font-size: 1rem;
  font-weight: 500;
  letter-spacing: 0.5px;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
}

.filter-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 15px;
  background: #fff;
  padding: 18px 24px;
  border-radius: 12px;
  box-shadow: 0 2px 16px rgba(0, 0, 0, 0.05);
  border: 1px solid #ebeef5;
}

.search-box {
  min-width: 280px;
  flex: 0 1 auto;
}

:deep(.el-radio-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-right: 10px;
}

:deep(.el-radio-button__inner) {
  border-radius: 20px !important;
  padding: 8px 18px;
  transition: all 0.3s;
  font-weight: 500;
  border: 1px solid #dcdfe6;
}

:deep(.el-radio-button__orig-radio:checked + .el-radio-button__inner) {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 10px var(--el-color-primary-light-5);
  color: #fff;
}

/* 头部操作按钮 */
.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}

.home-button {
  margin-left: 15px;
  margin-right: 20px;
  transition: all 0.3s ease;
  background-color: var(--brand-600, #2a7f53);
  border: none;
  padding: 8px 15px;
  border-radius: 4px;
  color: white;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 6px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
}

.home-button i {
  font-size: 16px;
}

.home-button:hover {
  background-color: var(--el-color-primary-light-3);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* 新闻列表 */
.news-list {
  margin-top: 30px;
}

.news-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 24px;
  margin-bottom: 20px;
}

.news-card {
  cursor: pointer;
  transition: all 0.3s ease;
  height: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
  -webkit-transition: all 0.3s ease;
  transition: all 0.3s ease;
}

.news-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 6px 18px 0 rgba(0, 0, 0, 0.1);
}

.news-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  padding: 20px;
}

.news-image {
  width: 100%;
  height: 180px;
  overflow: hidden;
  position: relative;
  border-radius: 4px 4px 0 0;
  margin-bottom: 16px;
}

.news-image .el-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
}

.news-card:hover .news-image .el-image {
  transform: scale(1.05);
}

.news-category {
  position: absolute;
  top: 10px;
  right: 10px;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.news-details {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.news-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 12px 0;
  color: #303133;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}

.news-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  color: #909399;
  font-size: 13px;
  margin-bottom: 12px;
}

.news-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.news-meta i {
  font-size: 14px;
}

/* 第 33 批：图片上传改用主题里的 .upload-tile 瓦片
   （原来的 .image-uploader / .image-preview-wrapper / .image-actions 一整套
   自定义样式已随旧弹窗一起删除）。这里只负责抹掉 el-upload 自带的 drag 外壳，
   让瓦片自己撑满、不要出现双层虚线边框。 */
.tile-uploader {
  width: 100%;
}

.tile-uploader :deep(.el-upload),
.tile-uploader :deep(.el-upload-dragger) {
  width: 100%;
  padding: 0;
  border: none;
  background: transparent;
}

.tile-uploader :deep(.el-upload-dragger.is-dragover) {
  border: none;
  background: transparent;
}

.news-summary {
  color: #606266;
  font-size: 14px;
  line-height: 1.8;
  margin-bottom: 16px;
  flex: 1;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}

.news-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px dashed #e4e7ed;
}

.news-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
}

.news-actions {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-left: auto;
}

.news-actions .el-button {
  padding: 4px 8px;
  font-size: 12px;
  color: #606266;
  transition: all 0.3s;
}

.news-actions .el-button:hover {
  color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
}

.news-actions .el-button + .el-button {
  margin-left: 0;
}

.read-more {
  color: var(--el-color-primary);
  font-size: 13px;
  font-weight: 500;
  transition: all 0.3s;
}

.read-more:hover {
  color: var(--el-color-primary-light-3);
}

.read-more i {
  transition: transform 0.3s;
}

.read-more:hover i {
  transform: translateX(3px);
}

.news-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
  border-color: #e4e7ed;
}

.news-uploader {
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #f5f7fa;
  -webkit-transition: border-color 0.3s;
  transition: border-color 0.3s;
  border: 1px dashed #d9d9d9;
  border-radius: 8px;
  width: 100%;
  height: 180px;
  cursor: pointer;
  -webkit-appearance: none;
  appearance: none;
  -webkit-text-size-adjust: 100%;
  -ms-text-size-adjust: 100%;
  -moz-text-size-adjust: 100%;
  text-size-adjust: 100%;
}

.news-uploader:hover {
  border-color: var(--brand-400, #5fb088);
}

.news-uploader-icon {
  font-size: 36px;
  color: #8c939b;
  transition: color 0.3s;
}

.news-uploader:hover .news-uploader-icon {
  color: var(--brand-600, #2a7f53);
}

.news-uploader-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
}

.news-uploader-img:hover {
  transform: scale(1.05);
}

/* 弹窗样式 */
:deep(.el-dialog) {
  border-radius: 12px;
  max-width: 700px;
}

:deep(.el-dialog__header) {
  padding: 20px 24px;
  border-bottom: 1px solid #f0f0f0;
  margin-right: 0;
}

:deep(.el-dialog__title) {
  font-size: 1.2rem;
  font-weight: 600;
  color: #303133;
}

:deep(.el-dialog__body) {
  padding: 24px;
}

/* 响应式布局 */
@media (max-width: 1200px) {
  .news-grid {
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 20px;
  }
}

@media (max-width: 992px) {
  .news-grid {
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 16px;
  }

  .board-latest {
    display: none;
  }
}

@media (max-width: 768px) {
  .news-container {
    padding: 15px;
  }

  .news-header {
    padding: 30px 15px;
  }

  .header-content h1 {
    font-size: 1.8rem;
  }

  .news-categories {
    flex-direction: column;
    align-items: stretch;
    padding: 15px;
  }

  .search-box {
    width: 100%;
    margin-top: 10px;
  }

  :deep(.el-radio-group) {
    justify-content: center;
    margin-bottom: 10px;
  }

  .news-grid {
    grid-template-columns: 1fr;
    gap: 20px;
  }

  .news-uploader {
    height: 180px;
  }
}

@media (max-width: 480px) {
  .header-content h1 {
    font-size: 1.6rem;
  }

  .header-desc {
    font-size: 1rem;
  }

  :deep(.el-radio-button__inner) {
    padding: 6px 14px;
    font-size: 13px;
  }
}

/* ================= 现代化覆写（设计变量见 assets/theme.css） ================= */
.news-container {
  width: 100%;
  max-width: 1500px;
  margin: 0 auto;
  padding: 8px 24px 48px;
  box-sizing: border-box;
}

/* 顶部标题区 */
.news-header {
  padding: 34px 32px;
  margin-bottom: 22px;
  border-radius: var(--radius-xl);
  background: var(--gradient-brand-soft);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}

.header-content h1,
.news-header h1 {
  font-size: 28px;
  font-weight: 800;
  color: var(--brand-800);
  letter-spacing: 0.5px;
}

.header-desc {
  margin-top: 8px;
  font-size: 14px;
  color: var(--ink-500);
}

/* 筛选栏 */
.filter-container {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 16px 20px;
  margin-bottom: 24px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-xs);
}

.filter-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-box input {
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-strong);
  padding: 9px 18px;
  font-size: 14px;
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.search-box input:focus {
  outline: none;
  border-color: var(--brand-500);
  box-shadow: var(--shadow-focus);
}

.add-news-btn {
  margin-left: auto;
  border-radius: var(--radius-pill);
  background: var(--gradient-brand);
  border: none;
  color: #fff;
  padding: 10px 22px;
  font-weight: 600;
  box-shadow: 0 8px 18px rgba(31, 99, 67, 0.2);
  cursor: pointer;
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.add-news-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 24px rgba(31, 99, 67, 0.26);
}

/* 新闻网格 */
.news-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 22px;
}

.news-card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.news-card:hover {
  transform: translateY(-6px);
  box-shadow: var(--shadow-lg);
}

.news-image {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: var(--ink-50);
}

.news-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.45s var(--ease);
}

.news-card:hover .news-image img {
  transform: scale(1.06);
}

.no-image {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  color: var(--ink-300);
  font-size: 34px;
  background: var(--ink-50);
}

.news-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  padding: 20px;
}

.news-title {
  margin: 0 0 10px;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.5;
  color: var(--ink-800);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.news-summary {
  margin: 0 0 14px;
  font-size: 13.5px;
  line-height: 1.75;
  color: var(--ink-500);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.news-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: auto;
  font-size: 12.5px;
  color: var(--ink-400);
}

.news-category {
  padding: 3px 12px;
  border-radius: var(--radius-pill);
  background: var(--brand-50);
  color: var(--brand-700);
  font-weight: 600;
}

.news-source,
.news-views {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.news-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 14px;
}

.news-tags span,
.news-tags .el-tag {
  border-radius: var(--radius-pill);
}

.news-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 14px;
  margin-top: 14px;
  border-top: 1px solid var(--border);
}

.read-more {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--brand-700);
  font-size: 13.5px;
  font-weight: 600;
  text-decoration: none;
  transition: gap var(--dur) var(--ease);
}

.read-more:hover {
  gap: 10px;
}

.news-actions {
  display: flex;
  gap: 8px;
}

/* 分页 */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 28px;
}

/* 表单弹窗（第 33 批：弹窗外壳、分段与底部操作条已抽到 theme.css 的
   .form-dialog / .form-section / .form-dialog-footer，这里只留图片占位） */
.image-slot {
  border-radius: var(--radius);
  border: 1px dashed var(--border-strong);
  background: var(--surface-muted);
}

@media (max-width: 768px) {
  .news-container {
    padding: 0 16px 32px;
  }

  .news-header {
    padding: 24px 20px;
  }

  .news-grid {
    grid-template-columns: 1fr;
  }

  .add-news-btn {
    margin-left: 0;
    width: 100%;
  }
}
</style>
