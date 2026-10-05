/**
 * 回归测试：鉴权 store 的登录/注册必须对"客户端是否解包"免疫。
 *
 * 背景（真实缺陷）：项目里有三套 HTTP 客户端，对响应的处理各不相同 ——
 *   · @/utils/axios 返回**已解包**的响应体
 *   · 若换成返回 AxiosResponse 的客户端，就会多一层 .data
 *   · 后端也可能直接返回扁平的 {user, token}
 * 原来 login() 写死读 `response.data`，只是"恰好"能拿到 {user, token}；
 * 一旦客户端或后端结构变化就会抛"服务器返回的用户数据格式不正确"。
 * 现在由 unwrapAuthPayload() 逐层向下寻找，本测试锁定这三种形状都能登录成功。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('@/utils/axios', () => ({
  default: {
    post,
    get: vi.fn(),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  },
}));

import { useAuthStore } from '@/stores/auth';

const USER = { id: 1, username: 'tester' };

beforeEach(() => {
  setActivePinia(createPinia());
  // 注意：身份现在以 sessionStorage 为主（见 utils/authStorage.js），
  // 两个存储都要清，否则上一个用例的登录态会被下一个用例读出来。
  localStorage.clear();
  sessionStorage.clear();
  post.mockReset();
});

describe('登录：三种响应形状都必须成功', () => {
  it('形状 A —— utils/axios 已解包：{status,message,data:{user,token}}', async () => {
    post.mockResolvedValue({ status: 'success', message: '登录成功', data: { user: USER, token: 'TOK-A' } });

    const store = useAuthStore();
    const result = await store.login({ username: 'tester', password: 'x' });

    expect(result.token).toBe('TOK-A');
    expect(store.authToken).toBe('TOK-A');
    expect(localStorage.getItem('auth_token')).toBe('TOK-A');
  });

  it('形状 B —— 客户端返回 AxiosResponse（多一层 .data）', async () => {
    post.mockResolvedValue({
      status: 200,
      data: { status: 'success', data: { user: USER, token: 'TOK-B' } },
    });

    const store = useAuthStore();
    const result = await store.login({ username: 'tester', password: 'x' });

    expect(result.token).toBe('TOK-B');
    expect(store.authToken).toBe('TOK-B');
  });

  it('形状 C —— 后端直接返回扁平 {user, token}', async () => {
    post.mockResolvedValue({ user: USER, token: 'TOK-C' });

    const store = useAuthStore();
    const result = await store.login({ username: 'tester', password: 'x' });

    expect(result.token).toBe('TOK-C');
    expect(store.authToken).toBe('TOK-C');
  });

  it('结构确实不对时，仍然给出明确错误（不能静默成功）', async () => {
    post.mockResolvedValue({ status: 'success', message: '登录成功', data: { nothing: true } });

    const store = useAuthStore();
    await expect(store.login({ username: 'tester', password: 'x' })).rejects.toThrow(/格式不正确/);
    expect(store.authToken).toBeNull();
  });
});

describe('注册：应支持"注册即登录"', () => {
  it('后端签发 token 时，直接写入登录态', async () => {
    post.mockResolvedValue({
      status: 'success',
      message: '注册成功',
      data: { user: USER, token: 'TOK-REG' },
    });

    const store = useAuthStore();
    const result = await store.register({ username: 'newbie', password: 'x', email: 'a@b.c' });

    expect(result.token).toBe('TOK-REG');
    expect(store.authToken).toBe('TOK-REG');
    expect(localStorage.getItem('auth_token')).toBe('TOK-REG');
  });

  it('后端未签发 token（旧行为）时不报错，交由调用方跳登录页', async () => {
    post.mockResolvedValue({ status: 'success', data: { user: USER } });

    const store = useAuthStore();
    const result = await store.register({ username: 'newbie', password: 'x' });

    expect(result.token).toBeUndefined();
    expect(store.authToken).toBeNull();
  });
});
