<template>
  <div class="forum-favorites">
    <div class="favorites-header">
      <div>
        <h1><i class="fas fa-bookmark"></i> {{ t('fav.title') }}</h1>
        <p class="subtitle">{{ t('fav.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <el-button @click="goToForum"><i class="fas fa-comments"></i> {{ t('forum.backToForum') }}</el-button>
        <el-button type="primary" plain :loading="loading" @click="fetchFavorites">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
      </div>
    </div>

    <div v-if="loading" class="loading-container">
      <el-skeleton :rows="6" animated />
    </div>

    <el-empty v-else-if="favorites.length === 0" :description="t('fav.empty')">
      <el-button type="primary" @click="goToForum">{{ t('fav.goForum') }}</el-button>
    </el-empty>

    <div v-else class="favorites-list">
      <div
        v-for="post in favorites"
        :key="post.id"
        class="favorite-item"
        :class="{ 'is-pinned': post.is_pinned, 'is-essence': post.is_essence }"
      >
        <div class="item-main" @click="goToPost(post.id)">
          <h3 class="item-title">
            <el-tag v-if="post.is_pinned" size="mini" type="danger" effect="dark">{{ t('forum.tagPinned') }}</el-tag>
            <el-tag v-if="post.is_essence" size="mini" type="warning" effect="dark">{{ t('forum.tagEssence') }}</el-tag>
            <el-tag v-if="post.status === 'draft'" size="mini" type="info" effect="dark">{{ t('forum.tagDraft') }}</el-tag>
            {{ localizedField(post, 'title') }}
          </h3>
          <div class="item-meta">
            <span v-if="post.board"><i class="fas fa-layer-group"></i> {{ localizedField(post.board, 'name') }}</span>
            <span><i class="fas fa-user"></i> {{ post.author?.username || t('forum.unknownUser') }}</span>
            <span><i class="fas fa-clock"></i> {{ formatTime(post.created_at) }}</span>
            <span><i class="fas fa-eye"></i> {{ post.view_count || 0 }}</span>
            <span><i class="fas fa-comment"></i> {{ post.comment_count || 0 }}</span>
            <span><i class="fas fa-thumbs-up"></i> {{ post.like_count || 0 }}</span>
          </div>
        </div>
        <div class="item-actions">
          <el-button size="small" :loading="removingId === post.id" @click.stop="removeFavorite(post)">
            <i class="fas fa-bookmark"></i> {{ t('fav.unfavorite') }}
          </el-button>
        </div>
      </div>

      <div v-if="total > pageSize" class="pagination-container">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next, total"
          background
          @current-change="handlePageChange"
        />
      </div>
    </div>

    <!-- 第 31 批：原来这一页只有"标题 + 空状态"，下面全是空白，这里补一块有用的说明 -->
    <!-- 第 68 批：卡片内容改由脚本 computed 生成，随语言切换 -->
    <PageExtras
      icon="fas fa-bookmark"
      :title="t('fav.guideTitle')"
      :subtitle="t('fav.guideSubtitle')"
      :items="guideItems"
    />
  </div>
</template>

<script>
import { ref, onMounted, computed } from 'vue';
import { useI18n } from '@/i18n';
import { useLocalized } from '@/utils/localized';  // 第 68 批：多语言（第 72 批起也用于版块名等内容数据）
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { getFavoritePosts, toggleFavorite } from '@/api/forum';
import { formatTime } from '@/utils/date';
// 第 31 批：页面底部"收藏夹怎么用"补充信息区
import PageExtras from '@/components/PageExtras.vue';

export default {
  name: 'ForumFavoritesView',
  components: { PageExtras },
  setup() {
    const { t } = useI18n();  // 第 68 批：多语言
    const { localizedField } = useLocalized();
    const router = useRouter();

    const favorites = ref([]);
    const loading = ref(false);
    const removingId = ref(null);
    const page = ref(1);
    const pageSize = ref(10);
    const total = ref(0);

    const fetchFavorites = async () => {
      loading.value = true;
      try {
        const data = await getFavoritePosts({
          page: page.value,
          page_size: pageSize.value,
        });
        favorites.value = data.results || [];
        total.value = data.count || 0;
      } catch (error) {
        console.error('获取收藏列表失败:', error);
        favorites.value = [];
        total.value = 0;
        ElMessage.error(t('fav.loadFailed', { detail: error.response?.data?.detail || error.message }));
      } finally {
        loading.value = false;
      }
    };

    const removeFavorite = async (post) => {
      removingId.value = post.id;
      try {
        const result = await toggleFavorite(post.id);
        // 后端返回权威状态；确认已取消才从列表里移除
        if (!result || result.is_favorited === false) {
          favorites.value = favorites.value.filter((item) => item.id !== post.id);
          total.value = Math.max(0, total.value - 1);
          ElMessage.success(t('msg.favoriteRemoved'));
        } else {
          ElMessage.warning(t('msg.favoriteFailed'));
        }
      } catch (error) {
        console.error('取消收藏失败:', error);
        ElMessage.error(t('msg.operationFailedWith', { detail: error.response?.data?.detail || error.message }));
      } finally {
        removingId.value = null;
      }
    };

    const handlePageChange = (newPage) => {
      page.value = newPage;
      fetchFavorites();
    };

    const goToPost = (id) => router.push({ name: 'post-detail', params: { id } });
    const goToForum = () => router.push({ name: 'forum' });

    onMounted(fetchFavorites);

    // 第 68 批：底部"收藏夹怎么用"卡片（原来内联在模板里，无法随语言切换）
    const guideItems = computed(() => [
      {
        icon: 'fas fa-hand-pointer',
        title: t('fav.guide1'),
        text: t('fav.guide1Desc'),
        more: t('fav.goForum'),
        to: '/forum',
      },
      { icon: 'fas fa-bookmark', title: t('fav.guide2'), text: t('fav.guide2Desc') },
      {
        icon: 'fas fa-comments',
        title: t('fav.guide3'),
        text: t('fav.guide3Desc'),
        more: t('post.title'),
        to: '/forum/post/new',
      },
    ]);

    return {
      t,
      localizedField,
      guideItems,
      favorites,
      loading,
      removingId,
      page,
      pageSize,
      total,
      formatTime,
      fetchFavorites,
      removeFavorite,
      handlePageChange,
      goToPost,
      goToForum,
    };
  },
};
</script>

<style scoped>
.forum-favorites {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
}

.favorites-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.favorites-header h1 {
  margin: 0 0 4px;
  font-size: 22px;
  font-weight: 800;
  color: var(--ink-900, #1f2d3d);
}

.subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--ink-500, #7a8699);
}

.header-actions {
  display: flex;
  gap: 8px;
}

.favorites-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.favorite-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #eef0f3;
  border-radius: 12px;
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.favorite-item:hover {
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.06);
  transform: translateY(-2px);
}

.item-main {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.item-title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 700;
  color: var(--ink-900, #1f2d3d);
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.item-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--ink-500, #7a8699);
}

.pagination-container {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

@media (max-width: 640px) {
  .favorite-item {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
