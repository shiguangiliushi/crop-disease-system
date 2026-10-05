/**
 * 「有未保存的修改，确定要离开吗？」—— 第 97 批
 * ============================================================================
 * 背景：全项目原来只有 `EditPostView` 一个页面挂了 `beforeunload`，而且它**只管一半**：
 *
 *   · `beforeunload` 只在**刷新 / 关标签 / 关浏览器**时触发；
 *   · 用户点站内链接（导航栏、"返回"按钮、列表页的分页…）走的是 vue-router，
 *     **根本不会触发 `beforeunload`** —— 表单填了一半，一点"论坛"就没了，
 *     没有任何提示。
 *
 * 现实里后者才是主要场景（站内导航比关标签页常见得多），所以这个 composable
 * 两件事都做：
 *   1. 注册 `beforeunload`（离开站点时用浏览器原生确认框）；
 *   2. 注册一个**路由守卫**（站内导航时用 Element Plus 的确认框）。
 *
 * 站点级守卫（`registerLeaveGuard`）：
 *   路由守卫是全局的，而"有没有未保存内容"是组件内的状态，所以这里用一个**极小的
 *   注册表**把它们接起来：组件挂载时注册一个 `shouldBlock()`，卸载时注销。
 *   `router/index.js` 的 `beforeEach` 开头调用 `runLeaveGuards()`。
 *
 * 用法：
 *   const { isDirty, markClean } = useUnsavedChanges(
 *     () => form.title !== original.title || form.content !== original.content,
 *     { messageKey: 'post.leaveConfirm' },   // 可选，默认 common.unsavedConfirm
 *   );
 *   // 保存成功后：markClean()  （或者直接改回原值，dirty 会自动变 false）
 *
 * 一个刻意的设计：**判定函数是"算出来"的，不是"设个 flag"**。
 *   用 flag 就得在每个输入框上挂 @input 去置脏，漏一个就失效；
 *   传一个比较函数（和原值比）几乎不会漏，也不会因为"改回原样"而误报。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { ElMessageBox } from 'element-plus';
import { t } from '@/i18n';

/** 已注册的守卫（按注册顺序执行，第一个返回 true 的就拦下导航） */
const leaveGuards = new Set();

/**
 * 注册一个"离开前是否要拦"的判定函数。
 * @param {() => boolean} shouldBlock
 * @returns {() => void} 注销函数
 */
export function registerLeaveGuard(shouldBlock) {
  leaveGuards.add(shouldBlock);
  return () => leaveGuards.delete(shouldBlock);
}

/**
 * 供 `router.beforeEach` 调用：如果有守卫要拦，弹确认框。
 *
 * @returns {Promise<boolean>} true = 可以离开；false = 用户选择留下
 */
export async function runLeaveGuards() {
  if (leaveGuards.size === 0) return true;

  // 任一守卫报"有未保存内容"就拦（多个表单同时脏的情况极少，取第一个即可）
  let blocked = false;
  for (const shouldBlock of leaveGuards) {
    try {
      if (shouldBlock()) { blocked = true; break; }
    } catch (error) {
      // 守卫本身出错不该卡住导航（宁可放行，也不要让人困在页面里）
      console.warn('[useUnsavedChanges] 守卫执行出错，已忽略：', error);
    }
  }
  if (!blocked) return true;

  try {
    await ElMessageBox.confirm(
      t('common.unsavedConfirm'),
      t('common.unsavedConfirmTitle'),
      {
        type: 'warning',
        confirmButtonText: t('common.unsavedLeave'),
        cancelButtonText: t('common.unsavedStay'),
        // 点遮罩等于"留下"：让"误点"的代价是留在原地，而不是丢掉内容
        closeOnClickModal: false,
        distinguishCancelAndClose: true,
      },
    );
    return true;              // 点了"离开"
  } catch {
    return false;             // 取消 / 关闭
  }
}

/**
 * 组件级：登记"未保存内容"，并接管刷新/关闭提示。
 *
 * @param {() => boolean} isDirtyFn 返回 true 表示当前有未保存的修改
 * @param {{ messageKey?: string, enabled?: () => boolean }} [options]
 *        `enabled` 返回 false 时一律视为"干净"（弹窗编辑用：只有弹窗开着才拦）
 * @returns {{ isDirty: import('vue').Ref<boolean>, markClean: () => void, markDirty: () => void }}
 */
export function useUnsavedChanges(isDirtyFn, options = {}) {
  const message = t(options.messageKey || 'post.leaveConfirm');
  const isDirty = ref(false);
  // 手动强制标记（有些页面"保存中"期间希望临时别拦）
  const forcedDirty = ref(false);
  /**
   * 主动开关（可选）：返回 false 时一律视为"干净"。
   * 用途：弹窗式编辑（例如"编辑资料"对话框）—— 只有**弹窗打开时**才需要拦，
   * 平时浏览页面不该因为"用户资料和草稿不一致"被拦下来。
   */
  const isEnabled = () => (typeof options.enabled === 'function' ? Boolean(options.enabled()) : true);

  const evaluate = () => {
    try {
      isDirty.value = isEnabled() && (forcedDirty.value || Boolean(isDirtyFn?.()));
    } catch (error) {
      console.warn('[useUnsavedChanges] 判定函数出错，按"无修改"处理：', error);
      isDirty.value = false;
    }
  };

  // 判定函数通常依赖响应式表单字段；每次渲染都算一遍太浪费，但也不能监听不到变化 ——
  // 这里用一个极短周期的 computed 式轮询是没必要的，改为：让调用方在输入时自然触发
  // 组件重渲染，我们则在**关键时机**求值（挂载、路由离开、beforeunload）。
  // 为了让"脏了但没触发任何事件"的情况也能被拦，这里再加一个轻量定时器兜底。
  let timer = null;

  const handleBeforeUnload = (event) => {
    evaluate();
    if (!isDirty.value) return undefined;
    // 浏览器只允许通过 returnValue 定制文案（现代浏览器显示的是通用提示）
    event.preventDefault();
    event.returnValue = message;
    return message;
  };

  let unregister = null;

  onMounted(() => {
    evaluate();
    unregister = registerLeaveGuard(() => {
      evaluate();
      return isDirty.value;
    });
    window.addEventListener('beforeunload', handleBeforeUnload);
    // 兜底轮询：2 秒一次，只做一次浅比较，开销可忽略
    timer = setInterval(evaluate, 2000);
  });

  onBeforeUnmount(() => {
    if (unregister) unregister();
    window.removeEventListener('beforeunload', handleBeforeUnload);
    if (timer) clearInterval(timer);
  });

  // 调用方也可以直接 watch 自己的字段来调 evaluate（这里额外暴露一下）
  watch(isDirtyFn ?? (() => false), evaluate);

  return {
    isDirty,
    markClean: () => { forcedDirty.value = false; isDirty.value = false; },
    markDirty: () => { forcedDirty.value = true; isDirty.value = true; },
  };
}
