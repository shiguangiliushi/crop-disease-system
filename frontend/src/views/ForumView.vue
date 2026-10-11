<template>
  <div class="forum-container">
    <!-- ============ 页头（第 32 批：原来只有一行裸标题 + 两个按钮） ============ -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-comments"></i></span>
        <div>
          <h1>{{ t('forum.title') }}</h1>
          <p>{{ t('forum.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-button v-if="authStore.isAuthenticated" plain @click="goToFavorites">
          <i class="fas fa-bookmark"></i> {{ t('forum.myFavorites') }}
        </el-button>
        <el-button v-if="authStore.isAuthenticated" plain @click="goToMyPosts">
          <i class="fas fa-file-lines"></i> {{ t('forum.myPosts') }}
        </el-button>
        <!-- 第 166 批：草稿入口。编辑页每 30 秒自动把草稿存到服务端，
             此前**没有任何入口**能看到它们（农户写到一半关掉页面就再也找不回来）。 -->
        <el-button v-if="authStore.isAuthenticated" plain @click="goMyDrafts">
          <i class="fas fa-file-pen"></i> {{ t('drafts.entry') }}
          <span v-if="draftCount" class="drafts-badge">{{ draftCount }}</span>
        </el-button>
        <el-button class="btn-on-brand" @click="goToNewPost">
          <i class="fas fa-pen"></i> {{ t('forum.newPost') }}
        </el-button>
      </div>
    </header>

    <!-- ============ 概览（第 32 批新增：原先首页没有任何整体数据） ============ -->
    <div class="admin-stats">
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-layer-group"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.boards }}</div>
          <div class="stat-tile-label">{{ t('forum.statBoards') }}</div>
        </div>
      </div>
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-comment-dots"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.posts }}</div>
          <div class="stat-tile-label">{{ t('forum.statPosts') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--ok">
        <span class="stat-tile-icon"><i class="fas fa-star"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.essence }}</div>
          <div class="stat-tile-label">{{ t('forum.statEssence') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--processing">
        <span class="stat-tile-icon"><i class="fas fa-fire"></i></span>
        <div>
          <div class="stat-tile-value">{{ hotPosts.length }}</div>
          <div class="stat-tile-label">{{ t('forum.statHot') }}</div>
        </div>
      </div>
      <div v-if="authStore.isAuthenticated" class="stat-tile stat-tile--pending">
        <span class="stat-tile-icon"><i class="fas fa-file-lines"></i></span>
        <div>
          <div class="stat-tile-value">{{ stats.mine }}</div>
          <div class="stat-tile-label">{{ t('forum.myPosts') }}</div>
        </div>
      </div>
    </div>

    <!-- ============ 版块 ============ -->
    <section class="board-grid">
      <el-skeleton v-if="loading" :rows="1" animated class="board-skeleton" />

      <article
        v-for="board in boards"
        v-else
        :key="board.id"
        class="board-card"
        @click="goToBoard(board.id)"
      >
        <div class="board-head">
          <!-- 第 32 批修复：原来渲染的是 `el-icon-${board.icon}` 类名，
               而后端存的是 Font Awesome 名字（bug / seedling / flask），
               类名不存在 → 版块图标一直是空白方块。 -->
          <span class="board-icon"><i :class="boardIconClass(board.icon)"></i></span>
          <div class="board-title">
            <h3>{{ localizedField(board, 'name') }}</h3>
            <p>{{ localizedField(board, 'description') || t('forum.noBoardDesc') }}</p>
          </div>
          <span class="board-count">{{ board.post_count }}<i>{{ t('forum.postsUnit') }}</i></span>
        </div>

        <div v-if="board.latest_post" class="board-latest">
          <span class="latest-tag">{{ t('forum.latest') }}</span>
          <span class="latest-title" :title="localizedField(board.latest_post, 'title')">
            {{ localizedField(board.latest_post, 'title') }}
          </span>
          <span class="latest-meta">
            {{ board.latest_post.author_name }} · {{ formatTime(board.latest_post.created_at) }}
          </span>
        </div>
        <div v-else class="board-latest is-empty">
          <i class="fas fa-seedling"></i> {{ t('forum.emptyBoard') }}
        </div>
      </article>
    </section>

    <!-- ============ 帖子列表 + 侧栏（第 32 批新增主列表） ============ -->
    <div class="forum-main">
      <section class="panel-card post-panel">
        <div class="panel-head">
          <span class="panel-icon"><i class="fas fa-list-ul"></i></span>
          <h2 class="panel-title">{{ activeTabLabel }}</h2>
          <span class="panel-count">{{ t('forum.totalCount', { count: postTotal }) }}</span>
          <div class="panel-head-right">
            <el-input
              v-model="keyword"
              size="small"
              class="post-search"
              :placeholder="t('forum.searchPlaceholder')"
              clearable
              @keyup.enter="applySearch"
              @clear="applySearch"
            >
              <template #prefix><i class="fas fa-search"></i></template>
            </el-input>
            <el-button size="small" @click="applySearch">
              <i class="fas fa-search"></i> {{ t('forum.search') }}
            </el-button>
          </div>
        </div>

        <div class="panel-body">
          <!-- 排序 / 筛选（调用后端已支持但前端从未用过的参数） -->
          <div class="post-tabs">
            <button
              v-for="tab in tabs"
              :key="tab.key"
              type="button"
              class="post-tab"
              :class="{ 'is-active': activeTab === tab.key }"
              @click="switchTab(tab.key)"
            >
              <i :class="tab.icon"></i> {{ tab.label }}
            </button>
            <span v-if="keyword" class="search-hint">
              {{ t('forum.searchHint', { keyword }) }}
              <button type="button" @click="clearSearch">{{ t('forum.clear') }}</button>
            </span>
          </div>

          <el-skeleton v-if="loadingPosts" :rows="5" animated />

          <el-empty
            v-else-if="posts.length === 0"
            :description="keyword ? t('forum.emptySearch') : t('forum.emptyCategory')"
          >
            <el-button type="primary" @click="goToNewPost">{{ t('forum.firstPost') }}</el-button>
          </el-empty>

          <ul v-else class="post-list">
            <li
              v-for="post in posts"
              :key="post.id"
              class="post-row"
              @click="goToPost(post.id)"
            >
              <div class="post-row-main">
                <div class="post-row-title">
                  <el-tag v-if="post.is_pinned" size="small" type="danger" effect="dark">{{ t('forum.tagPinned') }}</el-tag>
                  <el-tag v-if="post.is_essence" size="small" type="warning" effect="dark">{{ t('forum.tagEssence') }}</el-tag>
                  <el-tag v-if="post.status === 'draft'" size="small" type="info">{{ t('forum.tagDraft') }}</el-tag>
                  <!-- 第 38 批：待审核（作者自己的帖子尚未通过审核，别人看不到） -->
                  <el-tag v-if="post.status === 'pending'" size="small" type="warning">{{ t('forum.tagPending') }}</el-tag>
                  <span class="title-text">{{ localizedField(post, 'title') || t('forum.untitled') }}</span>
                </div>
                <div class="post-row-meta">
                  <span
                    v-if="post.board"
                    class="meta-board"
                    @click.stop="goToBoard(post.board.id)"
                  >
                    <i class="fas fa-layer-group"></i> {{ localizedField(post.board, 'name') }}
                  </span>
                  <span><i class="fas fa-user"></i> {{ post.author?.username || t('forum.unknownUser') }}</span>
                  <span><i class="fas fa-clock"></i> {{ formatTime(post.created_at) }}</span>
                </div>
              </div>

              <div class="post-row-stats">
                <span><b>{{ post.view_count || 0 }}</b><i>{{ t('forum.views') }}</i></span>
                <span><b>{{ post.comment_count || 0 }}</b><i>{{ t('forum.replies') }}</i></span>
                <span :class="{ 'is-liked': post.like_count > 0 }">
                  <b>{{ post.like_count || 0 }}</b><i>{{ t('forum.likes') }}</i>
                </span>
              </div>

              <!--
                第 145 批：版主的「置顶 / 加精」开关
                ----------------------------------------------------------------
                这两个能力（`posts/<id>/set_pinned/`、`set_essence/`）第 24 批就写好了，
                但界面上一直只有**作者自己的编辑页**有勾选框 —— 也就是说
                "版主给别人的帖子加精/置顶"**根本做不到**（接口成了死代码）。
                开关放在这里（而不是控制台）是因为版主就是在浏览帖子时决定哪条值得置顶。
                ⚠️ `@click.stop`：整行是可点的（进帖子详情），别让按钮顺手把人带走。
              -->
              <div v-if="canModerate" class="post-row-moderate" @click.stop>
                <el-button
                  size="small"
                  :type="post.is_pinned ? 'danger' : 'default'"
                  :plain="!post.is_pinned"
                  :loading="moderatingId === `pin-${post.id}`"
                  @click="togglePin(post)"
                >
                  <i class="fas fa-thumbtack"></i>
                  {{ post.is_pinned ? t('forum.unpinAction') : t('forum.pinAction') }}
                </el-button>
                <el-button
                  size="small"
                  :type="post.is_essence ? 'warning' : 'default'"
                  :plain="!post.is_essence"
                  :loading="moderatingId === `essence-${post.id}`"
                  @click="toggleEssence(post)"
                >
                  <i class="fas fa-star"></i>
                  {{ post.is_essence ? t('forum.unessenceAction') : t('forum.essenceAction') }}
                </el-button>
              </div>
            </li>
          </ul>

          <div v-if="postTotal > pageSize" class="post-pagination">
            <el-pagination
              background
              layout="prev, pager, next, total"
              :total="postTotal"
              :page-size="pageSize"
              :current-page="page"
              @current-change="changePage"
            />
          </div>
        </div>
      </section>

      <!-- 侧栏 -->
      <aside class="forum-side">
        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-fire"></i></span>
            <h3 class="panel-title">{{ t('forum.hotPosts') }}</h3>
            <div class="panel-head-right">
              <el-button size="small" text :loading="loadingHotPosts" @click="fetchHotPosts">
                <i class="fas fa-sync-alt"></i>
              </el-button>
            </div>
          </div>
          <div class="panel-body">
            <el-skeleton v-if="loadingHotPosts && hotPosts.length === 0" :rows="4" animated />
            <ol v-else-if="hotPosts.length" class="hot-list">
              <li v-for="(post, index) in hotPosts" :key="post.id" @click="goToPost(post.id)">
                <span class="hot-rank" :class="`is-${index + 1}`">{{ index + 1 }}</span>
                <div class="hot-info">
                  <p class="hot-title" :title="localizedField(post, 'title')">{{ localizedField(post, 'title') || t('forum.untitled') }}</p>
                  <p class="hot-meta">
                    {{ post.author?.username || t('forum.unknownUser') }} ·
                    {{ t('forum.hotMeta', { likes: post.like_count || 0, replies: post.comment_count || 0 }) }}
                  </p>
                </div>
              </li>
            </ol>
            <el-empty v-else :description="t('forum.noHotPosts')" :image-size="70" />
          </div>
        </section>

        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-bolt"></i></span>
            <h3 class="panel-title">{{ t('forum.quickLinks') }}</h3>
          </div>
          <div class="panel-body quick-links">
            <button type="button" @click="goToNewPost">
              <i class="fas fa-pen"></i> {{ t('forum.newPost') }}
            </button>
            <button v-if="authStore.isAuthenticated" type="button" @click="goToFavorites">
              <i class="fas fa-bookmark"></i> {{ t('forum.myFavorites') }}
            </button>
            <button v-if="authStore.isAuthenticated" type="button" @click="goToMyPosts">
              <i class="fas fa-file-lines"></i> {{ t('forum.myPosts') }}
            </button>
            <RouterLink to="/detect">
              <i class="fas fa-camera"></i> {{ t('forum.quickDetect') }}
            </RouterLink>
            <RouterLink to="/pests">
              <i class="fas fa-book-open-reader"></i> {{ t('forum.quickWiki') }}
            </RouterLink>
          </div>
        </section>
      </aside>
    </div>

    <!-- 发帖与交流指引（第 31 批新增，第 32 批随新版排版保留；第 59 批接入多语言） -->
    <PageExtras
      icon="fas fa-lightbulb"
      :title="t('forum.guideTitle')"
      :subtitle="t('forum.guideSubtitle')"
      :items="guideItems"
    />
  </div>
</template>

<script>
/**
 * 论坛首页（第 32 批重做）
 * ------------------------------------------------------------------
 * 这一版解决的功能问题：
 * 1. 首页原来**只有热门帖子**（最多 10 条），想看别的帖子必须点进版块 ——
 *    现在首页就有完整的帖子列表：最新 / 热门 / 最新回复 / 精华 四种排序与筛选，
 *    并且带分页、带关键词搜索（后端 `search` 早就支持，前端一直没用）。
 * 2. 版块卡片上的"最新帖子""帖子数"原来是这样算的：**把全站帖子一次性拉下来**
 *    （`page_size: 9999`）在前端分组统计 —— 帖子多了就是灾难，而且一大堆调试日志。
 *    现在每个版块只发一个小请求（`page_size=1`）拿 `count` 与最新一帖，
 *    并且**不再相信后端 boards 里的 post_count/today_posts**
 *    （实测这两个计数与实际不符：版块1 存 11 实为 4，版块3 存 4 实为 1）。
 * 3. 版块图标此前渲染为 `el-icon-{icon}`，而后端存的是 Font Awesome 名字，类名不存在
 *    → 图标一直是一个空白方块，现在按 FA 渲染。
 * 4. 首页没有任何整体数据，现在补了版块/帖子/精华/回复四个统计。
 */
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import {
  getForumBoards, getHotPosts, getPosts, getMyPosts,
  setPostEssence, setPostPinned,   // 第 145 批：版主置顶/加精
} from '@/api/forum';
import { formatApiError } from '@/api/http';
import { formatTime } from '@/utils/date';
import { useAuthStore } from '@/stores/auth';
import PageExtras from '@/components/PageExtras.vue';
import { useI18n } from '@/i18n';  // 第 59 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 72 批：内容数据多语言

// 只展示这三个业务版块（沿用原有产品口径）
const ALLOWED_BOARDS = ['作物病害交流', '种植技术', '农药肥料'];

// 首页帖子列表的排序 / 筛选方式 —— 全部对应后端 PostViewSet.get_queryset 已支持的参数
// 标签走 i18n（第 59 批）：labelKey 在 setup 里用 t() 解析，见 tabs computed
const TABS = [
  { key: 'latest', labelKey: 'forum.latest', icon: 'fas fa-clock', params: { ordering: 'latest' } },
  { key: 'hot', labelKey: 'forum.hot', icon: 'fas fa-fire', params: { ordering: 'hot' } },
  { key: 'reply', labelKey: 'forum.latestReply', icon: 'fas fa-comments', params: { ordering: 'last_reply' } },
  { key: 'essence', labelKey: 'forum.essence', icon: 'fas fa-star', params: { ordering: 'latest', is_essence: 'true' } },
];

export default {
  name: 'ForumView',
  components: { PageExtras },
  setup() {
    const { t } = useI18n();  // 第 59 批：多语言
    const { localizedField } = useLocalized();  // 第 72 批：版块名等内容的英文
    const router = useRouter();
    const authStore = useAuthStore();

    const boards = ref([]);
    const hotPosts = ref([]);
    const posts = ref([]);
    const loading = ref(true);
    const loadingHotPosts = ref(false);
    const loadingPosts = ref(false);

    const stats = ref({ boards: 0, posts: 0, essence: 0, mine: 0 });

    const activeTab = ref('latest');
    const keyword = ref('');
    const searchKeyword = ref(''); // 已提交的搜索词（与输入框分离，避免每敲一个字就请求）
    const page = ref(1);
    const pageSize = ref(10);
    const postTotal = ref(0);

    let timer = null;

    // 标签文案随语言切换（第 59 批）：TABS 里存的是 key
    const tabs = computed(() => TABS.map((tab) => ({ ...tab, label: t(tab.labelKey) })));

    const activeTabLabel = computed(
      () => tabs.value.find((tab) => tab.key === activeTab.value)?.label || t('forum.latest'),
    );

    // 底部发帖指引卡片（原来内联在模板属性里，无法随语言切换）
    const guideItems = computed(() => [
      { icon: 'fas fa-magnifying-glass', title: t('forum.guide1'), text: t('forum.guide1Desc') },
      { icon: 'fas fa-clipboard-list', title: t('forum.guide2'), text: t('forum.guide2Desc') },
      {
        icon: 'fas fa-image',
        title: t('forum.guide3'),
        text: t('forum.guide3Desc'),
        more: t('forum.guide3Link'),
        to: '/detect',
      },
      { icon: 'fas fa-star', title: t('forum.guide4'), text: t('forum.guide4Desc') },
    ]);

    /** 后端存的是 Font Awesome 名字（bug / seedling / flask），直接映射成 `fas fa-xxx` */
    const boardIconClass = (icon) => {
      const name = (icon || 'comments').replace(/^fa-/, '');
      return `fas fa-${name}`;
    };

    /**
     * 版块列表：并发为每个版块取"帖子数 + 最新一帖"。
     * 用 `page_size=1` 只拿一条，靠分页返回的 `count` 得到真实帖子数。
     */
    const fetchBoards = async () => {
      const list = await getForumBoards();
      const allowed = (list || []).filter((board) => ALLOWED_BOARDS.includes(board.name));

      const enriched = await Promise.all(
        allowed.map(async (board) => {
          try {
            const data = await getPosts({ board: board.id, page_size: 1, ordering: 'latest' });
            const latest = data.results?.[0] || null;
            return {
              ...board,
              post_count: data.count || 0,
              latest_post: latest
                ? {
                    id: latest.id,
                    // 第 83 批：兜底文案接入 i18n
                    title: latest.title || t('common.untitled'),
                    // 第 85 批：这里是把帖子字段**挑出来重组成新对象**，必须把 title_en
                    // 一起带上 —— 否则 localizedField() 拿不到英文标题，英文界面下
                    // "最新：" 后面又是中文标题（版块卡片上唯一残留的中文）。
                    title_en: latest.title_en || '',
                    author_name: latest.author?.username || t('forum.unknownUser'),
                    created_at: latest.created_at,
                  }
                : null,
            };
          } catch (error) {
            console.warn(`获取版块 ${board.name} 的帖子失败:`, error);
            return { ...board, post_count: 0, latest_post: null };
          }
        }),
      );

      boards.value = enriched;
      stats.value.boards = enriched.length;
    };

    /** 统计：帖子总数、精华数、我的帖子数（各一个轻量请求，靠分页 count 拿总数） */
    const fetchStats = async () => {
      try {
        const requests = [
          getPosts({ page_size: 1 }),
          getPosts({ page_size: 1, is_essence: 'true' }),
        ];
        if (authStore.isAuthenticated) requests.push(getMyPosts({ page_size: 1 }));

        const [all, essence, mine] = await Promise.all(requests);
        stats.value.posts = all.count || 0;
        stats.value.essence = essence.count || 0;
        stats.value.mine = mine?.count || 0;
      } catch (error) {
        console.warn('获取论坛统计失败:', error);
      }
    };

    /** 帖子列表（分页 + 排序/筛选 + 搜索） */
    const fetchPosts = async () => {
      loadingPosts.value = true;
      try {
        const tab = TABS.find((item) => item.key === activeTab.value) || TABS[0];
        const params = {
          page: page.value,
          page_size: pageSize.value,
          ...tab.params,
        };
        if (searchKeyword.value) params.search = searchKeyword.value;

        const data = await getPosts(params);
        posts.value = data.results || [];
        postTotal.value = data.count || 0;
      } catch (error) {
        console.error('获取帖子列表失败:', error);
        posts.value = [];
        postTotal.value = 0;
        ElMessage.error(t('forum.loadPostsFailed'));
      } finally {
        loadingPosts.value = false;
      }
    };

    const fetchHotPosts = async () => {
      loadingHotPosts.value = true;
      try {
        const data = await getHotPosts(10);
        hotPosts.value = Array.isArray(data) ? data : [];
      } catch (error) {
        console.error('获取热门帖子失败:', error);
        ElMessage.error(t('forum.loadHotFailed'));
      } finally {
        loadingHotPosts.value = false;
      }
    };

    const initData = async () => {
      loading.value = true;
      try {
        await Promise.all([fetchBoards(), fetchStats(), fetchPosts(), fetchHotPosts()]);
      } catch (error) {
        console.error('初始化论坛数据失败:', error);
      } finally {
        loading.value = false;
      }
    };

    onMounted(() => {
      fetchDraftCount();   // 第 166 批：草稿角标
    });

    onMounted(() => {
      initData();
      // 定时刷新热门帖子与统计，例如每 5 分钟
      timer = setInterval(() => {
        fetchHotPosts();
      }, 300000);
    });

    onUnmounted(() => {
      if (timer) clearInterval(timer);
    });

    const switchTab = (key) => {
      if (activeTab.value === key) return;
      activeTab.value = key;
      page.value = 1;
      fetchPosts();
    };

    const applySearch = () => {
      searchKeyword.value = keyword.value.trim();
      page.value = 1;
      fetchPosts();
    };

    const clearSearch = () => {
      keyword.value = '';
      searchKeyword.value = '';
      page.value = 1;
      fetchPosts();
    };

    const changePage = (nextPage) => {
      page.value = nextPage;
      fetchPosts();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const goToBoard = (boardId) => router.push({ name: 'forum-board', params: { id: boardId } });
    const goToPost = (postId) => router.push({ name: 'post-detail', params: { id: postId } });

    // ========================================================================
    // 第 145 批：版主的「置顶 / 加精」
    // ========================================================================
    /**
     * 谁能看到这两个按钮
     *
     * 与后端 `is_moderator()` **同一口径**：有 `review` 内容模块（信息编辑员/管理员）
     * 或属于 Moderators 组。前端拿不到"组"的信息，所以这里按前两条判断 ——
     * 只看组的那种用户看不到按钮（后端仍会放行），这是刻意选择：
     * **画一个后端可能拒绝的按钮，比少画一个按钮更糟**（后者只是不显示，用户不会白点）。
     */
    const canModerate = computed(() => Boolean(
      authStore.hasContentModule?.('review')
      || authStore.user?.is_staff
      || authStore.user?.is_superuser,
    ));

    const moderatingId = ref('');

    /**
     * 置顶 / 取消置顶
     *
     * 接口返回的是**最新状态**（`{id, is_pinned}`），所以用返回值就地更新那一行，
     * 不整页重载 —— 重载会把版主正在看的列表滚回顶部。置顶会改变排序，
     * 但"点完就跳位置"更让人困惑，所以这里只改标记，让用户自己刷新看新顺序。
     */
    const togglePin = async (post) => {
      moderatingId.value = `pin-${post.id}`;
      try {
        const data = await setPostPinned(post.id, !post.is_pinned);
        post.is_pinned = data?.is_pinned ?? !post.is_pinned;
        ElMessage.success(post.is_pinned ? t('forum.pinOk') : t('forum.unpinOk'));
      } catch (error) {
        ElMessage.error(formatApiError(error, t('forum.pinFailed')));
      } finally {
        moderatingId.value = '';
      }
    };

    /** 加精 / 取消加精（同上） */
    const toggleEssence = async (post) => {
      moderatingId.value = `essence-${post.id}`;
      try {
        const data = await setPostEssence(post.id, !post.is_essence);
        post.is_essence = data?.is_essence ?? !post.is_essence;
        ElMessage.success(post.is_essence ? t('forum.essenceOk') : t('forum.unessenceOk'));
      } catch (error) {
        ElMessage.error(formatApiError(error, t('forum.essenceFailed')));
      } finally {
        moderatingId.value = '';
      }
    };
    const goToNewPost = () => router.push({ name: 'new-post' });
    const goToFavorites = () => router.push({ name: 'forum-favorites' });

    /** 我的帖子：用户资料页的「发布的帖子」标签就是这个列表 */
    const goToMyPosts = () => {
      const userId = authStore.user?.id;
      if (!userId) {
        ElMessage.warning(t('msg.loginRequired'));
        return;
      }
      router.push({ name: 'user-profile', params: { id: userId } });
    };

    // 「我的草稿」入口与数量（第 166 批）
    //
    // 为什么要有：编辑页每 30 秒自动把草稿存到**服务端**（status='draft'），
    // 但在这一批之前前端**没有任何入口**能看到它们 —— 农户写到一半关掉页面，
    // 那条半成品就永远躺在库里（评审意见点名的就是这个）。
    // 数量用分页的 count 拿，一次轻量请求（page_size=1）。
    const draftCount = ref(0);
    const goMyDrafts = () => router.push({ name: 'my-drafts' });
    const fetchDraftCount = async () => {
      try {
        const userId = authStore.user?.id;
        if (!userId) return;
        const response = await getPosts({ status: 'draft', author: userId, page_size: 1 });
        draftCount.value = response?.count ?? (Array.isArray(response) ? response.length : 0);
      } catch (error) {
        console.warn('[forum] 草稿数量获取失败:', error?.message || error);
      }
    };

    return {
      boards,
      hotPosts,
      posts,
      stats,
      loading,
      loadingHotPosts,
      loadingPosts,
      activeTab,
      activeTabLabel,
      localizedField,
      tabs,
      guideItems,
      t,
      keyword,
      searchKeyword,
      page,
      pageSize,
      postTotal,
      authStore,
      formatTime,
      boardIconClass,
      fetchHotPosts,
      switchTab,
      applySearch,
      clearSearch,
      changePage,
      goToBoard,
      goToPost,
      // 第 145 批：版主置顶/加精
      canModerate, moderatingId, togglePin, toggleEssence,
      goToNewPost,
      goToFavorites,
      goToMyPosts,
      goMyDrafts,
      draftCount,
    };
  },
};
</script>

<style scoped>
/* 第 166 批：草稿数量角标（有草稿才显示） */
.drafts-badge {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--el-color-warning, #e6a23c);
  color: #fff;
  font-size: 11px;
  line-height: 16px;
}

.forum-container {
  /* 第 32 批：`.main-content` 是 `display:flex; align-items:center`，
     只写 max-width 的话弹性子项会**按内容收缩**（实测只有 918px 而不是 1240px），
     既浪费两侧空间，又把版块网格挤成 2 列。补 width:100% 让它真正吃满 max-width。 */
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 24px 20px 40px;
}

/* ============ 版块卡片 ============ */
.board-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.board-skeleton {
  grid-column: 1 / -1;
}

.board-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
  border: 1px solid var(--brand-200);
  border-radius: var(--radius-lg);
  background: linear-gradient(160deg, #ffffff, #f3faf6);
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.board-card:hover {
  transform: translateY(-3px);
  border-color: var(--brand-300);
  box-shadow: var(--shadow-sm);
}

.board-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.board-icon {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 14px;
  font-size: 19px;
  color: #fff;
  background: linear-gradient(135deg, var(--brand-500), var(--brand-700));
  box-shadow: 0 8px 16px rgba(25, 79, 55, 0.2);
}

.board-title {
  flex: 1;
  min-width: 0;
}

.board-title h3 {
  margin: 0 0 3px;
  font-size: 16px;
  font-weight: 800;
  color: var(--ink-900);
}

.board-title p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--ink-500);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.board-count {
  flex-shrink: 0;
  font-size: 20px;
  font-weight: 800;
  line-height: 1;
  color: var(--brand-700);
}

.board-count i {
  margin-left: 2px;
  font-size: 12px;
  font-style: normal;
  font-weight: 600;
  color: var(--ink-400);
}

.board-latest {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 10px;
  background: var(--brand-50);
  border: 1px solid var(--brand-100);
  font-size: 12.5px;
  min-width: 0;
}

.board-latest.is-empty {
  color: var(--ink-500);
  background: var(--ink-50);
  border-color: var(--border);
}

.latest-tag {
  flex-shrink: 0;
  padding: 1px 7px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: var(--brand-500);
}

.latest-title {
  flex: 1;
  min-width: 0;
  font-weight: 600;
  color: var(--ink-800);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.latest-meta {
  flex-shrink: 0;
  color: var(--ink-400);
}

/* ============ 主区（列表 + 侧栏） ============ */
.forum-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 18px;
  align-items: start;
}

.post-panel {
  min-width: 0;
}

.post-search {
  width: 200px;
}

/* 排序 / 筛选胶囊 */
.post-tabs {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.post-tab {
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

.post-tab:hover {
  border-color: var(--brand-300);
  color: var(--brand-700);
}

.post-tab.is-active {
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

/* 帖子行 */
.post-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.post-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 13px 16px;
  border: 1px solid var(--brand-100);
  border-radius: var(--radius);
  background: linear-gradient(160deg, #ffffff, #f6fbf8);
  cursor: pointer;
  /* 第 45 批（移动端）：flex 项默认 min-width:auto，会被内容撑得比父容器还宽，
     实测窄屏下每行比面板宽 21px（被 overflow:hidden 裁掉）。加 min-width:0 允许收缩。 */
  min-width: 0;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.post-row:hover {
  transform: translateX(3px);
  border-color: var(--brand-300);
  box-shadow: var(--shadow-sm);
}

.post-row-main {
  flex: 1;
  min-width: 0;
}

.post-row-title {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 14.5px;
  font-weight: 700;
  color: var(--ink-900);
}

.title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.post-row-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 6px;
  font-size: 12.5px;
  color: var(--ink-500);
}

.post-row-meta i {
  margin-right: 4px;
}

.meta-board {
  color: var(--brand-700);
  font-weight: 600;
}

.meta-board:hover {
  text-decoration: underline;
}

.post-row-stats {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-shrink: 0;
  text-align: center;
}

.post-row-stats span {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
  color: var(--ink-400);
}

.post-row-stats b {
  font-size: 15px;
  color: var(--ink-700);
}

.post-row-stats i {
  font-style: normal;
  font-size: 11px;
}

.post-row-stats .is-liked b {
  color: var(--brand-600);
}

.post-pagination {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

/* ============ 侧栏 ============ */
.forum-side {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hot-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.hot-list li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 8px;
  border-radius: 10px;
  cursor: pointer;
  transition: background-color 0.18s ease;
}

.hot-list li:hover {
  background: var(--brand-50);
}

.hot-rank {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 800;
  color: #fff;
  background: var(--ink-300);
}

.hot-rank.is-1 {
  background: linear-gradient(135deg, #f0a94a, #d9822b);
}

.hot-rank.is-2 {
  background: linear-gradient(135deg, #9fb4c7, #7b8fa3);
}

.hot-rank.is-3 {
  background: linear-gradient(135deg, #cd9a72, #a9764c);
}

.hot-info {
  min-width: 0;
}

.hot-title {
  margin: 0 0 2px;
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--ink-800);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.hot-meta {
  margin: 0;
  font-size: 11.5px;
  color: var(--ink-400);
}

.quick-links {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.quick-links button,
.quick-links a {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 12px;
  border: 1px solid var(--brand-100);
  border-radius: 10px;
  background: linear-gradient(160deg, #ffffff, #f4faf7);
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink-700);
  text-align: left;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.18s ease;
}

.quick-links button:hover,
.quick-links a:hover {
  border-color: var(--brand-300);
  color: var(--brand-700);
  transform: translateX(3px);
}

.quick-links i {
  width: 16px;
  color: var(--brand-600);
}

@media (max-width: 1080px) {
  .forum-main {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 640px) {
  .post-row {
    flex-direction: column;
    align-items: flex-start;
  }

  /* 第 45 批（移动端）：竖排后统计区必须允许收缩，否则整行仍会被撑宽 */
  .post-row-stats {
    width: 100%;
    justify-content: flex-start;
    gap: 22px;
    flex-shrink: 1;
  }

  .post-row-main,
  .post-row-title,
  .title-text {
    width: 100%;
    min-width: 0;
  }

  .post-search {
    width: 150px;
  }
}

/* 第 45 批（移动端）：面板头部的"标题 + 共 N 条 + 搜索框 + 搜索按钮"在 375px 下
   比面板宽 17px（被 overflow:hidden 裁掉），让头部换行、搜索框独占一行。 */
@media (max-width: 640px) {
  .panel-head {
    flex-wrap: wrap;
    row-gap: 8px;
  }

  .panel-head-right {
    width: 100%;
    margin-left: 0;
  }

  .post-search {
    flex: 1;
    width: auto;
    min-width: 0;
  }
}
</style>

