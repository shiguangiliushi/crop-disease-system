<template>
  <div class="calendar-page">
    <!-- 页头 -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-calendar-days"></i></span>
        <div>
          <h1>{{ t('calendar.title') }}</h1>
          <p>{{ t('calendar.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-select v-model="crop" size="default" class="crop-select" @change="load">
          <el-option value="all" :label="t('calendar.allCrops')" />
          <el-option v-for="item in crops" :key="item" :value="item" :label="cropLabel(item)" />
        </el-select>
        <el-button plain :loading="loading" @click="load">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
      </div>
    </header>

    <!-- 月份切换 -->
    <div class="month-bar">
      <button type="button" class="month-nav" @click="changeMonth(-1)">
        <i class="fas fa-chevron-left"></i> {{ t('calendar.prevMonth') }}
      </button>
      <div class="month-title">
        <strong>{{ month }}</strong>
        <span v-if="isCurrentMonth" class="month-now">{{ t('calendar.currentMonth') }}</span>
      </div>
      <button type="button" class="month-nav" @click="changeMonth(1)">
        {{ t('calendar.nextMonth') }} <i class="fas fa-chevron-right"></i>
      </button>
      <div class="month-quick">
        <button
          v-for="item in quickMonths"
          :key="item"
          type="button"
          class="quick-chip"
          :class="{ 'is-active': month === item }"
          @click="jumpMonth(item)"
        >
          {{ item }}
        </button>
      </div>
    </div>

    <el-skeleton v-if="loading" :rows="8" animated />

    <template v-else>
      <!-- 我的作物 -->
      <div v-if="myCrops.length" class="my-crops">
        <span class="my-crops-label"><i class="fas fa-seedling"></i> {{ t('calendar.myCrops') }}</span>
        <button
          v-for="item in myCrops"
          :key="item"
          type="button"
          class="crop-chip"
          :class="{ 'is-active': crop === item }"
          @click="filterByCrop(item)"
        >
          {{ cropLabel(item) }}
        </button>
      </div>

      <!-- ⚠️ 第 216 批：**月历网格**。
           格子里标的是"这一天有几天识别记录"，**不是**排定在那天的农事任务 ——
           `CalendarTask` 只有月份粒度、没有日期，把任务摆进格子就是编数据。
           所以 `gridHint` 把口径明确写给用户，避免被误读成日程表。 -->
      <section v-if="!loading" class="panel-card grid-card">
        <div class="panel-head">
          <span class="panel-icon"><i class="fas fa-calendar-week"></i></span>
          <h2 class="panel-title">{{ t('calendar.gridTitle', { month }) }}</h2>
          <span v-if="activitySummary.total" class="panel-count">
            {{ t('calendar.gridSummary', { days: activitySummary.days, count: activitySummary.total }) }}
          </span>
        </div>
        <div class="panel-body">
          <p class="grid-hint">
            <i class="fas fa-circle-info"></i> {{ t('calendar.gridHint') }}
          </p>

          <div class="month-grid">
            <div v-for="(label, i) in weekdayLabels" :key="`wh-${i}`" class="grid-weekday">
              {{ label }}
            </div>
            <div
              v-for="cell in monthGrid.flat()"
              :key="cell.key"
              class="grid-day"
              :class="{ 'is-pad': cell.pad, 'is-today': cell.today, 'is-mine': cell.mine, 'has-data': cell.count > 0 }"
            >
              <template v-if="!cell.pad">
                <span class="grid-day-num">{{ cell.day }}</span>
                <span class="grid-dots">
                  <i v-for="d in cell.dots" :key="`dot-${cell.day}-${d}`" class="grid-dot"></i>
                  <span v-if="cell.overflow" class="grid-overflow">+{{ cell.overflow }}</span>
                </span>
                <span v-if="cell.count" class="grid-count">{{ cell.count }}</span>
                <i v-if="cell.mine" class="fas fa-user grid-mine-mark" :title="t('calendar.gridMine')"></i>
              </template>
            </div>
          </div>

          <p v-if="!activitySummary.total" class="grid-empty">
            {{ t('calendar.gridNoData', { month }) }}
          </p>
          <p v-else class="grid-legend">
            <span class="legend-item"><i class="grid-dot"></i> {{ t('calendar.gridLegendDot') }}</span>
            <span class="legend-item"><i class="fas fa-user"></i> {{ t('calendar.gridMine') }}</span>
          </p>
        </div>
      </section>

      <div class="calendar-main">
        <!-- 农事任务 -->
        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-list-check"></i></span>
            <h2 class="panel-title">{{ t('calendar.tasksOfMonth', { month }) }}</h2>
            <span class="panel-count">{{ t('calendar.taskCount', { count: taskTotal }) }}</span>
          </div>
          <div class="panel-body">
            <el-empty
              v-if="!taskGroups.length"
              :description="t('calendar.noTasks')"
              :image-size="70"
            />

            <div v-for="group in taskGroups" :key="group.crop_type" class="crop-group">
              <h3 class="crop-group-title">
                <i class="fas fa-leaf"></i> {{ cropLabel(group.crop_type, group.crop_type_en) }}
                <el-button
                  v-if="isAdmin"
                  size="small"
                  text
                  type="primary"
                  @click="openAddDialog(group.crop_type)"
                >
                  <i class="fas fa-plus"></i> {{ t('calendar.addTask') }}
                </el-button>
              </h3>

              <ul class="task-list">
                <li v-for="task in group.tasks" :key="task.id" class="task-item">
                  <span class="task-type" :class="`is-${task.task_type}`">{{ taskTypeLabel(task.task_type) }}</span>
                  <div class="task-body">
                    <div class="task-title-row">
                      <strong>{{ localizedField(task, 'title') }}</strong>
                      <!-- 第 77 批：用语言无关的 source_key 判断要不要显示来源（原来比中文串） -->
                      <span v-if="task.source_key !== 'template'" class="task-source">
                        {{ localizedField(task, 'source') }}
                      </span>
                    </div>
                    <p v-if="task.detail" class="task-detail">{{ localizedField(task, 'detail') }}</p>
                  </div>
                  <button
                    v-if="isAdmin"
                    type="button"
                    class="task-delete"
                    :title="t('common.delete')"
                    @click="removeTask(task)"
                  >
                    <i class="fas fa-trash"></i>
                  </button>
                </li>
              </ul>
            </div>
          </div>
        </section>

        <!-- 本月重点防范（真实统计） -->
        <aside class="calendar-side">
          <section class="panel-card">
            <div class="panel-head">
              <span class="panel-icon"><i class="fas fa-shield-virus"></i></span>
              <h2 class="panel-title">{{ t('calendar.keyPrevention', { month }) }}</h2>
            </div>
            <div class="panel-body">
              <p class="panel-hint">{{ t('calendar.keyPreventionHint') }}</p>
              <ul v-if="seasonalPests.length" class="pest-stat-list">
                <li v-for="item in seasonalPests" :key="item.identifier">
                  <RouterLink :to="item.url" class="pest-stat">
                    <span class="pest-stat-name">
                      {{ localizedField(item, 'crop_type') }}·{{ localizedField(item, 'name') }}
                    </span>
                    <span class="pest-stat-count">{{ item.count }} {{ t('calendar.times') }}</span>
                  </RouterLink>
                </li>
              </ul>
              <el-empty v-else :description="t('calendar.noRecords')" :image-size="60" />
            </div>
          </section>

          <section v-if="myHistory.length" class="panel-card">
            <div class="panel-head">
              <span class="panel-icon"><i class="fas fa-clock-rotate-left"></i></span>
              <h2 class="panel-title">{{ t('calendar.lastYear') }}</h2>
            </div>
            <div class="panel-body">
              <p class="panel-hint">{{ t('calendar.lastYearHint', { month }) }}</p>
              <ul class="pest-stat-list">
                <li v-for="item in myHistory" :key="item.name">
                  <span class="pest-stat">
                    <span class="pest-stat-name">
                      {{ localizedField(item, 'crop_type') }}·{{ localizedField(item, 'name') }}
                    </span>
                    <span class="pest-stat-count">{{ item.count }} {{ t('calendar.times') }}</span>
                  </span>
                </li>
              </ul>
            </div>
          </section>

          <RouterLink to="/alerts" class="side-link">
            <i class="fas fa-triangle-exclamation"></i> {{ t('calendar.viewAlerts') }}
          </RouterLink>
        </aside>
      </div>

      <p class="calendar-source">
        <i class="fas fa-circle-info"></i> {{ localizedField(sourceNote, 'source_note') }}
      </p>
    </template>

    <!-- 新增任务（仅管理员） -->
    <el-dialog v-model="addDialog" width="520px" class="form-dialog" :close-on-click-modal="false">
      <template #header>
        <div class="form-dialog-head">
          <span class="form-dialog-head-icon"><i class="fas fa-plus"></i></span>
          <div>
            <h3>{{ t('calendar.addDialogTitle') }}</h3>
            <p>{{ addForm.crop_type }} · {{ addForm.month }}</p>
          </div>
        </div>
      </template>
      <div class="form-dialog-body">
        <el-form label-position="top">
          <el-form-item :label="t('calendar.formTitle')">
            <el-input v-model="addForm.title" maxlength="120" :placeholder="t('calendar.formTitlePlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('calendar.formType')">
            <el-select v-model="addForm.task_type" class="full-width">
              <el-option v-for="item in taskTypes" :key="item.value" :value="item.value" :label="t(item.labelKey)" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('calendar.formDetail')">
            <el-input v-model="addForm.detail" type="textarea" :rows="3" resize="none" :placeholder="t('calendar.formDetailPlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('calendar.formMonth')">
            <el-input-number v-model="addForm.month" :min="1" :max="12" />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <div class="form-dialog-footer">
          <span class="footer-hint">{{ t('calendar.sourceHint') }}</span>
          <span>
            <el-button @click="addDialog = false">{{ t('common.cancel') }}</el-button>
            <el-button type="primary" :loading="saving" @click="submitTask">{{ t('common.save') }}</el-button>
          </span>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script>
/**
 * 种植日历（第 47 批）
 * ------------------------------------------------------------------
 * ① 农事任务：来自 `/api/calendar/` 的 task_groups（通用模板或管理员录入）；
 * ② 本月需重点防范：同一接口里的 seasonal_pests —— 完全来自本站识别记录统计；
 * ③ 去年这个时候：my_history —— 当前用户在这个月份识别过的病害。
 * 页面底部会显示 source_note，明确区分"模板"和"站内统计"两类内容。
 */
import { computed, onMounted, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { createCalendarTask, deleteCalendarTask, fetchCalendar } from '@/api/calendar';
import { formatApiError } from '@/api/http';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';  // 第 48 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 72 批：内容数据多语言

export default {
  name: 'CalendarView',
  setup() {
    const authStore = useAuthStore();
    const { t, locale } = useI18n();
    const { localizedField } = useLocalized();

    // 第 72 批：作物中/英文名映射（后端任务里带 crop_type_en，作物下拉的选项列表没有，
    // 所以用已加载到的任务把映射攒起来，英文界面下显示英文作物名）
    // 第 77 批：后端改为一次性下发 `crop_names_en`（覆盖可选作物 + 我种过的作物），
    // 下拉选项、分组标题、"你种过的作物"按钮都能直接取到英文名。
    const cropEnMap = ref({});

    const cropLabel = (cropType, knownEn) => {
      if (!cropType) return '';
      if (locale.value !== 'en') return cropType;
      return knownEn || cropEnMap.value[cropType] || cropType;
    };

    const loading = ref(false);
    const saving = ref(false);
    const month = ref(new Date().getMonth() + 1);
    const crop = ref('all');
    const crops = ref([]);
    const myCrops = ref([]);
    const taskGroups = ref([]);
    const taskTotal = ref(0);
    const seasonalPests = ref([]);
    const myHistory = ref([]);
    //: 第 216 批：月历网格的数据源。
    //: ⚠️ `dayActivity` 是"当天有多少条**识别记录**"，**不是**排定在那天的农事任务 ——
    //:    `CalendarTask` 只有月份粒度（没有日期字段），把任务摆到具体格子就是编数据。
    //:    `myDays` 是我自己那天有没有识别过，网格上单独标记，便于对照"我这块地"与"全站"。
    const dayActivity = ref([]);
    const myDays = ref([]);
    const weekdayLabels = computed(() => [
      t('calendar.weekdayMon'), t('calendar.weekdayTue'), t('calendar.weekdayWed'),
      t('calendar.weekdayThu'), t('calendar.weekdayFri'), t('calendar.weekdaySat'),
      t('calendar.weekdaySun'),
    ]);
    // 第 77 批：整条"内容来源"声明（中英各一份）由后端下发，前端按语言取
    const sourceNote = ref({ source_note: '', source_note_en: '' });
    const isCurrentMonth = ref(true);
    const currentMonth = new Date().getMonth() + 1;

    const addDialog = ref(false);
    const addForm = ref({ crop_type: '', month: 1, task_type: 'other', title: '', detail: '' });

    // 第 48 批：农事类型改成 i18n key（后端返回的 task_type_display 只在缺翻译时兜底）
    const taskTypes = [
      { value: 'nursery', labelKey: 'calendar.typeNursery' },
      { value: 'sowing', labelKey: 'calendar.typeSowing' },
      { value: 'planting', labelKey: 'calendar.typePlanting' },
      { value: 'fertilizer', labelKey: 'calendar.typeFertilizer' },
      { value: 'pruning', labelKey: 'calendar.typePruning' },
      { value: 'pest_control', labelKey: 'calendar.typePestControl' },
      { value: 'harvest', labelKey: 'calendar.typeHarvest' },
      { value: 'winter', labelKey: 'calendar.typeWinter' },
      { value: 'other', labelKey: 'calendar.typeOther' },
    ];

    const taskTypeLabel = (value) => {
      const found = taskTypes.find((item) => item.value === value);
      return found ? t(found.labelKey) : value;
    };

    const isAdmin = computed(() => Boolean(authStore.isAdmin));
    // 当月前后各一个月做快捷切换，避免 12 个小按钮挤成一片
    const quickMonths = computed(() => {
      const list = [currentMonth - 1, currentMonth, currentMonth + 1]
        .map((value) => (value < 1 ? 12 : value > 12 ? 1 : value));
      return Array.from(new Set(list)).sort((a, b) => a - b);
    });

    const load = async () => {
      loading.value = true;
      try {
        const data = await fetchCalendar({ month: month.value, crop: crop.value });
        crops.value = data.crops || [];
        myCrops.value = data.my_crops || [];
        taskGroups.value = data.task_groups || [];
        // 攒下 作物中文名 → 英文名 的映射，供下拉/筛选按钮显示英文
        // （后端第 77 批给的 crop_names_en 是全集，任务里的 crop_type_en 作为兜底补充）
        const map = { ...cropEnMap.value, ...(data.crop_names_en || {}) };
        for (const group of taskGroups.value) {
          if (group.crop_type && group.crop_type_en) map[group.crop_type] = group.crop_type_en;
        }
        cropEnMap.value = map;
        taskTotal.value = data.task_total || 0;
        seasonalPests.value = data.seasonal_pests || [];
        myHistory.value = data.my_history || [];
        //: 第 216 批：月历网格要的**按天活动量**（当天识别记录数，不是排定的任务日）
        dayActivity.value = data.day_activity || [];
        myDays.value = data.my_days || [];
        sourceNote.value = {
          source_note: data.source_note || '',
          source_note_en: data.source_note_en || '',
        };
        isCurrentMonth.value = Boolean(data.is_current_month);
      } catch (error) {
        ElMessage.error(formatApiError(error, t('calendar.loadFailed')));
      } finally {
        loading.value = false;
      }
    };

    const changeMonth = (delta) => {
      let next = month.value + delta;
      if (next < 1) next = 12;
      if (next > 12) next = 1;
      month.value = next;
      load();
    };

    const jumpMonth = (value) => {
      month.value = value;
      load();
    };

    const filterByCrop = (value) => {
      crop.value = crop.value === value ? 'all' : value;
      load();
    };

    const openAddDialog = (cropType) => {
      addForm.value = { crop_type: cropType, month: month.value, task_type: 'pest_control', title: '', detail: '' };
      addDialog.value = true;
    };

    const submitTask = async () => {
      if (!addForm.value.title.trim()) {
        ElMessage.warning(t('calendar.formTitle'));
        return;
      }
      saving.value = true;
      try {
        await createCalendarTask({
          crop_type: addForm.value.crop_type,
          month: addForm.value.month,
          task_type: addForm.value.task_type,
          title: addForm.value.title.trim(),
          detail: addForm.value.detail.trim(),
        });
        ElMessage.success(t('calendar.added'));
        addDialog.value = false;
        load();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('calendar.addFailed')));
      } finally {
        saving.value = false;
      }
    };

    const removeTask = async (task) => {
      try {
        await ElMessageBox.confirm(
          t('calendar.deleteConfirm', { title: localizedField(task, 'title') }),
          t('common.delete'),
          {
            type: 'warning',
            confirmButtonText: t('common.delete'),
            cancelButtonText: t('common.cancel'),
          },
        );
      } catch {
        return;
      }
      try {
        await deleteCalendarTask(task.id);
        ElMessage.success(t('calendar.deleted'));
        load();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('calendar.deleteFailed')));
      }
    };

    onMounted(load);

    /* ══════════════════════════════════════════════════════════════════════
     * 第 216 批：月历网格
     * ----------------------------------------------------------------------
     * ⚠️ 格子里标的是**这一天的识别记录数**（真实数据），**不是**"安排在那天的农事任务"。
     *    依据：`CalendarTask` 只有 `month` 字段、**没有日期** ——
     *    把 7 条番茄任务硬摆进 7 个格子，看起来像日程，实际是编的。
     *    而 `DetectionHistory.timestamp` 是真正的按天数据，用它画网格才诚实。
     *
     * 网格本身仍然解决用户真正想解决的问题：**一眼看出这个月哪几天田里问题集中**。
     * `calendar.gridHint` 会把口径明确写给用户，避免误读成日程表。
     * ══════════════════════════════════════════════════════════════════════ */

    /** 每格最大显示几个"点"（超过就只给数字，避免格子被点撑破） */
    const MAX_DOTS = 5;

    const monthGrid = computed(() => {
      const year = new Date().getFullYear();
      const m = Number(month.value) || 1;
      const first = new Date(year, m - 1, 1);
      const daysInMonth = new Date(year, m, 0).getDate();
      //: 周一为一周起点（中文习惯）；`getDay()` 里 0 是周日，换算成 0=周一
      const leading = (first.getDay() + 6) % 7;

      const byDay = new Map((dayActivity.value || []).map((x) => [Number(x.day), Number(x.count)]));
      const mine = new Set((myDays.value || []).map(Number));
      const today = new Date();
      const isThisMonth = today.getFullYear() === year && today.getMonth() + 1 === m;

      const cells = [];
      for (let i = 0; i < leading; i += 1) cells.push({ key: `pad-${i}`, pad: true });
      for (let day = 1; day <= daysInMonth; day += 1) {
        const count = byDay.get(day) || 0;
        cells.push({
          key: `d-${day}`,
          pad: false,
          day,
          count,
          dots: Math.min(count, MAX_DOTS),
          overflow: Math.max(0, count - MAX_DOTS),
          mine: mine.has(day),
          today: isThisMonth && today.getDate() === day,
        });
      }
      //: 补齐到整周，网格不出现缺角
      while (cells.length % 7 !== 0) cells.push({ key: `tail-${cells.length}`, pad: true });

      const weeks = [];
      for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
      return weeks;
    });

    /** 本月有记录的天数与总条数（网格上方的一句话摘要） */
    const activitySummary = computed(() => {
      const list = dayActivity.value || [];
      return {
        days: list.length,
        total: list.reduce((sum, x) => sum + (Number(x.count) || 0), 0),
      };
    });

    return {
      loading, saving, month, crop, crops, myCrops, taskGroups, taskTotal,
      seasonalPests, myHistory, sourceNote, isCurrentMonth, quickMonths, taskTypes,
      addDialog, addForm, isAdmin, t, taskTypeLabel,
      localizedField, cropLabel,
      //: 第 216 批：月历网格
      dayActivity, myDays, weekdayLabels, monthGrid, activitySummary,
      load, changeMonth, jumpMonth, filterByCrop, openAddDialog, submitTask, removeTask,
    };
  },
};
</script>

