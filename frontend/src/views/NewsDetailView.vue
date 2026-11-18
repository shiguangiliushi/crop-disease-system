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

      <!-- 第 401 批：meta 行补阅读量 / 原文外链；关联病害 chip 单独一行 -->
      <div class="news-meta">
        <span v-if="news.source" class="news-source">
          <i class="fas fa-building-columns"></i>
          {{ t('newsDetail.source') }}{{ localizedField(news, 'source') }}
        </span>
        <span class="news-date">
          <i class="fas fa-clock"></i> {{ formatDate(news.created_at) }}
        </span>
        <span
          v-if="news.views !== undefined && news.views !== null"
          class="news-views"
        >
          <i class="fas fa-eye"></i> {{ t('forum.readsShort', { count: news.views }) }}
        </span>
        <!-- 第 401 批：原文外链（新标签页打开，rel 防反向利用） -->
        <a
          v-if="news.external_url"
          class="news-external"
          :href="news.external_url"
          target="_blank"
          rel="noopener noreferrer"
        >
          <i class="fas fa-arrow-up-right-from-square"></i> {{ t('newsDetail.externalLink') }}
        </a>
      </div>

      <!-- 第 401 批：阅读工具条 —— 复制链接 / 生成分享图 -->
      <div class="news-toolbar">
        <button type="button" class="tool-btn" @click="copyLink">
          <i class="fas fa-link"></i> {{ t('newsDetail.copyLink') }}
        </button>
        <button type="button" class="tool-btn" :disabled="sharing" @click="shareImage">
          <i :class="sharing ? 'fas fa-spinner fa-spin' : 'fas fa-image'"></i>
          {{ sharing ? t('newsDetail.shareGenerating') : t('newsDetail.shareImage') }}
        </button>
      </div>

      <!-- 第 401 批：关联病害 chip（后端 related_pest_details；点击进病害百科） -->
      <div v-if="relatedPests.length" class="news-pests">
        <span class="news-pests-label">
          <i class="fas fa-leaf"></i> {{ t('news.relatedPests') }}
        </span>
        <button
          v-for="pest in relatedPests"
          :key="pest.id"
          type="button"
          class="pest-chip"
          @click="goToPestDetail(pest)"
        >
          {{ pestChipLabel(pest) }}
        </button>
      </div>

      <div class="news-image" v-if="displayImage">
        <el-image
          :src="displayImage"
          fit="contain"
          :preview-src-list="[displayImage]"
          preview-teleported
        />
      </div>

      <!-- 第 401 批：正文目录（h2/h3）。无标题时整块不渲染 -->
      <nav v-if="toc.length" class="toc-card" :aria-label="t('newsDetail.tocTitle')">
        <div class="toc-head">
          <i class="fas fa-list-ul"></i> {{ t('newsDetail.tocTitle') }}
        </div>
        <ol class="toc-list">
          <li
            v-for="item in toc"
            :key="item.id"
            class="toc-item"
            :class="`toc-level-${item.level}`"
          >
            <button type="button" class="toc-link" @click="scrollToHeading(item.id)">
              {{ item.text }}
            </button>
          </li>
        </ol>
      </nav>

      <div class="news-content" v-html="contentHtml"></div>

      <!-- 第 401 批：上一篇 / 下一篇（后端 prev_news / next_news，可为 null） -->
      <nav v-if="prevNews || nextNews" class="news-adjacent" :aria-label="t('newsDetail.relatedTitle')">
        <button
          v-if="prevNews"
          type="button"
          class="adjacent-card"
          @click="goToNews(prevNews.id)"
        >
          <span class="adjacent-label">
            <i class="fas fa-arrow-left"></i> {{ t('newsDetail.prevNews') }}
          </span>
          <span class="adjacent-title">{{ localizedField(prevNews, 'title') }}</span>
        </button>
        <span v-else class="adjacent-spacer"></span>
        <button
          v-if="nextNews"
          type="button"
          class="adjacent-card is-next"
          @click="goToNews(nextNews.id)"
        >
          <span class="adjacent-label">
            {{ t('newsDetail.nextNews') }} <i class="fas fa-arrow-right"></i>
          </span>
          <span class="adjacent-title">{{ localizedField(nextNews, 'title') }}</span>
        </button>
      </nav>

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

    <!-- 第 401 批：相关推荐（接口失败 / 为空整块不渲染，不打扰读者） -->
    <section v-if="relatedNews.length" class="related-news">
      <h2 class="related-news-head">
        <i class="fas fa-newspaper"></i> {{ t('newsDetail.relatedTitle') }}
      </h2>
      <div class="related-news-grid">
        <article
          v-for="item in relatedNews"
          :key="item.id"
          class="related-news-card"
          @click="goToNews(item.id)"
        >
          <span v-if="item.category" class="related-news-cat">{{ getCategoryLabel(item.category) }}</span>
          <h3 class="related-news-title">{{ localizedField(item, 'title') }}</h3>
          <span class="related-news-date">
            <i class="fas fa-clock"></i> {{ formatDate(item.created_at) }}
          </span>
        </article>
      </div>
    </section>

    <!-- 第 401 批：返回顶部（滚动超过 400px 出现；监听在 onUnmounted 里移除） -->
    <button
      v-if="showBackTop"
      type="button"
      class="back-top"
      :aria-label="t('newsDetail.backToTop')"
      :title="t('newsDetail.backToTop')"
      @click="backToTop"
    >
      <i class="fas fa-arrow-up"></i>
    </button>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { goBackOr } from '@/utils/navigation';  // 第 165 批：返回兜底
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import api from '@/api';
import { fetchNewsRelated, getNewsCategoryLabel } from '@/api/news';  // 第 401 批：相关推荐 / 分类文案
import { toAbsoluteMediaUrl } from '@/api/http';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';  // 第 68 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 72 批：新闻正文多语言
import { sanitizeRichText } from '@/utils/richText';  // 第 91 批：正文净化（纵深防御）
import { extractToc, injectHeadingIds, stripHtmlText } from '@/utils/newsContent';  // 第 401 批：目录
import { buildNewsShareCard, downloadNewsShareCard } from '@/utils/newsShareCard';  // 第 401 批：分享图

