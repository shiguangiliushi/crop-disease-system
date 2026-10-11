<template>
  <div class="pest-tag-picker">
    <!-- 已选标签 -->
    <div v-if="selected.length" class="tag-chips">
      <span v-for="tag in selected" :key="tag.id" class="tag-chip">
        <i class="fas fa-virus"></i>
        {{ localizedField(tag, 'name') }}
        <button type="button" class="chip-remove" :title="t('pestTag.remove')" @click="remove(tag.id)">
          <i class="fas fa-times"></i>
        </button>
      </span>
    </div>

    <!-- 选择器：搜索病害词条 -->
    <el-select
      v-model="pending"
      class="tag-select"
      filterable
      remote
      clearable
      reserve-keyword
      :remote-method="search"
      :loading="loading"
      :placeholder="t('pestTag.placeholder')"
      @change="onPick"
    >
      <el-option
        v-for="option in options"
        :key="option.id"
        :label="optionLabel(option)"
        :value="option.id"
        :disabled="isSelected(option.id)"
      />
      <template #empty>
        <p class="tag-empty">{{ t('pestTag.empty') }}</p>
      </template>
    </el-select>

    <p class="tag-hint">{{ t('pestTag.hint') }}</p>
  </div>
</template>

<script>
/**
 * 帖子病害标签选择器（第 168 批）
 * ============================================================================
 * ## 为什么要有
 *
 * 评审意见："不能给帖子打『苹果黑星病』这种标签，后期没法按病害聚合讨论。"
 * 标签是 `Post ↔ PestInfo` 的多对多，后端已支持 `pest_ids`（写）与 `pests`（读），
 * 以及 `?pest=<id>` 筛选 —— 这个组件负责让作者把标签选上。
 *
 * ## 用法
 *
 * ```vue
 * <PestTagPicker v-model="form.pest_ids" />
 * ```
 *
 * `v-model` 绑定的是**词条 id 数组**（提交给后端的就是它）。
 * 组件内部另外维护一份 `selected`（含名字），用于渲染中文胶囊 ——
 * 因为这排胶囊需要在"还没提交、也没有 id→名字映射"的情况下也能显示名字。
 *
 * ## 一个刻意的取舍
 *
 * 远端搜索失败时**不报错**，只是把选项列表留空：标签是"锦上添花"的字段，
 * 不该因为词条接口抖了一下就让人发不出帖子。
 */
import { onMounted, ref, watch } from 'vue';
import { fetchPestDetail, fetchPestList } from '@/api/pest';
import { useI18n } from '@/i18n';
import { useLocalized } from '@/utils/localized';

export default {
  name: 'PestTagPicker',
  props: {
    modelValue: {
      type: Array,
      default: () => [],
    },
    /** 已经知道名字的标签（编辑页从帖子详情带过来，省一次查询） */
    initialTags: {
      type: Array,
      default: () => [],
    },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    const { t } = useI18n();
    const { localizedField } = useLocalized();
    const options = ref([]);
    const selected = ref([]);
    const pending = ref(null);
    const loading = ref(false);

    /** 选项标签：中文名（作物）—— 同名不同作物时能区分开 */
    const optionLabel = (option) => {
      const name = localizedField(option, 'name') || option.name || '';
      const crop = localizedField(option, 'crop_type') || option.crop_type || '';
      return crop ? `${name}（${crop}）` : name;
    };

    const isSelected = (id) => selected.value.some((tag) => tag.id === id);

    const emitValue = () => emit('update:modelValue', selected.value.map((tag) => tag.id));

    const add = (option) => {
      if (!option?.id || isSelected(option.id)) return;
      selected.value = [...selected.value, option];
      emitValue();
    };

    const remove = (id) => {
      selected.value = selected.value.filter((tag) => tag.id !== id);
      emitValue();
    };

    const onPick = (id) => {
      pending.value = null;   // 选完清空，方便连续选下一个
      if (!id) return;
      const option = options.value.find((item) => item.id === id);
      if (option) add(option);
    };

    const normalize = (response) => {
      const list = Array.isArray(response) ? response : (response?.results || response?.data || []);
      return Array.isArray(list) ? list : [];
    };

    /**
     * 搜索词条。
     * 没传关键词时也拉一批（page_size=20）—— 农户未必知道病害的学名怎么写，
     * 直接给一屏常见病害让他挑，比逼他打字更现实。
     */
    const search = async (keyword = '') => {
      loading.value = true;
      try {
        const response = await fetchPestList({ search: keyword || undefined, page_size: 20 });
        options.value = normalize(response);
      } catch (error) {
        console.warn('[pestTag] 病害词条搜索失败（不影响发帖）:', error?.message || error);
        options.value = [];
      } finally {
        loading.value = false;
      }
    };

    // 外部传入初始标签（编辑页）：收敛成 {id, name...} 形状
    watch(
      () => props.initialTags,
      (tags) => {
        if (!tags?.length) return;
        if (selected.value.length) return;   // 用户已经选过，不要覆盖
        selected.value = tags.map((tag) => ({ ...tag }));
      },
      { immediate: true, deep: true },
    );

    /**
     * 外部改 modelValue 时同步胶囊
     *
     * 两种情形都要处理：
     *   · **清空**（"重置表单"）：胶囊跟着清掉；
     *   · **只给了 id、我们还不知道名字**（识别页「发帖求助」把病害 id 带过来预选）：
     *     这种情况如果不管，标签其实已经选上了、界面上却是空的 —— 用户看不到自己选了什么，
     *     再点一次选择器还会重复添加。所以这里按 id 补查一次词条，把名字取回来。
     *     （实测过 `/api/pests/<id>/` 与 `/api/pests/<english_identifier>/` 都能取详情。）
     */
    watch(
      () => props.modelValue,
      async (ids) => {
        const list = Array.isArray(ids) ? ids : [];
        if (!list.length) {
          if (selected.value.length) selected.value = [];
          return;
        }
        const unknown = list.filter((id) => !selected.value.some((tag) => tag.id === id));
        for (const id of unknown) {
          try {
            // eslint-disable-next-line no-await-in-loop —— 一次最多几个，逐个补齐
            const detail = await fetchPestDetail(id);
            if (detail?.id && !selected.value.some((tag) => tag.id === detail.id)) {
              selected.value = [...selected.value, detail];
            }
          } catch (error) {
            console.warn('[pestTag] 补齐标签名字失败:', id, error?.message || error);
          }
        }
      },
      { immediate: true },
    );

    onMounted(() => search(''));

    return {
      t, options, selected, pending, loading,
      localizedField, optionLabel, isSelected, remove, onPick, search,
    };
  },
};
</script>

<style scoped>
.pest-tag-picker {
  width: 100%;
}

.tag-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: #eef7f2;
  border: 1px solid var(--brand-300, #a9d6bf);
  color: var(--brand-700, #276b4a);
  font-size: 13px;
}

.chip-remove {
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  padding: 0;
  font-size: 11px;
  opacity: 0.7;
}

.chip-remove:hover {
  opacity: 1;
}

.tag-select {
  width: 100%;
  max-width: 420px;
}

.tag-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--ink-400, #9dada5);
  line-height: 1.6;
}

.tag-empty {
  margin: 0;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--ink-400, #9dada5);
}
</style>