<style scoped>
.calendar-page {
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 24px 20px 40px;
}

.crop-select {
  width: 150px;
}

/* 月份条 */
.month-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  padding: 12px 16px;
  border: 1px solid var(--brand-150, #d8ece1);
  border-radius: var(--radius);
  background: #fff;
}

.month-nav {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--brand-200);
  border-radius: var(--radius-pill);
  background: #fff;
  color: var(--brand-700);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.18s ease;
}

.month-nav:hover {
  background: var(--brand-50);
}

.month-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.month-title strong {
  font-size: 20px;
  font-weight: 800;
  color: var(--ink-900);
}

.month-now {
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--brand-100);
  color: var(--brand-800, #1a5238);
  font-size: 11.5px;
  font-weight: 700;
}

.month-quick {
  display: flex;
  gap: 6px;
  margin-left: auto;
}

.quick-chip {
  padding: 5px 11px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #fff;
  color: var(--ink-600);
  font-size: 12.5px;
  cursor: pointer;
}

.quick-chip.is-active {
  background: var(--gradient-brand);
  border-color: transparent;
  color: #fff;
  font-weight: 700;
}

/* 我的作物 */
.my-crops {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 14px;
  font-size: 13px;
}

.my-crops-label {
  color: var(--ink-500);
}

.crop-chip {
  padding: 4px 12px;
  border: 1px solid var(--brand-200);
  border-radius: 999px;
  background: #fff;
  color: var(--brand-700);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}

