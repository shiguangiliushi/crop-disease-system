/**
 * 登录身份的存储适配器
 *
 * ── 要解决的问题 ──
 * 浏览器里 **localStorage 是按「源」共享的**：同一站点下所有标签页共用同一份数据。
 * 原来项目把 token + user 只存在 localStorage（键名 `auth_token` / `user`），
 * 于是"整个浏览器只有一个身份"：
 *
 *   标签页 A 登录管理员 → localStorage = 管理员
 *   标签页 B 登录普通用户 → localStorage = 普通用户（把管理员那份**覆盖**了）
 *   切回标签页 A 按 F5 → 应用启动时从 localStorage 重建身份 → A 变成了普通用户
 *   （再登录回管理员 → 标签页 B 刷新又变成管理员，如此来回）
 *
 * 而 sessionStorage 是**按标签页隔离**的：每个标签页各有一份，刷新保持不变，
 * 标签页之间互不影响 —— 这正是"同一浏览器分别登录两个账号"需要的东西。
 *
 * ── 本模块的规则 ──
 *   1. 身份（token + user）写入 **sessionStorage**：标签页内刷新后身份不变；
 *   2. 同时在 localStorage 留一份**镜像**，代表"最近一次成功登录的账号"，
 *      新标签页 / 重开浏览器时用它恢复登录（保持与改动前一致的便利性）；
 *   3. 读取时 **sessionStorage 优先**，只有它为空才回退 localStorage；
 *   4. 退出登录时两个存储一起清，避免"退出后新标签页又自动是登录态"。
 *
 * 键名沿用原有取值（`auth_token` / `user`），保证已有登录态平滑过渡。
 */

export const TOKEN_KEY = 'auth_token';   // 与旧版本一致，勿随意改名
export const USER_KEY = 'user';
export const LEGACY_TOKEN_KEY = 'token'; // 历史遗留键，仅做只读兼容

/** 取存储对象；隐私模式/被禁用时访问本身就会抛错，这里统一兜住 */
function sessionStore() {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function localStore() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function read(store, key) {
  if (!store) return null;
  try {
    return store.getItem(key);
  } catch {
    return null;
  }
}

function write(store, key, value) {
  if (!store) return;
  try {
    if (value === null || value === undefined) {
      store.removeItem(key);
    } else {
      store.setItem(key, value);
    }
  } catch {
    /* 存储满/被禁用时忽略，内存态仍然可用 */
  }
}

function parseUser(raw) {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

/**
 * 读取当前身份
 * @returns {{token: string|null, user: object|null, source: 'session'|'local'|null}}
 *          source 表示这份身份是从哪个存储读到的（便于排查问题）
 */
export function getIdentity() {
  const session = sessionStore();
  const local = localStore();

  const sessionToken = read(session, TOKEN_KEY) || read(session, LEGACY_TOKEN_KEY);
  const localToken = read(local, TOKEN_KEY) || read(local, LEGACY_TOKEN_KEY);

  const token = sessionToken || localToken;
  if (!token) return { token: null, user: null, source: null };

  const source = sessionToken ? 'session' : 'local';
  let user = parseUser(read(source === 'session' ? session : local, USER_KEY));
  if (!user) {
    // 容错：token 与 user 分处两个存储（历史数据/中途改动）时也要能读到
    user = parseUser(read(source === 'session' ? local : session, USER_KEY));
  }

  return { token, user, source };
}

/** 只取 token（多数调用点只需要它） */
export function getToken() {
  return getIdentity().token;
}

/** 只取 user 对象 */
export function getStoredUser() {
  return getIdentity().user;
}

/**
 * 保存身份：sessionStorage 为主，localStorage 作为"最近登录账号"的镜像
 * @param {{token: string|null, user: object|null}} identity
 */
export function saveIdentity({ token = null, user = null } = {}) {
  const userJson = user ? JSON.stringify(user) : null;

  write(sessionStore(), TOKEN_KEY, token);
  write(sessionStore(), USER_KEY, userJson);

  write(localStore(), TOKEN_KEY, token);
  write(localStore(), USER_KEY, userJson);
}

/** 清除身份（两个存储都清） */
export function clearIdentity() {
  [sessionStore(), localStore()].forEach((store) => {
    write(store, TOKEN_KEY, null);
    write(store, USER_KEY, null);
    write(store, LEGACY_TOKEN_KEY, null);
  });
}

/**
 * 局部更新已保存的 user（例如用户改了昵称/邮箱）
 * 两个存储都更新，避免刷新或新标签页读到旧资料。
 * @returns {object|null} 合并后的 user；未登录时返回 null
 */
export function patchStoredUser(partial = {}) {
  const { token, user } = getIdentity();
  if (!token) return null;

  const merged = { ...user, ...partial };
  const userJson = JSON.stringify(merged);
  write(sessionStore(), USER_KEY, userJson);
  write(localStore(), USER_KEY, userJson);
  return merged;
}
