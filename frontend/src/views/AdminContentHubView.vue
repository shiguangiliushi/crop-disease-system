<script setup>
/**
 * 管理端「内容管理」—— 一个页面 + 三个页签（第 183 批）
 * ============================================================================
 *
 * ## 为什么合并
 *
 * 在此之前侧栏里有**三项**指的是同一件事：`/admin/review`（内容审核）、
 * `/admin/forum`（论坛管理）、`/admin/comments`（评论管理）。它们都由
 * 「内容审核(review)」或「论坛交流(forum)」这两个模块覆盖（见 `capabilities.py`），
 * 三页之间互相跳来跳去，用户要在三个入口之间记"删帖去哪个、删评论去哪个"。
 * 现在合成一项「内容管理」，页内用页签切换。
 *
 * ## 三个页签与各自的权限（**页签按模块显示，看不到的不画**）
 *
 * | 页签 | 谁能看 | 依据 |
 * |---|---|---|
 * | 帖子 | `review` **或** `forum` | 后端 `is_moderator()`（views_forum） |
 * | 评论 | `review` **或** `forum` | 后端 `_reject_non_moderator`（views_comments_admin） |
 * | 举报 | `review` **或** `forum`（第 189 批放开） | 后端 `views_report._can_handle_reports()` |
 *
 * ⚠️ 举报在**第 189 批之前**是"仅全权管理员"（第 124 批的决策）。改的原因（用户反馈）：
 * 编辑员在这一页里能管帖子与评论（能驳回/下架），却**完全看不到举报页签** ——
 * 于是"已经有人在举报这件事"他永远不知道，只能自己去翻帖子发现问题。
 * 现在把举报当**线索入口**给他，但**只放开一半**（与后端同一口径）：
 *   · 能看别人的举报、能处置（handled/rejected + 备注）→ `review`/`forum` 模块；
 *   · **看不到举报人是谁**（回包里 `reporter.username` 为 null、`target_user_id` 不下发，
 *     另有 `reporter_hidden: true` 标记）—— 隐私；
 *   · 「同时隐藏内容」这个**不可逆**动作仍只给全权管理员（按项目一贯口径，见
 *     `capabilities.py`：不可逆动作只给全权管理员），编辑员勾了也不生效、且会明确告知。
 *
 * 一个相关模块都没有 → 侧栏里连「内容管理」都不显示（见 AdminLayout.vue 的 navItems）；
 * 手输网址则由路由守卫拦（`meta.modules`）。
 *
 * ## 实现方式
 *
 * 三个页签各自是一个子组件（`components/admin/content/{PostPanel,CommentPanel,ReportPanel}.vue`），
 * 内容是**原来那三页原样搬过来的**（连注释一起），本文件只负责：
 * 页签、`?tab=` 同步、按权限决定页签可见性、以及只挂载当前页签（v-if）。
 * 业务逻辑一行都不在这里 —— 免得合并时把两处的行为改成第三处的行为。
 *
 * ## 只挂载当前页签（v-if）的三个理由
 *
 * 1. 三个页签都自带 `onMounted` 加载：全挂载等于一进页面打 6+ 个请求；
 * 2. 编辑员不该去请求**敏感词**（那是 BROADCAST 的东西，他打开必然 403）——
 *    举报从第 189 批起编辑员**有权**看，不再是"点了会 403"的页签；
 * 3. 帖子页签与评论页签的分页/筛选都写进 URL 且**同名**（page / page_size / search），
 *    同时挂载会互相覆盖 —— 只挂一个，再加上切页签时清参数，就不会串味。
 *
 * ## `?tab=` 的口径
 *
 * * `/admin/content?tab=posts|comments|reports` —— 主入口，可直接分享这个地址；
 *   `tab` 缺失或不可见时落到他有权限的第一个页签，并**把地址栏修正过来**；
 * * 旧地址 `/admin/review`、`/admin/forum`、`/admin/comments` 全部重定向到
 *   对应页签（见 router/index.js），书签与外链不失效，且**保留原有查询参数**
 *   （`/admin/forum?search=xx` 这类老链接照样能用）；
 * * 切页签时清掉上一个页签的筛选参数：两个页签的同名参数（page/search）串味比"少一次筛选"更难解释。
 */
