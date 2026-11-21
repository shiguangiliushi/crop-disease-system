/**
 * 系统助手（管理端运维侧）接口
 *
 * 三个接口，同一个问题：
 *   · `POST /api/admin/assistant/ops/ask/`        —— 一次返回完整答案
 *   · `POST /api/admin/assistant/ops/ask/stream/` —— SSE，逐段返回（**页面用这个**）
 *   · `POST /api/admin/assistant/ops/confirm/`    —— 确认 / 取消一条**不可逆**写（第 426 批）
 *
 * 三个后端约定（页面必须照做，否则会把"答得保守"显示成报错）：
 *
 *  1. **降级也是 200**。`degraded=true` 表示"没调模型 / 调模型失败 / 数字没通过校验"，
 *     不是请求失败 —— 答案照样有内容（工具返回的原始表格），只是要加一句提示。
 *  2. 真正的失败只有 400（参数错）/ 401（未登录）/ 403（不是全权管理员）/ 429（限流）。
 *  3. 流式下 **`done.answer` 是权威答案**：数值校验在结束时做，不通过会换成表格 ——
 *     逐字拼接的结果只是"过程"。所以前端收到 `done` 必须**整体替换**已渲染的文本，
 *     否则用户会看到一段被判定为不可信的答案。
 *
 * ## `pending` / `token`（第 426 批）
 *
 * 回答里出现 `pending` 时，说明这条写操作**不可逆**、**还没有执行**：
 * 后端只落了一行待确认记录并把一次性 `token` 交回来。真正执行要调 `confirmOpsAction()`，
 * 那一步不经过模型 —— 确认的判定是后端纯函数（`ops/pending.is_confirm()`），
 * 不是"AI 觉得你说的是确认"。
 *
 * `token` 一次性：确认过、取消过、过期（10 分钟）之后再提交都会被拒（`ok=false`），
 * 前端不要把它当成"可以重试的请求"。
 *
 * 会话不落库：`history` 由页面持有，最多带最近 8 条（后端只取最近几轮）。
 */
import { baseURL } from './http';
import { useAuthStore } from '@/stores/auth';

/**
 * 问一次系统状态（一次返回完整答案）
 *
 * @param {object} payload
 * @param {string} payload.question   问题（后端上限 2000 字，闸门另有 500 字软上限）
 * @param {Array<{role: string, content: string}>} [payload.history] 最近几轮
 * @returns {Promise<{answer, intent, tools, degraded, degrade_reason, verified, evidence, usage, latency_ms}>}
 */
