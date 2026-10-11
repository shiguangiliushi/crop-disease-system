<template>
  <div class="user-profile">
    <div class="profile-header">
      <el-button type="text" @click="goBack" class="back-btn">
        <i class="el-icon-arrow-left"></i> {{ t('profile.back') }}
      </el-button>
      <h2>{{ t('profile.title') }}</h2>
    </div>

    <div class="profile-container">
      <!-- 错误提示 -->
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        show-icon
        class="error-alert"
        :closable="false"
      />

      <!-- 加载中状态 -->
      <div v-else-if="loading" class="loading-container">
        <el-skeleton :rows="5" animated />
      </div>

      <template v-else>
        <el-card class="profile-card">
          <div class="profile-avatar">
            <!-- 真实头像（第 23 批新增 CustomUser.avatar）。
                 没有头像时 el-avatar 会显示下面的首字母插槽 —— 不再依赖
                 ui-avatars.com 这个外网占位图服务（断网/内网部署会整片裂图）。 -->
            <el-avatar :size="100" :src="user.avatar || undefined">
              {{ user.username ? user.username[0].toUpperCase() : 'U' }}
            </el-avatar>
            <div v-if="isCurrentUser" class="avatar-actions">
              <el-upload
                :auto-upload="false"
                :show-file-list="false"
                accept="image/*"
                :on-change="handleAvatarChange"
              >
                <el-button size="small" type="primary" plain :loading="uploadingAvatar">
                  <i class="bi bi-image"></i> {{ user.avatar ? t('profile.changeAvatar') : t('profile.uploadAvatar') }}
                </el-button>
              </el-upload>
              <el-button
                v-if="user.avatar"
                size="small"
                type="danger"
                plain
                :loading="uploadingAvatar"
                @click="handleRemoveAvatar"
              >
                {{ t('profile.remove') }}
              </el-button>
            </div>
            <p v-if="isCurrentUser" class="avatar-hint">{{ t('profile.avatarHint') }}</p>
          </div>
          
          <div class="profile-info">
            <div class="profile-name-row">
              <h3>{{ user.username || t('profile.defaultUser') }}</h3>
              <el-button
                v-if="isCurrentUser"
                type="primary"
                plain
                size="small"
                class="edit-profile-btn"
                @click="openEditDialog"
              >
                <i class="bi bi-pencil-square"></i> {{ t('profile.editProfile') }}
              </el-button>
              <el-button
                v-if="isCurrentUser"
                plain
                size="small"
                class="change-password-btn"
                @click="openPasswordDialog"
              >
                <i class="bi bi-shield-lock"></i> {{ t('profile.changePassword') }}
              </el-button>

              <!-- 第 40 批：关注 / 取消关注（看自己的主页时不显示） -->
              <el-button
                v-if="canFollow"
                :type="isFollowing ? 'default' : 'primary'"
                size="small"
                class="follow-btn"
                :loading="followLoading"
                @click="handleFollow"
              >
                <i :class="isFollowing ? 'fas fa-user-check' : 'fas fa-user-plus'"></i>
                {{ isFollowing ? t('profile.following') : t('profile.follow') }}
              </el-button>

              <!-- 第 41 批：举报该用户 -->
              <el-button
                v-if="canFollow"
                size="small"
                text
                type="danger"
                class="report-user-btn"
                @click="reportDialogVisible = true"
              >
                <i class="fas fa-flag"></i> {{ t('profile.report') }}
              </el-button>

              <!-- 第 42 批：发私信 -->
              <el-button
                v-if="canFollow"
                size="small"
                plain
                class="message-user-btn"
                @click="goToMessages"
              >
                <i class="fas fa-envelope"></i> {{ t('profile.message') }}
              </el-button>
            </div>

            <!-- 第 42 批：等级徽章 + 积分进度 -->
            <div v-if="pointsInfo" class="level-row">
              <span class="level-badge" :class="`is-lv${pointsInfo.level}`">
                <!-- 第 79 批：等级名来自后端固定的等级表（原来只有中文，英文界面下显示「Lv.1 新手」） -->
                <i class="fas fa-medal"></i> Lv.{{ pointsInfo.level }} {{ localizedField(pointsInfo, 'level_name') }}
              </span>
              <span class="level-points">{{ t('profile.points', { count: pointsInfo.points }) }}</span>
              <div class="level-progress" :title="progressTitle">
                <span class="level-progress-bar" :style="{ width: `${pointsInfo.progress}%` }"></span>
              </div>
              <span v-if="pointsInfo.next_level_points" class="level-next">
                {{ t('profile.toNextLevel', { count: pointsInfo.next_level_points - pointsInfo.points }) }}
              </span>
              <button
                v-else
                type="button"
                class="level-next is-max"
              >
                {{ t('profile.maxLevel') }}
              </button>
            </div>

            <p class="profile-realname" v-if="user.first_name || user.last_name">
              {{ user.first_name }} {{ user.last_name }}
            </p>

            <p class="profile-email" v-if="isCurrentUser && user.email">
              <i class="bi bi-envelope"></i> {{ user.email }}
            </p>

            <p class="profile-bio" v-if="user.bio">{{ user.bio }}</p>

            <p class="join-date" v-if="user.date_joined || user.join_date">
              <i class="el-icon-date"></i> {{ t('profile.joinedAt', { time: formatDate(user.date_joined || user.join_date) }) }}
            </p>
            <p v-else class="join-date">
              <i class="el-icon-date"></i> {{ t('profile.registeredUnknown') }}
            </p>
            
            <div class="stats">
              <div class="stat-item">
                <div class="stat-value">{{ user.post_count || 0 }}</div>
                <div class="stat-label">{{ t('profile.statPosts') }}</div>
              </div>
              <div class="stat-item">
                <div class="stat-value">{{ user.comment_count || 0 }}</div>
                <div class="stat-label">{{ t('profile.statComments') }}</div>
              </div>
              <div class="stat-item">
                <div class="stat-value">{{ user.like_count || 0 }}</div>
                <div class="stat-label">{{ t('profile.statLikes') }}</div>
              </div>
              <!-- 第 40 批：关注 / 粉丝（可点开列表，支持回关） -->
              <div class="stat-item is-clickable" @click="openFollowDialog('following')">
                <div class="stat-value">{{ followingCount }}</div>
                <div class="stat-label">{{ t('profile.statFollowing') }}</div>
              </div>
              <div class="stat-item is-clickable" @click="openFollowDialog('followers')">
                <div class="stat-value">{{ followerCount }}</div>
                <div class="stat-label">{{ t('profile.statFollowers') }}</div>
              </div>
            </div>
          </div>
        </el-card>

      </template>

      <el-tabs v-model="activeTab" class="profile-tabs" v-if="!loading && !error">
        <el-tab-pane :label="t('profile.tabPosts')" name="posts">
          <div v-if="postsLoading" class="loading-container">
            <el-skeleton :rows="5" animated />
          </div>
          <div v-else-if="posts.length === 0" class="empty-tip">
            <el-empty :description="t('profile.emptyPosts')" />
          </div>
          <div v-else class="post-list">
            <div v-for="post in posts" :key="post.id" class="post-item">
              <div class="post-content" @click="goToPost(post.id)">
                <h4>
                  <el-tag v-if="post.is_pinned" size="mini" type="danger" effect="dark">{{ t('forum.tagPinned') }}</el-tag>
                  <el-tag v-if="post.is_essence" size="mini" type="warning" effect="dark">{{ t('forum.tagEssence') }}</el-tag>
                  <el-tag v-if="post.status === 'draft'" size="mini" type="info" effect="dark">{{ t('forum.tagDraft') }}</el-tag>
                  {{ localizedField(post, 'title') || t('forum.untitled') }}
                </h4>
                <div class="post-meta">
                  <!-- 第 25 批：显示"发在哪里" -->
                  <span v-if="post.board" class="post-board" @click.stop="goToBoard(post.board.id)">
                    <i class="fas fa-layer-group"></i> {{ localizedField(post.board, 'name') }}
                  </span>
                  <span><i class="fas fa-eye"></i> {{ post.view_count || 0 }}</span>
                  <span><i class="fas fa-comment"></i> {{ post.comment_count || 0 }}</span>
                  <span class="post-time">{{ post.created_at ? formatDate(post.created_at) : t('forum.unknownTime') }}</span>
                </div>
              </div>
              <div class="post-actions">
                <!-- 第 25 批：谁点赞了 -->
                <el-button size="small" text @click.stop="openPostLikers(post)">
                  <i class="fas fa-thumbs-up"></i> {{ t('profile.likedByCount', { count: post.like_count || 0 }) }}
                </el-button>
                <el-button
                  v-if="isCurrentUser"
                  type="danger"
                  size="small"
                  circle
                  @click.stop="confirmDeletePost(post)"
                  class="delete-btn"
                >
                  <i class="fas fa-trash"></i>
                </el-button>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <!-- 第 25 批新增：该用户发表的评论，并显示"发在哪里" -->
        <el-tab-pane :label="t('profile.tabComments', { count: commentsTotal })" name="comments">
          <div v-if="commentsLoading" class="loading-container">
            <el-skeleton :rows="5" animated />
          </div>
          <div v-else-if="comments.length === 0" class="empty-tip">
            <el-empty :description="t('profile.emptyComments')" />
          </div>
          <div v-else class="comment-list">
            <div v-for="comment in comments" :key="comment.id" class="comment-item">
              <div class="comment-content" @click="goToComment(comment)">
                <p class="comment-text">{{ localizedField(comment, 'content') }}</p>
                <div class="comment-meta">
                  <span class="comment-source" @click.stop="goToComment(comment)">
                    <i class="fas fa-location-dot"></i>
                    {{ t('profile.fromPost', { title: localizedField(comment, 'post_title') || t('profile.unknownPost') }) }}
                    <template v-if="comment.board_name">· {{ localizedField(comment, 'board_name') }}</template>
                  </span>
                  <span v-if="comment.reply_to" class="comment-reply-to">
                    <i class="fas fa-reply"></i> {{ t('forum.replyToPrefix', { name: comment.reply_to.username }) }}
                  </span>
                  <span class="comment-time">{{ formatDate(comment.created_at) }}</span>
                </div>
              </div>
              <div class="comment-actions">
                <el-button size="small" text @click.stop="openCommentLikers(comment)">
                  <i class="fas fa-thumbs-up"></i> {{ t('profile.likedByCount', { count: comment.like_count || 0 }) }}
                </el-button>
                <el-button size="small" text @click.stop="goToComment(comment)">
                  <i class="fas fa-arrow-up-right-from-square"></i> {{ t('profile.viewOriginal') }}
                </el-button>
              </div>
            </div>

            <div v-if="commentsTotal > comments.length" class="more-comments">
              <el-button :loading="commentsLoading" @click="loadMoreComments">{{ t('profile.loadMoreComments') }}</el-button>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>

      <!--
        危险区：注销账号（第 95 批）
        ------------------------------------------------------------------
        在此之前**没有注销入口**：隐私政策里写着"如需注销账号请通过意见反馈提出申请"，
        等于全靠人工，而管理端也删不了账号。现在用户自己就能注销。

        为什么单独一块"危险区"而不是并到上面的按钮里：
        注销不可逆，把它和"编辑资料/修改密码"放一起，误点的代价太大。
      -->
      <el-card v-if="isCurrentUser" class="danger-zone">
        <template #header>
          <div class="danger-zone-head">
            <i class="bi bi-exclamation-triangle"></i>
            <span>{{ t('profile.dangerZone') }}</span>
          </div>
        </template>
        <div class="danger-zone-body">
          <div>
            <p class="danger-zone-title">{{ t('profile.deleteAccount') }}</p>
            <p class="danger-zone-desc">{{ t('profile.deleteAccountDesc') }}</p>
          </div>
          <el-button type="danger" plain @click="openDeleteAccount">
            {{ t('profile.deleteAccountAction') }}
          </el-button>
        </div>
      </el-card>
    </div>

    <!-- 注销账号确认弹窗（第 95 批） -->
    <el-dialog
      v-model="deleteAccountVisible"
      :title="t('profile.deleteAccount')"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-alert type="error" :closable="false" show-icon class="delete-alert">
        <p>{{ t('profile.deleteAccountWarning') }}</p>
        <ul class="delete-list">
          <li>{{ t('profile.deleteAccountItem1') }}</li>
          <li>{{ t('profile.deleteAccountItem2') }}</li>
          <li>{{ t('profile.deleteAccountItem3') }}</li>
        </ul>
      </el-alert>

      <!--
        第 101 批：把"冷静期"这件事说在最显眼处
        ------------------------------------------------------------------
        改前是"点一下立刻删、不可恢复"；现在申请后**有 15 天可以反悔**。
        这是对用户最有利的一条信息，不能藏在按钮说明里 —— 所以单独一条绿色提示。
      -->
      <el-alert type="success" :closable="false" show-icon class="grace-alert">
        <p>{{ t('profile.deleteAccountGrace', { days: graceDays }) }}</p>
        <p class="grace-sub">{{ t('profile.deleteAccountGraceHow') }}</p>
      </el-alert>
      <el-form label-position="top" class="delete-form">
        <el-form-item :label="t('profile.deleteAccountPasswordLabel')">
          <el-input
            v-model="deleteAccountPassword"
            type="password"
            show-password
            autocomplete="current-password"
            :placeholder="t('profile.deleteAccountPasswordPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('profile.deleteAccountConfirmLabel', { word: deleteAccountWord })">
          <el-input v-model="deleteAccountConfirm" :placeholder="deleteAccountWord" autocomplete="off" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deleteAccountVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button
          type="danger"
          :loading="deleteAccountLoading"
          :disabled="deleteAccountConfirm.trim() !== deleteAccountWord || !deleteAccountPassword"
          @click="confirmDeleteAccount"
        >
          {{ t('profile.deleteAccountConfirmAction') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 谁点赞了（第 25 批新增，帖子与评论共用） -->
    <LikersDialog
      v-model="likersDialog.visible"
      :type="likersDialog.type"
      :post-id="likersDialog.postId"
      :comment-id="likersDialog.commentId"
      :title="likersDialog.title"
    />

    <!-- 资料编辑弹窗（仅本人可打开） -->
    <el-dialog
      v-model="editDialogVisible"
      :title="t('profile.editDialogTitle')"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-form label-width="80px" @submit.prevent>
        <el-form-item :label="t('profile.usernameLabel')">
          <el-input :model-value="user.username" disabled />
        </el-form-item>
        <el-form-item :label="t('profile.lastName')">
          <el-input v-model="editForm.last_name" maxlength="30" :placeholder="t('profile.optional')" />
        </el-form-item>
        <el-form-item :label="t('profile.firstName')">
          <el-input v-model="editForm.first_name" maxlength="30" :placeholder="t('profile.optional')" />
        </el-form-item>
        <el-form-item :label="t('profile.emailLabel')">
          <el-input v-model="editForm.email" :placeholder="t('profile.emailHint')" />
        </el-form-item>
        <el-form-item :label="t('profile.bioLabel')">
          <el-input
            v-model="editForm.bio"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            :placeholder="t('profile.bioPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">{{ t('profile.cancel') }}</el-button>
        <el-button type="primary" :loading="savingProfile" @click="submitProfileEdit">{{ t('profile.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 修改密码弹窗（仅本人）—— 第 23 批新增 -->
    <el-dialog
      v-model="passwordDialogVisible"
      :title="t('profile.passwordTitle')"
      width="460px"
      :close-on-click-modal="false"
    >
      <el-form label-width="90px" @submit.prevent>
        <el-form-item :label="t('profile.currentPassword')">
          <el-input v-model="pwdForm.oldPassword" type="password" show-password :placeholder="t('profile.currentPasswordPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('profile.newPassword')">
          <el-input v-model="pwdForm.newPassword" type="password" show-password :placeholder="t('profile.newPasswordHint')" />
        </el-form-item>
        <el-form-item :label="t('profile.confirmPassword')">
          <el-input v-model="pwdForm.confirmPassword" type="password" show-password :placeholder="t('profile.confirmPasswordPlaceholder')" />
        </el-form-item>
      </el-form>
      <p class="password-hint">
        {{ t('profile.passwordTokenNote') }}
      </p>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">{{ t('profile.cancel') }}</el-button>
        <el-button type="primary" :loading="changingPassword" @click="submitPasswordChange">{{ t('profile.confirmChange') }}</el-button>
      </template>
    </el-dialog>

    <!-- 关注 / 粉丝列表（第 40 批） -->
    <el-dialog
      v-model="followDialogVisible"
      :title="followDialogTab === 'followers' ? t('profile.followers') : t('profile.followingList')"
      width="460px"
    >
      <div class="follow-tabs">
        <button
          type="button"
          class="follow-tab"
          :class="{ 'is-active': followDialogTab === 'followers' }"
          @click="switchFollowTab('followers')"
        >
          {{ t('profile.followers') }} {{ followerCount }}
        </button>
        <button
          type="button"
          class="follow-tab"
          :class="{ 'is-active': followDialogTab === 'following' }"
          @click="switchFollowTab('following')"
        >
          {{ t('profile.followingList') }} {{ followingCount }}
        </button>
      </div>

      <el-skeleton v-if="followLoading" :rows="4" animated />
      <el-empty v-else-if="followList.length === 0" :description="followDialogTab === 'followers' ? t('profile.emptyFollowers') : t('profile.emptyFollowing')" :image-size="70" />

      <ul v-else class="follow-list">
        <li v-for="item in followList" :key="item.id" class="follow-item">
          <!-- 第 113 批：点头像 → 开私信 -->
          <UserAvatarLink
            :size="38"
            :user-id="item.id"
            :username="item.username"
            :avatar="item.avatar"
          />
          <div class="follow-info" @click="goToUserProfile(item.id)">
            <span class="follow-name">{{ item.username }}</span>
            <span class="follow-bio">{{ item.bio || t('profile.noBio') }}</span>
          </div>
          <el-button
            v-if="!item.is_self && authStore.isAuthenticated"
            size="small"
            :type="item.is_following ? 'default' : 'primary'"
            :loading="followActionId === item.id"
            @click.stop="toggleItemFollow(item)"
          >
            {{ item.is_following ? t('profile.following') : t('profile.follow') }}
          </el-button>
        </li>
      </ul>
    </el-dialog>

    <!-- 举报用户（第 41 批） -->
    <ReportDialog
      v-model="reportDialogVisible"
      target-type="user"
      :target-id="userId"
    />
  </div>
</template>

<script>
// 用户资料（自己 / 他人）
// 路由：/user/profile/:id
//
// 页面由五块组成：
//   1) 资料卡（头像上传、昵称、简介、专家身份）
//   2) 统计（发帖 / 评论 / 识别 / 获赞）
//   3) 我的发帖 / 我的评论（两个列表，各带分页）
//   4) 修改密码（第 23 批加的入口；**密码策略见 backend/api/password_policy.py**）
//   5) 危险操作：注销账号（第 95 批加入口，第 101 批改成 15 天冷静期）
//
// 改这个文件前值得知道的几件事：
//   · 第 5 块是本页最容易出事的地方 —— 冷静期语义（申请后立刻登不上、
//     但个人信息保留、15 天内可取消）写在那段模板注释与后端
//     AccountDeleteView / AccountCancelDeletionView 的 docstring 里。
//     **改文案前先读它们**，别把"可取消"写成"不可撤销"；
//   · 头像上传是 2MB + 白名单类型，比新闻/论坛的 5MB 更严；
//   · 看别人的资料时第 2、3 块只读，第 5 块整块不渲染（判断在 isSelf）。
import { ref, onMounted, computed, watch } from 'vue';
import { goBackOr } from '@/utils/navigation';  // 第 165 批：返回兜底
import { useI18n } from '@/i18n';
import { useLocalized } from '@/utils/localized';  // 第 64 批：多语言（第 72 批起也用于版块名等内容数据）
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  getUserProfile,
  getUserPosts,
  getMyPosts,
  deletePost,
  // 第 23 批新增：真实头像 + 修改密码
  uploadAvatar,
  deleteAvatar,
  changePassword,
  // 第 25 批新增：该用户的评论（带"发在哪里"的上下文）
  getUserComments,
} from '@/api/forum';
import { useAuthStore } from '@/stores/auth';
import http, { formatApiError } from '@/api/http';
// 第 25 批：「谁点赞了」弹窗（帖子与评论共用）
import LikersDialog from '@/components/LikersDialog.vue';
import ReportDialog from '@/components/ReportDialog.vue';  // 第 41 批：举报弹窗
import { fetchFollowers, fetchFollowing, toggleFollow } from '@/api/social';  // 第 40 批：关注/粉丝
// 第 95 批：自助注销账号
import { DELETE_ACCOUNT_CONFIRM_WORD, deleteMyAccount } from '@/api/account';
import { useUnsavedChanges } from '@/composables/useUnsavedChanges';  // 第 97 批：离开前提醒
import UserAvatarLink from '@/components/UserAvatarLink.vue';

export default {
  name: 'UserProfileView',
  components: { LikersDialog, ReportDialog, UserAvatarLink },
  
  setup() {
    const { t } = useI18n();  // 第 64 批：多语言
    const { localizedField } = useLocalized();
    const route = useRoute();
    const router = useRouter();
    
    // 确保userId是数字类型
    const userId = ref(parseInt(route.params.id, 10));
    
    // 监听路由参数变化，当用户从其他用户资料页面跳转时更新数据
    watch(() => route.params.id, (newId) => {
      if (newId) {
        userId.value = parseInt(newId, 10);
        fetchUserProfile();
      }
    });
    const user = ref({
      username: t('profile.loadingUser'),
      avatar: '',
      bio: t('profile.noBioYet'),
      join_date: new Date().toISOString(),
      post_count: 0,
      comment_count: 0,
      like_count: 0,
      date_joined: new Date().toISOString() // 添加默认的date_joined字段
    });
    
    const posts = ref([]);
    const loading = ref(true);
    const postsLoading = ref(false); // 添加帖子加载状态
    const error = ref(null);
    const activeTab = ref('posts');
    const authStore = useAuthStore();

    // ---------- 第 25 批：评论列表 + 谁点赞了 ----------
    const comments = ref([]);
    const commentsTotal = ref(0);
    const commentsLoading = ref(false);
    const commentsPage = ref(1);
    const commentsPageSize = 10;

    // 「谁点赞了」弹窗状态（帖子与评论共用同一个弹窗实例）
    const likersDialog = ref({
      visible: false,
      type: 'post',
      postId: null,
      commentId: null,
      title: t('likers.titleDefault'),
    });

    const openPostLikers = (post) => {
      likersDialog.value = {
        visible: true,
        type: 'post',
        postId: post.id,
        commentId: null,
        title: t('likers.titlePostNamed', { title: post.title || t('common.untitled') }),
      };
    };

    const openCommentLikers = (comment) => {
      likersDialog.value = {
        visible: true,
        type: 'comment',
        postId: comment.post_id,
        commentId: comment.id,
        title: t('likers.titleComment'),
      };
    };

    const loadComments = async (reset = true) => {
      commentsLoading.value = true;
      try {
        if (reset) commentsPage.value = 1;
        const data = await getUserComments(userId.value, {
          page: commentsPage.value,
          page_size: commentsPageSize,
        });
        comments.value = reset ? (data.results || []) : [...comments.value, ...(data.results || [])];
        commentsTotal.value = data.count || 0;
      } catch (err) {
        console.error('获取用户评论失败:', err);
        if (reset) {
          comments.value = [];
          commentsTotal.value = 0;
        }
        ElMessage.error(formatApiError(err, t('profile.loadCommentsFailed')));
      } finally {
        commentsLoading.value = false;
      }
    };

    const loadMoreComments = async () => {
      commentsPage.value += 1;
      await loadComments(false);
    };

    // 跳到"这条评论所在的帖子"，并定位到该评论（PostDetailView 会读 ?comment=）
    const goToComment = (comment) => {
      if (!comment?.post_id) return;
      router.push({
        name: 'post-detail',
        params: { id: comment.post_id },
        query: { comment: comment.id },
      });
    };

    // 跳到"发在哪个版块"
    const goToBoard = (boardId) => {
      if (!boardId) return;
      router.push({ name: 'forum-board', params: { id: boardId } });
    };
    
    // 检查当前浏览的用户是否是登录用户
    const isCurrentUser = computed(() => {
      return authStore.user?.id?.toString() === userId.value?.toString();
    });

    // ========================================================================
    // 关注 / 粉丝（第 40 批）
    // ------------------------------------------------------------------------
    // 数据来源：`/api/users/{id}/` 现在会带 following_count / follower_count /
    // is_following / is_self（两种资料序列化器都有），所以进页面就有数，不用额外请求。
    // ========================================================================
    const followLoading = ref(false);
    const followActionId = ref(null);
    const followDialogVisible = ref(false);
    const reportDialogVisible = ref(false);  // 第 41 批：举报该用户
    const followDialogTab = ref('followers');
    const followList = ref([]);

    const followerCount = computed(() => Number(user.value.follower_count || 0));
    const followingCount = computed(() => Number(user.value.following_count || 0));
    const isFollowing = computed(() => Boolean(user.value.is_following));
    /** 只有"登录了 + 看的不是自己"才显示关注按钮 */
    const canFollow = computed(() => authStore.isAuthenticated && !isCurrentUser.value);

    const handleFollow = async () => {
      if (!canFollow.value) return;
      followLoading.value = true;
      try {
        const data = await toggleFollow(userId.value);
        user.value = {
          ...user.value,
          is_following: data.is_following,
          follower_count: data.follower_count,
        };
        ElMessage.success(data.is_following ? t('profile.followOk') : t('profile.unfollowOk'));
      } catch (error) {
        ElMessage.error(formatApiError(error, t('msg.operationFailedRetry')));
      } finally {
        followLoading.value = false;
      }
    };

    const loadFollowList = async (tab = followDialogTab.value) => {
      followLoading.value = true;
      try {
        const fetcher = tab === 'followers' ? fetchFollowers : fetchFollowing;
        const data = await fetcher(userId.value, { page_size: 50 });
        followList.value = data?.results || [];
      } catch (error) {
        console.warn('加载关注列表失败:', error);
        followList.value = [];
      } finally {
        followLoading.value = false;
      }
    };

    const openFollowDialog = (tab) => {
      followDialogTab.value = tab;
      followDialogVisible.value = true;
      loadFollowList(tab);
    };

    const switchFollowTab = (tab) => {
      if (followDialogTab.value === tab) return;
      followDialogTab.value = tab;
      loadFollowList(tab);
    };

    /** 在列表里直接关注/取关某个人 */
    const toggleItemFollow = async (item) => {
      followActionId.value = item.id;
      try {
        const data = await toggleFollow(item.id);
        item.is_following = data.is_following;

        // 若正在看"自己关注的人"这个列表，取关后把它移除更符合直觉
        if (followDialogTab.value === 'following' && !data.is_following) {
          followList.value = followList.value.filter((row) => row.id !== item.id);
        }

        // 同步页面上的计数（第 40 批：一开始漏了这一步，导致"在弹窗里回关后，
        // 主页的『关注』数还是 0"）：
        //   · 在**自己的主页**操作 → 自己的"关注"数变化（following_count）
        //   · 操作的对象正好是**当前页面的主人** → 他的"粉丝"数变化（follower_count）
        const patch = {};
        if (isCurrentUser.value) {
          patch.following_count = data.following_count;
        }
        if (item.id === Number(userId.value)) {
          patch.is_following = data.is_following;
          patch.follower_count = data.follower_count;
        }
        if (Object.keys(patch).length) {
          user.value = { ...user.value, ...patch };
        }
      } catch (error) {
        ElMessage.error(formatApiError(error, t('msg.operationFailed')));
      } finally {
        followActionId.value = null;
      }
    };

    const goToUserProfile = (id) => {
      if (!id) return;
      followDialogVisible.value = false;
      // ⚠️ 第 112 批修：路由名是 `user-profile`，这里原来写成了驼峰的 `userProfile`。
      //    名字无效时 vue-router 只打 warn 不跳转 —— 后果是"在关注/粉丝列表里
      //    点某个人，弹窗关了但页面没动"，很容易被当成"点错了"。
      router.push({ name: 'user-profile', params: { id } });
    };

    // ========================================================================
    // 等级与积分（第 42 批）
    // ------------------------------------------------------------------------
    // 资料接口的 `points` 字段已经是 {points, level, level_name, next_level_points, progress}
    // 汇总（后端 points_summary 算好的），这里直接展示，不用再请求。
    // ========================================================================
    const pointsInfo = computed(() => {
      const value = user.value.points;
      return value && typeof value === 'object' ? value : null;
    });

    const progressTitle = computed(() => {
      const info = pointsInfo.value;
      if (!info) return '';
      return info.next_level_points
        ? t('profile.pointsProgress', { points: info.points, next: info.next_level_points })
        : t('profile.pointsMax', { points: info.points });
    });

    /** 私信：跳到私信页并直接打开与 TA 的会话 */
    const goToMessages = () => {
      if (!isCurrentUser.value && user.value.id) {
        router.push({ name: 'messages', query: { with: user.value.id } });
      }
    };
    
    const fetchUserProfile = async () => {
      try {
        loading.value = true;
        error.value = null;
        const response = await getUserProfile(userId.value);
        
        // 处理API返回的不同响应格式
        if (response && response.user) {
          user.value = { ...response.user, ...response };
        } else if (response) {
          // 如果API直接返回用户对象
          user.value = response;
        }
        
        // 说明（第 23 批）：这里原来会在没有头像时去请求
        // https://ui-avatars.com/api/?name=... 生成占位图 —— 属于外网依赖，
        // 断网/内网部署时头像全部裂图。现在交给 el-avatar 的首字母插槽兜底。
        // 获取用户帖子
        await fetchUserPosts();

        // 第 25 批：同时加载该用户的评论（「评论」标签）
        await loadComments(true);
        
      } catch (err) {
        console.error('获取用户资料失败:', err);
        error.value = t('profile.loadFailed');
        if (err.response?.status === 404) {
          error.value = t('profile.notFound');
        }
        ElMessage.error(error.value);
      } finally {
        loading.value = false;
      }
    };
    
    const fetchUserPosts = async () => {
      try {
        postsLoading.value = true;
        
        // 准备请求参数
        const params = {
          page: 1,
          page_size: 10,
          ordering: '-created_at',
          _t: Date.now() // 防止缓存
        };
        
        let response;
        
        // 如果是查看自己的资料，使用 /users/me/posts/ 接口
        if (isCurrentUser.value) {
          console.log('获取当前用户的帖子');
          response = await getMyPosts(params);
        } else {
          // 查看其他用户的资料，使用原来的接口
          console.log(`获取用户 ${userId.value} 的帖子`);
          response = await getUserPosts(userId.value, params);
        }
        
        console.log('获取到的帖子数据:', response);
        
        // 处理分页响应
        if (response && response.results) {
          posts.value = response.results;
          // 更新用户帖子数量
          if (response.count !== undefined) {
            user.value.post_count = response.count;
          }
        } else {
          posts.value = Array.isArray(response) ? response : [];
        }
        console.log('处理后帖子列表:', posts.value);
      } catch (err) {
        console.error('获取用户帖子失败:', err);
        if (err.response?.status !== 404) { // 404错误已经在fetchUserProfile中处理
          ElMessage.error(t('profile.loadPostsFailed'));
        }
        posts.value = [];
      } finally {
        postsLoading.value = false;
      }
    };
    
    const formatDate = (dateString) => {
      if (!dateString) return '';
      const date = new Date(dateString);
      return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
      });
    };
    
    const goBack = () => {
      // 第 165 批：没有上一页时兜底回首页
      goBackOr('/');
    };
    
    const goToPost = (postId) => {
      router.push({ 
        name: 'post-detail', 
        params: { id: postId },
        query: { fromBoard: user.value.board?.id }
      });
    };
    
    // 确认删除帖子
    const confirmDeletePost = (post) => {
      ElMessageBox.confirm(
        t('profile.deletePostConfirm', { title: post.title || t('common.untitled') }),
        t('post.deleteTitle'),
        {
          confirmButtonText: t('msg.confirmed'),
          cancelButtonText: t('msg.cancel'),
          type: 'warning',
        }
      )
        .then(async () => {
          try {
            await deletePost(post.id);
            ElMessage.success(t('profile.postDeleted'));
            // 从列表中移除已删除的帖子
            posts.value = posts.value.filter(p => p.id !== post.id);
            // 更新帖子数量
            if (user.value.post_count > 0) {
              user.value.post_count--;
            }
          } catch (error) {
            console.error('删除帖子失败:', error);
            if (error.response) {
              // 服务器返回了错误响应
              if (error.response.status === 403) {
                ElMessage.error(t('profile.noPermissionDelete'));
              } else if (error.response.status === 404) {
                ElMessage.error(t('profile.postMissing'));
              } else if (error.response.status === 500) {
                ElMessage.error(t('profile.serverErrorDelete'));
                console.error('服务器错误详情:', error.response.data);
              } else {
                ElMessage.error(t('msg.deleteFailedWith', { detail: `${error.response.status} ${error.response.statusText}` }));
              }
            } else if (error.request) {
              // 请求已发送但未收到响应
              ElMessage.error(t('msg.networkError'));
            } else {
              // 请求设置错误
              ElMessage.error(t('msg.deleteFailedWith', { detail: error.message }));
            }
          }
        })
        .catch(() => {
          // 用户取消删除
        });
    };
    
    // ---------- 资料编辑（仅本人 / 管理员） ----------
    const editDialogVisible = ref(false);
    const savingProfile = ref(false);
    const editForm = ref({
      first_name: '',
      last_name: '',
      email: '',
      bio: '',
    });

    const openEditDialog = () => {
      editForm.value = {
        first_name: user.value.first_name || '',
        last_name: user.value.last_name || '',
        email: user.value.email || '',
        bio: user.value.bio || '',
      };
      editDialogVisible.value = true;
    };

    // ========================================================================
    // 第 97 批：编辑资料弹窗里改了没保存就点别的链接 → 提醒
    // ------------------------------------------------------------------------
    // `enabled` 让守卫**只在弹窗打开时**生效：平时浏览别人的资料页不该因为
    // "表单和用户资料不一致"被拦下来（表单没打开时根本谈不上未保存）。
    // ========================================================================
    useUnsavedChanges(
      () => {
        const current = editForm.value || {};
        const original = user.value || {};
        return ['first_name', 'last_name', 'email', 'bio'].some(
          (key) => String(current[key] ?? '') !== String(original[key] ?? ''),
        );
      },
      { enabled: () => editDialogVisible.value },
    );

    const submitProfileEdit = async () => {
      savingProfile.value = true;
      try {
        // ⚠️ @/api/http 返回的是 **AxiosResponse**（该模块没有响应解包拦截器），
        // 必须取 .data。原实现直接把 response 当成资料对象 spread，
        // 结果新填的姓名/邮箱/简介在页面上根本不更新（保存"像"成功了），
        // 还会把 axios 的 status/headers/config 混进 store 里的用户对象。
        const updated = (await http.patch(`/users/${userId.value}/`, {
          first_name: editForm.value.first_name,
          last_name: editForm.value.last_name,
          email: editForm.value.email,
          bio: editForm.value.bio,
        })).data;

        // 用后端返回的最新数据刷新页面（保留本地统计字段）
        user.value = { ...user.value, ...updated };
        // 同步登录用户信息，保证顶部栏昵称等位置一致
        // （存储读写收口到 store，避免组件自己拼 localStorage 而与适配器脱节）
        if (authStore.user) {
          authStore.updateUser(updated);
        }

        editDialogVisible.value = false;
        ElMessage.success(t('profile.profileUpdated'));
      } catch (error) {
        console.error('更新资料失败:', error);
        ElMessage.error(formatApiError(error, t('msg.updateFailed')));
      } finally {
        savingProfile.value = false;
      }
    };

    // ---------- 头像上传 / 移除（仅本人） ----------
    const uploadingAvatar = ref(false);

    const applyAvatarResult = (data) => {
      user.value = { ...user.value, ...data };
      if (authStore.user) {
        authStore.updateUser({ avatar: data.avatar || '' });
      }
    };

    const handleAvatarChange = async (uploadFile) => {
      const raw = uploadFile?.raw;
      if (!raw) return;

      if (!raw.type.startsWith('image/')) {
        ElMessage.error(t('msg.imageOnly'));
        return;
      }
      if (raw.size / 1024 / 1024 >= 2) {
        ElMessage.error(t('profile.avatarTooLarge'));
        return;
      }

      uploadingAvatar.value = true;
      try {
        const data = await uploadAvatar(userId.value, raw);
        applyAvatarResult(data);
        ElMessage.success(t('profile.avatarUpdated'));
      } catch (error) {
        console.error('上传头像失败:', error);
        ElMessage.error(formatApiError(error, t('profile.avatarUploadFailed')));
      } finally {
        uploadingAvatar.value = false;
      }
    };

    const handleRemoveAvatar = async () => {
      try {
        await ElMessageBox.confirm(t('profile.removeAvatarConfirm'), t('msg.notice'), {
          confirmButtonText: t('msg.remove'),
          cancelButtonText: t('msg.cancel'),
          type: 'warning',
        });
      } catch {
        return; // 用户取消
      }

      uploadingAvatar.value = true;
      try {
        const data = await deleteAvatar(userId.value);
        applyAvatarResult(data);
        ElMessage.success(t('profile.avatarRemoved'));
      } catch (error) {
        console.error('移除头像失败:', error);
        ElMessage.error(formatApiError(error, t('profile.avatarRemoveFailed')));
      } finally {
        uploadingAvatar.value = false;
      }
    };

    // ---------- 修改密码（仅本人） ----------
    const passwordDialogVisible = ref(false);
    const changingPassword = ref(false);
    const pwdForm = ref({ oldPassword: '', newPassword: '', confirmPassword: '' });

    const openPasswordDialog = () => {
      pwdForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' };
      passwordDialogVisible.value = true;
    };

    const submitPasswordChange = async () => {
      const { oldPassword, newPassword, confirmPassword } = pwdForm.value;

      if (!oldPassword || !newPassword) {
        ElMessage.warning(t('profile.passwordRequired'));
        return;
      }
      if (newPassword.length < 8) {
        ElMessage.warning(t('profile.passwordMin8'));
        return;
      }
      if (newPassword !== confirmPassword) {
        ElMessage.warning(t('profile.passwordMismatch'));
        return;
      }
      if (newPassword === oldPassword) {
        ElMessage.warning(t('profile.passwordSame'));
        return;
      }

      changingPassword.value = true;
      try {
        const result = await changePassword(userId.value, { oldPassword, newPassword });

        // 后端会作废旧 token 并返回新 token：同步进 store，
        // 否则当前标签页下一次请求就会 401 被踢回登录页
        if (result?.token) {
          authStore.setAuth({ userData: authStore.user, token: result.token });
        }

        passwordDialogVisible.value = false;
        ElMessage.success(t('profile.passwordChanged'));
      } catch (error) {
        console.error('修改密码失败:', error);
        ElMessage.error(formatApiError(error, t('profile.passwordChangeFailed')));
      } finally {
        changingPassword.value = false;
      }
    };

    // ==================================================================
    // 第 95 批：注销自己的账号
    // ==================================================================
    const deleteAccountVisible = ref(false);
    const deleteAccountLoading = ref(false);
    const deleteAccountPassword = ref('');
    const deleteAccountConfirm = ref('');
    const deleteAccountWord = DELETE_ACCOUNT_CONFIRM_WORD;
    /** 冷静期天数：先用默认值渲染，收到后端响应后以**后端返回**的为准 */
    const graceDays = ref(15);

    const openDeleteAccount = () => {
      deleteAccountPassword.value = '';
      deleteAccountConfirm.value = '';
      deleteAccountVisible.value = true;
    };

    const confirmDeleteAccount = async () => {
      if (deleteAccountConfirm.value.trim() !== deleteAccountWord || !deleteAccountPassword.value) {
        return;
      }
      deleteAccountLoading.value = true;
      try {
        const result = await deleteMyAccount({ password: deleteAccountPassword.value });
        deleteAccountVisible.value = false;
        // 第 101 批：文案从"已注销"改成"已进入冷静期"，并把**后端给的**天数与日期告诉用户
        // （不在前端写死 15 天：冷静期长度是可配置的，写死会对不上）
        graceDays.value = result?.grace_days ?? graceDays.value;
        ElMessage.success({
          message: scheduledText.value
            ? t('profile.deleteAccountScheduled', { date: scheduledText.value })
            : t('profile.deleteAccountOk'),
          duration: 6000,
        });
        // 后端已把 Token 删掉：清本地身份并回首页。
        // 不跳登录页 —— 账号此刻是"待注销"状态，再让用户面对登录框只会更困惑。
        authStore.clearAuth();
        router.replace('/');
      } catch (error) {
        console.error('申请注销失败:', error);
        ElMessage.error(formatApiError(error, t('profile.deleteAccountFailed')));
      } finally {
        deleteAccountLoading.value = false;
      }
    };

    /** 计划删除时间（本地时区，精确到天）；冷静期结束后才会真正清空个人信息 */
    const scheduledText = computed(() => {
      const days = Number(graceDays.value) || 0;
      if (!days) return '';
      const date = new Date();
      date.setDate(date.getDate() + days);
      return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    });

    onMounted(() => {
      // 只调用 fetchUserProfile，它内部会调用 fetchUserPosts
      fetchUserProfile();
    });

    return {
      user,
      t,
      localizedField,
      // 第 71 批修复：模板里 <ReportDialog :target-id="userId"> 用到了 userId，
      // 但它此前只定义、没有 return —— targetId 恒为 undefined，
      // 举报用户时直接命中"缺少举报对象"分支，举报功能不可用。
      userId,
      posts,
      loading,
      postsLoading,
      error,
      activeTab,
      goBack,
      goToPost,
      formatDate,
      isCurrentUser,
      confirmDeletePost,
      // 第 95 批：注销账号
      deleteAccountVisible,
      deleteAccountLoading,
      deleteAccountPassword,
      deleteAccountConfirm,
      deleteAccountWord,
      graceDays,
      scheduledText,
      openDeleteAccount,
      confirmDeleteAccount,
      // 资料编辑
      editDialogVisible,
      savingProfile,
      editForm,
      openEditDialog,
      submitProfileEdit,
      // 头像（第 23 批）
      uploadingAvatar,
      handleAvatarChange,
      handleRemoveAvatar,
      // 修改密码（第 23 批）
      passwordDialogVisible,
      changingPassword,
      pwdForm,
      openPasswordDialog,
      submitPasswordChange,
      // 评论列表 + 谁点赞了（第 25 批）
      comments,
      commentsTotal,
      commentsLoading,
      loadMoreComments,
      likersDialog,
      openPostLikers,
      openCommentLikers,
      goToComment,
      goToBoard,
      // 关注 / 粉丝（第 40 批）
      authStore,
      followerCount,
      followingCount,
      isFollowing,
      canFollow,
      followLoading,
      followActionId,
      followDialogVisible,
      reportDialogVisible,
      followDialogTab,
      followList,
      handleFollow,
      openFollowDialog,
      switchFollowTab,
      toggleItemFollow,
      goToUserProfile,
      // 等级积分 + 私信（第 42 批）
      pointsInfo,
      progressTitle,
      goToMessages
    };
  }
};
</script>

<style scoped>
.user-profile {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
  background-color: #f5f7fa;
  min-height: calc(100vh - 100px);
}

.profile-header {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
}

.back-btn {
  margin-right: 15px;
  font-size: 16px;
}

.profile-container {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.profile-card {
  text-align: center;
  padding: 30px 20px;
  border: none;
  border-bottom: 1px solid #f0f0f0;
}

/* 第 23 批：容器改为纵向排列 —— 现在里面除了头像还有"上传/移除"按钮与提示文案，
   不能再是一个固定 88px 的圆形（会把按钮裁在圆外/挤在一起）。
   圆形渐变观感交给内部 el-avatar 自己。 */
.profile-avatar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: auto;
  height: auto;
  margin-bottom: 15px;
  background: none;
  box-shadow: none;
  border-radius: 0;
}

/* 无头像时显示首字母：沿用品牌渐变底 */
.profile-avatar :deep(.el-avatar) {
  background: var(--gradient-brand, linear-gradient(135deg, #2f7d4f, #1f6343));
  color: #fff;
  font-size: 34px;
  font-weight: 800;
  box-shadow: 0 12px 26px rgba(31, 99, 67, 0.24);
}

.profile-info h3 {
  margin: 10px 0 5px;
  font-size: 24px;
}

.join-date {
  color: #909399;
  margin-bottom: 20px;
}

.stats {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

.stat-item {
  padding: 0 20px;
  text-align: center;
}

.stat-value {
  font-size: 20px;
  font-weight: bold;
  color: #303133;
}

.stat-label {
  color: #909399;
  font-size: 14px;
}

.profile-tabs {
  padding: 20px;
}

.post-list {
  margin-top: 15px;
}

.post-item {
  position: relative;
  padding: 15px;
  margin-bottom: 15px;
  border-radius: 4px;
  background-color: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: all 0.3s;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.post-item:hover {
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  transform: translateY(-1px);
}

.post-content {
  flex: 1;
  cursor: pointer;
  padding-right: 20px;
}

.post-item h4 {
  margin: 0 0 10px 0;
  font-size: 16px;
  color: #303133;
  font-weight: 500;
  line-height: 1.4;
}

.post-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  font-size: 12px;
  color: #909399;
}

.post-meta span {
  margin-right: 15px;
  display: flex;
  align-items: center;
}

.post-meta i {
  margin-right: 3px;
  font-size: 14px;
}

.post-time {
  margin-left: auto;
  color: #909399;
}

.delete-btn {
  opacity: 0.7;
  transition: all 0.3s;
  margin-left: 15px;
  flex-shrink: 0;
}

.delete-btn:hover {
  opacity: 1;
  color: #f56c6c;
  background-color: #fef0f0;
  border-color: #fbc4c4;
}

.post-item {
  padding: 15px 0;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background-color 0.3s;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.post-item:hover {
  background-color: #f8f9fa;
}

.post-item h4 {
  margin: 0 0 8px 0;
  font-size: 16px;
  color: #303133;
}

.post-meta {
  display: flex;
  color: #909399;
  font-size: 13px;
}

.post-meta span {
  margin-right: 15px;
  display: flex;
  align-items: center;
}

.post-meta i {
  margin-right: 3px;
}

.post-time {
  margin-left: auto !important;
  color: #c0c4cc;
}

.loading-container {
  padding: 20px 0;
}

.empty-tip {
  padding: 40px 0;
  text-align: center;
  color: #909399;
}

/* ================= 现代化覆写（设计变量见 assets/theme.css） ================= */
.user-profile,
.profile-container {
  width: 100%;
  max-width: 1080px;
  margin: 0 auto;
  padding: 8px 24px 48px;
  box-sizing: border-box;
}

.profile-card {
  padding: 30px;
  margin-bottom: 22px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background: var(--surface);
  box-shadow: var(--shadow-md);
}

.profile-header {
  display: flex;
  align-items: center;
  gap: 22px;
  flex-wrap: wrap;
}

/* 说明（第 23 批）：这里原本是固定 88×88 的圆形渐变块（只够放一个头像）。
   现在头像容器里还有"上传/移除"按钮与格式提示，样式统一在上面那份
   .profile-avatar 里定义，这里不再重复覆盖。 */

.profile-info h2,
.profile-info h1 {
  margin: 0 0 6px;
  font-size: 24px;
  font-weight: 800;
  color: var(--ink-900);
}

.join-date {
  font-size: 13px;
  color: var(--ink-500);
}

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 16px;
  margin-top: 24px;
}

.stat-item {
  padding: 18px;
  text-align: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-muted);
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.stat-item:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-sm);
}

/* 第 40 批：关注/粉丝统计可点击 */
.stat-item.is-clickable {
  cursor: pointer;
}

.stat-item.is-clickable:hover {
  border-color: var(--brand-300);
}

/* 关注按钮 */
.follow-btn {
  border-radius: var(--radius-pill) !important;
}

/* 等级徽章 + 积分进度（第 42 批） */
.level-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 4px 0 12px;
}

.level-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  font-size: 12.5px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--brand-500), var(--brand-700));
}

