<script setup>
/**
 * 管理后台外壳（第 117 批新增）
 * ============================================================================
 * 为什么要有它：
 *   第 116 批把**入口**分开了（农户 /login，管理员 /admin/login），但管理员登录后
 *   进来的仍是农户那套页面：主站顶栏（首页/识别/百科/历史…）+ 页脚（快速导航/农事工具
 *   /联系我们）+ 一条「管理」下拉。也就是"管理端 = 农户端 + 一个下拉菜单"，
 *   两边的信息在同一个屏幕里抢位置。
 *
 * 现在 `/admin/**` 走这一套独立外壳：
 *   · **左侧固定侧栏**：只放管理功能（数据看板 / 用户管理 / 内容审核 / 新闻管理 / 意见反馈），
 *     底部是「返回用户端」——管理端不再出现农户端的导购式导航；
 *   · **顶部条**：面包屑（管理后台 / 当前页）+ 语言切换 + 身份 + 退出登录（退出直接回
 *     管理员登录页，不回农户登录页）；
 *   · **内容区**：各管理页原样嵌进来（它们的 `.admin-hero` 页头继续用，所以这里不再重复大标题）。
 *
 * 怎么接进 App.vue：路由 meta 标 `adminArea: true`，App.vue 据此**不渲染**主站顶栏与页脚，
 * 并把 RouterView 包进本组件（见 App.vue 的 isAdminArea / .is-admin-area）。
 * 这样做而不是改路由成父子结构：路径、路由名、重定向全部保持不变，
 * 书签、外链与 E2E 用例里的 `/admin/users` 一律照旧。
 */
