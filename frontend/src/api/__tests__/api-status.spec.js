/**
 * 回归测试：@/api（src/api/index.js）的 HTTP 状态语义与凭证日志。
 *
 * 背景（两个真实缺陷，本批修复）：
 *  1. `validateStatus` 原为 `status >= 200 && status < 500`，即 **400/401/403/404/429
 *     都被当成"请求成功"**。于是：
 *       - 评论被限流（400「操作过于频繁」）时，createComment 拿到的是错误体，
 *         调用方 `if (!newComment) throw` 不成立 → 界面照样提示"评论发表成功"；
 *       - DetectView / HistoryView / UserProfileView 里所有
 *         `error.response.status === 401/403/404` 的分支都不可达。
 *  2. 请求拦截器里 `console.log('[API Request] ...', config)`，而此时 config.headers
 *     已带上 `Authorization: Token xxx` → **每次请求都把登录令牌打进控制台**。
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import api from '@/api';

describe('api 实例的 HTTP 状态语义（回归：4xx 被当成成功）', () => {
  const validate = () => api.getInstance().defaults.validateStatus;

  it('2xx 视为成功', () => {
    [200, 201, 202, 204, 206].forEach((s) => {
      expect(validate()(s), `status ${s} 应成功`).toBe(true);
    });
  });

  it('3xx/4xx/5xx 一律视为失败，必须走 reject', () => {
    [301, 400, 401, 403, 404, 409, 422, 429, 500, 502].forEach((s) => {
      expect(validate()(s), `status ${s} 不应被当成成功`).toBe(false);
    });
  });

  it('实例配置里存在 validateStatus（不能被回退成"全部成功"）', () => {
    expect(typeof api.getInstance().defaults.validateStatus).toBe('function');
  });
});

describe('api 请求日志不得泄露凭证', () => {
  let logSpy;
  let debugSpy;
  let captured = null;

  beforeEach(() => {
    captured = null;
    localStorage.setItem('auth_token', 'SECRET_TOKEN_FOR_TEST');
    api.getInstance().defaults.adapter = async (config) => {
      captured = config;
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config, request: {} };
    };
    logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});
  });

  afterEach(() => {
    localStorage.removeItem('auth_token');
    logSpy.mockRestore();
    debugSpy.mockRestore();
  });

  const allLogged = () =>
    [...logSpy.mock.calls, ...debugSpy.mock.calls]
      .map((args) => JSON.stringify(args.map((a) => (typeof a === 'object' ? a : String(a)))))
      .join('\n');

  it('请求拦截器确实加上了 Authorization 头', async () => {
    await api.get('/forums/boards/');
    expect(captured.headers.Authorization).toBe('Token SECRET_TOKEN_FOR_TEST');
  });

  it('日志里不出现 token 明文，也不打印整个 config', async () => {
    await api.get('/forums/boards/');
    const logged = allLogged();
    expect(logged).not.toContain('SECRET_TOKEN_FOR_TEST');
    expect(logged).not.toContain('Authorization');
    // 只允许记录 方法 + 路径
    expect(logged).toContain('forums/boards/');
  });
});