.level-badge.is-lv3 { background: linear-gradient(135deg, #4a9f6b, #217a4c); }
.level-badge.is-lv4 { background: linear-gradient(135deg, #d9922f, #b8761b); }
.level-badge.is-lv5 { background: linear-gradient(135deg, #cf4436, #8f2a1f); }

.level-points {
  font-size: 13px;
  font-weight: 700;
  color: var(--ink-800);
}

.level-progress {
  flex: 1;
  min-width: 120px;
  max-width: 240px;
  height: 7px;
  border-radius: 999px;
  background: var(--ink-100);
  overflow: hidden;
}

.level-progress-bar {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--brand-400), var(--brand-600));
  transition: width 0.3s ease;
}

.level-next {
  font-size: 12px;
  color: var(--ink-500);
}

/* 关注/粉丝弹窗 */
.follow-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.follow-tab {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--surface);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-600);
  cursor: pointer;
  transition: all 0.18s ease;
}

.follow-tab.is-active {
  color: #fff;
  border-color: transparent;
  background: var(--gradient-brand);
}

.follow-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 380px;
  overflow-y: auto;
}

.follow-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border: 1px solid var(--brand-100);
  border-radius: var(--radius);
  background: linear-gradient(160deg, #ffffff, #f8fcfa);
}

.follow-info {
  flex: 1;
  min-width: 0;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.follow-name {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--ink-800);
}

.follow-bio {
  font-size: 12px;
  color: var(--ink-500);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stat-value {
  font-size: 24px;
  font-weight: 800;
  color: var(--brand-700);
}

.stat-label {
  margin-top: 4px;
  font-size: 12.5px;
  color: var(--ink-500);
}

/* 说明（第 31 批）：这里原来把"胶囊标签栏"的样式加在了**整个 el-tabs** 上
   （display:flex + width:fit-content + border-radius:999px + 边框），
   而 el-tabs 里除了标签栏还装着"发布的帖子/发表的评论"两个面板：
   结果整个面板区被收成 fit-content（实测只有 512px，容器宽 1032px），
   右半边整块留白，还在页面上画出一个 999px 圆角的空框。
   现在只把胶囊样式加在标签栏 .el-tabs__header 上，容器恢复整宽。 */
.profile-tabs {
  width: 100%;
  margin-bottom: 18px;
}

.profile-tabs :deep(.el-tabs__header) {
  display: flex;
  width: fit-content;
  gap: 8px;
  padding: 6px;
  margin: 0 0 18px;
  border-radius: var(--radius-pill);
  background: var(--surface);
  border: 1px solid var(--border);
}

.profile-tabs :deep(.el-tabs__nav-wrap)::after {
  display: none;
}

.profile-tabs :deep(.el-tabs__active-bar) {
  display: none;
}

.profile-tabs :deep(.el-tabs__item) {
  height: 34px;
  line-height: 34px;
  padding: 0 18px !important;
  border-radius: var(--radius-pill);
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink-500);
  transition: background-color var(--dur) var(--ease), color var(--dur) var(--ease);
}

.profile-tabs :deep(.el-tabs__item:hover) {
  color: var(--brand-700);
}

.profile-tabs :deep(.el-tabs__item.is-active) {
  color: #fff;
  background: var(--gradient-brand);
  box-shadow: 0 6px 14px rgba(31, 99, 67, 0.22);
}

.post-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.post-item {
  padding: 18px 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-xs);
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.post-item:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-sm);
}

