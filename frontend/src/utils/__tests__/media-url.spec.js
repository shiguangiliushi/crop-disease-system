/**
 * 媒体地址归一化（第 430 批）—— 生产站的 Mixed Content 修复
 *
 * 线上日志：HTTPS 页面里出现 `http://10.0.0.5/media/…` 的图片，
 * 浏览器按 Mixed Content 拦掉，用户看到的是"图片裂了"。根因是**历史数据存了完整地址**
 * （早期用局域网 IP 调试时写进去的），以及富文本正文里的 `<img src="http://…">`。
 *
 * 这里钉住三条边界：
 *   1. 只把 **http + `/media/`** 归一成相对路径 —— 改成 https 没用（那个 IP 没有证书）；
 *   2. **https 外链不动** —— 图床域名不归我们管；
 *   3. **`/media/` 不再拼 API 前缀**（`VITE_API_BASE_URL` 带 `/api` 时会拼成
 *      `/api/media/…`，那是 404，不是图片）。
 */
import { describe, expect, it } from 'vitest';

import { normalizeMediaUrl, normalizeMediaUrlsIn, sameOriginMediaPath } from '../mediaUrl';
import { getImageUrl } from '../image';

describe('sameOriginMediaPath', () => {
  it('http 的 /media/ 地址 → 同源相对路径（含 query）', () => {
    expect(sameOriginMediaPath('http://10.0.0.5/media/pest_images/x.jpg'))
      .toBe('/media/pest_images/x.jpg');
    expect(sameOriginMediaPath('http://10.0.0.5:8000/media/a.jpg?w=300'))
      .toBe('/media/a.jpg?w=300');
  });

  it('已经是相对的 /media/ → 不需要改写（返回空串）', () => {
    expect(sameOriginMediaPath('/media/a.jpg')).toBe('');
  });

  it('https 与外链不动', () => {
    expect(sameOriginMediaPath('https://www.shiguangiliushi.com/media/a.jpg')).toBe('');
    expect(sameOriginMediaPath('https://cdn.example.com/media/a.jpg')).toBe('');
    expect(sameOriginMediaPath('https://cdn.example.com/x.png')).toBe('');
  });

  it('http 但不是 /media/ 的地址不动', () => {
    expect(sameOriginMediaPath('http://example.com/x.jpg')).toBe('');
  });

  it('脏数据与空值不炸', () => {
    expect(sameOriginMediaPath('')).toBe('');
    expect(sameOriginMediaPath(null)).toBe('');
    expect(sameOriginMediaPath('http://')).toBe('');
  });
});

describe('normalizeMediaUrl', () => {
  it('能归一就归一，否则原样返回', () => {
    expect(normalizeMediaUrl('http://10.0.0.5/media/a.jpg')).toBe('/media/a.jpg');
    expect(normalizeMediaUrl('https://cdn.example.com/x.png')).toBe('https://cdn.example.com/x.png');
    expect(normalizeMediaUrl('')).toBe('');
  });
});

describe('getImageUrl', () => {
  it('http 的 /media/ 地址也被归一（历史数据不再裂图）', () => {
    expect(getImageUrl('http://10.0.0.5/media/detection/a.jpg')).toBe('/media/detection/a.jpg');
  });

  it('/media/ 不拼 API 前缀（带 /api 的 base 会拼成 404）', () => {
    expect(getImageUrl('/media/a.jpg')).toBe('/media/a.jpg');
  });

  it('其它绝对路径仍按原规则拼 API 前缀', () => {
    // 测试环境没有 VITE_API_BASE_URL，等价于 base = ''
    expect(getImageUrl('/static/a.png')).toBe('/static/a.png');
  });

  it('data: 与空值原样返回', () => {
    expect(getImageUrl('data:image/png;base64,AAA')).toBe('data:image/png;base64,AAA');
    expect(getImageUrl('')).toBe('');
  });
});

describe('normalizeMediaUrlsIn（响应体归一，第 431 批）', () => {
  // 页面里大量 `<img :src="news.image">` 是直接绑数据的 —— 在数据进内存那一刻收口，
  // 免得"这个组件改了、那个页面又漏"。
  it('深层对象/数组里的 http 媒体地址被改写，其它字段原样', () => {
    const payload = {
      count: 1,
      results: [{
        id: 7,
        title: '新闻',
        image: 'http://10.0.0.5/media/news/a.jpg',
        body: '<p>x</p><img src="http://10.0.0.5/media/news/b.jpg">',
        url: 'https://example.com/read?id=1',
      }],
    };

    const fixed = normalizeMediaUrlsIn(payload);

    expect(fixed.results[0].image).toBe('/media/news/a.jpg');
    expect(fixed.results[0].body).toContain('src="/media/news/b.jpg"');
    expect(fixed.results[0].url).toBe('https://example.com/read?id=1');
    expect(fixed.count).toBe(1);
    expect(fixed.results[0].title).toBe('新闻');
  });

  it('没有需要改的字符串时返回**原对象**（别为每次响应都重建一棵树）', () => {
    const payload = { results: [{ image: '/media/a.jpg', title: 'x' }] };
    expect(normalizeMediaUrlsIn(payload)).toBe(payload);
  });

  it('非普通对象（Blob/Date/File）原样返回', () => {
    const blob = new Blob(['x']);
    const date = new Date();
    expect(normalizeMediaUrlsIn(blob)).toBe(blob);
    expect(normalizeMediaUrlsIn(date)).toBe(date);
  });

  it('数字/null/布尔值不炸', () => {
    expect(normalizeMediaUrlsIn(0)).toBe(0);
    expect(normalizeMediaUrlsIn(null)).toBeNull();
    expect(normalizeMediaUrlsIn(false)).toBe(false);
  });
});