const { t, locale } = useI18n();
const { localizedField } = useLocalized();

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const news = ref(null);
const loading = ref(true);
const deleting = ref(false);
// 第 401 批：分享图生成中（禁用按钮，避免连点生成多张）
const sharing = ref(false);
// 第 401 批：底部相关推荐
const relatedNews = ref([]);
// 第 401 批：返回顶部按钮是否可见（滚动超过 400px）
const showBackTop = ref(false);

// 检查是否是管理员
// 第 17 批：改用 store 的统一口径。原实现只认 role（且把后端从未授权的
// EDITOR 也算作管理员），而登录响应此前根本不返回 role —— 于是**连真正的
// 管理员也看不到编辑/删除按钮**；现在 role 已随登录返回，这里再对齐后端
// `IsAdminOrReadOnly` 的判定（is_staff / is_superuser / role=ADMIN）。
const isAdmin = computed(() => Boolean(authStore.isAdmin));

// 第 401 批：关联病害（轻量条目，可能缺失 → 空数组、不渲染）
const relatedPests = computed(() => (Array.isArray(news.value?.related_pest_details) ? news.value.related_pest_details : []));

// 第 401 批：上一篇 / 下一篇（后端返回 {id,title,title_en} 或 null）
const prevNews = computed(() => news.value?.prev_news || null);
const nextNews = computed(() => news.value?.next_news || null);

// 第 401 批：封面显示地址（优先 image_url；老接口只有 image）
const displayImage = computed(() => toAbsoluteMediaUrl(news.value?.image_url || news.value?.image || ''));

