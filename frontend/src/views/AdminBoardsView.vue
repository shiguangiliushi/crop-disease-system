<template>
  <div class="board-admin tinted-page">
    <!-- 页头（沿用全站 .admin-hero：深绿实底 + 白色文字） -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-table-columns"></i></span>
        <div>
          <h1>{{ t('boardAdmin.title') }}</h1>
          <p>{{ t('boardAdmin.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-button plain :loading="loading" @click="loadList">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
      </div>
    </header>

    <!-- 概览小卡 -->
    <div class="admin-stats">
      <div class="stat-tile">
        <span class="stat-tile-icon"><i class="fas fa-table-columns"></i></span>
        <div>
          <div class="stat-tile-value">{{ boards.length }}</div>
          <div class="stat-tile-label">{{ t('boardAdmin.statTotal') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--ok">
        <span class="stat-tile-icon"><i class="fas fa-circle-check"></i></span>
        <div>
          <div class="stat-tile-value">{{ activeCount }}</div>
          <div class="stat-tile-label">{{ t('boardAdmin.statActive') }}</div>
        </div>
      </div>
      <div class="stat-tile stat-tile--pending">
        <span class="stat-tile-icon"><i class="fas fa-ban"></i></span>
        <div>
          <div class="stat-tile-value">{{ boards.length - activeCount }}</div>
          <div class="stat-tile-label">{{ t('boardAdmin.statDisabled') }}</div>
        </div>
      </div>
    </div>

    <!--
      说明条：把"停用会发生什么"写在页面上
      ----------------------------------------------------------------
      版块是**农户端论坛的入口**，停用会直接影响用户能不能看到它 ——
      这种"看起来只是改个开关"的操作，最需要在动手之前把后果写在眼前。
    -->
    <el-alert type="info" :closable="false" show-icon class="board-hint">
      <p>{{ t('boardAdmin.hintDisabled') }}</p>
      <p class="board-hint-sub">{{ t('boardAdmin.hintOrder') }}</p>
    </el-alert>

    <el-skeleton v-if="loading" :rows="5" animated />

    <div v-else class="board-list">
      <div
        v-for="(board, index) in boards"
        :key="board.id"
        class="board-row"
        :class="{ 'is-off': !board.is_active }"
      >
        <span class="board-order">{{ index + 1 }}</span>

        <div class="board-main">
          <div class="board-name">
            {{ localizedField(board, 'name') }}
            <el-tag v-if="!board.is_active" size="small" type="info" effect="light">
              {{ t('boardAdmin.disabled') }}
            </el-tag>
          </div>
          <p class="board-desc">{{ localizedField(board, 'description') || t('boardAdmin.noDesc') }}</p>
          <span class="board-meta">
            {{ t('boardAdmin.postCount', { count: board.post_count || 0 }) }}
            · {{ t('boardAdmin.todayPosts', { count: board.today_posts || 0 }) }}
          </span>
        </div>

        <div class="board-actions">
          <!-- 排序：上/下移一格后把**整份顺序**提交（接口要的就是完整 orders） -->
          <el-button
            size="small"
            :disabled="index === 0 || reordering"
            :title="t('boardAdmin.moveUp')"
            @click="move(index, -1)"
          >
            <i class="fas fa-arrow-up"></i>
          </el-button>
          <el-button
            size="small"
            :disabled="index === boards.length - 1 || reordering"
            :title="t('boardAdmin.moveDown')"
            @click="move(index, 1)"
          >
            <i class="fas fa-arrow-down"></i>
          </el-button>
          <el-button
            size="small"
            :type="board.is_active ? 'warning' : 'success'"
            plain
            :loading="togglingId === board.id"
            @click="toggleStatus(board)"
          >
            {{ board.is_active ? t('boardAdmin.disableAction') : t('boardAdmin.enableAction') }}
          </el-button>
        </div>
      </div>

      <el-empty v-if="!boards.length" :description="t('boardAdmin.empty')" />
    </div>
  </div>
</template>

<script>
/**
 * 管理端「版块管理」（第 140 批）
 *
 * 补的是一个**只筛不做**的空档：后端的 `boards/<id>/set_status/`（启停）与
 * `boards/update_order/`（排序）**早就有**，但控制台里没有任何入口 ——
 * 两条接口等于死代码，而版块的启停与排序只能进 Django admin 手动改。
 * （这也正是第 138 批接口可达性审计里"界面没调用"清单中的两条。）
 *
 * 权限：BROADCAST 能力（公告 / 预警 / 敏感词 / 版块是同一档"对全体发声与系统开关"）。
 * 信息编辑员（只有内容能力）看不到本页，后端也会 403 —— 前后端同一口径。
 *
 * ⚠️ 两个刻意设计：
 *  1. **排序提交整份顺序**：接口要的是 `orders: [{id, order}, ...]`，
 *     所以上移/下移后要把当前列表重新编号一次性提交（而不是只提交一条）；
 *  2. **停用前先看后果**：页面顶部写明"停用后农户端看不到该版块"，
 *     因为农户端论坛的版块入口直接受这个开关影响。
 */
import { computed, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getForumBoards, setForumBoardStatus, updateForumBoardOrder } from '@/api/forum';
import { formatApiError } from '@/api/http';
import { useI18n } from '@/i18n';
import { useLocalized } from '@/utils/localized';

export default {
  name: 'AdminBoardsView',
  setup() {
    const { t } = useI18n();
    const { localizedField } = useLocalized();

    const boards = ref([]);
    const loading = ref(false);
    const togglingId = ref(null);
    const reordering = ref(false);

    const activeCount = computed(() => boards.value.filter((b) => b.is_active).length);

    const loadList = async () => {
      loading.value = true;
      try {
        const data = await getForumBoards();
        // 接口对版块管理者会连**停用的**一起返回（农户端只看得到启用的）
        boards.value = Array.isArray(data) ? [...data] : [...(data?.results || [])];
        boards.value.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
      } catch (error) {
        ElMessage.error(formatApiError(error, t('boardAdmin.loadFailed')));
      } finally {
        loading.value = false;
      }
    };

    const toggleStatus = async (board) => {
      const turningOff = board.is_active;
      try {
        await ElMessageBox.confirm(
          t(turningOff ? 'boardAdmin.disableConfirm' : 'boardAdmin.enableConfirm',
            { name: localizedField(board, 'name') }),
          t(turningOff ? 'boardAdmin.disableAction' : 'boardAdmin.enableAction'),
          {
            type: turningOff ? 'warning' : 'info',
            confirmButtonText: t(turningOff ? 'boardAdmin.disableAction' : 'boardAdmin.enableAction'),
            cancelButtonText: t('common.cancel'),
          },
        );
      } catch {
        return;   // 用户点了取消
      }
      togglingId.value = board.id;
      try {
        const data = await setForumBoardStatus(board.id, !turningOff);
        board.is_active = data?.is_active ?? !turningOff;
        ElMessage.success(t(turningOff ? 'boardAdmin.disabledOk' : 'boardAdmin.enabledOk',
          { name: localizedField(board, 'name') }));
      } catch (error) {
        ElMessage.error(formatApiError(
          error, t(turningOff ? 'boardAdmin.disableFailed' : 'boardAdmin.enableFailed')));
      } finally {
        togglingId.value = null;
      }
    };

    /** 上移/下移一格：本地换位后把**整份顺序**提交给接口 */
    const move = async (index, delta) => {
      const target = index + delta;
      if (target < 0 || target >= boards.value.length) return;
      const next = [...boards.value];
      [next[index], next[target]] = [next[target], next[index]];
      reordering.value = true;
      try {
        // order 从 1 开始重新编号：与后端默认排序（order, -created_at）一致，
        // 也避免历史数据里 order 全是 0 时"排了却没变化"
        const orders = next.map((board, i) => ({ id: board.id, order: i + 1 }));
        await updateForumBoardOrder(orders);
        boards.value = next.map((board, i) => ({ ...board, order: i + 1 }));
        ElMessage.success(t('boardAdmin.orderOk'));
      } catch (error) {
        ElMessage.error(formatApiError(error, t('boardAdmin.orderFailed')));
        await loadList();   // 失败就以后端为准，别让界面停在错的顺序上
      } finally {
        reordering.value = false;
      }
    };

    loadList();

    return {
      t,
      boards,
      loading,
      togglingId,
      reordering,
      activeCount,
      localizedField,
      loadList,
      toggleStatus,
      move,
    };
  },
};
</script>

<style scoped>
.board-hint {
  margin-bottom: 14px;
}

.board-hint p {
  margin: 0;
  line-height: 1.7;
}

.board-hint-sub {
  margin-top: 4px !important;
  font-size: 12.5px;
  opacity: 0.85;
}

.board-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.board-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #fff;
}

/* 停用的版块整行压暗：一眼能看出哪些农户端看不到 */
.board-row.is-off {
  background: var(--ink-50);
  opacity: 0.75;
}

.board-order {
  flex: 0 0 28px;
  font-weight: 700;
  color: var(--ink-400, #9dada5);
  text-align: center;
}

.board-main {
  flex: 1 1 auto;
  min-width: 0;
}

.board-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ink-800);
}

.board-desc {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--ink-500, #78897f);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.board-meta {
  display: inline-block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--ink-400, #9dada5);
}

.board-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
