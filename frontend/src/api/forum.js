import api from '@/api';
import axios from 'axios';
// 本文件的 editComment / getCommentReplies / likeComment 是按 AxiosResponse 写的
// （结尾都有 .then(res => res.data)），但此前整个文件从未导入 http，
// 调用它们会直接抛 ReferenceError: http is not defined。
import http from './http';
import { useAuthStore } from '@/stores/auth';
// 第 64 批：API 层的兜底文案也走多语言（用全局 t，读取当前语言）
import { t as translate } from '@/i18n';

// 配置项
const API_CONFIG = {
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 60000, // 60秒超时
  headers: {
    'Content-Type': 'multipart/form-data',
  },
};



/**
 * 版块相关API
 */
/**
 * 停用 / 启用一个版块（第 140 批，管理端「版块管理」页用）
 *
 * 接口早就有（`boards/<id>/set_status/`），但控制台一直没有入口 ——
 * 本批补页面时把它接上（第 138 批接口可达性审计里"界面没调用"的两条之一）。
 *
 * ⚠️ 停用会直接影响农户端论坛：`BoardViewSet.get_queryset` 对普通用户只返回
 * 启用的版块，所以停用后农户端**看不到**该版块，而版块管理者仍看得到（才能再开回来）。
 *
 * @param {number} boardId
 * @param {boolean} isActive
 */
export function setForumBoardStatus(boardId, isActive) {
  return http.post(`/forums/boards/${boardId}/set_status/`, { is_active: isActive })
    .then((res) => res.data);
}

/**
 * 批量更新版块排序（第 140 批）
 *
 * 接口要的是**完整的一份顺序**：`{orders: [{id, order}, ...]}` ——
 * 所以界面上移/下移后重新编号整份列表再一次提交。
 *
 * @param {{id:number, order:number}[]} orders
 */
export function updateForumBoardOrder(orders) {
  return http.post('/forums/boards/update_order/', { orders }).then((res) => res.data);
}

// 获取所有版块列表
/**
 * 获取所有版块列表
 * @returns {Promise<Array>} 返回版块列表
 */
export function getForumBoards() {
  return axios.get(`/forums/boards/`, {
    // 添加响应拦截器处理编码问题
    transformResponse: [function (data) {
      if (typeof data === 'string') {
        try {
          // 处理可能的编码问题
          const decoder = new TextDecoder('utf-8');
          const encoder = new TextEncoder();
          const uint8Array = encoder.encode(data);
          const decodedString = decoder.decode(uint8Array);
          const parsedData = JSON.parse(decodedString);
          
          // 确保返回的数据是数组
          if (Array.isArray(parsedData)) {
            return parsedData;
          } else if (parsedData && Array.isArray(parsedData.results)) {
            return parsedData.results;
          }
          return parsedData;
        } catch (e) {
          console.error('解析版块数据失败:', e);
          return [];
        }
      }
      return data;
    }]
  }).then(response => response.data);
}

/**
 * 获取单个版块详情
 * @param {string|number} boardId - 版块ID
 * @returns {Promise<Object>} 返回版块详情
 */
export function getBoardDetail(boardId) {
  return axios.get(`/forums/boards/${boardId}/`)
  .then(response => {
    // 处理标准响应格式
    if (response && response.data) {
      // 如果返回的是分页结果，提取第一个结果
      if (response.data.results && Array.isArray(response.data.results) && response.data.results.length > 0) {
        return response.data.results[0];
      }
      return response.data;
    }
    return response;
  })
  .catch(error => {
    console.error('获取版块详情失败:', error);
    // 如果错误响应中有数据，直接返回以便上层处理
    if (error.response && error.response.data) {
      return Promise.reject(error.response.data);
    }
    return Promise.reject(error);
  });
}

/**
 * 帖子相关API
 */
