/**
 * 登录表单行为（第 119 批抽出）
 * ============================================================================
 * 为什么要有它：`/login`（农户）与 `/admin/login`（管理端）是**两套完全不同的界面**
 * —— 布局、配色、文案、有没有注册入口都不一样。但它们要的东西是同一套：
 *
 *   · 用户名建议（本地记录的最近登录账号，只记账号名、绝不记密码）
 *   · 「记住登录状态」偏好
 *   · 密码显隐
 *   · 被路由守卫弹回来时的**原因码**翻译（?reason=loginRequired / sessionExpired）
 *   · 注销冷静期的「取消注销」这条唯一出路（第 101 批）
 *   · 登录成功后的落点（带安全检查的 ?redirect=，否则按角色给默认页）
 *
 * 这些行为抄两份出来必然慢慢长歪（本项目已经吃过"同一套逻辑两个口径"的亏，
 * 见第 106 批把注册/改密/重置三处的密码规则统一）。所以：
 *   **行为在这里，界面与文案在各自的页面里。**
 *
 * 用法：
 *   const form = useLoginForm({ adminEntry: false });
 *   // 模板里用 form.username / form.handleLogin / form.pendingDeletion …
 *
 * ⚠️ 返回值是 `reactive({...})`，**不是普通对象** —— 这一点踩过坑，别改回去：
 *    普通对象里装 ref，模板里 `form.isLoading` 拿到的是 **Ref 本身**（永远 truthy），
 *    `:disabled="form.isLoading"` 于是恒为真，页面一打开输入框就是灰的、填不进去。
 *    Vue 只在**顶层 setup 绑定**和 **reactive 对象的属性**上自动解包 ref，
 *    "普通对象的一层属性"不在其列。用 reactive 包一层，`form.x` 才是值。
 */
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { useAuthStore } from '@/stores/auth.js';
import { useI18n } from '@/i18n';
import { cancelMyDeletion } from '@/api/account';
import { fetchCaptcha, loginCaptchaRequired } from '@/api/captcha';  // 第 246 批：登录验证码
import { formatApiError } from '@/api/http';

// ============================================================================
// 第 84 批：显示"为什么被弹回登录页"
// ----------------------------------------------------------------------------
// 路由守卫会把未登录访问受保护页面的人重定向到登录页（带 ?reason=xxx），
// 但登录页从来没读过这个参数 —— 用户只看到登录框，不知道刚才发生了什么。
// 这里**只认原因码**（不做"把 query 文本直接贴出来"）：query 是用户可以随手改的，
// 直接渲染等于给钓鱼文案留了一个展示位。
// ============================================================================
const LOGIN_REASON_KEYS = {
  loginRequired: 'msg.loginRequired',
  sessionExpired: 'history.sessionExpired',
};

/** 早期版本把明文密码写进过 localStorage（第 35 批已废止），进页面顺手清掉 */
const LEGACY_PASSWORD_KEY = 'saved_passwords';

