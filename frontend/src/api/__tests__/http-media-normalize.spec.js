/**
 * 响应拦截器：媒体地址归一（第 431 批）
 *
 * 第 430 批修了两处渲染出口（富文本钩子、`getImageUrl`），但页面里大量图片是
 * **直接绑数据**的（`<img :src="news.image">`）—— 数据里是
 * `http://<服务器IP>/media/…`，浏览器照样按 Mixed Content 拦掉。
 *
 * 所以在 `api/http.js` 的响应拦截器里统一归一：**数据进内存那一刻**就变成相对路径，
 * 所有页面自动受益，不用逐个组件去包（那种改法又漏又不持久）。
 *
 * 这条用例钉的是**接线**，不是纯函数（纯函数在 `utils/__tests__/media-url.spec.js`）：
 * 万一哪天有人把拦截器写成 `(response) => response`（第 123 批之前的原样），
 * 这里会红。用自替换的 adapter 打桩，不联网、也不碰后端。
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import http from '@/api/http';

describe('http 响应拦截器：混合内容归一', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  /** 用 axios 的 adapter 打桩：返回一段固定 payload，不发请求 */
  function stubAdapter(payload) {
    http.defaults.adapter = async (config) => ({
      data: payload,
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    });
  }

  it('JSON 里的 http 媒体地址被归一成相对路径', async () => {
    stubAdapter({
      results: [{ image: 'http://10.0.0.5/media/news/a.jpg', title: '新闻' }],
    });

    const response = await http.get('/news/');

    expect(response.data.results[0].image).toBe('/media/news/a.jpg');
    expect(response.data.results[0].title).toBe('新闻');
  });

  it('blob 响应原样返回（导出/下载不能被改写）', async () => {
    const blob = new Blob(['xls-bytes']);
    stubAdapter(blob);

    const response = await http.get('/export/', { responseType: 'blob' });

    expect(response.data).toBe(blob);
  });
});
