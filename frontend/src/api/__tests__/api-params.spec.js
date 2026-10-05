/**
 * 回归测试：@/api（src/api/index.js）的查询参数必须按 axios 约定透传。
 *
 * 背景（真实缺陷，已修复）：原实现是
 *     get(url, params = {}, config = {}) { return apiClient.get(url, { ...config, params }); }
 * 而**全部 16 个调用点都是按 axios 约定写的**：
 *     api.get('/detection-history/', { params: { page: 1, page_size: 6 } })
 * 于是被多包了一层，真实请求变成 `?params[page]=1&params[page_size]=6`，
 * 后端只认 `page`/`page_size`，导致分页与筛选**静默失效**。
 *
 * 本测试直接加载真实模块，用自定义 adapter 截获最终请求配置，
 * 断言参数既没有被包裹、也能被 axios 正确序列化成 URL。
 */
import { describe, it, expect, beforeEach } from 'vitest';
import api from '@/api';

let captured = null;

beforeEach(() => {
  captured = null;
  // 用自定义 adapter 拦截请求：不真的发网络请求，只记录 axios 最终处理过的配置
  api.getInstance().defaults.adapter = async (config) => {
    captured = config;
    return {
      data: { ok: true },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      request: {},
    };
  };
});

describe('api.get 的查询参数（回归：分页/筛选静默失效）', () => {
  it('把 { params } 原样交给 axios，不做二次包裹', async () => {
    await api.get('/detection-history/', {
      params: { page: 1, page_size: 6, all_users: 'true' },
    });

    // 注：本模块有一个"防缓存"请求拦截器，会给每个 GET 追加 _t 时间戳，
    //     因此这里用 toMatchObject 断言业务参数，而不是全等。
    expect(captured.params).toMatchObject({ page: 1, page_size: 6, all_users: 'true' });
    // 关键断言：不能出现被包一层的 params 键
    expect(captured.params).not.toHaveProperty('params');
    // 确认防缓存时间戳仍在（这是本模块的既有行为，未被本次修复改变）
    expect(typeof captured.params._t).toBe('number');
  });

  it('生成的 URL 是 ?page=1&page_size=6，而不是 ?params[page]=1', async () => {
    await api.get('/detection-history/', { params: { page: 1, page_size: 6 } });

    const url = api.getInstance().getUri(captured);
    expect(url).toContain('page=1');
    expect(url).toContain('page_size=6');
    expect(url).not.toContain('params%5Bpage%5D');
    expect(url).not.toContain('params[page]');
  });

  it('URL 前缀处理：/ 开头会被去掉且不产生双斜杠', async () => {
    await api.get('/detection-history/');
    expect(captured.url).toBe('detection-history/');

    await api.get('detection-history/');
    expect(captured.url).toBe('detection-history/');
  });

  it('config 里的其它字段（如 silent）原样保留', async () => {
    await api.get('statistics/', { silent: true, params: { all_users: 'true' } });
    expect(captured.silent).toBe(true);
    expect(captured.params).toMatchObject({ all_users: 'true' });
  });

  it('不再导出会破坏调用方的 setupInterceptors（解包拦截器已删除）', () => {
    expect(api.setupInterceptors).toBeUndefined();
  });
});
