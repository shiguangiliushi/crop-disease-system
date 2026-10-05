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

  const isAdmin = computed(() => {
    // 管理员判定必须与后端口径一致（否则前端放行、后端 403）：
    //   - permissions.IsAdminOrReadOnly：认 is_staff / is_superuser / role=ADMIN
    //   - DetectionHistoryView.get_queryset 的 user / search / all_users 分支同理
    //     （对应第 22 批把「识别记录管理」并入 HistoryView 之后的 /history 范围切换）
    // 第 17 批曾用过 `role === 'EDITOR'`，但 role 的取值里**没有** EDITOR
    // （以 grep models.py 的 ROLE_CHOICES 为准），所以这里不再引用它。
    // 结论：能进 /admin/* 的只有 role=ADMIN 或 is_staff，二者按"或"合并。
    return Boolean(
      user.value?.is_staff ||
      user.value?.is_superuser ||
      user.value?.role === 'ADMIN'
    );
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
      const response = await api.post('login/', credentials, {
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
            throw new Error(fieldErrors.join('\n'));
          }
        }
        
        throw new Error(errorMessage);
      } else if (error.request) {
        throw new Error(t('msg.cannotConnect'));
      } else {
        // 其它错误原样抛出
        throw error;
      }
    }
  }

  async function logout(router) {
    try {
      // 通知后端注销（失败也不影响本地登出）
      try {
        await api.post('logout/');  // 更新为正确的登出端点
      } catch (error) {
        console.warn("Logout API call failed, but continuing with local logout:", error);
      }
    } finally {
      clearAuth();
      // 有 router 就跳登录页
      if (router && typeof router.push === 'function') {
        router.push('/login');
      } else {
        // 没有 router（极少见）就整页跳转
        window.location.href = '/login';
      }
    }
  }

  async function checkAuth() {
    try {
      // 内存里已有 token
      if (authToken.value) {
        console.log('Auth token found in store, assuming user is authenticated.');
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


  return {
    user,
    authToken,
    isAuthenticated,
    isAdmin,
    setupAuthInterceptors,  // 拦截器注册与清理
    login,
    register,
    logout,
    checkAuth,
    setAuth,
    updateUser,
    // 必须导出 clearAuth：main.js 的 initAuth 与 utils/axios.js 的 401 处理
    // 都在调 authStore.clearAuth()，漏掉会抛 TypeError、401 之后清不掉登录态；
    // main.js 的初始化也依赖它处理"本地身份已失效"的情况。
    clearAuth,
  };
});
