<template>
  <div class="feedback-page tinted-page">
    <!-- 返回入口（第 87 批：本页从页脚/帮助中心进来，此前没有返回按钮） -->
    <BackButton class="feedback-back" />

    <!-- 页头（第 29 批：改用全局 .admin-hero 的深绿实底样式。
         原来只有一行裸标题 + 副标题，铺在浅绿工作区底上"白得发亮"） -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-comment-dots"></i></span>
        <div>
          <h1>{{ t('feedback.title') }}</h1>
          <p>
            {{ t('feedback.subtitle') }}
          </p>
        </div>
      </div>
    </header>

    <div class="feedback-body">
      <!-- 提交表单（第 29 批：卡片加"着色头条"，表单区不再是一整块白） -->
      <section class="form-card">
        <header class="panel-head">
          <span class="panel-icon"><i class="fas fa-pen-to-square"></i></span>
          <h3 class="panel-title">{{ t('feedback.newFeedback') }}</h3>
          <div class="panel-head-right">
            <span class="panel-hint">{{ t('feedback.newFeedbackHint') }}</span>
          </div>
        </header>
        <el-form label-width="72px" @submit.prevent>
          <el-form-item :label="t('feedback.category')">
            <el-radio-group v-model="form.category">
              <!-- Element Plus 2.6+ 用 value 作为绑定值、插槽作为显示文案。
                   原来写的是 label="suggestion"（无插槽），于是按钮上直接显示
                   "suggestion/bug/other" 而不是中文/英文分类名。 -->
              <el-radio-button value="suggestion">{{ t('feedbackAdmin.catSuggestion') }}</el-radio-button>
              <el-radio-button value="bug">{{ t('feedbackAdmin.catBug') }}</el-radio-button>
              <el-radio-button value="other">{{ t('feedbackAdmin.catOther') }}</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <el-form-item :label="t('feedback.content')">
            <el-input
              v-model="form.suggestion"
              type="textarea"
              :rows="5"
              maxlength="500"
              show-word-limit
              :placeholder="contentPlaceholder"
            />
          </el-form-item>

          <!--: 第 225 批（P2-7）：联系方式（选填）。
           改前用户只能留一段没有上下文的文字，管理员想追问"哪个浏览器/哪张图"时问不到人。 -->
      <el-form-item :label="t('feedback.contact')">
        <el-input
          v-model="form.contact"
          :placeholder="t('feedback.contactPlaceholder')"
          maxlength="100"
          clearable
        />
      </el-form-item>
      <el-form-item :label="t('feedback.screenshot')">
            <div class="upload-block">
              <el-upload
                :auto-upload="false"
                :show-file-list="false"
                accept="image/*"
                :on-change="handleImageChange"
              >
                <el-button plain><i class="fas fa-image"></i> {{ imageFile ? t('profile.changeAvatar') : t('feedback.uploadOptional') }}</el-button>
              </el-upload>
              <div v-if="imagePreview" class="preview">
                <img :src="imagePreview" :alt="t('feedback.imagePreviewAlt')">
                <el-button size="small" text type="danger" @click="removeImage">{{ t('profile.remove') }}</el-button>
              </div>
              <p class="hint">{{ t('profile.avatarHint') }}</p>
            </div>
          </el-form-item>

          <el-form-item>
            <el-button type="primary" :loading="submitting" @click="submit">
              <i class="fas fa-paper-plane"></i> {{ t('feedback.submit') }}
            </el-button>
            <el-button @click="resetForm">{{ t('feedback.clear') }}</el-button>
          </el-form-item>
        </el-form>
      </section>

      <!-- 我的反馈 -->
      <section class="list-card">
        <div class="panel-head list-head">
          <span class="panel-icon"><i class="fas fa-list-ul"></i></span>
          <h3 class="panel-title">{{ t('feedback.myFeedback') }}</h3>
          <span class="panel-count">{{ t('feedbackAdmin.totalCount', { count: total }) }}</span>
          <div class="panel-head-right">
            <el-button size="small" plain :loading="loading" @click="loadList">
              <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
            </el-button>
          </div>
        </div>

        <el-skeleton v-if="loading" :rows="4" animated />
        <el-empty v-else-if="items.length === 0" :description="t('feedback.empty')" :image-size="90" />

        <div v-else class="feedback-list">
          <div
            v-for="item in items"
            :key="item.id"
            class="feedback-item"
            :class="`is-${item.status}`"
          >
            <div class="item-head">
              <!-- 第 27 批：管理员在这个页面看到的是**所有用户**的反馈，
                   必须显示提交人，否则无法知道是谁提的 -->
              <span v-if="isAdmin" class="submitter">
                <i class="fas fa-user"></i> {{ item.user || t('feedbackAdmin.unknownUser') }}
              </span>
              <el-tag size="small" :type="categoryTagType(item.category)">{{ categoryLabel(item.category) }}</el-tag>
              <el-tag size="small" :type="statusTagType(item.status)" effect="light">{{ statusLabel(item.status) }}</el-tag>
              <span class="item-time">{{ formatTime(item.timestamp) }}</span>
              <el-button
                class="item-delete"
                size="small"
                text
                type="danger"
                :loading="deletingId === item.id"
                @click="removeFeedback(item)"
              >
                <i class="fas fa-trash"></i> {{ t('feedback.withdraw') }}
              </el-button>
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

            <div v-if="item.disease_name" class="item-context">
              <i class="fas fa-microscope"></i>
              <!-- 第 79 批：病害名是提交时的中文快照，后端按名字回查百科给出英文名 -->
              {{ t('feedback.linkedDetect', { name: localizedField(item, 'disease_name') }) }}
              <template v-if="item.confidence !== null && item.confidence !== undefined">
                · {{ t('feedbackAdmin.confidence', { value: (item.confidence * 100).toFixed(1) }) }}
              </template>
              <template v-if="item.is_correct !== null && item.is_correct !== undefined">
                · {{ item.is_correct ? t('feedback.userSaysCorrect') : t('feedback.userSaysIncorrect') }}
              </template>
            </div>

            <div v-if="item.admin_reply" class="item-reply">
              <strong><i class="fas fa-reply-all"></i> {{ t('feedbackAdmin.adminReply') }}</strong>
              <p>{{ localizedField(item, 'admin_reply') }}</p>
          <!--: 第 224 批：「处理于 x」—— 用户看到回复时，"什么时候处理的"是基本交代
               （后端一直在下发 `handled_at`，用户侧却没显示）。 -->
          <span v-if="item.handled_at" class="reply-time">
            {{ t('feedbackAdmin.handledAt', { time: formatTime(item.handled_at) }) }}
          </span>
            </div>
          </div>

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
        </div>
      </section>
    </div>
  </div>
