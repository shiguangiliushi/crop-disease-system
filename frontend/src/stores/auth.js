import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import api from '@/utils/axios';
import { t } from '@/i18n';  // 第 84 批：错误文案跟随语言
// 身份读写统一走适配器：token/user 存在 sessionStorage（标签页隔离，互不顶掉），
// localStorage 只留一份"最近一次登录的账号"作为新标签页的兜底。
// 具体规则见 utils/authStorage.js 的模块注释。
import { getIdentity, saveIdentity, clearIdentity, patchStoredUser } from '@/utils/authStorage';

// Helper function to get cookie value by name
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

/**
 * 从登录/注册响应里取出 user/token，屏蔽三种不同的响应形状。
 *
 * 历史上后端与拦截器改过几轮，实际拿到的可能是：
 *   ① @/utils/axios 已解包成 2xx 的业务体：{status, message, data}；
 *   ② 原始 AxiosResponse，还要再取一层 .data；
 *   ③ 后端直接返回扁平的 {user, token}。
 * 这里最多向下钻 3 层，找到同时含 user/token 的那一层为止，取不到就原样返回。
 */
function unwrapAuthPayload(response) {
  let cur = response;
  for (let depth = 0; depth < 3 && cur && typeof cur === 'object'; depth += 1) {
    if (cur.user && cur.token) return cur;
    if (cur.data && typeof cur.data === 'object') {
      cur = cur.data;
      continue;
    }
    break;
  }
  return cur && typeof cur === 'object' ? cur : {};
}