import { computed, ref, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';
import LanguageSwitcher from '@/components/LanguageSwitcher.vue';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

/**
 * 侧栏导航。文案直接复用 `manage.*`（顶栏「管理」下拉用的就是这几个 key），
 * 免得同一个功能在"下拉里叫一个名、侧栏里叫另一个名"。
 *
 * 第 126 批：每一项带 `capability` —— 侧栏**只显示当前账号真能用的**。
 * 第 128 批：内容那几项再带 `module` —— 内容能力拆成了四个互不干扰的模块，
 * 只勾了「新闻管理」的编辑员不该看到「病害百科维护」。
 * 但这只是体验：直接输网址由路由守卫拦，真正拦住的是后端（403）。
 */
const navItems = [
  // 数据看板：只读、聚合数字（没有用户明细），任何能进后台的人都可看
  { to: '/admin/dashboard', icon: 'fas fa-chart-line', labelKey: 'manage.dashboard',
    capability: authStore.CAP_CONTENT },
  { to: '/admin/users', icon: 'fas fa-users-gear', labelKey: 'manage.users',
    capability: authStore.CAP_USER_ADMIN },
  { to: '/admin/review', icon: 'fas fa-clipboard-check', labelKey: 'manage.review',
    capability: authStore.CAP_CONTENT, module: authStore.MODULE_REVIEW },
  // 第 147 批：论坛管理（与内容审核同一模块：能审帖的人就能管理帖子）
  { to: '/admin/forum', icon: 'fas fa-comments', labelKey: 'manage.forum',
    capability: authStore.CAP_CONTENT,
    modules: [authStore.MODULE_REVIEW, authStore.MODULE_FORUM] },
  // 第 149 批：评论管理（与论坛管理同一模块：评论审核就是内容审核工作）
  { to: '/admin/comments', icon: 'fas fa-comment-dots', labelKey: 'manage.comments',
    capability: authStore.CAP_CONTENT,
    modules: [authStore.MODULE_REVIEW, authStore.MODULE_FORUM] },
  // 第 148 批：操作日志（**仅全权管理员** —— 显示"谁对谁做了什么"，编辑员不该看到）
  { to: '/admin/audit-logs', icon: 'fas fa-clipboard-list', labelKey: 'manage.auditLogs',
    capability: authStore.CAP_USER_ADMIN, fullAdminOnly: true },
  { to: '/admin/news', icon: 'fas fa-newspaper', labelKey: 'manage.news',
    capability: authStore.CAP_CONTENT, module: authStore.MODULE_NEWS },
  // 第 122 批：病害百科维护（原来长在农户端百科页上，现在归这里）
  { to: '/admin/pests', icon: 'fas fa-book-medical', labelKey: 'manage.pests',
    capability: authStore.CAP_CONTENT, module: authStore.MODULE_PESTS },
  { to: '/admin/feedback', icon: 'fas fa-comment-dots', labelKey: 'manage.feedback',
    capability: authStore.CAP_CONTENT, module: authStore.MODULE_FEEDBACK },
  // 第 140 批：版块管理 —— BROADCAST（"对全体发声与系统开关"：公告/预警/敏感词/版块）。
  // 信息编辑员只有内容能力，看不到这一项（后端接口也会 403）。
  { to: '/admin/boards', icon: 'fas fa-table-columns', labelKey: 'manage.boards',
    capability: authStore.CAP_BROADCAST },
];

/**
 * 当前账号看得见的导航项（先按能力、再按内容模块过滤，顺序不变）
 *
 * 第 128 批：`module` 只对内容那几项有意义 —— 用户管理靠 USER_ADMIN，
 * 看板不带 module（任何能进后台的人都该有个落脚页，否则"只勾一块"的编辑员
 * 登录后会落在空白侧栏上）。
 */
const visibleNavItems = computed(() => navItems.filter((item) => {
  if (!authStore.hasCapability(item.capability)) return false;
  if (item.module && !authStore.hasContentModule(item.module)) return false;
  // 第 151 批：多模块项（论坛管理 / 评论管理）—— 任一命中即可见
  if (item.modules && !item.modules.some(m => authStore.hasContentModule(m))) return false;
  // 第 148 批：只给全权管理员看的入口（操作日志）
  if (item.fullAdminOnly && !authStore.isAdmin) return false;
  return true;
}));

/** 当前页名：优先用侧栏里那一条的文案，取不到再退回（不会露出 key 本身） */
const currentLabel = computed(() => {
  const hit = navItems.find((item) => route.path === item.to || route.path.startsWith(`${item.to}/`));
  return hit ? t(hit.labelKey) : t('adminLayout.title');
});

const userInitial = computed(() => (authStore.user?.username || '?').slice(0, 1).toUpperCase());

// 第 126 批：删掉了原来的 `isAdminUser`（身份标签改用下面的 roleLabel）。
// 这个页面里凡是与"能做什么"有关的显示都应当走 capabilities ——
// 留一个"是不是全权管理员"的 computed 只会让下一个人继续拿它当权限判断。

/**
 * 身份标签（第 126 批）
 *
 * 以前只有"管理员 / 普通用户"两种，因为能进后台的只有全权管理员；
 * 现在信息编辑员也能进，标签要如实显示 —— 否则编辑员会以为自己是管理员，
 * 然后困惑于"为什么没有用户管理"。
 */
const roleLabel = computed(() => {
  if (authStore.hasCapability(authStore.CAP_USER_ADMIN)) return t('adminLayout.roleAdmin');
  if (authStore.hasCapability(authStore.CAP_CONTENT)) return t('adminLayout.roleEditor');
  return t('adminLayout.roleUser');
});

// 窄屏抽屉：<1024px 时侧栏收起来，点顶部条的菜单键展开
const drawerOpen = ref(false);
watch(() => route.fullPath, () => { drawerOpen.value = false; });

// ============================================================================
// 侧栏折叠（第 117 批）
// ----------------------------------------------------------------------------
// 为什么需要：侧栏占了 236px，而「用户管理」那张表各列的 min-width 加起来就有
// 1406px —— 1440 这类常见笔记本宽度下表格会被挤到横向滚动（实测：内容区 1122px
// vs 表格 1406px，固定的「操作」列会盖住「注册时间」）。
// 折叠成图标栏（68px）能把 168px 还给内容；1600px 以上折叠后整张表放得下。
// 选择记在 localStorage：管理员的选择不该每次进后台都重置。
// ============================================================================
const COLLAPSE_KEY = 'admin_sidebar_collapsed';
const collapsed = ref(false);

try {
  collapsed.value = localStorage.getItem(COLLAPSE_KEY) === '1';
} catch {
  /* 隐私模式下 localStorage 可能不可用，忽略：默认展开 */
}

const toggleCollapsed = () => {
  collapsed.value = !collapsed.value;
  try {
    localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0');
  } catch {
    /* 存不了就算了，本次会话仍然生效 */
  }
};

const handleLogout = async () => {
  // 管理端退出后回**管理员登录页**（第 117 批给 logout 加了第二参数，
  // 默认仍是农户登录页，主站那边行为不变）
  await authStore.logout(router, '/admin/login');
};
</script>

<template>
  <div class="admin-console">
    <!-- 左侧导航（可折叠成图标栏，见 script 里的说明） -->
    <aside class="admin-sidebar" :class="{ 'is-open': drawerOpen, 'is-collapsed': collapsed }">
      <RouterLink to="/admin/dashboard" class="admin-brand" :title="t('adminLayout.title')">
        <span class="admin-brand-badge"><i class="fas fa-user-shield"></i></span>
        <span class="admin-brand-text">
          <strong>{{ t('adminLayout.title') }}</strong>
          <em>{{ t('adminLayout.subtitle') }}</em>
        </span>
      </RouterLink>

      <nav class="admin-nav">
        <RouterLink
          v-for="item in visibleNavItems"
          :key="item.to"
          :to="item.to"
          class="admin-nav-item"
          :title="collapsed ? t(item.labelKey) : ''"
        >
          <i :class="item.icon"></i>
          <span>{{ t(item.labelKey) }}</span>
        </RouterLink>
      </nav>

      <div class="admin-sidebar-foot">
        <RouterLink to="/" class="admin-exit" :title="t('adminLayout.backToSite')">
          <i class="fas fa-arrow-up-right-from-square"></i>
          <span>{{ t('adminLayout.backToSite') }}</span>
        </RouterLink>
        <p class="admin-sidebar-hint">{{ t('adminLayout.sidebarHint') }}</p>
      </div>
    </aside>

    <!-- 窄屏：抽屉遮罩 -->
    <div v-if="drawerOpen" class="admin-drawer-mask" @click="drawerOpen = false"></div>

    <div class="admin-body">
      <header class="admin-topbar">
        <button
          type="button"
          class="admin-burger"
          :aria-label="t('adminLayout.menu')"
          :title="t('adminLayout.menu')"
          @click="drawerOpen = !drawerOpen"
        >
          <i class="fas fa-bars"></i>
        </button>

        <!-- 折叠/展开侧栏（窄屏用抽屉，这个键只在 ≥1025px 出现） -->
        <button
          type="button"
          class="admin-collapse"
          :aria-label="collapsed ? t('adminLayout.expandSidebar') : t('adminLayout.collapseSidebar')"
          :title="collapsed ? t('adminLayout.expandSidebar') : t('adminLayout.collapseSidebar')"
          @click="toggleCollapsed"
        >
          <i :class="collapsed ? 'fas fa-angles-right' : 'fas fa-angles-left'"></i>
        </button>

        <nav class="admin-crumb" :aria-label="t('adminLayout.title')">
          <RouterLink to="/admin/dashboard" class="admin-crumb-root">{{ t('adminLayout.title') }}</RouterLink>
          <i class="fas fa-angle-right" aria-hidden="true"></i>
          <span class="admin-crumb-current">{{ currentLabel }}</span>
        </nav>

        <div class="admin-topbar-actions">
          <LanguageSwitcher />

          <span class="admin-who" :title="authStore.user?.username || ''">
            <img
              v-if="authStore.user?.avatar"
              :src="authStore.user.avatar"
              :alt="authStore.user?.username || ''"
              class="admin-who-avatar-img"
            >
            <span v-else class="admin-who-avatar">{{ userInitial }}</span>
            <span class="admin-who-text">
              <strong>{{ authStore.user?.username }}</strong>
              <em>{{ roleLabel }}</em>
            </span>
          </span>

          <button type="button" class="admin-logout" :title="t('app.logout')" @click="handleLogout">
            <i class="fas fa-right-from-bracket"></i>
            <span>{{ t('app.logout') }}</span>
          </button>
        </div>
      </header>

      <main class="admin-content">
        <slot />
      </main>
    </div>
  </div>
</template>

<style scoped>
.admin-console {
  display: flex;
  align-items: stretch;
  width: 100%;
  min-height: 100vh;
  background: var(--ink-50, #f8fbf9);
}

/* ---------- 左侧导航 ---------- */
.admin-sidebar {
  flex: 0 0 236px;
  width: 236px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 20px 16px 18px;
  color: rgba(255, 255, 255, 0.86);
  background: linear-gradient(180deg, #0d3f2c 0%, #123a29 60%, #0e3424 100%);
  position: sticky;
  top: 0;
  height: 100vh;
  box-sizing: border-box;
  z-index: 40;
}

.admin-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
  text-decoration: none;
}

.admin-brand-badge {
  flex: 0 0 auto;
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.14);
  color: #b7e6cb;
  font-size: 15px;
}

.admin-brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.admin-brand-text strong {
  font-size: 15px;
  font-weight: 800;
  color: #fff;
  letter-spacing: 0.3px;
}

.admin-brand-text em {
  font-style: normal;
  font-size: 11.5px;
  color: rgba(255, 255, 255, 0.55);
  letter-spacing: 0.4px;
}

.admin-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.admin-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  color: rgba(255, 255, 255, 0.78);
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  transition: background 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.admin-nav-item i {
  width: 18px;
  text-align: center;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.6);
  transition: color 0.2s ease;
}

