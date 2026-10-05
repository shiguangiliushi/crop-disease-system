<template>
  <div class="post-detail">
    <el-backtop target=".post-detail" :visibility-height="100" />

    <!-- 返回按钮 -->
    <el-button type="text" @click="goBack" class="back-btn">
      <i class="el-icon-arrow-left"></i> {{ t('forum.backToList') }}
    </el-button>

    <!-- 帖子内容区域 -->
    <el-card class="post-card" v-loading="loading">
      <div class="post-header">
        <h1 class="post-title">
          <el-tag v-if="post.is_pinned" size="small" type="danger" effect="dark">{{ t('forum.tagPinned') }}</el-tag>
          <el-tag v-if="post.is_essence" size="small" type="warning" effect="dark">{{ t('forum.tagEssence') }}</el-tag>
          <!-- 第 24 批：草稿角标（只有作者自己能看到自己的草稿） -->
          <el-tag v-if="post.status === 'draft'" size="small" type="info" effect="dark">{{ t('forum.tagDraft') }}</el-tag>
          {{ localizedField(post, 'title') }}
        </h1>
        <!-- 第 85 批：帖子正文的中英对照说明条（未翻译 / 译文过期 / 查看原文） -->
        <ContentTranslationBar
          :source="post"
          base="content"
          :show-original="showOriginalPost"
          :busy="translating"
          @toggle-original="showOriginalPost = !showOriginalPost"
          @translate="translatePost"
        />
        <div class="post-meta">
          <div class="author-info">
            <el-avatar :size="40" :src="post.author?.avatar || ''">
              {{ post.author?.username ? post.author.username[0].toUpperCase() : 'U' }}
            </el-avatar>
            <div class="author-meta">
              <span class="author-name">{{ post.author?.username || t('forum.unknownUser') }}</span>
              <span class="post-time">{{ formatTime(post.created_at) }}</span>
            </div>
          </div>
          <div class="post-actions">
            <el-button
              :type="post.is_liked ? 'danger' : 'default'"
              :icon="post.is_liked ? 'el-icon-star-on' : 'el-icon-star-off'"
              size="small"
              :loading="likeLoading"
              @click="handleLike"
            >
              {{ post.is_liked ? t('forum.liked') : t('forum.like') }} ({{ post.like_count || 0 }})
            </el-button>
            <!-- 第 25 批：看这条帖子被谁赞过 -->
            <el-button
              v-if="post.like_count > 0"
              size="small"
              text
              @click="openPostLikers"
            >
              <i class="fas fa-user-check"></i> {{ t('forum.likedBy') }}
            </el-button>
            <!-- 第 24 批：收藏按钮（后端接口一直存在，此前前端完全没用上） -->
            <el-button
              :type="post.is_favorited ? 'warning' : 'default'"
              :icon="post.is_favorited ? 'el-icon-star-on' : 'el-icon-star-off'"
              size="small"
              :loading="favoriteLoading"
              @click="handleFavorite"
            >
              {{ post.is_favorited ? t('forum.favorited') : t('forum.favorite') }}
            </el-button>
            <el-button size="small" @click="scrollToComment">
              <i class="el-icon-chat-dot-round"></i> {{ post.comment_count || 0 }}
            </el-button>
            <el-button v-if="isAuthor" type="text" @click="editPost">
              <i class="el-icon-edit"></i> {{ t('wiki.edit') }}
            </el-button>
            <!-- 第 41 批：举报（不是自己的帖子、且已登录时才显示） -->
            <el-button
              v-if="canReport"
              size="small"
              text
              type="danger"
              @click="openReport('post', post.id)"
            >
              <i class="fas fa-flag"></i> {{ t('report.entry') }}
            </el-button>
          </div>
        </div>
      </div>

      <div class="post-content" v-html="displayPostContent"></div>

      <div class="post-footer">
        <div class="post-tags">
          <el-tag v-if="post.board" size="small" type="info" effect="plain">
            {{ localizedField(post.board, 'name') }}
          </el-tag>
        </div>
        <div class="view-count">
          <i class="el-icon-view"></i> {{ t('forum.readCount', { count: post.view_count || 0 }) }}
        </div>
      </div>
    </el-card>

    <!-- 评论区域 -->
    <div class="comment-section" ref="commentSection">
      <div class="comment-header">
        <h3>{{ t('forum.commentsTitle', { count: comments.length }) }}</h3>
      </div>

      <!-- 评论表单 -->
      <div class="comment-form">
        <el-form :model="commentForm" :rules="commentRules" ref="formRef">
          <el-form-item prop="content">
            <el-input
              type="textarea"
              :rows="3"
              v-model="commentForm.content"
              :placeholder="isReplying ? t('forum.replyToPrefix', { name: commentForm.replyTo }) : t('forum.commentPlaceholder')"
              :maxlength="500"
              show-word-limit
              resize="none"
              :disabled="submitting"
              @keydown.enter.ctrl.prevent="handleSubmitComment"
              @keydown.esc="isReplying && cancelReply()"
            ></el-input>
          </el-form-item>
          <div class="form-actions">
            <el-button
              type="primary"
              size="small"
              @click="handleSubmitComment"
              :loading="submitting"
              :disabled="!commentForm.content.trim()"
            >
              <template v-if="submitting">
                <i class="el-icon-loading"></i> {{ t('forum.submitting') }}
              </template>
              <template v-else>
                <i class="el-icon-check"></i> {{ isReplying ? t('forum.reply') : t('forum.submitComment') }}
              </template>
            </el-button>
            <el-button
              v-if="isReplying"
              size="small"
              @click="cancelReply"
              :disabled="submitting"
            >
              {{ t('common.cancel') }}
            </el-button>
            <div class="keyboard-hint" v-else>
              {{ t('forum.keyboardHint') }} <kbd>Ctrl + Enter</kbd> {{ t('forum.keyboardHintTail') }}
            </div>
          </div>
        </el-form>
      </div>

      <!-- 评论列表 -->
      <div class="comment-list" ref="commentListRef" @scroll="handleScroll">
        <transition name="fade" mode="out-in">
          <div v-if="loadingComments" class="loading-comments">
            <el-skeleton
              v-for="i in 3"
              :key="i"
              :rows="3"
              animated
              class="comment-skeleton"
            />
          </div>
          <div v-else>
            <transition-group name="comment-list" tag="div">
              <div v-if="paginatedComments.length === 0" key="no-comments" class="no-comments">
                <el-empty :description="t('forum.noComments')" :image-size="120">
                  <template #description>
                    <p>{{ t('forum.firstComment') }}</p>
                  </template>
                </el-empty>
              </div>

              <div
                v-else
                v-for="comment in paginatedComments"
                :key="comment.id"
                :id="'comment-' + comment.id"
                class="comment-item"
              >
                <div class="comment-avatar">
                  <el-avatar :size="36" :src="comment.author?.avatar || ''">
                    {{ comment.author?.username ? comment.author.username[0].toUpperCase() : 'U' }}
                  </el-avatar>
                </div>
                <div class="comment-main">
                  <div class="comment-header">
                    <span class="comment-author">{{ comment.author?.username || t('forum.unknownUser') }}</span>
                    <span class="comment-time">{{ formatTime(comment.created_at) }}</span>
                    <div class="comment-actions">
                      <el-button
                        type="text"
                        size="small"
                        :class="{ 'liked': comment.is_liked }"
                        @click="handleCommentLike(comment)"
                      >
                        <i :class="comment.is_liked ? 'el-icon-star-on' : 'el-icon-star-off'"></i>
                        {{ comment.like_count || '' }}
                      </el-button>
                      <!-- 第 25 批：看这条评论被谁赞过 -->
                      <el-button
                        v-if="comment.like_count > 0"
                        type="text"
                        size="small"
                        @click="openCommentLikers(comment)"
                      >
                        {{ t('forum.likedBy') }}
                      </el-button>
                      <el-button
                        type="text"
                        size="small"
                        @click="handleReply(comment)"
                      >
                        {{ t('forum.reply') }}
                      </el-button>
                      <el-button
                        v-if="isCommentAuthor(comment)"
                        type="text"
                        size="small"
                        @click="handleEditComment(comment)"
                      >
                        {{ t('wiki.edit') }}
                      </el-button>
                      <el-button
                        v-if="isCommentAuthor(comment)"
                        type="text"
                        size="small"
                        @click="() => handleDeleteComment(comment.id)"
                      >
                        {{ t('wiki.delete') }}
                      </el-button>
                      <!-- 第 41 批：举报评论（不是自己的评论、且已登录时才显示） -->
                      <el-button
                        v-if="canReportComment(comment)"
                        type="text"
                        size="small"
                        class="report-comment-btn"
                        @click="openReport('comment', comment.id)"
                      >
                        <i class="fas fa-flag"></i> {{ t('report.entry') }}
                      </el-button>
                    </div>
                  </div>
                  <div class="comment-content" v-html="formatCommentContent(displayCommentContent(comment))"></div>
                  <!-- 第 85 批：评论译文状态（未翻译时给出"翻译"按钮） -->
                  <ContentTranslationBar
                    :source="comment"
                    base="content"
                    compact
                    :show-original="isOriginalShown(comment.id)"
                    :busy="translatingComment === comment.id"
                    @toggle-original="toggleOriginal(comment.id)"
                    @translate="translateComment(comment.id)"
                  />

                  <!-- 编辑评论（第 16 批补齐：此前只有函数、没有任何入口） -->
                  <div
                    v-if="editingComment === comment.id"
                    class="edit-comment-form"
                    :id="`edit-form-${comment.id}`"
                  >
                    <el-input
                      v-model="editContent"
                      type="textarea"
                      :rows="2"
                      :maxlength="1000"
                      :placeholder="t('forum.editCommentPlaceholder')"
                      show-word-limit
                    ></el-input>
                    <div class="form-actions">
                      <el-button
                        type="primary"
                        size="small"
                        :loading="submitting"
                        :disabled="!editContent.trim()"
                        @click="handleUpdateComment"
                      >
                        {{ t('forum.save') }}
                      </el-button>
                      <el-button
                        size="small"
                        :disabled="submitting"
                        @click="cancelEdit"
                      >
                        {{ t('common.cancel') }}
                      </el-button>
                    </div>
                  </div>

                  <!-- 回复表单 -->
                  <div
                    v-if="showReplyForm === comment.id"
                    class="reply-form"
                  >
                    <el-input
                      v-model="replyContent"
                      type="textarea"
                      :rows="2"
                      :maxlength="500"
                      :placeholder="t('forum.replyPlaceholder')"
                      show-word-limit
                    ></el-input>
                    <div class="form-actions">
                      <el-button
                        type="primary"
                        size="small"
                        @click="submitReply(comment)"
                        :loading="submittingReply"
                        :disabled="!replyContent.trim()"
                      >
                        {{ t('forum.reply') }}
                      </el-button>
                      <el-button
                        size="small"
                        @click="cancelReply"
                        :disabled="submittingReply"
                      >
                        {{ t('common.cancel') }}
                      </el-button>
                    </div>
                  </div>

                  <!-- 回复列表 -->
                  <!--
                    第 16 批修复：原条件 v-if="comment.replies.length > 0" 永远为假
                    （后端不在评论列表里内嵌回复），整块回复区（含「加载更多回复」
                    按钮）从不渲染 → 回复功能对用户完全不可见。
                    现只要有 reply_count 就渲染入口，由 loadMoreReplies 按需拉取。
                  -->
                  <div v-if="(comment.reply_count || 0) > 0" class="replies">
                    <div
                      v-for="reply in (comment.replies || [])"
                      :key="reply.id"
                      class="comment-item reply"
                    >
                      <div class="comment-avatar">
                        <el-avatar :size="32" :src="reply.author?.avatar || ''">
                          {{ reply.author?.username ? reply.author.username[0].toUpperCase() : 'U' }}
                        </el-avatar>
                      </div>
                      <div class="comment-main">
                        <div class="comment-header">
                          <span class="comment-author">{{ reply.author?.username || t('forum.unknownUser') }}</span>
                          <span v-if="reply.reply_to" class="reply-to">
                            {{ t('forum.replyToPrefix', { name: reply.reply_to.username }) }}
                          </span>
                          <span class="comment-time">{{ formatTime(reply.created_at) }}</span>
                          <div class="comment-actions">
                            <el-button
                              type="text"
                              size="small"
                              :class="{ 'liked': reply.is_liked }"
                              @click="handleCommentLike(reply)"
                            >
                              <i :class="reply.is_liked ? 'el-icon-star-on' : 'el-icon-star-off'"></i>
                              {{ reply.like_count || '' }}
                            </el-button>
                            <el-button
                              v-if="isCommentAuthor(reply)"
                              type="text"
                              size="small"
                              @click="handleEditComment(reply)"
                            >
                              {{ t('wiki.edit') }}
                            </el-button>
                            <el-button
                              v-if="isCommentAuthor(reply)"
                              type="text"
                              size="small"
                              @click="handleDeleteComment(reply.id)"
                            >
                              {{ t('wiki.delete') }}
                            </el-button>
                          </div>
                        </div>
                        <div class="comment-content" v-html="formatCommentContent(displayCommentContent(reply))"></div>
                        <!-- 第 85 批：回复同样支持译文/原文切换 -->
                        <ContentTranslationBar
                          :source="reply"
                          base="content"
                          compact
                          :show-original="isOriginalShown(reply.id)"
                          :busy="translatingComment === reply.id"
                          @toggle-original="toggleOriginal(reply.id)"
                          @translate="translateComment(reply.id)"
                        />

                        <!-- 编辑回复 -->
                        <div
                          v-if="editingComment === reply.id"
                          class="edit-comment-form"
                          :id="`edit-form-${reply.id}`"
                        >
                          <el-input
                            v-model="editContent"
                            type="textarea"
                            :rows="2"
                            :maxlength="1000"
                            :placeholder="t('forum.editReplyPlaceholder')"
                            show-word-limit
                          ></el-input>
                          <div class="form-actions">
                            <el-button
                              type="primary"
                              size="small"
                              :loading="submitting"
                              :disabled="!editContent.trim()"
                              @click="handleUpdateComment"
                            >
                              {{ t('forum.save') }}
                            </el-button>
                            <el-button
                              size="small"
                              :disabled="submitting"
                              @click="cancelEdit"
                            >
                              {{ t('common.cancel') }}
                            </el-button>
                          </div>
                        </div>
                      </div>
                    </div>

                    <!-- 查看/加载更多回复 -->
                    <div
                      v-if="(comment.replies || []).length < (comment.reply_count || 0)"
                      class="load-more-replies"
                    >
                      <el-button
                        type="text"
                        size="small"
                        @click="loadMoreReplies(comment)"
                        :loading="loadingMoreReplies === comment.id"
                      >
                        <span v-if="(comment.replies || []).length === 0">
                          {{ t('common.viewReplies', { count: comment.reply_count }) }}
                        </span>
                        <span v-else>
                          {{ t('common.loadMoreReplies', { count: comment.reply_count - comment.replies.length }) }}
                        </span>
                      </el-button>
                    </div>
                  </div>
                </div>
              </div>
            </transition-group>

            <!-- 加载更多评论 -->
            <div v-if="pagination.hasMore" class="load-more-comments">
              <el-button
                type="text"
                :loading="loadingMoreComments"
                @click="loadMoreComments"
                class="load-more-btn"
              >
                <span v-if="!loadingMoreComments">
                  <i class="el-icon-refresh"></i> {{ t('forum.loadMoreComments', { count: pagination.total - comments.length }) }}
                </span>
                <span v-else>{{ t('forum.loadingComments') }}</span>
              </el-button>
            </div>
          </div>
        </transition>
      </div>
    </div>

    <!-- 谁点赞了（第 25 批：帖子与每条评论共用） -->
    <LikersDialog
      v-model="likersDialog.visible"
      :type="likersDialog.type"
      :post-id="likersDialog.postId"
      :comment-id="likersDialog.commentId"
      :title="likersDialog.title"
    />

    <!-- 举报（第 41 批：帖子与评论共用同一个弹窗） -->
    <ReportDialog
      v-model="reportDialog.visible"
      :target-type="reportDialog.targetType"
      :target-id="reportDialog.targetId"
    />
  </div>