// 获取帖子列表
export function getPosts(params = {}) {
  // 处理参数，将 board 重命名为 board_id
  const requestParams = { ...params };
  
  // 如果传入了 board 参数，将其重命名为 board_id
  if (requestParams.board !== undefined) {
    requestParams.board_id = Number(requestParams.board);
    delete requestParams.board;
  }
  
  // 确保 board_id 是数字
  if (requestParams.board_id) {
    requestParams.board_id = Number(requestParams.board_id);
  }
  
  // 添加时间戳防止缓存
  requestParams._t = new Date().getTime();
  
  // 添加详细的调试日志
  console.log('getPosts 请求参数:', JSON.stringify(requestParams, null, 2));
  
  // 使用正确的URL路径，不需要加/api前缀，因为axios实例已经配置了baseURL
  return axios.get('/forums/posts/', { params: requestParams })
    .then(response => {
      console.log('getPosts 响应数据:', response.data);
      const responseData = response.data;
      
      // 处理标准分页响应
      if (responseData && responseData.results) {
        return {
          results: responseData.results,
          count: responseData.count || responseData.results.length,
          ...responseData // 保留其他分页信息
        };
      }
      
      // 处理直接返回数组的情况
      if (Array.isArray(responseData)) {
        return { 
          results: responseData, 
          count: responseData.length 
        };
      }
      
      console.warn('意外的API响应格式，返回空结果:', responseData);
      return { results: [], count: 0 };
    })
    .catch(error => {
      console.error('获取帖子列表出错:', {
        message: error.message,
        response: error.response,
        request: error.request,
        config: error.config
      });
      throw error;
    });
}

// 获取热门帖子
export function getHotPosts(limit = 10) {
  console.log('获取热门帖子，数量:', limit);
  return axios.get(`/forums/posts/hot/`, { params: { limit } })
  .then(response => {
    console.log('热门帖子API响应:', {
      status: response.status,
      data: response.data,
      headers: response.headers
    });
    const responseData = response.data;
    // 确保返回的数据格式一致
    if (Array.isArray(responseData)) {
      return responseData;
    } else if (responseData && Array.isArray(responseData.results)) {
      return responseData.results;
    }
    console.warn('意外的API响应格式:', responseData);
    return [];
  }).catch(error => {
    console.error('获取热门帖子失败:', error);
    throw error;
  });
}

// 获取帖子详情
export function getPost(postId) {
  console.log(`获取帖子详情，ID: ${postId}`);
  return api.get(`/forums/posts/${postId}/`).then(res => {
    console.log('帖子详情响应:', res.data);
    return res.data;
  }).catch(error => {
    console.error('获取帖子详情失败:', error);
    if (error.response) {
      console.error('响应数据:', error.response.data);
    }
    throw error;
  });
}

// 创建帖子
export function createPost(data) {
  console.log('准备发送的帖子数据:', JSON.stringify(data, null, 2));
  
  return api.post(`/forums/posts/`, data).then(res => res.data);
}

// 更新帖子
export function updatePost(postId, data) {
  return api.put(`/forums/posts/${postId}/`, data).then(res => res.data);
}

// 删除帖子
export function deletePost(postId) {
  return api.delete(`/forums/posts/${postId}/`).then(res => res.data);
}

// 增加帖子浏览数
export function incrementPostView(postId) {
  return api.post(`/forums/posts/${postId}/view/`).then(res => res.data);
}

/**
 * 收藏 / 取消收藏帖子（同一个接口切换）
 * 第 24 批接入：后端 `POST /forums/posts/{id}/favorite/` 一直存在，
 * 但前端从未调用过 —— 收藏模型、接口都有，界面上却完全没有这个功能。
 * @returns {Promise<{status: string, is_favorited: boolean}>}
 */
export function toggleFavorite(postId) {
  return api.post(`/forums/posts/${postId}/favorite/`).then(res => res.data);
}

/** 我的收藏（当前用户收藏过的帖子） */
export function getFavoritePosts(params = {}) {
  return getPosts({
    ...params,
    favorited: 'true',
  });
}

/**
 * 某个用户发表的评论（用户资料页「评论」标签）—— 第 25 批新增
 * 每条评论都带 post_id / post_title / board_name，用于显示"发在哪里"
 */