// 获取新闻详情
const fetchNewsDetail = async () => {
  // 第 401 批：记住本次请求对应的新闻 id。快速连点"下一篇/相关推荐"时，
  // 旧请求可能后返回，若不加判断会把上一篇的内容盖到新页面上。
  const requestedId = route.params.id;
  const isStillCurrent = () => String(route.params.id) === String(requestedId);
  try {
    loading.value = true;
    const response = await api.get(`/news/${requestedId}/`);
    if (!isStillCurrent()) return;
    news.value = response.data;
    // 第 401 批：详情拿到后再拉相关推荐（推荐失败不影响正文）
    loadRelatedNews();
  } catch (error) {
    if (!isStillCurrent()) return;
    console.error('获取新闻详情失败:', error);
    news.value = null;
    relatedNews.value = [];
    // 404 表示"不存在"或"已被管理员下架"（后端对非管理员不可见），
    // 与真正的服务异常区分开，避免用户把已下架当成"系统坏了"
    const status = error?.response?.status;
    ElMessage.error(status === 404 ? t('newsDetail.notFound') : t('newsDetail.loadFailed'));
  } finally {
    // 只有仍是当前新闻的请求才有权收掉 loading（否则新请求会被旧请求提前结束）
    if (isStillCurrent()) loading.value = false;
  }
};

/**
 * 第 401 批：底部相关推荐
 * 单独 catch：后端接口未上线 / 返回为空都按"没有推荐"处理，页面不报错也不打扰。
 * 过滤掉当前这条（后端理论上不会返回自己，但前端兜一层更稳，避免推荐区自指）。
 */
