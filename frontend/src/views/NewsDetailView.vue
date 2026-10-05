<template>
  <div class="news-detail-container">
    <!-- 返回按钮（第 81 批：去掉 type="primary" —— 全局主题会把 primary 按钮
         涂成深绿渐变，与本页的浅色胶囊样式冲突，导致"深绿底 + 灰字"看不清） -->
    <el-button 
      icon="ArrowLeft" 
      @click="goBack" 
      class="back-button"
    >
      {{ t('pestDetail.backToList') }}
    </el-button>

    <div class="news-detail" v-if="news">
      <h1 class="news-title">{{ localizedField(news, 'title') }}</h1>
      
      <div class="news-meta">
        <span v-if="news.source" class="news-source">{{ t('newsDetail.source') }}{{ localizedField(news, 'source') }}</span>
        <span class="news-date">{{ formatDate(news.created_at) }}</span>
      </div>

      <div class="news-image" v-if="news.image">
        <el-image 
          :src="news.image" 
          fit="contain"
          :preview-src-list="[news.image]"
          preview-teleported
        />
      </div>

      <div class="news-content" v-html="formatContent(localizedField(news, 'content'))"></div>

      <div class="news-actions" v-if="isAdmin">
        <el-button 
          type="primary" 
          @click="editNews"
          v-if="isAdmin"
        >
          {{ t('news.edit') }}
        </el-button>
        <el-button 
          type="danger" 
          @click="confirmDelete"
          :loading="deleting"
          v-if="isAdmin"
        >
          {{ t('news.delete') }}
        </el-button>
      </div>
    </div>

    <div class="loading-container" v-else-if="loading">
      <el-skeleton :rows="10" animated />
    </div>

    <div class="not-found" v-else>
      <el-empty :description="t('newsDetail.missing')" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import api from '@/api';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';  // 第 68 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 72 批：新闻正文多语言
import { sanitizeRichText } from '@/utils/richText';  // 第 91 批：正文净化（纵深防御）

const { t, locale } = useI18n();
const { localizedField } = useLocalized();

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const news = ref(null);
const loading = ref(true);
const deleting = ref(false);

// 检查是否是管理员
// 第 17 批：改用 store 的统一口径。原实现只认 role（且把后端从未授权的
// EDITOR 也算作管理员），而登录响应此前根本不返回 role —— 于是**连真正的
// 管理员也看不到编辑/删除按钮**；现在 role 已随登录返回，这里再对齐后端
// `IsAdminOrReadOnly` 的判定（is_staff / is_superuser / role=ADMIN）。
const isAdmin = computed(() => Boolean(authStore.isAdmin));

// 获取新闻详情
const fetchNewsDetail = async () => {
  try {
    loading.value = true;
    const response = await api.get(`/news/${route.params.id}/`);
    news.value = response.data;
  } catch (error) {
    console.error('获取新闻详情失败:', error);
    // 404 表示"不存在"或"已被管理员下架"（后端对非管理员不可见），
    // 与真正的服务异常区分开，避免用户把已下架当成"系统坏了"
    const status = error?.response?.status;
    ElMessage.error(status === 404 ? t('newsDetail.notFound') : t('newsDetail.loadFailed'));
  } finally {
    loading.value = false;
  }
};

// 格式化日期（跟随当前语言，避免英文界面下仍显示中文日期格式）
const formatDate = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleString(locale.value === 'en' ? 'en-US' : 'zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
};

// 格式化内容（处理换行等）
//
// 第 91 批（安全）：新闻正文同样是 `v-html`（模板第 30 行）。只写新闻的是管理员，
// 风险等级低于论坛（那里任何登录用户都能发），但富文本编辑器是**允许写 HTML** 的，
// 且正文可能带上外部复制来的标签 —— 所以同样过一遍净化，成本为零。
const formatContent = (content) => {
  if (!content) return '';
  return sanitizeRichText(content).replace(/\n/g, '<br>');
};

// 返回上一页
const goBack = () => {
  if (window.history.length > 1) {
    router.go(-1);
  } else {
    router.push('/news');
  }
};

// 编辑新闻
const editNews = () => {
  router.push(`/news/${route.params.id}/edit`);
};

// 删除新闻
const confirmDelete = () => {
  ElMessageBox.confirm(t('newsDetail.deleteConfirm'), t('newsDetail.deleteTitle'), {
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel'),
    type: 'warning'
  }).then(async () => {
    try {
      deleting.value = true;
      await api.delete(`/news/${route.params.id}/`);
      ElMessage.success(t('newsDetail.deleteOk'));
      router.push('/news');
    } catch (error) {
      console.error('删除新闻失败:', error);
      ElMessage.error(t('newsDetail.deleteFailed'));
    } finally {
      deleting.value = false;
    }
  }).catch(() => {});
};