export function getUserComments(userId, params = {}) {
  const userIdNum = parseInt(userId, 10);
  return axios.get(`/users/${userIdNum}/comments/`, {
    params: { page: 1, page_size: 10, ...params },
  }).then((response) => {
    const data = response.data || {};
    return {
      results: Array.isArray(data.results) ? data.results : (Array.isArray(data) ? data : []),
      count: data.count || 0,
    };
  });
}

/**
 * 谁点赞了这条帖子 —— 第 25 批新增
 * 说明：原来的 LikeViewSet 只能查"我赞过什么"，无法反查"被谁赞过"。
 */
export function getPostLikers(postId, params = {}) {
  return axios.get(`/forums/posts/${postId}/likes/`, {
    params: { page_size: 50, ...params },
  }).then((response) => response.data);
}

/** 谁点赞了这条评论 —— 第 25 批新增 */
export function getCommentLikers(postId, commentId, params = {}) {
  return axios.get(`/forums/posts/${postId}/comments/${commentId}/likes/`, {
    params: { page_size: 50, ...params },
  }).then((response) => response.data);
}

/**
 * 评论相关API
 */
// 获取评论列表
export function getComments(postId, params = {}) {
  // 确保 postId 是数字
  const postIdNum = parseInt(postId, 10);
  
  // 构建请求参数
  const requestParams = {
    page: params.page || 1,
    page_size: params.page_size || 10, // 默认每页10条
    ordering: params.ordering || '-created_at',
    parent__isnull: params.parent__isnull, // 是否只获取顶级评论
    _t: Date.now(), // 添加时间戳防止缓存
  };
  
  // 过滤掉未定义的参数
  Object.keys(requestParams).forEach(key => {
    if (requestParams[key] === undefined) {
      delete requestParams[key];
    }
  });
  
  console.log(`获取帖子 ${postIdNum} 的评论，参数:`, requestParams);
  
  return api.get(`/forums/posts/${postIdNum}/comments/`, { 
    params: requestParams
  }).then(response => {
    const data = response.data;
    console.log('评论API响应数据:', {
      count: data.count,
      next: data.next,
      results: data.results ? translate('common.totalItems', { count: data.results.length }) : translate('forum.noResult')
    });
    
    // 确保返回标准分页格式
    return {
      results: data.results || [],
      count: data.count || 0,
      next: data.next,
      previous: data.previous,
      currentPage: data.current_page || parseInt(requestParams.page, 10),
      totalPages: Math.ceil((data.count || 0) / (requestParams.page_size || 10))
    };
  }).catch(error => {
    console.error('获取评论失败:', error);
    if (error.response) {
      console.error('响应数据:', error.response.data);
      console.error('响应状态:', error.response.status);
    } else if (error.request) {
      console.error('请求已发送但无响应:', error.request);
    } else {
      console.error('请求设置错误:', error.message);
    }
    throw error;
  });
}

// 创建评论
export function createComment(postId, data, config = {}) {
  // 确保headers存在
  config.headers = config.headers || {};
  
  // 确保withCredentials为true以发送cookies
  config.withCredentials = true;
  
  // 添加认证token
  const authStore = useAuthStore();
  if (authStore.authToken) {
    config.headers['Authorization'] = `Token ${authStore.authToken}`;
  }
  
  console.log(`Sending comment to /forums/posts/${postId}/comments/ with config:`, config);
  
  return api.post(`/forums/posts/${postId}/comments/`, data, config)
    .then(res => res.data)
    .catch(error => {
      console.error('Error creating comment:', error);
      if (error.response) {
        // 服务器返回了错误响应
        console.error('Error response data:', error.response.data);
        console.error('Error status:', error.response.status);
        console.error('Error headers:', error.response.headers);
      } else if (error.request) {
        // 请求已发送但未收到响应
        console.error('No response received:', error.request);
      } else {
        // 请求设置出错
        console.error('Error setting up request:', error.message);
      }
      throw error; // 重新抛出错误，让调用者处理
    });
}

