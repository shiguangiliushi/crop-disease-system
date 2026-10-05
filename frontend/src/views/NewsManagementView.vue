<template>
  <div class="news-management tinted-page">
    <!-- 返回入口（第 87 批：本页只能从顶栏「管理」下拉进来，此前没有返回按钮） -->
    <BackButton />

    <!-- 页头（第 29 批：改用全局 .admin-hero 的深绿实底样式，
         原来浅绿页头铺在浅绿工作区底上会糊成一片） -->
    <div class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="bi bi-newspaper"></i></span>
        <div>
          <h2>{{ t('newsMgmt.title') }}</h2>
          <p>{{ t('newsMgmt.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <!-- 第 88 批修复：这里原来写了 `type="primary"`，而全局 theme.css（在
             Element Plus 之后引入）有一条
             `.el-button--primary:not(.is-link):not(.is-text):not(.is-plain):not(.is-disabled)`
             把背景设成 --gradient-brand。它与 `.btn-on-brand.el-button` 争这个按钮时，
             本按钮的底色被涂成**深绿渐变**，而文字色是 .btn-on-brand 给的**深绿**
             （--brand-700）—— 深绿字压深绿底，就是"文字看不清"。
             背景走 `background:` 简写、文字走 CSS 变量，两边各赢一半，才出现这种半吊子状态。
             修法与新闻详情页返回按钮（第 81 批）一致：**去掉 type="primary"**，
             那条全局规则就不再命中；`.btn-on-brand` 本身就提供白底 + 深绿字。
             ↓ 不要把它改回 type="primary"（理由同第 81 批，改了就是深绿底 + 深绿字）。 -->
        <el-button size="large" class="add-btn btn-on-brand" @click="handleCreate">
          <el-icon><Plus /></el-icon>
          <span>{{ t('newsMgmt.newNews') }}</span>
        </el-button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-input
        v-model="filters.keyword"
        class="filter-keyword"
        :placeholder="t('newsMgmt.searchPlaceholder')"
        clearable
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>

      <!-- 第 88 批：清空下拉也要重查（el-select 的清除不发 change，只发 clear） -->
      <el-select v-model="filters.category" class="filter-select" :placeholder="t('newsMgmt.allCategories')" clearable @change="handleSearch" @clear="handleSearch">
        <el-option v-for="item in NEWS_CATEGORIES" :key="item.value" :label="t(item.labelKey)" :value="item.value" />
      </el-select>

      <el-select v-model="filters.status" class="filter-select" :placeholder="t('newsMgmt.allStatus')" clearable @change="handleSearch" @clear="handleSearch">
        <el-option :label="t('newsMgmt.tabPublished')" value="published" />
        <el-option :label="t('newsMgmt.draft')" value="draft" />
      </el-select>

      <el-button type="primary" plain @click="handleSearch">{{ t('newsMgmt.query') }}</el-button>
      <el-button text @click="resetFilters">{{ t('newsMgmt.reset') }}</el-button>

      <span class="filter-total">{{ t('newsMgmt.totalCount', { count: pagination.total }) }}</span>
    </div>

    <!-- 统计小卡（第 28 批：原来整页只有白卡片，加一点色彩与信息密度） -->
    <div class="admin-stats">
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-newspaper"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.total }}</div>
          <div class="stat-tile-label">{{ t('newsMgmt.tabAll') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--ok">
        <span class="stat-tile-icon"><i class="fas fa-circle-check"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.published }}</div>
          <div class="stat-tile-label">{{ t('newsMgmt.tabPublished') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--pending">
        <span class="stat-tile-icon"><i class="fas fa-file-pen"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.draft }}</div>
          <div class="stat-tile-label">{{ t('newsMgmt.tabUnpublished') }}</div>
        </div>
      </div>
    </div>

    <!-- 列表（第 29 批：卡片加"着色头条"，表格加斑马纹，整块不再是一张白纸） -->
    <el-card class="table-card admin-list-card" shadow="never">
      <div class="panel-head">
        <span class="panel-icon"><i class="fas fa-table-list"></i></span>
        <h3 class="panel-title">{{ t('newsMgmt.listTitle') }}</h3>
        <span class="panel-count">{{ t('newsMgmt.totalCount', { count: pagination.total }) }}</span>
        <div class="panel-head-right">
          <span class="panel-hint">{{ t('newsMgmt.listHint') }}</span>
        </div>
      </div>

      <div class="panel-body">
        <el-table v-loading="loading" :data="newsList" style="width: 100%" row-key="id">
        <el-table-column :label="t('newsMgmt.colCover')" width="110">
          <template #default="{ row }">
            <div class="cover-cell">
              <img v-if="row.image_url" :src="row.image_url" class="cover-img" :alt="t('newsMgmt.colCover')" />
              <div v-else class="cover-placeholder"><i class="bi bi-image"></i></div>
            </div>
          </template>
        </el-table-column>

        <el-table-column :label="t('newsMgmt.colTitle')" min-width="240">
          <template #default="{ row }">
            <div class="title-cell">
              <!-- 第 79 批：标题与来源是内容数据（后端已有 title_en / source_en），
                   原来直接渲染中文，英文界面下后台新闻列表整列是中文 -->
              <span class="title-text">{{ localizedField(row, 'title') }}</span>
              <div class="title-meta">
                <el-tag size="small" effect="plain" type="success">{{ getNewsCategoryLabel(row.category, t) }}</el-tag>
                <span v-if="row.source" class="source-text">
                  {{ t('newsMgmt.sourceLabel', { source: localizedField(row, 'source') }) }}
                </span>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column :label="t('newsMgmt.colAuthor')" width="110">
          <template #default="{ row }">{{ row.author_name || t('newsMgmt.systemAdmin') }}</template>
        </el-table-column>

        <el-table-column :label="t('newsMgmt.colPublishedAt')" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>

        <el-table-column :label="t('newsMgmt.colStatus')" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_published ? 'success' : 'info'" effect="light">
              {{ row.is_published ? t('newsMgmt.tabPublished') : t('newsMgmt.draft') }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column :label="t('newsMgmt.colActions')" width="230" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="handleEdit(row)">{{ t('news.edit') }}</el-button>
            <el-button size="small" :type="row.is_published ? 'warning' : 'success'" link @click="togglePublishStatus(row)">
              {{ row.is_published ? t('newsMgmt.unpublish') : t('newsMgmt.publishLabel') }}
            </el-button>
            <el-popconfirm :title="t('newsMgmt.deleteConfirm')" :confirm-button-text="t('news.delete')" :cancel-button-text="t('common.cancel')" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button size="small" type="danger" link>{{ t('news.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>

        <template #empty>
          <div class="table-empty">
            <i class="bi bi-inbox"></i>
            <p>{{ t('newsMgmt.empty') }}</p>
          </div>
        </template>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="pagination.currentPage"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="pagination.total"
          background
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
      </div>
    </el-card>

    <!-- 新增 / 编辑（第 33 批：与「行业动态」页的编辑弹窗统一成深绿头条 + 分段表单） -->
    <el-dialog
      v-model="dialogVisible"
      width="720px"
      top="5vh"
      :close-on-click-modal="false"
      destroy-on-close
      class="form-dialog"
    >
      <template #header>
        <div class="form-dialog-head">
          <span class="form-dialog-head-icon">
            <i :class="isEditing ? 'fas fa-pen-to-square' : 'fas fa-plus'"></i>
          </span>
          <div>
            <h3>{{ formTitle }}</h3>
            <p>{{ t('newsMgmt.dialogCreateHint') }}</p>
          </div>
        </div>
      </template>

      <div class="form-dialog-body">
        <el-form ref="newsFormRef" :model="form" :rules="rules" label-position="top">
          <!-- 基本信息 -->
          <section class="form-section">
            <div class="form-section-head">
              <i class="fas fa-circle-info"></i>
              <h4>{{ t('news.basicInfo') }}</h4>
              <span class="section-hint">{{ t('newsMgmt.basicInfoHint') }}</span>
            </div>

            <el-form-item :label="t('news.fieldTitle')" prop="title">
              <el-input
                v-model="form.title"
                maxlength="200"
                show-word-limit
                :placeholder="t('news.fieldTitlePlaceholder')"
              />
            </el-form-item>

            <el-row :gutter="16">
              <el-col :xs="24" :sm="12">
                <el-form-item :label="t('news.fieldCategory')" prop="category">
                  <el-select v-model="form.category" :placeholder="t('news.fieldCategoryPlaceholder')" style="width: 100%">
                    <el-option v-for="item in NEWS_CATEGORIES" :key="item.value" :label="t(item.labelKey)" :value="item.value" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item :label="t('news.fieldSource')">
                  <el-input v-model="form.source" maxlength="100" :placeholder="t('newsMgmt.sourcePlaceholder')" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item :label="t('news.tagLabel')">
              <el-select
                v-model="form.tags"
                multiple
                filterable
                allow-create
                default-first-option
                :reserve-keyword="false"
                :placeholder="t('newsMgmt.tagMultiPlaceholder')"
                style="width: 100%"
              />
              <p class="field-hint">{{ t('newsMgmt.tagHint') }}</p>
            </el-form-item>
          </section>

          <!-- 正文 -->
          <section class="form-section">
            <div class="form-section-head">
              <i class="fas fa-align-left"></i>
              <h4>{{ t('news.bodySection') }}</h4>
              <span class="section-hint">{{ t('newsMgmt.bodyHint') }}</span>
            </div>

            <el-form-item :label="t('news.searchByContent')" prop="content">
              <div class="editor-wrap">
                <RichTextEditor v-model="form.content" />
              </div>
            </el-form-item>
          </section>

          <!-- 封面与状态 -->
          <section class="form-section">
            <div class="form-section-head">
              <i class="fas fa-image"></i>
              <h4>{{ t('newsMgmt.coverPublish') }}</h4>
              <span class="section-hint">{{ t('news.coverHint') }}</span>
            </div>

            <el-form-item :label="t('newsMgmt.coverLabel')">
              <div class="cover-field">
                <el-upload
                  class="cover-uploader"
                  :auto-upload="false"
                  :show-file-list="false"
                  accept="image/*"
                  :on-change="handleImageChange"
                >
                  <div class="upload-tile cover-tile">
                    <img v-if="coverPreview" :src="coverPreview" :alt="t('newsMgmt.coverPreview')" />
                    <div v-else class="upload-tile-empty">
                      <i class="fas fa-cloud-arrow-up"></i>
                      <span>{{ t('newsMgmt.uploadCover') }}</span>
                      <small>{{ t('newsMgmt.coverFormatHint') }}</small>
                    </div>
                    <div v-if="coverPreview" class="upload-tile-actions">
                      <button type="button" :title="t('newsMgmt.changeCover')">
                        <i class="fas fa-rotate"></i>
                      </button>
                      <button type="button" :title="t('newsMgmt.removeCover')" @click.stop="removeCover">
                        <i class="fas fa-trash"></i>
                      </button>
                    </div>
                  </div>
                </el-upload>
              </div>
            </el-form-item>

            <el-form-item :label="t('news.publishStatus')">
              <el-radio-group v-model="form.is_published">
                <el-radio-button :value="true">{{ t('newsMgmt.publishLabel') }}</el-radio-button>
                <el-radio-button :value="false">{{ t('newsMgmt.saveDraft') }}</el-radio-button>
              </el-radio-group>
              <p class="field-hint">
                <i class="fas fa-circle-info"></i>
                {{ t('newsMgmt.draftHint') }}
              </p>
            </el-form-item>

            <!-- 第 38 批：定时发布 -->
            <el-form-item :label="t('newsMgmt.scheduledPublish')">
              <el-date-picker
                v-model="form.published_at"
                type="datetime"
                :placeholder="t('newsMgmt.scheduledHint')"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DDTHH:mm:ssZ"
                clearable
                style="width: 100%"
              />
              <p class="field-hint">
                <i class="fas fa-clock"></i>
                {{ t('newsMgmt.scheduledNote') }}
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
            <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
            <el-button type="primary" :loading="submitting" @click="submitForm">
              <i class="fas fa-check"></i> {{ t('profile.save') }}
            </el-button>
          </span>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
// 新闻管理（管理端）
// 路由：/admin/news —— 发布/编辑/删除都在本页内完成，不额外开路由。
// 面向读者的详情是另一个组件 NewsDetailView（/news/:id）。
//
// 页面由三块组成：
//   1) 统计卡（总数 / 已发布 / 草稿）—— 用 page_size=1 只取 count，见 fetchStats
//   2) 筛选栏（关键词 / 状态 / 分类）+ 新建按钮
//   3) 列表表格：编辑、切换发布状态、删除
//
// 改这个文件前值得知道的几件事：
//   · **模板顶部有一段"不要把它改回 type=primary"的说明（第 88 批）**，
//     那是按钮文字看不清踩过的坑，别绕过；
//   · 正文校验是"先用正则剥掉 HTML 标签、再数剩余长度"，因为存的是富文本 ——
//     直接数原文长度会让"只插了一张图"的空新闻通过校验；
//   · 封面 5MB 上限在后端、本页、移动端各写了一份（i18n key 名字里也带数字），
//     改动时要一起看。
import { computed, onMounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { Plus, Search } from '@element-plus/icons-vue';
import { format } from 'date-fns';
import RichTextEditor from '@/components/RichTextEditor.vue';
import {
  NEWS_CATEGORIES,
  createNews,
  deleteNews,
  fetchNewsList,
  formatNewsError,
  getNewsCategoryLabel,
  toggleNewsPublished,
  updateNews,
} from '@/api/news';
import { toAbsoluteMediaUrl } from '@/api/http';
import { useI18n } from '@/i18n';  // 第 66 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 79 批：新闻标题/来源等内容数据
import BackButton from '@/components/BackButton.vue';  // 第 87 批：返回按钮

const { t } = useI18n();
const { localizedField } = useLocalized();

// ---------- 列表 ----------
const loading = ref(false);
const newsList = ref([]);

const filters = reactive({
  keyword: '',
  category: '',
  status: '',
});

const pagination = reactive({
  currentPage: 1,
  pageSize: 10,
  total: 0,
});

// 统计小卡数据（第 28 批）
const stats = ref({ total: 0, published: 0, draft: 0 });

/**
 * 拉取统计数字：各用一次 page_size=1 的请求拿 count，
 * 失败不打扰用户（统计只是辅助信息）。
 */
const fetchStats = async () => {
  try {
    const [all, published, draft] = await Promise.all([
      fetchNewsList({ page: 1, page_size: 1 }),
      fetchNewsList({ page: 1, page_size: 1, is_published: 'true' }),
      fetchNewsList({ page: 1, page_size: 1, is_published: 'false' }),
    ]);
    stats.value = {
      total: all.count || 0,
      published: published.count || 0,
      draft: draft.count || 0,
    };
  } catch (error) {
    console.warn('获取新闻统计失败:', error);
  }
};

const buildParams = () => {
  const params = {
    page: pagination.currentPage,
    page_size: pagination.pageSize,
  };
  if (filters.keyword) {
    params.search = filters.keyword;
    params.search_type = 'all';
  }
  if (filters.category) params.category = filters.category;
  if (filters.status) params.is_published = filters.status === 'published' ? 'true' : 'false';
  return params;
};

const fetchData = async () => {
  loading.value = true;
  try {
    const data = await fetchNewsList(buildParams());
    newsList.value = data.results;
    pagination.total = data.count;
    fetchStats();
  } catch (error) {
    console.error('获取新闻列表失败:', error);
    newsList.value = [];
    pagination.total = 0;
    ElMessage.error(formatNewsError(error, t('newsMgmt.loadFailed')));
  } finally {
    loading.value = false;
  }
};

const handleSearch = () => {
  pagination.currentPage = 1;
  fetchData();
};

const resetFilters = () => {
  filters.keyword = '';
  filters.category = '';
  filters.status = '';
  handleSearch();
};

const handleSizeChange = (size) => {
  pagination.pageSize = size;
  pagination.currentPage = 1;
  fetchData();
};

const handleCurrentChange = (page) => {
  pagination.currentPage = page;
  fetchData();
};

// ---------- 表单 ----------
const dialogVisible = ref(false);
const submitting = ref(false);
const formTitle = ref(t('newsMgmt.newNews'));
// 第 33 批：弹窗头条要区分"新增/编辑"，用 form.id 判断即可
const isEditing = computed(() => Boolean(form.id));
const newsFormRef = ref(null);

const form = reactive({
  id: null,
  title: '',
  content: '',
  category: 'notice',
  source: '',
  tags: [],
  is_published: true,
  published_at: null,  // 第 38 批：定时发布（留空 = 立即发布）
});

const imageFile = ref(null);
const coverPreview = ref('');
const clearImage = ref(false);

const rules = {
  title: [
    { required: true, message: t('news.validateTitle'), trigger: 'blur' },
    { min: 5, max: 200, message: t('news.validateTitleLen200'), trigger: 'blur' },
  ],
  category: [{ required: true, message: t('news.validateCategory'), trigger: 'change' }],
  content: [
    { required: true, message: t('news.validateContent'), trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        const text = (value || '').replace(/<[^>]*>/g, '').trim();
        if (text.length < 10) {
          callback(new Error(t('newsMgmt.contentMin')));
        } else {
          callback();
        }
      },
      trigger: 'blur',
    },
  ],
};

const resetForm = () => {
  Object.assign(form, {
    id: null,
    title: '',
    content: '',
    category: 'notice',
    source: '',
    tags: [],
    is_published: true,
    published_at: null,
  });
  imageFile.value = null;
  coverPreview.value = '';
  clearImage.value = false;
  newsFormRef.value?.clearValidate();
};

const handleCreate = () => {
  formTitle.value = t('newsMgmt.newNews');
  resetForm();
  dialogVisible.value = true;
};

const handleEdit = (row) => {
  formTitle.value = t('news.edit');
  resetForm();
  Object.assign(form, {
    id: row.id,
    title: row.title || '',
    content: row.content || '',
    category: row.category || 'notice',
    source: row.source || '',
    tags: row.tags ? String(row.tags).split(',').filter(Boolean) : [],
    is_published: !!row.is_published,
    published_at: row.published_at || null,
  });
  coverPreview.value = toAbsoluteMediaUrl(row.image_url || row.image);
  dialogVisible.value = true;
};

// ---------- 封面 ----------
const handleImageChange = (uploadFile) => {
  const raw = uploadFile?.raw;
  if (!raw) return;

  if (!raw.type.startsWith('image/')) {
    ElMessage.error(t('msg.imageOnly'));
    return;
  }
  if (raw.size / 1024 / 1024 >= 5) {
    ElMessage.error(t('msg.imageTooLarge5'));
    return;
  }

  imageFile.value = raw;
  clearImage.value = false;

  const reader = new FileReader();
  reader.onload = (event) => {
    coverPreview.value = event.target.result;
  };
  reader.readAsDataURL(raw);
};

const removeCover = () => {
  imageFile.value = null;
  coverPreview.value = '';
  clearImage.value = true;
};

// ---------- 提交 / 状态 / 删除 ----------
const submitForm = async () => {
  if (!newsFormRef.value) return;

  try {
    await newsFormRef.value.validate();
  } catch {
    return;
  }

  submitting.value = true;
  try {
    const payload = {
      title: form.title.trim(),
      content: form.content,
      category: form.category,
      source: form.source.trim(),
      tags: form.tags,
      is_published: form.is_published,
      published_at: form.published_at || null,  // 第 38 批：定时发布
      clear_image: clearImage.value,
    };

    if (form.id) {
      await updateNews(form.id, payload, imageFile.value);
      ElMessage.success(t('newsMgmt.updatedOk'));
    } else {
      await createNews(payload, imageFile.value);
      ElMessage.success(t('newsMgmt.createdOk'));
    }

    dialogVisible.value = false;
    await fetchData();
  } catch (error) {
    console.error('保存新闻失败:', error);
    ElMessage.error(formatNewsError(error, t('msg.savingFailedRetry')));
  } finally {
    submitting.value = false;
  }
};

const togglePublishStatus = async (row) => {
  const nextStatus = !row.is_published;
  try {
    const updated = await toggleNewsPublished(row.id, nextStatus);
    // 以服务端返回的状态为准（而不是本地取反），避免出现
    // "界面显示已下架、库里其实仍是已发布"这种难以察觉的不一致
    const actual = typeof updated?.is_published === 'boolean' ? updated.is_published : nextStatus;
    row.is_published = actual;
    ElMessage.success(t('newsMgmt.publishToggled', { action: actual ? t('newsMgmt.publishedAction') : t('newsMgmt.unpublishedAction') }));
    // 操作后重新拉取列表，确保管理端看到的与后端完全一致
    await fetchData();
  } catch (error) {
    console.error('更新新闻状态失败:', error);
    ElMessage.error(formatNewsError(error, t('msg.operationFailedRetry')));
    await fetchData();
  }
};

const handleDelete = async (id) => {
  try {
    await deleteNews(id);
    ElMessage.success(t('msg.deleteOk'));
    // 删除最后一条时回退一页
    if (newsList.value.length === 1 && pagination.currentPage > 1) {
      pagination.currentPage -= 1;
    }
    await fetchData();
  } catch (error) {
    console.error('删除新闻失败:', error);
    ElMessage.error(formatNewsError(error, t('msg.deleteFailedRetry')));
  }
};

// ---------- 工具 ----------
const formatDate = (value) => {
  if (!value) return '-';
  try {
    return format(new Date(value), 'yyyy-MM-dd HH:mm');
  } catch {
    return value;
  }
};

onMounted(fetchData);</script>

<style scoped>
.news-management {
  --nm-primary: #2a7f53;
  --nm-primary-dark: #1f6343;
  --nm-border: #e6ece9;
  --nm-text: #22312b;
  --nm-muted: #7b8c99;

  max-width: 1400px;
  margin: 0 auto;
  /* 第 29 批：整页套 .tinted-page（浅绿工作区底），这里保留工作区自身的内边距 */
  padding: 22px 22px 34px;
  color: var(--nm-text);
}

/* 第 87 批：返回按钮紧贴左边缘，和下面的深绿页头留出间距 */
.news-management > .back-button {
  margin-bottom: 12px;
}

/* 说明（第 29 批）：页头已改用全局 .admin-hero 的深绿实底样式，
   原来这里的 .page-head 浅绿渐变已删除 —— 浅绿页头铺在浅绿工作区底上会糊成一片。 */

/* 深绿页头上的白色按钮（配合全局 .btn-on-brand，这里只保留尺寸与圆角） */
.add-btn {
  border-radius: 12px;
  padding: 20px 22px;
}

.add-btn:hover {
  transform: translateY(-1px);
}

/* 筛选栏 */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin: 18px 0;
  padding: 16px 20px;
  /* 第 28 批：纯白改成极浅的绿底渐变，和统计卡形成层次 */
  background: linear-gradient(180deg, #ffffff, #eef8f2);
  border: 1px solid var(--brand-200, #bfe3cd);
  border-radius: 16px;
  box-shadow: 0 1px 2px rgba(19, 58, 41, 0.05);
}

.filter-keyword {
  width: 280px;
}

.filter-select {
  width: 150px;
}

.filter-total {
  margin-left: auto;
  font-size: 13px;
  color: var(--nm-muted);
}

/* 表格卡片 */
.table-card {
  border-radius: 18px;
  border: 1px solid var(--brand-200, #bfe3cd);
  overflow: hidden;
  box-shadow: 0 10px 30px rgba(31, 99, 67, 0.08);
}

/* 卡片内边距交给 .panel-head / .panel-body，避免头条被 8px 内边距挤住 */
.table-card :deep(.el-card__body) {
  padding: 0;
}

/* 头条右侧的说明文字 */
.panel-hint {
  font-size: 12px;
  color: var(--ink-500);
}

.cover-cell {
  width: 84px;
  height: 56px;
  border-radius: 10px;
  overflow: hidden;
  background: #f4f8f6;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cover-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.cover-placeholder {
  color: #b6c6be;
  font-size: 18px;
}

.title-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.title-text {
  font-weight: 600;
  color: var(--nm-text);
  line-height: 1.5;
}

.title-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--nm-muted);
}

.table-empty {
  padding: 28px 0;
  color: var(--nm-muted);
  text-align: center;
}

.table-empty i {
  font-size: 26px;
  display: block;
  margin-bottom: 6px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding: 14px 0 0;
}

/* 表单（第 33 批：封面改成主题里的 .upload-tile 瓦片，
   原来的 .cover-preview / .cover-uploader-empty / .cover-tips / .dialog-footer
   已随旧弹窗结构一起删除） */
.editor-wrap {
  width: 100%;
}

.editor-wrap :deep(.ql-container) {
  min-height: 220px;
}

.cover-field {
  width: 100%;
}

.cover-uploader {
  display: block;
  width: 100%;
}

.cover-uploader :deep(.el-upload) {
  display: block;
  width: 100%;
  border: none;
  overflow: visible;
}

.cover-tile {
  width: 100%;
}

@media (max-width: 768px) {
  .filter-keyword,
  .filter-select {
    width: 100%;
  }

  .filter-total {
    margin-left: 0;
  }
}
</style>
