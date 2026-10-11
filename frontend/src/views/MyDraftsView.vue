<template>
  <div class="drafts-page tinted-page">
    <header class="page-hero">
      <div class="page-hero-main">
        <span class="page-hero-icon"><i class="fas fa-file-pen"></i></span>
        <div>
          <h1>{{ t('drafts.title') }}</h1>
          <p>{{ t('drafts.subtitle') }}</p>
        </div>
      </div>
      <div class="page-hero-actions">
        <el-button type="primary" @click="goNewPost">
          <i class="fas fa-pen"></i> {{ t('drafts.newPost') }}
        </el-button>
      </div>
    </header>

    <div v-if="loading" class="drafts-loading">
      <i class="fas fa-spinner fa-spin"></i> {{ t('common.loading') }}
    </div>

    <el-empty v-else-if="!drafts.length" :description="t('drafts.empty')">
      <el-button type="primary" @click="goNewPost">{{ t('drafts.emptyAction') }}</el-button>
    </el-empty>

    <ul v-else class="draft-list">
      <li v-for="draft in drafts" :key="draft.id" class="draft-item">
        <div class="draft-main">
          <h3 class="draft-title">{{ draft.title || t('drafts.untitled') }}</h3>
          <p class="draft-excerpt">{{ excerptOf(draft) }}</p>
          <div class="draft-meta">
            <span><i class="fas fa-clock"></i> {{ t('drafts.updatedAt', { time: formatTime(draft.updated_at || draft.created_at) }) }}</span>
            <span v-if="draft.board"><i class="fas fa-folder"></i> {{ localizedField(draft.board, 'name') }}</span>
            <span><i class="fas fa-align-left"></i> {{ t('drafts.lengthHint', { count: lengthOf(draft) }) }}</span>
          </div>
        </div>
        <div class="draft-actions">
          <el-button size="small" type="primary" @click="continueEditing(draft)">
            <i class="fas fa-pen-to-square"></i> {{ t('drafts.continue') }}
          </el-button>
          <el-button size="small" plain type="danger" @click="removeDraft(draft)">
            <i class="fas fa-trash"></i> {{ t('drafts.discard') }}
          </el-button>
        </div>
      </li>
    </ul>
  </div>
</template>

<script>
/**
 * 「我的草稿」页（第 166 批）
 * ============================================================================
 * ## 为什么要有它
 *
 * 编辑页每 30 秒自动把草稿存到**服务端**（`is_draft: true` → `status='draft'`）。
 * 但在此之前**前端没有任何入口能看到它们** —— 农户写了一半点"取消"或关掉页面，
 * 那条半成品就永远躺在库里：作者只能去论坛列表里翻（草稿会混在正常帖子里，
 * 只靠一个小「草稿」标签区分），版主更是完全不知道该拿它们怎么办。
 * 评审意见点名的就是这件事。
 *
 * ## 口径
 *
 * 列表直接查 `?status=draft&author=<自己>`：后端的可见性规则保证**只有作者本人**
 * 能看到自己的草稿（版主也不行 —— 第 166 批起版主的默认列表连草稿都不会混入）。
 * 「删除」走的是帖子软删除（`DELETE /api/forums/posts/<id>/`），可在管理端审计到。
 */
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getPosts, deletePost } from '@/api/forum';
import { useI18n } from '@/i18n';
import { useLocalized } from '@/utils/localized';
import { formatTime } from '@/utils/date';
import { useAuthStore } from '@/stores/auth';

export default {
  name: 'MyDraftsView',
  setup() {
    const { t } = useI18n();
    const { localizedField } = useLocalized();
    const router = useRouter();
    const authStore = useAuthStore();
    const drafts = ref([]);
    const loading = ref(true);

    const myId = computed(() => authStore.user?.id);

    const fetchDrafts = async () => {
      loading.value = true;
      try {
        const response = await getPosts({
          status: 'draft',
          author: myId.value,
          page_size: 50,
        });
        const list = Array.isArray(response) ? response : (response?.results || []);
        drafts.value = list;
      } catch (error) {
        console.error('[drafts] 加载草稿失败:', error);
        ElMessage.error(t('drafts.loadFailed'));
      } finally {
        loading.value = false;
      }
    };

    /** 正文摘要：去掉标签、截断（草稿通常是半句话，够看就行） */
    const excerptOf = (draft) => {
      const text = String(localizedField(draft, 'content') || '')
        .replace(/<[^>]+>/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      if (!text) return t('drafts.noContent');
      return text.length > 80 ? `${text.slice(0, 80)}…` : text;
    };

    /** 字数（去掉标签后的字符数，给作者一个"写到哪了"的感觉） */
    const lengthOf = (draft) => String(draft.content || '').replace(/<[^>]+>/g, '').trim().length;

    const continueEditing = (draft) => {
      router.push({ name: 'edit-post', params: { id: draft.id } });
    };

    const removeDraft = async (draft) => {
      try {
        await ElMessageBox.confirm(
          t('drafts.discardConfirm', { title: draft.title || t('drafts.untitled') }),
          t('drafts.discardTitle'),
          {
            type: 'warning',
            confirmButtonText: t('drafts.discard'),
            cancelButtonText: t('common.cancel'),
          },
        );
      } catch {
        return;   // 用户取消
      }
      try {
        await deletePost(draft.id);
        drafts.value = drafts.value.filter((item) => item.id !== draft.id);
        ElMessage.success(t('drafts.discarded'));
      } catch (error) {
        console.error('[drafts] 删除失败:', error);
        ElMessage.error(t('drafts.discardFailed'));
      }
    };

    const goNewPost = () => router.push({ name: 'new-post' });

    onMounted(fetchDrafts);

    return {
      t, drafts, loading, localizedField, formatTime,
      excerptOf, lengthOf, continueEditing, removeDraft, goNewPost,
    };
  },
};
</script>

<style scoped>
.page-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  padding: 18px 20px;
  border-radius: 14px;
  background: linear-gradient(135deg, var(--brand-500, #3f9a6b), var(--brand-600, #2f7a55));
  color: #fff;
}

.page-hero-main {
  display: flex;
  align-items: center;
  gap: 14px;
}

.page-hero-icon {
  font-size: 26px;
  opacity: 0.9;
}

.page-hero h1 {
  margin: 0;
  font-size: 20px;
}

.page-hero p {
  margin: 4px 0 0;
  font-size: 13px;
  opacity: 0.9;
}

.drafts-loading {
  padding: 40px 0;
  text-align: center;
  color: var(--ink-400, #9dada5);
}

.draft-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.draft-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border: 1px solid var(--border, #e6ece8);
  border-radius: 12px;
  background: #fff;
  flex-wrap: wrap;
}

.draft-main {
  flex: 1 1 420px;
  min-width: 0;
}

.draft-title {
  margin: 0 0 6px;
  font-size: 15px;
  color: var(--ink-800, #2c3a33);
}

.draft-excerpt {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--ink-500, #7d8f86);
  word-break: break-all;
}

.draft-meta {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--ink-400, #9dada5);
}

.draft-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
</style>
