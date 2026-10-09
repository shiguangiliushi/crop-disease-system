<template>
  <div class="admin-feedback tinted-page">
    <!-- 第 117 批：原来的「返回」按钮已移除（本页现在在管理后台外壳里，左侧栏就是导航） -->

    <!-- 页头（第 29 批：全局 .admin-hero 已升级为深绿实底 + 白色文字） -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-comment-dots"></i></span>
        <div>
          <h1>{{ t('feedbackAdmin.title') }}</h1>
          <p>
            {{ t('feedbackAdmin.subtitle') }}
          </p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-button plain :loading="loading" @click="loadList">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
      </div>
    </header>

    <!-- 筛选 -->
    <div class="filter-bar">
      <!-- 第 88 批：清空下拉也要重查（el-select 的清除不发 change，只发 clear） -->
      <el-select v-model="filters.status" :placeholder="t('feedbackAdmin.statusFilter')" clearable style="width: 140px" @change="handleFilter" @clear="handleFilter">
        <el-option :label="t('feedbackAdmin.statusPending')" value="pending" />
        <el-option :label="t('feedbackAdmin.statusProcessing')" value="processing" />
        <el-option :label="t('feedbackAdmin.statusResolved')" value="resolved" />
      </el-select>
      <el-select v-model="filters.category" :placeholder="t('feedbackAdmin.categoryFilter')" clearable style="width: 150px" @change="handleFilter" @clear="handleFilter">
        <el-option :label="t('feedbackAdmin.catSuggestion')" value="suggestion" />
        <el-option :label="t('feedbackAdmin.catBug')" value="bug" />
        <el-option :label="t('feedbackAdmin.catRecognition')" value="recognition" />
        <el-option :label="t('feedbackAdmin.catOther')" value="other" />
      </el-select>
      <el-input
        v-model="filters.search"
        :placeholder="t('feedbackAdmin.searchPlaceholder')"
        clearable
        style="width: 260px"
        @clear="handleFilter"
        @keyup.enter="handleFilter"
      >
        <template #prefix><i class="fas fa-search"></i></template>
        <template #append>
          <el-button @click="handleFilter"><i class="fas fa-search"></i></el-button>
        </template>
      </el-input>
      <span class="total-hint">{{ t('feedbackAdmin.totalHint', { count: total }) }}</span>
    </div>

    <!-- 状态统计（第 28 批：原来整页只有裸标题 + 白卡片，观感"太白"） -->
    <div class="admin-stats">
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-inbox"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.total }}</div>
          <div class="stat-tile-label">{{ t('feedbackAdmin.statTotal') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--pending">
        <span class="stat-tile-icon"><i class="fas fa-hourglass-half"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.pending }}</div>
          <div class="stat-tile-label">{{ t('feedbackAdmin.statusPending') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--processing">
        <span class="stat-tile-icon"><i class="fas fa-spinner"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.processing }}</div>
          <div class="stat-tile-label">{{ t('feedbackAdmin.statusProcessing') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--ok">
        <span class="stat-tile-icon"><i class="fas fa-circle-check"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.resolved }}</div>
          <div class="stat-tile-label">{{ t('feedbackAdmin.statusResolved') }}</div>
        </div>
      </div>
    </div>

    <!-- 列表头条（第 29 批：原来列表直接铺在白底上，加一条着色头条 + 状态图例）
         各条反馈本身是独立卡片，所以这里只放一条"头条"，不再套一层白卡片外壳 -->
    <div class="panel-head list-panel-head">
      <span class="panel-icon"><i class="fas fa-comments"></i></span>
      <h3 class="panel-title">{{ t('feedbackAdmin.listTitle') }}</h3>
      <span class="panel-count">{{ t('feedbackAdmin.totalCount', { count: total }) }}</span>
      <div class="panel-head-right">
        <span class="legend"><i class="legend-dot is-pending"></i>{{ t('feedbackAdmin.statusPending') }}</span>
        <span class="legend"><i class="legend-dot is-processing"></i>{{ t('feedbackAdmin.statusProcessing') }}</span>
        <span class="legend"><i class="legend-dot is-resolved"></i>{{ t('feedbackAdmin.statusResolved') }}</span>
      </div>
    </div>

    <el-skeleton v-if="loading" :rows="6" animated />
    <el-empty v-else-if="items.length === 0" :description="t('feedbackAdmin.empty')" />

    <div v-else class="feedback-list">
      <div
        v-for="item in items"
        :key="item.id"
        class="feedback-item"
        :class="`is-${item.status}`"
      >
        <div class="item-head">
          <!-- 提交人：这就是管理员要看的"用户名字" -->
          <span class="submitter">
            <i class="fas fa-user"></i>
            {{ item.user || t('feedbackAdmin.unknownUser') }}
          </span>
          <el-tag size="small" :type="categoryTagType(item.category)">{{ categoryLabel(item.category) }}</el-tag>
          <el-tag size="small" :type="statusTagType(item.status)" effect="light">{{ statusLabel(item.status) }}</el-tag>
          <span class="item-time">{{ formatTime(item.timestamp) }}</span>
          <div class="item-actions">
            <el-button size="small" type="primary" plain @click="openReply(item)">
              <i class="fas fa-reply"></i> {{ item.admin_reply ? t('feedbackAdmin.editReply') : t('feedbackAdmin.replyAction') }}
            </el-button>
            <!--
              第 126 批：删除只给**全权管理员**。
              产品口径：信息编辑员可以看、可以回复，但"删别人的反馈"是不可逆动作，
              不给编辑员（后端 FeedbackView.destroy 也有同一道守卫，见 views.py）。
              前端隐藏只是不画这个按钮；接口那边是 403。
            -->
            <el-button
              v-if="canDeleteOthers"
              size="small"
              text
              type="danger"
              :loading="deletingId === item.id"
              @click="removeItem(item)"
            >
              <i class="fas fa-trash"></i> {{ t('feedbackAdmin.delete') }}
            </el-button>
          </div>
        </div>

        <p class="item-content">{{ localizedField(item, 'suggestion') || t('feedbackAdmin.noText') }}</p>

        <div v-if="item.image_url" class="item-image">
          <el-image
            :src="item.image_url"
            :preview-src-list="[item.image_url]"
            fit="cover"
            preview-teleported
          />
        </div>

        <div v-if="item.disease_name || item.is_correct !== null" class="item-context">
          <i class="fas fa-microscope"></i>
          <!-- 第 79 批：病害名是提交时的中文快照，后端按名字回查百科给出英文名 -->
          <template v-if="item.disease_name">{{ t('feedbackAdmin.detectResult', { name: localizedField(item, 'disease_name') }) }}</template>
          <template v-if="item.confidence !== null && item.confidence !== undefined">
            · {{ t('feedbackAdmin.confidence', { value: (item.confidence * 100).toFixed(1) }) }}
          </template>
          <template v-if="item.is_correct !== null && item.is_correct !== undefined">
            · {{ t('feedbackAdmin.userSays', { verdict: item.is_correct ? t('feedbackAdmin.correct') : t('feedbackAdmin.incorrect') }) }}
          </template>
        </div>

        <div v-if="item.admin_reply" class="item-reply">
          <strong><i class="fas fa-reply-all"></i> {{ t('feedbackAdmin.adminReply') }}</strong>
          <p>{{ localizedField(item, 'admin_reply') }}</p>
          <span v-if="item.handled_at" class="reply-time">{{ t('feedbackAdmin.handledAt', { time: formatTime(item.handled_at) }) }}</span>
        </div>
      </div>
    </div>

    <!-- 分页（第 89 批：原来是"加载更多"按钮 —— 反馈一多就得一直往下拉，
         拉到第 30 条之后想回到前面只能重新往下拉。改成真分页：
         可以跳页、可以改每页条数，删掉当前页最后一条会自动退到上一页。 -->
    <div v-if="total > 0" class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next, jumper"
        :total="total"
        background
        @size-change="handleSizeChange"
        @current-change="loadList"
      />
    </div>

    <!-- 回复 / 处理 -->
    <el-dialog v-model="replyVisible" :title="t('feedbackAdmin.replyTitle')" width="520px" :close-on-click-modal="false">
      <el-form label-width="80px" @submit.prevent>
        <el-form-item :label="t('feedbackAdmin.submitter')">
          <el-input :model-value="current?.user || t('feedbackAdmin.unknownUser')" disabled />
        </el-form-item>
        <el-form-item :label="t('feedbackAdmin.originalContent')">
          <el-input :model-value="localizedField(current, 'suggestion') || t('feedbackAdmin.noText')" type="textarea" :rows="3" disabled />
        </el-form-item>
        <el-form-item :label="t('feedbackAdmin.statusFilter')">
          <el-radio-group v-model="replyForm.status">
            <!-- Element Plus 2.6+：value 是绑定值，插槽是显示文案 -->
            <el-radio-button value="pending">{{ t('feedbackAdmin.statusPending') }}</el-radio-button>
            <el-radio-button value="processing">{{ t('feedbackAdmin.statusProcessing') }}</el-radio-button>
            <el-radio-button value="resolved">{{ t('feedbackAdmin.statusResolved') }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="t('feedbackAdmin.replyContent')">
          <el-input
            v-model="replyForm.admin_reply"
            type="textarea"
            :rows="4"
            maxlength="500"
            show-word-limit
            :placeholder="t('feedbackAdmin.replyPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="replyVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="replying" @click="submitReply">{{ t('profile.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
/**
 * 管理端「意见反馈管理」（第 27 批新增）
 *
 * 解决两个实际问题：
 *  1. 管理板块里此前**没有任何反馈入口**（只有新闻管理 / 病害百科维护）；
 *  2. 反馈列表里**看不到提交人**，管理员无法知道是谁提的。
 *
 * 后端：GET /feedback/（管理员返回全部，支持 category/status/search 筛选）
 *      POST /feedback/{id}/reply/（管理员回复并流转状态）
 */
import { computed, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { fetchMyFeedback, replyFeedback, deleteFeedback } from '@/api/feedback';
import { formatApiError } from '@/api/http';
import { formatTime } from '@/utils/date';
import { useI18n } from '@/i18n';  // 第 67 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 79 批：病害名等内容数据
import { useQueryState } from '@/composables/useQueryState';  // 第 98 批：筛选/分页进 URL
import { useAuthStore } from '@/stores/auth';  // 第 126 批：按能力决定"删除"按钮是否显示

export default {
  name: 'AdminFeedbackView',
  setup() {
    const { t } = useI18n();  // 必须在 setup 内取，模板才能拿到
    const { localizedField } = useLocalized();  // 第 79 批：病害名（中文快照 → 英文）
    const authStore = useAuthStore();

    /**
     * 能不能删除反馈（第 126 批）
     *
     * 产品口径：信息编辑员可以看、可以回复，但**不能删别人的反馈**（不可逆动作）。
     * 判断用 `isAdmin`（= 三项能力齐全，即全权管理员），与后端
     * `FeedbackView.destroy` 里的 `is_full_admin()` 守卫同一口径。
     * 自己提交的反馈仍然可以撤回 —— 但这一页是管理端列表（不区分提交人），
     * 所以这里按最严的来：非全权管理员不显示删除按钮。
     */
    const canDeleteOthers = computed(() => Boolean(authStore.isAdmin));
    const items = ref([]);
    const total = ref(0);
    const loading = ref(false);
    const page = ref(1);
    // 第 89 批：每页条数改成响应式（原来是常量 10，分页器要能改它）
    const pageSize = ref(10);
    const deletingId = ref(null);

    const filters = ref({ status: '', category: '', search: '' });

    const replyVisible = ref(false);
    const replying = ref(false);
    const current = ref(null);
    const replyForm = ref({ status: 'processing', admin_reply: '' });

    const categoryTagType = (category) => ({
      suggestion: 'success',
      bug: 'danger',
      recognition: 'warning',
      other: 'info',
    }[category] || 'info');

    const statusTagType = (status) => ({
      pending: 'info',
      processing: 'warning',
      resolved: 'success',
    }[status] || 'info');

    // 后端返回的中文 category_display/status_display 用前端映射覆盖，切换语言时跟着变
    const categoryLabel = (category) => ({
      suggestion: t('feedbackAdmin.catSuggestion'),
      bug: t('feedbackAdmin.catBug'),
      recognition: t('feedbackAdmin.catRecognition'),
      other: t('feedbackAdmin.catOther'),
    }[category] || category);

    const statusLabel = (status) => ({
      pending: t('feedbackAdmin.statusPending'),
      processing: t('feedbackAdmin.statusProcessing'),
      resolved: t('feedbackAdmin.statusResolved'),
    }[status] || status);

    // 状态统计小卡（第 28 批）：各用一次 page_size=1 的请求拿 count
    const stats = ref({ total: 0, pending: 0, processing: 0, resolved: 0 });

    const fetchStats = async () => {
      try {
        const [all, pending, processing, resolved] = await Promise.all([
          fetchMyFeedback({ page: 1, page_size: 1 }),
          fetchMyFeedback({ page: 1, page_size: 1, status: 'pending' }),
          fetchMyFeedback({ page: 1, page_size: 1, status: 'processing' }),
          fetchMyFeedback({ page: 1, page_size: 1, status: 'resolved' }),
        ]);
        stats.value = {
          total: all?.count || 0,
          pending: pending?.count || 0,
          processing: processing?.count || 0,
          resolved: resolved?.count || 0,
        };
      } catch (error) {
        console.warn('获取反馈统计失败:', error);
      }
    };

    const buildParams = () => {
      const params = { page: page.value, page_size: pageSize.value };
      if (filters.value.status) params.status = filters.value.status;
      if (filters.value.category) params.category = filters.value.category;
      if (filters.value.search.trim()) params.search = filters.value.search.trim();
      return params;
    };

    /**
     * 拉取列表（第 89 批：由"追加"改为**分页替换**）
     *
     * 原来 loadList(reset) 支持 reset=false 做"加载更多"的追加；现在改成真分页，
     * 每次只取当前页并整体替换 —— 第 3 页的内容不会还留在列表里。
     */
    const loadList = async () => {
      loading.value = true;
      try {
        const data = await fetchMyFeedback(buildParams());
        items.value = Array.isArray(data?.results) ? data.results : [];
        total.value = data?.count ?? items.value.length;
        fetchStats();
      } catch (error) {
        console.error('获取反馈列表失败:', error);
        items.value = [];
        total.value = 0;
        ElMessage.error(formatApiError(error, t('feedback.loadFailed')));
      } finally {
        loading.value = false;
      }
    };

    // ========================================================================
    // 第 98 批：筛选与分页写进 URL（与用户管理页同一套 composable）
    // ------------------------------------------------------------------------
    // 处理反馈时经常要"筛出待处理的，逐条看完再回来继续" —— 之前一旦点进某条
    // 或刷新页面，筛选就没了，得重新筛。现在条件在地址栏里，刷新/后退/分享都还在。
    // ========================================================================
    const filterRef = (key) => ({
      get value() { return filters.value[key]; },
      set value(next) { filters.value[key] = next ?? ''; },
    });

    const { isReady: queryReady } = useQueryState({
      fields: {
        page: { ref: page, type: 'int', default: 1 },
        page_size: { ref: pageSize, type: 'int', default: 10 },
        status: { ref: filterRef('status'), type: 'string', default: '' },
        category: { ref: filterRef('category'), type: 'string', default: '' },
        search: { ref: filterRef('search'), type: 'string', default: '' },
      },
      onExternalChange: () => loadList(),
    });

    const handleFilter = () => {
      page.value = 1;
      loadList();
    };

    /**
     * 改每页条数时回到第 1 页。
     * 否则"在第 5 页把每页条数改成 50"会让 page 越界，后端分页直接 404（页面空白）。
     */
    const handleSizeChange = () => {
      page.value = 1;
      loadList();
    };

    const openReply = (item) => {
      current.value = item;
      replyForm.value = {
        status: item.status || 'processing',
        admin_reply: item.admin_reply || '',
      };
      replyVisible.value = true;
    };

    const submitReply = async () => {
      if (!current.value) return;
      if (replyForm.value.status === 'resolved' && !replyForm.value.admin_reply.trim()) {
        ElMessage.warning(t('feedbackAdmin.replyRequiredForResolved'));
        return;
      }

      replying.value = true;
      try {
        const updated = await replyFeedback(current.value.id, {
          status: replyForm.value.status,
          admin_reply: replyForm.value.admin_reply.trim(),
        });
        // 就地更新，避免整页刷新丢失滚动位置
        const index = items.value.findIndex((row) => row.id === current.value.id);
        if (index !== -1 && updated) items.value[index] = updated;
        ElMessage.success(t('msg.saveOk'));
        replyVisible.value = false;
      } catch (error) {
        console.error('保存回复失败:', error);
        ElMessage.error(formatApiError(error, t('msg.savingFailedRetry')));
      } finally {
        replying.value = false;
      }
    };

    const removeItem = async (item) => {
      try {
        await ElMessageBox.confirm(
          t('feedbackAdmin.deleteConfirm', { user: item.user || t('feedbackAdmin.unknownUser') }),
          t('msg.notice'),
          { confirmButtonText: t('msg.delete'), cancelButtonText: t('msg.cancel'), type: 'warning' },
        );
      } catch {
        return;
      }

      deletingId.value = item.id;
      try {
        await deleteFeedback(item.id);
        ElMessage.success(t('msg.deleteOk'));
        // 第 89 批：原来一句 loadList() 会回到第 1 页，管理员的翻页位置就丢了；
        // 现在留在当前页，只在"删掉的是本页最后一条"时退一页，避免停在空白页。
        if (items.value.length === 1 && page.value > 1) page.value -= 1;
        await loadList();
      } catch (error) {
        console.error('删除反馈失败:', error);
        ElMessage.error(formatApiError(error, t('msg.deleteFailedRetry')));
      } finally {
        deletingId.value = null;
      }
    };

    // 第 98 批：等 URL 参数应用完再加载（避免"带参数打开链接"时先按默认值查一次）
    watch(queryReady, (ready) => {
      if (ready) {
        loadList();
        fetchStats();
      }
    }, { immediate: true });

    return {
      t,
      items,
      stats,
      total,
      loading,
      page,          // 第 89 批：分页
      pageSize,      // 第 89 批：分页
      deletingId,
      canDeleteOthers,   // 第 126 批：删除按钮只给全权管理员
      filters,
      replyVisible,
      replying,
      current,
      replyForm,
      categoryTagType,
      statusTagType,
      categoryLabel,
      statusLabel,
      localizedField,
      formatTime,
      loadList,
      handleFilter,
      handleSizeChange,  // 第 89 批：分页
      openReply,
      submitReply,
      removeItem,
    };
  },
};
</script>

<style scoped>
.admin-feedback {
  max-width: 1040px;
  margin: 0 auto;
  /* 第 29 批：整页套 .tinted-page（浅绿工作区底），这里保留工作区内边距 */
  padding: 22px 22px 34px;
}

/* 说明（第 29 批）：页头 / 头条 / 统计卡都改用主题里的公用块，
   原来这里是一段近白的 .page-header，整页观感"太白"。 */

/* 第 117 批：删掉了 `.admin-feedback > .back-button` 的间距规则（返回按钮已随管理后台外壳一起移除） */

/* 列表头条与下方卡片之间留一点间距 */
.list-panel-head {
  margin-bottom: 14px;
  border: 1px solid var(--brand-200, #bfe3cd);
  border-radius: var(--radius, 14px);
  box-shadow: var(--shadow-xs, 0 1px 2px rgba(19, 58, 41, 0.05));
}

/* 状态图例：让"左侧色条"的含义一眼可读 */
.legend {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--ink-600, #566b60);
}

.legend-dot {
  width: 9px;
  height: 9px;
  border-radius: 3px;
  display: inline-block;
}

.legend-dot.is-pending {
  background: var(--warning, #d9922f);
}

.legend-dot.is-processing {
  background: var(--info, #3d7ea6);
}

.legend-dot.is-resolved {
  background: var(--brand-500, #3d9a68);
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 12px 14px;
  margin-bottom: 16px;
  /* 第 28 批：纯白改成极浅绿底，和统计卡/列表形成层次 */
  background: linear-gradient(180deg, #ffffff, #eef8f2);
  border: 1px solid var(--brand-200, #bfe3cd);
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(19, 58, 41, 0.05);
}

.total-hint {
  margin-left: auto;
  font-size: 13px;
  color: var(--ink-500, #7a8699);
}

.feedback-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.feedback-item {
  padding: 14px 16px 14px 18px;
  /* 第 29 批：纯白改成极浅绿渐变（首尾都带色，卡片不再是"白纸"） */
  background: linear-gradient(180deg, #e8f6ee, #fbfefc);
  border: 1px solid var(--brand-200, #bfe3cd);
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(19, 58, 41, 0.04);
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.feedback-item:hover {
  box-shadow: 0 8px 20px rgba(19, 58, 41, 0.08);
  transform: translateY(-1px);
}

/* 按处理状态给左侧色条 + 轻微底色，一眼区分"待处理/处理中/已处理" */
.feedback-item.is-pending {
  border-left: 4px solid var(--warning, #d9922f);
  background: linear-gradient(180deg, #fdf3e2, #fffcf6);
}

.feedback-item.is-processing {
  border-left: 4px solid var(--info, #3d7ea6);
  background: linear-gradient(180deg, #e9f2fc, #f9fcff);
}

.feedback-item.is-resolved {
  border-left: 4px solid var(--brand-500, #3d9a68);
  background: linear-gradient(180deg, #ddf3e7, #f8fdfa);
}

.item-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.submitter {
  font-size: 14px;
  font-weight: 700;
  color: var(--brand-800, #245c3d);
}

.item-time {
  font-size: 12px;
  color: var(--ink-400, #9aa4b2);
}

.item-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
}

.item-content {
  margin: 10px 0 0;
  font-size: 14px;
  line-height: 1.75;
  color: var(--ink-700, #374151);
  white-space: pre-wrap;
}

.item-image {
  margin-top: 10px;
}

.item-image :deep(.el-image) {
  width: 120px;
  height: 90px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #eef0f3;
}

.item-context {
  margin-top: 8px;
  font-size: 12px;
  color: var(--ink-500, #7a8699);
}

.item-reply {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--brand-50, #eef7f1);
  border: 1px solid var(--brand-100, #d8ecdf);
}

.item-reply strong {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
  color: var(--brand-800, #245c3d);
}

.item-reply p {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--ink-700, #374151);
  white-space: pre-wrap;
}

.reply-time {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--ink-400, #9aa4b2);
}

/* 第 89 批：原来的"加载更多"按钮已换成真分页（见模板里的 el-pagination） */
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
