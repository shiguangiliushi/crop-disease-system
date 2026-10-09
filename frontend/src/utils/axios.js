import axios from 'axios';
import { useAuthStore } from '@/stores/auth';
import { t } from '@/i18n';  // 第 83 批：错误兜底文案跟随语言

// 创建 axios 实例
// baseURL 与统一客户端 src/api/http.js 保持一致，避免出现
// “一部分请求打到 127.0.0.1:8000、另一部分打到 localhost:8000” 的双源问题。
const service = axios.create({
  baseURL: (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api').replace(/\/+$/, ''),
  timeout: 30000,   // 请求超时时间
  withCredentials: true, // 跨域时携带 Cookie（会话认证 / CSRF 需要）
  // 移除了默认的 Content-Type，让 axios 自动设置
});

// 请求拦截器
service.interceptors.request.use(
  config => {
    const authStore = useAuthStore();
    // 如果用户已登录，添加 token 到请求头
    // 注意：store 暴露的字段名是 authToken（不是 token）。原来读 authStore.token
    // 永远是 undefined，等于没有带 Authorization 头；识别/论坛等需要登录的接口
    // 只能靠 main.js 里额外注册的那个拦截器兜底，非常脆弱。
    if (authStore.authToken) {
      config.headers.Authorization = `Token ${authStore.authToken}`;
    }
    return config;
  },
  error => {
    return Promise.reject(error);
  }
);

// 响应拦截器
service.interceptors.response.use(
  response => {
    // 2xx 一律算成功。
    // 原来只认 200，于是「注册」接口返回的 201 被当成失败：
    // 账号其实已经创建成功，前端却抛错，用户看到的是「无法连接到服务器，请检查网络连接」。
    if (response.status >= 200 && response.status < 300) {
      return Promise.resolve(response.data);
    } else {
      return Promise.reject(response);
    }
  },
  // 当 http 状态码非 200 时的处理
  error => {
    if (error.response) {
      // 401: 未登录或 token 过期
      if (error.response.status === 401) {
        // 第 117 批：少数请求**明知可能 401、也不要被强制跳转** —— 目前只有"登出"
        // （它带的是刚被本地清掉的旧 token；失效就失效，不该把已经准备离开的人
        //   再拽到登录页一次，在管理后台里那意味着被丢回农户登录页）。
        // 传 `skipAuthRedirect: true` 的请求仍然会 reject，只是不做全局跳转。
        if (error.config?.skipAuthRedirect) {
          return Promise.reject(error);
        }

        // 本文件顶部已经静态导入了 useAuthStore，这里无需再动态 import。
        // 原来的 import('@/stores/auth') 既没有绕开循环依赖（静态导入已存在），
        // 又会让构建报 “dynamically imported but also statically imported” 告警。
        try {
          const authStore = useAuthStore();
          authStore.clearAuth();
        } catch (err) {
          console.error('Error clearing auth state:', err);
        }

        // 获取当前路径
        const currentRoute = window.location.pathname;
        // 如果当前不是登录页，则跳转到登录页并带上重定向地址
        if (!currentRoute.includes('/login')) {
          window.location.href = `/login?redirect=${encodeURIComponent(currentRoute)}`;
        }
      }
      
      // 返回错误信息
      // ⚠️ 这里原来 reject 的是一个**普通对象** {status, message, data}，
      //    它没有 .response 也没有 .request，于是所有按 axios 习惯写的 catch
      //    （`error.response.data.detail` 之类，见 stores/auth.js、LoginView、
      //    RegisterView、DetectView）都拿不到真实错误 —— 用户只看到"请求失败"，
      //    DetectView 里"401 就跳登录页"的分支也永远不会触发。
      //    现在 reject 一个真正的 Error，并把 axios 原始信息挂上去，两种读法都能用。
      const errorData = error.response.data || {};
      const message =
        errorData.detail || errorData.message || errorData.error || t('msg.requestFailed');
      const wrapped = new Error(message);
      wrapped.status = error.response.status;
      wrapped.data = errorData;
      wrapped.response = error.response;  // 兼容 error.response.data.xxx 的既有写法
      wrapped.request = error.request;
      wrapped.originalError = error;
      return Promise.reject(wrapped);
    } else {
      const wrapped = new Error(t('msg.networkError'));
      wrapped.status = 0;
      wrapped.data = error;
      wrapped.request = error?.request;
      wrapped.originalError = error;
      return Promise.reject(wrapped);
    }
  }
);

export default service;
