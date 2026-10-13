<template>
  <!--
    「用户管理」合并页（第 184 批）
    ============================================================================
    把「用户管理」与「识别记录」两个侧栏项合成**一个入口、两个页签**：
    它们同属 `USER_ADMIN` 能力，本来就是一件事（都是"账号与他人数据"）。

    设计取舍（重要）：
      本批**不去拆分**两个既有页面的内部结构 —— Hub 只做"装进去"，
      `AdminUsersView` / `AdminDetectionHistoryView` 原样保留、行为不变。
      理由是上一批（内容管理）的教训：把页面内容搬成子组件是一大坨改动，
      一旦中途出问题就会留下半成品。所以这里先做到"一个入口两个页签"，
      内部拆分留作后续批次（需要时再做）。

    两个细节：
      · 页签用 `lazy`：只有切到某个页签才挂载它（避免一进页面就同时打两边的接口）；
      · `?tab=` 与页签双向同步，旧的 `/admin/detection-history` 也重定向到这里。
  -->
  <div class="user-hub">
    <el-tabs v-model="activeTab" class="user-hub-tabs" @tab-change="syncQuery">
      <el-tab-pane :label="t('userHub.tabUsers')" name="users" lazy>
        <AdminUsersView />
      </el-tab-pane>
      <el-tab-pane :label="t('userHub.tabDetections')" name="detections" lazy>
        <AdminDetectionHistoryView />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script>
/**
 * 用户管理合并页（第 184 批）
 *
 * 只负责三件事：页签、`?tab=` 同步、按 URL 决定初始页签。
 * **不含任何业务逻辑** —— 业务仍在两个既有页面里（本批刻意不动它们）。
 */
import { ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import AdminUsersView from '@/views/AdminUsersView.vue';
import AdminDetectionHistoryView from '@/views/AdminDetectionHistoryView.vue';
import { useI18n } from '@/i18n';

const TAB_USERS = 'users';
const TAB_DETECTIONS = 'detections';
const VALID_TABS = [TAB_USERS, TAB_DETECTIONS];

export default {
  name: 'AdminUserHubView',
  components: { AdminUsersView, AdminDetectionHistoryView },
  setup() {
    const { t } = useI18n();
    const route = useRoute();
    const router = useRouter();

    /** URL 里的 tab 优先；非法值一律回落「用户」 */
    const readTab = () => {
      const value = String(route.query.tab || '');
      return VALID_TABS.includes(value) ? value : TAB_USERS;
    };

    const activeTab = ref(readTab());

    /** 页签变化 → 写回 URL（replace，不往历史里堆一堆） */
    const syncQuery = (name) => {
      const tab = VALID_TABS.includes(name) ? name : TAB_USERS;
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
.user-hub {
  padding: 0 4px;
}

.user-hub-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
</style>
