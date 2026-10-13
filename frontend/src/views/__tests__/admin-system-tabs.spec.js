/**
 * 「系统」页的页签**按权限**计算 —— 单测（第 186 批）
 * ============================================================================
 * 这一条是本批的**核心验收**：`health` / `audit` 仅全权管理员、`boards` 为
 * "全权管理员 **或** BROADCAST"。页签与后端口径必须一致，否则就是本项目反复出过的
 * "按钮在、权限没有" —— 点了必然 403。
 *
 * ## 为什么用单测，而不是浏览器 E2E
 *
 * 本批要求的核心场景（"只有 BROADCAST、不是全权管理员的人进「系统」页只看到版块页签"）
 * 在当前系统里**双重不可达**，用浏览器**演不出来**：
 *
 *   ① **后端造不出这种账号** —— `api/capabilities.py` 的 `has_capability()`：
 *      `is_full_admin()`（is_staff / is_superuser / role='ADMIN'）一成立就三项能力全给
 *      并**提前 return**；`role='EDITOR'` 无论勾满几个内容模块都只给 CONTENT；
 *      全库没有按能力授权的表（只有内容模块的 `EditorModuleGrant`）。
 *      后端测试 `api.tests.RoleMatrixTests
 *      .test_no_account_can_hold_broadcast_without_being_a_full_admin` 固化了这条事实。
 *   ② **前端守卫也不放行** —— 管理区要求 `requiresAdmin`，且每个后台落脚页还各有
 *      capability/module（数据看板要 CONTENT + 一个内容模块、系统页要 BROADCAST……）。
 *      第 186 批试过用"合成身份"（真 token + sessionStorage 种
 *      `capabilities:['BROADCAST']`）走一遍浏览器：**进任何 `/admin/**` 都被弹回农户首页**，
 *      `.admin-console` 永远等不到（那次就是这么超时的）。
 *      用浏览器去测一个"根本进不去后台"的身份，测的是不可达状态，没有意义。
 *
 * 所以把"给定权限 → 算出哪几个页签"写成**纯函数**（`src/views/adminSystemTabs.js`）
 * 直接测：不依赖账号、不依赖网络、不依赖 Vue，三种身份都能覆盖。
 *
 * ## 这组断言什么时候该改
 *
 * 页签按权限显示是**为将来"按能力授权"预留的防御性设计**。哪天后端真的支持按能力授权
 * （能造出 BROADCAST-only 的账号），**后端那条测试与这组单测会同时红**，
 * 提醒把"浏览器里真跑一遍"补上 —— 那时它才有真实对象。
 */
import { describe, expect, it } from 'vitest';
import { TAB_AUDIT, TAB_BOARDS, TAB_HEALTH, adminSystemTabs } from '@/views/adminSystemTabs';
import { en, zhCN } from '@/i18n/messages';

describe('「系统」页页签按权限显示（第 186 批）', () => {
  it('只有 BROADCAST、不是全权管理员 → **只**看到「版块管理」一个页签', () => {
    expect(adminSystemTabs({ isAdmin: false, hasBroadcast: true })).toEqual([TAB_BOARDS]);
  });

  it('全权管理员 → 三个页签都有，且顺序是 系统健康 → 操作日志 → 版块管理', () => {
    expect(adminSystemTabs({ isAdmin: true, hasBroadcast: true }))
      .toEqual([TAB_HEALTH, TAB_AUDIT, TAB_BOARDS]);
  });

  it('全权管理员即使能力字段没下发（hasBroadcast=false）也仍看到三个页签', () => {
    // 组信息缺失时的兜底：`isAdmin` 一项就够（与"全权管理员三能力全给"同口径）
    expect(adminSystemTabs({ isAdmin: true, hasBroadcast: false }))
      .toEqual([TAB_HEALTH, TAB_AUDIT, TAB_BOARDS]);
  });

  it('什么相关权限都没有 → 空清单（页面渲染「无权限」空状态，而不是白屏）', () => {
    expect(adminSystemTabs({ isAdmin: false, hasBroadcast: false })).toEqual([]);
    expect(adminSystemTabs({})).toEqual([]);
    expect(adminSystemTabs()).toEqual([]);
  });

  it('默认落点 = 清单第一个：全权管理员落在系统健康，BROADCAST 落在版块管理', () => {
    const adminTabs = adminSystemTabs({ isAdmin: true, hasBroadcast: true });
    const broadcastTabs = adminSystemTabs({ isAdmin: false, hasBroadcast: true });
    expect(adminTabs[0]).toBe(TAB_HEALTH);
    expect(broadcastTabs[0]).toBe(TAB_BOARDS);
  });

  it('**看不到的页签不在清单里**（不是画出来再禁用 —— 点进去必然 403）', () => {
    const broadcastTabs = adminSystemTabs({ isAdmin: false, hasBroadcast: true });
    expect(broadcastTabs).not.toContain(TAB_HEALTH);
    expect(broadcastTabs).not.toContain(TAB_AUDIT);
  });

  it('三个页签的文案键在语言包里都有（中英各一份，缺了会露出键名）', () => {
    for (const [name, key] of [
      [TAB_HEALTH, 'tabHealth'],
      [TAB_AUDIT, 'tabAudit'],
      [TAB_BOARDS, 'tabBoards'],
    ]) {
      expect(zhCN.systemHub?.[key], `中文缺 systemHub.${key}（页签 ${name}）`).toBeTruthy();
      expect(en.systemHub?.[key], `英文缺 systemHub.${key}（页签 ${name}）`).toBeTruthy();
      // 两边不能一字不差（那就是复制过去忘了翻；本项目的语言包一致性检查也在盯这个）
      expect(zhCN.systemHub[key]).not.toBe(en.systemHub[key]);
    }
    // 「无权限」空状态那句人话也要在（页签为空时显示它）
    expect(zhCN.systemHub?.noAccess).toBeTruthy();
    expect(en.systemHub?.noAccess).toBeTruthy();
  });
});
