import { useUserStore } from '@/stores/user';

// 检查用户是否已登录
export function isAuthenticated() {
  const userStore = useUserStore();
  return userStore.isAuthenticated;
}

// 检查用户是否有特定角色
export function hasRole(role) {
  const userStore = useUserStore();
  if (!userStore.user) return false;
  return userStore.user.roles?.includes(role) || false;
}

// 检查用户是否有任一指定角色
export function hasAnyRole(roles = []) {
  if (!Array.isArray(roles)) return false;
  const userStore = useUserStore();
  if (!userStore.user?.roles) return false;
  return roles.some(role => userStore.user.roles.includes(role));
}

// 检查用户是否有所有指定角色
export function hasAllRoles(roles = []) {
  if (!Array.isArray(roles)) return false;
  const userStore = useUserStore();
  if (!userStore.user?.roles) return false;
  return roles.every(role => userStore.user.roles.includes(role));
}

// 检查用户是否是资源所有者
export function isOwner(userId) {
  const userStore = useUserStore();
  if (!userStore.user) return false;
  return userStore.user.id === userId;
}

// 检查用户是否有权限编辑帖子
export function canEditPost(post) {
  const userStore = useUserStore();
  if (!userStore.user) return false;
  
  // 管理员可以编辑任何帖子
  if (userStore.user.roles?.includes('admin')) return true;
  
  // 版主可以编辑自己版块的帖子
  if (userStore.user.roles?.includes('moderator') && 
      post.board?.moderators?.includes(userStore.user.id)) {
    return true;
  }
  
  // 用户只能编辑自己的帖子
  return isOwner(post.author?.id);
}

// 检查用户是否有权限删除帖子
export function canDeletePost(post) {
  const userStore = useUserStore();
  if (!userStore.user) return false;
  
  // 管理员可以删除任何帖子
  if (userStore.user.roles?.includes('admin')) return true;
  
  // 版主可以删除自己版块的帖子
  if (userStore.user.roles?.includes('moderator') && 
      post.board?.moderators?.includes(userStore.user.id)) {
    return true;
  }
  
  // 用户只能删除自己的帖子
  return isOwner(post.author?.id);
}

// 检查用户是否有权限管理版块
export function canManageBoard(board) {
  const userStore = useUserStore();
  if (!userStore.user) return false;
  
  // 管理员可以管理所有版块
  if (userStore.user.roles?.includes('admin')) return true;
  
  // 版主可以管理自己负责的版块
  if (userStore.user.roles?.includes('moderator') && 
      board?.moderators?.includes(userStore.user.id)) {
    return true;
  }
  
  return false;
}

// 路由守卫：需要登录
export function requireAuth(to, from, next) {
  if (isAuthenticated()) {
    next();
  } else {
    next({
      name: 'login',
      query: { redirect: to.fullPath }
    });
  }
}

// 路由守卫：需要角色
export function requireRole(roles) {
  return (to, from, next) => {
    if (hasAnyRole(roles)) {
      next();
    } else {
      next({ name: 'forbidden' });
    }
  };
}

export default {
  isAuthenticated,
  hasRole,
  hasAnyRole,
  hasAllRoles,
  isOwner,
  canEditPost,
  canDeletePost,
  canManageBoard,
  requireAuth,
  requireRole
};
