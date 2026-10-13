<template>
  <!--
    「系统」合并页（第 185 批）
    ============================================================================
    把「系统健康」与「操作日志」两个侧栏项合成**一个入口、两个页签**：
    它们同属"这台机器怎么样、谁对它做了什么"，也都是**仅全权管理员**可见
    （后端 `is_full_admin`，见 backend/api/role_matrix.py 的 FULL_ADMIN_PAGES）。

    设计取舍（与第 184 批的「用户管理」合并页一致）：
      本批**不去拆分**两个既有页面的内部结构 —— Hub 只做"装进去"，
      `AdminHealthView` / `AdminAuditLogView` 原样保留、行为不变。
      理由是第 183 批的教训：把页面内容搬成子组件是一大坨改动，
      一旦中途出问题就会留下半成品。内部拆分留作后续批次（需要时再做）。

    两个细节：
      · 页签用 `lazy`：只有切到某个页签才挂载它（避免一进页面就同时打两边的接口）；
      · `?tab=` 与页签双向同步，旧的 `/admin/audit-logs` 也重定向到这里（带 tab=audit）。

    ⚠️ 两个页面的筛选参数**不冲突**：`AdminHealthView` 不写 URL，
      `AdminAuditLogView` 的 `useQueryState`（page / search / start / end）是
      **合并式**写回（`{ ...route.query }`），所以 `tab=audit` 不会被它冲掉。
  -->
  <div class="system-hub">
    <el-tabs v-model="activeTab" class="system-hub-tabs" @tab-change="syncQuery">
      <el-tab-pane :label="t('systemHub.tabHealth')" name="health" lazy>
        <AdminHealthView />
      </el-tab-pane>
      <el-tab-pane :label="t('systemHub.tabAudit')" name="audit" lazy>
        <AdminAuditLogView />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script>
/**
 * 系统合并页（第 185 批）
 *
 * 只负责三件事：页签、`?tab=` 同步、按 URL 决定初始页签。
 * **不含任何业务逻辑** —— 业务仍在两个既有页面里（本批刻意不动它们）。
 */
import { ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import AdminHealthView from '@/views/AdminHealthView.vue';
import AdminAuditLogView from '@/views/AdminAuditLogView.vue';
import { useI18n } from '@/i18n';

const TAB_HEALTH = 'health';
const TAB_AUDIT = 'audit';
const VALID_TABS = [TAB_HEALTH, TAB_AUDIT];

export default {
  name: 'AdminSystemHubView',
  components: { AdminHealthView, AdminAuditLogView },
  setup() {
    const { t } = useI18n();
    const route = useRoute();
    const router = useRouter();

    /** URL 里的 tab 优先；非法值一律回落「系统健康」 */
    const readTab = () => {
      const value = String(route.query.tab || '');
      return VALID_TABS.includes(value) ? value : TAB_HEALTH;
    };

    const activeTab = ref(readTab());

    /** 页签变化 → 写回 URL（replace，不往历史里堆一堆） */
    const syncQuery = (name) => {
      const tab = VALID_TABS.includes(name) ? name : TAB_HEALTH;
      if (String(route.query.tab || '') === tab) return;
      router.replace({ query: { ...route.query, tab } });
    };

    /** 外部改 URL（比如从旧地址跳过来）→ 跟着切页签 */
    watch(() => route.query.tab, () => {
      const next = readTab();
      if (next !== activeTab.value) activeTab.value = next;
    });

    return { t, activeTab, syncQuery };
  },
};
</script>

<style scoped>
.system-hub {
  padding: 0 4px;
}

.system-hub-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
</style>
