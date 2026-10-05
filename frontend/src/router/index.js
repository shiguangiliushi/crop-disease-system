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
      meta: { title: '客服登录', bareLayout: true }
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
      meta: { title: '客服注册', bareLayout: true }
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
      path: '/news/create',
      name: 'news-create',
      component: NewsView,
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        title: '添加新闻',
        breadcrumb: ['新闻', '添加']
      }
    },
    {
      path: '/news/:id/edit',
      name: 'news-edit',
      component: NewsView,
      props: true,
      meta: {
        requiresAuth: true,
        requiresAdmin: true,
        title: '编辑新闻',
        breadcrumb: ['新闻', '编辑']
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
        title: '新闻管理',
        breadcrumb: ['管理', '新闻管理']
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
      // 未登录，重定向到登录页
      next({
        name: 'login',
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

    // 检查是否需要管理员权限
    if (to.matched.some(record => record.meta.requiresAdmin)) {
      // 第 17 批：改用 store 的统一管理员口径（is_staff / is_superuser / role=ADMIN），
      // 与后端权限类一致。原实现漏了 is_superuser，且依赖 role —— 而登录响应此前
      // 不返回 role，导致"仅角色管理员"被挡在管理页外面（后端其实是允许的）。
      if (!authStore.isAdmin) {
        // 非管理员用户：提示并送回上一页；但直接输网址进来时 from 是空路径，
        // 送 "/" 比留在管理页更合理（第 103 批补：原来 `from.path || '/'` 在
        // 直接进入时确实会回首页，这里保持并补上注释说明为什么不是留在原地）。
        ElMessage.warning(t('msg.noPermission'))
        next(from.path || '/')
        return
      }
    }
  }

  // 继续导航
  next()
})

// 第 77 批：切换语言后，标签页标题要立刻跟着变（守卫只在导航时跑）
watch(locale, () => applyDocumentTitle(router.currentRoute.value))

export default router