// 删除评论
export function deleteComment(postId, commentId) {
  console.log(`正在删除帖子 ${postId} 的评论，ID: ${commentId}`);
  // 契约对齐：后端 DELETE（DRF destroy）是"**仅管理员**硬删除"，
  // 普通用户删自己的评论会被 403（"只有管理员可以硬删除评论"），界面上的删除按钮等于失效。
  // 作者/版主软删除的入口是自定义 action：POST .../comments/{id}/delete/（返回 204）。
  return api.post(`/forums/posts/${postId}/comments/${commentId}/delete/`, {}).then(res => {
    console.log('评论删除成功:', res.data);
    return res.data;
  }).catch(error => {
    console.error('删除评论失败:', error);
    if (error.response) {
      console.error('响应数据:', error.response.data);
      console.error('状态码:', error.response.status);
    }
    throw error;
  });
}

/**
 * 更新评论
 * 说明：原来是 axios.patch(`/forums/posts/comments/${commentId}/`)，路径缺少帖子 ID 且顺序错误，
 * 而调用方 PostDetailView 传的是 (postId, commentId, data)，参数也完全错位。现统一为嵌套路由。
 * @param {number} postId - 帖子ID
 * @param {number} commentId - 评论ID
 * @param {Object} data - 更新的评论数据
 */
export function updateComment(postId, commentId, data) {
  return http.patch(`/forums/posts/${postId}/comments/${commentId}/`, data).then(res => res.data);
}

/**
 * 获取评论的回复列表
 * @param {number} postId - 帖子ID
 * @param {number} commentId - 评论ID
 * @param {Object} params - 查询参数
 */
export function getCommentReplies(postId, commentId, params = {}) {
  return http.get(`/forums/posts/${postId}/comments/${commentId}/replies/`, { params })
    .then(response => {
      const payload = response.data;
      if (payload && Array.isArray(payload.results)) {
        return {
          results: payload.results,
          count: payload.count || payload.results.length,
          next: payload.next,
          previous: payload.previous
        };
      }
      if (Array.isArray(payload)) {
        return { results: payload, count: payload.length, next: null, previous: null };
      }
      return { results: [], count: 0, next: null, previous: null };
    });
}

/**
 * 第 85 批：按需翻译帖子（英文界面下"立即翻译"按钮用）
 *
 * 后端会调翻译服务并把译文写库，返回 `{ title_en, content_en, translation_* }`。
 * 与"发帖时自动翻译"是同一套逻辑，只是由读者手动触发 —— 用于补历史帖子、
 * 或自动翻译当时失败（额度/网络）的情况。
 * @param {number} postId
 */
export function translatePost(postId) {
  return http.post(`/forums/posts/${postId}/translate/`).then(res => res.data);
}

/**
 * 第 85 批：按需翻译评论/回复
 * @param {number} postId
 * @param {number} commentId
 */
export function translateComment(postId, commentId) {
  return http.post(`/forums/posts/${postId}/comments/${commentId}/translate/`).then(res => res.data);
}

/**
 * 评论点赞 / 取消点赞
 * @param {number} postId - 帖子ID
 * @param {number} commentId - 评论ID
 */
export function toggleCommentLike(postId, commentId) {
  return http.post(`/forums/posts/${postId}/comments/${commentId}/like/`).then(res => res.data);
}

/**
 * 点赞相关API
 */
// 点赞/取消点赞
// 参数兼容：调用方原先传的是 {content_type, object_id}，而这里只读 data.post，
// 于是 Number(undefined) → NaN，请求打到 /forums/posts/NaN/like/ 必然失败。
export function toggleLike(data) {
  const postId = Number(data.post ?? data.object_id);
  if (!postId || Number.isNaN(postId)) {
    return Promise.reject(new Error(translate('msg.operationFailed')));
  }
  return axios.post(`/forums/posts/${postId}/like/`, {}, {
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'
    },
    withCredentials: true  // 确保发送cookies
  }).then(res => {
    console.log('点赞响应:', res.data);
    return res.data;
  }).catch(error => {
    console.error('点赞操作失败:', error);
    throw error;
  });
}