const loadRelatedNews = async () => {
  const requestedId = route.params.id;
  if (!requestedId) {
    relatedNews.value = [];
    return;
  }
  try {
    const data = await fetchNewsRelated(requestedId, { limit: 4 });
    // 请求期间又切了新闻：旧推荐直接丢弃
    if (String(route.params.id) !== String(requestedId)) return;
    relatedNews.value = (Array.isArray(data.results) ? data.results : [])
      .filter((item) => String(item?.id) !== String(requestedId));
  } catch (error) {
    console.warn('获取相关推荐失败（不渲染该区块）:', error);
    if (String(route.params.id) === String(requestedId)) {
      relatedNews.value = [];
    }
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

/**
 * 第 401 批：把正文 HTML 交给 v-html 前**先注入标题 id**（目录锚点）
 * ------------------------------------------------------------------
 * 顺序固定：sanitizeRichText（净化，白名单里保留 id）→ injectHeadingIds（补 id）→
 * 换行转 <br>。注入的 id（news-h-1…）与 extractToc 的编号规则一致，
 * 因此目录里的 id 一定能在正文里找到对应标题。
 */
const formatContent = (content) => {
  if (!content) return '';
  return injectHeadingIds(sanitizeRichText(content)).replace(/\n/g, '<br>');
};

// 第 401 批：正文（注入 id 后）与目录；正文无 h2/h3 时 toc 为 []
const contentHtml = computed(() => formatContent(localizedField(news.value, 'content')));
const toc = computed(() => extractToc(contentHtml.value));

// 第 401 批：分享图摘要（优先后端 summary，没有就截正文纯文本）
const SHARE_SUMMARY_MAX = 180;
const shareSummary = computed(() => {
  if (!news.value) return '';
  const provided = String(localizedField(news.value, 'summary') || '').trim();
  const text = provided || stripHtmlText(localizedField(news.value, 'content'));
  return text.length > SHARE_SUMMARY_MAX ? `${text.slice(0, SHARE_SUMMARY_MAX)}...` : text;
});

/**
 * 第 401 批：分享图封面必须走**同源**地址
 * ------------------------------------------------------------------
 * 后端序列化给的 image_url 是绝对地址（开发环境是 http://127.0.0.1:8000/media/…），
 * 而页面在 5173 —— 把跨源图片画进 canvas 会污染画布，`toBlob()` 直接抛 SecurityError，
 * 整张分享图就生成失败。vite 已把 `/media` 代理到后端，所以这里把
 * "本机后端绝对地址"归一成相对路径，拿到同源副本；无法归一的（外站图片）返回 ''，
 * 分享图留白也不让生成失败。
 */
const getFullImageUrl = (url) => {
  if (!url || typeof url !== 'string') return '';
  if (typeof window === 'undefined') return '';
  if (url.startsWith('data:image/') || url.startsWith('blob:')) return url;
  const raw = /^https?:\/\//i.test(url) || url.startsWith('/') ? url : `/${url}`;
  try {
    const parsed = new URL(raw, window.location.href);
    if (parsed.origin === window.location.origin) {
      return `${parsed.pathname}${parsed.search}`;
    }
    // 指向后端媒体目录的绝对地址：改用同源的 /media 代理路径
    if (parsed.pathname.startsWith('/media/')) {
      return `${parsed.pathname}${parsed.search}`;
    }
    return '';
  } catch {
    return '';
  }
};
const shareCoverUrl = computed(() => getFullImageUrl(news.value?.image_url || news.value?.image || ''));

/** 第 401 批：目录点击 → 平滑滚动到对应标题 */
const scrollToHeading = (id) => {
  if (typeof document === 'undefined') return;
  const target = document.getElementById(id);
  if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

// 第 401 批：分类角标文案（复用列表页同一份分类表，英文界面不显示中文）
const getCategoryLabel = (value) => getNewsCategoryLabel(value, t);

/** 第 401 批：关联病害 chip 文案（名称缺失时退回英文标识符，不渲染空 chip） */
const pestChipLabel = (pest) => localizedField(pest, 'name') || pest?.english_identifier || '';

/** 第 401 批：跳病害百科详情 */
const goToPestDetail = (pest) => {
  const identifier = pest?.english_identifier;
  if (!identifier) return;
  router.push({ name: 'PestDetail', params: { english_identifier: identifier } });
};

/** 第 401 批：跳新闻详情（上一篇/下一篇/相关推荐共用；同组件复用由 watch 重新拉数据） */
const goToNews = (id) => {
  if (!id) return;
  router.push({ name: 'news-detail', params: { id } });
};

/**
 * 第 401 批：复制当前页链接
 * ------------------------------------------------------------------
 * 优先 Clipboard API（https / localhost 可用）；非安全上下文（局域网 http）下
 * `navigator.clipboard` 是 undefined，回退到 `document.execCommand('copy')` 的
 * 隐藏 textarea 方案；两步都失败才提示用户手动复制地址栏。
 */
const fallbackCopy = (text) => {
  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.top = '-9999px';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    const copied = typeof document.execCommand === 'function' && document.execCommand('copy');
    document.body.removeChild(textarea);
    return Boolean(copied);
  } catch (error) {
    console.warn('复制链接回退方案失败:', error);
    return false;
  }
};

const copyLink = async () => {
  const url = window.location.href;
  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      await navigator.clipboard.writeText(url);
      ElMessage.success(t('newsDetail.copied'));
      return;
    }
  } catch (error) {
    // 权限被拒 / 非安全上下文：继续走 execCommand 回退，不让用户看到半截提示
    console.warn('Clipboard API 复制失败，回退 execCommand:', error);
  }
  if (fallbackCopy(url)) {
    ElMessage.success(t('newsDetail.copied'));
  } else {
    ElMessage.warning(t('newsDetail.copyFailed'));
  }
};

/** 第 401 批：生成并下载分享图（失败只提示，不影响阅读） */
const shareImage = async () => {
  if (!news.value) return;
  sharing.value = true;
  try {
    const blob = await buildNewsShareCard({
      title: String(localizedField(news.value, 'title') || '').trim(),
      summary: shareSummary.value,
      source: String(localizedField(news.value, 'source') || '').trim(),
      dateText: formatDate(news.value.created_at),
      coverUrl: shareCoverUrl.value,
      brandName: t('auth.brandName'),
      footer: t('newsDetail.shareFooter'),
    });
    const downloaded = downloadNewsShareCard(blob, `news-${news.value.id || route.params.id}.png`);
    if (downloaded) {
      ElMessage.success(t('newsDetail.shareSaved'));
    } else {
      ElMessage.error(t('newsDetail.shareFailed'));
    }
  } catch (error) {
    console.error('生成分享图失败:', error);
    ElMessage.error(t('newsDetail.shareFailed'));
  } finally {
    sharing.value = false;
  }
};