</template>

<script>
/**
 * 意见反馈（第 26 批新增；页脚的原「意见反馈」是一个 href="#" 的死链，
 * 反馈提交此前只内嵌在「病害识别」的结果卡片里）
 *
 * 后端：`/api/feedback/`（FeedbackView）—— 用户只能看到 / 撤回自己的反馈，
 * 处理状态与管理员回复由管理员在 Django 后台填写。
 */
import { ref, computed, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { submitFeedback, fetchMyFeedback, deleteFeedback } from '@/api/feedback';
import { formatApiError } from '@/api/http';
import { formatTime } from '@/utils/date';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';  // 第 67 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 79 批：病害名等内容数据
import BackButton from '@/components/BackButton.vue';  // 第 87 批：返回按钮

// 各类型的输入提示（走 i18n，第 67 批）
const PLACEHOLDER_KEYS = {
  suggestion: 'feedback.phSuggestion',
  bug: 'feedback.phBug',
  other: 'feedback.phOther',
};

export default {
  name: 'FeedbackCenterView',
  components: { BackButton },
  setup() {
    const { t } = useI18n();  // 第 67 批：多语言（必须在 setup 内取）
    const { localizedField } = useLocalized();  // 第 79 批：病害名（提交时的中文快照 → 英文）
    const authStore = useAuthStore();
    // 管理员在本页看到的是全部用户的反馈（后端按角色返回），需要额外显示提交人
    const isAdmin = computed(() => Boolean(authStore.isAdmin));

    const form = ref({ category: 'suggestion', suggestion: '', contact: '' });   //: 第 225 批：contact
    const imageFile = ref(null);
    const imagePreview = ref('');
    const submitting = ref(false);

    const items = ref([]);
    const total = ref(0);
    const loading = ref(false);
    const page = ref(1);
    // 第 90 批：每页条数改成响应式（原来是常量 10，分页器要能改它）
    const pageSize = ref(10);
    const deletingId = ref(null);

    const contentPlaceholder = computed(
      () => t(PLACEHOLDER_KEYS[form.value.category] || PLACEHOLDER_KEYS.other),
    );

    const categoryTagType = (category) => ({
      suggestion: 'success',
      bug: 'danger',
      other: 'info',
    }[category] || 'info');

    const statusTagType = (status) => ({
      pending: 'info',
      processing: 'warning',
      resolved: 'success',
    }[status] || 'info');

    // 后端返回的中文 category_display/status_display 用前端映射覆盖，切语言时跟着变
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

    /**
     * 拉取列表（第 90 批：由"追加"改为**分页替换**）
     *
     * 原来 loadList(reset) 支持 reset=false 做"加载更多"的追加；现在改成真分页，
     * 每次只取当前页并整体替换。管理端（AdminFeedbackView）在第 89 批已先改，
     * 这一页跟着对齐 —— 否则"管理端有分页、用户端还在往下拉"，同一个功能两套体验。
     */
    const loadList = async () => {
      loading.value = true;
      try {
        const data = await fetchMyFeedback({ page: page.value, page_size: pageSize.value });
        items.value = Array.isArray(data?.results) ? data.results : [];
        total.value = data?.count ?? items.value.length;
      } catch (error) {
        console.error('获取反馈列表失败:', error);
        items.value = [];
        total.value = 0;
        ElMessage.error(formatApiError(error, t('feedback.loadFailed')));
      } finally {
        loading.value = false;
      }
    };

    /**
     * 改每页条数时回到第 1 页。
     * 否则"在第 5 页把每页条数改成 50"会让 page 越界，后端分页直接 404（页面空白）。
     */
    const handleSizeChange = () => {
      page.value = 1;
      loadList();
    };

    const handleImageChange = (uploadFile) => {
      const raw = uploadFile?.raw;
      if (!raw) return;

      if (!raw.type.startsWith('image/')) {
        ElMessage.error(t('feedback.imageOnly'));
        return;
      }
      if (raw.size / 1024 / 1024 >= 5) {
        ElMessage.error(t('feedback.imageTooLarge'));
        return;
      }

      imageFile.value = raw;
      const reader = new FileReader();
      reader.onload = (event) => {
        imagePreview.value = event.target.result;
      };
      reader.readAsDataURL(raw);
    };

    const removeImage = () => {
      imageFile.value = null;
      imagePreview.value = '';
    };

    const resetForm = () => {
      form.value = { category: 'suggestion', suggestion: '', contact: '' };
      removeImage();
    };

    const submit = async () => {
      // 早期写法直接 form.value.suggestion.trim()，一旦 suggestion 为 undefined
      // 就会抛 TypeError，整页失去响应（用户反馈"意见反馈页面出错用不了"）
      const content = String(form.value.suggestion ?? '').trim();
      if (!content && !imageFile.value) {
        ElMessage.warning(t('feedback.formIncomplete'));
        return;
      }

      submitting.value = true;
      try {
        await submitFeedback(
          { category: form.value.category, suggestion: content, contact: (form.value.contact || '').trim() },
          imageFile.value,
        );
        ElMessage.success(t('feedback.submitOk'));
        resetForm();
        // 新提交的反馈排在最前（后端按时间倒序），回到第 1 页才看得到它
        page.value = 1;
        await loadList();
      } catch (error) {
        console.error('提交反馈失败:', error);
        ElMessage.error(formatApiError(error, t('feedback.submitFailed')));
      } finally {
        submitting.value = false;
      }
    };

    const removeFeedback = async (item) => {
      try {
        await ElMessageBox.confirm(t('feedback.withdrawConfirm'), t('feedback.withdrawTitle'), {
          confirmButtonText: t('feedback.withdraw'),
          cancelButtonText: t('common.cancel'),
          type: 'warning',
        });
      } catch {
        return;
      }

      deletingId.value = item.id;
      try {
        await deleteFeedback(item.id);
        ElMessage.success(t('feedback.withdrawOk'));
        // 第 90 批：留在当前页；只有"撤回的是本页最后一条"时才退一页，避免停在空白页
        if (items.value.length === 1 && page.value > 1) page.value -= 1;
        await loadList();
      } catch (error) {
        console.error('撤回反馈失败:', error);
        ElMessage.error(formatApiError(error, t('feedback.withdrawFailed')));
      } finally {
        deletingId.value = null;
      }
    };

    onMounted(() => loadList());

    return {
      t,
      form,
      isAdmin,
      imageFile,
      imagePreview,
      submitting,
      items,
      total,
      loading,
      deletingId,
      contentPlaceholder,
      categoryTagType,
      statusTagType,
      // 第 71 批修复：这两个函数此前只定义、没有 return，
      // 模板里 `categoryLabel(item.category)` / `statusLabel(item.status)`
      // 会调用到 undefined → TypeError，整页反馈列表渲染失败。
      categoryLabel,
      statusLabel,
      formatTime,
      // 第 79 批：病害名按语言取值（Options API 不 return 就是 undefined）
      localizedField,
      loadList,
      // 第 90 批：分页（page / pageSize / handleSizeChange 必须 return，否则模板里是 undefined）
      page,
      pageSize,
      handleSizeChange,
      handleImageChange,
      removeImage,
      resetForm,
      submit,
      removeFeedback,
    };
  },
};
</script>

<style scoped>
.feedback-page {
  /* 第 32 批：`.main-content` 是 flex + align-items:center，只写 max-width 会被
     按内容收缩（实测 658px，而这里写的是 980px）—— 浅绿工作区两侧白留一大片。
     补 width:100% 才会真正吃满 max-width。 */
  width: 100%;
  max-width: 980px;
  margin: 0 auto;
  /* 第 29 批：整页套 .tinted-page（浅绿工作区底），这里保留工作区内边距 */
  padding: 26px 20px 48px;
}

/* 说明（第 29 批）：原来页头只有一行 h1 + 副标题（.page-header/.subtitle），
   已换成主题里的 .admin-hero（深绿实底 + 白色文字 + 图标块）。 */

/* 返回按钮（第 87 批）：贴左摆放，和下面的深绿页头留出间距 */
.feedback-back {
  align-self: flex-start;
  margin-bottom: 12px;
}

.feedback-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 20px;
}

