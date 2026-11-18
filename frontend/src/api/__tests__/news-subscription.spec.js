/**
 * 回归测试：行业动态订阅接口的路径 / 方法 / 参数契约（第 402 批）
 * ============================================================================
 * 这一批前端新增四个订阅接口调用，最容易出错的不是业务逻辑，而是：
 *   1. **路径写错**（少 / 多斜杠、check 的路径前缀）—— axios 会拼成 404，
 *      而页面按"未订阅"静默降级，问题会一直藏着；
 *   2. **参数被二次包裹**（`?params[target_type]=…`）—— 后端读不到业务参数；
 *   3. **分页归一化只认一种返回形状**（分页对象 vs 裸数组），老后端/测试桩下整块崩；
 *   4. `check` 的失败被吞掉 —— 调用方需要它 reject 才能决定降级，不能变成"永远未订阅"。
 *
 * 做法与其他 api spec 一致：给真实 http 实例换自定义 adapter，不真的发网络请求，
 * 只记录 axios 最终交给 adapter 的配置。
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import http from '../http';
import newsSubscription, {
  checkNewsSubscription,
  createNewsSubscription,
  deleteNewsSubscription,
  fetchNewsSubscriptions,
} from '../newsSubscription';

// http.js 的请求拦截器会读 auth store（拿 Token），store 需要先装一个 pinia
beforeEach(() => {
  setActivePinia(createPinia());
});

let captured = null;

/** 用固定响应体替换 axios adapter，并记录最终请求配置 */
const respondWith = (data) => async (config) => {
  captured = config;
  return { data, status: 200, statusText: 'OK', headers: {}, config, request: {} };
};

const originalAdapter = http.defaults.adapter;

beforeEach(() => {
  captured = null;
});

afterEach(() => {
  // 换回 axios 自带的 adapter，避免影响同进程里的其他用例
  http.defaults.adapter = originalAdapter;
});

describe('fetchNewsSubscriptions：我的订阅列表', () => {
  it('请求 news-subscriptions/ 并归一化分页结构', async () => {
    http.defaults.adapter = respondWith({
      count: 2,
      results: [
        { id: 1, target_type: 'category', category: 'policy' },
        { id: 2, target_type: 'pest', pest: 7 },
      ],
    });

    const data = await fetchNewsSubscriptions({ page: 1, page_size: 100 });

    expect(captured.url).toBe('news-subscriptions/');
    // 用 toMatchObject：GET 可能被客户端追加防缓存时间戳（_t），只断言业务参数
    expect(captured.params).toMatchObject({ page: 1, page_size: 100 });
    expect(data.count).toBe(2);
    expect(data.results).toHaveLength(2);
    expect(data.results[1]).toMatchObject({ target_type: 'pest', pest: 7 });
  });

  it('后端直接返回数组时也兼容成 { count, results }', async () => {
    http.defaults.adapter = respondWith([{ id: 3, target_type: 'category', category: 'tech' }]);

    const data = await fetchNewsSubscriptions();

    expect(data).toEqual({
      count: 1,
      results: [{ id: 3, target_type: 'category', category: 'tech' }],
    });
  });

  it('响应缺 results/count 时归一化成空数组与 0（接口未上线不崩）', async () => {
    http.defaults.adapter = respondWith({});

    expect(await fetchNewsSubscriptions()).toEqual({ count: 0, results: [] });
  });
});

describe('createNewsSubscription：新增订阅', () => {
  it('POST news-subscriptions/，body 原样透传分类订阅', async () => {
    http.defaults.adapter = respondWith({ id: 9, target_type: 'category', category: 'policy' });

    const created = await createNewsSubscription({ target_type: 'category', category: 'policy' });

    expect(captured.url).toBe('news-subscriptions/');
    expect(captured.method).toBe('post');
    // axios 默认 transformRequest 会把对象序列化成 JSON 字符串
    expect(JSON.parse(captured.data)).toEqual({ target_type: 'category', category: 'policy' });
    expect(created).toMatchObject({ id: 9, target_type: 'category' });
  });

  it('病害订阅 body 带 target_type=pest 与 pest id', async () => {
    http.defaults.adapter = respondWith({ id: 10, target_type: 'pest', pest: 7 });

    await createNewsSubscription({ target_type: 'pest', pest: 7 });

    expect(JSON.parse(captured.data)).toEqual({ target_type: 'pest', pest: 7 });
  });
});

describe('deleteNewsSubscription：取消订阅', () => {
  it('DELETE news-subscriptions/<id>/ 并返回 true', async () => {
    http.defaults.adapter = respondWith({});

    const result = await deleteNewsSubscription(42);

    expect(captured.url).toBe('news-subscriptions/42/');
    expect(captured.method).toBe('delete');
    expect(result).toBe(true);
  });
});

describe('checkNewsSubscription：查询订阅状态', () => {
  it('请求 check/ 并透传分类查询参数，返回 {subscribed, id}', async () => {
    http.defaults.adapter = respondWith({ subscribed: true, id: 7 });

    const data = await checkNewsSubscription({ target_type: 'category', category: 'policy' });

    expect(captured.url).toBe('news-subscriptions/check/');
    expect(captured.method).toBe('get');
    expect(captured.params).toMatchObject({ target_type: 'category', category: 'policy' });
    expect(data).toEqual({ subscribed: true, id: 7 });
  });

  it('病害查询参数同样透传', async () => {
    http.defaults.adapter = respondWith({ subscribed: false, id: null });

    await checkNewsSubscription({ target_type: 'pest', pest: 7 });

    expect(captured.params).toMatchObject({ target_type: 'pest', pest: 7 });
  });

  it('响应缺 id 时归一化成 null，subscribed 缺省为 false', async () => {
    http.defaults.adapter = respondWith({});

    expect(await checkNewsSubscription({ target_type: 'category', category: 'tech' })).toEqual({
      subscribed: false,
      id: null,
    });
  });

  it('请求失败时向上抛（调用方据此降级，不能静默成"未订阅"）', async () => {
    http.defaults.adapter = async () => {
      const error = new Error('Request failed with status code 404');
      error.response = { status: 404, data: { detail: 'Not found' } };
      throw error;
    };

    await expect(
      checkNewsSubscription({ target_type: 'category', category: 'policy' }),
    ).rejects.toThrow('404');
  });
});

describe('default 导出', () => {
  it('四个函数都挂在默认导出上（页面按命名导入，导出不全会静默 undefined）', () => {
    expect(typeof newsSubscription.fetchNewsSubscriptions).toBe('function');
    expect(typeof newsSubscription.createNewsSubscription).toBe('function');
    expect(typeof newsSubscription.deleteNewsSubscription).toBe('function');
    expect(typeof newsSubscription.checkNewsSubscription).toBe('function');
  });
});
