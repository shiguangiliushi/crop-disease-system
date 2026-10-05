<template>
  <el-dialog
    :model-value="modelValue"
    :title="displayTitle"
    width="420px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-if="loading" class="likers-loading">
      <el-skeleton :rows="4" animated />
    </div>

    <el-empty v-else-if="likers.length === 0" :description="t('likers.empty')" :image-size="80" />

    <ul v-else class="likers-list">
      <li v-for="like in likers" :key="like.id" class="liker-item">
        <!-- 第 113 批：点头像 → 开私信 -->
        <UserAvatarLink
          :size="32"
          :user-id="like.user?.id"
          :username="like.user?.username"
          :avatar="like.user?.avatar"
        />
        <div class="liker-main">
          <span class="liker-name">{{ like.user?.username || t('likers.unknownUser') }}</span>
          <span class="liker-time">{{ formatTime(like.created_at) }}</span>
        </div>
      </li>
    </ul>

    <p v-if="!loading && count > likers.length" class="likers-more">
      {{ t('likers.more', { count, shown: likers.length }) }}
    </p>
  </el-dialog>
</template>

<script>
/**
 * 「谁点赞了」弹窗（第 25 批新增）
 *
 * 帖子详情、用户资料、版块列表都可能有"点赞"要展示点赞者，
 * 统一收口到一个组件里，避免每个页面各写一套。
 */
import { ref, watch, computed } from 'vue';
import { getPostLikers, getCommentLikers } from '@/api/forum';
import { formatTime } from '@/utils/date';
import { useI18n } from '@/i18n';  // 第 83 批：弹窗标题此前写死中文
import UserAvatarLink from '@/components/UserAvatarLink.vue';

export default {
  name: 'LikersDialog',
  components: { UserAvatarLink },  // 第 113 批：点头像 → 开私信
  props: {
    modelValue: { type: Boolean, default: false },
    // 'post' = 查帖子的点赞者；'comment' = 查某条评论的点赞者
    type: { type: String, default: 'post' },
    postId: { type: [Number, String], default: null },
    commentId: { type: [Number, String], default: null },
    // 第 83 批：默认值不能写 `default: t(...)` —— props 默认值只在组件定义时求值一次，
    // 不会跟随语言切换。这里保持空串，显示时再按当前类型/语言取标题。
    title: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  setup(props) {
    const { t } = useI18n();
    const likers = ref([]);
    const count = ref(0);
    const loading = ref(false);

    /** 标题：调用方显式传了就用调用方的，否则按 type 给默认文案（跟随语言） */
    const displayTitle = computed(() => props.title
      || (props.type === 'comment' ? t('likers.titleComment') : t('likers.titlePost')));

    const initial = (user) => (user?.username ? user.username[0].toUpperCase() : 'U');

    const load = async () => {
      if (!props.postId) return;
      if (props.type === 'comment' && !props.commentId) return;

      loading.value = true;
      try {
        const data = props.type === 'comment'
          ? await getCommentLikers(props.postId, props.commentId)
          : await getPostLikers(props.postId);
        likers.value = data?.results || [];
        count.value = data?.count ?? likers.value.length;
      } catch (error) {
        console.error('获取点赞名单失败:', error);
        likers.value = [];
        count.value = 0;
      } finally {
        loading.value = false;
      }
    };

    // 每次打开都重新拉取（点赞状态随时会变）
    watch(() => props.modelValue, (visible) => {
      if (visible) load();
    });

    return { likers, count, loading, initial, formatTime, t, displayTitle };
  },
};
</script>

<style scoped>
.likers-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 340px;
  overflow-y: auto;
}

.liker-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 4px;
  border-bottom: 1px solid #f4f6f8;
}

.liker-item:last-child {
  border-bottom: none;
}

.liker-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.liker-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-800, #2c3e50);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.liker-time {
  font-size: 12px;
  color: var(--ink-400, #9aa4b2);
}

.likers-more {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--ink-400, #9aa4b2);
  text-align: center;
}

.likers-loading {
  padding: 4px 0;
}
</style>
