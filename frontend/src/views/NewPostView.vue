<template>
  <div class="new-post">
    <!-- 页头（第 33 批：原来只有一行 h2） -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-pen-to-square"></i></span>
        <div>
          <h1>{{ t('post.title') }}</h1>
          <p>{{ t('post.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-button plain @click="cancel">
          <i class="fas fa-arrow-left"></i> {{ t('post.backToForum') }}
        </el-button>
      </div>
    </header>

    <div class="post-layout">
      <!-- 左：表单 -->
      <section class="panel-card post-main">
        <div class="panel-head">
          <span class="panel-icon"><i class="fas fa-file-pen"></i></span>
          <h2 class="panel-title">{{ t('post.contentSection') }}</h2>
          <div class="panel-head-right">
            <span v-if="saveStatus" class="draft-status">
              <i class="fas fa-cloud-arrow-up"></i> {{ saveStatus }}
            </span>
          </div>
        </div>

        <div class="panel-body">
          <el-form ref="postForm" :model="form" :rules="rules" label-position="top">
            <el-form-item :label="t('post.boardLabel')" prop="board">
              <el-select
                v-model="form.board"
                :placeholder="t('post.boardPlaceholder')"
                style="width: 100%"
                :loading="loading"
                :disabled="loading"
                filterable
              >
                <el-option
                  v-for="board in boards"
                  :key="board.id"
                  :label="localizedField(board, 'name')"
                  :value="board.id"
                >
                  <div class="board-option">
                    <i :class="boardIconClass(board.icon)"></i>
                    <span>{{ localizedField(board, 'name') }}</span>
                    <span v-if="board.description" class="board-option-desc">
                      {{ localizedField(board, 'description') }}
                    </span>
                  </div>
                </el-option>
              </el-select>
              <p class="field-hint">
                <i class="fas fa-circle-info"></i>
                {{ t('post.boardHint') }}
              </p>
            </el-form-item>

            <el-form-item :label="t('post.titleLabel')" prop="title">
              <el-input
                v-model="form.title"
                maxlength="100"
                show-word-limit
                :placeholder="t('post.titlePlaceholder')"
              />
            </el-form-item>

            <el-form-item :label="t('post.bodyLabel')" prop="content" class="editor-item">
              <!-- 第 141 批：论坛发帖走**通用**图片上传通道（新闻编辑器走 news 通道） -->
        <RichTextEditor v-model="form.content" upload-target="generic" />
              <p class="field-hint">
                <i class="fas fa-lightbulb"></i>
                {{ t('post.bodyHint') }}
              </p>
            </el-form-item>

            <!--
              第 86 批：可选的英文版本
              ------------------------------------------------------------------
              帖子是用户写的中文，英文界面下默认由后端自动翻译。作者如果愿意
              自己给一版英文（通常是术语更准），填在这里 —— 后端会把它记成
              「人工翻译」，自动翻译与 `translate_forum_content --force` 都不会
              覆盖它。**留空即可**，不会影响发布。
            -->
            <el-form-item class="en-block">
              <template #label>
                <span class="en-label">
                  {{ t('post.englishSection') }}
                  <em>{{ t('post.englishOptional') }}</em>
                  <button type="button" class="en-toggle" @click="showEnglish = !showEnglish">
                    {{ showEnglish ? t('post.englishHide') : t('post.englishFill') }}
                  </button>
                </span>
              </template>
              <div v-show="showEnglish" class="en-fields">
                <p class="field-hint">
                  <i class="fas fa-language"></i>
                  {{ t('post.englishHint') }}
                </p>
                <el-input
                  v-model="form.title_en"
                  maxlength="200"
                  show-word-limit
                  :placeholder="t('post.titleEnPlaceholder')"
                />
                <el-input
                  v-model="form.content_en"
                  type="textarea"
                  :rows="4"
                  :placeholder="t('post.contentEnPlaceholder')"
                />
              </div>
            </el-form-item>

            <el-form-item v-if="isModerator" :label="t('post.moderatorOps')">
              <div class="moderator-ops">
                <label class="op-card" :class="{ 'is-on': form.is_essence }">
                  <el-checkbox v-model="form.is_essence">{{ t('post.setEssence') }}</el-checkbox>
                  <small>{{ t('post.setEssenceHint') }}</small>
                </label>
                <label class="op-card" :class="{ 'is-on': form.is_pinned }">
                  <el-checkbox v-model="form.is_pinned">{{ t('post.setPinned') }}</el-checkbox>
                  <small>{{ t('post.setPinnedHint') }}</small>
                </label>
              </div>
            </el-form-item>
          </el-form>
        </div>

        <div class="form-dialog-footer post-footer">
          <span class="footer-hint">
            <i :class="needReview ? 'fas fa-shield-halved' : 'fas fa-circle-info'"></i>
            {{ footerHint }}
          </span>
          <span class="footer-actions">
            <el-button @click="cancel">{{ t('common.cancel') }}</el-button>
            <el-button @click="resetForm">{{ t('post.reset') }}</el-button>
            <el-button type="primary" :loading="submitting" @click="submitForm">
              <i class="fas fa-paper-plane"></i> {{ t('post.submit') }}
            </el-button>
          </span>
        </div>
      </section>

      <!-- 右：发帖指引 + 草稿 -->
      <aside class="post-side">
        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-list-check"></i></span>
            <h3 class="panel-title">{{ t('post.guideTitle') }}</h3>
          </div>
          <div class="panel-body">
            <ol class="tips">
              <li>
                <b>{{ t('post.guide1') }}</b>
                <p>{{ t('post.guide1Desc') }}</p>
              </li>
              <li>
                <b>{{ t('post.guide2') }}</b>
                <p>{{ t('post.guide2Desc') }}</p>
              </li>
              <li>
                <b>{{ t('post.guide3') }}</b>
                <p>{{ t('post.guide3Desc') }}</p>
              </li>
              <li>
                <b>{{ t('post.guide4') }}</b>
                <p>{{ t('post.guide4Desc') }}</p>
              </li>
            </ol>
            <RouterLink to="/detect" class="side-cta">
              <i class="fas fa-camera"></i> {{ t('post.detectFirst') }}
            </RouterLink>
          </div>
        </section>

        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-floppy-disk"></i></span>
            <h3 class="panel-title">{{ t('post.draftTitle') }}</h3>
          </div>
          <div class="panel-body">
            <p class="draft-line">
              <template v-if="draftSavedAt">
                <i class="fas fa-circle-check"></i>
                {{ t('post.draftSaved', { time: draftSavedAt }) }}
              </template>
              <template v-else>
                <i class="fas fa-circle-info"></i>
                {{ t('post.draftAutoSave') }}
              </template>
            </p>
            <button type="button" class="draft-clear" :disabled="!draftSavedAt" @click="discardDraft">
              <i class="fas fa-trash"></i> {{ t('post.draftClear') }}
            </button>
          </div>
        </section>
      </aside>
    </div>
  </div>
</template>

<script>
/**
 * 发表新帖（第 33 批重做）
 * ------------------------------------------------------------------
 * 原来的问题：
 * 1. 外观：整页只有一张白卡片 + 一行 h2，没有任何页面头与分区；版块下拉里的图标写成
 *    `el-icon-{board.icon}`，而 Element Plus 2 没有图标字体 → 图标全空。
 * 2. 功能：写一半关掉页面内容就没了（编辑页 EditPostView 有草稿能力，发帖页却没有）。
 * 3. 代码：提交路径里塞了多个 console.group/console.log，把整份表单数据打进控制台。
 *
 * 现在：
 *  - 深绿页头 + 左侧表单面板 + 右侧"发帖四要素/草稿"侧栏；
 *  - 本地草稿自动保存（localStorage，键沿用 EditPostView 的 `post_draft_new`），
 *    进入页面时若有草稿会询问是否恢复，发布成功后清除；
 *  - 版块图标改用 Font Awesome；控制台调试输出清理掉。
 */
import { ref, onMounted, onUnmounted, computed, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getForumBoards, createPost } from '@/api/forum';
import { fetchSiteConfig } from '@/api/content';  // 第 38 批：发帖审核策略
import RichTextEditor from '@/components/RichTextEditor.vue';
import { useI18n } from '@/i18n';
import { useLocalized } from '@/utils/localized';  // 第 55 批：多语言（第 72 批起也用于版块名等内容数据）
import { useUnsavedChanges } from '@/composables/useUnsavedChanges';  // 第 97 批：离开前提醒

const DRAFT_KEY = 'post_draft_new';

export default {
  name: 'NewPostView',
  components: { RichTextEditor },
  setup() {
    const { t } = useI18n();  // 第 55 批：多语言
    const { localizedField } = useLocalized();
    const router = useRouter();
    const route = useRoute();
    const authStore = useAuthStore();
    const postForm = ref(null);

    const form = ref({
      board: '',
      title: '',
      content: '',
      // 第 86 批：可选的英文版本（留空 → 后端自动翻译；填了 → 记成"人工翻译"）
      title_en: '',
      content_en: '',
      is_essence: false,
      is_pinned: false,
    });

    /** 英文区块默认折叠（绝大多数人不需要填），点一下展开 */
    const showEnglish = ref(false);

    const boards = ref([]);
    const loading = ref(true);
    const submitting = ref(false);

    // 草稿状态
    const draftSavedAt = ref('');
    const saveStatus = ref('');
    let draftTimer = null;
    let restoredDraft = false;

    const isModerator = computed(() => authStore.user?.is_staff || false);

    // 第 38 批：发帖审核策略（来自后端 /api/site-config/，不硬编码，避免提示与真实行为不符）
    const postRequireReview = ref(false);
    /** 我这次发帖是否会被送审：非版主 且 后端开启了审核 */
    const needReview = computed(() => postRequireReview.value && !isModerator.value);
    const footerHint = computed(() => {
      if (needReview.value) return t('post.hintReview');
      return isModerator.value ? t('post.hintModerator') : t('post.hintPublic');
    });

    const loadSiteConfig = async () => {
      try {
        const data = await fetchSiteConfig();
        postRequireReview.value = Boolean(data?.post_require_review);
      } catch (error) {
        console.warn('获取站点配置失败:', error);
      }
    };

    /** 后端存的是 Font Awesome 名字（bug / seedling / flask） */
    const boardIconClass = (icon) => `fas fa-${(icon || 'comments').replace(/^fa-/, '')}`;

    const rules = {
      // 第 83 批：校验文案接入 i18n（此前写死中文，英文界面下报错仍是中文）
      board: [{ required: true, message: t('forum.boardRequired'), trigger: 'change' }],
      title: [
        { required: true, message: t('forum.titleRequired'), trigger: 'blur' },
        { min: 5, max: 100, message: t('forum.titleLength'), trigger: 'blur' },
      ],
      content: [
        { required: true, message: t('forum.contentRequired'), trigger: 'blur' },
        { min: 10, message: t('forum.contentMin'), trigger: 'blur' },
      ],
    };

    const fetchBoards = async () => {
      loading.value = true;
      try {
        const response = await getForumBoards();
        // 只显示启用中的版块
        boards.value = Array.isArray(response)
          ? response.filter((board) => board.is_active !== false)
          : [];

        // URL 参数指定了版块就用它，否则默认第一个
        const wanted = route.query.boardId ? parseInt(route.query.boardId, 10) : null;
        const exists = wanted && boards.value.some((board) => board.id === wanted);
        if (exists) {
          form.value.board = wanted;
        } else if (boards.value.length > 0) {
          form.value.board = boards.value[0].id;
        }
      } catch (error) {
        console.error('获取版块列表失败:', error);
        ElMessage.error(t('post.loadBoardsFailed', { detail: error.message || t('msg.unknownError') }));
        boards.value = [];
      } finally {
        loading.value = false;
      }
    };

    // ---------- 本地草稿 ----------
    const clearDraft = () => {
      // 注意：必须先取消"待写入"的防抖定时器 —— 否则点发布后 clearDraft() 清掉了草稿，
      // 800ms 后那个还没执行的定时器又会把草稿写回去（实测发布成功后草稿仍在）。
      if (draftTimer) {
        clearTimeout(draftTimer);
        draftTimer = null;
      }
      localStorage.removeItem(DRAFT_KEY);
      draftSavedAt.value = '';
      saveStatus.value = '';
      restoredDraft = false;
    };

    const writeDraft = () => {
      const hasContent = form.value.title?.trim() || form.value.content?.trim();
      if (!hasContent) return;
      const now = new Date();
      localStorage.setItem(
        DRAFT_KEY,
        JSON.stringify({
          board: form.value.board,
          title: form.value.title,
          content: form.value.content,
          // 第 86 批：英文草稿一起存，否则"填了英文但没发布"时草稿恢复会丢内容
          title_en: form.value.title_en,
          content_en: form.value.content_en,
          updatedAt: now.toISOString(),
        }),
      );
      draftSavedAt.value = now.toLocaleTimeString('zh-CN', { hour12: false });
      saveStatus.value = t('post.draftSaved', { time: draftSavedAt.value });
      setTimeout(() => {
        saveStatus.value = '';
      }, 2500);
    };

    /** 恢复草稿（进页面时询问一次） */
    const maybeRestoreDraft = () => {
      let draft = null;
      try {
        draft = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null');
      } catch {
        localStorage.removeItem(DRAFT_KEY);
        return;
      }
      if (!draft || (!draft.title && !draft.content)) return;

      ElMessageBox.confirm(t('post.draftRestoreConfirm'), t('post.draftRestoreTitle'), {
        confirmButtonText: t('msg.restore'),
        cancelButtonText: t('msg.discard'),
        type: 'warning',
      })
        .then(() => {
          form.value.title = draft.title || '';
          form.value.content = draft.content || '';
          // 第 86 批：英文草稿也恢复；有内容时自动展开英文区块
          form.value.title_en = draft.title_en || '';
          form.value.content_en = draft.content_en || '';
          if (form.value.title_en || form.value.content_en) showEnglish.value = true;
          if (draft.board) form.value.board = draft.board;
          restoredDraft = true;
          draftSavedAt.value = draft.updatedAt
            ? new Date(draft.updatedAt).toLocaleTimeString('zh-CN', { hour12: false })
            : '';
          ElMessage.success(t('post.draftRestored'));
        })
        .catch(() => {
          clearDraft();
          ElMessage.info(t('post.draftDiscarded'));
        });
    };

    const discardDraft = () => {
      clearDraft();
      ElMessage.success(t('post.draftCleared'));
    };

    // 输入变化后 800ms 写入草稿
    watch(
      () => [form.value.board, form.value.title, form.value.content],
      () => {
        if (draftTimer) clearTimeout(draftTimer);
        draftTimer = setTimeout(writeDraft, 800);
      },
    );

    const submitForm = async () => {
      try {
        await postForm.value.validate();
      } catch {
        ElMessage.warning(t('post.requiredFields'));
        return;
      }

      const content = Array.isArray(form.value.content)
        ? form.value.content.join('\n')
        : String(form.value.content || '').trim();

      if (!content) {
        ElMessage.error(t('msg.contentRequired'));
        return;
      }

      submitting.value = true;
      try {
        const postData = {
          board_id: form.value.board ? Number(form.value.board) : null,
          title: String(form.value.title || '').trim(),
          content,
        };
        // 第 86 批：作者自己填的英文（可选）。**只在非空时提交** ——
        // 后端对空的 *_en 会忽略，但少发一个字段更清楚，也避免"看起来像是要清空译文"。
        const titleEn = String(form.value.title_en || '').trim();
        const contentEn = String(form.value.content_en || '').trim();
        if (titleEn) postData.title_en = titleEn;
        if (contentEn) postData.content_en = contentEn;
        // 置顶/精华只有版主能设置（后端也会拦）
        if (isModerator.value) {
          postData.is_essence = !!form.value.is_essence;
          postData.is_pinned = !!form.value.is_pinned;
        }

        const response = await createPost(postData);
        clearDraft();
        // 第 97 批：提交成功 → 清掉"脏"标记，否则紧接着的 router.push 会被
        // 自己的离开守卫拦下来问一句"有未保存的修改"（很荒谬，但确实会）
        markClean();

        // 第 38 批：后端可能把帖子置为"待审核"（普通用户 + 开启审核策略）
        const created = response?.data ?? response;
        const newId = created?.id;
        if (created?.status === 'pending') {
          ElMessage.success(t('post.submittedForReview'));
        } else {
          ElMessage.success(t('post.postOk'));
        }

        router.push(newId ? { name: 'post-detail', params: { id: newId } } : { name: 'forum' });
      } catch (error) {
        console.error('发帖失败:', error);
        const errorData = error?.response?.data;
        let message = t('post.publishFailed');
        if (typeof errorData === 'string') message = errorData;
        else if (errorData?.detail) message = errorData.detail;
        else if (errorData?.message) message = errorData.message;
        else if (errorData && typeof errorData === 'object') {
          const parts = Object.entries(errorData).map(([field, messages]) =>
            `${field}: ${Array.isArray(messages) ? messages.join(', ') : messages}`,
          );
          if (parts.length) message = parts.join('；');
        } else if (error?.request) {
          message = t('msg.cannotConnect');
        }
        ElMessage.error(message);
      } finally {
        submitting.value = false;
      }
    };

    const resetForm = () => {
      form.value = {
        board: route.query.boardId ? parseInt(route.query.boardId, 10) : (boards.value[0]?.id ?? ''),
        title: '',
        content: '',
        title_en: '',
        content_en: '',
        is_essence: false,
        is_pinned: false,
      };
      postForm.value?.clearValidate();
      clearDraft();
    };

    const cancel = () => router.push({ name: 'forum' });

    onMounted(async () => {
      await Promise.all([fetchBoards(), loadSiteConfig()]);
      maybeRestoreDraft();
    });

    // ========================================================================
    // 第 97 批：离开前提醒（未保存的修改）
    // ------------------------------------------------------------------------
    // 此前**完全没有**拦截：新帖写了一半，点导航栏"论坛"就没了 ——
    // 草稿虽然有自动保存（30 秒），但最后一次改动之后的输入会丢。
    // 判定用"和空白表单比"而不是"设个 flag"：flag 要在每个输入框上挂事件，漏一个就失效。
    // ========================================================================
    // 判定"有没有值得留下的内容"：只看**文字字段**。
    // ⚠️ 不要算上 `board` 与两个勾选框：版块是进页面就默认选好的（表单里本来就有值），
    //    把它们算进去会让"刚打开页面、什么都没写"也判定为脏 —— 实测就是
    //    "点一下导航立刻被问要不要放弃修改"，属于误报。
    // 判定范围与草稿保存的范围保持一致（草稿存的也是这几个文字字段），
    // 避免"提示说会丢、其实草稿已经存了"或反过来的不一致。
    const DRAFT_FIELDS = ['title', 'content', 'title_en', 'content_en'];
    const { markClean } = useUnsavedChanges(() => {
      if (submitting.value) return false;   // 正在提交：不要拦
      const current = form.value || {};
      return DRAFT_FIELDS.some((key) => {
        const value = current[key];
        return String(Array.isArray(value) ? value.join('') : value ?? '').trim() !== '';
      });
    });

    onUnmounted(() => {
      if (draftTimer) clearTimeout(draftTimer);
    });

    return {
      form,
      rules,
      boards,
      loading,
      submitting,
      postForm,
      isModerator,
      needReview,
      footerHint,
      draftSavedAt,
      saveStatus,
      boardIconClass,
      submitForm,
      resetForm,
      cancel,
      discardDraft,
      // 第 86 批：可选英文版本的展开状态
      showEnglish,
      // 第 97 批：提交成功后清掉"脏"标记
      markClean,
      t,
      localizedField,
    };
  },
};
</script>

<style scoped>
.new-post {
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 24px 20px 40px;
}

.post-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 322px;
  gap: 18px;
  align-items: start;
  margin-top: 18px;
}

.post-main {
  min-width: 0;
}

/* 底部操作条沿用主题里的 .form-dialog-footer，只调整成卡片圆角 */
.post-footer {
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
}

.footer-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 版块下拉里的选项：图标 + 名称 + 说明 */
.board-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.board-option i {
  color: var(--brand-600);
}

.board-option-desc {
  margin-left: auto;
  font-size: 12px;
  color: var(--ink-400);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.field-hint {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--ink-400);
}

/* 第 86 批：可选的英文版本区块 */
.en-block :deep(.el-form-item__label) {
  width: 100%;
}

.en-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.en-label em {
  font-style: normal;
  font-weight: 400;
  color: var(--ink-400);
}

.en-toggle {
  margin-left: auto;
  border: none;
  background: transparent;
  color: var(--brand-500, #2f7d5d);
  font-size: 12px;
  cursor: pointer;
  text-decoration: underline;
}

.en-fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.field-hint i {
  margin-right: 4px;
  color: var(--brand-500);
}

/* 版主操作：两张可点的小卡 */
.moderator-ops {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  width: 100%;
}

.op-card {
  flex: 1 1 220px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--ink-50);
  cursor: pointer;
  transition: all 0.18s ease;
}

.op-card:hover {
  border-color: var(--brand-300);
}

.op-card.is-on {
  border-color: var(--brand-400);
  background: var(--brand-50);
}

.op-card small {
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--ink-500);
}

.op-card :deep(.el-checkbox__label) {
  font-weight: 700;
  color: var(--ink-800);
}

/* 草稿状态 */
.draft-status {
  font-size: 12.5px;
  color: var(--brand-700);
  font-weight: 600;
}

/* 侧栏 */
.post-side {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tips {
  margin: 0;
  padding: 0;
  list-style: none;
  counter-reset: tip;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tips li {
  position: relative;
  padding-left: 30px;
  counter-increment: tip;
}

.tips li::before {
  content: counter(tip);
  position: absolute;
  left: 0;
  top: 1px;
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 800;
  color: var(--brand-700);
  background: var(--brand-100);
}

.tips b {
  display: block;
  margin-bottom: 2px;
  font-size: 13.5px;
  color: var(--ink-800);
}

.tips p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-500);
}

.side-cta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 14px;
  padding: 10px 14px;
  border: 1px solid var(--brand-200);
  border-radius: var(--radius);
  background: linear-gradient(160deg, #ffffff, #f2faf6);
  font-size: 13.5px;
  font-weight: 700;
  color: var(--brand-700);
  text-decoration: none;
  transition: all 0.18s ease;
}

.side-cta:hover {
  border-color: var(--brand-400);
  transform: translateY(-1px);
  box-shadow: var(--shadow-xs);
}

.draft-line {
  margin: 0 0 10px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-500);
}

.draft-line i {
  margin-right: 4px;
  color: var(--brand-600);
}

.draft-clear {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 13px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-600);
  cursor: pointer;
  transition: all 0.18s ease;
}

.draft-clear:hover:not(:disabled) {
  border-color: var(--brand-300);
  color: var(--brand-700);
}

.draft-clear:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 1080px) {
  .post-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