.admin-nav-item:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.admin-nav-item.router-link-active {
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
  box-shadow: inset 3px 0 0 #7ddca8;
}

.admin-nav-item.router-link-active i {
  color: #b7e6cb;
}

.admin-sidebar-foot {
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  padding-top: 14px;
}

.admin-exit {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.85);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.admin-exit:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.34);
  color: #fff;
}

.admin-sidebar-hint {
  margin: 10px 2px 0;
  font-size: 11.5px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.45);
}

/* ---------- 右半：顶部条 + 内容 ---------- */
.admin-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.admin-topbar {
  position: sticky;
  top: 0;
  z-index: 30;
  height: 62px;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 0 22px;
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border, #e2ebe5);
}

.admin-burger {
  display: none;
  width: 36px;
  height: 36px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border, #e2ebe5);
  border-radius: 10px;
  background: #fff;
  color: var(--ink-600, #566b60);
  font-size: 15px;
  cursor: pointer;
}

.admin-collapse {
  display: inline-flex;
  width: 32px;
  height: 32px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border, #e2ebe5);
  border-radius: 9px;
  background: #fff;
  color: var(--ink-500, #78897f);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.admin-collapse:hover {
  border-color: var(--brand-300, #93cdad);
  background: var(--brand-50, #f1f9f4);
  color: var(--brand-700, #1f6343);
}

.admin-crumb {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 13.5px;
  color: var(--ink-400, #9dada5);
}

.admin-crumb i {
  font-size: 10px;
}

.admin-crumb-root {
  color: var(--ink-500, #78897f);
  text-decoration: none;
}

.admin-crumb-root:hover {
  color: var(--brand-700, #1f6343);
}

.admin-crumb-current {
  font-weight: 700;
  color: var(--ink-800, #24352c);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.admin-topbar-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.admin-who {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 5px 12px 5px 6px;
  border-radius: var(--radius-pill, 999px);
  background: var(--ink-50, #f8fbf9);
  border: 1px solid var(--border, #e2ebe5);
}

.admin-who-avatar,
.admin-who-avatar-img {
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  border-radius: 50%;
  display: grid;
  place-items: center;
  object-fit: cover;
  background: var(--gradient-brand, linear-gradient(135deg, #3d9a68, #1f6343));
  color: #fff;
  font-size: 13px;
  font-weight: 700;
}

.admin-who-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
  min-width: 0;
}

.admin-who-text strong {
  font-size: 13px;
  font-weight: 700;
  color: var(--ink-800, #24352c);
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin-who-text em {
  font-style: normal;
  font-size: 11px;
  color: var(--ink-400, #9dada5);
}

.admin-logout {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 14px;
  border: 1px solid var(--border, #e2ebe5);
  border-radius: var(--radius-pill, 999px);
  background: #fff;
  color: var(--ink-600, #566b60);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.admin-logout:hover {
  border-color: #f0c9c9;
  background: #fdf5f5;
  color: #c0392b;
}

.admin-content {
  flex: 1;
  min-width: 0;
  padding: 18px 18px 36px;
}

/* 抽屉遮罩（只在窄屏出现） */
.admin-drawer-mask {
  display: none;
}

/* ---------- 折叠态：只留图标（把宽度还给表格） ---------- */
.admin-sidebar.is-collapsed {
  flex-basis: 68px;
  width: 68px;
  padding-left: 10px;
  padding-right: 10px;
  align-items: center;
}

.admin-sidebar.is-collapsed .admin-brand {
  justify-content: center;
  padding-left: 0;
  padding-right: 0;
}

.admin-sidebar.is-collapsed .admin-brand-text,
.admin-sidebar.is-collapsed .admin-nav-item span,
.admin-sidebar.is-collapsed .admin-exit span,
.admin-sidebar.is-collapsed .admin-sidebar-hint {
  display: none;
}

.admin-sidebar.is-collapsed .admin-nav {
  width: 100%;
}

.admin-sidebar.is-collapsed .admin-nav-item {
  justify-content: center;
  padding: 11px 0;
}

.admin-sidebar.is-collapsed .admin-nav-item i {
  width: auto;
  font-size: 16px;
}

.admin-sidebar.is-collapsed .admin-exit {
  justify-content: center;
  padding: 9px 0;
}

.admin-sidebar.is-collapsed .admin-sidebar-foot {
  width: 100%;
}

/* ---------- 窄屏：侧栏收成抽屉 ---------- */
@media (max-width: 1024px) {
  .admin-sidebar {
    position: fixed;
    top: 0;
    left: 0;
    height: 100vh;
    transform: translateX(-100%);
    transition: transform 0.25s ease;
    box-shadow: 0 18px 40px rgba(9, 40, 27, 0.3);
  }

  .admin-sidebar.is-open {
    transform: translateX(0);
  }

  /* 窄屏一律用抽屉 + 完整侧栏：折叠键在这里没有意义 */
  .admin-sidebar.is-collapsed {
    flex-basis: 236px;
    width: 236px;
    padding-left: 16px;
    padding-right: 16px;
    align-items: stretch;
  }

  .admin-sidebar.is-collapsed .admin-brand {
    justify-content: flex-start;
    padding-left: 8px;
    padding-right: 8px;
  }

  .admin-sidebar.is-collapsed .admin-brand-text,
  .admin-sidebar.is-collapsed .admin-nav-item span,
  .admin-sidebar.is-collapsed .admin-exit span,
  .admin-sidebar.is-collapsed .admin-sidebar-hint {
    display: initial;
  }

  .admin-sidebar.is-collapsed .admin-brand-text {
    display: flex;
  }

  .admin-sidebar.is-collapsed .admin-nav-item {
    justify-content: flex-start;
    padding: 10px 12px;
  }

  .admin-sidebar.is-collapsed .admin-nav-item i {
    width: 18px;
  }

  .admin-sidebar.is-collapsed .admin-exit {
    justify-content: flex-start;
    padding: 9px 12px;
  }

  .admin-collapse {
    display: none;
  }

  .admin-drawer-mask {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 35;
    background: rgba(12, 32, 23, 0.42);
  }

  .admin-burger {
    display: inline-flex;
  }

  .admin-content {
    padding: 14px 12px 30px;
  }
}

@media (max-width: 720px) {
  .admin-who-text {
    display: none;
  }

  .admin-logout span {
    display: none;
  }

  .admin-logout {
    padding: 8px 11px;
  }
}
</style>
