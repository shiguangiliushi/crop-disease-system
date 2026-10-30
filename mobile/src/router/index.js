/**
 * 移动端路由
 * ----------------------------------------------------------------------------
 * 只放"农户在田里用得到"的五页：登录 / 注册 / 识别 / 结果 / 记录 / 我的。
 * 桌面端的论坛、百科、看板等一律不放 —— 手机屏幕塞不下，
 * 硬塞的结果是每个页面都不好用。
 *
 * meta 约定（第 173 批起顶栏由 App.vue 统一渲染，所以多了 back / navbar）：
 *   requiresAuth: true   → 未登录跳登录页（带上回跳地址）
 *   tabbar: false        → 不显示底部导航（登录/注册/结果页）
 *   title                → i18n key，用于 document.title
 */
import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { t } from '@/i18n';

const routes = [
  { path: '/', redirect: '/detect' },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: 'auth.loginTitle', tabbar: false },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { title: 'auth.registerTitle', tabbar: false, back: true },
  },
  {
    // 第 268 批：我的反馈
    path: '/feedback/mine',
    name: 'my-feedback',
    component: () => import('@/views/MyFeedbackView.vue'),
    meta: { title: 'myFeedback.title', tabbar: false, back: true },
  },
  {
    // 第 266 批：意见反馈
    path: '/feedback',
    name: 'feedback-form',
    component: () => import('@/views/FeedbackView.vue'),
    meta: { title: 'feedbackForm.title', tabbar: false, back: true },
  },
  {
    // 第 264 批：资料编辑
    path: '/profile/edit',
    name: 'profile-edit',
    component: () => import('@/views/ProfileEditView.vue'),
    meta: { title: 'profileEdit.title', tabbar: false, back: true },
  },
  {
    // 第 261 批：站内通知（入口在「我的」）
    path: '/notifications',
    name: 'notifications',
    component: () => import('@/views/NotificationsView.vue'),
    meta: { title: 'notify.title', tabbar: false, back: true },
  },
  {
    // 第 260 批：病害百科详情（结果页点「查看病害百科」进来）
    path: '/pests/:keyword',
    name: 'pest-detail',
    component: () => import('@/views/PestDetailView.vue'),
    meta: { title: 'pestWiki.title', tabbar: false, back: true },
  },
  {
    // 第 91 批：忘记密码。此前移动端没有这一页，忘了密码 = 永久登不进（只能找管理员）。
    path: '/forgot-password',
    name: 'forgot-password',
    component: () => import('@/views/ForgotPasswordView.vue'),
    meta: { title: 'auth.forgotTitle', tabbar: false, back: true },
  },
  {
    path: '/detect',
    name: 'detect',
    component: () => import('@/views/DetectView.vue'),
    meta: { title: 'detect.title', requiresAuth: true },
  },
  {
    path: '/result',
    name: 'result',
    component: () => import('@/views/ResultView.vue'),
    meta: { title: 'result.title', requiresAuth: true, tabbar: false, back: true },
  },
  {
    // 从识别记录点进来的详情：同一个结果页，数据源换成接口
    path: '/result/:id(\\d+)',
    name: 'result-detail',
    component: () => import('@/views/ResultView.vue'),
    props: true,
    meta: { title: 'history.detail', requiresAuth: true, tabbar: false, back: true },
  },
  {
    path: '/history',
    name: 'history',
    component: () => import('@/views/HistoryView.vue'),
    meta: { title: 'history.title', requiresAuth: true },
  },
  {
    // 未登录也能看：页面里引导去登录，比"点进去被弹回登录页"友好
    path: '/mine',
    name: 'mine',
    component: () => import('@/views/MineView.vue'),
    meta: { title: 'mine.title' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/detect' },
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});

router.beforeEach((to) => {
  const auth = useAuthStore();

  document.title = to.meta?.title ? `${t(to.meta.title)} · ${t('common.appName')}` : t('common.appName');

  if (to.meta?.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } };
  }
  // 已登录还去登录/注册页 → 直接回识别页，省掉"再登一次"的困惑
  // （忘记密码页不在此列：已登录的人也可能是来给别的账号重置的，不该被弹走）
  if (auth.isAuthenticated && (to.name === 'login' || to.name === 'register')) {
    return { name: 'detect' };
  }
  return true;
});

export default router;
