/**
 * 回归测试：行业动态接口的参数与表单拼装契约（第 399 批）
 * ============================================================================
 * 这一批后端给 News 加了 `summary` / `is_featured`（读者端还有 `featured` 头条段），
 * 并给列表接口加了 `ordering` / `tags` / `date_range` / `featured` 参数。
 *
 * 前端的三个关键约定，本测试逐个钉住：
 *   1. `buildNewsFormData` 里三个**可选字段只在 payload 存在该键时才 append** ——
 *      否则「行业动态」弹窗保存会顺手把「新闻管理」页维护的定时发布/摘要清空；
 *   2. 列表返回的 `featured` 必须归一化成数组：老后端没有该字段时是 `[]`，
 *      页面据此走"无头条区"的分支，而不是 `undefined.length` 崩掉；
 *   3. `fetchNewsTags` 打 `/news/tags/` 并把 `{tags,count}` 归一化。
 *
 * 做法和 api-params.spec.js 一致：给真实 http 实例换一个自定义 adapter，
 * 不发网络请求，只记录 axios 最终交给 adapter 的配置。
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import http from '../http';
import { buildNewsFormData, fetchNewsList, fetchNewsTags, fetchNewsRelated } from '../news';

// http.js 的请求拦截器会读 auth store（拿 Token），而 store 需要先装一个 pinia
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

describe('buildNewsFormData：新增字段只在显式传入时才提交', () => {
  it('summary / is_featured / published_at 都按后端约定 append', () => {
    const formData = buildNewsFormData({
      title: '小麦病害预警',
      content: '正文',
      summary: '一句话摘要',
      is_featured: true,
      published_at: '2026-11-18T09:30:00+08:00',
      tags: ['政策', '病害'],
    });

    expect(formData.get('summary')).toBe('一句话摘要');
    expect(formData.get('is_featured')).toBe('true');
    expect(formData.get('published_at')).toBe('2026-11-18T09:30:00+08:00');
    // 原有行为保持不变：标签数组 → 逗号拼接
    expect(formData.get('tags')).toBe('政策,病害');
  });

  it('is_featured=false 打成字符串 false（multipart 没有布尔类型）', () => {
    const formData = buildNewsFormData({ title: 't', content: 'c', is_featured: false });
    expect(formData.get('is_featured')).toBe('false');
  });

  it('published_at=null 打成空串（表示清空定时发布、立即发布）', () => {
    const formData = buildNewsFormData({ title: 't', content: 'c', published_at: null });
    expect(formData.has('published_at')).toBe(true);
    expect(formData.get('published_at')).toBe('');
  });

  it('缺省这三个键时一个都不 append（避免 A 页面保存清空 B 页面的字段）', () => {
    const formData = buildNewsFormData({
      title: 't',
      content: 'c',
      category: 'policy',
      source: 's',
      tags: ['a'],
      is_published: true,
    });

    expect(formData.has('summary')).toBe(false);
    expect(formData.has('is_featured')).toBe(false);
    expect(formData.has('published_at')).toBe(false);
    // 老字段行为不变
    expect(formData.get('is_published')).toBe('true');
  });

  it('summary 显式传空串时仍然 append 空串（用于清空摘要）', () => {
    const formData = buildNewsFormData({ title: 't', content: 'c', summary: '' });
    expect(formData.has('summary')).toBe(true);
    expect(formData.get('summary')).toBe('');
  });

  it('clear_image / image 的既有行为不变', () => {
    const file = new File(['x'], 'cover.png', { type: 'image/png' });
    const formData = buildNewsFormData({ title: 't', content: 'c', clear_image: true }, file);
    expect(formData.get('clear_image')).toBe('true');
    expect(formData.get('image')).toBe(file);
  });
});

describe('fetchNewsList：featured 段归一化', () => {
  it('分页对象带 featured 时原样返回，并保留 count/results', async () => {
    http.defaults.adapter = respondWith({
      count: 5,
      results: [{ id: 1 }, { id: 2 }],
      featured: [{ id: 9 }],
    });

    const data = await fetchNewsList({ page: 1, page_size: 10, featured: '1' });

    expect(captured.url).toBe('/news/');
    expect(captured.params).toMatchObject({ page: 1, page_size: 10, featured: '1' });
    expect(data.count).toBe(5);
    expect(data.results).toEqual([{ id: 1 }, { id: 2 }]);
    expect(data.featured).toEqual([{ id: 9 }]);
  });

  it('老后端没有 featured 字段 → []，不崩也不造数据', async () => {
    http.defaults.adapter = respondWith({ count: 1, results: [{ id: 1 }] });

    const data = await fetchNewsList({ page: 1 });
    expect(data.featured).toEqual([]);
  });

  it('接口返回数组（不分页）时同样带 featured: []', async () => {
    http.defaults.adapter = respondWith([{ id: 1 }, { id: 2 }]);

    const data = await fetchNewsList();
    expect(data.results).toEqual([{ id: 1 }, { id: 2 }]);
    expect(data.count).toBe(2);
    expect(data.total_pages).toBe(1);
    expect(data.featured).toEqual([]);
  });
});

describe('fetchNewsTags：热门标签聚合', () => {
  it('请求 /news/tags/ 并归一化 { tags, count }', async () => {
    http.defaults.adapter = respondWith({
      tags: [{ name: '政策', count: 3 }, { name: '病害', count: 2 }],
      count: 2,
    });

    const data = await fetchNewsTags({ limit: 10 });

    expect(captured.url).toBe('/news/tags/');
    expect(captured.params).toMatchObject({ limit: 10 });
    expect(data).toEqual({
      tags: [{ name: '政策', count: 3 }, { name: '病害', count: 2 }],
      count: 2,
    });
  });

  it('响应缺 tags/count 时归一化成空数组与 0', async () => {
    http.defaults.adapter = respondWith({});

    const data = await fetchNewsTags();
    expect(data).toEqual({ tags: [], count: 0 });
  });
});

// ============================================================================
// 第 401 批：原文链接 / 关联病害 / 相关推荐
// ----------------------------------------------------------------------------
// 这一批后端给 News 加了 external_url、related_pests（写 id 数组）、
// clear_related_pests（multipart 清空开关）与 GET /news/{id}/related/。
//
// 表单拼装的关键约定（与 summary 等可选字段同一口径）：
//   · **只在 payload 里存在该键时才 append** —— 否则行业动态弹窗保存一次，
//     就会把新闻管理页维护的原文链接/关联病害清空；
//   · 关联病害用**重复同名 key** 表达数组；空数组不能 append 空串
//     （后端 PrimaryKeyRelatedField 会把 '' 当非法主键），清空走 clear_related_pests；
//   · clear_related_pests 是布尔，multipart 里打成 'true'/'false'。
// ============================================================================
describe('buildNewsFormData：第 401 批新增字段', () => {
  it('external_url 只在 payload 存在该键时才 append（空串表示清空原文链接）', () => {
    expect(buildNewsFormData({ title: 't', content: 'c' }).has('external_url')).toBe(false);

    const cleared = buildNewsFormData({ title: 't', content: 'c', external_url: '' });
    expect(cleared.has('external_url')).toBe(true);
    expect(cleared.get('external_url')).toBe('');

    const filled = buildNewsFormData({
      title: 't',
      content: 'c',
      external_url: 'https://www.moa.gov.cn/news/1.html',
    });
    expect(filled.get('external_url')).toBe('https://www.moa.gov.cn/news/1.html');
  });

  it('related_pests 数组逐个 append（multipart 用重复同名 key）', () => {
    const formData = buildNewsFormData({ title: 't', content: 'c', related_pests: [3, 7] });
    expect(formData.getAll('related_pests')).toEqual(['3', '7']);
  });

  it('空 related_pests 不 append 空串，清空由 clear_related_pests 表达', () => {
    const formData = buildNewsFormData({
      title: 't',
      content: 'c',
      related_pests: [],
      clear_related_pests: true,
    });

    expect(formData.has('related_pests')).toBe(false);
    expect(formData.getAll('related_pests')).toEqual([]);
    expect(formData.get('clear_related_pests')).toBe('true');
  });

  it('related_pests 缺键时一个都不 append（避免 A 页面保存清空 B 页面）', () => {
    const formData = buildNewsFormData({ title: 't', content: 'c' });
    expect(formData.has('related_pests')).toBe(false);
    expect(formData.has('clear_related_pests')).toBe(false);
  });

  it('related_pests 里的空值会被过滤，只保留有效 id', () => {
    const formData = buildNewsFormData({ title: 't', content: 'c', related_pests: [null, 5, '', undefined] });
    expect(formData.getAll('related_pests')).toEqual(['5']);
  });

  it("clear_related_pests 布尔 → 'true'/'false'（仅键存在时）", () => {
    const cleared = buildNewsFormData({ title: 't', content: 'c', clear_related_pests: true });
    expect(cleared.get('clear_related_pests')).toBe('true');

    const kept = buildNewsFormData({ title: 't', content: 'c', clear_related_pests: false });
    expect(kept.get('clear_related_pests')).toBe('false');
  });
});

describe('fetchNewsRelated：相关推荐接口', () => {
  it('请求 /news/{id}/related/ 并归一化 { results, count }', async () => {
    http.defaults.adapter = respondWith({
      results: [{ id: 2, title: '相关报道' }],
      count: 1,
    });

    const data = await fetchNewsRelated(12, { limit: 4 });

    expect(captured.url).toBe('/news/12/related/');
    // 用 toMatchObject：http 客户端的 GET 可能追加防缓存时间戳（_t），只断言关心的参数
    expect(captured.params).toMatchObject({ limit: 4 });
    expect(data).toEqual({ results: [{ id: 2, title: '相关报道' }], count: 1 });
  });

  it('响应缺 results/count 时归一化成空数组与 0（接口未上线 / 异常返回不崩）', async () => {
    http.defaults.adapter = respondWith({});

    expect(await fetchNewsRelated(1)).toEqual({ results: [], count: 0 });
  });

  it('后端直接返回数组时也兼容成 { results, count }', async () => {
    http.defaults.adapter = respondWith([{ id: 5 }]);

    expect(await fetchNewsRelated(5, { limit: 4 })).toEqual({
      results: [{ id: 5 }],
      count: 1,
    });
  });
});