</template>

<script>
import { ref, onMounted, computed, watch, nextTick, getCurrentInstance, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { 
  getPost, 
  getComments, 
  incrementPostView, 
  toggleLike, 
  toggleFavorite,
  createComment, 
  deleteComment, 
  updateComment,
  toggleCommentLike,
  getCommentReplies,
  translatePost as translatePostContent,
  translateComment as translateCommentContent
} from '@/api/forum';
import { useUserStore } from '@/stores/user';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';
import { useLocalized } from '@/utils/localized';  // 第 60 批：多语言（第 72 批起也用于版块名等内容数据）
import { formatTime } from '@/utils/date';
// 身份读写统一走适配器（sessionStorage 优先）
import { getStoredUser } from '@/utils/authStorage';
// 第 25 批：「谁点赞了」弹窗（帖子与评论共用）
import LikersDialog from '@/components/LikersDialog.vue';
import ReportDialog from '@/components/ReportDialog.vue';  // 第 41 批：举报弹窗
// 第 85 批：帖子/评论的"译文状态"说明条（未翻译 / 已过期 / 查看原文）
import ContentTranslationBar from '@/components/ContentTranslationBar.vue';
// 第 91 批（安全）：帖子正文与评论都要进 v-html，必须先净化（存储型 XSS）
import { sanitizeRichText } from '@/utils/richText';

export default {
  name: 'PostDetailView',
  components: { LikersDialog, ReportDialog, ContentTranslationBar },
  setup() {
    const { t } = useI18n();  // 第 60 批：多语言
    const { localizedField, hasTranslation, isTranslationStale } = useLocalized();
    // 路由和状态管理
    const route = useRoute();
    const router = useRouter();
    const userStore = useUserStore();
    const authStore = useAuthStore();

    // 响应式数据
    const postId = ref(route.params.id);
    const post = ref({
      id: '',
      title: '',
      title_en: '',
      content: '',
      content_en: '',
      author: {},
      board: {},
      is_pinned: false,
      is_essence: false,
      is_liked: false,
      like_count: 0,
      comment_count: 0,
      view_count: 0,
      created_at: '',
      updated_at: ''
    });

    // ========================================================================
    // 第 85 批：用户内容的英文译文
    // ------------------------------------------------------------------------
    // 帖子/评论没法像界面文案那样预先写死译文，靠后端翻译（人工或机器）。
    // 这里负责三件事：
    //   ① 显示哪一份文本：英文界面且有译文 → 译文；否则原文；
    //   ② 读者可以手动切回原文（译文质量不理想时对照着看）；
    //   ③ 没有译文或译文过期时，提供"立即翻译"按钮 —— 调后端按需翻译接口，
    //      成功后把返回的字段合并进本地数据（不用整页刷新）。
    // ========================================================================
    const showOriginalPost = ref(false);
    const translating = ref(false);
    const translatingComment = ref(null);
    /** 手动切回原文的评论 id 集合（默认显示译文） */
    const originalCommentIds = ref([]);

    const isOriginalShown = (id) => originalCommentIds.value.includes(id);
    const toggleOriginal = (id) => {
      originalCommentIds.value = isOriginalShown(id)
        ? originalCommentIds.value.filter((item) => item !== id)
        : [...originalCommentIds.value, id];
    };

    /**
     * 帖子正文：英文界面 + 有译文 + 没手动切回原文 → 用译文
     *
     * 第 91 批（安全）：这里的结果直接给 `v-html`（模板第 88 行），
     * 而正文是**用户自己写的内容** —— 必须净化，否则一条带
     * `<img src=x onerror=...>` 的帖子会在每个读者浏览器里执行。
     */
    const displayPostContent = computed(() => {
      const raw = showOriginalPost.value
        ? (post.value.content || '')
        : localizedField(post.value, 'content');
      return sanitizeRichText(raw);
    });

    /**
     * 单条评论/回复的正文（同样规则）
     *
     * 这是修复前的**实际漏洞点**：正文经 formatCommentContent 只把 `\n` 换成 `<br>`，
     * 就直接进了模板第 247 / 379 行的 v-html，等于把评论内容当 HTML 执行。
     */
    const displayCommentContent = (comment) => {
      if (!comment) return '';
      const raw = isOriginalShown(comment.id)
        ? (comment.content || '')
        : localizedField(comment, 'content');
      return sanitizeRichText(raw);
    };

    const comments = ref([]);
    const loading = ref(true);
    const loadingComments = ref(true);
    const loadingMoreComments = ref(false);
    const loadingMoreReplies = ref(null);
    // 每次向上/向下加载回复的条数（与后端 replies 分页接口的 page_size 对应）
    const REPLIES_PAGE_SIZE = 5;
    const likeLoading = ref(false);
    const favoriteLoading = ref(false);
    // 第 25 批：「谁点赞了」弹窗（帖子与评论共用）
    const likersDialog = ref({
      visible: false,
      type: 'post',
      postId: null,
      commentId: null,
      title: t('likers.titleDefault'),
    });

    const openPostLikers = () => {
      likersDialog.value = {
        visible: true,
        type: 'post',
        postId: postId.value,
        commentId: null,
        title: t('likers.titlePost'),
      };
    };

    const openCommentLikers = (comment) => {
      likersDialog.value = {
        visible: true,
        type: 'comment',
        postId: postId.value,
        commentId: comment.id,
        title: t('likers.titleComment'),
      };
    };

    // ========================================================================
    // 举报（第 41 批）
    // ------------------------------------------------------------------------
    // 入口：帖子操作栏 + 每条评论（都不是自己发的内容才显示）。
    // 提交逻辑在 ReportDialog 组件里，这里只负责开关和选中目标。
    // ========================================================================
    const reportDialog = ref({ visible: false, targetType: 'post', targetId: null });

    const canReport = computed(
      () => Boolean(authStore.isAuthenticated) && !isAuthor.value,
    );

    const canReportComment = (comment) =>
      Boolean(authStore.isAuthenticated) && comment.author?.id !== authStore.user?.id;

    const openReport = (targetType, targetId) => {
      if (!authStore.isAuthenticated) {
        ElMessage.warning(t('msg.loginBeforeReport'));
        return;
      }
      reportDialog.value = { visible: true, targetType, targetId };
    };
    const submitting = ref(false);
    const submittingReply = ref(false);
    const showReplyForm = ref(null);
    const replyContent = ref('');
    const replyingTo = ref('');
    const commentForm = ref({
      content: '',
      parentId: null,
      replyTo: ''
    });
    
    // 添加缺失的响应式属性
    // ⚠️ 第 107 批：这里原本还有一个 `const totalComments = ref(0);` —— 已删。
    //    它只在一处被 `+= 1`，从来没有被读取（不在 setup 返回对象里、模板也不用），
    //    是纯死状态。评论总数以 `post.value.comment_count` 为准。
    const isReplying = ref(false);
    const commentRules = ref({
      content: [
        { required: true, message: t('forum.commentRequired'), trigger: 'blur' },
        { min: 1, max: 500, message: t('forum.commentMax'), trigger: 'blur' }
      ]
    });
    const formRef = ref(null);
    const commentSection = ref(null);
    const commentList = ref(null);
    const commentListRef = ref(null);
    const replyFormRefs = ref({});
    const replyFormRef = ref(null);  // 添加缺失的replyFormRef
    
    // 分页状态
    const pagination = ref({
      currentPage: 1,
      pageSize: 10,
      total: 0,
      hasMore: false,
      isLoading: false
    });
    
    // 是否是首次加载
    const isInitialLoad = ref(true);

    // 表单验证规则 (已在上方定义)

    // 计算属性
    const currentUser = computed(() => userStore.user);
    const isAuthor = computed(() => {
      return post.value.author && currentUser.value &&
             post.value.author.id === currentUser.value.id;
    });
    
    // 确保用户信息已加载
    onMounted(async () => {
      console.log('Current user from store:', userStore.user);
      console.log('Is authenticated:', authStore.isAuthenticated);
      console.log('Is admin:', userStore.isAdmin);
      
      // 如果用户已认证但用户信息未加载，尝试从本地存储加载
      if (authStore.isAuthenticated && !userStore.user) {
        try {
          // 从适配器读取（sessionStorage 优先，回退 localStorage）
          const parsedUser = getStoredUser();
          if (parsedUser) {
            userStore.setUser(parsedUser);
            console.log('User data loaded from storage:', parsedUser);
          } else {
            console.log('No user data found in storage');
          }
        } catch (error) {
          console.error('Error loading user data:', error);
        }
      }
    });
    
    // 检查当前用户是否是评论作者或管理员
    const isCommentAuthor = (comment) => {
      if (!authStore.isAuthenticated) return false;
      
      // 如果是管理员，允许删除
      if (userStore.isAdmin) return true;
      
      // 检查当前用户是否是评论作者
      const currentUserId = currentUser.value?.id || -1;
      const commentAuthorId = comment?.author?.id || -1;
      
      return currentUserId === commentAuthorId;
    };

    // 分页后的评论列表
    const paginatedComments = computed(() => {
      console.log('计算 paginatedComments，当前评论数:', comments.value?.length || 0);
      if (!Array.isArray(comments.value)) {
        console.warn('评论数据格式不正确:', comments.value);
        return [];
      }
      return [...comments.value];
    });

    const hasMoreComments = computed(() => {
      return pagination.value.hasMore;
    });

    // 辅助方法
    /**
     * 评论/回复正文：换行 → `<br>`
     *
     * 第 91 批（安全）：结果进 `v-html`，但**净化不在这一步做** ——
     * 调用方 displayCommentContent() 已经用 sanitizeRichText 净化过，
     * 这里再净化一次会把刚加上的 `<br>` 也当普通文本处理，得不偿失。
     */
    const formatCommentContent = (content) => {
      if (!content) return '';
      // 简单的换行处理
      return content.replace(/\n/g, '<br>');
    };

    // 获取帖子详情
    const fetchPost = async () => {
      try {
        loading.value = true;
        loadingComments.value = true;
        const data = await getPost(postId.value);
        console.log('获取到帖子详情:', data);
        
        post.value = { 
          ...data, 
          is_liked: data.is_liked || false, 
          is_favorited: data.is_favorited || false,
          status: data.status || 'published',
          like_count: data.like_count || 0, 
          comment_count: data.comment_count || 0, 
          view_count: data.view_count || 0 
        };
        
        // 只更新评论总数，不处理评论数据
        if (data.comment_count !== undefined) {
          pagination.value.total = data.comment_count;
          // 设置是否有更多评论可以加载
          pagination.value.hasMore = data.comment_count > 0;
          
          console.log('评论总数:', data.comment_count);
          
          // 确保 DOM 更新后滚动到评论区域
          nextTick(() => {
            if (comments.value.length > 0) {
              scrollToComment();
            }
          });
        }
        
        // 2. 增加浏览次数
        try {
          await incrementPostView(postId.value);
          // 更新本地视图计数，避免重新获取整个帖子
          post.value.view_count = (post.value.view_count || 0) + 1;
        } catch (error) {
          console.error('更新浏览次数失败:', error);
          // 这里不显示错误提示，避免影响用户体验
        }
      } catch (error) {
        console.error('获取帖子失败:', error);
        ElMessage.error(t('post.loadPostFailed'));
      } finally {
        loading.value = false;
        loadingComments.value = false;
      }
    };


    // ========================================================================
    // 第 85 批：「立即翻译」——按需给帖子/评论补英文译文
    // ------------------------------------------------------------------------
    // 发帖时后端会顺手翻一次，但接口可能超时/额度用完，老帖子也可能还没译文。
    // 这里给读者一个入口：点一下调后端 `/translate/`，成功后把返回的字段
    // **合并**进本地数据（只覆盖 *_en 与翻译状态，不动用户可能正在编辑的字段），
    // 不整页刷新，避免打断阅读位置。
    // ========================================================================
    const mergeTranslation = (target, payload) => {
      if (!target || !payload) return;
      ['title_en', 'content_en', 'translation_stale', 'translation_source'].forEach((key) => {
        if (key in payload) target[key] = payload[key];
      });
    };

    const translatePost = async () => {
      if (translating.value) return;
      translating.value = true;
      try {
        const data = await translatePostContent(postId.value);
        mergeTranslation(post.value, data);
        // 翻译成功的瞬间把视图切回译文（否则用户会以为"点了没反应"）
        showOriginalPost.value = false;
        ElMessage.success(t('trans.done'));
      } catch (error) {
        console.error('翻译帖子失败:', error);
        ElMessage.error(error?.message || t('trans.failed'));
      } finally {
        translating.value = false;
      }
    };

    const translateComment = async (commentId) => {
      if (translatingComment.value) return;
      translatingComment.value = commentId;
      try {
        const data = await translateCommentContent(postId.value, commentId);
        // 评论可能出现在顶级列表，也可能在某个评论的 replies 里，两处都找
        const all = [];
        for (const item of comments.value) {
          all.push(item);
          if (Array.isArray(item.replies)) all.push(...item.replies);
        }
        const target = all.find((item) => String(item.id) === String(commentId));
        mergeTranslation(target, data);
        originalCommentIds.value = originalCommentIds.value.filter((id) => id !== commentId);
        ElMessage.success(t('trans.done'));
      } catch (error) {
        console.error('翻译评论失败:', error);
        ElMessage.error(error?.message || t('trans.failed'));
      } finally {
        translatingComment.value = null;
      }
    };

    // 获取评论列表
    const fetchComments = async (loadMore = false) => {
      if ((loadingMoreComments.value && loadMore) || (loadingComments.value && !loadMore)) {
        console.log('正在加载中，跳过重复请求');
        return;
      }
      
      try {
        if (loadMore) {
          loadingMoreComments.value = true;
          pagination.value.currentPage++;
        } else {
          loadingComments.value = true;
          pagination.value.currentPage = 1;
          // 清空评论前先记录当前评论ID，用于去重
          const currentCommentIds = new Set(comments.value.map(c => c.id));
          console.log('当前已加载的评论ID:', Array.from(currentCommentIds));
          comments.value = [];
        }

        const params = {
          page: pagination.value.currentPage,
          page_size: pagination.value.pageSize,
          ordering: '-created_at',
          parent__isnull: true // 只获取顶级评论
        };

        console.log('正在获取评论，参数:', params);
        const response = await getComments(postId.value, params);
        console.log('获取到评论响应:', response);
        
        let results = response.results || [];
        const count = response.count || 0;
        const next = response.next;

        if (loadMore) {
          // 去重处理：过滤掉已存在的评论
          const currentCommentIds = new Set(comments.value.map(c => c.id));
          const newComments = results.filter(comment => !currentCommentIds.has(comment.id));
          console.log(`加载更多评论：新加载${results.length}条，去重后${newComments.length}条`);
          comments.value = [...comments.value, ...newComments];
        } else {
          // 首次加载或刷新
          console.log(`首次加载评论，共${results.length}条`);
          comments.value = results;
          pagination.value.total = count;
        }
        
        // 更新分页信息
        pagination.value.hasMore = !!next;
        
        console.log('更新后的评论列表:', comments.value);
        console.log('分页信息:', {
          hasMore: pagination.value.hasMore,
          currentPage: pagination.value.currentPage,
          total: pagination.value.total
        });
        
        // 如果是初始加载，滚动到评论区域
        if (isInitialLoad.value) {
          isInitialLoad.value = false;
          nextTick(() => {
            if (commentSection.value) {
              commentSection.value.scrollIntoView({ behavior: 'smooth' });
            }
          });
        }
      } catch (error) {
        console.error('获取评论失败:', error);
        ElMessage.error(t('post.loadCommentsFailed'));
      } finally {
        loadingComments.value = false;
        loadingMoreComments.value = false;
        pagination.value.isLoading = false;
      }
    };
    
    // 滚动加载更多
    const handleScroll = () => {
      if (loadingMoreComments.value || !pagination.value.hasMore) return;
      
      const container = commentListRef.value;
      if (!container) return;
      
      const scrollPosition = container.scrollTop + container.clientHeight;
      const scrollHeight = container.scrollHeight;
      
      // 当滚动到距离底部100px时加载更多
      if (scrollHeight - scrollPosition < 100) {
        loadMoreComments();
      }
    };
    
    // 监听滚动事件
    onMounted(() => {
      const container = commentListRef.value;
      if (container) {
        container.addEventListener('scroll', handleScroll);
      }
    });
    
    onBeforeUnmount(() => {
      const container = commentListRef.value;
      if (container) {
        container.removeEventListener('scroll', handleScroll);
      }
    });

    // 取消回复
    const cancelReply = () => {
      commentForm.value = {
        content: '',
        parentId: null,
        replyTo: ''
      };
      isReplying.value = false;
    };
    
    // 提交评论
    const handleSubmitComment = async () => {
      if (submitting.value) return;
      
      // 检查用户是否已登录
      if (!authStore.isAuthenticated) {
        ElMessage.warning(t('msg.loginBeforeComment'));
        router.push({ 
          name: 'login', 
          query: { 
            redirect: route.fullPath,
            from: 'comment'  // 添加来源标识
          } 
        });
        return;
      }

      try {
        // 验证评论内容
        const content = commentForm.value.content.trim();
        if (!content) {
          ElMessage.warning(t('post.commentEmpty'));
          return;
        }
        
        if (content.length > 1000) {
          ElMessage.warning(t('post.commentMaxLength'));
          return;
        }
        
        submitting.value = true;
        
        // 确保postId是数字类型
        const currentPostId = Number(route.params.id);
        if (isNaN(currentPostId)) {
          throw new Error(t('msg.invalidPostId'));
        }
        
        const commentData = {
          content: content,
          parent: commentForm.value.parentId ? Number(commentForm.value.parentId) : null
        };
        
        console.log('提交评论数据:', commentData);

        // 创建评论
        const newComment = await createComment(currentPostId, commentData);
        
        if (!newComment) {
          throw new Error(t('msg.serverEmptyResponse'));
        }
        
        // 显示成功消息
        ElMessage.success(commentForm.value.parentId ? t('post.replyOk') : t('post.commentOk'));

        // 更新评论列表
        if (commentForm.value.parentId) {
          // 回复评论
          const parentComment = comments.value.find(c => c.id === commentForm.value.parentId);
          if (parentComment) {
            if (!parentComment.replies) {
              parentComment.replies = [];
            }
            parentComment.replies.unshift({
              ...newComment,
              author: { ...currentUser.value },
              is_liked: false,
              like_count: 0,
              can_edit: true,  // 添加可编辑权限
              can_delete: true, // 添加可删除权限
              is_author: true  // 标记为当前用户发表的评论
            });
            parentComment.reply_count = (parentComment.reply_count || 0) + 1;
          }
        } else {
          // 新评论
          comments.value.unshift({
            ...newComment,
            author: { ...currentUser.value },
            replies: [],
            reply_count: 0,
            is_liked: false,
            like_count: 0,
            can_edit: true,  // 添加可编辑权限
            can_delete: true, // 添加可删除权限
            is_author: true  // 标记为当前用户发表的评论
          });
        }
        
        // 更新评论计数
        //
        // ⚠️ 第 107 批：删掉了紧跟其后的一行 `totalComments.value += 1`。
        //    那个 ref 只被写、从来没有被读（模板与 setup 返回对象里都没有它），
        //    属于"看起来在维护一个计数、实际没人用"的死状态 ——
        //    留着会让人以为某处显示着"评论总数"，从而不敢动它。
        //    真正的计数以 `post.value.comment_count` 为准（下一行）。
        post.value.comment_count = (post.value.comment_count || 0) + 1;
        
        // 重置表单
        commentForm.value = {
          content: '',
          parentId: null,
        };
        
        // 重置回复表单状态
        showReplyForm.value = null;
        replyingTo.value = '';
        
        // 清空回复表单
        commentForm.value = {
          content: '',
          parentId: null,
          replyTo: ''
        };
        
        // 重置表单验证
        if (formRef.value) {
          formRef.value.resetFields();
        }
      } catch (error) {
        console.error('提交评论失败:', error);
        ElMessage.error(error.message || (commentForm.value.parentId ? t('post.replyFailed') : t('post.commentFailed')));
      } finally {
        submitting.value = false;
      }
    };

    // 处理回复评论
    const handleReply = (comment) => {
      if (!authStore.isAuthenticated) {
        ElMessage.warning(t('msg.loginRequired'));
        router.push({ name: 'login', query: { redirect: route.fullPath } });
        return;
      }
      
      // 设置当前正在回复的评论ID
      showReplyForm.value = comment.id;
      
      // 清空回复内容
      replyContent.value = '';
      
      commentForm.value = {
        content: '',
        parentId: comment.id,
        replyTo: comment.author?.username || t('profile.defaultUser')
      };

      // 滚动到评论框
      nextTick(() => {
        const formElement = document.querySelector('.comment-form');
        if (formElement) {
          formElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      });
    };


    // 提交回复
    const submitReply = async (comment) => {
      if (!replyContent.value.trim()) {
        ElMessage.warning(t('post.replyEmpty'));
        return;
      }

      try {
        submittingReply.value = true;
        const currentPostId = Number(route.params.id);
        const response = await createComment(currentPostId, {
          content: replyContent.value.trim(),
          parent: comment.id
        });

        // 更新回复列表
        if (!comment.replies) {
          comment.replies = [];
        }
        comment.replies.unshift({
          ...response,
          author: currentUser.value
        });
        comment.reply_count = (comment.reply_count || 0) + 1;
        
        // 清空回复内容并关闭回复表单
        replyContent.value = '';
        showReplyForm.value = null;

        // 更新帖子评论数
        post.value.comment_count = (post.value.comment_count || 0) + 1;

        // 重置表单
        replyContent.value = '';
        showReplyForm.value = null;
        ElMessage.success(t('post.replyOk'));
        
        // 刷新评论列表
        fetchComments();
      } catch (error) {
        console.error('回复失败:', error);
        ElMessage.error(error.response?.data?.detail || t('post.replyFailedRetry'));
      } finally {
        submittingReply.value = false;
      }
    };

    // 加载更多评论
    const loadMoreComments = () => {
      if (!hasMoreComments.value || loadingMoreComments.value) return;
      fetchComments(true);
    };

    // 编辑评论
    //
    // 第 16 批修复：这一整块此前是**死代码** —— 函数没有从 setup 返回、模板里也没有
    // 任何编辑入口；而且 handleUpdateComment 里把 `editingComment.value`（存的是
    // 评论 id，数字）当成对象读 `.id`，即使接上也会请求
    // `/comments/undefined/`。现修正 id 取值并补上界面入口。
    const editingComment = ref(null);
    const editContent = ref('');
    
    // 处理编辑评论
    const handleEditComment = (comment) => {
      editingComment.value = comment.id;
      editContent.value = comment.content;
      
      // 滚动到编辑框
      nextTick(() => {
        const editForm = document.querySelector(`#edit-form-${comment.id}`);
        if (editForm) {
          editForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      });
    };
    
    // 取消编辑
    const cancelEdit = () => {
      editingComment.value = null;
      editContent.value = '';
    };
    
    // 更新评论
    const handleUpdateComment = async () => {
      if (submitting.value || !editingComment.value) return;

      const commentId = editingComment.value;
      const content = editContent.value.trim();

      if (!content) {
        ElMessage.warning(t('post.commentEmpty'));
        return;
      }
      if (content.length > 1000) {
        ElMessage.warning(t('post.commentMaxLength'));
        return;
      }

      try {
        submitting.value = true;

        const response = await updateComment(postId.value, commentId, {
          content: content
        });

        // 顶级评论与回复都要能找到
        const comment = comments.value.find(c => c.id === commentId) ||
                       comments.value.flatMap(c => [c, ...(c.replies || [])]).find(c => c.id === commentId);

        if (comment) {
          comment.content = response?.content ?? content;
          if (response?.updated_at) {
            comment.updated_at = response.updated_at;
          }
        }

        // 重置编辑状态
        editingComment.value = null;
        editContent.value = '';

        ElMessage.success(t('post.commentUpdated'));
      } catch (error) {
        console.error('更新评论失败:', error);
        ElMessage.error(error.response?.data?.detail || error.message || t('post.updateCommentFailed'));
      } finally {
        submitting.value = false;
      }
    };
    
    // 回复相关状态
    //
    // ⚠️ 第 107 批：删掉了这里的"折叠展开"一套（原第 1285-1325 行）：
    //      showReplies / loadingReplies / getReplies / toggleReplies / fetchReplies
    //
    // 为什么删：它们**没有任何外部引用** —— 既没出现在 setup 的返回对象里，
    // 也没在模板里出现过（逐个 grep 确认）。模板真正走的是 `loadMoreReplies`
    // （见第 1330 行那段说明与模板第 435 行的「查看回复/加载更多回复」按钮），
    // 也就是"回复区一直可见 + 按钮渐进加载"这套，靠的是 `comment.replies` 数组本身。
    //
    // 为什么不是"接线"而是"删"：
    //   · 折叠展开属于**另一套交互设计**（回复默认收起、点「查看 N 条回复」才展开），
    //     而现在的渐进加载已经能满足需求，且第 16 批还专门修过它的渲染条件；
    //   · 把这五个函数接回模板，等于同时存在两套控制"回复可见性"的状态
    //     （`showReplies` 与 `comment.replies.length`），必然打架。
    //   · 留着不标记是最坏的选择：下一个人会以为"折叠功能坏了"去修它，
    //     而它从来没被接线（同文件第 16/17 批已经记录过两次同类缺陷）。
    // 真要做折叠，应当**重写**而不是复活这几个函数。
    //
    // 注意：`fetchReplies` 虽然也是死的，但它引用的 `getCommentReplies`
    // 与 `REPLIES_PAGE_SIZE` 仍被 `loadMoreReplies` 使用，所以那两个保留。

    /**
     * 加载更多回复
     *
     * 第 16 批补齐：模板里一直有「加载更多回复」按钮并绑定 loadMoreReplies /
     * loadingMoreReplies，但**两者都没有从 setup 返回**（loadingMoreReplies 甚至
     * 没有对应函数）→ 点击必然报错，回复列表无法展开。
     * 现按已加载条数推算下一页，与后端 replies 分页接口对接。
     */
    const loadMoreReplies = async (comment) => {
      if (!comment || !comment.id) return;
      if (loadingMoreReplies.value === comment.id) return;

      if (!Array.isArray(comment.replies)) {
        comment.replies = [];
      }

      loadingMoreReplies.value = comment.id;
      try {
        const nextPage = Math.floor(comment.replies.length / REPLIES_PAGE_SIZE) + 1;
        const response = await getCommentReplies(postId.value, comment.id, {
          page: nextPage,
          page_size: REPLIES_PAGE_SIZE
        });

        const incoming = response.results || [];
        const loadedIds = new Set(comment.replies.map(r => r.id));
        comment.replies = [...comment.replies, ...incoming.filter(r => !loadedIds.has(r.id))];

        // 后端返回的 count 是该评论的回复总数，作为权威值校正 reply_count
        if (typeof response.count === 'number' && response.count >= 0) {
          comment.reply_count = response.count;
        }
      } catch (error) {
        console.error('加载更多回复失败:', error);
        ElMessage.error(error.response?.data?.detail || error.message || t('post.loadRepliesFailedRetry'));
      } finally {
        loadingMoreReplies.value = null;
      }
    };
    
    // 处理删除评论
    const handleDeleteComment = async (commentId) => {
      if (!commentId) {
        console.error('删除评论失败: 评论ID不能为空');
        ElMessage.error(t('msg.nothingToDelete'));
        return;
      }

      if (!postId.value) {
        console.error('删除评论失败: 帖子ID不能为空');
        ElMessage.error(t('msg.missingPostInfo'));
        return;
      }

      try {
        await ElMessageBox.confirm(t('post.deleteCommentConfirm'), t('msg.confirmDelete'), {
          confirmButtonText: t('msg.confirmDelete'),
          cancelButtonText: t('msg.cancel'),
          type: 'warning',
          confirmButtonClass: 'el-button--danger'
        });

        // 显示加载状态
        const loading = ElMessage({
          message: t('msg.deletingComment'),
          type: 'info',
          duration: 0
        });

        try {
          console.log(`正在删除帖子 ${postId.value} 的评论 ${commentId}`);
          // 调用API删除评论，需要传入帖子ID和评论ID
          await deleteComment(postId.value, commentId);
          
          // 从评论列表中移除被删除的评论
          const removeComment = (commentsList) => {
            return commentsList.reduce((acc, comment) => {
              // 过滤掉被删除的评论
              if (comment.id === commentId) {
                console.log(`从评论列表中移除评论 ${commentId}`);
                return acc;
              }

              // 处理回复
              if (comment.replies && comment.replies.length > 0) {
                const originalCount = comment.replies.length;
                comment.replies = comment.replies.filter(reply => reply.id !== commentId);
                if (originalCount !== comment.replies.length) {
                  // 第 17 批修复：这里原来写的是 comment.reply_count = comment.replies.length，
                  // 即把「已加载条数」当成「回复总数」。而回复是按页加载的——
                  // 一旦只加载了 5/10 条时删掉 1 条，总数会被写成 4，
                  // 「加载更多回复」按钮随之消失，剩下 5 条再也拉不出来（除非刷新）。
                  // 正确做法：在原有的总数上减 1（没有 total 时退回已加载条数）。
                  comment.reply_count = Math.max(
                    0,
                    (comment.reply_count || originalCount) - 1
                  );
                  console.log(`从回复中移除了评论 ${commentId}`);
                }
              }

              acc.push(comment);
              return acc;
            }, []);
          };

          // 更新评论列表
          const newComments = removeComment([...comments.value]);
          
          // 更新帖子评论数
          const oldCount = post.value.comment_count || 0;
          const newCount = Math.max(0, oldCount - 1);
          post.value.comment_count = newCount;
          console.log(`更新评论数: ${oldCount} -> ${newCount}`);
          
          // 更新评论列表
          comments.value = newComments;
          
          // 更新分页总数
          if (pagination.value.total > 0) {
            pagination.value.total--;
          }
          
          // 如果当前页没有评论了，且不是第一页，则回到上一页
          if (comments.value.length === 0 && pagination.value.currentPage > 1) {
            pagination.value.currentPage--;
            // 重新加载上一页的评论
            await fetchComments();
          }
          
          ElMessage.success(t('post.commentDeleted'));
        } catch (error) {
          console.error('删除评论失败:', error);
          ElMessage.error(t('msg.deleteFailedWith', { detail: error.response?.data?.detail || error.message || t('msg.unknownError') }));
        } finally {
          loading.close();
        }
      } catch (error) {
        // 用户取消删除
        if (error !== 'cancel') {
          console.error('删除评论出错:', error);
        }
      }
    };

    // 编辑帖子
    const editPost = () => {
      router.push({ name: 'edit-post', params: { id: postId.value } });
    };

    // 返回上一页
    const goBack = () => {
      router.go(-1);
    };

    // 滚动到评论区域
    const scrollToComment = () => {
      nextTick(() => {
        if (commentSection.value) {
          commentSection.value.scrollIntoView({ 
            behavior: 'smooth',
            block: 'start'
          });
          
          // 如果评论框存在，则自动聚焦
          const commentInput = document.querySelector('.comment-form textarea');
          if (commentInput) {
            commentInput.focus();
          }
        }
      });
    };

    // 滚动并高亮定位到某条评论（第 25 批：从用户资料页点评论跳过来时使用）
    const scrollToTargetComment = async (commentId) => {
      if (!commentId) return;
      // 目标评论可能还没加载出来（按页加载），尝试多加载几页再找
      for (let attempt = 0; attempt < 4; attempt += 1) {
        await nextTick();
        const el = document.getElementById(`comment-${commentId}`);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.classList.add('comment-highlight');
          setTimeout(() => el.classList.remove('comment-highlight'), 2400);
          return;
        }
        if (!hasMoreComments?.value) break;
        await fetchComments(true);
      }
      // 兜底：找不到具体评论时至少滚到评论区
      scrollToComment();
    };

    onMounted(async () => {
      // 先获取帖子详情
      await fetchPost();
      // 然后获取评论
      await fetchComments();
      
      console.log('初始评论加载完成，当前评论数:', comments.value.length);

      // 检查URL中是否有评论锚点
      if (route.hash === '#comments') {
        nextTick(() => {
          scrollToComment();
        });
      }

      // 第 25 批：?comment=<id> → 定位到该评论（用户资料页点评论跳过来）
      if (route.query.comment) {
        scrollToTargetComment(route.query.comment);
      }
    });

    // 监听路由参数变化
    watch(() => route.params.id, (newId) => {
      if (newId && newId !== postId.value) {
        postId.value = newId;
        fetchPost();
      }
    });

    // 收藏 / 取消收藏（第 24 批接入）
    const handleFavorite = async () => {
      if (favoriteLoading.value) return;

      if (!authStore.isAuthenticated) {
        ElMessage.warning(t('msg.loginRequired'));
        router.push({ name: 'login', query: { redirect: route.fullPath } });
        return;
      }

      favoriteLoading.value = true;
      const original = post.value.is_favorited;
      try {
        post.value.is_favorited = !original;              // 乐观更新
        const result = await toggleFavorite(postId.value);
        if (result && typeof result.is_favorited === 'boolean') {
          post.value.is_favorited = result.is_favorited;  // 以服务端返回为准
        }
        ElMessage.success(post.value.is_favorited ? t('msg.favoriteAdded') : t('msg.favoriteRemoved'));
      } catch (error) {
        post.value.is_favorited = original;               // 失败回滚
        console.error('收藏操作失败:', error);
        ElMessage.error(t('msg.operationFailedWith', { detail: error.response?.data?.detail || error.message }));
      } finally {
        favoriteLoading.value = false;
      }
    };

    // 处理帖子点赞/取消点赞
    const handleLike = async () => {
      if (likeLoading.value) return;
      
      likeLoading.value = true;
      const originalLikeStatus = post.value.is_liked;
      const originalLikeCount = post.value.like_count;
      
      console.log('开始点赞/取消点赞，当前状态:', originalLikeStatus, '点赞数:', originalLikeCount);
      
      try {
        // 1. 立即更新UI，提升用户体验
        post.value.is_liked = !originalLikeStatus;
        post.value.like_count = originalLikeStatus 
          ? Math.max(0, originalLikeCount - 1) 
          : (originalLikeCount || 0) + 1;
        
        // 2. 发送点赞/取消点赞请求
        const response = await toggleLike({ post: postId.value });
        console.log('点赞API返回:', response);
        
        // 3. 显示操作成功提示
        ElMessage.success(post.value.is_liked ? t('msg.likeOk') : t('msg.unlikeOk'));
        
        // 4. 重新获取帖子详情以确保数据同步
        try {
          const postData = await getPost(postId.value);
          console.log('重新获取的帖子数据:', postData);
          
          // 保留当前UI状态，只更新其他字段
          post.value = {
            ...postData,
            is_liked: post.value.is_liked, // 保持当前UI状态
            like_count: postData.like_count // 使用服务器返回的点赞数
          };
        } catch (fetchError) {
          console.warn('获取最新帖子数据失败，使用本地状态:', fetchError);
          // 如果获取最新数据失败，保持当前UI状态
        }
      } catch (error) {
        console.error('操作失败:', error);
        
        // 恢复原始状态
        post.value.is_liked = originalLikeStatus;
        post.value.like_count = originalLikeCount;
        
        // 显示错误提示
        const errorMessage = error.response?.data?.detail || t('msg.operationFailedRetry');
        console.error('点赞操作失败详情:', errorMessage);
        ElMessage.error(errorMessage);
      } finally {
        likeLoading.value = false;
      }
    };
    
    // 处理评论点赞/取消点赞
    const handleCommentLike = async (comment) => {
      if (!comment || !comment.id) {
        console.error('无效的评论数据');
        return;
      }
      
      try {
        console.log(`正在${comment.is_liked ? '取消点赞' : '点赞'}评论 ${comment.id}`);
        // 评论接口是嵌套路由，需要带上帖子 ID
        const result = await toggleCommentLike(postId.value, comment.id);

        // 第 16 批：后端点赞接口已改为返回权威状态（is_liked / like_count），
        // 优先采用服务端值；旧响应（只有 detail）时退回本地翻转。
        if (result && typeof result.is_liked === 'boolean') {
          comment.is_liked = result.is_liked;
          if (typeof result.like_count === 'number') {
            comment.like_count = result.like_count;
          }
        } else {
          comment.is_liked = !comment.is_liked;
          comment.like_count = Math.max(0, (comment.like_count || 0) + (comment.is_liked ? 1 : -1));
        }

        ElMessage.success(result?.detail || (comment.is_liked ? t('msg.likeOk') : t('msg.unlikeOk')));
      } catch (error) {
        console.error('操作失败:', error);
        ElMessage.error(error.response?.data?.detail || error.message || t('msg.operationFailedRetry'));
      }
    };

    // 返回所有需要的方法和响应式数据
    return {
      // 响应式数据
      t,
      localizedField,
      // 第 85 批：用户内容的译文（显示哪一份 / 查看原文 / 立即翻译）
      showOriginalPost,
      translating,
      translatingComment,
      displayPostContent,
      displayCommentContent,
      isOriginalShown,
      toggleOriginal,
      translatePost,
      translateComment,
      post,
      comments,
      loading,
      loadingComments,
      loadingMoreComments,  // 添加这一行
      likeLoading,
      submitting,
      submittingReply,
      showReplyForm,
      replyContent,
      loadingMoreReplies,
      loadMoreReplies,
      commentForm,
      commentRules,
      formRef,
      commentSection,
      commentListRef,
      pagination,
      paginatedComments,
      hasMoreComments,
      isReplying,
      
      // 计算属性
      currentUser,
      isAuthor,
      isCommentAuthor,
      
      // 方法
      handleLike,
      handleFavorite,
      favoriteLoading,
      likersDialog,
      openPostLikers,
      // 举报（第 41 批）
      reportDialog,
      canReport,
      canReportComment,
      openReport,
      openCommentLikers,
      handleCommentLike,
      handleSubmitComment,
      handleReply,
      cancelReply,
      submitReply,
      handleDeleteComment,
      handleEditComment,
      cancelEdit,
      handleUpdateComment,
      editingComment,
      editContent,
      loadMoreComments,
      handleScroll,
      editPost,
      goBack,
      scrollToComment,
      formatTime,
      formatCommentContent
    };
  }
}
</script>

<style scoped>
.load-more-comments {
  text-align: center;
  margin: 20px 0;
  padding: 10px 0;
  position: relative;
  z-index: 1;
  
  &::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 0;
    right: 0;
    height: 1px;
    background-color: #ebeef5;
    z-index: -1;
  }
  
  .el-button {
    background-color: #fff;
    padding: 0 20px;
    
    &:hover {
      background-color: #f5f7fa;
    }
  }
}

.load-more-btn {
  width: 100%;
  min-height: 44px;
  padding: 12px 0;
  color: var(--brand-700, #1f6343);
  font-size: 15px;
  border-radius: var(--radius-sm, 10px);
  transition: all 0.3s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.load-more-btn:hover {
  background-color: var(--brand-50, #f1f9f4);
  color: var(--brand-800, #194f37);
}

.load-more-btn i {
  margin-right: 6px;
  font-size: 16px;
  transition: transform 0.3s;
}

.load-more-btn:hover i {
  transform: rotate(180deg);
}

.post-detail {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
  position: relative;
}

.back-btn {
  position: absolute;
  left: 20px;
  top: 20px;
  z-index: 10;
}

.post-card {
  margin-top: 30px;
  margin-bottom: 30px;
}

.post-header {
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid #eee;
}

.post-title {
  margin: 0 0 15px 0;
  font-size: 24px;
  line-height: 1.4;
}

.post-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #666;
  font-size: 14px;
}

.author-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.author-meta {
  display: flex;
  flex-direction: column;
}

.author-name {
  font-weight: 500;
  color: #333;
}

.post-time {
  font-size: 12px;
  color: #999;
}

.post-content {
  line-height: 1.8;
  word-break: break-word;
}

/* 确保按钮有足够的空间显示文本 */
.post-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

/* 确保按钮文本可见 */
.post-actions .el-button {
  min-width: 80px;
  padding: 8px 15px;
  white-space: nowrap;
  overflow: visible;
}

/* 确保图标和文字之间有间距 */
.post-actions .el-button [class*="el-icon-"] + span {
  margin-left: 5px;
}

.post-actions {
  margin-top: 30px;
  padding-top: 15px;
  border-top: 1px solid #eee;
  display: flex;
  gap: 10px;
}

.comment-section {
  margin-top: 30px;
  padding: 20px 0;
}

.comment-header {
  margin-bottom: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.comment-form {
  margin-bottom: 30px;
  background: #f9f9f9;
  padding: 20px;
  border-radius: 4px;
}

.form-actions {
  margin-top: 10px;
  text-align: right;
}

.comment-list {
  margin-top: 20px;
}

.comment-item {
  padding: 15px 0;
  border-bottom: 1px solid #eee;
}

.comment-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
}

.comment-actions {
  display: flex;
  gap: 10px;
}

.comment-content {
  margin-left: 50px;
  line-height: 1.6;
}

.reply-form {
  margin: 10px 0 10px 50px;
  padding: 10px;
  background: #f5f5f5;
  border-radius: 4px;
}

/* 评论编辑表单（第 16 批新增入口，样式与回复表单保持一致） */
.edit-comment-form {
  margin: 10px 0 10px 50px;
  padding: 10px;
  background: #f5f5f5;
  border-radius: 4px;
}

.reply-item {
  margin: 10px 0;
  padding: 10px;
  background: #f9f9f9;
  border-radius: 4px;
}

.load-more {
  text-align: center;
  margin: 20px 0;
}

.loading-comments {
  padding: 20px 0;
}

.no-comments {
  text-align: center;
  padding: 40px 0;
  color: #999;
}

/* 动画效果 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.comment-list-enter-active,
.comment-list-leave-active {
  transition: all 0.3s ease;
}

.comment-list-enter-from,
.comment-list-leave-to {
  opacity: 0;
  transform: translateX(30px);
}

.comment-list-move {
  transition: transform 0.3s;
}

/* 点赞按钮样式 */
.is-liked {
  color: #f56c6c;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .post-detail {
    padding: 10px;
  }

  .post-title {
    font-size: 20px;
  }

  .post-meta {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .post-actions {
    flex-wrap: wrap;
  }

  .comment-content {
    margin-left: 0;
    padding-left: 10px;
  }

  .reply-form {
    margin-left: 20px;
  }
  
  .post-detail {
    max-width: 1000px;
    margin: 0 auto;
    padding: 20px;
  }
  
  .post-card {
    margin-bottom: 20px;
  }
  
  .comment-section {
    margin-top: 20px;
  }
}

/* ================= 现代化覆写（设计变量见 assets/theme.css） ================= */
.post-detail {
  width: 100%;
  max-width: 1000px;
  margin: 0 auto;
  padding: 8px 24px 48px;
  box-sizing: border-box;
}

.post-card {
  padding: 32px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background: var(--surface);
  box-shadow: var(--shadow-md);
}

.post-header {
  padding-bottom: 18px;
  margin-bottom: 22px;
  border-bottom: 1px solid var(--border);
}

.post-title {
  margin: 0 0 16px;
  font-size: 26px;
  font-weight: 800;
  line-height: 1.45;
  color: var(--ink-900);
}

.author-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.author-name {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--ink-800);
}

.author-meta,
.post-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px;
  font-size: 12.5px;
  color: var(--ink-400);
}

.post-time,
.view-count {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.post-content {
  font-size: 15px;
  line-height: 2;
  color: var(--ink-700);
  word-break: break-word;
}

.post-content :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: var(--radius);
}

.post-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 22px;
}

.post-footer,
.post-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 24px;
  padding-top: 18px;
  border-top: 1px solid var(--border);
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 20px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-pill);
  background: var(--surface);
  color: var(--ink-600);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--dur) var(--ease);
}

