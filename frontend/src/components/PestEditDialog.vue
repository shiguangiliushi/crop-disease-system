<script setup>
/**
 * 病害百科编辑弹窗（仅管理员使用）
 * - 新增 / 修改病害信息与图片
 * - 支持维护多条防治方法（类别 + 具体措施）
 */
import { computed, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { createPest, fetchPestDetail, formatPestError, updatePest, toAbsoluteMediaUrl } from '@/api/pest';
import { useI18n } from '@/i18n';  // 第 66 批：多语言

const { t } = useI18n();

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // 有值表示编辑，为空表示新增
  pestId: { type: [Number, String], default: null },
  // 可选的作物类型建议
  cropTypes: { type: Array, default: () => [] },
});

const emit = defineEmits(['update:modelValue', 'saved']);

// 防治类别标签走 i18n（value 与后端枚举一致）
const CATEGORY_KEYS = [
  { value: 'AGRICULTURAL', labelKey: 'prevent.agricultural' },
  { value: 'CHEMICAL', labelKey: 'prevent.chemical' },
  { value: 'ECOLOGICAL', labelKey: 'prevent.ecological' },
  { value: 'PHYSICAL', labelKey: 'prevent.physical' },
  { value: 'MONITORING', labelKey: 'prevent.monitoring' },
];
const CATEGORY_OPTIONS = computed(() => CATEGORY_KEYS.map((item) => ({ value: item.value, label: t(item.labelKey) })));

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
});

const isEdit = computed(() => !!props.pestId);
const dialogTitle = computed(() => (isEdit.value ? t('pestDetail.editPest') : t('wiki.addPest')));

const formRef = ref(null);
const loadingDetail = ref(false);
const submitting = ref(false);

const form = reactive({
  name: '',
  crop_type: '',
  english_identifier: '',
  symptoms: '',
  description: '',
  prevention_methods: [],
});

const imageFile = ref(null);
const imagePreview = ref('');
const existingImageUrl = ref('');
const clearImage = ref(false);

