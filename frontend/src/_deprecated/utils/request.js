import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

// 创建axios实例
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
  timeout: 10000, // 请求超时时间
  withCredentials: true // 允许携带cookie
})

// 请求拦截器
service.interceptors.request.use(
  config => {
    const authStore = useAuthStore()
    
    // 添加认证token
    if (authStore.token) {
      config.headers['Authorization'] = `Token ${authStore.token}`
    }
    
    // 添加CSRF token
    const csrfToken = document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1];
    if (csrfToken) {
      config.headers['X-CSRFToken'] = csrfToken;
    }
    
    // 确保URL以斜杠结尾，除非是文件扩展名
    if (config.url && !config.url.endsWith('/') && !config.url.includes('.')) {
      config.url = config.url + '/';
    }
    
    // 添加请求日志
    console.log(`[Request] ${config.method?.toUpperCase()} ${config.url}`, {
      params: config.params,
      data: config.data,
      headers: config.headers
    });
    
    return config
  },
  error => {
    console.error('Request interceptor error:', error);
    return Promise.reject(error)
  }
)

// 响应拦截器
service.interceptors.response.use(
  response => {
    const res = response.data
    
    console.log('请求成功:', {
      url: response.config.url,
      status: response.status,
      data: res
    });
    
    // 处理未授权的情况
    if (response.status === 401 || res.code === 401 || res.code === 1001) {
      const authStore = useAuthStore()
      authStore.logout()
      router.push(`/login?redirect=${router.currentRoute.value.fullPath}`)
      return Promise.reject(new Error(res.message || '未登录或登录已过期，请重新登录'))
    }
    
    // 如果响应中有code且不为200，显示错误信息
    if (res.code && res.code !== 200) {
      const errMsg = res.message || '请求失败'
      ElMessage.error(errMsg)
      return Promise.reject(new Error(errMsg))
    }
    
    // 返回响应数据
    return res
  },
  error => {
    console.error('请求错误详情:', {
      message: error.message,
      code: error.code,
      config: {
        url: error.config?.url,
        method: error.config?.method,
        data: error.config?.data,
        headers: error.config?.headers
      },
      response: {
        status: error.response?.status,
        statusText: error.response?.statusText,
        data: error.response?.data,
        headers: error.response?.headers
      },
      request: error.request,
      stack: error.stack
    });

    // 处理网络错误
    if (error.message.includes('timeout')) {
      ElMessage.error('请求超时，请检查网络连接')
    } else if (error.response) {
      // 请求已发出，但服务器响应的状态码不在 2xx 范围内
      const status = error.response.status
      const message = error.response.data?.message || '请求错误'
      const data = error.response.data
      
      // 记录完整的错误响应
      console.error('API 错误响应:', {
        status,
        message,
        data,
        headers: error.response.headers
      });
      
      switch (status) {
        case 400:
          // 显示具体的字段错误信息
          if (data) {
            const errorMessages = [];
            for (const [field, errors] of Object.entries(data)) {
              if (Array.isArray(errors)) {
                errorMessages.push(`${field}: ${errors.join(', ')}`);
              } else {
                errorMessages.push(`${field}: ${errors}`);
              }
            }
            ElMessage.error(`请求参数错误: ${errorMessages.join('; ')}`);
          } else {
            ElMessage.error(`请求参数错误: ${message}`);
          }
          break
        case 401:
          // 未授权，跳转到登录页
          const authStore = useAuthStore()
          authStore.logout()
          router.push(`/login?redirect=${router.currentRoute.value.fullPath}`)
          ElMessage.error('登录已过期，请重新登录')
          break
        case 403:
          ElMessage.error('权限不足，拒绝访问')
          break
        case 404:
          ElMessage.error('请求的资源不存在')
          break
        case 500:
          ElMessage.error(`服务器内部错误: ${message}`)
          break
        default:
          ElMessage.error(`请求失败: ${message}`)
      }
    } else {
      ElMessage.error('网络错误，请检查您的网络连接')
    }
    
    return Promise.reject(error)
  }
)

/**
 * GET 请求
 * @param {string} url - 请求地址
 * @param {object} params - 请求参数
 * @param {object} config - 其他配置
 * @returns {Promise} - 返回Promise对象
 */
export function get(url, params = {}, config = {}) {
  return service({
    method: 'get',
    url,
    params,
    ...config
  })
}

/**
 * POST 请求
 * @param {string} url - 请求地址
 * @param {object} data - 请求数据
 * @param {object} config - 其他配置
 * @returns {Promise} - 返回Promise对象
 */
export function post(url, data = {}, config = {}) {
  return service({
    method: 'post',
    url,
    data,
    ...config
  })
}

/**
 * PUT 请求
 * @param {string} url - 请求地址
 * @param {object} data - 请求数据
 * @param {object} config - 其他配置
 * @returns {Promise} - 返回Promise对象
 */
export function put(url, data = {}, config = {}) {
  return service({
    method: 'put',
    url,
    data,
    ...config
  })
}

/**
 * DELETE 请求
 * @param {string} url - 请求地址
 * @param {object} config - 其他配置
 * @returns {Promise} - 返回Promise对象
 */
export function del(url, config = {}) {
  return service({
    method: 'delete',
    url,
    ...config
  })
}

export default service
