import './assets/main.css'
import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap-icons/font/bootstrap-icons.css'
// Font Awesome 图标字体改为本地引入（原来走 CDN，离线时图标会全部丢失）
import '@fortawesome/fontawesome-free/css/all.min.css'
import 'vue3-carousel/dist/carousel.css'
import 'element-plus/dist/index.css'
import 'vue-toast-notification/dist/theme-bootstrap.css';
import 'highlight.js/styles/github.css';
// 全站设计变量与主题覆盖（必须放在 Element Plus 样式之后）
import './assets/theme.css'
// Bootstrap 组件主题化（第 73 批）：把 .btn/.card/.badge 等从默认蓝改成品牌绿，
// 必须放在 theme.css 之后，才能用到其中的 --brand-* / --ink-* 令牌
import './assets/bootstrap-theme.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import setupElementPlus from './plugins/element-plus'
import ToastPlugin from 'vue-toast-notification'
// 注意：$toast 的各个方法里用到了 useToast()，但此前没有导入它，
// 于是任何一次 $toast.xxx() 都会抛 ReferenceError: useToast is not defined
// （连全局 errorHandler 自己也会跟着抛错）。
import { useToast } from 'vue-toast-notification'
import axios from 'axios'

// Font Awesome 说明：
// 项目里所有图标都通过 CSS 类使用（<i class="fas fa-*">），样式由 index.html 中的
// Font Awesome Webfont 提供；没有任何组件使用 <font-awesome-icon> 组件。
// 原来这里 library.add(fas) 会把整包 @fortawesome/free-solid-svg-icons（约 0.96MB）
// 打进产物，属于无效体积，已移除。若将来要用 SVG 图标组件，再按需 import 单个图标。

import App from './App.vue'
import router from './router'
// 第 48 批：多语言（自研极简实现，见 src/i18n/index.js）
import { locale, setLocale, t } from './i18n'
import { useAuthStore } from './stores/auth'
// 身份的读写统一走适配器（sessionStorage 优先），不要在组件/入口里直接碰 localStorage
import { getToken, clearIdentity } from './utils/authStorage'

// 配置 WebSocket 重连机制
// 配置 WebSocket 连接
const setupWebSocket = () => {
  // 只在生产环境启用 WebSocket
  if (import.meta.env.PROD && window.WebSocket) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    let reconnectTimeout;
    
    const connectWebSocket = () => {
      try {
        const ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
          console.log('WebSocket connected');
          reconnectAttempts = 0; // 重置重连次数
        };
        
        ws.onclose = (e) => {
          console.log(`WebSocket disconnected: ${e.code} ${e.reason}`);
          
          // 指数退避重连
          if (reconnectAttempts < maxReconnectAttempts) {
            const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
            console.log(`Reconnecting in ${delay}ms...`);
            reconnectTimeout = setTimeout(connectWebSocket, delay);
            reconnectAttempts++;
          } else {
            console.warn('Max reconnection attempts reached, giving up');
          }
        };
        
        ws.onerror = (err) => {
          console.error('WebSocket error:', err);
          ws.close();
        };
        
        return ws;
      } catch (err) {
        console.error('WebSocket connection error:', err);
        return null;
      }
    };
    
    // 初始连接
    window.ws = connectWebSocket();
    
    // 清理函数
    return () => {
      if (window.ws) {
        window.ws.close();
        window.ws = null;
      }
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
    };
  } else {
    console.log('WebSocket is disabled in development mode');
    return () => {}; // 返回空清理函数
  }
};

// 创建应用实例
const app = createApp(App);
const pinia = createPinia();

// 配置 axios 默认头
axios.defaults.withCredentials = true;
// 注意：原来这里写的是 VITE_APP_API_BASE_URL（多了一个 APP），该变量在任何 .env 里
// 都不存在，于是全局 axios 一直悄悄回退到 http://localhost:8000/api；
// 而其余客户端（api/http.js 等）用的是 127.0.0.1，等于同一个后端被当成两个源。
axios.defaults.baseURL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

// 请求拦截器
axios.interceptors.request.use(
  config => {
    const token = getToken();
    if (token) {
      config.headers['Authorization'] = `Token ${token}`;
    }
    if (!config.headers['Content-Type']) {
      config.headers['Content-Type'] = 'application/json';
    }
    return config;
  },
  error => {
    return Promise.reject(error);
  }
);

// 响应拦截器
axios.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      clearIdentity();
      if (router.currentRoute.value.path !== '/login') {
        router.push({ 
          path: '/login',
          query: { redirect: router.currentRoute.value.fullPath }
        });
      }
    }
    return Promise.reject(error);
  }
);

// 设置全局属性
app.config.globalProperties.$http = axios;