import { computed, nextTick, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from '@/i18n';
import { useAuthStore } from '@/stores/auth';
import PostPanel from '@/components/admin/content/PostPanel.vue';
import CommentPanel from '@/components/admin/content/CommentPanel.vue';
import ReportPanel from '@/components/admin/content/ReportPanel.vue';

defineOptions({ name: 'AdminContentHubView' });

const TAB_POSTS = 'posts';
const TAB_COMMENTS = 'comments';
const TAB_REPORTS = 'reports';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

/**
 * 帖子 / 评论页签：`review` 或 `forum` 模块
 *
 * 与后端 `is_moderator()` 同一口径；`is_staff` / `is_superuser` 兜底是为了
 * "组信息没下发"的极端情况（与 AdminForumView 原来的写法一致，第 145 批的说明）。
 */
const canModeratePosts = computed(() => Boolean(
  authStore.hasContentModule?.('review')
  || authStore.hasContentModule?.('forum')
  || authStore.user?.is_staff
  || authStore.user?.is_superuser,
));

/** 举报页签：**有 review/forum 模块的人**（第 189 批放开）+ 全权管理员 */
const canHandleReports = computed(() => Boolean(
  canModeratePosts.value || authStore.isAdmin,
));

const tabs = computed(() => [
  {
    name: TAB_POSTS,
    labelKey: 'contentHub.tabPosts',
    icon: 'fas fa-clipboard-check',
    show: canModeratePosts.value,
    panel: PostPanel,
  },
  {
    name: TAB_COMMENTS,
    labelKey: 'contentHub.tabComments',
    icon: 'fas fa-comment-dots',
    show: canModeratePosts.value,
    panel: CommentPanel,
  },
  {
    name: TAB_REPORTS,
    labelKey: 'contentHub.tabReports',
    icon: 'fas fa-flag',
    show: canHandleReports.value,
    panel: ReportPanel,
  },
].filter((tab) => tab.show));

const firstTab = computed(() => tabs.value[0]?.name || '');
const validTab = (name) => tabs.value.some((tab) => tab.name === name);
/** URL 里的 tab（同一个参数出现多次时取第一个） */
const requestedTab = () => (Array.isArray(route.query.tab) ? route.query.tab[0] : route.query.tab);

const activeTab = ref('');

/** 当前页签对应的子组件（只挂载它，见文件头第 3 点） */
const activePanel = computed(
  () => tabs.value.find((tab) => tab.name === activeTab.value)?.panel || null,
);

// ---------------------------------------------------------------------------
// ① URL → 页签
// ---------------------------------------------------------------------------
watch(
  [() => route.query.tab, tabs],
  () => {
    const requested = requestedTab();
    const next = validTab(requested) ? requested : firstTab.value;
    if (activeTab.value !== next) activeTab.value = next;
    // 请求的页签这个人看不到（或不存在）：把地址栏修正成真正显示的那个，
    // 否则刷新/分享会一直带着一个无效的 tab。
    if (requested && requested !== next && next) {
      router.replace({ query: { ...router.currentRoute.value.query, tab: next } });
    }
  },
  { immediate: true },
);

// ---------------------------------------------------------------------------
// ② 页签 → URL（顺带清掉上一个页签的筛选参数）
// ---------------------------------------------------------------------------
watch(activeTab, async (name) => {
  if (!name) return;
  // 等一个 tick：上一个页签的 useQueryState 可能刚好还有一个"把筛选写进 URL"的
  // 待执行回调（它是 nextTick 里 push 的），让它先落地，我们再整体清干净。
  await nextTick();
  const requested = requestedTab();
  const hasOtherParams = Object.keys(route.query).some((key) => key !== 'tab');
  if (requested === name && !hasOtherParams) return;
  router.replace({ query: { ...router.currentRoute.value.query, tab: name } });
});
</script>

<template>
  <div class="content-hub">
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-layer-group"></i></span>
        <div>
          <h1>{{ t('manage.content') }}</h1>
          <p>{{ t('contentHub.subtitle') }}</p>
        </div>
      </div>
    </header>

    <!-- 一个相关模块都没有（理论上进不来：侧栏不显示 + 路由守卫拦）——
         仍然给一句人话，而不是白屏 -->
    <el-empty v-if="!tabs.length" :description="t('contentHub.noAccess')" />

    <el-tabs v-else v-model="activeTab" class="content-hub-tabs">
      <el-tab-pane v-for="tab in tabs" :key="tab.name" :name="tab.name">
        <template #label>
          <span class="hub-tab"><i :class="tab.icon"></i> {{ t(tab.labelKey) }}</span>
        </template>
        <!-- v-if：只挂载当前页签的组件（见文件头"只挂载当前页签"的三条理由） -->
        <component :is="activePanel" v-if="activeTab === tab.name" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.content-hub {
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
}

.hub-tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-weight: 600;
}

.hub-tab i {
  font-size: 13px;
}

/* 页签栏与页签内容之间的留白（Element Plus 默认几乎贴在一起） */
.content-hub-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.content-hub-tabs :deep(.el-tabs__item) {
  font-size: 14px;
}
</style>
