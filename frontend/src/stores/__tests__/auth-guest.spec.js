/**
 * 游客试用（第 439 批）：store 侧的行为。
 *
 * 钉住三件事：
 *  1. 开试用成功后，身份要写进两个存储（新标签页不该再开一个账号）；
 *  2. 开失败（试用关闭 / 限流）必须返回 false，让路由守卫回到"跳登录页"的老路；
 *  3. 退出登录要连额度一起清，否则下一个人进来会看到上一个人的"还剩 2 次"。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';

const { post, get } = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));

vi.mock('@/api/http', () => ({
  default: {
    post,
    get,
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  },
}));

// 登录用的客户端也要挡掉：否则会真的加载 utils/axios 的拦截器
vi.mock('@/utils/axios', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  },
}));

import { useAuthStore } from '@/stores/auth';

const GUEST_USER = { id: 9, username: 'guest_abc', is_guest: true, role: 'USER' };
const QUOTA = { is_guest: true, unlimited: false, detect_left: 3, ask_left: 5, resets_at: '2026-11-29T00:00:00+08:00' };

beforeEach(() => {
  setActivePinia(createPinia());
  localStorage.clear();
  sessionStorage.clear();
  post.mockReset();
  get.mockReset();
});

describe('游客试用：开身份', () => {
  it('成功后写入身份与额度', async () => {
    post.mockResolvedValue({
      status: 'success',
      message: '已开启试用',
      data: { user: GUEST_USER, token: 'GUEST-TOK', quota: QUOTA },
    });

    const store = useAuthStore();
    const ok = await store.startGuestTrial();

    expect(ok).toBe(true);
    expect(store.authToken).toBe('GUEST-TOK');
    expect(store.isGuest).toBe(true);
    expect(store.quota.detect_left).toBe(3);
    // 两个存储都要有：新标签页不该再开一个新账号
    expect(sessionStorage.getItem('auth_token')).toBe('GUEST-TOK');
    expect(localStorage.getItem('auth_token')).toBe('GUEST-TOK');
  });

  it('试用被关闭（403）时返回 false，且不写入任何身份', async () => {
    post.mockRejectedValue(Object.assign(new Error('试用功能当前未开放'), { status: 403 }));

    const store = useAuthStore();
    const ok = await store.startGuestTrial();

    expect(ok).toBe(false);
    expect(store.authToken).toBeNull();
    expect(localStorage.getItem('auth_token')).toBeNull();
  });

  it('响应结构不对时也返回 false（不能静默变成"已登录但没身份"）', async () => {
    post.mockResolvedValue({ status: 'success', data: { nothing: true } });

    const store = useAuthStore();
    expect(await store.startGuestTrial()).toBe(false);
    expect(store.authToken).toBeNull();
  });
});

describe('游客试用：额度', () => {
  it('refreshQuota 用后端返回覆盖本地', async () => {
    post.mockResolvedValue({
      status: 'success',
      data: { user: GUEST_USER, token: 'GUEST-TOK', quota: QUOTA },
    });
    const store = useAuthStore();
    await store.startGuestTrial();

    get.mockResolvedValue({
      status: 'success',
      data: { ...QUOTA, detect_left: 1, ask_left: 2 },
    });
    const quota = await store.refreshQuota();

    expect(quota.detect_left).toBe(1);
    expect(store.quota.detect_left).toBe(1);
  });

  it('没有 token 时不去请求额度', async () => {
    const store = useAuthStore();
    expect(await store.refreshQuota()).toBeNull();
    expect(get).not.toHaveBeenCalled();
  });

  it('退出登录把额度一起清掉', async () => {
    post.mockResolvedValue({
      status: 'success',
      data: { user: GUEST_USER, token: 'GUEST-TOK', quota: QUOTA },
    });
    const store = useAuthStore();
    await store.startGuestTrial();
    expect(store.quota).not.toBeNull();

    store.clearAuth();

    expect(store.quota).toBeNull();
    expect(store.isGuest).toBe(false);
  });
});
