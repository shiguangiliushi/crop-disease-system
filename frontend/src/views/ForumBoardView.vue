<template>
  <div class="forum-board-container">
    <!-- ============ 版块页头（第 34 批重做） ============
         原来这里有三套互相覆盖的样式：第 2 套把 .forum-header 设成蓝色渐变 + 白字，
         第 3 套（"现代化覆写"）又把背景改成浅绿渐变，但**白字没跟着改** ——
         于是版块名与"帖子/今日"两个标签全是白字白底，页面上只剩两个孤零零的数字。
         现在统一用全站的 .admin-hero + .stat-tile，并把失效的 el-icon-* 换成 Font Awesome。 -->
    <header class="admin-hero board-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i :class="boardIconClass(board?.icon)"></i></span>
        <div>
          <!-- 第 79 批：版块名/描述是**站点内容数据**（后端已有 name_en / description_en），
               原来直接渲染中文，英文界面下版块标题一直是中文 -->
          <h1>{{ localizedField(board, 'name') || t('forum.loadingBoard') }}</h1>
          <p>{{ localizedField(board, 'description') || t('forum.noBoardDescLong') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-button plain @click="goToForum">
          <i class="fas fa-arrow-left"></i> {{ t('forum.backToForum') }}
        </el-button>
        <el-button class="btn-on-brand" @click="goToNewPost">
          <i class="fas fa-pen"></i> {{ t('forum.newPost') }}
        </el-button>
      </div>
    </header>

    <!-- 版块统计 -->
    <div class="admin-stats board-stats-row">
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-comment-dots"></i></span>
        <div>
          <div class="stat-tile-value">{{ board?.post_count || 0 }}</div>
          <div class="stat-tile-label">{{ t('forum.boardPosts') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--ok">
        <span class="stat-tile-icon"><i class="fas fa-star"></i></span>
        <div>
          <div class="stat-tile-value">{{ board?.essence_count || 0 }}</div>
          <div class="stat-tile-label">{{ t('forum.boardEssence') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--processing">
        <span class="stat-tile-icon"><i class="fas fa-list-ul"></i></span>
        <div>
          <div class="stat-tile-value">{{ total }}</div>
          <div class="stat-tile-label">{{ t('forum.filterResult') }}</div>
        </div>
      </div>
    </div>

    <!-- ============ 帖子列表 ============ -->
    <section class="panel-card board-panel">
      <div class="panel-head">
        <span class="panel-icon"><i class="fas fa-list-ul"></i></span>
        <h2 class="panel-title">{{ localizedField(board, 'name') || t('forum.postsUnit') }}</h2>
        <span class="panel-count">{{ t('forum.totalCount', { count: total }) }}</span>
        <div class="panel-head-right board-filters">
          <el-select
            v-model="sortBy"
            size="small"
            :placeholder="t('forum.sortBy')"
            class="sort-select"
            @change="handleSortChange"
          >
            <el-option :label="t('forum.sortLatest')" value="-created_at"></el-option>
            <el-option :label="t('forum.sortReply')" value="-last_reply"></el-option>
            <el-option :label="t('forum.sortViews')" value="-view_count"></el-option>
            <el-option :label="t('forum.sortComments')" value="-comment_count"></el-option>
          </el-select>

          <el-input
            v-model="searchQuery"
            :placeholder="t('forum.searchBoardPlaceholder')"
            size="small"
            clearable
            class="search-input"
            @clear="handleSearch"
            @keyup.enter="handleSearch"
          >
            <template #prefix><i class="fas fa-search"></i></template>
          </el-input>
        </div>
      </div>

      <div class="panel-body">
        <!-- 排序 / 筛选胶囊 -->
        <div class="board-tabs">
          <button
            v-for="tab in tabs"
            :key="tab.value"
            type="button"
            class="board-tab"
            :class="{ 'is-active': activeTab === tab.value }"
            @click="handleTabChange(tab.value)"
          >
            <i :class="tab.icon"></i> {{ tab.label }}
          </button>
          <span v-if="searchQuery" class="search-hint">
            {{ t('forum.searchHint', { keyword: searchQuery }) }}
            <button type="button" @click="clearSearch">{{ t('forum.clear') }}</button>
          </span>
        </div>

        <div v-if="loading" class="loading-container">
          <el-skeleton :rows="5" animated />
        </div>

        <template v-else>
          <el-empty
            v-if="posts.length === 0"
            :description="searchQuery ? t('forum.emptySearchBoard') : t('forum.emptyBoardPosts')"
          >
            <el-button v-if="!searchQuery" type="primary" @click="goToNewPost">
              <i class="fas fa-pen"></i> {{ t('forum.publishPost') }}
            </el-button>
          </el-empty>

          <transition-group v-else name="post-list" tag="div" class="post-list">
            <article
              v-for="post in posts"
              :key="post.id"
              class="post-item"
              :class="{ 'is-pinned': post.is_pinned, 'is-essence': post.is_essence }"
              @click="goToPost(post.id)"
            >
              <el-avatar
                class="post-avatar"
                :size="44"
                :src="post.author?.avatar"
                @click.stop="goToUserProfile(post.author.id)"
              >
                {{ post.author?.username ? post.author.username[0].toUpperCase() : 'U' }}
              </el-avatar>

              <div class="post-content">
                <h3 class="post-title">
                  <el-tag v-if="post.is_pinned" size="small" type="danger" effect="dark">{{ t('forum.tagPinned') }}</el-tag>
                  <el-tag v-if="post.is_essence" size="small" type="warning" effect="dark">{{ t('forum.tagEssence') }}</el-tag>
                  <el-tag v-if="post.status === 'draft'" size="small" type="info">{{ t('forum.tagDraft') }}</el-tag>
                  <!-- 第 38 批：待审核 -->
                  <el-tag v-if="post.status === 'pending'" size="small" type="warning">{{ t('forum.tagPending') }}</el-tag>
                  {{ localizedField(post, 'title') }}
                </h3>
                <!-- 第 34 批：后端列表接口没有 excerpt 字段，模板却一直读它 →
                     每条帖子下面恒显示"暂无内容预览"。改为用正文前 80 字做摘要。 -->
                <p class="post-excerpt">{{ excerptOf(post) }}</p>
                <div class="post-meta">
                  <span><i class="fas fa-user"></i> {{ post.author?.username || t('forum.anonymous') }}</span>
                  <span><i class="fas fa-clock"></i> {{ formatTime(post.created_at) }}</span>
                  <span><i class="fas fa-eye"></i> {{ t('forum.viewsCount', { count: post.view_count || 0 }) }}</span>
                </div>
              </div>

              <div class="post-stats">
                <span class="post-stat">
                  <b>{{ post.comment_count || 0 }}</b><i>{{ t('forum.replies') }}</i>
                </span>
                <button
                  type="button"
                  class="post-stat is-action"
                  :class="{ 'is-on': post.is_liked }"
                  :title="post.is_liked ? t('forum.unlike') : t('forum.like')"
                  @click.stop="toggleLike(post, $event)"
                >
                  <b>{{ post.like_count || 0 }}</b><i>{{ t('forum.likes') }}</i>
                </button>
                <button
                  type="button"
                  class="post-stat is-action"
                  :class="{ 'is-on': post.is_favorited }"
                  :title="post.is_favorited ? t('forum.unfavorite') : t('forum.favorite')"
                  @click.stop="toggleFavorite(post)"
                >
                  <b><i :class="post.is_favorited ? 'fas fa-bookmark' : 'far fa-bookmark'"></i></b>
                  <i>{{ t('forum.favorite') }}</i>
                </button>
              </div>
            </article>
          </transition-group>

          <div v-if="total > pageSize" class="pagination-container">
            <el-pagination
              v-model:current-page="currentPage"
              :page-size="pageSize"
              :total="total"
              layout="prev, pager, next, jumper, ->, total"
              background
              @current-change="handleCurrentChange"
            />
          </div>
        </template>
      </div>
    </section>

    <!-- 回到顶部 -->
    <el-backtop :bottom="100">
      <div class="back-to-top">
        <i class="fas fa-arrow-up"></i>
      </div>
    </el-backtop>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElLoading } from 'element-plus';
// 注：原来这里 import request from '@/utils/request' 但整个文件从未使用它，
// 属于死导入（该模块会连带注册一套拦截器并引入 Element Plus / router）。
// 该页所有数据请求都已走 @/api/forum（内部使用 @/api 客户端）。
import { getBoardDetail, getPosts, toggleLike as apiToggleLike, toggleFavorite as apiToggleFavorite } from '@/api/forum'; // 导入点赞/收藏API
import { formatTime } from '@/utils/date';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';  // 第 60 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 79 批：版块名/描述等内容数据

const API_PREFIX = '/api';

export default {
  name: 'ForumBoardView',
  setup() {
    const { t } = useI18n();  // 第 60 批：多语言
    const { localizedField } = useLocalized();  // 第 79 批：版块名/描述等内容数据
    const route = useRoute();
    const router = useRouter();
    const authStore = useAuthStore(); // 使用 auth store
    
    console.log('ForumBoardView 初始化，路由参数:', route.params);
    console.log('完整路由对象:', route);
    
    // 组件挂载时加载数据
    onMounted(() => {
      console.log('ForumBoardView 组件已挂载，开始加载数据...');
      fetchBoard();
      fetchPosts();
    });
    
    // 监听路由参数变化
    watch(() => route.params.id, (newId, oldId) => {
      console.log('版块ID变化:', { oldId, newId });
      if (newId && newId !== oldId) {
        console.log('版块ID变化，重新加载数据');
        fetchBoard();
        fetchPosts();
      }
    });
    
    // 状态管理
    const board = ref({});
    const posts = ref([]);
    const loading = ref(false);
    const loadingPosts = ref(false);
    const activeTab = ref('all');
    const sortBy = ref('-created_at'); // 排序
    const searchQuery = ref(''); // 搜索查询
    const currentPage = ref(1);
    const pageSize = ref(20); // 使用 ref 以便将来可能动态调整
    const total = ref(0);
    const totalPages = ref(1);
    const todayPosts = ref(0);
    
    // 确保boardId是数字类型
    const boardId = computed(() => {
      const id = Number(route.params.id);
      console.log('计算属性 boardId 被调用，原始值:', route.params.id, '转换后:', id);
      return isNaN(id) ? null : id;
    });
    
    // 调试用
    console.log('初始状态:', {
      routeParams: route.params,
      routeQuery: route.query,
      path: route.path,
      fullPath: route.fullPath,
      boardId: boardId.value
    });
    
    // 获取版块详情
    const fetchBoard = async () => {
      console.log('fetchBoard 被调用，当前 boardId:', boardId.value);
      
      if (!boardId.value) {
        console.error('无法获取版块：boardId 为空');
        return;
      }
      
      loading.value = true;
      
      try {
        console.log('正在获取版块详情，ID:', boardId.value);
        
        // 获取版块详情
        const [boardData, postsData, essenceData] = await Promise.all([
          getBoardDetail(boardId.value).catch(err => {
            console.error('获取版块详情API调用失败:', err);
            throw err;
          }),
          // 获取帖子数据，page_size 设置为 1 只获取数量
          getPosts({ 
            board: boardId.value, 
            page_size: 1,
            page: 1
          }).catch(err => {
            console.error('获取帖子数量API调用失败:', err);
            // 不抛出错误，继续显示版块信息
            return { count: 0, results: [] };
          }),
          // 第 34 批：精华帖数量。**不再展示后端的 today_posts** —— 那是模型上的自增计数器，
          // 实测与实际严重不符（版块 3 存 4、实际当天 0），属于脏数据；
          // 精华数用同样的"page_size=1 只取 count"办法拿，永远是准的。
          getPosts({
            board: boardId.value,
            page_size: 1,
            page: 1,
            is_essence: 'true'
          }).catch(() => ({ count: 0 }))
        ]);
        
        console.log('版块详情数据:', boardData);
        console.log('帖子统计数据:', {
          total: postsData?.count || 0,
          results: postsData?.results?.length || 0
        });
        
        // 更新版块数据
        board.value = {
          ...boardData,
          post_count: postsData?.count || 0,
          essence_count: essenceData?.count || 0
        };
        
      } catch (error) {
        console.error('获取版块数据失败:', error);
        ElMessage.error(t('forum.loadBoardFailed', { detail: error.response?.data?.detail || error.message }));
      } finally {
        loading.value = false;
      }
    };
    
    // 获取帖子列表
    const fetchPosts = async () => {
      if (!boardId.value) {
        console.error('无法获取帖子：boardId 为空');
        return;
      }
      
      loading.value = true;
      
      try {
        const params = {
          board_id: boardId.value,
          page: currentPage.value,
          page_size: pageSize.value,
          // 第 24 批：后端只认 order_by —— 原来发的是 ordering，排序下拉一直是装饰
          order_by: sortBy.value,
          search: searchQuery.value || undefined
        };

        // 第 24 批：标签页此前只是改 activeTab + 重新请求，从不参与筛选
        // （「精华」点了和"全部"完全一样）。现在映射成后端支持的参数。
        if (activeTab.value === 'essence') {
          params.is_essence = 'true';
        } else if (activeTab.value === 'hot') {
          params.order_by = 'hot';
        } else if (activeTab.value === 'latest') {
          params.order_by = '-created_at';
        }

        console.log('获取帖子参数:', params);
        
        const response = await getPosts(params);
        console.log('获取帖子响应:', response);
        
        // 处理不同的响应格式
        if (response) {
          // 处理分页数据
          let results = response.results || [];
          let count = response.count || 0;
          
          // 在前端再次过滤，确保只显示当前版块的帖子
          const originalCount = results.length;
          results = results.filter(post => {
            const postBoardId = post.board?.id || post.board;
            return postBoardId == boardId.value;
          });
          
          // 如果过滤后的数量与原始数量不一致，说明后端返回了错误的数据
          if (originalCount !== results.length) {
            console.warn(`发现 ${originalCount - results.length} 个不属于当前版块的帖子`);
            count = results.length; // 更新总数
          }
          
          // 更新帖子数据和分页信息
          posts.value = results;
          total.value = count;
          totalPages.value = Math.ceil(count / pageSize.value);
          
          // 更新今日帖子数
          const today = new Date().toISOString().split('T')[0];
          todayPosts.value = results.filter(post => {
            return post.created_at && post.created_at.startsWith(today);
          }).length;
          
          console.log(`成功获取 ${results.length} 条帖子，共 ${count} 条，总页数: ${totalPages.value}`);
          console.log('帖子详情:', results.map(post => ({
            id: post.id,
            title: post.title,
            board_id: post.board?.id || post.board,
            created_at: post.created_at
          })));
          
          // 更新版块中的帖子总数
          if (board.value) {
            board.value.post_count = count;
          }
          
          // 滚动到顶部
          nextTick(() => {
            const container = document.querySelector('.forum-content');
            if (container) container.scrollTop = 0;
          });
        }
      } catch (error) {
        console.error('获取帖子列表失败:', error);
        
        // 输出更详细的错误信息
        if (error.response) {
          // 请求已发出，服务器返回了非 2xx 状态码
          console.error('错误响应数据:', error.response.data);
          console.error('错误状态码:', error.response.status);
          
          if (error.response.status === 404) {
            ElMessage.error(t('msg.notFoundResource'));
          } else if (error.response.status === 403) {
            ElMessage.error(t('msg.forbidden'));
          } else {
            ElMessage.error(t('msg.serverErrorWith', { detail: `${error.response.status} ${error.response.statusText || ''}` }));
          }
        } else if (error.request) {
          // 请求已发出但没有收到响应
          console.error('没有收到响应:', error.request);
          ElMessage.error(t('msg.networkError'));
        } else {
          // 其他错误
          console.error('请求配置错误:', error.config);
          ElMessage.error(t('msg.badRequestWith', { detail: error.message || t('msg.unknownError') }));
        }
        
        posts.value = [];
        total.value = 0;
      } finally {
        loading.value = false;
      }
    };
    
    // 处理分页变化
    const handleCurrentChange = (page) => {
      currentPage.value = page;
      fetchPosts();
    };
    
    // 处理标签页切换
    // 第 34 批：标签从 el-radio-group 换成自定义胶囊按钮，需要显式接收并写入 activeTab
    // （原来的实现不带参数、完全依赖 v-model，换成按钮后会让切换失效）。
    const handleTabChange = (value) => {
      if (value !== undefined) {
        activeTab.value = value;
      }
      currentPage.value = 1;
      fetchPosts();
    };
    
    // 处理排序变化
    const handleSortChange = () => {
      currentPage.value = 1;
      fetchPosts();
    };
    
    // 处理搜索
    const handleSearch = () => {
      currentPage.value = 1;
      fetchPosts();
    };
    
    // 点赞/取消点赞
    const toggleLike = async (post, event) => {
      if (!authStore.isAuthenticated) {
        ElMessage.warning(t('msg.loginRequired'));
        router.push({ name: 'login', query: { redirect: route.fullPath } });
        return;
      }

      // 说明：原代码直接用全局 `event`（非标准、仅部分浏览器提供），
      // 编程式调用或缺少该全局时必然 ReferenceError。改为显式接收模板传入的 $event。
      const targetElement = event?.currentTarget?.closest?.('.post-item') || undefined;
      const loadingInstance = ElLoading.service({ 
        target: targetElement,
        background: 'rgba(255, 255, 255, 0.7)',
      });
      
      try {
        // 传 { post: id }：forum.js 的 toggleLike 读的就是 data.post
        // （原先传 {content_type, object_id} → Number(undefined) → NaN → 请求 /posts/NaN/like/）
        const response = await apiToggleLike({ post: post.id });
        
        // 更新帖子点赞状态（后端现已返回 is_liked / like_count）
        const postIndex = posts.value.findIndex(p => p.id === post.id);
        if (postIndex !== -1) {
          posts.value[postIndex].is_liked = response.is_liked;
          posts.value[postIndex].like_count = response.like_count;
        }
      } catch (error) {
        console.error('点赞失败:', error);
        ElMessage.error(t('msg.operationFailedRetry'));
      } finally {
        loadingInstance.close();
      }
    };

    // 收藏/取消收藏（第 24 批新增）
    const toggleFavorite = async (post) => {
      if (!authStore.isAuthenticated) {
        ElMessage.warning(t('msg.loginRequired'));
        router.push({ name: 'login', query: { redirect: route.fullPath } });
        return;
      }

      try {
        const response = await apiToggleFavorite(post.id);
        const postIndex = posts.value.findIndex(p => p.id === post.id);
        if (postIndex !== -1) {
          // 后端返回权威状态，拿不到时才本地取反
          posts.value[postIndex].is_favorited =
            typeof response?.is_favorited === 'boolean' ? response.is_favorited : !post.is_favorited;
        }
        ElMessage.success(
          (typeof response?.is_favorited === 'boolean' ? response.is_favorited : post.is_favorited)
            ? t('post.favoriteAdded') : t('post.favoriteRemoved')
        );
      } catch (error) {
        console.error('收藏失败:', error);
        ElMessage.error(t('msg.operationFailedWith', { detail: error.response?.data?.detail || error.message }));
      }
    };

    const goToPost = (postId) => {
      if (!postId) {
        console.error('帖子ID无效:', postId);
        ElMessage.warning(t('forum.invalidPostId'));
        return;
      }
      
      console.log('正在跳转到帖子详情，ID:', postId);
      
      try {
        // 使用路由跳转到帖子详情页
        router.push({ name: 'post-detail', params: { id: postId } });
      } catch (error) {
        console.error('跳转帖子详情页失败:', error);
        
        // 如果是重复导航错误，可以忽略
        if (error.name === 'NavigationDuplicated') {
          return;
        }
        
        // 显示友好的错误信息（第 83 批：接入 i18n）
        let errorMessage = t('forum.openPostFailed');
        
        if (error.message && error.message.includes('No match for')) {
          errorMessage = t('forum.postNotFound');
        } else if (error.message && error.message.includes('Failed to fetch')) {
          errorMessage = t('msg.networkError');
        }
        
        ElMessage.error(errorMessage);
      }
    };
    
    // 跳转到发帖页面
    const goToNewPost = () => {
      try {
        // 检查是否已登录
        if (!authStore.isAuthenticated) {
          ElMessage.warning(t('msg.loginRequired'));
          router.push({ 
            name: 'login', 
            query: { 
              redirect: route.fullPath 
            } 
          });
          return;
        }
        
        // 如果当前有版块ID，则传递版块ID
        const params = boardId.value ? { boardId: boardId.value } : {};
        
        // 跳转到发帖页面
        router.push({ 
          name: 'new-post',
          query: params
        });
      } catch (error) {
        console.error('跳转发帖页面失败:', error);
        ElMessage.error(t('forum.navigateFailed'));
      }
    };
    
    // 跳转到用户个人主页
    const goToUserProfile = (userId) => {
      if (!userId) {
        console.error('用户ID无效:', userId);
        ElMessage.warning(t('forum.invalidUserId'));
        return;
      }
      
      console.log('正在跳转到用户主页，用户ID:', userId);
      
      try {
        // 使用路由跳转到用户主页
        router.push({ 
          name: 'userProfile', 
          params: { id: userId } 
        });
      } catch (error) {
        console.error('跳转用户主页失败:', error);
        
        // 如果是重复导航错误，可以忽略
        if (error.name === 'NavigationDuplicated') {
          return;
        }
        
        // 显示友好的错误信息（第 83 批：接入 i18n）
        let errorMessage = t('forum.openUserFailed');
        
        if (error.message && error.message.includes('No match for')) {
          errorMessage = t('forum.userNotFound');
        } else if (error.message && error.message.includes('Failed to fetch')) {
          errorMessage = t('msg.networkError');
        }
        
        ElMessage.error(errorMessage);
      }
    };

    // 发帖成功后的回调
    const postCreated = () => {
      console.log('检测到新帖子创建，刷新帖子列表...');
      // 刷新帖子列表
      fetchPosts();
      // 如果当前在版块页面，也刷新版块统计信息
      if (boardId.value) {
        fetchBoard();
      }
    };

      // 将 postCreated 方法挂载到 window 对象，以便 NewPostView 可以调用
    onMounted(() => {
      window.postCreated = postCreated;
    });

    // 组件卸载时清理
    onUnmounted(() => {
      if (window.postCreated === postCreated) {
        delete window.postCreated;
      }
    });

    // ---------- 第 34 批新增的展示辅助 ----------
    /** 后端存的是 Font Awesome 名字（bug / seedling / flask） */
    const boardIconClass = (icon) => `fas fa-${(icon || 'comments').replace(/^fa-/, '')}`;

    /** 排序 / 筛选胶囊（对应后端已支持的参数）；标签走 i18n（第 60 批） */
    const tabs = computed(() => [
      { value: 'all', label: t('forum.filterAll'), icon: 'fas fa-list-ul' },
      { value: 'essence', label: t('forum.essence'), icon: 'fas fa-star' },
      { value: 'latest', label: t('forum.latest'), icon: 'fas fa-clock' },
      { value: 'hot', label: t('forum.hot'), icon: 'fas fa-fire' },
    ]);

    /**
     * 帖子摘要：后端列表接口**没有 excerpt 字段**，原来模板却读 `post.excerpt`，
     * 于是每条帖子下面恒显示"暂无内容预览"。这里从正文里剥掉 HTML 标签取前 80 字。
     *
     * 第 85 批：英文界面下用 `content_en`（`localizedField`），否则摘要栏是整页
     * 唯一的残留中文 —— 标题已经英文化、摘要还是中文，看起来像"翻译只做了一半"。
     */
    const excerptOf = (post) => {
      const raw = String(
        localizedField(post, 'content') || post?.excerpt || '',
      ).trim();
      if (!raw) return t('forum.noPreview');
      const text = raw
        .replace(/<[^>]+>/g, ' ')
        .replace(/&nbsp;/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      return text.length > 80 ? `${text.slice(0, 80)}…` : text;
    };

    const goToForum = () => router.push({ name: 'forum' });

    const clearSearch = () => {
      searchQuery.value = '';
      handleSearch();
    };

    // 返回模板所需的数据和方法
    return {
      board,
      posts,
      loading,
      activeTab,
      sortBy,
      searchQuery,
      currentPage,
      pageSize,
      total,
      boardId,
      tabs,
      boardIconClass,
      excerptOf,
      clearSearch,
      t,
      // 第 79 批：模板里要按语言取版块名/描述（Options API 不 return 就是 undefined）
      localizedField,
      goToForum,
      fetchBoard,
      fetchPosts,
      handleCurrentChange,
      handleTabChange,
      handleSortChange,
      handleSearch,
      toggleLike,
      toggleFavorite,
      goToPost,
      goToNewPost,
      goToUserProfile,
      formatTime,
      postCreated // 导出 postCreated 方法，以便在模板中使用（如果需要）
    };
  }
};
</script>

<style scoped>
/* ==========================================================================
   版块详情页样式（第 34 批重写）
   --------------------------------------------------------------------------
   这一页原先有**三套互相覆盖**的样式块：
     · 第 1 套（蓝色渐变 + 白字）—— 最早的设计
     · 第 2 套（蓝色渐变 + 白字，更细）—— 又一次覆写
     · 第 3 套（"现代化覆写"，浅绿渐变）—— 只改了背景，**白字没跟着改**
   于是版块名、帖子/今日两个标签全成了白字白底（页面上只剩两个数字），
   而"帖子/今日"用的还是 Element Plus 的图标字体类名（EP2 已无），图标也全是空的。
   现在统一使用主题里的公用块（.admin-hero / .stat-tile / .panel-card / .panel-head），
   本文件只保留版块页特有的少量样式。
   ========================================================================== */
.forum-board-container {
  /* 父级 .main-content 是 flex + align-items:center，只写 max-width 会被按内容收缩 */
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px 20px 40px;
}

.board-hero {
  margin-bottom: 18px;
}

.board-stats-row {
  margin-bottom: 18px;
}

/* 头条右侧的排序 / 搜索 */
.board-filters {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sort-select {
  width: 132px;
}

.search-input {
  width: 230px;
}

/* 排序 / 筛选胶囊 */
.board-tabs {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.board-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--surface);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-600);
  cursor: pointer;
  transition: all 0.2s ease;
}

.board-tab:hover {
  border-color: var(--brand-300);
  color: var(--brand-700);
}

.board-tab.is-active {
  color: #fff;
  border-color: transparent;
  background: var(--gradient-brand);
  box-shadow: 0 6px 14px rgba(31, 99, 67, 0.22);
}

.search-hint {
  margin-left: auto;
  font-size: 12.5px;
  color: var(--ink-500);
}

.search-hint button {
  margin-left: 6px;
  border: none;
  background: none;
  color: var(--brand-700);
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  text-decoration: underline;
}

.loading-container {
  padding: 8px 0;
}

/* ---------- 帖子行 ---------- */
.post-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.post-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid var(--brand-100);
  border-radius: var(--radius);
  background: linear-gradient(160deg, #ffffff, #f6fbf8);
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.post-item:hover {
  transform: translateX(3px);
  border-color: var(--brand-300);
  box-shadow: var(--shadow-sm);
}

.post-item.is-pinned {
  border-left: 3px solid var(--danger);
}

.post-item.is-essence {
  border-left: 3px solid var(--warning);
}

.post-avatar {
  flex-shrink: 0;
  cursor: pointer;
  background: var(--brand-500);
  color: #fff;
  font-weight: 700;
}

.post-content {
  flex: 1;
  min-width: 0;
}

.post-title {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 700;
  color: var(--ink-900);
}

.post-excerpt {
  margin: 0 0 8px;
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--ink-500);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.post-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 12.5px;
  color: var(--ink-400);
}

.post-meta i {
  margin-right: 4px;
}

/* 右侧统计：回复 / 点赞 / 收藏 */
.post-stats {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
  text-align: center;
}

.post-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  min-width: 42px;
  border: none;
  background: none;
  padding: 0;
  font-family: inherit;
  line-height: 1.25;
  color: var(--ink-400);
}

.post-stat b {
  font-size: 15px;
  font-weight: 700;
  color: var(--ink-700);
}

.post-stat i {
  font-style: normal;
  font-size: 11px;
}

.post-stat.is-action {
  cursor: pointer;
  border-radius: 10px;
  padding: 4px 6px;
  transition: background-color 0.18s ease, color 0.18s ease;
}

.post-stat.is-action:hover {
  background: var(--brand-50);
}

.post-stat.is-action.is-on b,
.post-stat.is-action.is-on i {
  color: var(--brand-600);
}

.pagination-container {
  display: flex;
  justify-content: center;
  margin-top: 18px;
}

.back-to-top {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--gradient-brand);
  color: #fff;
  box-shadow: 0 8px 18px rgba(31, 99, 67, 0.24);
}

/* 列表增删的过渡动画 */
.post-list-enter-active,
.post-list-leave-active {
  transition: all 0.25s ease;
}

.post-list-enter-from,
.post-list-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

@media (max-width: 900px) {
  .board-filters {
    width: 100%;
    margin-top: 8px;
  }

  .search-input {
    width: 100%;
  }

  .post-item {
    flex-direction: column;
    align-items: flex-start;
  }

  .post-stats {
    gap: 22px;
  }
}
</style>
