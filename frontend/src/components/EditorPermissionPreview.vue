<template>
  <!--
    第 179 批：开通/修改编辑员时的"他能做什么"预览
    ----------------------------------------------------------------------------
    授权的人（全权管理员）勾模块时，不必凭记忆猜：
    勾了哪几项，这里就实时列出他能进哪一页、能做哪几件事。

    数据来源：
      · 模块清单与"能做什么"来自 `GET /api/admin/role-matrix/`
        （与后端自查命令 `manage.py role_matrix` **同一份表**）；
      · 文案走 i18n（后端表里是中文，界面要支持中英）。
    接口取不到时退回 authStore 的模块清单 —— **绝不因为一个提示接口失败
    就让"开通编辑员"这件事做不成**。
  -->
  <div v-if="modules.length" class="perms-preview">
    <p class="perms-title">
      <i class="fas fa-circle-info"></i> {{ t('editorPerms.title') }}
    </p>
    <ul class="perms-list">
      <li v-for="module in modules" :key="module" class="perms-item">
        <span class="perms-module">{{ t(`contentModule.${module}`) }}</span>
        <span class="perms-functions">{{ functionsOf(module) }}</span>
      </li>
    </ul>
    <p class="perms-hint">{{ t('editorPerms.hint') }}</p>
  </div>
  <p v-else class="perms-empty">{{ t('editorPerms.empty') }}</p>
</template>

<script>
/**
 * 编辑员权限预览（第 179 批）
 *
 * 为什么单独抽一个组件：**两个地方**要用它 —— 「开通编辑员」对话框与「修改角色」对话框。
 * 早先这两处的模块勾选框是各写一份的（文案也各写各的），抽出来就不容易只改一处。
 */
import { onMounted, ref } from 'vue';
import { fetchRoleMatrix } from '@/api/adminUser';
import { useI18n } from '@/i18n';

export default {
  name: 'EditorPermissionPreview',
  props: {
    /** 当前勾选的模块（如 ['news', 'pests']） */
    modules: {
      type: Array,
      default: () => [],
    },
  },
  setup() {
    const { t } = useI18n();
    /** 后端 matrix 里的模块 → 它能做的动作（接口失败时为空对象，走 i18n 兜底文案） */
    const backendFunctions = ref({});

    /**
     * 一个模块"能做什么"
     *
     * 优先用**后端表**里的动作清单（那是唯一来源）；但界面要中英双语，
     * 所以实际上优先用 i18n 里那句人话总结 `editorPerms.functions.<模块>`，
     * 取不到再退回后端的中文清单（例如后端新加了模块、前端还来不及翻译）。
     */
    const functionsOf = (module) => {
      const key = `editorPerms.functions.${module}`;
      const text = t(key);
      if (text && text !== key) return text;
      const list = backendFunctions.value[module];
      return Array.isArray(list) ? list.join('；') : t('editorPerms.unknownModule');
    };

    onMounted(async () => {
      try {
        const data = await fetchRoleMatrix();
        const map = {};
        for (const item of data?.modules || []) {
          map[item.key] = item.functions || [];
        }
        backendFunctions.value = map;
      } catch (error) {
        // 提示接口挂了不该挡住授权本身
        console.warn('[editorPerms] 权限矩阵获取失败，改用内置文案:', error?.message || error);
      }
    });

    return { t, functionsOf };
  },
};
</script>

<style scoped>
.perms-preview {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--el-color-primary-light-9, #f0f9f4);
  border: 1px solid var(--el-color-primary-light-7, #c8e6d4);
}

.perms-title {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary, #2e7d32);
}

.perms-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.perms-item {
  display: flex;
  gap: 8px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-700, #46564d);
}

.perms-module {
  flex-shrink: 0;
  min-width: 76px;
  font-weight: 600;
}

.perms-hint,
.perms-empty {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--ink-400, #9dada5);
  line-height: 1.6;
}
</style>