.post-content {
  margin-bottom: 10px;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink-800);
}

.post-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 12.5px;
  color: var(--ink-400);
}

.post-time {
  font-size: 12.5px;
  color: var(--ink-400);
}

.back-btn,
.delete-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border-radius: var(--radius-pill);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--dur) var(--ease);
}

.back-btn {
  border: 1px solid var(--border-strong);
  background: var(--surface);
  color: var(--ink-600);
}

.back-btn:hover {
  border-color: var(--brand-400);
  background: var(--brand-50);
  color: var(--brand-700);
}

.delete-btn {
  border: 1px solid #f0d3cf;
  background: #fdf5f4;
  color: var(--danger);
}

.delete-btn:hover {
  background: var(--danger);
  border-color: transparent;
  color: #fff;
}

.empty-tip,
.loading-container {
  padding: 48px 24px;
  text-align: center;
  color: var(--ink-400);
  font-size: 14.5px;
}

/* 用户名 + 编辑入口 */
.profile-name-row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.profile-name-row h3 {
  margin: 0;
}

.edit-profile-btn {
  border-radius: var(--radius-pill) !important;
}

/* 头像操作（第 23 批：真实头像上传/移除） */
.avatar-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.avatar-actions .el-button {
  border-radius: var(--radius-pill) !important;
}

