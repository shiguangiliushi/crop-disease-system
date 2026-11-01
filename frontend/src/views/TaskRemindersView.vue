<template>
  <div class="reminders-page">
    <header class="page-head">
      <div>
        <h1>{{ t('assistant.remindersTitle') }}</h1>
        <p class="page-sub">{{ t('assistant.remindersSubtitle') }}</p>
      </div>
      <el-button :loading="loading" @click="load">
        <i class="bi bi-arrow-clockwise me-1"></i>{{ t('assistant.remindersRefresh') }}
      </el-button>
    </header>

    <el-empty v-if="!loading && !items.length" :description="t('assistant.remindersEmpty')" />

    <el-table v-else v-loading="loading" :data="items" class="reminders-table">
      <el-table-column width="56">
        <template #default="{ row }">
          <el-checkbox :model-value="row.is_done" @change="toggle(row)" />
        </template>
      </el-table-column>
      <el-table-column :label="t('assistant.remindersColTitle')" min-width="240">
        <template #default="{ row }">
          <span :class="{ done: row.is_done }">{{ row.title }}</span>
          <el-tag v-if="row.crop_type" size="small" effect="plain" class="crop-tag">{{ row.crop_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="t('assistant.remindersColDetail')" min-width="300">
        <template #default="{ row }">
          <span class="detail-text">{{ row.detail || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="t('assistant.remindersColDate')" width="130">
        <template #default="{ row }">{{ row.due_date || t('assistant.remindersNoDate') }}</template>
      </el-table-column>
      <el-table-column width="90">
        <template #default="{ row }">
          <el-button link type="danger" @click="remove(row)">{{ t('common.delete') }}</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
/**
 * 我的农事提醒（第 316 批）
 *
 * 后端接口第 315 批就齐了（列表 / 完成 / 删除），这页只是把它露出来 ——
 * 否则"从回答加入提醒"之后，用户根本看不到自己加了什么。
 */
import { onMounted, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useI18n } from '@/i18n';
import { deleteTaskReminder, listTaskReminders, setTaskReminderDone } from '@/api/calendar';

const { t } = useI18n();
const items = ref([]);
const loading = ref(false);

const load = async () => {
  loading.value = true;
  try {
    items.value = await listTaskReminders();
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || t('assistant.remindersLoadFailed'));
  } finally {
    loading.value = false;
  }
};

const toggle = async (row) => {
  const next = !row.is_done;
  row.is_done = next; // 乐观更新：勾选立刻反馈
  try {
    await setTaskReminderDone(row.id, next);
  } catch {
    row.is_done = !next; // 失败回滚
    ElMessage.error(t('assistant.remindersUpdateFailed'));
  }
};

const remove = async (row) => {
  try {
    await ElMessageBox.confirm(
      t('assistant.remindersDeleteConfirm', { title: row.title }),
      t('assistant.remindersDeleteTitle'),
      { type: 'warning' },
    );
  } catch {
    return; // 用户取消
  }
  try {
    await deleteTaskReminder(row.id);
    items.value = items.value.filter((item) => item.id !== row.id);
    ElMessage.success(t('assistant.remindersDeleted'));
  } catch {
    ElMessage.error(t('assistant.remindersDeleteFailed'));
  }
};

onMounted(load);
</script>

<style scoped>
.reminders-page { padding: 24px 28px 40px; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; }
.page-head h1 { font-size: 1.25rem; margin: 0 0 4px; }
.page-sub { margin: 0; color: var(--ink-400, #8a8f8c); font-size: 0.86rem; }
.reminders-table { background: #fff; border-radius: 12px; }
.done { color: var(--ink-400, #9aa39f); text-decoration: line-through; }
.crop-tag { margin-left: 8px; }
.detail-text { color: var(--ink-500, #6b7472); font-size: 0.85rem; }
</style>
