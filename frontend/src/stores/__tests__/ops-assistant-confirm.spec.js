/**
 * 系统助手 store 的确认流程（第 426 批）
 *
 * store 里做的是**凭据的生命周期管理**，三件事值得钉住：
 *
 *   1. 没有 token 就不发请求 —— 连续点两次不该产生第二个请求；
 *   2. 成功后就清 token（一次性凭据留在内存里，只会让按钮被再点一次）；
 *   3. 请求失败时**保留 token**：网络没到、400 之类重试是合法的；
 *      "过期 / 已被处理"由后端 200 + `ok=false` 表达，会写进 `pendingResult`。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

vi.mock('@/api/opsAssistant', () => ({
  askOpsAssistantStream: vi.fn(),
  confirmOpsAction: vi.fn(),
}));

import { confirmOpsAction } from '@/api/opsAssistant';
import { useOpsAssistantStore } from '@/stores/opsAssistant';

describe('系统助手 store：不可逆写的确认', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  /** 造一条"后端提议了不可逆写"的对话（字段与 `ask()` 回来的一致） */
  function proposalTurn(overrides = {}) {
    const store = useOpsAssistantStore();
    store.turns.push({
      question: '删掉反馈 #12',
      answer: '准备执行：**删除反馈**',
      pending: { action: 'delete_feedback', label: '删除反馈', target: '反馈 #12 番茄晚疫病' },
      token: 'tok-1',
      pendingResult: null,
      confirming: false,
      pendingError: '',
      ...overrides,
    });
    return store.turns[0];
  }

  it('确认成功后记住结果，并清掉一次性 token', async () => {
    confirmOpsAction.mockResolvedValue({ ok: true, status: 'confirmed', answer: '已执行' });
    const turn = proposalTurn();

    await useOpsAssistantStore().confirm(turn, 'confirm');

    expect(confirmOpsAction).toHaveBeenCalledWith({ token: 'tok-1', decision: 'confirm' });
    expect(turn.pendingResult.ok).toBe(true);
    expect(turn.token).toBe('');
    expect(turn.confirming).toBe(false);
  });

  it('取消同样记结果（状态落 cancelled，页面据此显示"没有改动任何数据"）', async () => {
    confirmOpsAction.mockResolvedValue({ ok: false, status: 'cancelled', answer: '已取消' });
    const turn = proposalTurn();

    await useOpsAssistantStore().confirm(turn, 'cancel');

    expect(confirmOpsAction).toHaveBeenCalledWith({ token: 'tok-1', decision: 'cancel' });
    expect(turn.pendingResult.status).toBe('cancelled');
    expect(turn.token).toBe('');
  });

  it('没有 token 就不发请求（防连点）', async () => {
    const turn = proposalTurn({ token: '' });

    expect(await useOpsAssistantStore().confirm(turn, 'confirm')).toBeNull();
    expect(confirmOpsAction).not.toHaveBeenCalled();
  });

  it('已经有结果就不再发第二次（凭据一次性）', async () => {
    const turn = proposalTurn({ pendingResult: { ok: true, status: 'confirmed' } });

    expect(await useOpsAssistantStore().confirm(turn, 'confirm')).toBeNull();
    expect(confirmOpsAction).not.toHaveBeenCalled();
  });

  it('请求失败：错误留在 turn 上、token 保留、loading 复位', async () => {
    const error = new Error('HTTP 403');
    confirmOpsAction.mockRejectedValue(error);
    const turn = proposalTurn();

    await expect(useOpsAssistantStore().confirm(turn, 'confirm')).rejects.toBe(error);

    expect(turn.pendingError).toBe(error);
    expect(turn.token).toBe('tok-1');
    expect(turn.confirming).toBe(false);
    expect(turn.pendingResult).toBeNull();
  });
});
