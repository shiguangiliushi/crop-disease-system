<template>
  <!--
    「系统」合并页（第 185 批建，第 186 批扩成三个页签）
    ============================================================================
    一个入口、三个页签，**页签按权限画**：

    | 页签 | 谁能看到 | 依据（后端同口径） |
    |---|---|---|
    | `health` 系统健康 | **仅全权管理员** | `/api/admin/health/` 是 `is_full_admin` |
    | `audit` 操作日志 | **仅全权管理员** | `/api/admin/audit-logs/` 是 `is_full_admin` |
    | `boards` 版块管理 | 全权管理员 **或** BROADCAST 能力 | `/api/forums/boards/` 写接口是 `IsBroadcastManager` |

    ⚠️ 第 186 批的核心就在这里：**只有 BROADCAST、不是全权管理员**的人（能发公告/
    管版块的那一档）现在也进得来这一页 —— 但他**只看到「版块管理」一个页签**，
    系统健康与操作日志**不画给他**。理由与第 183 批「举报页签」完全相同：
    页签也是入口，点进去必然 403 的东西不该出现在界面上。
    反过来也一样：这两条接口是 `is_full_admin`，所以绝不能因为"他在这一页上"
    就顺手把 health/audit 画给 BROADCAST 的人。

    设计取舍（与前两批的合并页一致）：
      本批**不拆分**三个既有页面的内部结构 —— Hub 只做"装进去"，
      `AdminHealthView` / `AdminAuditLogView` / `AdminBoardsView` 原样保留、行为不变。

    两个细节：
      · 页签带 `lazy`：只有切到某个页签才挂载它（避免一进页面就同时打三边的接口）；
      · `?tab=` 与页签双向同步，非法值或**指向无权页签**的值一律回落到
        他有权看到的第一个页签，并把地址栏修正过来（否则刷新/分享会一直带着一个
        看不到的 tab）；旧的 `/admin/boards` 也重定向到这里（带 tab=boards）。

    ⚠️ 三个页面的筛选参数**不冲突**：`AdminHealthView` 不写 URL，
      `AdminAuditLogView` 的 `useQueryState`（page / search / start / end）是
      **合并式**写回（`{ ...route.query }`），所以 `tab=audit` 不会被它冲掉。
  -->
  <div class="system-hub">
    <!-- 一个页签都看不到（理论上进不来：侧栏不显示 + 路由守卫拦）——
         仍然给一句人话，而不是白屏（与内容管理页的处理一致） -->
    <el-empty v-if="!tabs.length" :description="t('systemHub.noAccess')" />

    <el-tabs v-else v-model="activeTab" class="system-hub-tabs" @tab-change="syncQuery">
      <el-tab-pane v-for="tab in tabs" :key="tab.name" :name="tab.name" lazy>
        <template #label>
          <span class="hub-tab"><i :class="tab.icon"></i> {{ t(tab.labelKey) }}</span>
        </template>
        <!-- 只挂载当前页签：否则光打开这一页就会同时请求健康 / 日志 / 版块三边 -->
        <component :is="tab.panel" v-if="activeTab === tab.name" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script>
/**
 * 系统合并页（第 185 批建，第 186 批扩成三个页签）
 *
 * 只负责四件事：页签清单（按权限算）、`?tab=` 同步、按 URL 决定初始页签、
 * 只挂载当前页签。**不含任何业务逻辑** —— 业务仍在三个既有页面里（本批刻意不动它们）。
 */
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import AdminHealthView from '@/views/AdminHealthView.vue';
import AdminAuditLogView from '@/views/AdminAuditLogView.vue';
import AdminBoardsView from '@/views/AdminBoardsView.vue';
import { useI18n } from '@/i18n';

const TAB_HEALTH = 'health';
const TAB_AUDIT = 'audit';
const TAB_BOARDS = 'boards';

export default {
  name: 'AdminSystemHubView',
  components: { AdminHealthView, AdminAuditLogView, AdminBoardsView },
  setup() {
    const { t } = useI18n();
    const route = useRoute();
    const router = useRouter();
    const authStore = useAuthStore();

    /**
     * 版块页签：全权管理员 **或** BROADCAST 能力
     *
     * 全权管理员三项能力全给（后端 `capabilities.has_capability` 对 `is_full_admin`
     * 直接返回 True），所以这里写 `isAdmin || hasCapability(BROADCAST)` 与
     * "BROADCAST 或全权管理员"是同一件事 —— 但仍然两个都写出来：
     * 读的人一眼能看出这一档**不是**只有能力，避免下一个人以为漏判了管理员。
     */
    const canBoards = computed(
      () => Boolean(authStore.isAdmin || authStore.hasCapability(authStore.CAP_BROADCAST)),
    );

    /**
     * 页签清单 —— **看不到的页签根本不在这里**（不是画出来再禁用）
     *
     * 顺序即默认落点：全权管理员从「系统健康」进（与第 185 批一致），
     * 只有 BROADCAST 的人清单里就只剩「版块管理」，自然落在它上面。
     */
    const tabs = computed(() => [
      {
        name: TAB_HEALTH,
        labelKey: 'systemHub.tabHealth',
        icon: 'fas fa-heart-pulse',
        show: Boolean(authStore.isAdmin),
        panel: AdminHealthView,
      },
      {
        name: TAB_AUDIT,
        labelKey: 'systemHub.tabAudit',
        icon: 'fas fa-clipboard-list',
        show: Boolean(authStore.isAdmin),
        panel: AdminAuditLogView,
      },
      {
        name: TAB_BOARDS,
        labelKey: 'systemHub.tabBoards',
        icon: 'fas fa-table-columns',
        show: canBoards.value,
        panel: AdminBoardsView,
      },
    ].filter((tab) => tab.show));

    /** 有权看到的第一个页签（没有可见页签时是空串） */
    const firstTab = computed(() => tabs.value[0]?.name || '');
    const validTab = (name) => tabs.value.some((tab) => tab.name === name);
    /** URL 里的 tab（同一个参数出现多次时取第一个） */
    const requestedTab = () => (Array.isArray(route.query.tab) ? route.query.tab[0] : route.query.tab);

    const activeTab = ref('');

    /** URL → 页签：非法值或**指向无权页签**的值一律回落到第一个有权页签 */
    watch(
      [() => route.query.tab, tabs],
      () => {
        const requested = requestedTab();
        const next = validTab(requested) ? requested : firstTab.value;
        if (activeTab.value !== next) activeTab.value = next;
        // 请求的页签这个人看不到（典型：只有 BROADCAST 的人打开别人的
        // `/admin/health?tab=audit` 链接）：把地址栏修正成真正显示的那个
        if (requested && requested !== next && next) {
          router.replace({ query: { ...router.currentRoute.value.query, tab: next } });
        }
      },
      { immediate: true },
    );

    /** 页签 → URL（replace，不往历史里堆一堆） */
    const syncQuery = (name) => {
      const tab = validTab(name) ? name : firstTab.value;
      if (!tab || String(route.query.tab || '') === tab) return;
      router.replace({ query: { ...route.query, tab } });
    };

    return { t, tabs, activeTab, syncQuery };
  },
};
</script>

<style scoped>
.system-hub {
  padding: 0 4px;
}

.hub-tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-weight: 600;
}

.hub-tab i {
  font-size: 13px;
}

.system-hub-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
</style>
