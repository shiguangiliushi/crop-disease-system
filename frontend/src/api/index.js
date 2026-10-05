import axios from 'axios';
// 身份读写统一走适配器（sessionStorage 优先），避免各客户端各自读 localStorage 而读串账号
import { getToken, clearIdentity } from '@/utils/authStorage';
// 说明：原先这里还 import 了 @/router 与 element-plus 的 ElMessage，
// 但它们只被那套"从未安装的响应拦截器"使用（负责 401 跳转与错误弹窗）。
// 那套代码已删除，这两个依赖也随之移除 —— 本模块不再牵扯整个路由树与 Element Plus。

// 创建axios实例
// 确保baseURL以/结尾，这样在拼接路径时不会出现问题
// 注意：兜底值必须带 /api 前缀，与 http.js / utils/axios.js / main.js 保持一致。
// 原来兜底是 'http://127.0.0.1:8000'（少 /api），而仓库只有 .env.development；
// production 构建不会加载它，于是所有请求会打到 .../news/ 这类缺 /api 的地址 → 404。
const baseURL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api').replace(/\/+$/, '') + '/';

const apiClient = axios.create({
  baseURL: baseURL,
  timeout: 30000, // 请求超时时间30秒
  withCredentials: true, // 跨域请求时发送cookies
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  // 第 16 批修复：原先这里是 `status >= 200 && status < 500`，
  // 即 **400/401/403/404/429 全部被当成"请求成功"**。后果是真实的失败被静默吞掉：
  //   - 评论被限流（400「操作过于频繁」）→ createComment 拿到错误体，`!newComment`
  //     不成立，界面照样提示"评论发表成功"；
  //   - 401/403 走不到任何 catch 分支，DetectView / HistoryView / UserProfileView
  //     里按 `error.response.status` 写的提示与跳转全部不可达。
  // 现恢复 axios 默认语义：仅 2xx 成功，其余走 reject（错误对象由调用方 catch）。
  validateStatus: function (status) {
    return status >= 200 && status < 300;
  }
});

// 确保请求URL不以//开头
apiClient.interceptors.request.use(config => {
  if (config.url) {
    config.url = config.url.replace(/^\/+/, '');
  }
  return config;
});

// 添加请求拦截器
apiClient.interceptors.request.use(config => {
  const token = getAuthToken();
  if (token) {
    config.headers.Authorization = `Token ${token}`;
  }
  
  // 为每个请求添加时间戳防止缓存
  if (config.method === 'get') {
    config.params = {
      ...config.params,
      _t: new Date().getTime()
    };
  }
  
  // 第 16 批：这里原来会 `console.log(..., config)`，而 config.headers 里已经带上
  // `Authorization: Token xxxx`（上一个请求拦截器刚写入）→ **每次请求都把登录令牌
  // 打进浏览器控制台**，属于凭证泄露，且日志量极大。现只记录方法+路径。
  if (import.meta.env.DEV) {
    console.debug(`[API] ${String(config.method).toUpperCase()} ${config.url}`);
  }
  return config;
}, error => {
  console.error('[API Request Error]', error);
  return Promise.reject(error);
});

// 说明：原有一个 getCSRFToken() 辅助函数，只被上面提到的、从未安装的拦截器使用，
// 随该拦截器一并删除。CSRF 仍由本实例的 xsrfCookieName/xsrfHeaderName 配置
// （axios 会自动读 csrftoken cookie 并写入 X-CSRFToken 头）处理。

// 从存储获取token（统一走适配器：sessionStorage 优先，localStorage 兜底）
const getAuthToken = () => getToken();

// 说明：此处原先还有一整套"可安装的拦截器"（setupRequestInterceptor /
// setupResponseInterceptor / setupInterceptors），它们会在安装时把响应**解包**成
// response.data、对 204 返回 {success:true}、并接管错误中文文案与 401 跳转。
// 但全项目**没有任何地方调用 setupInterceptors**（已 grep 确认，只有定义与导出），
// 所以这套解包逻辑从未生效 —— 也就是说 api.get()/api.post() 实际返回的是完整
// AxiosResponse（8 个调用方正是按这个形状写的）。
// 危险点在于：一旦有人调用这个公开导出的 setupInterceptors()，那 8 个调用方会集体失效。
// 本轮直接删除这套死代码，把"返回 AxiosResponse"确立为 api/index.js 的正式契约。

// 清除认证信息（两个存储一起清，避免"退出后新标签页又是登录态"）
const clearAuth = () => {
  clearIdentity();
};


// 导出API方法
const api = {
  // 原始axios实例
  axios: apiClient,
  
  // 通用请求方法
  request(config) {
    return apiClient.request(config);
  },
  
  // GET请求
  // ⚠️ 已修复的真实缺陷：这里原来是 get(url, params = {}, config = {})，
  //    内部再拼成 apiClient.get(url, { ...config, params })。
  //    但**全部 16 个调用点都是按 axios 约定写的**，第二个参数传的是 config
  //    （例如 api.get('/detection-history/', { params: { page: 1 } })），
  //    于是被多包了一层，真实请求变成 `?params[page]=1`，
  //    后端只认 `page`/`page_size`/`all_users` 等 → **分页与筛选全部静默失效**。
  //    现在直接把 config 透传给 axios（与 post/put/patch/delete 的写法一致）。
  get(url, config = {}) {
    // 确保 url 不以 / 开头
    const cleanUrl = url.startsWith('/') ? url.substring(1) : url;
    return apiClient.get(cleanUrl, config);
  },
  
  // POST请求
  post(url, data = {}, config = {}) {
    const cleanUrl = url.startsWith('/') ? url.substring(1) : url;
    return apiClient.post(cleanUrl, data, config);
  },
  
  // PUT请求
  put(url, data = {}, config = {}) {
    const cleanUrl = url.startsWith('/') ? url.substring(1) : url;
    return apiClient.put(cleanUrl, data, config);
  },
  
  // PATCH请求
  patch(url, data = {}, config = {}) {
    const cleanUrl = url.startsWith('/') ? url.substring(1) : url;
    return apiClient.patch(cleanUrl, data, config);
  },
  
  // DELETE请求
  delete(url, config = {}) {
    const cleanUrl = url.startsWith('/') ? url.substring(1) : url;
    return apiClient.delete(cleanUrl, config);
  },
  
  // 上传文件
  upload(url, file, config = {}) {
    const formData = new FormData();
    formData.append('file', file);
    const cleanUrl = url.startsWith('/') ? url.substring(1) : url;
    
    return apiClient.post(cleanUrl, formData, {
      ...config,
      headers: {
        'Content-Type': 'multipart/form-data',
        ...config.headers,
      },
    });
  },
  
  // 工具方法（setupInterceptors 已删除，见上方说明；它从未被调用过）
  clearAuth,
  getAuthToken,
  
  // 获取当前axios实例
  getInstance() {
    return apiClient;
  }
};

// 导出默认实例和命名导出
export default api;

// 导出工具方法
export {
  clearAuth,
  getAuthToken
};
