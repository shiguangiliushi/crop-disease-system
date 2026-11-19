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

import { askOpsAssistantStream } from '@/api/opsAssistant';

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

  function reset() {
    turns.value = [];
  }

  return { turns, loading, ask, reset, historyPayload };
});
