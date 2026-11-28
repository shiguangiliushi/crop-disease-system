/**
 * 管理端用户列表的「真实用户口径」（第 447 批）
 *
 * 背景：管理端「用户总数」显示 13、系统健康页显示 11 —— 因为健康/看板走
 * `real_users()`（排除游客试用账号），而用户列表把 `guest_*` 一起算了。
 * 两个数字都不错，但界面上没交代口径，演示时看着像"统计坏了"。
 *
 * 修法（前后端各一半）：
 *   · 后端 `/api/admin/users/` 支持 `?include_guests=false`；
 *   · 前端「用户总数」按真实用户计，游客数单独用小字显示；
 *   · 「账号范围」下拉新增「仅真实用户」。
 *
 * 这是静态扫描用例（与 `admin-system-tabs.spec.js` 同一套路）：组件是纯 UI，
 * 用 jsdom 挂载成本高、收益低，而这里要钉的恰好是"有没有把这两个参数发出去"。
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { en as enMessages, zhCN } from '@/i18n/messages';

const here = dirname(fileURLToPath(import.meta.url));
const viewSource = readFileSync(resolve(here, '../../views/AdminUsersView.vue'), 'utf-8');

describe('管理端用户列表：真实用户口径', () => {
  it('「用户总数」用 include_guests=false 取真实用户数', () => {
    // loadStats 里必须有"只取真实用户"的那次请求
    expect(viewSource).toMatch(/include_guests:\s*'false'/);
    // 且总数用的是 real 而不是 all
    expect(viewSource).toMatch(/total:\s*totalReal/);
  });

  it('游客数 = 全部 − 真实，且不会出现负数', () => {
    expect(viewSource).toMatch(/guests:\s*Math\.max\(totalAll - totalReal,\s*0\)/);
  });

  it('「账号范围」下拉有「仅真实用户」，并且会转成 include_guests=false', () => {
    expect(viewSource).toContain('value="real_only"');
    expect(viewSource).toMatch(/scope === 'real_only'\)\s*params\.include_guests = 'false'/);
  });

  it('中英文都补齐了两个新文案', () => {
    const zhKeys = zhCN.adminUsers;
    const enKeys = enMessages.adminUsers;
    for (const key of ['scopeRealOnly', 'statGuests']) {
      expect(zhKeys[key], `zh.${key}`).toBeTruthy();
      expect(enKeys[key], `en.${key}`).toBeTruthy();
    }
  });
});
