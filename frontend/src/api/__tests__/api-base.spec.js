/**
 * API 基地址的兜底（第 432 批）—— 生产构建**不能**带 localhost
 *
 * ## 这次线上到底出了什么
 *
 * 服务器上只有 `frontend/.env.development`，**没有 `.env.production`**。
 * `vite build` 取不到 `VITE_API_BASE_URL`，于是代码里的兜底
 * `http://127.0.0.1:8000/api` 被打进产物（`grep -c 127.0.0.1:8000 dist/assets/index-*.js`
 * 得到 3），线上表现为：
 *
 *   · 接口请求指向**访客自己的机器**（或直接被 Mixed Content 拦掉）；
 *   · 图片地址 `http://127.0.0.1:8000/media/…` 在 HTTPS 页面里被浏览器拦截 → 裂图
 *     （`host is an IP address` 就是它，不是"库里脏数据"）。
 *
 * ## 修法
 *
 * 1. 兜底值改成**同源 `/api`**（nginx 反代到后端）——"没配"时的行为必须是最安全的那个；
 * 2. 补上 `.env.production`（`VITE_API_BASE_URL=/api`），把生产契约显式写下来；
 * 3. 媒体地址只拼 **origin**（去掉 `/api`，见 `utils/mediaUrl.js` 的 `mediaOrigin`）。
 *
 * 这条用例钉住第 1 条：**测试环境没有 env**，所以读到的就是兜底值。
 */
import { describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import { baseURL } from '@/api/http';
import api from '@/api/index';

describe('API 基地址兜底', () => {
  it('没有 VITE_API_BASE_URL 时是同源 /api（不是 127.0.0.1）', () => {
    expect(baseURL).toBe('/api');
    expect(baseURL).not.toContain('127.0.0.1');
  });

  it('旧实例（api/index.js）也是同一个口径', () => {
    setActivePinia(createPinia());
    const instance = api.getInstance();
    expect(instance.defaults.baseURL).toBe('/api/');
    expect(instance.defaults.baseURL).not.toContain('127.0.0.1');
  });
});
