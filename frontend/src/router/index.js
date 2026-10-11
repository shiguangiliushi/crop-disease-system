import { createRouter, createWebHistory } from 'vue-router'
import { watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
// 第 75 批修复：守卫里调用 t('msg.noPermission')，但本文件从未导入过 t ——
// 非管理员访问 /admin/* 时会抛 `ReferenceError: t is not defined`，
// 提示弹不出来、导航也卡在守卫里（而不是像预期那样被挡回上一页）。
import { t, locale } from '@/i18n'
// 第 97 批：「有未保存的修改」时的离开确认。判定函数由组件注册（见 useUnsavedChanges），
// 这里只负责在导航前问一句 —— 因为守卫是全局的，而"脏不脏"是组件内的状态。
import { runLeaveGuards } from '@/composables/useUnsavedChanges'

// 使用动态导入实现路由懒加载
const HomeView = () => import('@/views/HomeView.vue')
const DetectView = () => import('@/views/DetectView.vue')
const HistoryView = () => import('@/views/HistoryView.vue')
const EditPostView = () => import('@/views/EditPostView.vue')
const PestEncyclopediaView = () => import('@/views/PestEncyclopediaView.vue')
const PestDetailView = () => import('@/views/PestDetailView.vue')
const LoginView = () => import('@/views/LoginView.vue')
// 第 116 批：管理端登录独立成页（`/admin/login`），与农户侧的 /login 分开
const AdminLoginView = () => import('@/views/AdminLoginView.vue')
const RegisterView = () => import('@/views/RegisterView.vue')
const PreventionView = () => import('@/views/PreventionView.vue')
const AboutView = () => import('@/views/AboutView.vue')
// 第 26 批：用户协议 / 隐私政策 / 帮助中心 / 意见反馈
const TermsView = () => import('@/views/TermsView.vue')
const PrivacyView = () => import('@/views/PrivacyView.vue')
const HelpView = () => import('@/views/HelpView.vue')
const FeedbackCenterView = () => import('@/views/FeedbackCenterView.vue')
const NewsView = () => import('@/views/NewsView.vue')
const NewsDetailView = () => import('@/views/NewsDetailView.vue')
const ForumView = () => import('@/views/ForumView.vue')
const PostDetailView = () => import('@/views/PostDetailView.vue')
// 第 22 批：DetectionHistoryView.vue 已随「识别记录管理」合并进 HistoryView 而停用，
// 路由 /admin/detection-history 改为重定向到 /history。
// 第 109 批：那份旧文件所在的 `src/_deprecated/` 已删除（建立版本控制之后），
// 需要参考旧实现时用 `git show 1f54f00:frontend/src/_deprecated/views/DetectionHistoryView.vue`。
const NewsManagementView = () => import('@/views/NewsManagementView.vue')
// 第 27 批：管理端意见反馈管理
const AdminFeedbackView = () => import('@/views/AdminFeedbackView.vue')
const NotFoundView = () => import('@/views/NotFoundView.vue')
const ForumBoardView = () => import('@/views/ForumBoardView.vue')
const ForumFavoritesView = () => import('@/views/ForumFavoritesView.vue')
const UserProfileView = () => import('@/views/UserProfileView.vue')
const NewPostView = () => import('@/views/NewPostView.vue')

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    // 公共路由
    {
      path: '/',
      name: 'home',
      component: HomeView,
      meta: { title: '首页' }
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { title: '登录', bareLayout: true }
    },
    // 第 116 批：管理员登录**独立成页**。
    // 改前 /login 一个页面既当农户第一屏、又写着「客服工作台/坐席专用入口」，
    // 两边都不像；现在农户走 /login，管理员走这里（文案、左侧一栏、登录后的落点都不同）。
    {
      path: '/admin/login',
      name: 'admin-login',
      component: AdminLoginView,
      meta: { title: '管理员登录', bareLayout: true }
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
      meta: { title: '注册', bareLayout: true }
    },
    // 第 35 批：忘记密码自助流程（此前只能"联系管理员重置"）
    {
      path: '/forgot-password',
      name: 'forgot-password',
      component: () => import('@/views/ForgotPasswordView.vue'),
      meta: { title: '找回密码', bareLayout: true }
    },
    {
      path: '/reset-password',
      name: 'reset-password',
      component: () => import('@/views/ResetPasswordView.vue'),
      meta: { title: '重置密码', bareLayout: true }
    },
    {
      path: '/about',
      name: 'about',
      component: AboutView,
      meta: { title: '关于我们' }
    },

    // 第 26 批：页脚原本是四个 href="#" 死链，这里补上真实页面
    {
      path: '/terms',
      name: 'terms',
      component: TermsView,
      meta: { title: '用户协议' }
    },
    {
      path: '/privacy',
      name: 'privacy',
      component: PrivacyView,
      meta: { title: '隐私政策' }
    },
    {
      path: '/help',
      name: 'help',
      component: HelpView,
      meta: { title: '帮助中心' }
    },
    {
      path: '/feedback',
      name: 'feedback',
      component: FeedbackCenterView,
      meta: {
        requiresAuth: true,
        title: '意见反馈'
      }
    },
    // 第 37 批：通知中心（帖子互动通知 + 系统公告）
    {
      path: '/notifications',
      name: 'notifications',
      component: () => import('@/views/NotificationsView.vue'),
      meta: {
        requiresAuth: true,
        title: '通知中心'
      }
    },
    // 第 38 批：内容审核（待审核帖子 + 敏感词词库，仅管理员）
    {
      path: '/admin/review',
      name: 'content-review',
      component: () => import('@/views/ContentReviewView.vue'),
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        capability: 'CONTENT',   // 第 126 批：内容生产
        module: 'review',    // 第 128 批：内容侧按模块隔离（内容审核）
        // 第 117 批：`adminArea` = 走管理后台外壳（AdminLayout：左侧栏 + 顶部条），
        // 不显示农户端的顶栏与页脚。App.vue 读这个标记（isAdminArea）。
        adminArea: true,
        title: '内容审核',
        breadcrumb: ['管理', '内容审核']
      }
    },
    // 第 39 批：管理员数据看板
    {
      path: '/admin/dashboard',
      name: 'admin-dashboard',
      component: () => import('@/views/AdminDashboardView.vue'),
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        capability: 'CONTENT',   // 第 126 批：看板只读，信息编辑员可看（用户明细由后端裁剪）
        adminArea: true,   // 第 117 批：管理后台外壳
        title: '数据看板',
        breadcrumb: ['管理', '数据看板']
      }
    },
    {
      // 第 76 批：管理端「用户管理」（此前管理板块完全没有用户入口，
      // 想看用户列表/专家身份只能进 Django 自带的 /admin/）
      path: '/admin/users',
      name: 'admin-users',
      component: () => import('@/views/AdminUsersView.vue'),
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        capability: 'USER_ADMIN',   // 第 126 批：用户管理只给全权管理员
        adminArea: true,   // 第 117 批：管理后台外壳
        title: '用户管理',
        breadcrumb: ['管理', '用户管理']
      }
    },
    // 第 42 批：私信
    {
      path: '/messages',
      name: 'messages',
      component: () => import('@/views/MessagesView.vue'),
      meta: {
        requiresAuth: true,
        title: '私信'
      }
    },
    // 第 46 批：病害预警
    {
      path: '/alerts',
      name: 'alerts',
      component: () => import('@/views/AlertsView.vue'),
      meta: {
        requiresAuth: true,
        title: '病害预警',
        breadcrumb: ['病害预警']
      }
    },
    // 第 47 批：种植日历
    {
      path: '/calendar',
      name: 'calendar',
      component: () => import('@/views/CalendarView.vue'),
      meta: {
        requiresAuth: true,
        title: '种植日历',
        breadcrumb: ['种植日历']
      }
    },
    // 第 49 批：专家咨询
    {
      path: '/consult',
      name: 'consult',
      component: () => import('@/views/ConsultView.vue'),
      meta: {
        requiresAuth: true,
        title: '专家咨询',
        breadcrumb: ['专家咨询']
      }
    },

    // 需要登录的路由
    {
      path: '/detect',
      name: 'detect',
      component: DetectView,
      meta: {
        requiresAuth: true,
        title: '病害识别',
        breadcrumb: ['识别']
      }
    },
    {
      path: '/history',
      name: 'history',
      component: HistoryView,
      meta: {
        requiresAuth: true,
        title: '历史记录',
        breadcrumb: ['历史']
      }
    },

    // 病害百科相关路由
    {
      path: '/pests',
      name: 'pests',
      component: PestEncyclopediaView,
      meta: {
        requiresAuth: true,
        title: '病害百科',
        breadcrumb: ['病害百科']
      }
    },
    {
      path: '/pests/:english_identifier',
      name: 'PestDetail',
      component: PestDetailView,
      meta: {
        requiresAuth: true,
        title: '病害详情',
        breadcrumb: ['病害百科', '详情']
      },
      props: true
    },
    {
      path: '/preventions/:id',
      name: 'preventions',
      component: PreventionView,
      props: true,
      meta: {
        requiresAuth: true,
        title: '防治方案',
        breadcrumb: ['防治方案']
      }
    },

    // 新闻相关路由
    {
      path: '/news',
      name: 'news',
      component: NewsView,
      meta: {
        requiresAuth: true,
        title: '行业动态',
        breadcrumb: ['新闻']
      }
    },
    {
      // 第 121 批：这两条是**历史深链**（"打开行业动态页并把新增/编辑弹窗打开"）。
      // 它们以前直接渲染 `NewsView` —— 也就是**农户端外观**的页面 + 一个弹窗，
      // 而这两条路由都要管理员权限，等于让管理员在管理动作上看到农户那张脸。
      // 现在改成**重定向进管理后台的新闻管理页**（那一页本来就有自己的新增/编辑弹窗，
      // 第 33 批做的），由它按 ?action= 打开对应弹窗。
      // 保留路由名：`docTitle` 与任何 `{ name: 'news-create' }` 的老跳转都还认。
      path: '/news/create',
      name: 'news-create',
      redirect: () => ({ name: 'news-management', query: { action: 'create' } }),
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        title: '添加新闻'
      }
    },
    {
      path: '/news/:id/edit',
      name: 'news-edit',
      redirect: (to) => ({ name: 'news-management', query: { action: 'edit', id: to.params.id } }),
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        title: '编辑新闻'
      }
    },
    {
      path: '/news/:id',
      name: 'news-detail',
      component: NewsDetailView,
      props: true,
      meta: {
        requiresAuth: true,
        title: '新闻详情',
        breadcrumb: ['新闻', '详情']
      }
    },

    // 论坛相关路由
    {
      path: '/forum',
      name: 'forum',
      component: ForumView,
      meta: {
        requiresAuth: true,
        title: '论坛交流',
        breadcrumb: ['论坛']
      }
    },
    {
      path: '/forum/board/:id',
      name: 'forum-board',
      component: ForumBoardView,
      props: true,
      meta: {
        requiresAuth: true,
        title: '版块详情',
        breadcrumb: ['论坛', '版块']
      }
    },
    {
      // 第 24 批新增：我的收藏（放在论坛各动态路由之前，避免路径被其它规则先匹配）
      path: '/forum/favorites',
      name: 'forum-favorites',
      component: ForumFavoritesView,
      meta: {
        requiresAuth: true,
        title: '我的收藏',
        breadcrumb: ['论坛', '我的收藏']
      }
    },
    {
      // 第 166 批：「我的草稿」—— 编辑页每 30 秒会把草稿自动存到**服务端**
      // （is_draft → status='draft'），但此前前端**没有任何入口**能看到它们：
      // 农户写到一半关掉页面，那条半成品就永远躺在库里（评审意见点名）。
      path: '/forum/drafts',
      name: 'my-drafts',
      component: () => import('@/views/MyDraftsView.vue'),
      meta: {
        requiresAuth: true,
        title: '我的草稿',
        breadcrumb: ['论坛', '我的草稿']
      }
    },
    {
      path: '/forum/post/new',
      name: 'new-post',
      component: NewPostView,
      meta: {
        requiresAuth: true,
        title: '发表新帖',
        breadcrumb: ['论坛', '发帖']
      }
    },
    {
      path: '/forum/post/:id',
      name: 'post-detail',
      component: PostDetailView,
      props: true,
      meta: {
        requiresAuth: true,
        title: '帖子详情',
        breadcrumb: ['论坛', '帖子']
      }
    },
    {
      path: '/forum/post/:id/edit',
      name: 'edit-post',
      component: EditPostView,
      props: true,
      meta: {
        requiresAuth: true,
        title: '编辑帖子',
        breadcrumb: ['论坛', '编辑']
      }
    },

    // 用户相关路由
    {
      path: '/user/profile/:id',
      name: 'user-profile',
      component: UserProfileView,
      props: true,
      meta: {
        requiresAuth: true,
        title: '用户资料',
        breadcrumb: ['用户']
      }
    },

    // 管理后台路由
    // 第 22 批：「识别记录管理」已与「历史记录」合并为同一个页面（/history）。
    // 管理员在该页用「查看全部用户」开关切换范围，能力（全部用户 / 按用户名搜索 /
    // 批量删除）都已并入。这里保留旧路径做重定向，避免书签/外链 404。
    {
      path: '/admin/detection-history',
      name: 'detection-history',
      redirect: { name: 'history' },
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        title: '识别记录管理',
        breadcrumb: ['管理', '识别记录']
      }
    },
    {
      path: '/admin/news',
      name: 'news-management',
      component: NewsManagementView,
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        capability: 'CONTENT',   // 第 126 批：内容生产
        module: 'news',      // 第 128 批：新闻管理模块
        adminArea: true,   // 第 117 批：管理后台外壳
        title: '新闻管理',
        breadcrumb: ['管理', '新闻管理']
      }
    },
    {
      // 第 122 批：病害百科维护。此前它的维护入口长在**农户端**的百科页上
      // （顶部「管理员模式」工具条 + 卡片上的编辑/删除），现在与新闻/用户/反馈一样
      // 归进管理后台侧栏；农户端 `/pests` 因此变回纯阅读页。
      path: '/admin/pests',
      name: 'admin-pests',
      component: () => import('@/views/AdminPestsView.vue'),
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        capability: 'CONTENT',   // 第 126 批：内容生产
        module: 'pests',     // 第 128 批：病害百科模块
        adminArea: true,
        title: '病害百科维护'
      }
    },
    {
      // 第 157 批：管理端「系统健康」
      // 把 manage.py check_env 的检查搬到界面上（依赖/迁移/模型文件/目录可写/
      // 注销到期任务/备份新鲜度/生产开关），外加数据量概览。**仅全权管理员**：
      // 它会暴露服务器路径与部署细节。
      path: '/admin/health',
      name: 'admin-health',
      component: () => import('@/views/AdminHealthView.vue'),
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        fullAdminOnly: true,   // 与操作日志同档
        adminArea: true,
        title: '系统健康',
        breadcrumb: ['管理', '系统健康']
      }
    },

    {
      // 第 149 批：管理端「评论管理」
      // 帖子有「论坛管理」页，评论却一直没有控制台入口 —— 一波广告刷在十几条帖子的
      // 评论区里，只能一条条帖子点进去删。农户端的评论列表还挂在帖子下，没法跨帖子看。
      path: '/admin/comments',
      name: 'admin-comments',
      component: () => import('@/views/AdminCommentsView.vue'),
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        capability: 'CONTENT',
        // 第 151 批：「内容审核」或「论坛交流」任一即可（review 宽口径，forum 细口径）
        modules: ['review', 'forum'],
        adminArea: true,
        title: '评论管理',
        breadcrumb: ['管理', '评论管理']
      }
    },

    {
      // 第 148 批：管理端「操作日志」
      // 第 146 批把管理动作落进了 AdminAuditLog 表并给了只读接口，但只能在 Django admin 里看。
      // 这一页把它接进控制台：按动作/操作人/时间/关键字筛选。**仅全权管理员**。
      path: '/admin/audit-logs',
      name: 'admin-audit-logs',
      component: () => import('@/views/AdminAuditLogView.vue'),
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        fullAdminOnly: true,   // 第 148 批：与后端 is_full_admin 同一档
        adminArea: true,
        title: '操作日志',
        breadcrumb: ['管理', '操作日志']
      }
    },

    {
      // 第 147 批：管理端「论坛管理」
      // 在此之前控制台只能管理**待审核**的帖子（内容审核页）：已发布的帖子里有广告、
      // 有吵架、也有该置顶加精的好帖，但控制台看不到它们 —— 只能回农户端论坛翻。
      path: '/admin/forum',
      name: 'admin-forum',
      component: () => import('@/views/AdminForumView.vue'),
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        // 与内容审核同一口径：能审帖的人（review 模块）就能进来管理帖子
        capability: 'CONTENT',
        // 第 151 批：「内容审核」或「论坛交流」任一即可
        modules: ['review', 'forum'],
        adminArea: true,   // 第 117 批：管理后台外壳
        title: '论坛管理',
        breadcrumb: ['管理', '论坛管理']
      }
    },

    {
      // 第 140 批：管理端「版块管理」
      // 补的是一个空档：后端 `boards/<id>/set_status/`（启停）与 `boards/update_order/`
      // （排序）接口早就有，但控制台没有任何入口 —— 版块启停与排序只能进 Django admin。
      path: '/admin/boards',
      name: 'admin-boards',
      component: () => import('@/views/AdminBoardsView.vue'),
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        // 第 140 批：BROADCAST —— 版块与公告/预警/敏感词同属"对全体发声与系统开关"，
        // 信息编辑员（只有内容能力）进不来，后端接口也是 403。
        capability: 'BROADCAST',
        adminArea: true,   // 第 117 批：管理后台外壳
        title: '版块管理',
        breadcrumb: ['管理', '版块管理']
      }
    },

    {
      // 第 27 批：管理端「意见反馈管理」（管理板块此前没有任何反馈入口）
      path: '/admin/feedback',
      name: 'admin-feedback',
      component: AdminFeedbackView,
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        capability: 'CONTENT',   // 第 126 批：内容生产
        module: 'feedback',  // 第 128 批：意见反馈模块
        adminArea: true,   // 第 117 批：管理后台外壳
        title: '意见反馈管理',
        breadcrumb: ['管理', '意见反馈']
      }
    },

    // 404 页面
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: NotFoundView,
      meta: {
        title: '页面未找到',
        breadcrumb: ['404']
      }
    }
  ]
})