export function useLoginForm({ adminEntry = false } = {}) {
  const router = useRouter();
  const route = useRoute();
  const authStore = useAuthStore();
  const { t } = useI18n();

  // 第 246 批：登录验证码（开关由后端 GET /api/login/ 决定，默认关闭）
  const captchaRequired = ref(false);
  const captchaId = ref('');
  const captchaImage = ref('');
  const captchaCode = ref('');

  async function loadCaptcha() {
    try {
      captchaRequired.value = await loginCaptchaRequired();
      if (!captchaRequired.value) return;
      const data = await fetchCaptcha();
      captchaId.value = data.id;
      captchaImage.value = data.image;
      captchaCode.value = '';
    } catch (error) {
      console.warn('[login] 加载验证码失败，按"不需要验证码"处理', error);
      captchaRequired.value = false;
    }
  }

  const username = ref('');
  const password = ref('');
  const rememberMe = ref(false);
  const showPassword = ref(false);
  const errorMessage = ref('');
  const isLoading = ref(false);

  // 用户名建议
  const usernameSuggestions = ref([]);
  const showSuggestions = ref(false);

  // 注销冷静期（第 101 批）
  const pendingDeletion = ref(null);
  const cancelDialogVisible = ref(false);
  const cancelLoading = ref(false);
  const cancelError = ref('');

  const purgeLegacySavedPasswords = () => {
    try {
      if (localStorage.getItem(LEGACY_PASSWORD_KEY) !== null) {
        localStorage.removeItem(LEGACY_PASSWORD_KEY);
        console.warn('[安全] 已清除本地保存的明文密码（legacy saved_passwords）');
      }
    } catch (error) {
      console.error('清除历史明文密码失败:', error);
    }
  };

  const getUsernameSuggestions = () => {
    try {
      const allUsernames = JSON.parse(localStorage.getItem('all_usernames') || '[]');
      const lastUsername = localStorage.getItem('last_username');
      const usernames = [...allUsernames];
      if (lastUsername && usernames.includes(lastUsername)) {
        usernames.splice(usernames.indexOf(lastUsername), 1);
        usernames.unshift(lastUsername);
      }
      return usernames;
    } catch (error) {
      console.error('Failed to get username suggestions:', error);
      return [];
    }
  };

  const showUsernameSuggestions = () => {
    const suggestions = getUsernameSuggestions();
    if (suggestions.length > 0) {
      usernameSuggestions.value = suggestions;
      showSuggestions.value = true;
    }
  };

  /** 延迟隐藏：让用户有时间点到建议项 */
  const hideUsernameSuggestions = () => {
    setTimeout(() => {
      showSuggestions.value = false;
    }, 200);
  };

  const selectUsername = (selected) => {
    username.value = selected;
    showSuggestions.value = false;
    onUsernameChange();
  };

  /** 用户名变化时只恢复「记住我」偏好，**绝不回填密码**（密码交给浏览器密码管理器） */
  const onUsernameChange = () => {
    if (!username.value) return;
    rememberMe.value = localStorage.getItem(`remember_me_${username.value}`) === 'true';
  };

  // ==========================================================================
  // 登录后的落点（第 116 批起：管理端与农户端不同）
  // --------------------------------------------------------------------------
  // · 先看 `?redirect=`（守卫带过来的原目标）—— 但要**校一遍**：
  //   只接受站内绝对路径（以 / 开头且不是 //），否则 `?redirect=//evil.com`
  //   就成了一个开放重定向。
  // · 没有 redirect 时：管理员去「数据看板」，农户去首页。
  // ==========================================================================
  const destination = computed(() => {
    const raw = route.query.redirect;
    const safe = typeof raw === 'string' && raw.startsWith('/') && !raw.startsWith('//') ? raw : '';
    if (safe) return safe;
    return adminEntry ? '/admin/dashboard' : '/';
  });

  onMounted(() => {
    purgeLegacySavedPasswords();

    // 第 246 批：问一次"要不要验证码"（开关打开时才显示）
    loadCaptcha();

    const reasonKey = LOGIN_REASON_KEYS[route.query.reason];
    if (reasonKey) errorMessage.value = t(reasonKey);

    const lastUsername = localStorage.getItem('last_username');
    if (lastUsername) {
      username.value = lastUsername;
      onUsernameChange();
    }
  });

  const handleLogin = async () => {
    if (isLoading.value) return;

    errorMessage.value = '';
    isLoading.value = true;

    try {
      // ⚠️ 这里**不把 router 交给 store**：store 里的 login() 只会 `push('/')`，
      //    而管理员要落到「数据看板」、农户也可能要回到被拦下的页面。
      //    交给调用方决定落点，路径只有一条（少了"先跳首页再改跳"的闪一下）。
      await authStore.login({
        username: username.value,
        password: password.value,
        remember: rememberMe.value,
        // 第 246 批：后端开关打开时才需要；关着时多传两个字段无害
        captcha_id: captchaRequired.value ? captchaId.value : '',
        captcha_code: captchaRequired.value ? captchaCode.value.trim() : '',
      });

      // 只保存**账号名**（用于下次快速选择），密码交给浏览器密码管理器
      localStorage.setItem('last_username', username.value);
      try {
        const allUsernames = JSON.parse(localStorage.getItem('all_usernames') || '[]');
        if (!allUsernames.includes(username.value)) {
          allUsernames.push(username.value);
          localStorage.setItem('all_usernames', JSON.stringify(allUsernames));
        }
      } catch (error) {
        console.error('Failed to save username to all_usernames:', error);
      }
      localStorage.setItem(`remember_me_${username.value}`, rememberMe.value.toString());

      // 普通账号走错到管理员入口：不把人往"无权限"的墙上撞，说明白再送去首页
      //
      // 第 126 批：判定从 `isAdmin` 改成 `canAccessConsole` ——
      // 第 125 批起**信息编辑员（EDITOR）也能进管理后台**，他不是"管理员"
      // （isAdmin 要求三项能力齐全），但绝不是"走错门的普通账号"。
      // 用 isAdmin 会把他当成普通用户送回首页，而且提示"该账号不是管理员账号"——
      // 于是"有权限却进不去后台"，只有真的用编辑员登录一次才会发现。
      if (adminEntry && !authStore.canAccessConsole) {
        ElMessage.warning(t('adminAuth.notAdmin'));
        router.replace('/');
        return;
      }

      router.replace(destination.value);
    } catch (error) {
      console.error('Login error:', error);
      // 第 101 批：注销冷静期 —— 密码是对的，但账号已停用。
      // 这里必须给一条**出路**（"取消注销"），否则用户只会看到"无法登录"，
      // 而 15 天冷静期就白设了：没人知道还能反悔。
      //
      // ⚠️ 注意读的是 `error.code` 而不是 `error.response.data.code`：
      //    authStore.login 会把 axios error 包成普通 Error（只保留文案），
      //    响应体里的 code 由它转挂到 error.code 上（见 stores/auth.js）。
      pendingDeletion.value = error?.code === 'account_pending_deletion'
        ? { message: error.message || '', daysLeft: error.daysLeft }
        : null;
      // 第 142 批：被**停用**（不是冷静期）的账号，后端已经能给出准确原因了
      // （`account_disabled`）。这里用前端文案覆盖一下：后端那句是中文，
      // 英文界面下会中英混排 —— 这类**固定**提示适合放语言包里，
      // 带动态数字的（如"还可尝试 N 次"）才继续用后端文案。
      errorMessage.value = error?.code === 'account_disabled'
        ? t('auth.accountDisabled')
        : (error?.message || t('auth.networkError'));
    } finally {
      isLoading.value = false;
    }
  };

  // ==========================================================================
  // 第 101 批：取消注销（冷静期内账号登不上，所以入口在登录页）
  // ==========================================================================
  const openCancelDialog = () => {
    cancelError.value = '';
    // 账号名已经在输入框里了（用户刚从登录框提交过），这里不再重复问
    cancelDialogVisible.value = true;
  };

  const confirmCancelDeletion = async () => {
    if (!username.value || !password.value) {
      cancelError.value = t('auth.cancelNeedsBoth');
      return;
    }
    cancelLoading.value = true;
    cancelError.value = '';
    try {
      const result = await cancelMyDeletion({
        username: username.value,
        password: password.value,
      });
      cancelDialogVisible.value = false;
      pendingDeletion.value = null;
      // 后端取消成功后直接签发 Token：写进登录态，用户不必再登一次
      if (result?.token) {
        authStore.setAuth({
          userData: { username: result.username || username.value },
          token: result.token,
        });
      }
      ElMessage.success(t('auth.cancelOk'));
      router.replace(destination.value);
    } catch (error) {
    const data = error?.response?.data || error?.data || {};
    if (data.captcha_required) {
      // 第 246 批：验证码错/过期 —— 换一张再让用户填
      await loadCaptcha();
      errorMessage.value = t('auth.captchaWrong');
      isLoading.value = false;
      return;
    }

      cancelError.value = formatApiError(error, t('auth.cancelFailed'));
    } finally {
      cancelLoading.value = false;
    }
  };

  return reactive({
    // 状态
    username,
    password,
    rememberMe,
    showPassword,
    errorMessage,
    isLoading,
    // 第 246 批：登录验证码
    captchaRequired,
    captchaImage,
    captchaCode,
    loadCaptcha,
    usernameSuggestions,
    showSuggestions,
    pendingDeletion,
    // 交互
    onUsernameChange,
    showUsernameSuggestions,
    hideUsernameSuggestions,
    selectUsername,
    handleLogin,
    // 取消注销
    cancelDialogVisible,
    cancelLoading,
    cancelError,
    openCancelDialog,
    confirmCancelDeletion,
    // 落点（取消注销成功后也用同一个目标）
    destination,
  });
}