// 组件挂载时获取数据
onMounted(() => {
  if (route.params.id) {
    fetchNewsDetail();
  }
});
</script>

<style scoped>
.news-detail-container {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
}

.back-button {
  margin-bottom: 20px;
}

.news-detail {
  background: #fff;
  border-radius: 8px;
  padding: 30px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.news-title {
  font-size: 28px;
  color: #303133;
  margin-bottom: 20px;
  text-align: center;
}

.news-meta {
  text-align: center;
  color: #909399;
  margin-bottom: 30px;
  font-size: 14px;
}

.news-source {
  margin-right: 15px;
}

.news-image {
  margin-bottom: 30px;
  text-align: center;
}

.news-image img {
  max-width: 100%;
  border-radius: 4px;
}

.news-content {
  line-height: 1.8;
  color: #606266;
  font-size: 16px;
  margin-bottom: 30px;
}

.news-actions {
  margin-top: 40px;
  text-align: center;
  padding-top: 20px;
  border-top: 1px solid #ebeef5;
}

.loading-container {
  padding: 30px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.not-found {
  text-align: center;
  padding: 50px 0;
}

/* ================= 现代化覆写（设计变量见 assets/theme.css） ================= */
.news-detail-container {
  width: 100%;
  max-width: 900px;
  margin: 0 auto;
  padding: 8px 24px 48px;
  box-sizing: border-box;
}

.news-detail {
  padding: 36px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background: var(--surface);
  box-shadow: var(--shadow-md);
}

.news-title {
  margin: 0 0 16px;
  font-size: 28px;
  font-weight: 800;
  line-height: 1.45;
  letter-spacing: 0.3px;
  color: var(--ink-900);
}

.news-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
  padding-bottom: 18px;
  margin-bottom: 22px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  color: var(--ink-400);
}

.news-date,
.news-source {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.news-date i,
.news-source i {
  color: var(--brand-500);
}

.news-image {
  margin-bottom: 22px;
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--border);
}

.news-image img {
  display: block;
  width: 100%;
  height: auto;
}

.news-content {
  font-size: 15.5px;
  line-height: 2;
  color: var(--ink-700);
  word-break: break-word;
}

.news-content :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: var(--radius);
}

.news-content :deep(p) {
  margin-bottom: 16px;
}

.news-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
}

/* 第 81 批修复：返回按钮"文字看不清"
   ------------------------------------------------------------------
   现象（浏览器实测 computed 值）：按钮底色是**深绿渐变**
   `linear-gradient(135deg, #3d9a68, #1f6343)`，文字却是 `--ink-600`（#566b60）——
   对比度约 1.6:1，几乎读不出来。

   根因：模板上写了 `type="primary"`，而全局 theme.css（在 Element Plus 之后引入）
   有一条 `.el-button--primary:not(.is-link):not(.is-text):not(.is-plain):not(.is-disabled)`
   把背景强制设成 --gradient-brand。这条规则与本文件 scoped 的 `.back-button[data-v-x]`
   优先级同为 (0,2,0)，靠源码顺序取胜 —— 背景被全局规则拿走了，文字色却留在本文件，
   于是"深绿底 + 灰字"。

   修法：**去掉模板上的 type="primary"**，那条全局规则就不再命中这个按钮了；
   返回按钮本来也不是页面主操作，用中性胶囊样式更合适。这样不必和全局主题
   比优先级，也不用 !important。同时在下面的规则里显式覆盖 Element Plus 的按钮
   变量（它的文字色取自 --el-button-text-color，只写 color 会被顶掉，
   参见 theme.css 中 .btn-on-brand 的同类注释）。 */
.back-button {
  --el-button-text-color: var(--ink-700);
  --el-button-hover-text-color: var(--brand-700);
  --el-button-active-text-color: var(--brand-800);
  --el-button-bg-color: var(--surface);
  --el-button-hover-bg-color: var(--brand-50);
  --el-button-active-bg-color: var(--brand-100);
  --el-button-border-color: var(--border-strong);
  --el-button-hover-border-color: var(--brand-400);
  --el-button-active-border-color: var(--brand-500);

  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 20px;
  padding: 9px 20px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-pill);
  background: var(--surface);
  color: var(--ink-700);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: none;
  transition: all var(--dur) var(--ease);
}

.back-button:hover,
.back-button:focus-visible {
  border-color: var(--brand-400);
  background: var(--brand-50);
  color: var(--brand-700);
  box-shadow: var(--shadow-xs);
}

.loading-container,
.not-found {
  padding: 64px 24px;
  text-align: center;
  color: var(--ink-400);
  font-size: 15px;
}

@media (max-width: 768px) {
  .news-detail-container {
    padding: 0 16px 32px;
  }

  .news-detail {
    padding: 22px 18px;
  }

  .news-title {
    font-size: 21px;
  }
}
</style>
