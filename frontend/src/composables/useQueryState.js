/**
 * 把筛选条件与分页写进 URL（第 98 批）
 * ============================================================================
 * 解决的问题：管理页的筛选/分页原来只存在组件内存里。后果有三个，都很日常：
 *   · **刷新即重置** —— 筛了"待处理 + 意见反馈"，按 F5 回到全部；
 *   · **后退丢条件** —— 点进一条详情再按浏览器后退，筛选没了，得重新筛一遍；
 *   · **不能分享** —— 想把"这一页待审帖"发给同事，只能口头描述怎么筛。
 *
 * 做法：双向同步（local refs ⇄ `route.query`）。
 *   · 用户改筛选 → 写 URL（`router.replace`，不新增历史记录 —— 每敲一个字都压一条
 *     历史会让"后退"变成退格键，反而更难用）；
 *   · URL 变（后退/前进/手改地址/别人发来的链接）→ 写回 local refs。
 *
 * 为什么不用 `router.push`：筛选项是**页面状态**，不是"去过哪一页"。
 * 想要"后退回到上一次筛选"的场景本来就少，而按键逐次入栈会把前进/后退毁掉。
 *
 * 用法：
 *   const { isReady } = useQueryState({
 *     fields: {
 *       page: { ref: page, type: 'int', default: 1 },
 *       search: { ref: filters.value.search, type: 'string' },
 *     },
 *     onExternalChange: () => loadList(),
 *   });
 *   watch(isReady, (ok) => { if (ok) loadList(); }, { immediate: true });
 */
import { nextTick, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

/** 只在值"真的不一样"时才写 URL 的比较（数组按内容比） */
function sameValue(a, b) {
  if (Array.isArray(a) || Array.isArray(b)) {
    const arrA = Array.isArray(a) ? a : [a];
    const arrB = Array.isArray(b) ? b : [b];
    return arrA.length === arrB.length && arrA.every((item, i) => String(item) === String(arrB[i]));
  }
  return String(a ?? '') === String(b ?? '');
}

function parseValue(raw, type, fallback) {
  if (raw === undefined || raw === null || raw === '') return fallback;
  if (Array.isArray(raw)) raw = raw[0];        // 同一个参数出现多次时取第一个
  if (type === 'int') {
    const n = Number.parseInt(String(raw), 10);
    return Number.isFinite(n) ? n : fallback;
  }
  if (type === 'bool') return String(raw) === 'true' || String(raw) === '1';
  return String(raw);
}

function serializeValue(value, fallback) {
  // 等于默认值的参数**不写进 URL** —— 地址栏保持干净：
  // /admin/users 而不是 /admin/users?page=1&search=&role=&status=
  if (value === undefined || value === null || value === '') return undefined;
  if (value === fallback) return undefined;
  if (typeof value === 'boolean') return value ? '1' : undefined;
  return String(value);
}

/**
 * @param {{
 *   fields: Record<string, { ref: any, type?: 'string'|'int'|'bool', default?: any }>,
 *   onExternalChange?: () => void,
 * }} options
 * @returns {{ isReady: import('vue').Ref<boolean> }}
 */
export function useQueryState({ fields = {}, onExternalChange } = {}) {
  const route = useRoute();
  const router = useRouter();
  // 初始化期间不要触发"外部变化"回调（否则挂载时会加载两次）
  const isReady = ref(false);
  let applying = false;

  const entries = Object.entries(fields);

  const defaults = () => {
    const out = {};
    for (const [key, cfg] of entries) out[key] = cfg.default ?? (cfg.type === 'int' ? 1 : '');
    return out;
  };

  /** URL → refs（后退/前进/打开带参数的链接） */
  const applyFromRoute = () => {
    const fallback = defaults();
    applying = true;
    for (const [key, cfg] of entries) {
      const next = parseValue(route.query[key], cfg.type, fallback[key]);
      if (!sameValue(cfg.ref.value, next)) cfg.ref.value = next;
    }
    applying = false;
  };

  /** refs → URL */
  const pushToRoute = async () => {
    if (applying) return;
    const fallback = defaults();
    const nextQuery = { ...route.query };
    let changed = false;

    for (const [key, cfg] of entries) {
      const serialized = serializeValue(cfg.ref.value, fallback[key]);
      const current = route.query[key];
      if (serialized === undefined) {
        if (current !== undefined) { delete nextQuery[key]; changed = true; }
      } else if (!sameValue(current, serialized)) {
        nextQuery[key] = serialized;
        changed = true;
      }
    }
    if (!changed) return;
    // replace 而不是 push：见文件头说明（筛选是页面状态，不该压历史记录）
    await router.replace({ query: nextQuery });
  };

  // 立即用 URL 初始化一次（这样"带参数打开链接"能直接生效）
  applyFromRoute();

  // URL 变化 → refs
  //
  // ⚠️ 这里有个**写回环**的坑（第 100 批实测）：把 refs 推到 URL（`router.replace`）后，
  //    `route.query` 也会变，于是这个 watcher 又会跑一次 `applyFromRoute()` ——
  //    它读的是**旧 URL** 的快照，会把刚写进去的值**覆盖回去**，表现为
  //    "第二次点表头没反应、地址栏又变回上一次的值"。
  //    解法：只有 URL 里的值**和当前 refs 确实不同**时才回写（并认为是"外部变化"）。
  const routeDiffersFromRefs = () => {
    const fallback = defaults();
    return entries.some(([key, cfg]) => {
      const fromUrl = parseValue(route.query[key], cfg.type, fallback[key]);
      return !sameValue(cfg.ref.value, fromUrl);
    });
  };

  watch(() => route.query, () => {
    if (!routeDiffersFromRefs()) return;   // 是我们自己刚写进去的，忽略
    applyFromRoute();
    if (isReady.value && typeof onExternalChange === 'function') onExternalChange();
  });

  // refs 变化 → URL（静默写，不触发外部回调）
  watch(
    () => entries.map(([, cfg]) => cfg.ref.value),
    () => {
      if (!isReady.value) return;
      nextTick(() => { pushToRoute(); });
    },
  );

  // 初始化完成：让调用方在这之后才开始加载数据（避免一进页面加载两次）
  nextTick(() => { isReady.value = true; });

  return { isReady };
}