const rules = {
  // 第 83 批：后台病害编辑弹窗的校验文案接入 i18n（管理员在英文界面下也会看到）
  name: [{ required: true, message: t('pestEdit.nameRequired'), trigger: 'blur' }],
  crop_type: [{ required: true, message: t('pestEdit.cropRequired'), trigger: 'change' }],
  english_identifier: [
    { required: true, message: t('pestEdit.identifierRequired'), trigger: 'blur' },
    {
      // 历史数据形如 Apple___Apple_scab、Corn___Cercospora_leaf_spot Gray_leaf_spot，
      // 因此只限制会破坏 URL 的字符
      pattern: /^[^/\\?#]+$/,
      message: t('pestEdit.identifierInvalid'),
      trigger: 'blur',
    },
  ],
};

const resetForm = () => {
  Object.assign(form, {
    name: '',
    crop_type: '',
    english_identifier: '',
    symptoms: '',
    description: '',
    prevention_methods: [],
  });
  imageFile.value = null;
  imagePreview.value = '';
  existingImageUrl.value = '';
  clearImage.value = false;
  formRef.value?.clearValidate();
};

/** 打开弹窗时加载数据 */
const initDialog = async () => {
  resetForm();

  if (!props.pestId) {
    // 新增时默认给一条空的防治方法，方便直接填写。
    //
    // ⚠️ 第 122 批修：这一行原来默认带着 `category: 'AGRICULTURAL'`，
    //    而 `normalizeMethods()` 判定"空行"的依据是**分类与措施都为空** ——
    //    于是这条默认行永远算"填了一半"，新增时只要没动过它，
    //    点「保存」就会被拦下（只弹一句 3 秒后消失的 warning，看起来就像"保存没反应"）。
    //    默认行改成真正空行：不填就跳过，填了才校验。
    form.prevention_methods = [{ category: '', measure: '' }];
    return;
  }

  loadingDetail.value = true;
  try {
    const detail = await fetchPestDetail(props.pestId);
    Object.assign(form, {
      name: detail.name || '',
      crop_type: detail.crop_type || '',
      english_identifier: detail.english_identifier || '',
      symptoms: detail.symptoms || '',
      description: detail.description || '',
      prevention_methods: Array.isArray(detail.prevention_methods)
        ? detail.prevention_methods.map((item) => ({
            category: item.category || 'AGRICULTURAL',
            measure: item.measure || '',
          }))
        : [],
    });
    existingImageUrl.value = detail.image ? toAbsoluteMediaUrl(detail.image) : '';
  } catch (error) {
    console.error('加载病害详情失败:', error);
    ElMessage.error(formatPestError(error, t('pestEdit.loadFailed')));
    visible.value = false;
  } finally {
    loadingDetail.value = false;
  }
};

watch(
  () => props.modelValue,
  (value) => {
    if (value) initDialog();
  },
);

// ---------- 图片 ----------
const handleImageChange = (uploadFile) => {
  const raw = uploadFile?.raw;
  if (!raw) return;

  if (!raw.type.startsWith('image/')) {
    ElMessage.error(t('msg.imageOnly'));
    return;
  }
  if (raw.size / 1024 / 1024 >= 5) {
    ElMessage.error(t('msg.imageTooLarge5'));
    return;
  }

  imageFile.value = raw;
  clearImage.value = false;

  const reader = new FileReader();
  reader.onload = (event) => {
    imagePreview.value = event.target.result;
  };
  reader.readAsDataURL(raw);
};

const removeImage = () => {
  imageFile.value = null;
  imagePreview.value = '';
  existingImageUrl.value = '';
  clearImage.value = true;
};

const previewUrl = computed(() => imagePreview.value || existingImageUrl.value);

// ---------- 防治方法 ----------
const addMethod = () => {
  // 同上：新增的行也留成真正空行，不填就跳过（分类下拉自带 placeholder「分类」）
  form.prevention_methods.push({ category: '', measure: '' });
};

const removeMethod = (index) => {
  form.prevention_methods.splice(index, 1);
};

/** 只保留填写完整的防治方法 */
const normalizeMethods = () => {
  const cleaned = [];
  for (let index = 0; index < form.prevention_methods.length; index += 1) {
    const item = form.prevention_methods[index];
    const category = (item.category || '').trim();
    const measure = (item.measure || '').trim();

    if (!category && !measure) continue;
    if (!category || !measure) {
      ElMessage.warning(t('pestEdit.measureRowIncomplete', { index: index + 1 }));
      return null;
    }
    cleaned.push({ category, measure });
  }
  return cleaned;
};

// ---------- 提交 ----------
const handleSubmit = async () => {
  if (!formRef.value) return;

  try {
    await formRef.value.validate();
  } catch {
    return;
  }

  const preventionMethods = normalizeMethods();
  if (preventionMethods === null) return;

  submitting.value = true;
  try {
    const payload = {
      name: form.name.trim(),
      crop_type: form.crop_type.trim(),
      english_identifier: form.english_identifier.trim(),
      symptoms: form.symptoms,
      description: form.description,
      prevention_methods: preventionMethods,
      clear_image: clearImage.value,
    };

    if (isEdit.value) {
      const updated = await updatePest(props.pestId, payload, imageFile.value);
      ElMessage.success(t('pestEdit.savedUpdate'));
      visible.value = false;
      emit('saved', updated);
    } else {
      const created = await createPest(payload, imageFile.value);
      ElMessage.success(t('pestEdit.savedCreate'));
      visible.value = false;
      emit('saved', created);
    }
  } catch (error) {
    console.error('保存病害信息失败:', error);
    ElMessage.error(formatPestError(error, t('pestEdit.saveFailed')));
  } finally {
    submitting.value = false;
  }
};
</script>

<template>
  <el-dialog
    v-model="visible"
    width="780px"
    top="6vh"
    :close-on-click-modal="false"
    class="form-dialog"
  >
    <!-- 第 33 批：原来用的是弹窗默认标题栏（一行灰字），现在换成"深绿头条 + 说明" -->
    <template #header>
      <div class="form-dialog-head">
        <span class="form-dialog-head-icon">
          <i :class="isEdit ? 'fas fa-pen-to-square' : 'fas fa-plus'"></i>
        </span>
        <div>
          <h3>{{ dialogTitle }}</h3>
          <p>
            {{ isEdit
              ? t('pestEdit.editHint')
              : t('pestEdit.createHint') }}
          </p>
        </div>
      </div>
    </template>

    <div v-loading="loadingDetail" class="form-dialog-body pest-edit-body">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <!-- 基本信息 -->
        <section class="form-section">
          <div class="form-section-head">
            <i class="fas fa-circle-info"></i>
            <h4>{{ t('pestEdit.basicInfo') }}</h4>
            <span class="section-hint">{{ t('pestEdit.basicInfoHint') }}</span>
          </div>

          <el-row :gutter="16">
            <el-col :xs="24" :sm="12">
              <el-form-item :label="t('pestEdit.name')" prop="name">
                <el-input v-model="form.name" maxlength="100" :placeholder="t('pestEdit.namePlaceholder')" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item :label="t('pestEdit.cropType')" prop="crop_type">
                <el-select
                  v-model="form.crop_type"
                  filterable
                  allow-create
                  default-first-option
                  :placeholder="t('pestEdit.cropPlaceholder')"
                  style="width: 100%"
                >
                  <!--
                    ⚠️ 第 190 批：`cropTypes` 的每一项是 `{ key, label }`（键=库里 crop_type 原值，
                    显示名按语言取）。原来这里把数组项当**字符串**用（`v-for="crop in cropTypes"` +
                    `:value="crop"`），一旦上游改成对象，下拉里就会显示成 `[object Object]`。
                    `allow-create` 保留：管理员可以录入库里还没有的新作物名。
                  -->
                  <el-option
                    v-for="crop in cropTypes"
                    :key="crop.key"
                    :label="crop.label"
                    :value="crop.key"
                  />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>

          <el-form-item :label="t('pestEdit.identifier')" prop="english_identifier">
            <div class="pest-field-block">
              <el-input
                v-model="form.english_identifier"
                :placeholder="t('pestEdit.identifierPlaceholder')"
              />
              <p v-if="isEdit" class="field-hint is-warning">
                <i class="fas fa-triangle-exclamation"></i>
                {{ t('pestEdit.identifierWarn') }}
              </p>
              <p v-else class="field-hint">
                {{ t('pestEdit.identifierHint') }}
              </p>
            </div>
          </el-form-item>
        </section>

        <!-- 症状与规律 -->
        <section class="form-section">
          <div class="form-section-head">
            <i class="fas fa-stethoscope"></i>
            <h4>{{ t('pestEdit.symptomsSection') }}</h4>
            <span class="section-hint">{{ t('pestEdit.symptomsSectionHint') }}</span>
          </div>

          <el-form-item :label="t('pestEdit.symptoms')" prop="symptoms">
            <el-input
              v-model="form.symptoms"
              type="textarea"
              :rows="3"
              resize="none"
              :placeholder="t('pestEdit.symptomsPlaceholder')"
            />
          </el-form-item>

          <el-form-item :label="t('pestEdit.pattern')" prop="description">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="3"
              resize="none"
              :placeholder="t('pestEdit.patternPlaceholder')"
            />
          </el-form-item>
        </section>

        <!-- 病害图片 -->
        <section class="form-section">
          <div class="form-section-head">
            <i class="fas fa-image"></i>
            <h4>{{ t('pestEdit.imageSection') }}</h4>
            <span class="section-hint">{{ t('pestEdit.imageSectionHint') }}</span>
          </div>

          <el-form-item :label="t('pestEdit.image')">
            <div class="pest-image-field">
              <el-upload
                class="pest-image-uploader"
                :auto-upload="false"
                :show-file-list="false"
                accept="image/*"
                :on-change="handleImageChange"
              >
                <div class="upload-tile pest-image-tile">
                  <img v-if="previewUrl" :src="previewUrl" :alt="t('pestEdit.imagePreviewAlt')" />
                  <div v-else class="upload-tile-empty">
                    <i class="fas fa-cloud-arrow-up"></i>
                    <span>{{ t('pestEdit.uploadImage') }}</span>
                    <small>{{ t('pestEdit.imageFormats') }}</small>
                  </div>
                  <div v-if="previewUrl" class="upload-tile-actions">
                    <button type="button" :title="t('pestEdit.changeImage')">
                      <i class="fas fa-rotate"></i>
                    </button>
                    <button type="button" :title="t('pestEdit.removeImage')" @click.stop="removeImage">
                      <i class="fas fa-trash"></i>
                    </button>
                  </div>
                </div>
              </el-upload>

              <p class="field-hint pest-image-note">
                {{ t('pestEdit.imageTip') }}
              </p>
            </div>
          </el-form-item>
        </section>

        <!-- 防治方法 -->
        <section class="form-section">
          <div class="form-section-head">
            <i class="fas fa-shield-halved"></i>
            <h4>{{ t('pestEdit.preventionSection') }}</h4>
            <span class="section-hint">{{ t('pestEdit.preventionSectionHint') }}</span>
          </div>

          <el-form-item :label="t('pestEdit.preventionSection')">
            <div class="pest-methods">
              <div v-if="form.prevention_methods.length === 0" class="pest-methods-empty">
                <i class="fas fa-circle-info"></i> {{ t('pestEdit.preventionEmpty') }}
              </div>

              <div
                v-for="(method, index) in form.prevention_methods"
                :key="index"
                class="pest-method-row"
              >
                <span class="pest-method-index">{{ index + 1 }}</span>
                <el-select v-model="method.category" :placeholder="t('pestEdit.categoryLabel')" style="width: 132px">
                  <el-option
                    v-for="option in CATEGORY_OPTIONS"
                    :key="option.value"
                    :label="option.label"
                    :value="option.value"
                  />
                </el-select>
                <el-input
                  v-model="method.measure"
                  type="textarea"
                  :rows="2"
                  resize="none"
                  :placeholder="t('pestEdit.measurePlaceholder')"
                />
                <el-button
                  class="pest-method-remove"
                  text
                  type="danger"
                  :title="t('pestEdit.deleteRow')"
                  @click="removeMethod(index)"
                >
                  <i class="fas fa-trash"></i>
                </el-button>
              </div>

              <el-button class="pest-methods-add" plain @click="addMethod">
                <i class="fas fa-plus"></i> {{ t('pestEdit.addMeasure') }}
              </el-button>
            </div>
          </el-form-item>
        </section>
      </el-form>
    </div>

    <template #footer>
      <div class="form-dialog-footer">
        <span class="footer-hint">
          <i class="fas fa-shield-halved"></i> {{ t('pestEdit.saveNow') }}
        </span>
        <span>
          <el-button @click="visible = false">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            <i class="fas fa-check"></i> {{ t('profile.save') }}
          </el-button>
        </span>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
/* 第 33 批：弹窗外壳 / 分段 / 底部操作条都改用 theme.css 里的公用块
   （.form-dialog-head / .form-section / .form-dialog-footer），
   这里只保留本表单特有的部分。 */
.pest-edit-body {
  padding-top: 4px;
}

.pest-field-block {
  width: 100%;
}

.pest-image-field {
  width: 100%;
}

/* 上传瓦片：让 el-upload 的默认外壳消失，瓦片自己撑满一栏 */
.pest-image-uploader {
  display: block;
  width: 100%;
}

.pest-image-uploader :deep(.el-upload) {
  display: block;
  width: 100%;
}

.pest-image-tile {
  min-height: 176px;
}

.pest-image-note {
  margin-top: 10px;
}

.pest-methods {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pest-methods-empty {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 14px 16px;
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  background: var(--ink-50);
  font-size: 13px;
  color: var(--ink-500);
}

.pest-methods-empty i {
  color: var(--brand-500);
}

/* 防治方法行：编号 + 类别 + 措施 + 删除 */
.pest-method-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--brand-100);
  border-radius: var(--radius);
  background: linear-gradient(160deg, #ffffff, #f6fbf8);
}

.pest-method-index {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  margin-top: 6px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 800;
  color: var(--brand-700);
  background: var(--brand-100);
}

.pest-method-row :deep(.el-textarea) {
  flex: 1;
}

.pest-method-remove {
  margin-top: 4px;
}

.pest-methods-add {
  align-self: flex-start;
  border-style: dashed;
}
</style>