/** 第 401 批：返回顶部（平滑滚动） */
const backToTop = () => {
  if (typeof window === 'undefined') return;
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

/** 第 401 批：滚动监听 —— 只有超过 400px 才出现返回顶部按钮，避免首屏多余悬浮物 */
const handleScroll = () => {
  if (typeof window === 'undefined') return;
  const top = window.scrollY || document.documentElement?.scrollTop || 0;
  showBackTop.value = top > 400;
};

// 返回上一页
const goBack = () => {
  if (window.history.length > 1) {
    // 第 165 批：没有上一页时兜底回新闻列表
      goBackOr('/news');
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

// 组件挂载时获取数据 + 注册滚动监听（第 401 批：返回顶部）
onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll();
  }
  if (route.params.id) {
    fetchNewsDetail();
  }
});

// 第 401 批：卸载时移除 scroll 监听 —— 不能留在全局，否则页面反复进出会叠加监听器
onUnmounted(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('scroll', handleScroll);
  }
});

/**
 * 第 401 批：同组件内切换新闻（上一篇/下一篇/相关推荐都是 /news/:id → /news/:id）
 * ------------------------------------------------------------------
 * Vue Router 会复用同一个组件实例，**不会**重新触发 onMounted；
 * 不监听 id 的话，点"下一篇"后正文还是上一篇的内容。
 */
watch(() => route.params.id, (newId, oldId) => {
  if (!newId || String(newId) === String(oldId)) return;
  news.value = null;
  relatedNews.value = [];
  loading.value = true;
  if (typeof window !== 'undefined') {
    window.scrollTo({ top: 0, behavior: 'auto' });
  }
  fetchNewsDetail();
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
  text-align: left;
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
  text-align: left;
}

.news-date,
.news-source,
.news-views {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.news-date i,
.news-source i,
.news-views i {
  color: var(--brand-500);
}

/* 第 401 批：原文外链（与卡片上的样式同一套观感） */
.news-external {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--brand-700);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  border-bottom: 1px dashed transparent;
  transition: color var(--dur) var(--ease), border-color var(--dur) var(--ease);
}

.news-external:hover {
  color: var(--brand-500);
  border-bottom-color: var(--brand-300);
}

/* ---- 第 401 批：阅读工具条 ---- */
.news-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 0 0 18px;
}

.tool-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 16px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-pill);
  background: var(--surface);
  color: var(--ink-600);
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: color var(--dur) var(--ease), border-color var(--dur) var(--ease),
    background var(--dur) var(--ease);
}

.tool-btn:hover {
  border-color: var(--brand-400);
  background: var(--brand-50);
  color: var(--brand-700);
}

.tool-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

/* ---- 第 401 批：关联病害 chip ---- */
.news-pests {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 0 0 20px;
}

.news-pests-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-500);
}

.pest-chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 4px 12px;
  border: 1px solid var(--brand-200);
  border-radius: var(--radius-pill);
  background: var(--brand-50);
  color: var(--brand-700);
  font-family: inherit;
  font-size: 12.5px;
  line-height: 18px;
  cursor: pointer;
  transition: border-color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.pest-chip:hover {
  border-color: var(--brand-400);
  background: var(--brand-100);
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

/* ---- 第 401 批：正文目录（桌面为纵向列表，<=768px 变成置顶横向滚动条） ---- */
.toc-card {
  margin: 0 0 24px;
  padding: 16px 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-muted);
  min-width: 0;
}

.toc-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 700;
  color: var(--brand-700);
}

.toc-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
  min-width: 0;
}

.toc-item {
  margin: 0;
  min-width: 0;
}

.toc-level-3 {
  padding-left: 18px;
}

.toc-link {
  display: block;
  width: 100%;
  padding: 5px 8px;
  border: none;
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--ink-600);
  font-family: inherit;
  font-size: 13.5px;
  line-height: 1.6;
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.toc-level-3 .toc-link {
  font-size: 13px;
  color: var(--ink-500);
}