export const useAuthStore = defineStore('auth', () => {
  // 初始状态从存储恢复（sessionStorage 优先，见 utils/authStorage.js）
  const loadInitialState = () => {
    try {
      const { token, user: storedUser, source } = getIdentity();

      // 没有 token 就没有登录态，直接返回
      if (!token) {
        console.log('No auth token found in storage');
        return { user: null, token: null };
      }

      console.log('Loaded initial auth state:', {
        hasUser: !!storedUser,
        hasToken: !!token,
        source,                    // 'session' = 本标签页自己的登录态
        tokenLength: token?.length || 0
      });

      return { user: storedUser, token };
    } catch (error) {
      console.error('Error loading initial auth state:', error);
      return { user: null, token: null };
    }
  };
  
  // 初始状态
  const initialState = loadInitialState();
  const user = ref(initialState.user);
  const authToken = ref(initialState.token);
  
  // 同步到本地存储
  const updateStorage = ({ user: userData, token }) => {
    saveIdentity({ user: userData, token });
  };

  // 拦截器的清理函数（重复注册前先清旧的）
  let cleanupInterceptors = null;
  
  const setupAuthInterceptors = (router) => {
    // 避免重复注册
    if (cleanupInterceptors) {
      cleanupInterceptors();
    }
    
    // 请求拦截器
    const requestInterceptor = api.interceptors.request.use(
      config => {
        // 自动带上 Token
        if (authToken.value) {
          config.headers.Authorization = `Token ${authToken.value}`;
        }
        return config;
      },
      error => {
        return Promise.reject(error);
      }
    );
    
    // 响应拦截器
    const responseInterceptor = api.interceptors.response.use(
      response => response,
      error => {
        if (error.response?.status === 401) {
          // 登录已失效
          clearAuth();
          // 跳登录页（已经在登录页就不重复跳）
          if (router && router.currentRoute.value.path !== '/login') {
            router.push('/login');
          }
        }
        return Promise.reject(error);
      }
    );
    
    // 清理函数
    cleanupInterceptors = () => {
      // 注意：拦截器挂在 api（utils/axios 的实例）上，**没有** .axios 这一层。
      // 写成 api.axios.interceptors 会抛 TypeError，且旧的拦截器不会被摘掉。
      api.interceptors.request.eject(requestInterceptor);
      api.interceptors.response.eject(responseInterceptor);
    };
    
    return cleanupInterceptors;
  };
  
  const isAuthenticated = computed(() => {
    // 有 token 即视为已登录
    const hasToken = !!authToken.value;
    console.log('Auth store - isAuthenticated check:', { 
      hasToken,
      user: user.value,
      currentTime: new Date().toISOString()
    });
    return hasToken;
  });

  // ==========================================================================
  // 能力（capabilities）—— 第 124 批
  // --------------------------------------------------------------------------
  // 后端 `api/capabilities.py` 是**唯一**口径，并通过 `/api/login/`、
  // `/api/check-auth/` 的 `user.capabilities` 字段下发。前端不再自己拿
  // is_staff / role 推"我是不是管理员"—— 因为那样必然与后端漂移
  // （第 17 批就踩过：前端认 `role === 'EDITOR'`，后端根本不认它）。
  //
  // 三个能力（见后端 capabilities.py）：
  //   CONTENT      内容生产：病害百科 / 新闻 / 内容审核 / 反馈回复 / 日历 / 只读看板
  //   USER_ADMIN   用户与他人数据：用户管理 / 重置链接 / 专家授予 / 他人识别记录
  //   BROADCAST    对外发声与系统开关：公告 / 预警推送 / 敏感词 / 论坛版块
  //
  // ⚠️ 前端只负责"别把做不到的东西画出来"（菜单、按钮），**边界始终在后端**。
  // ==========================================================================
  const CAP_CONTENT = 'CONTENT';
  const CAP_USER_ADMIN = 'USER_ADMIN';
  const CAP_BROADCAST = 'BROADCAST';

  /**
   * 当前账号的能力清单
   *
   * 优先用后端下发的 `user.capabilities`；**缺失时按老口径兜底**：
   * 老版本登录响应没有这个字段（或用户资料来自旧缓存），此时按
   * is_staff / is_superuser / role==='ADMIN' 给全部三项 —— 与后端
   * `is_full_admin()` 完全一致，因此兜底不会放行后端不允许的事。
   */
  const capabilities = computed(() => {
    const raw = user.value?.capabilities;
    if (Array.isArray(raw)) return raw;
    const isLegacyFullAdmin = Boolean(
      user.value?.is_staff ||
      user.value?.is_superuser ||
      user.value?.role === 'ADMIN'
    );
    return isLegacyFullAdmin ? [CAP_CONTENT, CAP_USER_ADMIN, CAP_BROADCAST] : [];
  });

  // ==========================================================================
  // 内容模块（第 128 批）
  // --------------------------------------------------------------------------
  // `CONTENT` 这一个能力内部再分四个**互不干扰**的模块，按人授权（后端
  // `EditorModuleGrant`）：内容审核 / 新闻管理 / 病害百科 / 意见反馈。
  // 侧栏与路由守卫都要看它 —— 只勾了「新闻管理」的编辑员**看不到**也算不进
  // 病害百科维护（后端同样会 403）。
  // ==========================================================================
  const MODULE_REVIEW = 'review';
// 第 151 批：论坛交流（只管论坛：帖子与评论，含置顶加精与帖子审核）
const MODULE_FORUM = 'forum';
  const MODULE_NEWS = 'news';
  const MODULE_PESTS = 'pests';
  const MODULE_FEEDBACK = 'feedback';
  // 顺序即用户管理弹窗里勾选框的顺序（与后端 capabilities.CONTENT_MODULES 一致）
const CONTENT_MODULES = [
  MODULE_REVIEW, MODULE_FORUM, MODULE_NEWS, MODULE_PESTS, MODULE_FEEDBACK,
];

  /**
   * 当前账号拥有的内容模块
   *
   * 后端在 `/api/login/`、`/api/check-auth/` 的 `user.content_modules` 里下发。
   * 兜底规则与后端 `is_full_admin()` 一致：全权管理员四个模块全给
   * （老缓存里没有这个字段时也不会把管理员的菜单弄丢）。
   */
  const contentModules = computed(() => {
    const raw = user.value?.content_modules;
    if (Array.isArray(raw)) return raw;
    return capabilities.value.length === 3 ? [...CONTENT_MODULES] : [];
  });

  /** 是否有某个内容模块（页面/菜单用它，不要再用 hasCapability(CONTENT)） */
  const hasContentModule = (module) => contentModules.value.includes(module);

  /** 是否具备某个能力（页面/按钮用它，不要再用 isAdmin） */
  const hasCapability = (capability) => capabilities.value.includes(capability);

  /**
   * 能否进入管理后台（侧栏里至少有一项可看）
   *
   * 路由守卫 `requiresAdmin` 用的是它 —— 比 isAdmin 更准：
   * 第 125 批起 `role=EDITOR`（信息编辑员）能进后台，但要**进来的不是管理员**。
   */
  const canAccessConsole = computed(() => capabilities.value.length > 0);

  const isAdmin = computed(() => {
    // 全权管理员（is_staff / is_superuser / role=ADMIN）—— **保留原名**，
    // 因为农户端页面上还有一批"管理员才有"的入口（识别记录全站视图、公告发布、
    // 预警推送、敏感词、版块管理…），它们分散在十几个视图里，逐个改名的风险大于收益。
    //
    // 第 124 批：语义收紧为"**三项能力全都有**"（而不是"is_staff 或 role=ADMIN"），
    // 于是信息编辑员不会因为能进后台就被当成管理员（否则他会看到公告发布、
    // 清空识别记录这些按钮，点了必然 403）。
    // ⚠️ 新代码请优先用 hasCapability(cap) / canAccessConsole，
    //    需要"全权管理员"时才用 isAdmin。
    return capabilities.value.length === 3;
  });

  function setAuth({ userData, token, remember = true }) {
    console.log('Setting auth:', { 
      hasUserData: !!userData, 
      hasToken: !!token,
      remember
    });
    
    // 更新内存状态
    user.value = userData;
    authToken.value = token;
    
    // 同步本地存储
    if (remember) {
      updateStorage({ user: userData, token });
    } else {
      // 不记住：清掉本地存储里的身份
      updateStorage({ user: null, token: null });
    }
  }

  function clearAuth() {
    user.value = null;
    authToken.value = null;
    clearIdentity();
    // 注意：这里只清身份，不动其它本地数据（例如用户自己保存的账号偏好）
  }

  /**
   * 局部更新当前登录用户（如改了昵称/邮箱），并同步到存储。
   * 之所以单独提供：UserProfileView 里直接 `authStore.user = {...}` 不会落盘，
   * 刷新后"改了资料却还是旧名字"，所以统一走这里。
   */
  function updateUser(partial = {}) {
    const merged = { ...user.value, ...partial };
    user.value = merged;
    patchStoredUser(partial);
    return merged;
  }

  async function login(credentials, router) {
    try {
      console.log('Sending login request with credentials:', credentials);
      
      // 先清掉旧登录态，避免半登录状态
      clearAuth();
      
      // 发起登录请求
      // 第 231 批：`device: 'web'` —— 后端"每设备一张 token"，
      // 桌面登录不再把手机端那张凭证删掉（两端可以同时在线）
      const response = await api.post('login/', { ...credentials, device: 'web' }, {
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'X-CSRFToken': getCookie('csrftoken'),
          // 登录接口不需要旧的 Authorization 头
          'Authorization': undefined
        },
        withCredentials: true
      });
      
      console.log('Raw login response:', response);

      if (!response) {
        console.error('Empty response from server');
        throw new Error(t('msg.serverEmptyResponse'));
      }

      // 统一取出载荷
      // 说明：@/utils/axios 会把 2xx 的响应**解包**一次，但各接口写法不一，
      // 于是这里可能是 {status, message, data:{user, token}}，也可能是已经解到
      // response.data、甚至直接是扁平的 {user, token}；早期还可能拿到原始
      // AxiosResponse。统一交给 unwrapAuthPayload 处理，避免"登录明明成功、
      // 界面却没登录"这类只在某种响应形状下才复现的问题。
      const payload = unwrapAuthPayload(response);
      console.log('Response data structure:', payload);

      // 后端可能返回 200 但 status:'error'（业务失败）
      if (payload.status === 'error' || response.status === 'error') {
        const msg = payload.message || response.message || t('msg.loginFailed');
        console.error('Login failed with status:', payload.status, 'Message:', msg);
        throw new Error(msg);
      }

      // 校验响应结构
      if (!payload.user || !payload.token) {
        console.error('Invalid response data structure:', payload);
        throw new Error(t('msg.loginBadPayload'));
      }

      // 写入登录态
      setAuth({
        userData: payload.user,
        token: payload.token,
        remember: true
      });

      console.log('Login succeeded, redirecting to home');
      
      // 有 router 就自动跳首页
      if (router) {
        router.push('/');
      }
      
      return { user: payload.user, token: payload.token };
    } catch (error) {
      console.error("Login failed:", error);
      if (error.response) {
        // 后端返回了错误详情（如"密码错误，还可尝试 N 次"）
        const data = error.response.data || {};
        const errorMessage = data.detail || data.message || 'Login failed';
        // 第 101 批：**把后端的业务错误码带出来**。
        //
        // 改前这里 `throw new Error(msg)` 会把 axios error 整个丢掉，调用方只能看到
        // 一句话 —— 于是登录页无法区分"密码错"和"账号在注销冷静期（可取消）"，
        // 也就没法给出「取消注销」这个唯一出路。
        // 现在把 `code` 与几个附加字段挂到抛出的 Error 上，调用方按需读取。
        const wrapped = new Error(errorMessage);
        wrapped.status = error.response.status;
        if (data.code) {
          wrapped.code = data.code;
          // 冷静期相关的附加信息（前端要用它显示"还剩几天"）
          wrapped.canCancel = data.can_cancel;
          wrapped.daysLeft = data.days_left;
          wrapped.scheduledFor = data.scheduled_for;
        }
        throw wrapped;
      } else if (error.request) {
        throw new Error(t('msg.cannotConnect'));
      } else {
        // 其它错误原样抛出
        throw error;
      }
    }
  }

  // 注意：不要在这里引用组件内的 router（会 ReferenceError: router is not defined）。
  // 因此 login(credentials, router) / register(userData, router) 都由调用方传入 router，
  // 见 LoginView.vue / RegisterView.vue 的用法。
  async function register(userData, router) {
    try {
      console.log('Sending registration request with data:', userData);
      const body = await api.post('register/', userData);
      console.log('Registration response data:', body);

      if (!body) {
        throw new Error(t('msg.serverEmptyResponse'));
      }

      // 统一取出载荷（兼容"客户端已解包"、"AxiosResponse 多一层 .data"、
      // "后端返回扁平 {user, token}" 三种情况）
      const payload = unwrapAuthPayload(body);

      // 后端签发了 token → 直接完成登录
      if (payload.token && payload.user) {
        setAuth({
          userData: payload.user,
          token: payload.token,
          remember: true
        });
        console.log('Registration successful, redirecting to home');
        if (router && typeof router.push === 'function') {
          router.push('/');
        }
      } else {
        // 旧行为：后端没签发 token，交给用户再登录一次
        console.log('Registration successful, redirecting to login');
        if (router && typeof router.push === 'function') {
          router.push('/login');
        }
      }

      return payload;
    } catch (error) {
      console.error("Registration failed:", error);
      if (error.response) {
        // 后端返回了错误详情
        const errorMessage = error.response.data?.detail || 
                           error.response.data?.message || 
                           error.response.data?.error ||
                           'Registration failed';
        
        // 字段级错误（如"该邮箱已被其他账号使用"）
        if (error.response.data) {
          const fieldErrors = [];
          for (const [field, errors] of Object.entries(error.response.data)) {
            if (Array.isArray(errors)) {
              fieldErrors.push(`${field}: ${errors.join(', ')}`);
            } else if (typeof errors === 'string') {
              fieldErrors.push(errors);
            }
          }
          
          if (fieldErrors.length > 0) {
            // 第 233 批：把原始响应挂回去 —— 调用方（注册页）要靠
            // `error.response.data.captcha_code` 判断"是不是验证码错"，
            // 只抛一句拼好的字符串会让这个判断失效（实测：验证码错了却不换图）。
            const wrapped = new Error(fieldErrors.join('\n'));
            wrapped.response = error.response;
            wrapped.data = error.response.data;
            throw wrapped;
          }
        }

        const wrapped = new Error(errorMessage);
        wrapped.response = error.response;
        wrapped.data = error.response?.data;
        throw wrapped;
      } else if (error.request) {
        throw new Error(t('msg.cannotConnect'));
      } else {
        // 其它错误原样抛出
        throw error;
      }
    }
  }

  /**
   * 登出。
   *
   * 第 117 批改了**顺序**，并加了 `redirectTo`：
   *   · 改前：`await api.post('logout/')` → 再 `clearAuth()` + 跳转。
   *     开发机上这个注销请求实测要 5 秒以上，于是用户点完"退出登录"会**盯着管理后台
   *     发呆好几秒**，看起来像按钮没反应（管理端尤其明显，因为它就在顶部条上）。
   *   · 现在：先取 token → 立刻 `clearAuth()` + 跳转 → 再**尽力**通知服务端。
   *     本地登出是用户能感知的那一半，不该等服务端。
   *
   * ⚠️ 顺序换了之后有个坑：`clearAuth()` 会把内存里的 token 清掉，而两个请求拦截器
   *    正是从 `authStore.authToken` 取 `Authorization` —— 服务端那一步必须**显式带上**
   *    刚才取出来的 token，否则后端删不掉这个 token（`LogoutView` 是靠
   *    `request.user.auth_token.delete()` 作废它的）。
   *
   * `redirectTo` 默认仍是农户登录页；管理后台传 `/admin/login`（第 117 批），
   * 免得管理员退出后被丢到农户登录页、以为自己走错了站。
   */
  async function logout(router, redirectTo = '/login') {
    const token = authToken.value;

    clearAuth();

    if (router && typeof router.push === 'function') {
      router.push(redirectTo);
    } else {
      // 没有 router（极少见）就整页跳转
      window.location.href = redirectTo;
    }

    try {
      await api.post('logout/', {}, {
        headers: token ? { Authorization: `Token ${token}` } : {},
        // 这一请求 401 只说明"这个 token 早就失效了"，不该再把人往登录页拽一次
        // （在管理后台里那就是被丢回农户登录页）——见 utils/axios.js 的 skipAuthRedirect
        skipAuthRedirect: true,
      });
    } catch (error) {
      // 本地已经登出，通知服务端失败不影响用户；最坏情况是这个 token 留到服务端过期
      console.warn('Logout API call failed, but local logout already done:', error);
    }
  }

  /**
   * 恢复登录态（**只读本地**，不请求后端）
   *
   * ⚠️ 第 123 批把话说明白：这里以前叫"检查认证状态"，日志也写
   *    "checking auth status"，但实现**只是读 sessionStorage/localStorage**，
   *    对"token 还有没有效"一无所知 —— 于是失效 token 也会被判定为已登录
   *    （打印 "assuming user is authenticated"），接着一整屏接口 401。
   *
   * 为什么不在这里补一次网络校验：
   *   · 真正该管这件事的是**接口层**：任何请求 401 都由 `api/http.js` 的响应
   *     拦截器统一清登录态 + 跳对应端的登录页（第 123 批补的），
   *     所以"第一次真正需要数据的时候"就会被纠正，不需要额外加一次开机请求；
   *   · 开机多打一个请求对**离线场景**不友好：本项目有离线模式，
   *     断网时不该因为"校验不了"就把用户登出。
   * 需要主动校验时用 `verifyToken()`（会打后端，只在明确需要时调用）。
   */
  async function checkAuth() {
    try {
      // 内存里已有 token
      if (authToken.value) {
        console.log('Auth token found in store, using cached login state (validity is enforced on API 401).');
        return true;
      }

      console.log('No token in store, reading from storage...');
      const { token: storedToken, user: storedUser } = getIdentity();

      if (storedToken && storedUser) {
        console.log('Found token and user in storage, restoring auth state.');
        authToken.value = storedToken;
        user.value = storedUser;
        return true;
      }

      // 只有 token 没有 user：仍算已登录（用户资料可以稍后再拉），
      // 避免"token 有效却因为缺资料被判定未登录"。
      if (storedToken) {
        console.log('Found token only, restoring token without user profile.');
        authToken.value = storedToken;
        user.value = null;
        return true;
      }

      console.log('No auth token found in storage.');
      return false;
    } catch (error) {
      console.error("An unexpected error occurred during auth check:", error);
      clearAuth();
      return false;
    }
  }

  /**
   * 主动向后端校验 token（第 123 批）
   *
   * 与 `checkAuth()` 的区别：这个**会发请求**，返回 boolean，并在 401 时清掉本地登录态。
   * 断网（请求根本没发出去）时**不动登录态**，返回 true —— 离线模式仍然可用。
   */
  /**
   * 向后端**核对一次身份**，把权限相关字段刷新到本地（第 180 批）
   * ------------------------------------------------------------------
   * 为什么需要：`checkAuth()` 只看本地存储（有 token 就直接返回），于是
   * 「管理员把某人的信息编辑员取消掉」之后，那个人**刷新页面也仍然看到「管理后台」**
   * —— 浏览器里缓存的 `user.capabilities` / `content_modules` 还是旧的 ✗。
   * 后端其实立刻收回了（`capabilities.py` 刻意不做缓存），
   * 于是他点进去每个接口都 403：**入口还在、里面全拒**，最难排查的一种状态。
   *
   * 所以这里在**启动**与**标签页重新可见**时各核对一次（成本一个轻量请求）：
   *   · 成功 → 用后端返回的 user 覆盖本地（角色/能力/内容模块立即生效）；
   *   · 401 → 交给 `clearAuth()`（登录态确实失效了）；
   *   · **断网/网络错误 → 什么都不做**（离线模式仍然可用，绝不清登录态）。
   *
   * @returns {Promise<boolean>} 是否成功取到最新身份
   */
  /**
   * 核对身份并让权限变更立即生效（第 180 批）
   * ------------------------------------------------------------------
   * 场景：管理员在后台把某人的「信息编辑员」取消 → 那人浏览器里缓存的
   * `user.capabilities` / `content_modules` 仍是旧的，`checkAuth()` 又只看本地存储，
   * 于是**刷新页面也仍然看到「管理后台」** ✗，点进去每个接口却都 403
   * —— "入口还在、里面全拒"，最难排查的一种状态。
   *
   * 所以：启动时与标签页重新可见时各核对一次。
   *
   * ⚠️ 这里**复用 `verifyToken()`**：它已经用 `unwrapAuthPayload()` 正确解开了后端
   * `{status, message, data}` 那层包装并把 user 合并进内存。我自己再手写一份解析
   * 就踩了坑（层级搞错、永远取不到最新身份，等于修复没生效）—— 解析只留一处。
   *
   * 核对后把**权限相关字段**写回存储，这样立刻刷新也别再退回旧值。
   * 断网/5xx 时什么都不做（离线模式仍然可用），只有 401/403 才清登录态 —— 见 verifyToken。
   */
  async function refreshIdentity() {
    if (!authToken.value) return false;
    const ok = await verifyToken();
    if (!ok) return false;
    try {
      const current = user.value || {};
      const patch = {};
      for (const key of ['role', 'capabilities', 'content_modules', 'is_staff', 'is_superuser']) {
        if (current[key] !== undefined) patch[key] = current[key];
      }
      if (Object.keys(patch).length) patchStoredUser(patch);
    } catch (error) {
      console.warn('[auth] 权限字段写回存储失败（不影响本次会话）:', error?.message || error);
    }
    return true;
  }

  async function verifyToken() {
    if (!authToken.value) return false;
    try {
      const response = await api.get('check-auth/');
      const payload = unwrapAuthPayload(response);
      const data = payload?.data ?? payload;
      if (data?.username) {
        user.value = { ...(user.value || {}), ...data };
      }
      return true;
    } catch (error) {
      const status = error?.response?.status;
      if (status === 401 || status === 403) {
        clearAuth();
        return false;
      }
      // 网络问题（断网 / 后端没起）不该把人登出：离线模式还要用
      console.warn('Token 校验请求失败（按离线处理，不清登录态）:', error?.message || error);
      return true;
    }
  }


  return {
    user,
    authToken,
    isAuthenticated,
    isAdmin,
    // 第 124 批：能力口径（后端 capabilities.py 是唯一正源）
    capabilities,
    hasCapability,
    canAccessConsole,
    CAP_CONTENT,
    CAP_USER_ADMIN,
    CAP_BROADCAST,
    // 第 128 批：内容模块（内容审核 / 新闻管理 / 病害百科 / 意见反馈）
    contentModules,
    hasContentModule,
    CONTENT_MODULES,
    MODULE_REVIEW,
    MODULE_FORUM,
    MODULE_NEWS,
    MODULE_PESTS,
    MODULE_FEEDBACK,
    setupAuthInterceptors,  // 拦截器注册与清理
    login,
    register,
    logout,
    checkAuth,
    refreshIdentity,   // 第 180 批：核对身份，权限变更立即生效
    verifyToken,   // 第 123 批：主动向后端校验 token（会发请求，断网时不清登录态）
    setAuth,
    updateUser,
    // 必须导出 clearAuth：main.js 的 initAuth 与 utils/axios.js 的 401 处理
    // 都在调 authStore.clearAuth()，漏掉会抛 TypeError、401 之后清不掉登录态；
    // main.js 的初始化也依赖它处理"本地身份已失效"的情况。
    clearAuth,
  };
});