// 说明：原有一个 getLikeStatus()，请求 `/forums/likes/status/`，
// 但后端 likes 只有 create/destroy（没有 status 动作），该 URL 会落到 detail 路由被当作
// pk='status' 处理；且全项目没有任何调用点。已删除。

// 评论点赞/取消点赞已在上方以嵌套路由实现（toggleCommentLike(postId, commentId)）

/**
 * 获取用户资料
 * @param {number} userId - 用户ID
 * @returns {Promise<Object>} 返回用户资料
 */
export function getUserProfile(userId) {
  // 确保userId是数字
  const userIdNum = parseInt(userId, 10);

  console.log(`正在获取用户资料，用户ID: ${userIdNum}`);

  // 第 23 批修复：原实现把两个请求的错误**全部吞掉**，外层 catch 还会返回一个
  // **编造出来的用户**（username = `用户{id}`），于是：
  //   · 访问不存在的用户 → 页面显示一个假资料，`用户不存在` 的分支成了死代码；
  //   · 真实故障（401/500/断网）→ 同样被伪装成"用户 0 帖子"的正常页面。
  // 现在：资料请求如实抛出（404 让页面提示"用户不存在"），
  // 只有统计数据允许降级为 0 —— 统计失败不该让整页不可用。
  const userInfoRequest = axios.get(`/users/${userIdNum}/`);
  const statsRequest = axios
    .get(`/users/${userIdNum}/stats/`)
    .catch(error => {
      console.warn('获取用户统计数据失败，统计暂显示为 0', error);
      return { data: { post_count: 0, comment_count: 0, like_count: 0 } };
    });

  return Promise.all([userInfoRequest, statsRequest])
  .then(([userInfo, userStats]) => {
    const info = userInfo.data || {};
    const userData = {
      ...info,
      ...userStats.data,
      // 确保有必要的字段
      id: info.id || userIdNum,
      username: info.username || `${translate('profile.defaultUser')}${userIdNum}`,
      avatar: info.avatar || '',
      bio: info.bio || translate('profile.noBioYet'),
      // 确保有 date_joined 和 join_date 字段
      date_joined: info.date_joined || info.join_date || new Date().toISOString(),
      join_date: info.join_date || info.date_joined || new Date().toISOString(),
      // 设置统计信息
      post_count: userStats.data.post_count || 0,
      comment_count: userStats.data.comment_count || 0,
      like_count: userStats.data.like_count || 0,
    };

    console.log('返回的用户数据:', userData);
    return userData;
  });
}

/**
 * 上传 / 替换头像（仅本人或管理员）
 * @param {number} userId
 * @param {File} file
 * @returns {Promise<Object>} 更新后的用户资料（含 avatar 绝对地址）
 */