.crop-chip.is-active {
  background: var(--brand-100);
  border-color: var(--brand-400);
}

/* 主区 */
/* ══ 第 216 批：月历网格 ═════════════════════════════════════════════════ */
.grid-card {
  margin-bottom: 16px;
}

.grid-hint {
  margin: 0 0 12px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-500, #6b7280);
}

.grid-hint i {
  margin-right: 4px;
  color: var(--brand-600);
}

.month-grid {
  display: grid;
  /* 7 列等宽：周一到周日 */
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
}

.grid-weekday {
  text-align: center;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-500, #6b7280);
  padding-bottom: 4px;
}

.grid-day {
  position: relative;
  min-height: 58px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 5px;
  background: var(--surface);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.grid-day.is-pad {
  border: none;
  background: transparent;
  min-height: 0;
}

.grid-day.is-today {
  border-color: var(--brand-500, #2f6b4f);
  box-shadow: inset 0 0 0 1px var(--brand-500, #2f6b4f);
}

.grid-day.has-data {
  background: var(--brand-50, #f0f7f3);
}

.grid-day-num {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-600, #4b5563);
  line-height: 1.2;
}

.grid-day.is-today .grid-day-num {
  color: var(--brand-700, #245a41);
}

.grid-dots {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  align-items: center;
  /*: ⚠️ `+N` 要单独占位：格子窄时它和圆点挤在同一行会叠在一起（实测 5 个点 + "+2" 溢出） */
  row-gap: 3px;
}

/*: 圆点本身 —— 别在改上面那条时把它误删（我第一版就删掉过一次） */
.grid-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--brand-600, #16a34a);
  display: inline-block;
}

.grid-overflow {
  font-size: 10px;
  color: var(--brand-700, #245a41);
  font-weight: 600;
  flex: 0 0 auto;          /* 不被挤扁 */
  margin-left: 1px;
}

.grid-count {
  margin-top: auto;
  font-size: 11px;
  font-weight: 700;
  color: var(--brand-700, #245a41);
  line-height: 1;
}

.grid-mine-mark {
  position: absolute;
  top: 3px;
  right: 4px;
  font-size: 9px;
  color: var(--brand-600, #16a34a);
}

.grid-empty {
  margin: 12px 0 0;
  font-size: 12.5px;
  color: var(--ink-400, #9aa4a0);
}

.grid-legend {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--ink-500, #6b7280);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.calendar-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 16px;
  align-items: start;
}

.calendar-side {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.crop-group + .crop-group {
  margin-top: 18px;
}

.crop-group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 9px;
  font-size: 15px;
  font-weight: 800;
  color: var(--ink-800);
}

.crop-group-title i {
  color: var(--brand-500);
}

.task-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 12px;
  border: 1px solid var(--brand-100);
  border-radius: var(--radius);
  background: linear-gradient(160deg, #ffffff, #f8fcfa);
}

.task-type {
  flex-shrink: 0;
  padding: 3px 9px;
  border-radius: 8px;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--brand-800, #1a5238);
  background: var(--brand-100);
}

.task-type.is-pest_control { background: #fdecea; color: #a32f22; }
.task-type.is-harvest { background: #fdf3e3; color: #8a5a12; }
.task-type.is-fertilizer { background: #e9f1fd; color: #2a6fdb; }
.task-type.is-winter { background: #eef2f7; color: #48596b; }
.task-type.is-nursery,
.task-type.is-planting { background: #eaf7f0; color: #1f6343; }

.task-body {
  flex: 1;
  min-width: 0;
}

.task-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.task-title-row strong {
  font-size: 13.8px;
  color: var(--ink-900);
}

.task-source {
  padding: 1px 7px;
  border-radius: 6px;
  background: var(--ink-50);
  color: var(--ink-500);
  font-size: 11px;
}

.task-detail {
  margin: 4px 0 0;
  font-size: 12.8px;
  line-height: 1.7;
  color: var(--ink-600);
}

.task-delete {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  color: var(--ink-400);
  cursor: pointer;
  transition: all 0.18s ease;
}

.task-delete:hover {
  border-color: #f3c9c3;
  color: #cf4436;
  background: #fdecea;
}

/* 侧栏统计 */
.panel-hint {
  margin: 0 0 10px;
  font-size: 12.3px;
  line-height: 1.7;
  color: var(--ink-500);
}

.panel-hint strong {
  color: var(--brand-700);
}

.pest-stat-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pest-stat {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 11px;
  border-radius: 10px;
  background: var(--ink-50);
  text-decoration: none;
  font-size: 13px;
}

a.pest-stat:hover {
  background: var(--brand-50);
}

.pest-stat-name {
  color: var(--ink-800);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pest-stat-count {
  flex-shrink: 0;
  color: var(--brand-700);
  font-weight: 800;
  font-size: 12.5px;
}

.side-link {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 11px;
  border: 1px solid #f0d9b0;
  border-radius: var(--radius);
  background: linear-gradient(120deg, #fdf6ea, #ffffff);
  color: #8a5a12;
  font-size: 13.3px;
  font-weight: 700;
  text-decoration: none;
}

.side-link:hover {
  background: #fdf3e3;
}

.calendar-source {
  margin: 18px 0 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--ink-400);
  text-align: center;
}

.calendar-source i {
  margin-right: 4px;
}

.full-width {
  width: 100%;
}

@media (max-width: 900px) {
  .calendar-main {
    grid-template-columns: minmax(0, 1fr);
  }

  .month-quick {
    margin-left: 0;
    width: 100%;
  }
}
</style>
