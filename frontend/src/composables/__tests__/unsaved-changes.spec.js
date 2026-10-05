/**
 * 「未保存修改」离开提醒的单元测试（第 97 批）
 * ----------------------------------------------------------------------------
 * 为什么值得写：这条链路上**每一环都是"看起来没事"的类型** ——
 *   · `beforeunload` 只在刷新/关标签时触发，站内导航根本不经过它；
 *   · 路由守卫是全局的、判定函数是组件内的，中间的注册表断了也不报错，
 *     只是"再也不提醒了"（而这正是改动前长达几十批的状态）。
 * 所以这里把三件事分别钉住：
 *   ① 注册表能拦住导航（返回 false）；
 *   ② 干净时直接放行（不弹框、不 await）；
 *   ③ 组件挂载后确实注册了自己、卸载后确实注销（否则会**泄漏**：
 *      离开页面后旧守卫还在，之后每次导航都会被问一句）。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { defineComponent, ref, nextTick } from 'vue';

// Element Plus 的确认框在单测里不该真的弹：把它替换成可编程的桩
const confirmMock = vi.fn();
vi.mock('element-plus', () => ({
  ElMessageBox: {
    confirm: (...args) => confirmMock(...args),
  },
}));

import {
  registerLeaveGuard,
  runLeaveGuards,
  useUnsavedChanges,
} from '@/composables/useUnsavedChanges';

/** 让守卫表在用例间互不干扰 */
function clearGuards() {
  // 注册表是模块私有的，只能靠注销函数清理 —— 每个用例自己负责
}

describe('runLeaveGuards：导航前的未保存确认', () => {
  beforeEach(() => {
    confirmMock.mockReset();
  });

  afterEach(() => {
    clearGuards();
  });

  it('没有任何守卫时直接放行，且不弹框', async () => {
    const canLeave = await runLeaveGuards();
    expect(canLeave).toBe(true);
    expect(confirmMock).not.toHaveBeenCalled();
  });

  it('守卫报"干净"时放行，不弹框', async () => {
    const unregister = registerLeaveGuard(() => false);
    const canLeave = await runLeaveGuards();
    unregister();
    expect(canLeave).toBe(true);
    expect(confirmMock).not.toHaveBeenCalled();
  });

  it('守卫报"有未保存"时弹框；用户点"离开" → 放行', async () => {
    confirmMock.mockResolvedValue('confirm');
    const unregister = registerLeaveGuard(() => true);
    const canLeave = await runLeaveGuards();
    unregister();
    expect(confirmMock).toHaveBeenCalledTimes(1);
    expect(canLeave).toBe(true);
  });

  it('守卫报"有未保存"时弹框；用户点"留下" → 拦下导航', async () => {
    confirmMock.mockRejectedValue(new Error('cancel'));
    const unregister = registerLeaveGuard(() => true);
    const canLeave = await runLeaveGuards();
    unregister();
    expect(canLeave).toBe(false);
  });

  it('守卫自身抛异常不能把用户困在页面里（按放行处理）', async () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const unregister = registerLeaveGuard(() => {
      throw new Error('判定函数炸了');
    });
    const canLeave = await runLeaveGuards();
    unregister();
    spy.mockRestore();
    expect(canLeave).toBe(true);
    expect(confirmMock).not.toHaveBeenCalled();
  });

  it('注销后不再拦截（防止页面切走后旧守卫残留）', async () => {
    const unregister = registerLeaveGuard(() => true);
    unregister();
    confirmMock.mockResolvedValue('confirm');
    const canLeave = await runLeaveGuards();
    expect(canLeave).toBe(true);
    expect(confirmMock).not.toHaveBeenCalled();
  });
});

describe('useUnsavedChanges：组件级登记', () => {
  beforeEach(() => {
    confirmMock.mockReset();
  });

  it('挂载时注册、卸载时注销（否则离开后每次导航都被问）', async () => {
    const dirty = ref(false);
    const Comp = defineComponent({
      setup() {
        useUnsavedChanges(() => dirty.value);
        return () => null;
      },
    });

    // 挂载前：干净
    confirmMock.mockResolvedValue('confirm');
    expect(await runLeaveGuards()).toBe(true);

    const wrapper = mount(Comp);
    dirty.value = true;
    await nextTick();

    // 挂载后：脏 → 应当拦截
    confirmMock.mockRejectedValue(new Error('cancel'));
    expect(await runLeaveGuards()).toBe(false);

    wrapper.unmount();
    // 卸载后：不再拦（这里 confirm 仍是 reject 桩；若还注册着会返回 false）
    confirmMock.mockResolvedValue('confirm');
    expect(await runLeaveGuards()).toBe(true);
  });

  it('enabled 返回 false 时视为干净（弹窗编辑：只有弹窗开着才拦）', async () => {
    const dirty = ref(true);
    const dialogOpen = ref(false);
    const Comp = defineComponent({
      setup() {
        useUnsavedChanges(() => dirty.value, { enabled: () => dialogOpen.value });
        return () => null;
      },
    });
    const wrapper = mount(Comp);

    confirmMock.mockResolvedValue('confirm');
    // 弹窗没开 → 即便数据"不一致"也放行
    expect(await runLeaveGuards()).toBe(true);
    expect(confirmMock).not.toHaveBeenCalled();

    dialogOpen.value = true;
    await nextTick();
    confirmMock.mockRejectedValue(new Error('cancel'));
    expect(await runLeaveGuards()).toBe(false);

    wrapper.unmount();
  });
});