.toc-link:hover,
.toc-link:focus-visible {
  outline: none;
  color: var(--brand-700);
  background: var(--brand-50);
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

/* 目录锚点要避开吸顶导航（滚动后标题不要贴在视口最上沿） */
.news-content :deep(h2),
.news-content :deep(h3) {
  scroll-margin-top: 90px;
}

.news-content :deep(h2) {
  margin: 30px 0 14px;
  font-size: 21px;
  font-weight: 700;
  line-height: 1.5;
  color: var(--ink-900);
}

.news-content :deep(h3) {
  margin: 24px 0 12px;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.5;
  color: var(--ink-800);
}

/* ---- 第 401 批：上一篇 / 下一篇 ---- */
.news-adjacent {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 30px;
  padding-top: 22px;
  border-top: 1px solid var(--border);
}

.adjacent-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-muted);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.adjacent-card:hover {
  border-color: var(--brand-300);
  background: var(--brand-50);
}

.adjacent-card.is-next {
  align-items: flex-end;
  text-align: right;
}

.adjacent-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--brand-700);
}

.adjacent-title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--ink-800);
}

.adjacent-spacer {
  display: block;
}

/* ---- 第 401 批：相关推荐 ---- */
.related-news {
  margin-top: 30px;
}

.related-news-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 14px;
  font-size: 20px;
  font-weight: 800;
  color: var(--ink-900);
}

.related-news-head i {
  color: var(--brand-500);
}

.related-news-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.related-news-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  padding: 18px 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease),
    border-color var(--dur) var(--ease);
}

.related-news-card:hover {
  transform: translateY(-3px);
  border-color: var(--brand-200);
  box-shadow: var(--shadow-md);
}

.related-news-cat {
  align-self: flex-start;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: var(--brand-50);
  color: var(--brand-700);
  font-size: 12px;
  font-weight: 600;
}

.related-news-title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin: 0;
  font-size: 15.5px;
  font-weight: 700;
  line-height: 1.5;
  color: var(--ink-800);
}

.related-news-date {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: auto;
  font-size: 12.5px;
  color: var(--ink-400);
}

.news-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
}

/* ---- 第 401 批：返回顶部悬浮按钮 ---- */
.back-top {
  position: fixed;
  right: 28px;
  bottom: 36px;
  z-index: 30;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 46px;
  border: none;
  border-radius: 50%;
  background: var(--gradient-brand);
  color: #fff;
  font-size: 18px;
  cursor: pointer;
  box-shadow: 0 10px 24px rgba(31, 99, 67, 0.28);
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.back-top:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 28px rgba(31, 99, 67, 0.34);
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
    padding: 0 16px 88px; /* 第 401 批：给右下角「返回顶部」留出空间，不遮挡末段内容 */
  }

  .news-detail {
    padding: 22px 18px;
  }

  .news-title {
    font-size: 21px;
  }

  /* 第 401 批：目录在手机上收成横向滚动条 —— 不能换行撑高，也不能撑破页面 */
  .toc-card {
    padding: 12px 14px;
  }

  .toc-list {
    flex-direction: row;
    flex-wrap: nowrap;
    gap: 6px;
    max-width: 100%;
    overflow-x: auto;
    padding-bottom: 4px;
    -webkit-overflow-scrolling: touch;
  }

  .toc-item {
    flex: 0 0 auto;
  }

  .toc-level-3 {
    padding-left: 0;
  }

  .toc-link {
    width: auto;
    padding: 5px 12px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-pill);
    background: var(--surface);
    font-size: 12.5px;
  }

  .related-news-grid {
    grid-template-columns: 1fr;
  }

  .back-top {
    right: 16px;
    bottom: 20px;
    width: 42px;
    height: 42px;
    font-size: 16px;
  }
}

@media (max-width: 600px) {
  .news-adjacent {
    grid-template-columns: 1fr;
  }

  .adjacent-card.is-next {
    align-items: flex-start;
    text-align: left;
  }
}

@media (max-width: 480px) {
  .news-title {
    font-size: 19px;
  }

  .tool-btn {
    flex: 1 1 auto;
    justify-content: center;
  }
}
</style>
