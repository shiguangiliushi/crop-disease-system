<template>
  <!--
    病害百科批量导入（第 44 批）
    ------------------------------------------------------------------
    管理员从 Excel/CSV 一次导入多条病害，避免一条条手录。
    流程：下载模板 → 上传文件 → 选导入模式 → 看逐行结果报告。
  -->
  <el-dialog
    v-model="visible"
    width="620px"
    :close-on-click-modal="false"
    class="form-dialog"
  >
    <template #header>
      <div class="form-dialog-head">
        <span class="form-dialog-head-icon"><i class="fas fa-file-import"></i></span>
        <div>
          <h3>{{ t('pestImport.title') }}</h3>
          <p>{{ t('pestImport.limitHint') }}</p>
        </div>
      </div>
    </template>

    <div class="form-dialog-body">
      <ol class="import-steps">
        <li>
          <span class="step-index">1</span>
          <div class="step-body">
            <p class="step-title">{{ t('pestImport.step1Title') }}</p>
            <p class="step-desc">
              {{ t('pestImport.step1Desc') }}
            </p>
            <el-button size="small" plain :loading="downloading" @click="downloadTemplate">
              <i class="fas fa-download"></i> {{ t('pestImport.downloadTemplate') }}
            </el-button>
          </div>
        </li>

        <li>
          <span class="step-index">2</span>
          <div class="step-body">
            <p class="step-title">{{ t('pestImport.step2Title') }}</p>
            <el-upload
              drag
              :auto-upload="false"
              :limit="1"
              :show-file-list="true"
              :on-change="handleFileChange"
              :on-remove="() => (file = null)"
              accept=".xlsx,.xlsm,.csv,.txt"
            >
              <i class="fas fa-cloud-upload-alt upload-icon"></i>
              <div class="upload-text">{{ t('pestImport.dropOr') }}<em>{{ t('pestImport.clickChoose') }}</em></div>
              <template #tip>
                <div class="upload-tip">{{ t('pestImport.fileTip') }}</div>
              </template>
            </el-upload>
          </div>
        </li>

        <li>
          <span class="step-index">3</span>
          <div class="step-body">
            <p class="step-title">{{ t('pestImport.modeTitle') }}</p>
            <el-radio-group v-model="mode">
              <el-radio value="upsert">{{ t('pestImport.modeUpsert') }}</el-radio>
              <el-radio value="create_only">{{ t('pestImport.modeCreateOnly') }}</el-radio>
            </el-radio-group>
          </div>
        </li>
      </ol>

      <!-- 导入结果 -->
      <section v-if="result" class="import-result">
        <h4 class="result-title">
          <i class="fas fa-clipboard-check"></i> {{ result.message }}
        </h4>
        <div class="result-tiles">
          <span class="result-tile is-ok">{{ t('pestImport.createdTile', { count: result.created }) }}</span>
          <span class="result-tile is-info">{{ t('pestImport.updatedTile', { count: result.updated }) }}</span>
          <span class="result-tile is-warn">{{ t('pestImport.skippedTile', { count: result.skipped }) }}</span>
        </div>

        <div v-if="result.errors?.length" class="error-list">
          <p class="error-title">{{ t('pestImport.errorsTitle') }}</p>
          <table class="error-table">
            <thead>
              <tr><th>{{ t('pestImport.colRow') }}</th><th>{{ t('pestImport.colReason') }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in result.errors" :key="item.row">
                <td>{{ t('pestImport.rowNumber', { row: item.row }) }}</td>
                <td>{{ item.message }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <template #footer>
      <div class="form-dialog-footer">
        <span class="footer-hint">
          <i class="fas fa-circle-info"></i> {{ t('pestImport.rowHint') }}
        </span>
        <span>
          <el-button @click="visible = false">{{ t('pestImport.close') }}</el-button>
          <el-button type="primary" :loading="importing" :disabled="!file" @click="submit">
            <i class="fas fa-file-import"></i> {{ t('pestImport.import') }}
          </el-button>
        </span>
      </div>
    </template>
  </el-dialog>
</template>

<script>
// 病害百科批量导入（管理端）。**组件说明写在模板顶部**（第 44 批的流程说明），
// 这里只补三件读代码时看不出来的事：
//   1. 导入模式 mode 默认是 **upsert（覆盖同名病害）**，不是 create_only ——
//      这是有意的：管理员导入通常是想"订正一批数据"，而不是"再插一遍"。
//      但覆盖是破坏性的，所以结果报告必须逐行给出（管理员得看到改了哪些）。
//   2. 下载模板走 downloadPestTemplate()（后端生成 xlsx），
//      **不是前端拼一个 CSV** —— 表头与校验规则只有后端那一份，避免两边分叉。
//   3. 模板里 accept 也放行了 .xlsm/.txt，真正能不能解析由后端的
//      views_pest_import.py 决定；前端不做格式判断（做了也会与后端不一致）。
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { downloadPestTemplate, importPests } from '@/api/pestImport';
import { formatApiError } from '@/api/http';
import { useI18n } from '@/i18n';  // 第 67 批：多语言

export default {
  name: 'PestImportDialog',
  props: {
    modelValue: { type: Boolean, default: false },
  },
  emits: ['update:modelValue', 'imported'],
  setup(props, { emit }) {
    const { t } = useI18n();  // 必须在 setup 内取，模板才能拿到
    const visible = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value),
    });

    const file = ref(null);
    const mode = ref('upsert');
    const importing = ref(false);
    const downloading = ref(false);
    const result = ref(null);

    watch(visible, (open) => {
      if (open) {
        result.value = null;
        file.value = null;
        mode.value = 'upsert';
      }
    });

    const handleFileChange = (uploadFile) => {
      file.value = uploadFile.raw || null;
      result.value = null;
    };

    const downloadTemplate = async () => {
      downloading.value = true;
      try {
        const blob = await downloadPestTemplate();
        const url = window.URL.createObjectURL(new Blob([blob]));
        const link = document.createElement('a');
        link.href = url;
        link.download = t('pestImport.templateFileName');
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      } catch (error) {
        ElMessage.error(formatApiError(error, t('pestImport.templateFailed')));
      } finally {
        downloading.value = false;
      }
    };

    const submit = async () => {
      if (!file.value) {
        ElMessage.warning(t('pestImport.emptyFile'));
        return;
      }
      importing.value = true;
      try {
        const data = await importPests(file.value, mode.value);
        result.value = data;
        ElMessage.success(data.message || t('pestImport.done'));
        emit('imported', data);
      } catch (error) {
        ElMessage.error(formatApiError(error, t('pestImport.importFailed')));
      } finally {
        importing.value = false;
      }
    };

    return {
      t,
      visible,
      file,
      mode,
      importing,
      downloading,
      result,
      handleFileChange,
      downloadTemplate,
      submit,
    };
  },
};
</script>