.avatar-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--ink-400, #9aa4b2);
}

.change-password-btn {
  border-radius: var(--radius-pill) !important;
}

.password-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--ink-500);
}

.profile-realname {
  margin: 0 0 6px;
  font-size: 14px;
  color: var(--ink-600);
}

.profile-email {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--ink-500);
}

.profile-email i {
  margin-right: 5px;
  color: var(--brand-500);
}

.profile-bio {
  margin: 0 0 10px;
  padding: 10px 14px;
  border-left: 3px solid var(--brand-300);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  background: var(--surface-muted);
  font-size: 13.5px;
  line-height: 1.8;
  color: var(--ink-600);
}

.error-alert {
  padding: 14px 18px;
  margin-bottom: 18px;
  border: 1px solid #f0d3cf;
  border-radius: var(--radius);
  background: #fdf5f4;
  color: var(--danger);
  font-size: 14px;
}

@media (max-width: 768px) {
  .user-profile,
  .profile-container {
    padding: 0 16px 32px;
  }

  .profile-card {
    padding: 20px;
  }

  .profile-avatar {
    width: 68px;
    height: 68px;
    font-size: 26px;
  }
}

/* ---------- 第 25 批：帖子"发在哪里 / 谁点赞了" + 评论列表 ---------- */
.post-item h4 {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.post-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.post-board {
  color: var(--brand-700, #2f7d4f);
  cursor: pointer;
}

.post-board:hover {
  text-decoration: underline;
}

.comment-list {
  margin-top: 15px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.comment-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  transition: box-shadow 0.25s ease, transform 0.25s ease;
}

.comment-item:hover {
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
}

.comment-content {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.comment-text {
  margin: 0 0 8px;
  font-size: 14px;
  line-height: 1.6;
  color: #303133;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.comment-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--ink-500, #7a8699);
}

.comment-source {
  color: var(--brand-700, #2f7d4f);
  cursor: pointer;
}

.comment-source:hover {
  text-decoration: underline;
}

.comment-reply-to {
  color: var(--ink-500, #7a8699);
}

.comment-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.more-comments {
  display: flex;
  justify-content: center;
  padding-top: 4px;
}

@media (max-width: 640px) {
  .comment-item {
    flex-direction: column;
    align-items: stretch;
  }
}

/* ============================================================================
   第 95 批：注销账号「危险区」
   ----------------------------------------------------------------------------
   视觉上刻意与页面其它卡片区分：红色左边框 + 淡红底，让人一眼看出
   "这一块的操作不可逆"，不会和上面的编辑资料混在一起。
   ============================================================================ */
.danger-zone {
  margin-top: 20px;
  border: 1px solid #f3c9c3;
  border-left: 4px solid var(--danger, #cf4436);
  background: #fdf7f6;
}

.danger-zone :deep(.el-card__header) {
  padding: 12px 18px;
  border-bottom: 1px solid #f3c9c3;
  background: #fdecea;
}

.danger-zone-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  color: #a32f22;
}

.danger-zone-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.danger-zone-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 700;
  color: var(--ink-800, #24352c);
}

.danger-zone-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--ink-600, #566b60);
  max-width: 620px;
}

.delete-alert {
  margin-bottom: 10px;
}

/* 第 101 批：冷静期提示（比"后果"那条更显眼，因为它是用户最关心的"能不能反悔"） */
.grace-alert {
  margin-bottom: 14px;
}

.grace-alert p {
  margin: 0;
  line-height: 1.7;
}

.grace-sub {
  margin-top: 4px !important;
  font-size: 12.5px;
  opacity: 0.9;
}

.delete-alert p {
  margin: 0 0 6px;
  line-height: 1.7;
}

.delete-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.8;
}

.delete-form {
  margin-top: 4px;
}
</style>