export async function askOpsAssistant({ question, history, lang = 'zh' } = {}) {
  const authStore = useAuthStore();
  const response = await fetch(`${baseURL}/admin/assistant/ops/ask/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(authStore.authToken ? { Authorization: `Token ${authStore.authToken}` } : {}),
    },
    body: JSON.stringify({ question, history, lang }),
  });
  if (!response.ok) throw await httpError(response);
  return response.json();
}

/**
 * 问一次系统状态（SSE 逐段返回）
 *
 * `onDelta(text)` 收增量；`onDelta(null, finalAnswer)` 表示"定稿，请整体替换"。
 * 这个双参数约定与农户侧的 `askAssistantStream` 一致 —— 两处不要写成两种。
 *
 * @returns {Promise<{answer, intent, tools, degraded, degrade_reason, verified, evidence, usage, latency_ms}>}
 */
export async function askOpsAssistantStream({ question, history, lang = 'zh' } = {}, { onDelta } = {}) {
  const authStore = useAuthStore();
  const response = await fetch(`${baseURL}/admin/assistant/ops/ask/stream/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(authStore.authToken ? { Authorization: `Token ${authStore.authToken}` } : {}),
    },
    body: JSON.stringify({ question, history, lang }),
  });
  if (!response.ok) throw await httpError(response);
  if (!response.body) throw new Error('当前环境不支持流式响应（response.body 为空）');

  const result = {
    answer: '', intent: '', tools: [],
    degraded: false, degrade_reason: '', verified: true,
    evidence: [], usage: {}, latency_ms: 0,
    //: 第 426 批：不可逆写的提议（`pending` 非空 = 还没执行，等管理员确认）
    pending: null, token: '',
  };

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const handleEvent = (rawEvent) => {
    let eventName = 'message';
    let dataLine = '';
    for (const line of rawEvent.split('\n')) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLine += line.slice(5).trim();
    }
    if (!dataLine) return;
    let data = null;
    try {
      data = JSON.parse(dataLine);
    } catch {
      return;   // 解析不了就跳过这一段，不让整个回答炸掉
    }

    if (eventName === 'meta') {
      result.intent = data.intent || '';
      result.tools = Array.isArray(data.tools) ? data.tools : [];
      result.degraded = Boolean(data.degraded);
      result.degrade_reason = data.degrade_reason || '';
    } else if (eventName === 'delta') {
      const text = data.text || '';
      result.answer += text;
      if (text && onDelta) onDelta(text);
    } else if (eventName === 'done') {
      // ⚠️ 以 done 为准：数值校验不过时它带的是**换过的表格**
      result.answer = typeof data.answer === 'string' ? data.answer : result.answer;
      result.intent = data.intent || result.intent;
      result.tools = Array.isArray(data.tools) ? data.tools : result.tools;
      result.degraded = Boolean(data.degraded);
      result.degrade_reason = data.degrade_reason || '';
      result.verified = data.verified !== false;
      result.evidence = Array.isArray(data.evidence) ? data.evidence : [];
      result.usage = data.usage || {};
      result.latency_ms = data.latency_ms || 0;
      //: 第 426 批：提议 + 一次性凭据。**必须在 done 里取** —— meta 阶段还没提出写。
      result.pending = data.pending || null;
      result.token = data.token || '';
      if (onDelta) onDelta(null, result.answer);
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index = buffer.indexOf('\n\n');
    while (index >= 0) {
      handleEvent(buffer.slice(0, index));
      buffer = buffer.slice(index + 2);
      index = buffer.indexOf('\n\n');
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) handleEvent(buffer);

  return result;
}

/**
 * 确认 / 取消一条**不可逆**写操作（第 426 批）
 *
 * 只做"把 token 交回去 + 说一句要不要做"：**没有模型参与**，也没有自然语言解析 ——
 * 后端只认 `confirm` / `cancel` 两个词（`ops/pending.CONFIRM_WORDS`）。
 *
 * @param {{token: string, decision?: 'confirm'|'cancel'}} payload
 * @returns {Promise<{ok: boolean, status: string, reason?: string, answer: string, token: string}>}
 *   `status` ∈ `confirmed` / `cancelled` / `expired` / `failed` / `rejected`；
 *   失败也是 **200**（`ok=false` + `reason`），只有参数错才 400。
 */
export async function confirmOpsAction({ token, decision = 'confirm' } = {}) {
  const authStore = useAuthStore();
  const response = await fetch(`${baseURL}/admin/assistant/ops/confirm/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(authStore.authToken ? { Authorization: `Token ${authStore.authToken}` } : {}),
    },
    body: JSON.stringify({ token, decision }),
  });
  if (!response.ok) throw await httpError(response);
  return response.json();
}

/**
 * 系统助手的质量看板（E）
 *
 * 与农户侧的 `/admin/assistant/stats/` 是两份数据：那边看 RAG 问答，
 * 这边看**系统助手自己**的降级率、数字未校验率、意图分布、工具失败。
 *
 * @param {{ days?: number }} params 时间窗（后端上限 90 天）
 * @returns {Promise<{range, totals, by_reason, by_intent, tool_failures, recent_unverified}>}
 */
export async function fetchOpsAssistantStats({ days = 7, lang = 'zh' } = {}) {
  const authStore = useAuthStore();
  const response = await fetch(
    `${baseURL}/admin/assistant/ops/stats/?days=${encodeURIComponent(days)}&lang=${encodeURIComponent(lang)}`,
    {
      headers: {
        Accept: 'application/json',
        ...(authStore.authToken ? { Authorization: `Token ${authStore.authToken}` } : {}),
      },
    },
  );
  if (!response.ok) throw await httpError(response);
  return response.json();
}

/** 把非 2xx 的响应包成带 `response.status` / `response.data` 的错误（`formatApiError` 认得） */
async function httpError(response) {
  const error = new Error(`HTTP ${response.status}`);
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;   // 不是 JSON（比如代理返回的 HTML）就只留状态码
  }
  error.response = { status: response.status, data };
  return error;
}
