/**
 * 系统助手页签的**回答渲染**契约（回归）
 *
 * ## 这条测试防的是什么
 *
 * 用户反馈"回答里为什么会有 `**`" —— 根因不是模型乱输出，而是这个页签把回答按
 * **纯文本**直接插值了（`<pre>{{ answer }}</pre>`），而模型写的是 Markdown。
 * 农户侧第 210 批就解决过：`utils/assistantText.js` 只解析加粗一种标记，
 * 片段走文本插值、标签写死在模板里，**不用 `v-html`**。
 *
 * 这条用例不渲染组件（组件依赖 Element Plus / i18n / fetch，挂载成本远大于收益），
 * 而是**直接读源码**钉住三件事：
 *
 *   1. 用的是共用解析器，而不是把 `answer` 直出；
 *   2. 模板里确实渲染了 `<strong>`（否则解析了也没用）；
 *   3. 没有 `v-html=` —— 模型输出是不可信输入，这条边界不能被"图省事"破掉。
 *
 * 与 `api/tests.py:AuditActionDeclaredTests` 同一种思路：**静态扫描**抓那种
 * "不报错、不崩、只是显示不对"的回归。
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(resolve(HERE, '../AdminOpsAssistantView.vue'), 'utf8');
const STORE = readFileSync(resolve(HERE, '../../stores/opsAssistant.js'), 'utf8');

describe('系统助手页签的回答渲染', () => {
  it('用共用的受控解析器，而不是把回答直出', () => {
    expect(SOURCE).toContain("from '@/utils/assistantText'");
    expect(SOURCE).toContain('parseAnswerParagraphs');
    // 直出（`{{ turn.answer }}`）会把 `**` 原样显示出来
    expect(SOURCE).not.toContain('{{ turn.answer }}');
  });

  it('渲染了 <strong>，且标签名写死在模板里', () => {
    expect(SOURCE).toMatch(/<strong v-if="segment\.bold">/);
  });

  it('没有 v-html=（模型输出是不可信输入）', () => {
    expect(SOURCE).not.toMatch(/v-html\s*=/);
  });
});

describe('系统助手页签的对话状态', () => {
  it('状态放在 store，不放组件的 ref（切页签会卸载组件）', () => {
    // Hub 是 `<component :is="tab.panel" v-if="activeTab === tab.name" />` ——
    // 切到别的页签就卸载。状态留在组件里，用户切走再回来内容就没了（第 414 批实测）。
    expect(SOURCE).toContain("from '@/stores/opsAssistant'");
    expect(SOURCE).toContain('useOpsAssistantStore');
    expect(SOURCE).not.toMatch(/const turns = ref\(/);
  });

  it('把界面语言带进请求（切英文后新问的问题才是英文）', () => {
    expect(SOURCE).toMatch(/opsStore\.ask\(text, \{ lang:/);
  });
});

describe('不可逆写的二次确认（第 426 批）', () => {
  // 静态扫描，理由同上：接口可用但**页面上没有调用点**，等于没做（第 425 批就是这样）。
  it('页面上确实有确认 / 取消两个按钮，且都挂到 store.confirm', () => {
    expect(SOURCE).toContain("v-if=\"turn.pending\"");
    expect(SOURCE).toMatch(/@click="decide\(turn, 'confirm'\)"/);
    expect(SOURCE).toMatch(/@click="decide\(turn, 'cancel'\)"/);
    expect(SOURCE).toContain('opsStore.confirm(turn, decision)');
    expect(STORE).toContain('confirmOpsAction');
  });

  it('发给后端的只有 confirm / cancel，不是自然语言', () => {
    // 让模型判断"这句话算不算确认"= 模型可以确认自己刚提的议，是二次确认要防的那件事
    expect(SOURCE).not.toMatch(/confirmOpsAction\(/);      // 组件不直接发请求，统一走 store
    // 第 428 批起对话卡与待确认队列共用 `confirmToken`，只发 token + 两个词之一
    expect(STORE).toMatch(/confirmOpsAction\(\{ token, decision \}\)/);
    expect(STORE).not.toMatch(/confirmOpsAction\(\{ token: .*decision: .*words/);
  });

  it('决定之后按钮消失（凭据一次性）', () => {
    // `!turn.pendingResult` 才渲染按钮 —— 留着它只会让人重复点、再看到"已经处理过了"
    expect(SOURCE).toContain('v-if="!turn.pendingResult"');
    expect(STORE).toMatch(/turn\.token = ''/);
  });
});

describe('待确认队列（第 428 批）', () => {
  // 第 426 批的按钮只长在"提议它的那条对话"里，刷新页面就没了 ——
  // 这一块读服务端的 `OpsPendingWrite`，是那个缺口的补丁。
  it('页面上有队列区块，且确认/取消都走 store', () => {
    expect(SOURCE).toContain('opsStore.openPending');
    expect(SOURCE).toContain("t('opsAssistant.pendingTitle'");
    expect(SOURCE).toMatch(/@click="decideRow\(row, 'confirm'\)"/);
    expect(SOURCE).toMatch(/@click="decideRow\(row, 'cancel'\)"/);
    expect(SOURCE).toContain('opsStore.confirmToken(row.token, decision)');
  });

  it('进页面就取队列（刷新后靠它找回凭据）', () => {
    expect(SOURCE).toContain('opsStore.loadPending()');
    expect(STORE).toContain('fetchOpsPending');
    expect(STORE).toContain('openPending');
  });

  it('观测卡片显示待确认数（接口第 427 批就有，界面第 428 批才有）', () => {
    expect(SOURCE).toContain('stats.totals.pending_confirmations');
    expect(SOURCE).toContain("t('opsAssistant.statsPending')");
  });
});
