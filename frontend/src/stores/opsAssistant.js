/**
 * 系统助手的对话状态（第 414 批）
 *
 * ## 为什么必须放 store，而不是组件里的 `ref`
 *
 * 这个页签挂在「系统」合并页里，而 Hub 是
 * `<component :is="tab.panel" v-if="activeTab === tab.name" />` ——
 * **切到别的页签、或去别的路由再回来，组件会被卸载**，组件内的 `turns` 随之清空。
 * 用户实测：答到一半切走再切回来，内容不见了。
 *
 * 放进 store 有两个直接好处：
 *   1. 卸载不影响数据；
 *   2. **流式进行中切走也不会中断** —— 写入的是 store，不是组件实例。
 *
 * ## 为什么不做 localStorage 持久化
 *
 * 这里的对话是"看系统**当下**状态"的一次性问答，隔天恢复出来的是旧状态，反而误导。
 * 刷新页面即清空是有意的（要留证据请看「观测」里的最近未校验问题）。
 */
import { defineStore } from 'pinia';
import { ref } from 'vue';

import { askOpsAssistantStream, confirmOpsAction } from '@/api/opsAssistant';

export const useOpsAssistantStore = defineStore('opsAssistant', () => {
  const turns = ref([]);
  const loading = ref(false);

  /** 带进下一轮的上下文：只留最近 8 条（后端也只取最近几轮，多了白花 token） */
  function historyPayload() {
    return turns.value
      .flatMap((turn) => [
        { role: 'user', content: turn.question },
        { role: 'assistant', content: turn.answer },
      ])
      .filter((item) => item.content)
      .slice(-8);
  }

  /**
   * 问一个问题的完整流程（含流式）
   *
   * @param {string} question
   * @param {{lang?: string}} [options] 回答语言（`zh` / `en`，来自界面语言）
   * @returns {Promise<object|null>} 后端返回体；被拒（空问题/正在加载）时为 null
   */
  async function ask(question, { lang = 'zh' } = {}) {
    const text = String(question || '').trim();
    if (!text || loading.value) return null;

    const history = historyPayload();
    loading.value = true;

    // 先把这一问推进列表：流式是逐段填进 `answer` 的，
    // 用户要能立刻看见"自己问了什么"，而不是盯着一个空白面板。
    const turn = {
      question: text, answer: '', intent: '', tools: [],
      degraded: false, degrade_reason: '', verified: true, evidence: [],
      streaming: true, failed: false,
      //: 第 426 批：不可逆写的提议。`pending` 非空且 `token` 有效时，页面上出现确认按钮
      pending: null, token: '',
      //: 确认结果（`null` = 还没决定）。有了它就不再显示按钮 —— 凭据是一次性的
      pendingResult: null, confirming: false, pendingError: '',
    };
    turns.value.push(turn);

    try {
      const result = await askOpsAssistantStream({ question: text, history, lang }, {
        // 双参数约定（与农户侧一致）：`(text)` 增量，`(null, final)` 定稿整体替换
        onDelta: (chunk, finalAnswer) => {
          turn.answer = typeof finalAnswer === 'string' ? finalAnswer : turn.answer + chunk;
        },
      });
      Object.assign(turn, result, { failed: false });
      return result;
    } catch (error) {
      turn.failed = true;
      throw error;
    } finally {
      turn.streaming = false;
      loading.value = false;
    }
  }

  /**
   * 确认 / 取消一条不可逆写（第 426 批）
   *
   * 三件刻意的事：
   *  1. **只认 `confirm` / `cancel`**（后端同样只认这两个词）—— 不做"AI 判断这句话算不算确认"；
   *  2. 成功后就**清掉 token**：一次性的东西留在内存里，只会让按钮被再点一次
   *     （后端会拒，但让用户点了再看到"已经处理过了"是多余的坏体验）；
   *  3. 失败时**保留 token 并抛出**：网络没到、400 之类的情况重试是合法的；
   *     真正"不可重试"的失败（过期/已处理）由后端 `ok=false` 表达，会写进 `pendingResult`。
   *
   * @param {object} turn store 里的那一条对话
   * @param {'confirm'|'cancel'} decision
   * @returns {Promise<object|null>} 后端返回体；不该发请求时返回 null
   */
  async function confirm(turn, decision = 'confirm') {
    if (!turn || !turn.token || turn.confirming || turn.pendingResult) return null;
    turn.confirming = true;
    turn.pendingError = '';
    try {
      const result = await confirmOpsAction({ token: turn.token, decision });
      turn.pendingResult = result;
      //: 凭据一次性：不管执行成功、失败、取消、过期，都不再重试
      turn.token = '';
      return result;
    } catch (error) {
      turn.pendingError = error;
      throw error;
    } finally {
      turn.confirming = false;
    }
  }

  function reset() {
    turns.value = [];
  }

  return { turns, loading, ask, confirm, reset, historyPayload };
});