export function uploadAvatar(userId, file) {
  const formData = new FormData();
  formData.append('avatar', file);
  return http.post(`/users/${parseInt(userId, 10)}/avatar/`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(res => res.data);
}

/**
 * 删除头像（恢复为"无头像"，前端用用户名首字母兜底）
 */
export function deleteAvatar(userId) {
  return http.delete(`/users/${parseInt(userId, 10)}/avatar/`).then(res => res.data);
}

/**
 * 修改密码（仅本人）
 * @param {number} userId
 * @param {{oldPassword: string, newPassword: string}} payload
 * @returns {Promise<Object>} { status, message, token } —— token 是轮换后的新令牌
 */
export function changePassword(userId, { oldPassword, newPassword }) {
  return http.post(`/users/${parseInt(userId, 10)}/password/`, {
    old_password: oldPassword,
    new_password: newPassword,
  }).then(res => res.data);
}

/**
 * 获取用户发布的帖子
 * @param {number} userId - 用户ID
 * @param {Object} params - 查询参数
 * @returns {Promise<Array>} 返回用户发布的帖子列表
 */
/**
 * 获取当前登录用户自己的帖子
 * @param {Object} params - 查询参数
 * @returns {Promise<Object>} 返回当前用户的帖子列表
 */
export function getMyPosts(params = {}) {
  // 设置默认参数
  const defaultParams = {
    page: 1,
    page_size: 10,
    ordering: '-created_at',
    _t: Date.now() // 防止缓存
  };
  
  // 合并参数
  const requestParams = { ...defaultParams, ...params };
  
  console.log('获取当前用户的帖子，参数:', requestParams);
  
  // 使用专门获取当前用户帖子的API
  // 注意：这里直接传递 params 对象，axios 会自动处理参数编码
  return axios.get('/users/me/posts/', { 
    params: requestParams,
    // 添加这个配置，确保参数正确序列化
    paramsSerializer: params => {
      return Object.entries(params)
        .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
        .join('&');
    }
  })
    .then(response => {
      console.log('当前用户帖子API响应:', response.data);
      // 处理标准分页响应
      if (response.data && (response.data.results !== undefined || response.data.count !== undefined)) {
        return {
          results: Array.isArray(response.data.results) ? response.data.results : [],
          count: response.data.count || 0,
          ...response.data // 保留其他分页信息
        };
      }
      
      // 处理直接返回数组的情况
      if (Array.isArray(response.data)) {
        return { results: response.data, count: response.data.length };
      }
      
      console.warn('意外的API响应格式，返回空结果:', response.data);
      return { results: [], count: 0 };
    })
    .catch(error => {
      console.error('获取当前用户帖子失败:', error);
      if (error.response) {
        console.error('响应数据:', error.response.data);
        console.error('响应状态:', error.response.status);
      }
      
      // 如果获取失败，返回空结果
      return { results: [], count: 0 };
    });
}

/**
 * 获取指定用户发布的帖子（公开可见）
 * @param {number} userId - 用户ID
 * @param {Object} params - 查询参数
 * @returns {Promise<Array>} 返回用户发布的帖子列表
 */
export function getUserPosts(userId, params = {}) {
  // 确保userId是数字
  const userIdNum = parseInt(userId, 10);
  
  // 设置默认参数
  const defaultParams = {
    author: userIdNum,  // 添加作者过滤参数
    page: 1,
    page_size: 10,
    ordering: '-created_at',
    _t: Date.now() // 防止缓存
  };
  
  // 合并参数
  const requestParams = { ...defaultParams, ...params };
  
  console.log(`获取用户 ${userIdNum} 的帖子，参数:`, requestParams);
  
  // 使用论坛帖子的API，通过author参数过滤
  return axios.get('/forums/posts/', { params: requestParams })
    .then(response => {
      console.log('用户帖子API响应:', response.data);
      // 处理标准分页响应
      if (response.data && (response.data.results !== undefined || response.data.count !== undefined)) {
        return {
          results: Array.isArray(response.data.results) ? response.data.results : [],
          count: response.data.count || 0,
          ...response.data // 保留其他分页信息
        };
      }
      
      // 处理直接返回数组的情况
      if (Array.isArray(response.data)) {
        return { results: response.data, count: response.data.length };
      }
      
      console.warn('意外的API响应格式，返回空结果:', response.data);
      return { results: [], count: 0 };
    })
    .catch(error => {
      console.error('获取用户帖子失败:', error);
      if (error.response) {
        console.error('响应数据:', error.response.data);
        console.error('响应状态:', error.response.status);
      }
      
      // 如果获取失败，返回空结果
      return { results: [], count: 0 };
    });
}


/**
 * 上传图片
 * @param {FormData} formData - 包含图片文件的FormData对象
 * @returns {Promise<Object>} 返回上传结果，包含图片URL
 */
export function uploadImage(formData) {
  return axios.post(`/upload/image/`, formData, {
    ...API_CONFIG,
    onUploadProgress: (progressEvent) => {
      // 可以在这里添加上传进度处理
      const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
      console.log(`Upload progress: ${percentCompleted}%`);
    },
    // 必须解包：调用方（EditPostView）拿的是响应体 `{url, image_url, message}`，
    // 原来直接返回 AxiosResponse 导致 `response.url` 恒为 undefined ——
    // 图片其实已上传成功，但 base64 永远不被替换、并误报"上传失败"。
  }).then(res => res.data);
}