<style scoped>
.import-steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.import-steps li {
  display: flex;
  gap: 10px;
}

.step-index {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--brand-100, #e3f3ea);
  color: var(--brand-700, #1f6343);
  font-size: 12px;
  font-weight: 800;
}

.step-body {
  flex: 1;
  min-width: 0;
}

.step-title {
  margin: 0 0 3px;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--ink-800, #2c3a33);
}

.step-desc {
  margin: 0 0 8px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-500, #78897f);
}

.step-desc code {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--ink-50, #f4f8f6);
  color: var(--brand-700, #1f6343);
  font-size: 12px;
}

.upload-icon {
  font-size: 34px;
  color: var(--brand-300, #93cdad);
}

.upload-text {
  margin-top: 6px;
  font-size: 13px;
  color: var(--ink-600, #566b60);
}

.upload-text em {
  color: var(--brand-600, #2f8757);
  font-style: normal;
  font-weight: 700;
}

.upload-tip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--ink-400, #9dada5);
}

.import-result {
  margin-top: 16px;
  padding: 13px 14px;
  border: 1px solid var(--brand-200, #cfe9db);
  border-radius: var(--radius, 10px);
  background: linear-gradient(160deg, #f6fdf9, #ffffff);
}

.result-title {
  margin: 0 0 9px;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--brand-800, #1a5238);
}

.result-title i {
  margin-right: 5px;
}

.result-tiles {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.result-tile {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  background: var(--ink-50, #f4f8f6);
  color: var(--ink-600, #566b60);
}

.result-tile.is-ok { background: #e7f6ee; color: #1f6343; }
.result-tile.is-info { background: #e9f1fd; color: #2a6fdb; }
.result-tile.is-warn { background: #fdf3e3; color: #8a5a12; }

.error-list {
  margin-top: 12px;
}

.error-title {
  margin: 0 0 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: #a32f22;
}

.error-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
  max-height: 220px;
}

.error-table th {
  text-align: left;
  padding: 6px 8px;
  background: #fdecea;
  color: #a32f22;
}

.error-table td {
  padding: 6px 8px;
  border-bottom: 1px solid #f3e3e0;
  color: var(--ink-600, #566b60);
}
</style>