.back-btn:hover {
  border-color: var(--brand-400);
  background: var(--brand-50);
  color: var(--brand-700);
}

/* 评论区 */
.comment-section {
  margin-top: 22px;
  padding: 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.comment-form {
  margin-bottom: 22px;
}

.comment-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.comment-item {
  display: flex;
  gap: 14px;
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-muted);
  transition: border-color var(--dur) var(--ease);
}

.comment-item:hover {
  border-color: var(--brand-200);
}

/* 第 25 批：从用户资料页跳过来定位到某条评论时的高亮反馈 */
.comment-item.comment-highlight {
  border-color: var(--brand-500, #2f7d4f);
  box-shadow: 0 0 0 3px rgba(47, 125, 79, 0.14);
  animation: comment-highlight-fade 2.4s ease forwards;
}

@keyframes comment-highlight-fade {
  0%, 60% { background: rgba(47, 125, 79, 0.08); }
  100% { background: var(--surface-muted); }
}

.comment-avatar {
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--gradient-brand);
  color: #fff;
  font-size: 15px;
  font-weight: 700;
}

.comment-main {
  flex: 1;
  min-width: 0;
}

.comment-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.comment-author {
  font-size: 14px;
  font-weight: 700;
  color: var(--ink-800);
}

/* 回复目标（第 16 批新增：后端开始返回 reply_to 后展示） */
.reply-to {
  font-size: 12px;
  color: var(--brand-700, #2f7d4f);
  background: var(--brand-50, #eef7f1);
  border-radius: 999px;
  padding: 1px 8px;
}

.comment-time {
  font-size: 12px;
  color: var(--ink-400);
}

.comment-content {
  font-size: 14px;
  line-height: 1.85;
  color: var(--ink-700);
}

.comment-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 10px;
  font-size: 12.5px;
  color: var(--ink-500);
}

.comment-skeleton {
  padding: 18px;
  border-radius: var(--radius-lg);
  background: var(--ink-50);
}

.no-comments,
.loading-comments {
  padding: 32px 20px;
  text-align: center;
  font-size: 14px;
  color: var(--ink-400);
}

.keyboard-hint {
  font-size: 12px;
  color: var(--ink-400);
}

@media (max-width: 768px) {
  .post-detail {
    padding: 0 16px 32px;
  }

  .post-card,
  .comment-section {
    padding: 20px 18px;
  }

  .post-title {
    font-size: 20px;
  }
}
</style>
