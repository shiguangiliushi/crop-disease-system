/**
 * 回归测试：登录身份的存储适配器
 *
 * 背景（真实故障）：token/user 只存 localStorage 时，"同一浏览器分别登录管理员和普通用户"
 * 会互相顶掉 —— 因为 localStorage 按「源」共享，后登录的那份覆盖先登录的，
 * 任意标签页刷新时又从 localStorage 重建身份，于是"刷新就变成另一个账号"。
 *
 * 现在：身份以 sessionStorage 为准（按标签页隔离，刷新不变），
 * localStorage 只作为"最近登录账号"的镜像供新标签页恢复。
 */
import { describe, it, expect, beforeEach } from 'vitest';
import {
  getIdentity,
  getToken,
  getStoredUser,
  saveIdentity,
  clearIdentity,
  patchStoredUser,
} from '@/utils/authStorage';

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

describe('身份存储：标签页之间不能互相顶掉', () => {
  it('本标签页（sessionStorage）优先于 localStorage 里的另一个账号', () => {
    // 模拟：另一个标签页最后登录了管理员，于是共享的 localStorage 里是管理员
    localStorage.setItem('auth_token', 'ADMIN-TOKEN');
    localStorage.setItem('user', JSON.stringify({ username: 'admin', is_staff: true }));

    // 本标签页登录的是普通用户
    saveIdentity({ token: 'USER-TOKEN', user: { username: '123456', is_staff: false } });

    // 刷新（重新读取）后必须仍然是本标签页登录的账号
    const identity = getIdentity();
    expect(identity.token).toBe('USER-TOKEN');
    expect(identity.user.username).toBe('123456');
    expect(identity.source).toBe('session');
  });

  it('新标签页（没有 sessionStorage）回退到"最近一次登录的账号"', () => {
    saveIdentity({ token: 'TOK-1', user: { username: 'someone' } });
    sessionStorage.clear(); // 模拟新开的标签页

    const identity = getIdentity();
    expect(identity.token).toBe('TOK-1');
    expect(identity.user.username).toBe('someone');
    expect(identity.source).toBe('local');
  });

  it('同一标签页内先登录 A 再登录 B，刷新后是 B（本页身份被正确覆盖）', () => {
    saveIdentity({ token: 'TOK-A', user: { username: 'a' } });
    saveIdentity({ token: 'TOK-B', user: { username: 'b' } });
    expect(getToken()).toBe('TOK-B');
    expect(getStoredUser().username).toBe('b');
  });

  it('退出登录时两个存储一起清（新标签页不应又是登录态）', () => {
    saveIdentity({ token: 'TOK-1', user: { username: 'someone' } });
    clearIdentity();
    sessionStorage.clear(); // 模拟退出后新开的标签页

    expect(getToken()).toBeNull();
    expect(getIdentity().user).toBeNull();
    expect(localStorage.getItem('auth_token')).toBeNull();
    expect(localStorage.getItem('user')).toBeNull();
  });

  it('兼容历史遗留键 localStorage.token', () => {
    localStorage.setItem('token', 'LEGACY-TOKEN');
    expect(getToken()).toBe('LEGACY-TOKEN');
  });

  it('user 内容损坏时不应抛错（只当作用户资料缺失）', () => {
    localStorage.setItem('auth_token', 'TOK-1');
    localStorage.setItem('user', '{不是合法 JSON');
    const identity = getIdentity();
    expect(identity.token).toBe('TOK-1');
    expect(identity.user).toBeNull();
  });
});

describe('patchStoredUser：改资料后两个存储都要更新', () => {
  it('更新昵称/邮箱后，本标签页与新标签页读到的都是新值', () => {
    saveIdentity({ token: 'TOK-1', user: { id: 1, username: 'a', email: 'old@x.com' } });

    const merged = patchStoredUser({ email: 'new@x.com', bio: '你好' });

    expect(merged.email).toBe('new@x.com');
    expect(getStoredUser().email).toBe('new@x.com');

    sessionStorage.clear(); // 新标签页
    expect(getStoredUser().email).toBe('new@x.com');
    expect(getStoredUser().username).toBe('a');
  });

  it('未登录时不做任何写入', () => {
    expect(patchStoredUser({ email: 'x@y.z' })).toBeNull();
    expect(localStorage.getItem('user')).toBeNull();
  });
});