// 全局前置守卫
/**
 * 标签页标题（第 77 批）
 * ------------------------------------------------------------------
 * 原来这里把中文系统名和 `meta.title`（也是中文）直接拼进 document.title，
 * 英文界面下浏览器标签页、历史记录里全是中文。现在标题按**路由名**取 i18n
 * 文案（key = `docTitle.<路由名>`），语言切换时通过 watch 立即刷新。
 * 路由名没有对应文案时（新增路由忘了加），只显示品牌名，不会漏出 key 本身。
 */
const applyDocumentTitle = (to) => {
  const brand = t('auth.brandName')
  const routeName = to?.name
  const key = routeName ? `docTitle.${routeName}` : ''
  const page = key ? t(key) : ''
  const hasPage = page && page !== key
  document.title = hasPage ? `${page} - ${brand}` : brand
}

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // 设置页面标题
  applyDocumentTitle(to)

  // ------------------------------------------------------------------------
  // 第 97 批：先问"未保存的修改要不要带走"
  // ------------------------------------------------------------------------
  // 放在**权限判断之前**：如果先判权限、再问未保存，管理员点到无权页面时会先被
  // 弹一个"没权限"、再弹一个"要不要离开"，两次弹窗叠在一起很困惑。
  // 顺序换成"先问去留、再判权限"更自然（用户表达的是"我要走"）。
  //
  // ⚠️ 这里用的是 **async 守卫 + 显式 `next()`** 的混合写法：本守卫是 `async`，
  //    所以 vue-router 会把返回值当作"是否放行"；但函数签名里还有 `next`，
  //    于是"既不 return 也不 next"的那条分支会让 vue-router 报
  //    `Invalid navigation guard`（实测：点"留在此页"时控制台出现这条 error）。
  //    统一改成显式 `next(false)` / `next()`，两种风格都满足。
  // ⚠️ 第 97 批的写法有个**严重副作用**（第 103 批的 E2E 抓出来的真实 bug）：
  //    当时为了让"无未保存内容"和"有未保存内容但用户选择离开"都继续走后面的
  //    权限判断，写成了
  //        if (!canLeave) { next(false); return }
  //        next(); return          // ← 这个 return 把**后面所有鉴权逻辑全跳过了**
  //    于是 `runLeaveGuards()` 返回 true 时，`requiresAuth` / `requiresAdmin`
  //    的检查**根本不执行** —— 匿名用户直接访问 `/admin/users` 会停在管理页面上
  //    （顶栏显示"登录/立即注册"，页面却是用户管理表格，只是数据为空）。
  //
  //    修法：拦下时 `next(false)` 并结束；放行时**不 return**，让控制流继续往下
  //    走完鉴权。这就是"用 next 风格时不要再 return"的意义。
  if (to.fullPath !== from.fullPath) {
    const canLeave = await runLeaveGuards()
    if (!canLeave) {
      next(false)
      return
    }
  }

  // 检查是否需要登录
  if (to.matched.some(record => record.meta.requiresAuth)) {
    if (!authStore.isAuthenticated) {
      // 未登录，重定向到登录页。
      //
      // 第 116 批：**管理区送管理端登录页**。改前不管目标是什么一律送 `/login`，
      // 于是管理员点开 /admin/dashboard 时看到的是农户那套"拍照识别/注册"页面，
      // 与"入口分开"自相矛盾。这里按目标是否管理区选入口：
      //   · /admin/**  → /admin/login（深色「管理后台」入口）
      //   · 其它受保护页 → /login
      // 仍然只传**原因码**（第 84 批的约定），由登录页按当前语言翻译后显示。
      const targetIsAdminArea = to.matched.some(record => record.meta.requiresAdmin)
      next({
        name: targetIsAdminArea ? 'admin-login' : 'login',
        query: {
          redirect: to.fullPath,
          // 第 84 批：这里原来传的是 **已翻译好的句子** 且键名写错（auth.loginRequired
          // 在 i18n 表里不存在），登录页又完全没有读取它 —— 等于"跳转原因"整条链路是死的。
          // 现在只传**原因码**，由登录页按当前语言翻译后显示（允许列表见 LoginView）。
          reason: 'loginRequired'
        }
      })
      return
    }

    // 检查是否需要管理端权限（第 126 批：从"是不是管理员"改成"有没有这个页面的能力"）
    //
    // 第 17 批原本用的是 `authStore.isAdmin`（is_staff / is_superuser / role=ADMIN）。
    // 第 125 批起 `role=EDITOR`（信息编辑员）也能进后台，但他**不是**管理员 ——
    // 用 isAdmin 会把他挡在门外；反过来只判断"能进后台"又会让他直接输
    // `/admin/users` 就能打开用户管理页（虽然接口会 403，但页面白开）。
    // 因此按每条路由的 `meta.capability` 逐个判断，并保留 `requiresAdmin` 作为
    // 老路由（农户端页面上的管理员按钮）的兼容标记。
    //
    // 第 128 批：内容侧再按 `meta.module` 判断 —— 内容能力拆成四个互不干扰的模块
    // （内容审核 / 新闻管理 / 病害百科 / 意见反馈），只勾其中一块的编辑员
    // 手输别的模块网址会被弹回，并被告知"没有该模块权限"。
    if (to.matched.some(record => record.meta.requiresAdmin)) {
      const required = to.matched
        .map(record => record.meta.capability)
        .find(Boolean);
      const requiredModule = to.matched
        .map(record => record.meta.module)
        .find(Boolean);
      // 第 151 批：一个页面可以由**多个模块中的任意一个**开放 —— 典型是论坛管理/评论管理：
      // 「内容审核」（宽口径：能审帖自然能管论坛）与「论坛交流」（细口径：只管论坛）
      // 任一命中即可。用数组写 meta.modules，优先级高于单个 meta.module。
      const requiredModules = to.matched
        .map(record => record.meta.modules)
        .find(list => Array.isArray(list) && list.length);

      // 没标能力的老路由：能进后台即可
      let allowed = required ? authStore.hasCapability(required) : authStore.canAccessConsole;
      let blockedByModule = false;
      if (allowed && requiredModules) {
        allowed = requiredModules.some(module => authStore.hasContentModule(module));
        blockedByModule = !allowed;
      } else if (allowed && requiredModule) {
        allowed = authStore.hasContentModule(requiredModule);
        blockedByModule = !allowed;
      }

      // 第 148 批：有几页**只有全权管理员**能看 —— 典型是「操作日志」：
      // 它显示"谁在什么时候对谁做了什么"，内容编辑员不该看到别的管理员的操作记录
      // （后端接口也是 is_full_admin 门禁，这里只是别让他白开一个空页面）。
      const needsFullAdmin = to.matched.some(record => record.meta.fullAdminOnly);
      if (allowed && needsFullAdmin && !authStore.isAdmin) {
        allowed = false;
      }

      if (!allowed) {
        // 提示并送回上一页；但直接输网址进来时 from 是空路径，
        // 送 "/" 比留在管理页更合理（第 103 批补：原来 `from.path || '/'` 在
        // 直接进入时确实会回首页，这里保持并补上注释说明为什么不是留在原地）。
        //
        // 第 126 批补充：如果这个人**能进后台、只是没有这一页的权限**（典型：信息编辑员
        // 手输 /admin/users），把他丢回首页会让人以为是"页面坏了"；送回后台里他
        // 有权限的那一页更说得通，并明确告诉他原因。
        const fallback = authStore.canAccessConsole ? '/admin/dashboard' : (from.path || '/');
        if (blockedByModule) {
          const moduleLabel = (requiredModules || [requiredModule])
            .map(module => t(`contentModule.${module}`))
            .join(t('msg.moduleOr'));
          ElMessage.warning(t('msg.needModule', { module: moduleLabel }));
        } else if (needsFullAdmin) {
          ElMessage.warning(t('msg.needFullAdmin'));
        } else {
          ElMessage.warning(required === 'USER_ADMIN'
            ? t('msg.needUserAdmin')
            : t('msg.noPermission'));
        }
        next(fallback);
        return;
      }
    }
  }

  // 继续导航
  next()
})

// 第 77 批：切换语言后，标签页标题要立刻跟着变（守卫只在导航时跑）
watch(locale, () => applyDocumentTitle(router.currentRoute.value))

export default router
