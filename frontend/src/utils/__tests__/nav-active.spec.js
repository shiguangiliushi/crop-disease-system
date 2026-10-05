/**
 * 导航高亮判定测试（第 74 批）
 * ----------------------------------------------------------------------------
 * 背景：实测反馈"在 /history 页面顶栏却亮了首页胶囊"。这类串页问题一旦出现，
 * 用户会以为自己点错了、或页面没跳转。这里用固定用例把规则钉死。
 */
import { describe, expect, it } from 'vitest';
import { isNavActive, normalizePath } from '@/utils/navActive';

describe('导航高亮判定', () => {
  it('首页只在根路径点亮，不会在其它任何页面串亮', () => {
    expect(isNavActive('/', '/')).toBe(true);
    // 回归重点：这些路径过去出现过"首页被点亮"
    for (const path of ['/history', '/detect', '/pests', '/news', '/forum', '/alerts', '/calendar', '/consult', '/about']) {
      expect(isNavActive(path, '/'), `首页不应在 ${path} 被点亮`).toBe(false);
    }
  });

  it('每个页面只点亮自己那一项', () => {
    const targets = {
      '/detect': '/detect',
      '/pests': '/pests',
      '/history': '/history',
      '/alerts': '/alerts',
      '/calendar': '/calendar',
      '/consult': '/consult',
      '/news': '/news',
      '/forum': '/forum',
      '/about': '/about',
    };

    for (const [path, expected] of Object.entries(targets)) {
      const lit = Object.values(targets).filter((t) => isNavActive(path, t));
      expect(lit, `${path} 应恰好点亮 1 项，实际点亮 ${JSON.stringify(lit)}`).toEqual([expected]);
    }
  });

  it('子路由点亮其父导航项', () => {
    expect(isNavActive('/news/12', '/news')).toBe(true);
    expect(isNavActive('/pests/Apple___Apple_scab', '/pests')).toBe(true);
    expect(isNavActive('/forum/post/3', '/forum')).toBe(true);
    expect(isNavActive('/forum/board/2', '/forum')).toBe(true);
    expect(isNavActive('/user/profile/7', '/about')).toBe(false);
  });

  it('前缀相近但不构成父子关系的路径不会误点亮', () => {
    // /newspaper 不是 /news 的子路由
    expect(isNavActive('/newspaper', '/news')).toBe(false);
    // /historyArchive 不是 /history 的子路由
    expect(isNavActive('/historyArchive', '/history')).toBe(false);
  });

  it('尾斜杠与查询串不影响判定', () => {
    expect(isNavActive('/history/', '/history')).toBe(true);
    expect(isNavActive('/news?page=2', '/news')).toBe(true);
    expect(isNavActive('/', '/')).toBe(true);
    expect(isNavActive('', '/')).toBe(true);
  });

  it('normalizePath 归一化正确', () => {
    expect(normalizePath('/news/')).toBe('/news');
    expect(normalizePath('/news//')).toBe('/news');
    expect(normalizePath('/')).toBe('/');
    expect(normalizePath('')).toBe('/');
    expect(normalizePath('/news?page=2')).toBe('/news');
    expect(normalizePath('/news#top')).toBe('/news');
  });
});
