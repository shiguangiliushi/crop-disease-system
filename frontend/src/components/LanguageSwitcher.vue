<template>
  <!-- 语言切换（第 48 批）：顶栏小地球 + 当前语言，点开切换 -->
  <el-dropdown trigger="click" @command="handleCommand">
    <button type="button" class="lang-btn" :title="t('language.label')">
      <i class="fas fa-globe"></i>
      <span class="lang-text">{{ shortLabel }}</span>
    </button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="item in locales"
          :key="item.value"
          :command="item.value"
          :class="{ 'is-current': item.value === locale }"
        >
          <i class="fas" :class="item.value === locale ? 'fa-circle-check' : 'fa-circle'"></i>
          {{ t(item.labelKey) }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script>
import { computed } from 'vue';
import { ElMessage } from 'element-plus';
import { locale, setLocale, t, SUPPORTED_LOCALES } from '@/i18n';

export default {
  name: 'LanguageSwitcher',
  setup() {
    const locales = SUPPORTED_LOCALES;
    const shortLabel = computed(() => (locale.value === 'en' ? 'EN' : '中'));

    const handleCommand = (value) => {
      if (value === locale.value) return;
      if (!setLocale(value)) return;
      const name = t(value === 'en' ? 'language.en' : 'language.zh');
      ElMessage.success(t('language.switched', { name }));
    };

    return { locales, locale, shortLabel, handleCommand, t };
  },
};
</script>

<style scoped>
.lang-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 36px;
  padding: 0 11px;
  border: 1px solid var(--border, #e2ebe5);
  border-radius: var(--radius-pill, 999px);
  background: var(--surface, #fff);
  color: var(--ink-600, #566b60);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s ease;
}

.lang-btn:hover {
  border-color: var(--brand-400, #5fb088);
  color: var(--brand-700, #1f6343);
}

.lang-text {
  line-height: 1;
}

:deep(.el-dropdown-menu__item.is-current) {
  color: var(--brand-700, #1f6343);
  font-weight: 700;
}

@media (max-width: 768px) {
  .lang-btn {
    height: 42px;
    padding: 0 13px;
    font-size: 14px;
  }
}
</style>