/* 卡片：内边距交给"着色头条 + 内容区"，头条要能贴到卡片左右边缘 */
.form-card,
.list-card {
  overflow: hidden;
  padding: 0;
  background: var(--surface, #fff);
  border: 1px solid var(--brand-200, #bfe3cd);
  border-radius: 14px;
  box-shadow: var(--shadow-sm, 0 2px 8px rgba(19, 58, 41, 0.06));
}

.form-card .el-form {
  padding: 18px 22px 20px;
  /* 表单区也给一层极浅绿，卡片内不再是"一整块纯白" */
  background: linear-gradient(180deg, #f5fcf8, #ffffff 62%);
}

/* 列表卡片内容区（骨架 / 空状态 / 列表）统一内边距 + 极浅绿底 */
.list-card > .feedback-list,
.list-card > .el-skeleton,
.list-card > .el-empty {
  padding: 16px 18px 18px;
  background: linear-gradient(180deg, #f5fcf8, #ffffff 40%);
}

.list-head {
  /* 第 29 批：原来的 .list-head 是白底上的一行标题，现在换成着色头条 */
  margin-bottom: 0;
}

.panel-hint {
  font-size: 12px;
  color: var(--ink-500, #78897f);
}

.upload-block .hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--ink-400, #9aa4b2);
}

.preview {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.preview img {
  max-width: 160px;
  max-height: 120px;
  border-radius: 8px;
  border: 1px solid #eef0f3;
}

.feedback-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.feedback-item {
  padding: 14px 16px 14px 18px;
  border: 1px solid var(--brand-200, #bfe3cd);
  border-radius: 10px;
  /* 第 29 批：纯白底改成极浅绿渐变（首尾都带色，卡片不再是"白纸"） */
  background: linear-gradient(180deg, #e8f6ee, #fbfefc);
  box-shadow: var(--shadow-xs, 0 1px 2px rgba(19, 58, 41, 0.05));
}

/* 第 29 批：和管理页一致，按处理状态给左侧色条 —— 用户一眼能看出
   "哪条还没被处理"，不用去读右侧的状态标签 */
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
  gap: 8px;
  flex-wrap: wrap;
}

.item-time {
  font-size: 12px;
  color: var(--ink-400, #9aa4b2);
}

/* 提交人（仅管理员可见） */
.submitter {
  font-size: 14px;
  font-weight: 700;
  color: var(--brand-800, #245c3d);
}

.item-delete {
  margin-left: auto;
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

/* 第 90 批：原来的"加载更多"按钮已换成真分页（见模板里的 el-pagination） */
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