// 第 48 批：多语言。把 `$t` 挂到全局属性，模板里可直接 {{ $t('nav.home') }}；
// 组件内更推荐用 `useI18n()`（响应式，且便于测试）。
app.config.globalProperties.$t = t;
app.config.globalProperties.$setLocale = setLocale;
app.config.globalProperties.$locale = locale;

// 使用插件
app.use(pinia);
app.use(router);
// Element Plus 按需注册（只注册项目用到的组件，避免整包进入产物）
// 组件清单与模板的对应关系由 src/plugins/element-plus.js 维护；
// 中文语言包在 App.vue 中通过 <el-config-provider :locale="zhCn"> 提供。
setupElementPlus(app);

// 使用Toast插件
const toastOptions = {
  position: 'top-right',
  duration: 3000,
  dismissible: true
};
app.use(ToastPlugin, toastOptions);

// 全局挂载 toast
app.config.globalProperties.$toast = {
  success(message) {
    const toast = useToast();
    toast.success(message, { ...toastOptions, type: 'success' });
  },
  error(message) {
    const toast = useToast();
    toast.error(message, { ...toastOptions, type: 'error' });
  },
  info(message) {
    const toast = useToast();
    toast.info(message, { ...toastOptions, type: 'info' });
  },
  warning(message) {
    const toast = useToast();
    toast.warning(message, { ...toastOptions, type: 'warning' });
  },
  show(message, type = 'success') {
    const toast = useToast();
    const options = { ...toastOptions, type };
    switch (type) {
      case 'success':
        return toast.success(message, options);
      case 'error':
        return toast.error(message, options);
      case 'info':
        return toast.info(message, options);
      case 'warning':
        return toast.warning(message, options);
      default:
        return toast.show(message, options);
    }
  }
};

// 全局错误处理
app.config.errorHandler = (err) => {
  console.error('Vue error:', err);
  if (app.config.globalProperties.$toast) {
    app.config.globalProperties.$toast.error(err.message || 'An error occurred');
  }
};

// 注册 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component);
}

// 初始化认证状态
const initAuth = async () => {
  const authStore = useAuthStore();
  const token = getToken();
  
  if (token) {
    console.log('Found auth token, checking auth status...');
    try {
      await authStore.checkAuth();
    } catch (error) {
      console.error('Auth check failed:', error);
      authStore.clearAuth();
    }
  }
};

// 挂载应用
const mountApp = async () => {
  try {
    // 确保DOM已加载
    await new Promise(resolve => {
      if (document.readyState === 'complete' || document.readyState === 'interactive') {
        resolve();
      } else {
        const onLoad = () => {
          document.removeEventListener('DOMContentLoaded', onLoad);
          window.removeEventListener('load', onLoad);
          resolve();
        };
        document.addEventListener('DOMContentLoaded', onLoad);
        window.addEventListener('load', onLoad);
      }
    });
    
    // 检查挂载点
    const appElement = document.querySelector('#app-container');
    if (!appElement) {
      throw new Error('Failed to find app container element');
    }
    
    // 初始化认证
    await initAuth();
    
    // 设置认证拦截器
    const authStore = useAuthStore();
    authStore.setupAuthInterceptors(router);
    
    // 挂载应用
    app.mount('#app-container');
    window.__app_mounted__ = true;
    console.log('App mounted successfully');
    
    // 初始化 WebSocket
    if (!window.__websocket_initialized__) {
      setupWebSocket();
      window.__websocket_initialized__ = true;
    }
    
  } catch (error) {
    console.error('Failed to mount app:', error);
    
    // 显示错误信息
    const errorDiv = document.createElement('div');
    errorDiv.style.padding = '20px';
    errorDiv.style.color = 'red';
    errorDiv.style.fontFamily = 'Arial, sans-serif';
    errorDiv.innerHTML = `
      <h2>${t('msg.bootFailedTitle')}</h2>
      <p>${error.message || t('msg.unknownError')}</p>
      <p>${t('msg.bootFailedHint')}</p>
    `;
    document.body.appendChild(errorDiv);
  }
};

// 启动应用
mountApp();

// ============================================================================
// 第 51 批：注册 Service Worker（仅生产构建）
// ----------------------------------------------------------------------------
// 只在 PROD 注册：开发环境下 Vite 的模块 URL 是动态的，SW 缓存会干扰热更新；
// 而"离线外壳"这件事本来就该在构建产物上验证（见 docs/系统完善记录.md 第五十七节）。
// ============================================================================
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js')
      .then((registration) => {
        console.log('[pwa] Service Worker 已注册:', registration.scope);
      })
      .catch((error) => {
        // 注册失败不影响正常使用，只记日志
        console.warn('[pwa] Service Worker 注册失败:', error?.message || error);
      });
  });
}